"""کدام مدل Claude برای کدام کار. تنظیم در data/models.json، از صفحه‌ی «تنظیمات» عوض می‌شود.

پیش‌فرض Sonnet 5.5 است: روی اشتراک Pro سهمیه را دیرتر تمام می‌کند و برای بیشتر کارها کافی است.
هر کار را می‌شود جدا روی Opus 5.5 گذاشت (دقیق‌تر، ولی سهمیه را زودتر تمام می‌کند).
همیشه شناسه‌ی کامل به --model داده می‌شود؛ اسم کوتاه («sonnet») در بعضی نسخه‌های Claude Code مدل قدیمی‌تر است.
"""
import json, threading
from pathlib import Path

FILE = Path(__file__).resolve().parent.parent / "data" / "models.json"
CHOICES = {"claude-sonnet-5-5": "Sonnet 5.5 (سریع‌تر، سهمیه‌ی کمتر)", "claude-opus-5-5": "Opus 5.5 (دقیق‌تر، سهمیه‌ی بیشتر)"}
STEPS = {
    "analyze": "بانک ایده: تحلیل",
    "enrich": "بانک ایده: جستجوی وب",
    "produce": "بانک ایده: ساخت ریلز",
    "regen": "ریلز: بازنویسی یک بخش",
    "advisor": "مشاور",
    "carousel": "کاروسل",
    "translate": "ترجمه‌ی یوتیوب",
    "video": "تدوین ویدیو",
    "analyst": "تحلیلگر اینستاگرام",
}
DEFAULT = "claude-sonnet-5-5"
LOCK = threading.Lock()


def load():
    try:
        saved = json.loads(FILE.read_text(encoding="utf-8"))
    except Exception:
        saved = {}
    return {s: saved.get(s) if saved.get(s) in CHOICES else DEFAULT for s in STEPS}


def get(step):
    return load().get(step, DEFAULT)


def handle_get(p, q):
    if p == "/api/models":
        return 200, {"models": load(), "choices": CHOICES, "steps": STEPS}
    return None


def handle_post(p, body):
    if p == "/api/models":
        step, model = body.get("step"), body.get("model")
        if model not in CHOICES or (step not in STEPS and step != "*"):
            return 400, {"error": "bad request"}
        with LOCK:
            cur = load()
            for s in (STEPS if step == "*" else [step]):
                cur[s] = model
            FILE.parent.mkdir(exist_ok=True)
            FILE.write_text(json.dumps(cur, ensure_ascii=False, indent=2), encoding="utf-8")
        return 200, {"ok": True, "models": cur}
    return None
