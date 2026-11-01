# HANDOFF — Web Logwork tổng hợp 2 Jira (enotion + vortech)

## Mục đích
Web dashboard dạng lưới timesheet hiển thị **số giờ logwork / thành viên / ngày**, gom theo team,
cộng dồn từ CẢ HAI Jira Cloud. Có cây mở rộng: team → thành viên → ticket (key + summary + giờ/ngày).
Theme **shadcn dark / monochrome**.

## Vị trí dự án: `~/logwork-web/`
- `logwork.py` — backend: fetch 2 Jira (stdlib urllib), HTTP server, xuất snapshot tĩnh.
- `logwork.html` — frontend (fetch `/api/logwork`, hoặc dùng dữ liệu nhúng khi mở file tĩnh).
- `members.json` — roster studio `[{id, jira_id, team}]`, tạo bởi `--refresh-members`.
- `filter.json` — danh sách 18 member được phép hiển thị (list các label).
- `start.sh` — chạy server (dùng venv bot).
- `run_server.sh` — wrapper cho launchd.
- `logwork-report.html` — snapshot offline (nhúng sẵn dữ liệu).
- `README.md`, `node_validate.js` (test render), `data.json`/`/tmp/lw.json` (data mẫu, có thể xóa).

## Kết nối Jira (không để lộ token — nằm trong `~/.jira-connect/`)
- `config.json` → **enotion**: URL `https://enotion.atlassian.net/`, user `mien.0762@enotion.io`.
- `vortechinc.json` → **vortech**: URL `https://vvortech.atlassian.net/`, user `lisa.ho@vortechinc.io`.
- Auth = HTTP **Basic** `base64(email:api_token)` (KHÔNG Bearer).
- Scope theo site (biến `SITE_PROJECT` trong logwork.py):
  - **enotion = đọc TẤT CẢ board.** (yêu cầu: "count all boards")
  - **vortech = chỉ project `APK`** (board APEK). Đổi bằng env `VORTECH_PROJECT` (vd `VORTECH_PROJECT= logwork.py` = mọi board).

## Roster (danh sách thành viên + team)
- Nguồn: Google Sheet **'Apek Studio Master Plan'** tab **Resource** gid `1215444134`
  qua `drive_tools.studio_members()` (bot venv có google libs). Cột K = jira_id/accountId.
- Cập nhật: `~/chatbot-discord/.venv/bin/python logwork.py --refresh-members` → ghi `members.json`.
- Team từ sheet (GD/Static/Anim/FE/QC…); team dự phòng = đuôi display name (xem bucketing dưới).

## QUAN TRỌNG — gộp dữ liệu 2 Jira (pitfall lớn nhất)
Cùng một người có **accountId KHÁC NHAU ở mỗi site**, nhưng **giống display name / số ID đầu**
(vd cả enotion lẫn vortech đều `563-vu.ngo-GD`). Vì vậy **phải key theo số ID đầu của display name**
(fallback: tên normalized) — `_person_key()`. KHÔNG key theo accountId, nếu không giờ bị tách/đếm trùng.

## Bucketing team theo đuôi display name (`_team_from_name`)
`UI/Concept/ConceptArt/Static/ART/Art→Static`; `Anim/ANIM/3DAnim→Anim`; `FE/GD/QC` giữ nguyên;
`3D/3DModel/3DVFX→3D`; `PM/PMA/PA→PM`; `RND→RND`; còn lại = chính đuôi đó.
Ứng dụng chỉ hiện 4 team GD/STATIC/ANIM/FE (nhờ filter.json).

## Data model (output `build_grid`)
```
{
  from, to, days: ["YYYY-MM-DD", ...],
  groups: [ {
    name: "GD",
    members: [ {
      label, team,
      hours: {"2026-10-19": 8.0, ...},          // tổng member theo ngày
      tickets: [ {key, summary, hours:{date:h}} ] // giờ theo ticket theo ngày
    } ]
  } ]
}
```
- **Không còn** group `total` (đã bỏ theo yêu cầu).
- Thứ tự group theo `TEAM_ORDER`; ticket sort theo tổng giờ giảm dần rồi key.

## API (server)
- `GET /` → trả `logwork.html`.
- `GET /api/logwork?from=&to=` → dữ liệu grid (JSON). Cache theo `(from,to)` trong tiến trình.
- `GET /api/default` → `{from,to}` = 2 tuần ISO đầy đủ gần nhất (Mon–Sun).
- Nếu `from`/`to` thiếu → dùng default.

## Cách chạy
- **Live (khuyến nghị):** đã chạy bằng **LaunchAgent** `com.pma-lily.logwork-server`
  (auto-start khi đăng nhập + KeepAlive, port 8765). Mở **http://127.0.0.1:8765/**.
  - Dừng: `launchctl unload ~/Library/LaunchAgents/com.pma-lily.logwork-server.plist`
  - Chạy lại: `launchctl kickstart -k gui/$(id -u)/com.pma-lily.logwork-server`
  - Log: `~/logwork-web/server.log`
- Thủ công: `~/logwork-web/start.sh` (dùng `~/chatbot-discord/.venv/bin/python`).
- **Offline:** mở `logwork-report.html` (nhúng sẵn data). Tạo mới:
  `~/chatbot-discord/.venv/bin/python ~/logwork-web/logwork.py --static report.html [--from ... --to ...]`
  (thay `/*__DATA__*/null` trong HTML bằng JSON).

## Frontend
- shadcn dark: `--background:#0a0a0a`, `--card:#0d0d0f`, `--border:#27272a`, `--primary:#fafafa`.
- Cây: button tròn ▾/▸. Mặc định **team mở**, **member đóng** (bấm ▸ để xổ ticket).
- Không có dòng Total team. Thanh dưới ô: xanh =8h, cam <8h, đỏ >8h; cuối tuần hatch.
- Hover row highlight `#121215`. Lưới nằm trong card bo góc, viền 1px, không bóng.
- Mở `logwork.html` trực tiếp bằng file:// → hiện hướng dẫn (vì không fetch được API).
- Expand/collapse lưu trong `EXPAND` (team/member set), re-render từ `LAST` (không gọi lại API).

## Lỗi / lưu ý đã gặp
- Jira search KHÔNG trả `total` → paginate bằng `nextPageToken`/`isLast` (xem skill `discord-ai-bot` ref `jira-multi-site.md`).
- Fetch worklog theo từng issue (`/rest/api/3/issue/{key}/worklog`, paginate `startAt`), dùng
  `ThreadPoolExecutor(max_workers=16)`. Lần fetch đầu ~15s–2 phút (rate limit), sau đó cache.
- `members.json` cũ (thiếu `id`) làm key mọi roster gộp thành `"id:"` → phải `--refresh-members`.
- `write_static` phải replace `/*__DATA__*/null` (đủ cả `null`) để tránh JSON bị dính `null` sau.
- Snapshot/`preview` cần file có dữ liệu nhúng mới hiển thị; `logwork.html` trần thì cần server.

## Kiến thức liên quan (skill)
- `discord-ai-bot` → refs: `jira-multi-site.md`, `jira-team-hours.md`, `jira-pagination.md`,
  `worklog-studio-accountid-filter.md`.
- `macos-launchd-services` → cách tạo/load LaunchAgent (bootstrap bị chặn, dùng load/kickstart).
