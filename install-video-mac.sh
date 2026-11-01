#!/bin/bash
# نصب بخش «تدوین ویدیو» (فقط مک، حدود ۴۰۰ مگابایت): Google Chrome، بسته‌های Node و کتابخانه‌ی افکت صوتی.
set -e
cd "$(dirname "$0")"
for b in /opt/homebrew/bin/brew /usr/local/bin/brew; do [ -x "$b" ] && eval "$("$b" shellenv)"; done
say() { printf "\n\033[1;36m▸ %s\033[0m\n" "$1"; }

if [ ! -d "/Applications/Google Chrome.app" ]; then
  say "نصب Google Chrome (برای ساختن زیرنویس، گرافیک و کاور)"
  brew install --cask google-chrome
fi
command -v node >/dev/null 2>&1 || brew install node
command -v ffmpeg >/dev/null 2>&1 || brew install ffmpeg
xcode-select -p >/dev/null 2>&1 || { say "ابزارهای خط فرمان اپل لازم است؛ پنجره‌اش را تأیید کن و بعد دوباره همین اسکریپت را اجرا کن."; xcode-select --install; exit 1; }

say "نصب بسته‌های Node (چند دقیقه)"
(cd modules/video && npm ci --no-audit --no-fund)

say "ساختن کتابخانه‌ی افکت صوتی (دانلود از Mixkit)"
python3 modules/video/sfx/build_lib.py || echo "  (افکت‌ها کامل نشد؛ تدوین بدون افکت صوتی هم کار می‌کند)"

say "تمام شد ✓  استودیو را ببند و دوباره باز کن؛ تب «تدوین ویدیو» آماده است."
echo "  این بخش کلید Gemini را هم لازم دارد (تب «تنظیمات»)."
