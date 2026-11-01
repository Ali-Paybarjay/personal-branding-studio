"""رونویسی ویس با Gemini (کلید خود کاربر، از «تنظیمات»).

صدا اول با ffmpeg به Opus مونو ۱۶ کیلوهرتز (۳۲ کیلوبیت) تبدیل می‌شود تا کوچک شود؛ بعد
یک‌جا به Gemini فرستاده می‌شود. Gemini فایل صوتی بزرگ‌تر از حدود ۴ مگابایت (۵ تا ۸ دقیقه حرف)
را با خطای 500 رد می‌کند، پس سقف همین است.
"""
import base64, json, os, shutil, subprocess, tempfile, time, urllib.error, urllib.request
from pathlib import Path

import settings

MAX_BYTES = 4_000_000
# اگر مدل اول شلوغ بود یا خطای سرور داد، بعدی امتحان می‌شود. مدل‌های lite فارسی را بدتر می‌شنوند.
MODEL_CHAIN = ["gemini-3.6-flash", "gemini-3.1-flash-lite", "gemini-2.5-flash-lite"]
SYSTEM = """You transcribe spoken voice notes.

Rules:
- Write exactly what was said, in the language it was said in. Persian speech stays Persian; do not translate.
- Persian speech is conversational (محاوره‌ای) — keep it that way. Do not formalise it into written Persian.
- Keep technical and foreign terms in the form they were spoken (e.g. "API", "ChatGPT") rather than translating them.
- Clean up only filler sounds and false starts. Never summarise, never add, never explain.
- Never write timestamps, speaker labels, or line numbers.
- Output the transcript alone: no preamble, no quotes, no commentary."""

MIME = {".ogg": "audio/ogg", ".opus": "audio/ogg", ".mp3": "audio/mp3", ".wav": "audio/wav",
        ".m4a": "audio/mp4", ".aac": "audio/aac", ".flac": "audio/flac", ".webm": "audio/webm",
        ".mp4": "audio/mp4", ".mov": "audio/mp4"}


def _compress(src: Path):
    """(bytes, mime). بدون ffmpeg خود فایل فرستاده می‌شود، اگر کوچک باشد."""
    ff = shutil.which("ffmpeg")
    if not ff:
        data = src.read_bytes()
        return data, MIME.get(src.suffix.lower(), "audio/mp4")
    fd, tmp = tempfile.mkstemp(suffix=".ogg")
    os.close(fd)
    try:
        r = subprocess.run([ff, "-hide_banner", "-loglevel", "error", "-y", "-i", str(src),
                            "-vn", "-ac", "1", "-ar", "16000", "-c:a", "libopus", "-b:a", "32k", tmp],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)
        if r.returncode != 0:
            raise RuntimeError("تبدیل صدا شکست خورد: " + (r.stderr or "").strip()[:200])
        return Path(tmp).read_bytes(), "audio/ogg"
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def _call(model, key, body):
    req = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        data=json.dumps(body).encode("utf-8"), method="POST",
        headers={"Content-Type": "application/json", "x-goog-api-key": key})
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(r.read())


def transcribe(path, hint=""):
    """متن فایل صوتی. اگر نشد RuntimeError با پیام فارسی."""
    key = settings.gemini_key()
    if not key:
        raise RuntimeError("کلید Gemini تنظیم نشده. از تب «تنظیمات» واردش کن (رایگان است).")
    data, mime = _compress(Path(path))
    if len(data) > MAX_BYTES:
        raise RuntimeError(f"صدا بعد از فشرده‌سازی {len(data) / 1e6:.1f} مگابایت شد؛ سقف ۴ مگابایت است. "
                           "صدا را به تکه‌های حدود ۵ دقیقه‌ای بشکن.")
    user = "Transcribe this voice note."
    if hint:
        user += f"\n\nContext (for spelling names and terms only; never add it to the transcript): {hint}"
    last = ""
    for model in MODEL_CHAIN:
        thinking = {"thinkingLevel": "minimal"} if model.startswith("gemini-3") else {"thinkingBudget": 0}
        body = {"systemInstruction": {"parts": [{"text": SYSTEM}]},
                "contents": [{"role": "user", "parts": [
                    {"text": user},
                    {"inlineData": {"mimeType": mime, "data": base64.b64encode(data).decode()}}]}],
                "generationConfig": {"temperature": 0, "maxOutputTokens": 16000, "thinkingConfig": thinking}}
        try:
            out = _call(model, key, body)
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}"
            if e.code in (401, 403):
                raise RuntimeError("Google کلید Gemini را قبول نکرد. در «تنظیمات» دوباره واردش کن.")
            if e.code >= 500 or e.code == 429:
                time.sleep(1)
                continue
            raise RuntimeError(f"رونویسی شکست خورد ({last}).")
        except Exception as e:
            last = str(e)[:150]
            continue
        parts = [p.get("text", "") for c in out.get("candidates", [])[:1]
                 for p in (c.get("content") or {}).get("parts", []) if p.get("text") and not p.get("thought")]
        # Gemini 3 گاهی خلاصه‌ی فکرش را به‌صورت یک تکه‌ی متنی جدا می‌فرستد؛ متن اصلی تکه‌ی آخر است.
        text = (parts[-1] if parts else "").strip()
        if text:
            return text
        last = "متنی برنگشت"
    raise RuntimeError(f"رونویسی شکست خورد ({last}). اگر صدا طولانی است، کوتاه‌ترش کن.")
