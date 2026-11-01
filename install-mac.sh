#!/bin/bash
# نصب «استودیوی محتوا» روی مک.
#   curl -fsSL https://raw.githubusercontent.com/siavash-smf/personal-branding-studio/main/install-mac.sh | bash
# کارها: Homebrew ← هر کدام از Python، Git، ffmpeg، yt-dlp و Node که نیست ← Claude Code ← دانلود استودیو در
#        ~/content-studio ← میان‌بر «Content Studio» روی دسکتاپ.
# دوباره اجرا کردنش بی‌خطر است: فقط چیزهای جاافتاده نصب می‌شوند و ابزاری که از قبل هست ارتقا داده نمی‌شود
# (جز yt-dlp، که باید تازه باشد تا یوتیوب کار کند).
#
# همه‌چیز داخل main است: وقتی اسکریپت با curl | bash اجرا می‌شود، bash آن را تکه‌تکه از stdin می‌خواند و
# برنامه‌ای مثل brew که stdin را بخواند بقیه‌ی اسکریپت را می‌بلعد. با تابع، کل اسکریپت اول خوانده می‌شود.

main() {
set -e

REPO="https://github.com/siavash-smf/personal-branding-studio.git"
DIR="${STUDIO_DIR:-$HOME/content-studio}"

say()  { printf "\n\033[1;36m▸ %s\033[0m\n" "$1"; }
fail() { printf "\n\033[1;31m✕ %s\033[0m\n" "$1"; exit 1; }
has()  { command -v "$1" >/dev/null 2>&1; }

[ "$(uname)" = "Darwin" ] || fail "این اسکریپت مال مک است. روی ویندوز install-windows.ps1 را اجرا کن."

# ---------- Homebrew ----------
if ! has brew; then
  for b in /opt/homebrew/bin/brew /usr/local/bin/brew; do [ -x "$b" ] && eval "$("$b" shellenv)"; done
fi
if ! has brew; then
  say "نصب Homebrew (برنامه‌ی نصب ابزارها). رمز مک را می‌خواهد؛ موقع تایپ چیزی نشان داده نمی‌شود، عادی است."
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)" </dev/tty
  for b in /opt/homebrew/bin/brew /usr/local/bin/brew; do [ -x "$b" ] && eval "$("$b" shellenv)"; done
  has brew || fail "Homebrew نصب نشد. پیام‌های بالا را ببین."
fi
# تا ترمینال‌های بعدی هم brew و ابزارهایش را پیدا کنند
if ! grep -qs "brew shellenv" "$HOME/.zprofile"; then
  echo "eval \"\$($(command -v brew) shellenv)\"" >> "$HOME/.zprofile"
fi

# ---------- ابزارها: فقط آن‌هایی که نیستند ----------
export HOMEBREW_NO_INSTALL_UPGRADE=1 HOMEBREW_NO_ENV_HINTS=1
need=()
python3 -c 'import sys; sys.exit(sys.version_info < (3, 9))' >/dev/null 2>&1 || need+=(python)
has git    || need+=(git)
has ffmpeg || need+=(ffmpeg)
has yt-dlp || need+=(yt-dlp)
has node   || need+=(node)
if [ ${#need[@]} -gt 0 ]; then
  say "نصب ${need[*]} (چند دقیقه)"
  brew install "${need[@]}" </dev/null || fail "نصب ابزارها شکست خورد. پیام‌های بالا را ببین."
else
  say "Python، Git، ffmpeg، yt-dlp و Node از قبل نصب‌اند"
fi
brew upgrade yt-dlp </dev/null >/dev/null 2>&1 || true     # یوتیوب زود‌به‌زود عوض می‌شود؛ yt-dlp باید تازه باشد

# ---------- Claude Code ----------
export PATH="$HOME/.local/bin:$PATH"
if ! has claude; then
  say "نصب Claude Code"
  curl -fsSL https://claude.ai/install.sh | bash </dev/null
  export PATH="$HOME/.local/bin:$PATH"
fi
if ! grep -qs '.local/bin' "$HOME/.zprofile"; then
  echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.zprofile"
fi

# ---------- خود استودیو ----------
HERE="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd || true)"
if [ -d "$DIR/.git" ]; then
  say "به‌روزرسانی استودیو در $DIR"
  git -C "$DIR" pull --ff-only </dev/null || echo "  (به‌روزرسانی نشد؛ نسخه‌ی فعلی می‌ماند)"
elif [ -z "$STUDIO_DIR" ] && [ -n "$HERE" ] && [ -f "$HERE/app/server.py" ]; then
  DIR="$HERE"
  say "استودیو همین‌جاست: $DIR"
else
  say "دانلود استودیو در $DIR"
  git clone --depth 1 "$REPO" "$DIR" </dev/null || fail "دانلود استودیو شکست خورد. اینترنت را چک کن."
fi
chmod +x "$DIR"/*.sh "$DIR"/*.command 2>/dev/null || true

# ---------- میان‌بر دسکتاپ ----------
LAUNCH="$HOME/Desktop/Content Studio.command"
[ -n "$STUDIO_NO_SHORTCUT" ] && LAUNCH="$DIR/.launcher-test.command"
mkdir -p "$(dirname "$LAUNCH")"
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
}

main "$@"
