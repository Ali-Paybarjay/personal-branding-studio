"""کاروسل و پست اینستاگرام — اسلاید به اسلاید، دستی یا با Claude، با لوگو و تصویر؛ دانلود و انتشار دستی.

رندر کامل در مرورگر انجام می‌شود (app/carousel.js روی canvas ۱۰۸۰×۱۳۵۰ با موتور متن story.js)؛
این‌جا داده‌ها، کارهای پس‌زمینه و انتشار است:
- data/carousels/decks/<id>.json   هر کاروسل: اسلایدها (HTML ویرایشگر)، کپشن، هشتگ، استایل، وضعیت انتشار
- data/carousels/media/            کتابخانه‌ی تصویر (آپلودی و ساخته‌ی Gemini)؛ media.json برچسب‌هاست
- data/carousels/settings.json     «استایل من» برای کاروسل‌های تازه
متن با claude -p (روی اشتراک خود کاربر) و بیرون از پوشه‌ی استودیو ساخته می‌شود تا CLAUDE.md قاطی نشود؛
هسته‌ی برند کامل داخل خود پرامپت است. تصویر با Gemini (کلید خود کاربر از «تنظیمات»).
"""
import base64, json, re, secrets, shutil, subprocess, tempfile, threading, time, urllib.error, urllib.request
from html import escape, unescape
from html.parser import HTMLParser
from pathlib import Path
import settings as cfg
import ai_models as am

APP = Path(__file__).resolve().parent
ROOT = APP.parent
DIR = ROOT / "data" / "carousels"
DECKS = DIR / "decks"
TRASH = DIR / "trash"
MEDIA = DIR / "media"
MEDIA_INDEX = DIR / "media.json"
SETTINGS = DIR / "settings.json"
OUT = DIR / "out"
IDEAS = ROOT / "data" / "ideas"
BRAND_MD = ROOT / "brand" / "brand-core.md"

IMG_MODELS = ("gemini-3.1-flash-image", "gemini-2.5-flash-image")   # اولی ~۱۰ ثانیه؛ دومی اگر اولی شلوغ بود
IMG = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}
STATIC = {"/carousel.js": ("carousel.js", "text/javascript; charset=utf-8"),
          "/carousel.css": ("carousel.css", "text/css; charset=utf-8")}
MAX_UPLOAD = 15 * 1024 * 1024
MAX_SLIDES = 40                 # در ویرایشگر (۲۰ بود؛ ۲۰۲۶-۱۰-۱۴ برای کاروسل ۳۳اسلایدی نظرات)؛ انتشار حداکثر ۱۰ (سقف API اینستاگرام)
PUBLISH_MAX = 10
CAPTION_MAX = 2200              # سقف کپشن اینستاگرام، با هشتگ‌ها
HASHTAG_MAX = 5                 # سقف هشتگ خود اینستاگرام از دسامبر ۲۰۲۵ (مرجع API هنوز ۳۰ می‌گوید)
IMG_MODES = ("above", "between", "below", "circle", "bg", "full")
ASPECT = {"above": "16:9", "between": "16:9", "below": "16:9", "circle": "1:1", "bg": "4:5", "full": "4:5"}

LOCK = threading.Lock()         # همه‌ی نوشتن‌های فایل‌های کاروسل و کتابخانه
JOBS = {}                       # "<deck>:<کار>" ← {kind, state, step, error, ...}
JLOCK = threading.Lock()


# ---------------- کمک‌ها ----------------
def _safe(s):
    return isinstance(s, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,64}", s) is not None


def now():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def read_text(p, limit=None):
    try:
        t = Path(p).read_text(encoding="utf-8")
    except Exception:
        return ""
    return t[:limit] if limit else t


def jload(p, default):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:
        return default


def jsave(p, obj):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(p)


