#!/bin/bash
# استودیوی محتوا را روی مک باز می‌کند. این پنجره را تا وقتی با استودیو کار می‌کنی باز نگه دار؛ برای بستن Ctrl+C.
cd "$(dirname "$0")"
for b in /opt/homebrew/bin/brew /usr/local/bin/brew; do [ -x "$b" ] && eval "$("$b" shellenv)"; done
export PATH="$HOME/.local/bin:$PATH"
# اگر استودیو همین حالا باز است، فقط مرورگر را باز کن
if curl -s -o /dev/null -m 1 http://127.0.0.1:7788/api/state; then
  open http://127.0.0.1:7788; exit 0
fi
command -v python3 >/dev/null 2>&1 || { echo "Python پیدا نشد. اول install-mac.sh را اجرا کن."; read -r; exit 1; }
exec python3 app/server.py
