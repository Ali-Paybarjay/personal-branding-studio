#!/bin/bash
# آخرین نسخه‌ی استودیو را می‌گیرد. داده‌هایت (پوشه‌های data و brand) دست نمی‌خورند.
cd "$(dirname "$0")"
for b in /opt/homebrew/bin/brew /usr/local/bin/brew; do [ -x "$b" ] && eval "$("$b" shellenv)"; done
echo "▸ گرفتن آخرین نسخه…"
if git pull --ff-only; then
  brew upgrade yt-dlp >/dev/null 2>&1 || true
  [ -d modules/video/node_modules ] && (cd modules/video && npm ci --no-audit --no-fund >/dev/null 2>&1) || true
  echo "✓ به‌روز شد. اگر استودیو باز است، پنجره‌اش را ببند (Ctrl+C) و دوباره باز کن."
else
  echo "✕ به‌روز نشد. اگر خودت فایلی از کد استودیو را عوض کرده‌ای، پیام بالا را ببین."
fi
read -r -p "Enter را بزن تا بسته شود…"