class _Lines(HTMLParser):
    """HTML ویرایشگر ← خط‌ها، با ** برای پررنگ (تأکید). اندازه‌ها (<font size>) در متن ساده نمی‌آیند."""
    BLOCK = {"div", "p", "li", "h1", "h2", "h3", "h4"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.lines, self.cur, self.bold = [], "", 0

    def _flush(self):
        self.lines.append(self.cur)
        self.cur = ""

    def handle_starttag(self, tag, attrs):
        if tag == "br":
            self._flush()
        elif tag in self.BLOCK and self.cur:
            self._flush()
        elif tag in ("b", "strong", "mark"):
            self.bold += 1
            if self.bold == 1:
                self.cur += "**"

    def handle_endtag(self, tag):
        if tag in ("b", "strong", "mark") and self.bold:
            self.bold -= 1
            if not self.bold:
                self.cur += "**"
        elif tag in self.BLOCK and self.cur:
            self._flush()

    def handle_data(self, data):
        self.cur += data.replace(" ", " ")


def html_to_md(h):
    p = _Lines()
    p.feed(h or "")
    p.close()
    if p.cur:
        p._flush()
    lines = [re.sub(r"\*\*(\s*)\*\*", r"\1", l).rstrip() for l in p.lines]
    while lines and not lines[-1].strip():
        lines.pop()
    while lines and not lines[0].strip():
        lines.pop(0)
    return "\n".join(lines)


def md_to_html(text):
    """متن با ** ← همان HTML که ویرایشگر می‌سازد (هر خط یک div، پررنگ = تأکید)."""
    out = []
    for line in (text or "").replace("\r", "").split("\n"):
        if not line.strip():
            out.append("<div><br></div>")
            continue
        parts, h = line.split("**"), ""
        for k, part in enumerate(parts):
            if part:
                h += f"<b>{escape(part, quote=False)}</b>" if k % 2 else escape(part, quote=False)
        out.append(f"<div>{h}</div>")
    while out and out[-1] == "<div><br></div>":
        out.pop()
    return "".join(out)


def plain(h):
    return html_to_md(h).replace("**", "").strip()


# ---------------- کاروسل‌ها ----------------
def deck_path(did):
    return DECKS / f"{did}.json"


def load(did):
    return jload(deck_path(did), None) if _safe(did) else None


def _write(deck):
    deck["updated"] = now()
    jsave(deck_path(deck["id"]), deck)


def new_slide(title="", body="", img=None, img_prompt=""):
    return {"id": "s" + secrets.token_hex(4), "title": title, "body": body, "img": img, "imgPrompt": img_prompt}


def saved_style():
    s = jload(SETTINGS, {})
    return s.get("style") if isinstance(s.get("style"), dict) else None


def create(title="", source=None, slides=None):
    did = "c" + time.strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(2)
    deck = {"id": did, "v": 1, "title": title, "created": now(), "source": source or {"kind": "manual"},
            "slides": slides if slides is not None else [new_slide()], "caption": "", "hashtags": "",
            "style": saved_style(), "note": "", "published": [], "pending": None, "prevCaption": None}
    with LOCK:
        _write(deck)
    return deck


def clean_img(v):
    if not isinstance(v, dict) or not media_ok(v.get("file")):
        return None
    out = {"file": v["file"], "mode": v.get("mode") if v.get("mode") in IMG_MODES else "below",
           "fit": "cover" if v.get("fit") == "cover" else "contain"}
    try:
        dim = float(v.get("dim", 0.65))
        out["dim"] = max(0.0, min(0.95, dim))
    except (TypeError, ValueError):
        out["dim"] = 0.65
    return out


def clean_slide(s, base):
    out = dict(base)
    for k in ("title", "body"):
        if isinstance(s.get(k), str):
            out[k] = s[k][:30000]
    if isinstance(s.get("imgPrompt"), str):
        out["imgPrompt"] = s["imgPrompt"][:1500]
    if "img" in s:
        out["img"] = clean_img(s["img"])
    return out


def busy_slides(did):
    with JLOCK:
        return {j.get("slide") for k, j in JOBS.items() if k.startswith(did + ":") and j.get("state") == "running"}


def generating(did):
    with JLOCK:
        return JOBS.get(f"{did}:gen", {}).get("state") == "running"


def save(body):
    """فقط چیزهایی که صفحه فرستاده ادغام می‌شوند: اسلایدهای عوض‌شده (با id)، و اگر ترتیب عوض شده
    order + known. اسلایدی که صفحه هرگز ندیده (مثلاً از گوشی اضافه شده) حذف نمی‌شود."""
    did = body.get("id")
    busy = busy_slides(did)
    with LOCK:
        deck = load(did)
        if not deck:
            return 404, {"error": "این کاروسل پیدا نشد."}
        if generating(did) and not deck["slides"]:
            # Claude هنوز متن را ننوشته: فقط استایل (انتخاب صفحه) می‌ماند؛ بقیه را ساخت بازنویسی می‌کند
            st = body.get("style")
            if isinstance(st, dict) and len(json.dumps(st)) < 20000:
                deck["style"] = st
                _write(deck)
            return 200, {"ok": True, "updated": deck["updated"], "skipped": len(body.get("slides") or [])}
        have = [s["id"] for s in deck["slides"]]
        cur = {s["id"]: s for s in deck["slides"]}
        skipped = 0
        for s in body.get("slides") or []:
            if not isinstance(s, dict) or not _safe(s.get("id")):
                continue
            if s["id"] in busy:
                skipped += 1
                continue
            cur[s["id"]] = clean_slide(s, cur.get(s["id"]) or new_slide() | {"id": s["id"]})
        if isinstance(body.get("order"), list):
            order = [x for x in body["order"] if isinstance(x, str) and x in cur]
            known = {x for x in body.get("known") or [] if isinstance(x, str)}
            ids = list(dict.fromkeys(order + [i for i in have if i not in order and i not in known]))
        else:
            ids = have + [i for i in cur if i not in have]
        deck["slides"] = [cur[i] for i in ids][:MAX_SLIDES]
        for k, n in (("title", 200), ("caption", 6000), ("hashtags", 3000)):
            if isinstance(body.get(k), str):
                deck[k] = body[k][:n]
        st = body.get("style")
        if isinstance(st, dict) and len(json.dumps(st)) < 20000:
            deck["style"] = st
        _write(deck)
    return 200, {"ok": True, "updated": deck["updated"], "skipped": skipped}


def summary(d):
    cover = d["slides"][0] if d.get("slides") else {}
    with JLOCK:
        gen = JOBS.get(f"{d['id']}:gen", {})
    return {"id": d["id"], "title": d.get("title") or plain(cover.get("title", ""))[:120] or "بی‌نام",
            "updated": d.get("updated"), "created": d.get("created"), "n": len(d.get("slides") or []),
            "published": (d.get("published") or [])[-1:] or None, "source": d.get("source"),
            "generating": gen.get("state") == "running", "error": gen.get("error") if gen.get("state") == "error" else "",
            "cover": cover, "style": d.get("style")}


def list_decks():
    out = []
    for f in DECKS.glob("*.json"):
        d = jload(f, None)
        if isinstance(d, dict) and d.get("id"):
            out.append(summary(d))
    return sorted(out, key=lambda x: x.get("updated") or "", reverse=True)


def delete(did):
    with LOCK:
        f = deck_path(did) if _safe(did) else None
        if not f or not f.exists():
            return 404, {"error": "این کاروسل پیدا نشد."}
        TRASH.mkdir(parents=True, exist_ok=True)
        f.replace(TRASH / f.name)      # برگشت‌پذیر: data/carousels/trash/
    return 200, {"ok": True}


def duplicate(did):
    d = load(did)
    if not d:
        return 404, {"error": "این کاروسل پیدا نشد."}
    slides = [dict(s, id="s" + secrets.token_hex(4), prev=None, notes=[]) for s in d["slides"]]
    c = create(title=(d.get("title") or "کاروسل") + " (کپی)", source={"kind": "copy", "from": did}, slides=slides)
    with LOCK:
        c = load(c["id"])
        c.update(caption=d.get("caption", ""), hashtags=d.get("hashtags", ""), style=d.get("style"))
        _write(c)
    return 200, {"ok": True, "deck": c}


# ---------------- کتابخانه‌ی تصویر ----------------
def media_ok(name):
    return (isinstance(name, str) and re.fullmatch(r"\d{10,16}-[A-Za-z0-9_-]{0,40}\.(png|jpe?g|webp)", name) is not None
            and (MEDIA / name).is_file())


def save_media(filename, blob, label="", src="upload", prompt=""):
    ext = Path(str(filename or "")).suffix.lower()
    if ext not in IMG:
        raise ValueError("فقط PNG، JPG یا WEBP.")
    if not blob or len(blob) > MAX_UPLOAD:
        raise ValueError("فایل خالی است یا از ۱۵ مگابایت بزرگ‌تر.")
    stem = re.sub(r"[^A-Za-z0-9_-]", "", Path(str(filename)).stem)[:30] or "img"
    name = f"{int(time.time() * 1000)}-{stem}{'.jpg' if ext == '.jpeg' else ext}"
    with LOCK:
        MEDIA.mkdir(parents=True, exist_ok=True)
        (MEDIA / name).write_bytes(blob)
        idx = jload(MEDIA_INDEX, {})
        idx[name] = {"label": (label or Path(str(filename)).stem)[:120], "src": src, "prompt": prompt[:1500], "at": now()}
        jsave(MEDIA_INDEX, idx)
    return name


def media_list():
    idx = jload(MEDIA_INDEX, {})
    out = [{"file": f, **m} for f, m in idx.items() if media_ok(f)]
    return sorted(out, key=lambda x: x["file"], reverse=True)


def media_used(name):
    used = []
    for f in DECKS.glob("*.json"):
        d = jload(f, {})
        if any((s.get("img") or {}).get("file") == name for s in d.get("slides") or []):
            used.append(d.get("title") or plain((d.get("slides") or [{}])[0].get("title", "")) or d.get("id"))
    return used


# ---------------- Claude ----------------
def claude_bin():
    return cfg.claude_bin()


def ask(prompt, timeout, web=False, effort=None):
    """claude -p بیرون از پوشه‌ی استودیو (CLAUDE.md و حافظه قاطی نشوند)؛ پرامپت از stdin."""
    cmd = [claude_bin(), "-p", "--output-format", "json", "--model", am.get("carousel"), "--no-session-persistence", "--safe-mode"]
    cmd += ["--tools", "WebSearch,WebFetch", "--allowedTools", "WebSearch", "WebFetch"] if web else ["--tools", ""]
    if effort:
        cmd += ["--effort", effort]
    r = subprocess.run(cmd, input=prompt, cwd=tempfile.gettempdir(), capture_output=True, text=True, timeout=timeout)
    try:
        out = json.loads(r.stdout)
    except Exception:
        out = {}
    return r.returncode, (out.get("result") or "").strip(), (r.stderr or "")[-300:]


def json_block(text, a, b):
    """JSON بین دو نشانه؛ اگر نشانه‌ها یا حصار ``` جابه‌جا بودند، از اولین { تا آخرین }."""
    t = text or ""
    i = t.find(a)
    if i >= 0:
        j = t.find(b, i + len(a))
        t = t[i + len(a): j if j >= 0 else None]
    t = re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", t.strip())
    for cand in (t, t[t.find("{"): t.rfind("}") + 1] if "{" in t else ""):
        try:
            v = json.loads(cand)
            if isinstance(v, dict):
                return v
        except Exception:
            pass
    return None


SLIDE_RULES = """- هر اسلاید فقط یک حرف. تیتر حداکثر حدود ۸ کلمه. متن حداکثر حدود ۴۵ کلمه در یک تا سه پاراگراف کوتاه؛ اسلاید شلوغ خوانده نمی‌شود.
- هر اسلاید باید یک دلیل برای ورق زدن به بعدی بدهد. اگر کاروسل فهرست است، شماره‌ی هر مورد اول تیتر همان اسلاید بیاید.
- فارسی محاوره‌ای و صدای خود او (بخش «صدا و لحن»)، خطاب «شما». اصطلاح فنی انگلیسی بماند و بار اول یک توضیح کوتاه فارسی بگیرد.
- تأکید: در هر اسلاید یک تا سه کلمه یا عبارت کلیدی را بین ** بگذار (روی تصویر رنگی می‌شود)؛ هرگز کل اسلاید را.
- هیچ عدد، آمار، تاریخ، قیمت یا نقل‌قولی که در ورودی یا هسته‌ی برند نیست نساز. تردید منبع را منتقل کن و اسم گوینده را بیاور.
- روی اسلایدها ایموجی نه. تاریخ میلادی با معادل شمسی داخل پرانتز."""

COVER_RULE = """- اسلاید ۱ کاور است: تیتری که در یک نگاه می‌گوید خواننده با ورق زدن چه می‌گیرد (فهرست با عدد، اسم مشخص یا نتیجه‌ی مشخص) و به زندگی یا کار خود خواننده وصل است؛ حداکثر حدود ۱۲ کلمه، بدون کلیک‌بیت دروغ. متن زیر تیتر کاور اختیاری و حداکثر یک جمله‌ی کوتاه است."""

LAST_RULE = """- اسلاید آخر جمع‌بندی و دعوت به اقدام است، دقیقاً طبق قواعد CTA و «کتابخانه‌ی CTA» هسته‌ی برند. اگر هسته‌ی برند CTA مشخصی ندارد، «سیو کنین» یا «برای کسی که لازمش داره بفرستین» بنویس."""

CAPTION_RULES = """کپشن: نوشتاری، نه گفتاری. خط اول خودش هوک است (فقط همان قبل از «بیشتر» دیده می‌شود). دو تا پنج پاراگراف کوتاه که حرف اصلی کاروسل را خلاصه می‌کند و یک چیز اضافه می‌دهد؛ آخرش همان دعوت به اقدام. ایموجی کم. هشتگ داخل کپشن نه.
هشتگ‌ها: سه تا پنج، نه بیشتر (اینستاگرام از دسامبر ۲۰۲۵ بیشتر از پنج هشتگ نمی‌گذارد)؛ ترکیب فارسی و انگلیسی، از خاص به عام، همه در یک خط با فاصله."""

GEN_PROMPT = """تو نویسنده‌ی کاروسل‌های اینستاگرام __OWNER__ هستی.

هسته‌ی برند او این است. «خط قرمزها» و قواعد CTA قانون‌اند، نه سلیقه:
<<<BRAND
__BRAND__
BRAND>>>

__SOURCE__

کار: از این ورودی یک کاروسل اینستاگرام بساز (پست چنداسلایدی، هر اسلاید یک تصویر ۴:۵). __COUNT__

قواعد:
__COVER__
__SLIDES__
__LAST__
__KEEP__
__WEB__

تصویر:
__MEDIA__
- برای اسلایدهایی که یک تصویر واقعاً به فهمش کمک می‌کند (حداکثر نصف اسلایدها؛ اسلایدی که متنش بلند است نه)، یا یکی از فایل‌های کتابخانه‌ی بالا را با اسم دقیقش انتخاب کن (فقط اگر توضیحش به همان اسلاید می‌خورد)، یا یک پرامپت انگلیسی کوتاه برای ساخت تصویر بنویس: یک صحنه‌ی ساده و مشخص که حرف همان اسلاید را نشان می‌دهد. سبک و رنگ را خود استودیو اضافه می‌کند؛ هیچ متن، حرف، عدد یا لوگویی در تصویر نخواه.
- imageMode یکی از این‌هاست: below (زیر متن)، above (بالای متن)، between (بین تیتر و متن)، circle (فقط عکس چهره‌ی یک آدم از کتابخانه، گرد و بالای تیتر)، bg (زمینه‌ی کل اسلاید زیر یک لایه‌ی رنگ).

__CAPTION__

خروجی: فقط یک JSON معتبر بین یک خط <<<CAROUSEL و یک خط CAROUSEL>>>، بدون هیچ توضیح دیگری:
<<<CAROUSEL
{"title": "اسم کوتاه این کاروسل برای فهرست استودیو",
 "slides": [{"title": "...", "body": "...", "image": null, "imageMode": "below"}],
 "caption": "...", "hashtags": "#... #...",
 "note": "امتیاز: X/۱۰ — یک جمله که چرا این کاروسل کار می‌کند"}
CAROUSEL>>>
مقدار image یکی از این‌هاست: null، {"file": "اسم فایل کتابخانه"}، یا {"prompt": "English scene description"}.
خط تازه‌ی داخل متن‌ها را با \\n بنویس (خط خالی = پاراگراف تازه). هیچ سؤالی نپرس."""

REGEN_PROMPT = """تو نویسنده‌ی کاروسل‌های اینستاگرام __OWNER__ هستی. هسته‌ی برند او (خط قرمزها و قواعد CTA قانون‌اند):
<<<BRAND
__BRAND__
BRAND>>>

این کاروسل فعلی است. کاربر ممکن است بخش‌هایی را دستی ویرایش کرده باشد؛ آن ویرایش‌ها تصمیم خود اوست، به آن‌ها احترام بگذار:
<<<CURRENT
__CURRENT__
CURRENT>>>

__TASK__

__NOTE__

اگر نظر کاربر عدد، منبع یا خبر تازه می‌خواهد، با WebSearch و WebFetch بگرد و منبع را در متن بگو؛ هیچ عددی از حافظه نیاور.

__RULES__

خروجی: فقط یک JSON معتبر بین یک خط <<<OUT و یک خط OUT>>>، بدون هیچ توضیح دیگری:
<<<OUT
__SHAPE__
OUT>>>
خط تازه‌ی داخل متن‌ها را با \\n بنویس. هیچ سؤالی نپرس."""


def brand_text():
    return read_text(BRAND_MD) or "(هسته‌ی برند خالی است)"


def idea_record(iid):
    ideas = jload(ROOT / "data" / "ideas.json", [])
    return next((i for i in ideas if i.get("id") == iid), None)


def source_block(opts):
    if opts["mode"] == "idea":
        it = idea_record(opts["idea"]) or {}
        d = IDEAS / opts["idea"]
        parts = [f"ورودی: ایده‌ی «{it.get('title', opts['idea'])}» از بانک ایده‌ی خودش. فایل‌هایش:"]
        for f, label, note in (("raw.md", "RAW", "ایده‌ی خام خود کاربر"),
                               ("brief.md", "BRIEF", "دستورالعمل کاربر"),
                               ("analysis.md", "ANALYSIS", "تحلیل"),
                               ("research.md", "RESEARCH", "پژوهش وب؛ فقط عددها و حرف‌های منبع‌دار همین‌جا مجازند"),
                               ("reel.md", "REEL", "متن ریلزی که از همین ایده ساخته شده؛ کاروسل قالب دیگری است، فقط مایه بگیر")):
            t = read_text(d / f, 40000).strip()
            if t:
                parts.append(f"({note})\n<<<{label}\n{t}\n{label}>>>")
        return "\n\n".join(parts)
    return "ورودی: متنی که خود کاربر نوشته (ممکن است یک ایده‌ی کوتاه باشد یا یک متن کامل):\n<<<TEXT\n" + opts["text"] + "\nTEXT>>>"


def gen_prompt(opts):
    n = opts["count"]
    count = (f"دقیقاً {n} اسلاید." if n else
             "تعداد اسلایدها را خودت از روی محتوا انتخاب کن: بین ۵ و ۸، و هرگز بیشتر از ۱۰.")
    keep = ("- متن کاربر را عیناً نگه دار: کلمه، ترتیب و لحنش عوض نمی‌شود؛ فقط بین اسلایدها تقسیمش کن و تأکیدها را بگذار. "
            "تیتر اسلایدها و کاور را می‌توانی کوتاه و تازه بنویسی، ولی هیچ ادعای تازه‌ای اضافه نکن."
            if opts["keep"] else "")
    web = ("- اگر برای دقیق کردن حرف‌ها به عدد یا منبع تازه نیاز است، با WebSearch و WebFetch بگرد و منبع را در کپشن بگو. "
           "از هیچ منبعی کامل ترجمه نکن." if opts["web"] else
           "- به وب دسترسی نداری؛ فقط از ورودی و هسته‌ی برند استفاده کن.")
    lib = media_list()
    media = ("- کتابخانه‌ی تصویر کاربر (اسم فایل — توضیح):\n" + "\n".join(f"  - {m['file']} — {m['label']}" for m in lib[:40])
             if lib else "- کتابخانه‌ی تصویر کاربر فعلاً خالی است.")
    notes = opts.get("notes", "").strip()
    p = (GEN_PROMPT.replace("__OWNER__", cfg.owner_line()).replace("__BRAND__", brand_text()).replace("__SOURCE__", source_block(opts))
         .replace("__COUNT__", count).replace("__COVER__", COVER_RULE).replace("__SLIDES__", SLIDE_RULES)
         .replace("__LAST__", LAST_RULE).replace("__KEEP__", keep).replace("__WEB__", web)
         .replace("__MEDIA__", media).replace("__CAPTION__", CAPTION_RULES))
    if notes:
        p += "\n\nخواسته‌ی کاربر برای همین کاروسل — بر قواعد بالا (جز خط قرمزها) اولویت دارد:\n<<<NOTE\n" + notes + "\nNOTE>>>"
    return p


def deck_md(deck):
    out = []
    n = len(deck["slides"])
    for k, s in enumerate(deck["slides"]):
        tag = " (کاور)" if k == 0 else " (آخر)" if k == n - 1 and n > 1 else ""
        out.append(f"## اسلاید {k + 1}{tag}\nتیتر: {html_to_md(s.get('title', '')) or '—'}\n"
                   f"متن:\n{html_to_md(s.get('body', '')) or '—'}")
    out.append("## کپشن\n" + (deck.get("caption") or "—"))
    out.append("## هشتگ‌ها\n" + (deck.get("hashtags") or "—"))
    return "\n\n".join(out)


def _slide_from_ai(x):
    title = str(x.get("title") or "").strip()
    body = str(x.get("body") or "").strip()
    image, mode = x.get("image"), x.get("imageMode")
    mode = mode if mode in IMG_MODES and mode != "full" else "below"
    img, prompt = None, ""
    if isinstance(image, dict):
        if media_ok(image.get("file")):
            img = {"file": image["file"], "mode": mode, "fit": "cover" if mode in ("circle", "bg") else "contain", "dim": 0.65}
        elif isinstance(image.get("prompt"), str):
            prompt = image["prompt"].strip()[:1200]
    s = new_slide(md_to_html(title), md_to_html(body), img, prompt)
    if prompt:
        s["imgMode"] = mode
    return s


# ---------------- کارهای پس‌زمینه ----------------
def jset(key, **kw):
    with JLOCK:
        JOBS.setdefault(key, {}).update(kw)


def jget(key):
    with JLOCK:
        return dict(JOBS.get(key, {}))


def start(key, target, *args, **fields):
    with JLOCK:
        if JOBS.get(key, {}).get("state") == "running":
            return False
        JOBS[key] = {"state": "running", "step": "", "error": "", "started": time.time(), **fields}
    threading.Thread(target=target, args=args, daemon=True).start()
    return True


def run_generate(did, opts):
    key = f"{did}:gen"
    try:
        jset(key, step="Claude دارد متن اسلایدها را می‌نویسد… (معمولاً ۱ تا ۳ دقیقه)")
        code, res, err = ask(gen_prompt(opts), 2400, web=opts["web"], effort="high")
        data = json_block(res, "<<<CAROUSEL", "CAROUSEL>>>") if res else None
        slides = [x for x in (data or {}).get("slides") or [] if isinstance(x, dict)]
        if code != 0 or not slides:
            if res:
                (DIR / "gen").mkdir(parents=True, exist_ok=True)
                (DIR / "gen" / f"{did}.last-output.txt").write_text(res, encoding="utf-8")
            return jset(key, state="error", error="ساخت کاروسل ناتمام ماند." + (f" {err}" if err and code else
                        " خروجی قالب درستی نداشت (data/carousels/gen/ را ببین)." if res else ""))
        made = [_slide_from_ai(x) for x in slides[:MAX_SLIDES]]
        with LOCK:
            deck = load(did)
            deck.update(title=str(data.get("title") or "")[:200] or deck.get("title", ""), slides=made,
                        caption=str(data.get("caption") or "").strip(),
                        hashtags=five_tags(data.get("hashtags")),
                        note=str(data.get("note") or "").strip()[:500])
            deck["source"]["at"] = now()
            _write(deck)
        want = [s for s in made if s.get("imgPrompt")][:5] if opts["images"] else []
        warn = []
        for k, s in enumerate(want, 1):
            jset(key, step=f"ساخت تصویر {fa(k)} از {fa(len(want))} با Gemini…")
            try:
                make_image(did, s["id"], s["imgPrompt"], s.get("imgMode") or "below")
            except Exception as e:
                warn.append(str(e)[:200])
        jset(key, state="done", step="تمام شد", warn=" · ".join(dict.fromkeys(warn)))
    except subprocess.TimeoutExpired:
        jset(key, state="error", error="زمان ساخت تمام شد.")
    except Exception as e:
        jset(key, state="error", error=f"خطا: {e}")


def fa(n):
    return str(n).translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))


