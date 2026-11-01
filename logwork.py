#!/usr/bin/env python3
"""logwork.py — Server + static snapshot for the combined 2-Jira logwork grid.

Shows per-team / per-member / per-day hours logged on BOTH Jira workspaces:
  - enotion  (config.json)   https://enotion.atlassian.net   -> ALL boards
  - vortech  (vortechinc.json) https://vvortech.atlassian.net -> project APK (APEK board)
    (scope per site is configurable in SITE_PROJECT below / --vortech-project)

Run as a live web server (default):
    ~/chatbot-discord/.venv/bin/python logwork.py --port 8765
    then open http://127.0.0.1:8765/

Or emit a self-contained (offline) snapshot with the data baked in:
    ~/chatbot-discord/.venv/bin/python logwork.py --static out.html [--from 2026-10-19 --to 2026-10-30]

The same person often has a DIFFERENT accountId on each site but the SAME
display name / leading numeric id, so worklog is combined across sites by that
ID prefix (fallback: normalized display name).
"""
from __future__ import annotations

import base64
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
JIRA_DIR = Path.home() / ".jira-connect"
SITE_FILES = {"enotion": "config.json", "vortech": "vortechinc.json"}
# project scope per site: "" = ALL boards
SITE_PROJECT = {"enotion": "", "vortech": os.environ.get("VORTECH_PROJECT", "APK")}
MEMBERS_FILE = HERE / "members.json"
FILTER_FILE = HERE / "filter.json"

TEAM_ORDER = ["Default", "GD", "Static", "Anim", "FE", "QC", "3D", "PM", "RND", "Khác"]
# display-name suffix token -> canonical team bucket
SUFFIX_TEAM = {
    "UI": "Static", "CONCEPT": "Static", "CONCEPTART": "Static", "STATIC": "Static",
    "ART": "Static", "ARTS": "Static",
    "ANIM": "Anim", "ANIMATION": "Anim", "3DANIM": "Anim",
    "FE": "FE", "GD": "GD", "QC": "QC", "3D": "3D", "3DMODEL": "3D", "3DVFX": "3D",
    "PMA": "PM", "PM": "PM", "PA": "PM", "PROJECTASSISTANT": "PM",
    "RND": "RND", "R&D": "RND",
}
# members not carrying a leading id keep their full name
_NAME_FALLBACK = re.compile(r"^\s*(\d+)")


def _creds(site: str) -> tuple[str, str]:
    # prefer env vars (CI / Vercel build), fall back to local ~/.jira-connect files
    env = site.upper()
    u = os.environ.get(f"JIRA_{env}_URL")
    e = os.environ.get(f"JIRA_{env}_EMAIL")
    t = os.environ.get(f"JIRA_{env}_TOKEN")
    if u and e and t:
        return u.rstrip("/"), base64.b64encode(f"{e}:{t}".encode()).decode()
    fname = SITE_FILES.get(site, "config.json")
    d = json.load(open(JIRA_DIR / fname))
    tok = base64.b64encode(f"{d['email']}:{d['api_token']}".encode()).decode()
    return d["url"].rstrip("/"), tok


