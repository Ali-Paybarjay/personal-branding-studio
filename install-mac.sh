#!/bin/bash
# نصب «استودیوی محتوا» روی مک.
#   curl -fsSL https://raw.githubusercontent.com/siavash-smf/personal-branding-studio/main/install-mac.sh | bash
# کارها: Homebrew ← Python، Git، ffmpeg، yt-dlp، Node ← Claude Code ← دانلود استودیو در ~/content-studio
#        ← میان‌بر «Content Studio» روی دسکتاپ. دوباره اجرا کردنش بی‌خطر است (فقط چیزهای جاافتاده نصب می‌شوند).
set -e

REPO="https://github.com/siavash-smf/personal-branding-studio.git"
DIR="${STUDIO_DIR:-$HOME/content-studio}"

say()  { printf "\n\033[1;36m▸ %s\033[0m\n" "$1"; }
fail() { printf "\n\033[1;31m✕ %s\033[0m\n" "$1"; exit 1; }

[ "$(uname)" = "Darwin" ] || fail "این اسکریپت مال مک است. روی ویندوز install-windows.ps1 را اجرا کن."

# ---------- Homebrew ----------
if ! command -v brew >/dev/null 2>&1; then
  for b in /opt/homebrew/bin/brew /usr/local/bin/brew; do [ -x "$b" ] && eval "$("$b" shellenv)"; done
fi
if ! command -v brew >/dev/null 2>&1; then
  say "نصب Homebrew (برنامه‌ی نصب ابزارها). رمز مک را می‌خواهد؛ موقع تایپ چیزی نشان داده نمی‌شود، عادی است."
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)" </dev/tty
  for b in /opt/homebrew/bin/brew /usr/local/bin/brew; do [ -x "$b" ] && eval "$("$b" shellenv)"; done
  command -v brew >/dev/null 2>&1 || fail "Homebrew نصب نشد. پیام‌های بالا را ببین."
fi
# تا ترمینال‌های بعدی هم brew و ابزارهایش را پیدا کنند
BREW_LINE="eval \"\$($(command -v brew) shellenv)\""
grep -qsF "$BREW_LINE" "$HOME/.zprofile" || echo "$BREW_LINE" >> "$HOME/.zprofile"

say "نصب Python، Git، ffmpeg، yt-dlp و Node (چند دقیقه)"
brew install python git ffmpeg yt-dlp node || fail "نصب ابزارها شکست خورد."
brew upgrade yt-dlp >/dev/null 2>&1 || true      # یوتیوب زود‌به‌زود عوض می‌شود؛ yt-dlp باید تازه باشد

# ---------- Claude Code ----------
export PATH="$HOME/.local/bin:$PATH"
if ! command -v claude >/dev/null 2>&1; then
  say "نصب Claude Code"
  curl -fsSL https://claude.ai/install.sh | bash
  export PATH="$HOME/.local/bin:$PATH"
fi
grep -qsF '.local/bin' "$HOME/.zprofile" || echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.zprofile"

# ---------- خود استودیو ----------
if [ -d "$DIR/.git" ]; then
  say "به‌روزرسانی استودیو در $DIR"
  git -C "$DIR" pull --ff-only || echo "  (به‌روزرسانی نشد؛ نسخه‌ی فعلی می‌ماند)"
elif [ -f "$(dirname "$0")/app/server.py" ] 2>/dev/null; then
  DIR="$(cd "$(dirname "$0")" && pwd)"
  say "استودیو همین‌جاست: $DIR"
else
  say "دانلود استودیو در $DIR"
  git clone --depth 1 "$REPO" "$DIR" || fail "دانلود استودیو شکست خورد. اینترنت را چک کن."
fi
chmod +x "$DIR"/*.sh "$DIR"/*.command 2>/dev/null || true

# ---------- میان‌بر دسکتاپ ----------
LAUNCH="$HOME/Desktop/Content Studio.command"
[ -n "$STUDIO_NO_SHORTCUT" ] && LAUNCH="$DIR/.launcher-test.command"
cat > "$LAUNCH" <<EOF
#!/bin/bash
# استودیوی محتوا را باز می‌کند. این پنجره را تا وقتی با استودیو کار می‌کنی باز نگه دار.
exec "$DIR/start-mac.command"
EOF
chmod +x "$LAUNCH"

say "تمام شد ✓"
cat <<EOF

  قدم‌های بعدی:
  ۱. اگر هنوز وارد Claude نشده‌ای، همین‌جا بنویس:  claude
     و با حساب Claude (اشتراک Pro یا Max) وارد شو. بعد بنویس /exit
  ۲. روی دسکتاپ «Content Studio» را دوبار کلیک کن.
     (اگر مک گفت باز نمی‌شود: راست‌کلیک ← Open ← Open)
  ۳. صفحه‌ی «شروع» در مرورگر باز می‌شود؛ قدم‌به‌قدم جلو برو.

  تدوین ویدیو (اختیاری، حدود ۴۰۰ مگابایت):  $DIR/install-video-mac.sh

EOF