def run_regen(did, target, sid, note):
    key = f"{did}:{sid if target == 'slide' else 'caption'}"
    try:
        deck = load(did)
        idx = next((k for k, s in enumerate(deck["slides"]) if s["id"] == sid), -1) if target == "slide" else -1
        if target == "slide" and idx < 0:
            return jset(key, state="error", error="این اسلاید دیگر نیست.")
        n = len(deck["slides"])
        history = (deck["slides"][idx].get("notes") if target == "slide" else deck.get("captionNotes")) or []
        note_block = ("نظر کاربر برای این بازنویسی — مهم‌ترین ورودی است، دقیقاً اجرایش کن:\n<<<NOTE\n" + note + "\nNOTE>>>"
                      if note else "کاربر نظر خاصی ننوشته؛ یک نسخه‌ی تازه و بهتر بنویس که با نسخه‌ی فعلی فرق واقعی داشته باشد.")
        if history:
            note_block += "\n\nنظرهای قبلی کاربر درباره‌ی همین بخش (تا خواسته‌های قبلی‌اش گم نشود):\n" + "\n".join(
                f"- {h['t']}" for h in history[-4:])
        if target == "slide":
            task = (f"فقط اسلاید {fa(idx + 1)} را از نو بنویس (تیتر و متنش). بقیه‌ی اسلایدها دست نمی‌خورند، "
                    "پس اسلاید تازه باید با آن‌ها جور باشد: ترتیب، شماره‌ی فهرست و لحن.")
            rules = "قواعد اسلاید:\n" + (COVER_RULE + "\n" if idx == 0 else "") + SLIDE_RULES + (
                "\n" + LAST_RULE if idx == n - 1 and n > 1 else "")
            shape = '{"title": "...", "body": "..."}'
        else:
            task = "فقط کپشن و هشتگ‌های این کاروسل را از نو بنویس؛ اسلایدها دست نمی‌خورند."
            rules = CAPTION_RULES + "\nقواعد CTA هسته‌ی برند در کپشن هم قانون است."
            shape = '{"caption": "...", "hashtags": "#... #..."}'
        prompt = (REGEN_PROMPT.replace("__OWNER__", cfg.owner_line()).replace("__BRAND__", brand_text()).replace("__CURRENT__", deck_md(deck))
                  .replace("__TASK__", task).replace("__NOTE__", note_block).replace("__RULES__", rules)
                  .replace("__SHAPE__", shape))
        jset(key, step="Claude دارد بازنویسی می‌کند…")
        code, res, err = ask(prompt, 1500, web=True)
        data = json_block(res, "<<<OUT", "OUT>>>") if res else None
        ok = data and (str(data.get("title") or data.get("body") or "").strip() if target == "slide"
                       else str(data.get("caption") or "").strip())
        if code != 0 or not ok:
            return jset(key, state="error", error="بازنویسی ناتمام ماند." + (f" {err}" if err else ""))
        stamp = {"t": note, "at": time.strftime("%Y-%m-%d %H:%M")} if note else None
        with LOCK:
            deck = load(did)
            if target == "slide":
                s = next((x for x in deck["slides"] if x["id"] == sid), None)
                if not s:
                    return jset(key, state="error", error="این اسلاید وسط کار حذف شد.")
                s["prev"] = {"title": s.get("title", ""), "body": s.get("body", "")}
                s["title"] = md_to_html(str(data.get("title") or "").strip())
                s["body"] = md_to_html(str(data.get("body") or "").strip())
                if stamp:
                    s.setdefault("notes", []).append(stamp)
            else:
                deck["prevCaption"] = {"caption": deck.get("caption", ""), "hashtags": deck.get("hashtags", "")}
                deck["caption"] = str(data.get("caption") or "").strip()
                deck["hashtags"] = five_tags(data.get("hashtags"))
                if stamp:
                    deck.setdefault("captionNotes", []).append(stamp)
            _write(deck)
        jset(key, state="done", step="تمام شد")
    except subprocess.TimeoutExpired:
        jset(key, state="error", error="زمان بازنویسی تمام شد.")
    except Exception as e:
        jset(key, state="error", error=f"خطا: {e}")