def _get(url: str, tok: str, path: str, params=None):
    q = "?" + urllib.parse.urlencode(params) if params else ""
    req = urllib.request.Request(
        url + path + q,
        headers={"Authorization": f"Basic {tok}", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.loads(r.read().decode())


# ---------- roster ----------
def load_roster() -> list[dict]:
    """[{id, jira_id, team}] from members.json (fallback embedded)."""
    if MEMBERS_FILE.exists():
        try:
            return json.loads(MEMBERS_FILE.read_text())
        except Exception:
            pass
    return EMBED_ROSTER


EMBED_ROSTER: list[dict] = []


def refresh_members() -> list[dict]:
    try:
        sys.path.insert(0, str(Path.home() / "chatbot-discord" / "src"))
        import drive_tools  # noqa: F401
    except Exception as exc:
        print(f"[roster] drive_tools unavailable ({exc}); keeping existing.", file=sys.stderr)
        return load_roster()
    seen = set()
    out = []
    for m in drive_tools.studio_members(force=True).get("members", []):
        jid = (m.get("jira_id") or "").strip()
        team = (m.get("team") or "Static").strip()
        if not jid or jid in seen:
            continue
        seen.add(jid)
        out.append({"id": (m.get("id") or "").strip(), "jira_id": jid, "team": team})
    MEMBERS_FILE.write_text(json.dumps(out, ensure_ascii=False, indent=2))
    return out


# ---------- member filter ----------
def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _load_filter() -> tuple[set, set] | None:
    """Return (allowed_ids, allowed_names) from filter.json, or None (show all).

    filter.json = list of member labels (e.g. "563-vu.ngo-GD"). Matching is by
    the leading numeric id (cross-site safe) OR the normalized display name.
    """
    if not FILTER_FILE.exists():
        return None
    try:
        data = json.loads(FILTER_FILE.read_text())
    except Exception:
        return None
    labels = []
    if isinstance(data, list):
        labels = [str(x) for x in data]
    elif isinstance(data, dict):
        labels = [str(x) for x in data.get("members", [])]
    ids, names = set(), set()
    for lb in labels:
        lb = lb.strip()
        if not lb:
            continue
        names.add(_norm(lb))
        m = re.match(r"^\s*(\d+)", lb)
        if m:
            ids.add(m.group(1))
    if not ids and not names:
        return None
    return (ids, names)


# ---------- worklog fetch ----------
def _worklogs_all(url: str, tok: str, date_from: str, date_to: str,
                  project: str = "", cap_issues: int = 2000) -> list[dict]:
    jql = f"worklogDate >= {date_from} AND worklogDate <= {date_to}"
    if project:
        jql = f"project = {project} AND {jql}"
    keys = []
    summ = {}
    token = None
    guard = 0
    while guard < 200:
        params = {"jql": jql, "maxResults": 100, "fields": "key,summary"}
        if token:
            params["nextPageToken"] = token
        res = _get(url, tok, "/rest/api/3/search/jql", params) or {}
        batch = res.get("issues") or []
        for it in batch:
            k = it.get("key")
            if k:
                keys.append(k)
                summ[k] = (it.get("fields") or {}).get("summary") or ""
        if res.get("isLast") or not res.get("nextPageToken") or not batch:
            break
        if len(keys) >= cap_issues:
            keys = keys[:cap_issues]
            break
        token = res.get("nextPageToken")
        guard += 1

    def _fetch(key):
        out = []
        start = 0
        try:
            while True:
                r = _get(url, tok, f"/rest/api/3/issue/{key}/worklog",
                         {"startAt": start, "maxResults": 100}) or {}
                wl = r.get("worklogs") or []
                out.extend(wl)
                if r.get("total", 0) <= start + len(wl) or not wl:
                    break
                start += len(wl)
        except Exception:
            return []
        return out

    entries = []
    with ThreadPoolExecutor(max_workers=16) as ex:
        for key, res in zip(keys, ex.map(_fetch, keys)):
            summary = summ.get(key, "")
            for w in res:
                started = (w.get("started") or "")
                day = started[:10]
                if not day or not (date_from <= day <= date_to):
                    continue
                au = w.get("author") or {}
                sec = int(w.get("timeSpentSeconds") or 0)
                if sec <= 0:
                    continue
                entries.append({
                    "accountId": (au.get("accountId") or "").strip(),
                    "displayName": (au.get("displayName") or "").strip(),
                    "day": day,
                    "seconds": sec,
                    "issueKey": key,
                    "summary": summary,
                })
    return entries


def _team_from_name(display: str) -> str:
    low = (display or "").strip().upper()
    if not low:
        return "Khác"
    tok = re.split(r"[-_\s]+", low)
    tok = [t for t in tok if t]
    last = tok[-1] if tok else ""
    return SUFFIX_TEAM.get(last, last or "Khác")


def _person_key(display: str, accountId: str, roster_by_jid: dict) -> str:
    """Cross-site stable key: leading numeric id, else normalized display name."""
    if accountId in roster_by_jid:
        return "id:" + roster_by_jid[accountId]
    m = _NAME_FALLBACK.match(display or "")
    if m:
        return "id:" + m.group(1)
    return "name:" + re.sub(r"\s+", " ", (display or "").strip().lower())


_cache: dict[str, dict] = {}


def build_grid(date_from: str, date_to: str) -> dict:
    key = (date_from, date_to)
    if key in _cache:
        return _cache[key]

    roster = load_roster()
    # roster index by jira_id -> id (for cross-site keying)
    roster_by_jid = {m.get("jira_id", ""): m.get("id", "") for m in roster if m.get("jira_id")}
    roster_team = {}
    for m in roster:
        if m.get("id"):
            roster_team["id:" + m["id"]] = m.get("team", "Static")

    # person_key -> {accountId, displayName, days}
    members: dict[str, dict] = {}
    # seed from roster so the whole team shows (even 0h)
    for m in roster:
        if not m.get("id"):
            continue
        k = "id:" + m["id"]
        members[k] = {"accountId": m.get("jira_id", ""), "displayName": "",
                      "team": m.get("team", "Static"), "days": {}, "tickets": {}}

    for site, fname in SITE_FILES.items():
        url, tok = _creds(site)
        project = SITE_PROJECT.get(site, "")
        try:
            entries = _worklogs_all(url, tok, date_from, date_to, project)
        except Exception as exc:
            print(f"[{site}] fetch failed: {exc}", file=sys.stderr)
            continue
        for e in entries:
            k = _person_key(e["displayName"], e["accountId"], roster_by_jid)
            m = members.get(k)
            if m is None:
                m = {"accountId": e["accountId"], "displayName": e["displayName"],
                     "team": _team_from_name(e["displayName"]), "days": {}, "tickets": {}}
                members[k] = m
            m["days"][e["day"]] = m["days"].get(e["day"], 0) + e["seconds"]
            ikey = e.get("issueKey")
            if ikey:
                t = m["tickets"].setdefault(ikey, {"summary": e.get("summary", ""), "days": {}})
                t["days"][e["day"]] = t["days"].get(e["day"], 0) + e["seconds"]
                if e.get("summary"):
                    t["summary"] = e["summary"]
            if e["displayName"]:
                m["displayName"] = e["displayName"]

    # resolve labels (display names) for roster members that logged nothing
    _resolve_labels(members)

    # apply member filter (only show members in filter.json, if present)
    flt = _load_filter()
    if flt:
        ids, names = flt
        def _keep(k, m):
            if k.startswith("id:") and k[3:] in ids:
                return True
            return _norm(m.get("displayName") or "") in names
        members = {k: m for k, m in members.items() if _keep(k, m)}

    days = _day_range(date_from, date_to)

    # group by team
    groups: dict[str, list] = {}
    for m in members.values():
        team = m.get("team") or "Khác"
        if team not in groups:
            groups[team] = []
        groups[team].append(m)

    out_groups = []
    ordered = TEAM_ORDER + [t for t in sorted(groups) if t not in TEAM_ORDER]
    for team in ordered:
        ms = groups.get(team)
        if not ms:
            continue
        ms = sorted(ms, key=lambda x: (-sum(x["days"].values()), x.get("displayName") or ""))
        out_groups.append({
            "name": team,
            "members": [{
                "label": m.get("displayName") or m.get("accountId") or "—",
                "team": team,
                "hours": {d: round(m["days"].get(d, 0) / 3600.0, 4) for d in days},
                "tickets": _tickets_list(m.get("tickets", {}), days),
            } for m in ms],
        })

    data = {"from": date_from, "to": date_to, "days": days, "groups": out_groups}
    _cache[key] = data
    return data


def _tickets_list(tdict: dict, days: list[str]) -> list[dict]:
    """Convert per-member ticket dict {key:{summary,days}} to a sorted list."""
    out = []
    for key, t in tdict.items():
        tdays = {d: round(t["days"].get(d, 0) / 3600.0, 4) for d in days}
        out.append({"key": key, "summary": t.get("summary", ""),
                    "hours": tdays, "_tot": sum(tdays.values())})
    out.sort(key=lambda x: (-x["_tot"], x["key"]))
    for x in out:
        x.pop("_tot", None)
    return out


def _resolve_labels(members: dict) -> None:
    url = tok = None
    for m in members.values():
        if m.get("displayName"):
            continue
        jid = m.get("accountId")
        if not jid:
            continue
        if url is None:
            url, tok = _creds("enotion")
        try:
            u = _get(url, tok, "/rest/api/3/user", {"accountId": jid})
            m["displayName"] = u.get("displayName") or ""
        except Exception:
            m["displayName"] = ""
    for m in members.values():
        if not m.get("displayName"):
            m["displayName"] = m.get("accountId") or "?"


def _day_range(date_from: str, date_to: str) -> list[str]:
    d = datetime.strptime(date_from, "%Y-%m-%d")
    end = datetime.strptime(date_to, "%Y-%m-%d")
    out = []
    while d <= end:
        out.append(d.strftime("%Y-%m-%d"))
        d += timedelta(days=1)
    return out


def default_range() -> tuple[str, str]:
    """Default to the two most recent full ISO weeks (Mon-Sun)."""
    today = datetime.now().date()
    this_mon = today - timedelta(days=today.weekday())
    return (this_mon - timedelta(days=14)).isoformat(), (this_mon - timedelta(days=1)).isoformat()


# ---------- HTTP server ----------
def make_handler():
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, body: bytes, ctype: str):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path == "/":
                self._send(200, (HERE / "logwork.html").read_bytes(), "text/html; charset=utf-8")
                return
            if parsed.path == "/api/logwork":
                q = urllib.parse.parse_qs(parsed.query)
                frm = (q.get("from") or [None])[0]
                to = (q.get("to") or [None])[0]
                if not frm:
                    frm, to = default_range()
                try:
                    data = build_grid(frm, to)
                except Exception as exc:
                    self._send(500, json.dumps({"error": str(exc)}).encode(), "application/json")
                    return
                self._send(200, json.dumps(data, ensure_ascii=False).encode("utf-8"),
                           "application/json; charset=utf-8")
                return
            if parsed.path == "/api/default":
                frm, to = default_range()
                self._send(200, json.dumps({"from": frm, "to": to}).encode(), "application/json")
                return
            self._send(404, b"not found", "text/plain")
    return H


def write_static(out_path: str, frm: str, to: str) -> None:
    data = build_grid(frm, to)
    html = (HERE / "logwork.html").read_text()
    payload = html.replace("/*__DATA__*/null", json.dumps(data, ensure_ascii=False))
    Path(out_path).write_text(payload, encoding="utf-8")
    total = sum(v for g in data["groups"] for m in g["members"] for v in m["hours"].values())
    print(f"Wrote {out_path}  | {data['from']}..{data['to']} | {len(data['groups'])} groups "
          f"| total {total:.1f}h")


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--static")
    ap.add_argument("--json", action="store_true", help="build_grid -> data.json (CI)")
    ap.add_argument("--from", dest="from_d")
    ap.add_argument("--to", dest="to_d")
    ap.add_argument("--refresh-members", action="store_true")
    args = ap.parse_args()

    if args.refresh_members:
        refresh_members()
        print("members.json refreshed")
        return

    if args.json:
        frm, to = args.from_d, args.to_d
        if not frm or not to:
            frm, to = default_range()
        data = build_grid(frm, to)
        out = HERE / "data.json"
        out.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        total = sum(v for g in data["groups"] for m in g["members"] for v in m["hours"].values())
        print(f"Wrote {out.name}  | {frm}..{to} | {len(data['groups'])} groups | total {total:.1f}h")
        return

    if args.static:
        frm, to = args.from_d, args.to_d
        if not frm or not to:
            frm, to = default_range()
        write_static(args.static, frm, to)
        return

    frm, to = default_range()
    print(f"Logwork grid server: http://127.0.0.1:{args.port}/  (default {frm}..{to})")
    srv = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler())
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
