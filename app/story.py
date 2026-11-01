"""استوری متنی — استایل پیش‌فرض و پس‌زمینه‌های آپلودی.

رندر کامل در مرورگر انجام می‌شود (app/story.js روی canvas ۱۰۸۰×۱۹۲۰)؛ این‌جا فقط
تنظیمات ذخیره می‌شود: data/stories/settings.json و تصویرهای زمینه در data/stories/bg/.
"""
import json, re, time, base64, threading
from pathlib import Path

APP = Path(__file__).resolve().parent
DIR = APP.parent / "data" / "stories"
FILE = DIR / "settings.json"
BG = DIR / "bg"
LOCK = threading.Lock()
IMG = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}
STATIC = {"/story.js": ("story.js", "text/javascript; charset=utf-8"),
          "/story.css": ("story.css", "text/css; charset=utf-8")}
MAX_BG = 15 * 1024 * 1024


def load():
    try:
        return json.loads(FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def handle_get(p, q):
    """(code, payload, ctype) — ctype=None یعنی payload جیسون است."""
    if p in STATIC:
        name, ctype = STATIC[p]
        return 200, (APP / name).read_bytes(), ctype
    if p == "/api/story":
        return 200, load(), None
    if p.startswith("/story-bg/"):
        f = BG / p[len("/story-bg/"):]
        if f.parent != BG or f.suffix.lower() not in IMG or not f.is_file():
            return 404, {"error": "not found"}, None
        return 200, f.read_bytes(), IMG[f.suffix.lower()]
    return None


def handle_post(p, body):
    if p == "/api/story":
        style = body.get("style")
        if not isinstance(style, dict) or len(json.dumps(style)) > 20000:
            return 400, {"error": "bad payload"}
        cur = {"style": style, "preset": str(body.get("preset") or "")[:40],
               "updated": time.strftime("%Y-%m-%d %H:%M")}
        with LOCK:
            DIR.mkdir(parents=True, exist_ok=True)
            FILE.write_text(json.dumps(cur, ensure_ascii=False, indent=2), encoding="utf-8")
        return 200, {"ok": True, **cur}
    if p == "/api/story/bg":
        ext = Path(str(body.get("filename") or "")).suffix.lower()
        if ext not in IMG:
            return 400, {"error": "فقط PNG، JPG یا WEBP."}
        try:
            blob = base64.b64decode(str(body.get("data") or "").split(",")[-1])
        except Exception:
            return 400, {"error": "فایل خوانده نشد."}
        if not blob or len(blob) > MAX_BG:
            return 400, {"error": "فایل خالی است یا از ۱۵ مگابایت بزرگ‌تر."}
        stem = re.sub(r"[^A-Za-z0-9_-]", "", Path(str(body.get("filename"))).stem)[:30] or "bg"
        name = f"{int(time.time() * 1000)}-{stem}{ext}"
        BG.mkdir(parents=True, exist_ok=True)
        (BG / name).write_bytes(blob)
        return 200, {"ok": True, "file": name}
    return None