def undo(did, target, sid):
    with LOCK:
        deck = load(did)
        if not deck:
            return 404, {"error": "این کاروسل پیدا نشد."}
        if target == "slide":
            s = next((x for x in deck["slides"] if x["id"] == sid), None)
            if not s or not s.get("prev"):
                return 404, {"error": "نسخه‌ی قبلی نیست."}
            s["prev"], s["title"], s["body"] = ({"title": s["title"], "body": s["body"]},
                                                s["prev"]["title"], s["prev"]["body"])
        else:
            p = deck.get("prevCaption")
            if not p:
                return 404, {"error": "نسخه‌ی قبلی نیست."}
            deck["prevCaption"] = {"caption": deck.get("caption", ""), "hashtags": deck.get("hashtags", "")}
            deck["caption"], deck["hashtags"] = p["caption"], p["hashtags"]
        _write(deck)
    return 200, {"ok": True}


# ---------------- تصویر با Gemini ----------------
def gemini_key():
    return cfg.gemini_key()


def brand_palette():
    """رنگ‌های «هسته‌ی برند ← هویت بصری» (hex)."""
    try:
        d = json.loads((ROOT / "brand" / "brand-core.json").read_text(encoding="utf-8"))
        return [c["hex"] for c in (d["fields"].get("colors") or {}).get("v") or []
                if isinstance(c, dict) and re.fullmatch(r"#[0-9a-fA-F]{6}", c.get("hex") or "")]
    except Exception:
        return []


