#!/bin/bash
# Refresh logwork data.json from Jira, then push to GitHub (Vercel auto-deploys).
# Runs every 15 min via launchd com.pma-lily.logwork-refresh. Only pushes if changed.
set -euo pipefail
cd "$HOME/logwork-web"
PY="$HOME/chatbot-discord/.venv/bin/python"
LOG="$HOME/logwork-web/refresh.log"

echo "===== $(date '+%Y-%m-%d %H:%M:%S') =====" >> "$LOG"
"$PY" logwork.py --json >> "$LOG" 2>&1 || { echo "json failed" >> "$LOG"; exit 1; }

if git diff --quiet -- data.json; then
  echo "no change" >> "$LOG"
  exit 0
fi

git config user.name "logwork-bot"
git config user.email "logwork-bot@users.noreply.github.com"
git add data.json
git commit -m "data: refresh logwork $(date -u '+%Y-%m-%d %H:%M UTC')" >> "$LOG" 2>&1
git push >> "$LOG" 2>&1
echo "pushed" >> "$LOG"
