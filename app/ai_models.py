"""کدام مدل Claude برای کدام کار. تنظیم در data/models.json، از صفحه‌ی «تنظیمات» عوض می‌شود.

پیش‌فرض Sonnet 5.5 است: روی اشتراک Pro سهمیه را دیرتر تمام می‌کند و برای بیشتر کارها کافی است.
هر کار را می‌شود جدا روی Opus 5.5 گذاشت (دقیق‌تر، ولی سهمیه را زودتر تمام می‌کند).
همیشه شناسه‌ی کامل به --model داده می‌شود؛ اسم کوتاه («sonnet») در بعضی نسخه‌های Claude Code مدل قدیمی‌تر است.

کارهایی که فقط متن برمی‌گردانند (CODEX_STEPS) را می‌شود روی GPT-6 Astra هم گذاشت؛ با Codex CLI و اشتراک
ChatGPT خود کاربر اجرا می‌شود (codex_engine.py). هر جا claude صدا زده می‌شود از claude_model() بخوان، نه get().
"""
import json, threading
from pathlib import Path
import codex_engine as ce

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
CODEX = {"gpt-6-astra": "GPT-6 Astra (اشتراک ChatGPT، با Codex)"}
CODEX_STEPS = ("produce", "regen")   # فقط این‌ها متن خالص برمی‌گردانند؛ بقیه به ابزارهای Claude Code وابسته‌اند
DEFAULT = "claude-sonnet-5-5"
LOCK = threading.Lock()


def load():
    try:
        saved = json.loads(FILE.read_text(encoding="utf-8"))
    except Exception:
        saved = {}
    return {s: saved.get(s) if allowed(s, saved.get(s)) else DEFAULT for s in STEPS}


def allowed(step, model):
    return model in CHOICES or (model in CODEX and step in CODEX_STEPS)


def get(step):
    return load().get(step, DEFAULT)


def is_codex(model):
    return model in CODEX


def claude_model(step):
    """برای جاهایی که حتماً claude اجرا می‌کنند (مثلاً یوتیوب ← ریلز که با همان کلید produce است)."""
    m = get(step)
    return m if m in CHOICES else DEFAULT


def label(model):
    return CHOICES.get(model) or CODEX.get(model) or model


def handle_get(p, q):
    if p == "/api/models":
        return 200, {"models": load(), "choices": CHOICES, "steps": STEPS,
                     "codex": CODEX, "codex_steps": list(CODEX_STEPS), "codex_status": ce.status()}
    return None


def handle_post(p, body):
    if p == "/api/models":
        step, model = body.get("step"), body.get("model")
        # «همه» فقط بین مدل‌های Claude است؛ Astra جداگانه برای هر کار مجازش انتخاب می‌شود
        if not (model in CHOICES and step == "*") and not (step in STEPS and allowed(step, model)):
            return 400, {"error": "bad request"}
        with LOCK:
            cur = load()
            for s in (STEPS if step == "*" else [step]):
                cur[s] = model
            FILE.parent.mkdir(exist_ok=True)
            FILE.write_text(json.dumps(cur, ensure_ascii=False, indent=2), encoding="utf-8")
        return 200, {"ok": True, "models": cur}
    if p == "/api/models/codex-test":
        st = ce.status(fresh=True)
        if not st["logged_in"]:
            return 200, {"ok": False, "error": st["note"]}
        code, text, err = ce.ask("فقط بنویس: آماده‌ام", 300, next(iter(CODEX)))
        return 200, {"ok": code == 0 and bool(text), "reply": text, "error": err}
    return None