IMG_STYLE = ("Flat vector illustration for a professional Instagram carousel for a personal brand. "
             "Minimal, clean geometric shapes, generous empty space, no gradients, no photo-realism. "
             "Background color exactly {bg}. Accent colors only from: {palette}. "
             "Absolutely no text, letters, numbers, captions, logos or watermarks anywhere in the image.")


def gen_image(prompt, aspect, bg):
    key = gemini_key()
    if not key:
        raise RuntimeError("کلید Gemini تنظیم نشده؛ از تب «تنظیمات» واردش کن (رایگان است).")
    light = _lum(bg) > 0.6
    brand = [c for c in brand_palette() if c.lower() != bg.lower()]
    # روی زمینه‌ی روشن رنگ‌های تیره‌تر برند، روی زمینه‌ی تیره روشن‌ترها؛ اگر برند رنگی نداشت، خنثی
    pick = sorted(brand, key=_lum, reverse=not light)[:4]
    palette = ", ".join(pick) if pick else ("#22262e charcoal, #4a6fa5 blue, #ffcc4d yellow" if light else
                                            "#ffffff white, #8ecae6 light blue, #ffcc4d yellow")
    body = {"contents": [{"parts": [{"text": IMG_STYLE.format(bg=bg, palette=palette) + "\nScene: " + prompt}]}],
            "generationConfig": {"responseModalities": ["IMAGE"], "imageConfig": {"aspectRatio": aspect}}}
    last = ""
    for model in IMG_MODELS:
        req = urllib.request.Request(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            data=json.dumps(body).encode("utf-8"),
            headers={"x-goog-api-key": key, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=150) as r:
                d = json.loads(r.read())
        except urllib.error.HTTPError as e:
            last = f"Gemini {e.code}"
            continue
        except Exception as e:
            last = str(e)[:120]
            continue
        for c in d.get("candidates") or []:
            for p in (c.get("content") or {}).get("parts") or []:
                if "inlineData" in p:
                    mime = p["inlineData"].get("mimeType", "image/png")
                    return base64.b64decode(p["inlineData"]["data"]), (".jpg" if "jpeg" in mime else ".png")
        last = "Gemini تصویری برنگرداند"
    raise RuntimeError(f"ساخت تصویر نشد ({last}).")


def _lum(hexc):
    try:
        n = int(str(hexc).lstrip("#")[:6], 16)
    except ValueError:
        return 0
    return (0.2126 * (n >> 16 & 255) + 0.7152 * (n >> 8 & 255) + 0.0722 * (n & 255)) / 255


def make_image(did, sid, prompt, mode):
    deck = load(did) or {}
    st = deck.get("style") or {}
    idx = next((k for k, s in enumerate(deck.get("slides") or []) if s["id"] == sid), 0)
    bg = st.get("altBg") if st.get("alt") == "light" and idx % 2 == 1 else st.get("bg")
    if mode == "bg":
        bg = "#0b1c24"
    blob, ext = gen_image(prompt, ASPECT.get(mode, "16:9"), bg or "#1a3c64")
    name = save_media(f"ai{ext}", blob, label="هوش مصنوعی: " + prompt[:70], src="ai", prompt=prompt)
    with LOCK:
        deck = load(did)
        s = next((x for x in (deck or {}).get("slides") or [] if x["id"] == sid), None)
        if s is not None:
            s["img"] = {"file": name, "mode": mode if mode in IMG_MODES else "below",
                        "fit": "cover" if mode in ("circle", "bg", "full") else "contain", "dim": 0.65}
            s["imgPrompt"] = prompt
            _write(deck)
    return name


def run_image(did, sid, prompt, mode):
    key = f"{did}:img-{sid}"
    try:
        jset(key, step="Gemini دارد تصویر را می‌سازد… (حدود ۱۰ ثانیه)")
        name = make_image(did, sid, prompt, mode)
        jset(key, state="done", step="تمام شد", file=name)
    except Exception as e:
        jset(key, state="error", error=str(e)[:300])


# ---------------- انتشار در اینستاگرام (از راه سایت) ----------------
def five_tags(s):
    """اینستاگرام از دسامبر ۲۰۲۵ بیشتر از ۵ هشتگ نمی‌گذارد (مرجع API هنوز ۳۰ می‌گوید)؛ اگر Claude بیشتر داد، پنج‌تای اول
    که خاص‌ترها هستند می‌ماند. ویرایش دستی کاربر کوتاه نمی‌شود؛ شمارنده و بررسی پیش از انتشار خبر می‌دهند."""
    words = str(s or "").split()
    tags = [w for w in words if w.startswith("#")]
    return " ".join(tags[:5]) if tags else " ".join(words)


def hashtag_count(text):
    return len(re.findall(r"(?:^|\s)#[^\s#]+", text or ""))


def full_caption(deck):
    cap, tags = (deck.get("caption") or "").strip(), " ".join((deck.get("hashtags") or "").split())
    return cap + ("\n\n" + tags if cap and tags else tags)


def decode_jpeg(data_url):
    try:
        blob = base64.b64decode(str(data_url).split(",")[-1])
    except Exception:
        return None
    return blob if blob[:3] == b"\xff\xd8\xff" and len(blob) <= 8 * 1024 * 1024 else None


# ---------------- مسیرهای HTTP ----------------
def handle_get(p, q):
    """(code, payload, ctype) — ctype=None یعنی payload جیسون است."""
    if p in STATIC:
        name, ctype = STATIC[p]
        return 200, (APP / name).read_bytes(), ctype
    if p == "/api/carousel/list":
        return 200, {"decks": list_decks()}, None
    if p == "/api/carousel/deck":
        did = q.get("id", [""])[0]
        d = load(did)
        if not d:
            return 404, {"error": "این کاروسل پیدا نشد."}, None
        with JLOCK:
            jobs = {k.split(":", 1)[1]: dict(v) for k, v in JOBS.items() if k.startswith(did + ":")}
        return 200, {"deck": d, "jobs": jobs}, None
    if p == "/api/carousel/status":
        did = q.get("id", [""])[0]
        with JLOCK:
            jobs = {k: dict(v) for k, v in JOBS.items() if not did or k.startswith(did + ":")}
        return 200, {"jobs": jobs, "running": sorted(k for k, v in jobs.items() if v.get("state") == "running")}, None
    if p == "/api/carousel/media":
        return 200, {"media": media_list()}, None
    if p == "/api/carousel/style":
        return 200, jload(SETTINGS, {}), None
    if p.startswith("/carousel-media/"):
        name = p[len("/carousel-media/"):]
        if not media_ok(name):
            return 404, {"error": "not found"}, None
        return 200, (MEDIA / name).read_bytes(), IMG[Path(name).suffix.lower()]
    return None


def handle_post(p, body):
    if not p.startswith("/api/carousel/"):
        return None
    did = body.get("id", "")

    if p == "/api/carousel/new":
        return 200, {"ok": True, "deck": create(str(body.get("title") or "")[:200])}
    if p == "/api/carousel/save":
        return save(body)
    if p == "/api/carousel/delete":
        return delete(did)
    if p == "/api/carousel/duplicate":
        return duplicate(did)

    if p == "/api/carousel/style":
        style = body.get("style")
        if not isinstance(style, dict) or len(json.dumps(style)) > 20000:
            return 400, {"error": "bad payload"}
        cur = {"style": style, "preset": str(body.get("preset") or "")[:40], "updated": now()}
        with LOCK:
            jsave(SETTINGS, cur)
        return 200, {"ok": True, **cur}

    if p == "/api/carousel/media":
        try:
            blob = base64.b64decode(str(body.get("data") or "").split(",")[-1])
            name = save_media(body.get("filename"), blob, str(body.get("label") or ""))
        except ValueError as e:
            return 400, {"error": str(e)}
        except Exception:
            return 400, {"error": "فایل خوانده نشد."}
        return 200, {"ok": True, "file": name, "media": media_list()}
    if p == "/api/carousel/media/label":
        name = body.get("file")
        if not media_ok(name):
            return 404, {"error": "این تصویر پیدا نشد."}
        with LOCK:
            idx = jload(MEDIA_INDEX, {})
            idx.setdefault(name, {})["label"] = str(body.get("label") or "").strip()[:120]
            jsave(MEDIA_INDEX, idx)
        return 200, {"ok": True}
    if p == "/api/carousel/media/delete":
        name = body.get("file")
        if not media_ok(name):
            return 404, {"error": "این تصویر پیدا نشد."}
        used = media_used(name)
        if used:
            return 409, {"error": "این تصویر در این کاروسل‌ها استفاده شده: " + "، ".join(used[:5])}
        with LOCK:
            (MEDIA / "trash").mkdir(parents=True, exist_ok=True)
            (MEDIA / name).replace(MEDIA / "trash" / name)
            idx = jload(MEDIA_INDEX, {})
            idx.pop(name, None)
            jsave(MEDIA_INDEX, idx)
        return 200, {"ok": True, "media": media_list()}
    if p == "/api/carousel/generate":
        again = load(did) if did else None
        if did and not again:
            return 404, {"error": "این کاروسل پیدا نشد."}
        src = (again or {}).get("source") or {}
        if again and src.get("kind") not in ("text", "idea"):
            return 400, {"error": "این کاروسل با هوش مصنوعی ساخته نشده که از نو ساخته شود."}
        b = src if again else body
        mode = "idea" if (b.get("kind") if again else b.get("mode")) == "idea" else "text"
        text = str(b.get("text") or "").strip()
        idea = str(b.get("idea") or "")
        if mode == "text" and len(text) < 3:
            return 400, {"error": "متن یا ایده را بنویس."}
        if mode == "idea" and not (_safe(idea) and (IDEAS / idea / "raw.md").exists()):
            return 400, {"error": "این ایده پیدا نشد."}
        try:
            count = int(b.get("count") or 0)
        except (TypeError, ValueError):
            count = 0
        opts = {"mode": mode, "text": text[:60000], "idea": idea if mode == "idea" else "",
                "count": count if 2 <= count <= PUBLISH_MAX else 0, "keep": bool(b.get("keep")) and mode == "text",
                "web": bool(b.get("web")), "images": bool(b.get("images")), "notes": str(b.get("notes") or "")[:4000]}
        source = {"kind": mode, **{k: v for k, v in opts.items() if k != "mode"}}
        if again:
            if f"{did}:gen" in JOBS and generating(did):
                return 409, {"error": "این کاروسل همین حالا در حال ساخت است."}
            with LOCK:
                deck = load(did)
                deck["prevSlides"] = deck.get("slides") or deck.get("prevSlides")   # کاروسل قبلی دور ریخته نمی‌شود
                deck["slides"] = []
                _write(deck)
        else:
            it = idea_record(idea) if mode == "idea" else None
            deck = create(title=str((it or {}).get("title", ""))[:200], source=source, slides=[])
        start(f"{deck['id']}:gen", run_generate, deck["id"], opts, kind="gen")
        return 200, {"ok": True, "id": deck["id"]}

    if p == "/api/carousel/regen":
        target = "caption" if body.get("target") == "caption" else "slide"
        sid = str(body.get("slide") or "")
        deck = load(did)
        if not deck or (target == "slide" and not any(s["id"] == sid for s in deck["slides"])):
            return 400, {"error": "bad request"}
        note = str(body.get("note") or "").strip()[:4000]
        key = f"{did}:{sid if target == 'slide' else 'caption'}"
        if not start(key, run_regen, did, target, sid, note, kind="regen", slide=sid if target == "slide" else ""):
            return 409, {"error": "همین بخش در حال بازنویسی است."}
        return 200, {"ok": True}
    if p == "/api/carousel/undo":
        return undo(did, "caption" if body.get("target") == "caption" else "slide", str(body.get("slide") or ""))

    if p == "/api/carousel/image":
        sid, prompt = str(body.get("slide") or ""), str(body.get("prompt") or "").strip()[:1200]
        mode = body.get("mode") if body.get("mode") in IMG_MODES else "below"
        deck = load(did)
        if not deck or not prompt or not any(s["id"] == sid for s in deck["slides"]):
            return 400, {"error": "اول بنویس چه تصویری می‌خواهی."}
        if not start(f"{did}:img-{sid}", run_image, did, sid, prompt, mode, kind="image", slide=sid):
            return 409, {"error": "تصویر همین اسلاید در حال ساخت است."}
        return 200, {"ok": True}

    if p.startswith("/api/carousel/publish"):
        return 410, {"error": "انتشار مستقیم در این استودیو نیست؛ اسلایدها را دانلود کن و خودت منتشر کن."}
    return 404, {"error": "not found"}
