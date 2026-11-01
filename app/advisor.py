"""مشاور — چت‌بات مشاور مارکتینگ داخل استودیو.

هر گفت‌وگو یک سشن Claude Code است (روی اشتراک خود کاربر، بدون کلید API) که با --resume ادامه پیدا می‌کند.
دستورالعمل و «پرونده» (هسته‌ی برند، آمار اینستاگرام، گزارش تحلیلگر، بانک ایده، ترجمه‌ها، استوری‌ها، حافظه)
یک بار در شروع هر گفت‌وگو ساخته می‌شود و ثابت می‌ماند تا کش شود.

مشاور فقط می‌خواند: ابزارهایش Read/Grep/Glob روی «پوشه‌ی دانش» (data/advisor/kb — کپی داده‌های بی‌خطر استودیو،
نه .env و کلیدها) و WebSearch/WebFetch است. ذخیره‌ی ایده و یادداشت فقط با دکمه‌ی کاربر انجام می‌شود.

صدا: جواب‌ها با Gemini TTS خوانده می‌شوند (کلید خود کاربر از «تنظیمات») و روی دیسک کش می‌شوند.

داده‌ها (data/advisor/):
  chats/<id>/chat.json   پیام‌ها و سشن
  chats/<id>/system.md   دستورالعمل + پرونده‌ی همین گفت‌وگو
  chats/<id>/audio/      صدای جواب‌ها
  kb/                    پوشه‌ی دانش (هر گفت‌وگوی تازه از نو ساخته می‌شود)
  memory.json            حافظه‌ی مشاور
  stories.json           استوری‌هایی که در تب استوری دانلود یا کپی شده‌اند
  settings.json          صدا، سرعت، خواندن خودکار
  usage.json             آخرین سهمیه‌ای که Claude Code گزارش داده
  voices/                نمونه‌ی هر صدا
  work/                  cwd ثابت claude؛ سشن‌ها با همین مسیر پیدا می‌شوند
"""
import json, re, time, uuid, shutil, subprocess, threading, base64, struct, statistics, tempfile, socket
import urllib.request, urllib.error
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
import settings as cfg            # IDEAS_LOCK: همه‌ی نوشتن‌های ideas.json از این قفل رد می‌شوند
import ai_models as am
import voice
import brand as bc

APP = Path(__file__).resolve().parent
ROOT = APP.parent
DATA = ROOT / "data"
IDEAS = DATA / "ideas"
OUTPUT = ROOT / "modules" / "reels" / "output"
DIR = DATA / "advisor"
CHATS = DIR / "chats"
KB = DIR / "kb"
WORK = DIR / "work"
VOICES_DIR = DIR / "voices"

EFFORT = {"normal": "high", "deep": "xhigh"}   # پیش‌فرض «medium» برای مشاوره کم است
TOOLS = ["Read", "Grep", "Glob", "WebSearch", "WebFetch"]
TURN_TIMEOUT = 20 * 60
TTS_MODEL = "gemini-3.8-flash-tts"             # تست ۲۰۲۶-۱۰-۰۵: بهترین تطابق رفت‌وبرگشت و سریع‌ترین در میان ۵ مدل TTS
# کلید Gemini برای هر مدل TTS سقف ۱۰ درخواست در دقیقه دارد (۴۲۹، اندازه‌گیری ۲۰۲۶-۱۰-۰۵). مدل دوم سهمیه‌ی جدا دارد و
# همان صداها را می‌شناسد؛ در تست رفت‌وبرگشت فارسی ۰٫۹۷ گرفت. اگر هر دو پر بودند، به‌اندازه‌ی retryDelay صبر می‌کنیم.
TTS_FALLBACK = "gemini-3.1-flash-tts-preview"


def listen_hint():
    return f"گفت‌وگوی {cfg.owner()} با مشاور برند شخصی‌اش درباره‌ی محتوای اینستاگرام، ریلز، استوری و کار و برندش"


def now():
    """ساعت محلی همین کامپیوتر."""
    return datetime.now().astimezone()

STATIC = {"/advisor.js": ("advisor.js", "text/javascript; charset=utf-8"),
          "/advisor.css": ("advisor.css", "text/css; charset=utf-8")}

LOCK = threading.Lock()                        # chat.json ها، حافظه، تنظیم‌ها
KB_LOCK = threading.Lock()
TTS_LOCKS = defaultdict(threading.Lock)
JOBS = {}                                      # chat id → نوبتِ در حال اجرا
JLOCK = threading.Lock()

# صداهایی که ۲۰۲۶-۱۰-۰۵ روی متن فارسی تست شدند (همه متن را کامل و درست خواندند)
VOICES = [
    ("Sadaltager", "مرد، دانا و آرام"), ("Achird", "مرد، دوستانه"), ("Charon", "مرد، رسمی و روشن"),
    ("Algieba", "مرد، نرم"), ("Iapetus", "مرد، شفاف"), ("Orus", "مرد، محکم"), ("Puck", "مرد، پرانرژی"),
    ("Gacrux", "مرد، پخته"), ("Sulafat", "زن، گرم"), ("Aoede", "زن، سبک و روان"), ("Despina", "زن، نرم"),
    ("Kore", "زن، محکم"),
]
VOICE_NAMES = {v for v, _ in VOICES}
DEFAULT_SETTINGS = {"voice": "Sadaltager", "rate": 1.0, "autoplay": False}
SAMPLE_TEXT = ("سلام! من مشاورتم. ایده‌ات رو بگو تا با هم ببینیم چقدر قویه، "
               "به برندت می‌خوره یا نه، و چطور می‌شه بهترش کرد.")


# ---------- ابزار ----------
def claude_bin():
    return cfg.claude_bin()


def fa(n):
    return str(n).translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))


def jread(f, default):
    try:
        return json.loads(Path(f).read_text(encoding="utf-8"))
    except Exception:
        return default


def jwrite(f, obj):
    f = Path(f)
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_name(f.name + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(f)


def read_text(f, limit=None):
    try:
        t = Path(f).read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""
    return t if limit is None or len(t) <= limit else t[:limit].rstrip() + "…"


def strip_bidi(s):
    return re.sub(r"[⁦-⁩‎‏‪-‮]", "", s or "")


def one_line(s, n):
    s = " ".join(strip_bidi(s).split())
    return s if len(s) <= n else s[:n].rstrip() + "…"


# ---------- زمان ----------
G_MONTHS = ["ژانویه", "فوریه", "مارس", "آوریل", "مه", "ژوئن", "ژوئیه", "اوت", "سپتامبر", "اکتبر", "نوامبر", "دسامبر"]
J_MONTHS = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور", "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"]
WEEKDAYS = ["دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه", "شنبه", "یکشنبه"]


def jalali(gy, gm, gd):
    g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    gy2 = gy + 1 if gm > 2 else gy
    days = 355666 + 365 * gy + (gy2 + 3) // 4 - (gy2 + 99) // 100 + (gy2 + 399) // 400 + gd + g_d_m[gm - 1]
    jy = -1595 + 33 * (days // 12053); days %= 12053
    jy += 4 * (days // 1461); days %= 1461
    if days > 365:
        jy += (days - 1) // 365; days = (days - 1) % 365
    if days < 186:
        return jy, 1 + days // 31, 1 + days % 31
    return jy, 7 + (days - 186) // 30, 1 + (days - 186) % 30


def fa_date(d):
    jy, jm, jd = jalali(d.year, d.month, d.day)
    return f"{fa(d.day)} {G_MONTHS[d.month - 1]} {fa(d.year)} ({fa(jd)} {J_MONTHS[jm - 1]} {fa(jy)})"


def now_line():
    v = now()
    return f"{WEEKDAYS[v.weekday()]} {fa_date(v)}، ساعت {fa(v.strftime('%H:%M'))} (ساعت کامپیوتر خودش)"


def stamp():
    return now().strftime("%Y-%m-%d %H:%M")


# ---------- تنظیم‌ها ----------
def load_settings():
    s = {**DEFAULT_SETTINGS, **jread(DIR / "settings.json", {})}
    if s.get("voice") not in VOICE_NAMES:
        s["voice"] = DEFAULT_SETTINGS["voice"]
    return s


def save_settings(body):
    with LOCK:
        s = load_settings()
        if body.get("voice") in VOICE_NAMES:
            s["voice"] = body["voice"]
        if isinstance(body.get("rate"), (int, float)) and 0.75 <= body["rate"] <= 2:
            s["rate"] = round(float(body["rate"]), 2)
        if isinstance(body.get("autoplay"), bool):
            s["autoplay"] = body["autoplay"]
        jwrite(DIR / "settings.json", s)
    return s


# ---------- حافظه ----------
# پیش‌نویس‌ها از حافظه‌ی Claude (جلسه‌های کاری قبلی)، فقط چیزهای مربوط به مارکتینگ که در هسته‌ی برند نیست.
# تا کاربر تأییدشان نکند برچسب «پیش‌نویس» دارند و مشاور هم همین را می‌بیند.
SEED_MEMORY = []   # حافظه خالی شروع می‌شود؛ مشاور در گفت‌وگوها پیشنهاد می‌دهد و کاربر با دکمه ذخیره می‌کند


def load_memory():
    m = jread(DIR / "memory.json", None)
    if m is None:
        m = {"items": [{"id": f"m{k + 1}", "text": t, "src": "حافظه‌ی Claude", "draft": True,
                        "at": now().strftime("%Y-%m-%d")} for k, t in enumerate(SEED_MEMORY)],
             "next": len(SEED_MEMORY) + 1}
        jwrite(DIR / "memory.json", m)
    return m


def memory_op(body):
    act, today = body.get("action"), now().strftime("%Y-%m-%d")
    with LOCK:
        m = load_memory()
        items = m["items"]
        it = next((x for x in items if x["id"] == body.get("id")), None)
        text = " ".join(str(body.get("text") or "").split())[:600]
        if act == "add":
            if not text:
                return 400, {"error": "متن یادداشت خالی است."}
            new = {"id": f"m{m['next']}", "text": text, "src": "خودت" if not body.get("chat") else "گفت‌وگو",
                   "draft": False, "at": today}
            if body.get("chat"):
                new["chat"] = str(body["chat"])[:40]
            m["next"] += 1
            items.append(new)
            it = new
        elif not it:
            return 404, {"error": "این یادداشت پیدا نشد."}
        elif act == "update":
            if not text:
                return 400, {"error": "متن یادداشت خالی است."}
            it.update(text=text, draft=False, at=today)
        elif act == "confirm":
            it.update(draft=False, at=today)
        elif act == "delete":
            items.remove(it)
        else:
            return 400, {"error": "bad action"}
        jwrite(DIR / "memory.json", m)
    return 200, {"ok": True, "items": m["items"], "id": it["id"]}


def memory_md(items):
    if not items:
        return "هنوز یادداشتی نیست."
    out = []
    for x in items:
        tag = " — *پیش‌نویس؛ هنوز تأیید نشده*" if x.get("draft") else ""
        out.append(f"- [{x['at']}] {x['text']}{tag}")
    return "\n".join(out)


# ---------- استوری‌ها ----------
def log_story(text):
    text = "\n".join(l.rstrip() for l in str(text or "").strip().splitlines())[:3000]
    if not text:
        return 400, {"error": "متن خالی است."}
    with LOCK:
        s = jread(DIR / "stories.json", {"made": []})
        s["made"] = [x for x in s["made"] if x.get("text") != text]
        s["made"].insert(0, {"text": text, "at": stamp()})
        del s["made"][200:]
        jwrite(DIR / "stories.json", s)
    return 200, {"ok": True}


def clean_drafts(drafts):
    out = []
    for d in drafts if isinstance(drafts, list) else []:
        t = "\n".join(l.rstrip() for l in str(d or "").strip().splitlines()).strip()
        if t and t not in out:
            out.append(t[:3000])
    return out[:30]


# ---------- پوشه‌ی دانش + پرونده ----------
TYPE_FA = {"REELS": "ریل", "CAROUSEL": "کاروسل", "POST": "پست"}
STATUS_FA = {"idea": "خام", "approved": "تأییدشده", "producing": "در تولید", "done": "منتشرشده"}
SRC_FA = {"youtube": "یوتیوب", "website": "سایت", "url": "لینک", "file": "فایل", "text": "متن", "manual": "دستی",
          "analyst": "تحلیلگر", "advisor": "مشاور"}
STEP_FA = {"transcribe": "رونویسی", "analyze": "تحلیل", "enrich": "جستجوی وب", "produce": "ریلز"}


def _n(x, d=0):
    if x is None:
        return "—"
    return f"{x:,.{d}f}" if isinstance(x, (int, float)) else str(x)


def _instagram(kb):
    ds = jread(DATA / "instagram" / "dataset.json", {})
    raw = jread(DATA / "instagram" / "raw.json", {})
    if not ds.get("posts"):
        return "داده‌ی اینستاگرام هنوز جمع نشده (تب «تحلیل اینستاگرام»)."
    caps = {m.get("id"): m.get("caption") or "" for m in raw.get("media") or []}
    posts = sorted(ds["posts"], key=lambda p: p.get("posted_at") or "", reverse=True)
    reels = [p["views"] for p in posts if p.get("type") == "REELS" and p.get("views")]
    med = statistics.median(reels) if reels else None

    # kb: همه‌ی پست‌ها با کپشن کامل
    lines = [f"# همه‌ی پست‌های @{ds.get('username', '')} — کپشن کامل و آمار", "",
             f"داده: {ds.get('generated_at', '')[:16]} (UTC). «هوک» = خط اول کپشن.", ""]
    for p in posts:
        lines += [f"## {p.get('date')} · {TYPE_FA.get(p.get('type'), p.get('type'))} · {_n(p.get('views'))} بازدید",
                  f"- لینک: {p.get('permalink')}",
                  f"- reach {_n(p.get('reach'))} · لایک {_n(p.get('likes'))} · کامنت {_n(p.get('comments'))} · "
                  f"share {_n(p.get('shares'))} ({_n(p.get('share_rate'), 2)}٪) · save {_n(p.get('saved'))} ({_n(p.get('save_rate'), 2)}٪) · "
                  f"فالو {_n(p.get('follows'))} · زمان تماشا {_n(p.get('avg_watch_s'), 1)} ثانیه · skip {_n(p.get('skip_rate'), 1)}٪",
                  "", strip_bidi(caps.get(p.get("id"), "")).strip() or "(کپشن ندارد)", ""]
    (kb / "instagram-posts.md").write_text("\n".join(lines), encoding="utf-8")

    sm = ds.get("summary") or {}
    l30 = sm.get("last30") or {}
    last = next((p for p in posts if p.get("date")), None)
    days_since = (now().date() - datetime.fromisoformat(last["date"]).date()).days if last else None
    out = [f"- **پیج:** @{ds.get('username', '')} · فالوور: {_n(sm.get('followers'))} · داده تا {ds.get('generated_at', '')[:10]}",
           f"- **آخرین پست:** {last.get('date') if last else '—'} ({_n(days_since)} روز پیش)" if last else "",
           f"- **۳۰ روز اخیر (حساب):** بازدید {_n(l30.get('views'))} · reach {_n(l30.get('reach'))} · تعامل {_n(l30.get('interactions'))} · "
           f"فالو {_n(l30.get('follows'))} · آنفالو {_n(l30.get('unfollows'))} · پست منتشرشده {_n(l30.get('posts'))}",
           f"- **میانه‌ی بازدید ریل‌ها:** {_n(med)} (n={len(reels)}) — برای مقایسه‌ی هر ریل با معمول پیج"
           if med else ""]
    days = ds.get("account_days") or []
    if days:
        out += ["", "**روزبه‌روز حساب (۳۰ روز اخیر):**", "",
                "| روز | بازدید | reach | reach غیرفالوور | تعامل | فالو | آنفالو |", "|---|---|---|---|---|---|---|"]
        out += [f"| {d.get('date')} | {_n(d.get('views'))} | {_n(d.get('reach'))} | {_n(d.get('reach_non_followers'))} | "
                f"{_n(d.get('interactions'))} | {_n(d.get('follows'))} | {_n(d.get('unfollows'))} |" for d in days]
    au = ds.get("audience") or {}
    if au.get("age"):
        tot = sum(au["age"].values()) or 1
        out += ["", f"**مخاطب ({ds.get('audience_at', '')}):** سن: " + "، ".join(
            f"{k}: {v * 100 / tot:.1f}٪" for k, v in sorted(au["age"].items()))]
    if au.get("country"):
        top = sorted(au["country"].items(), key=lambda kv: -kv[1])[:8]
        out.append("کشور (۸ اول): " + "، ".join(f"{k} {_n(v)}" for k, v in top))
    if au.get("gender"):
        g = au["gender"]
        out.append(f"جنسیت: مرد {_n(g.get('M'))}، زن {_n(g.get('F'))}، نامشخص {_n(g.get('U'))} — نامشخص زیاد است، نتیجه نگیر.")
    out += ["", f"**همه‌ی پست‌ها ({fa(len(posts))} پست، جدیدترین اول؛ کپشن کامل در `{kb / 'instagram-posts.md'}`):**", "",
            "| تاریخ | نوع | هوک (خط اول کپشن) | بازدید | reach | share٪ | save٪ | لایک | کامنت | تماشا (ث) | لینک |",
            "|---|---|---|---|---|---|---|---|---|---|---|"]
    for p in posts:
        out.append(f"| {p.get('date')} | {TYPE_FA.get(p.get('type'), p.get('type'))} | {one_line(p.get('hook') or '', 90).replace('|', '/')} | "
                   f"{_n(p.get('views'))} | {_n(p.get('reach'))} | {_n(p.get('share_rate'), 2)} | {_n(p.get('save_rate'), 2)} | "
                   f"{_n(p.get('likes'))} | {_n(p.get('comments'))} | {_n(p.get('avg_watch_s'), 1)} | {p.get('permalink', '')} |")
    return "\n".join(x for x in out if x is not None)


def _report(kb):
    reps = sorted((DATA / "instagram" / "reports").glob("*.md"))
    if not reps:
        return "هنوز گزارشی ساخته نشده."
    d = kb / "instagram-reports"
    d.mkdir(exist_ok=True)
    for r in reps:
        shutil.copyfile(r, d / r.name)
    older = f"\n\n(گزارش‌های قبلی در `{d}`)" if len(reps) > 1 else ""
    return read_text(reps[-1]) + older


def _ideas(kb):
    ideas = jread(DATA / "ideas.json", [])
    if not ideas:
        return "بانک ایده خالی است."
    d = kb / "ideas"
    d.mkdir(exist_ok=True)
    out = []
    for it in ideas:
        iid = str(it.get("id") or "")
        if not re.fullmatch(r"[\w-]{1,40}", iid):
            continue
        idir = IDEAS / iid
        parts = [f"# {it.get('title', '')}", "", f"- شناسه: {iid}", f"- وضعیت: {STATUS_FA.get(it.get('status'), it.get('status'))}",
                 f"- پیلر: {it.get('pillar') or '—'} · امتیاز: {it.get('score') if it.get('score') is not None else '—'}",
                 f"- منبع: {SRC_FA.get((it.get('source') or {}).get('kind'), '—')} · ساخته‌شده: {it.get('created', '')}", ""]
        for f, h in (("brief.md", "خلاصه"), ("raw.md", "متن خام ایده"), ("analysis.md", "تحلیل"),
                     ("research.md", "پژوهش وب"), ("reel.md", "ریل ساخته‌شده")):
            t = read_text(idir / f)
            if t.strip():
                parts += [f"## {h} ({f})", "", t.strip(), ""]
        (d / f"{iid}.md").write_text("\n".join(parts), encoding="utf-8")

        steps = [STEP_FA[k] for k in STEP_FA if (it.get("steps") or {}).get(k)]
        src = it.get("source") or {}
        line = [f"### {one_line(it.get('title', ''), 110)}",
                f"- وضعیت: {STATUS_FA.get(it.get('status'), it.get('status'))} · پیلر: {it.get('pillar') or '—'} · "
                f"امتیاز: {it.get('score') if it.get('score') is not None else '—'} · منبع: {SRC_FA.get(src.get('kind'), '—')}"
                f"{' — ' + one_line(src.get('video', ''), 70) if src.get('video') else ''} · {it.get('created', '')}"
                f"{' · انجام‌شده: ' + '، '.join(steps) if steps else ''}"]
        raw = read_text(idir / "raw.md")
        if raw.strip():
            line.append(f"- متن خام: {one_line(raw, 380)}")
        reel = jread(idir / "reel.json", None)
        if reel:
            hooks = reel.get("hooks") or []
            pick = reel.get("pick") if isinstance(reel.get("pick"), int) and 0 <= reel.get("pick") < len(hooks) else 0
            line.append(f"- ریل ساخته شده: «{one_line(reel.get('title', ''), 100)}» · هوک انتخاب‌شده: «{one_line(hooks[pick], 160) if hooks else '—'}»"
                        f" · CTA: «{one_line(reel.get('cta', ''), 160)}»")
        line.append(f"- همه‌ی جزئیات: `{d / (iid + '.md')}`")
        out.append("\n".join(line))
    return "\n\n".join(out)


def _translations(kb):
    if not OUTPUT.is_dir():
        return "هنوز ویدیویی پردازش نشده."
    d = kb / "translations"
    d.mkdir(exist_ok=True)
    out = []
    for v in sorted(OUTPUT.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if not v.is_dir() or not re.fullmatch(r"[\w-]{1,80}", v.name):
            continue
        tr = jread(v / "translation.json", {})
        info = read_text(v / "video-info.md")
        title = tr.get("title") or (re.search(r"^#\s+(.+)$", info, re.M) or [None, v.name])[1]
        meta = f"{tr.get('channel', '')} · {tr.get('duration', '')} · {tr.get('url', '')}" if tr else one_line(info, 200)
        parts = [f"# {title}", "", meta, ""]
        ideas = jread(v / "reel-ideas.json", {}).get("items") or []
        for f in ("08-ایده‌های-ریلز.md", "03-پیشنهاد-ریلز.md", "04-متن-آماده-ضبط.md", "07-ترجمه-کامل.md", "01-متن-کامل-فارسی.md"):
            t = read_text(v / f)
            if t.strip():
                parts += [f"## {f}", "", t.strip(), ""]
        (d / f"{v.name}.md").write_text("\n".join(parts), encoding="utf-8")
        line = [f"### {one_line(title, 120)}", f"- {one_line(meta, 200)}"]
        if tr.get("chunks"):
            done = sum(1 for c in tr["chunks"] if c.get("state") == "done")
            line.append(f"- ترجمه‌ی کامل فارسی: {fa(done)} از {fa(len(tr['chunks']))} بخش")
        for x in ideas[:10]:
            line.append(f"- ایده‌ی پیشنهادی: «{one_line(x.get('title', ''), 90)}» — هوک: «{one_line(x.get('hook', ''), 140)}» "
                        f"({x.get('pillar', '')}، امتیاز {x.get('score', '—')}){' — در بانک ایده' if x.get('sent') else ''}")
        line.append(f"- متن کامل: `{d / (v.name + '.md')}`")
        out.append("\n".join(line))
    return "\n\n".join(out) or "هنوز ویدیویی پردازش نشده."


def _stories(kb, drafts):
    made = jread(DIR / "stories.json", {"made": []}).get("made") or []
    lines = ["# استوری‌های متنی", ""]
    if made:
        lines += ["## ساخته‌شده (دانلود یا کپی در تب استوری؛ جدیدترین اول)", ""]
        lines += [f"### {x['at']}\n\n{x['text']}\n" for x in made]
    if drafts:
        lines += ["## پیش‌نویس‌های فعلی تب استوری (هنوز ساخته نشده)", ""] + [f"---\n\n{t}\n" for t in drafts]
    (kb / "stories.md").write_text("\n".join(lines), encoding="utf-8")
    if not made and not drafts:
        return "هنوز استوری‌ای ثبت نشده. (تب «استوری» متن هر استوری را که دانلود یا کپی شود ثبت می‌کند.)"
    out = []
    if made:
        out.append(f"**ساخته‌شده ({fa(len(made))}، جدیدترین اول):**")
        out += [f"- [{x['at']}] {one_line(x['text'], 300)}" for x in made[:25]]
    if drafts:
        out.append("**پیش‌نویس‌های فعلی (ساخته نشده):**")
        out += [f"- {one_line(t, 300)}" for t in drafts[:10]]
    out.append(f"متن کامل: `{kb / 'stories.md'}`")
    return "\n".join(out)


PERSONA = """# تو کی هستی

تو «مشاور» @@OWNER@@ هستی: یک استراتژیست ارشد برند شخصی و تولید محتوا که کنار او، داخل استودیوی تولید محتوای خودش کار می‌کند. @@NAME@@ دارد برند شخصی‌اش را می‌سازد و محتوای اینستاگرامش را خودش تولید می‌کند. کارت این است که کمکش کنی محتوای بهتری بسازد، پیجش رشد کند و به هدف‌هایش برسد: ایده‌هایش را بسنجی، پخته‌شان کنی، و بگویی الان چه چیزی بسازد و منتشر کند.

همه‌ی چیزهایی که از او می‌دانی پایین همین پیام است: هسته‌ی برند، آمار پیج (اگر وصلش کرده باشد)، گزارش تحلیلگر، بانک ایده، ترجمه‌های یوتیوب، استوری‌ها و حافظه‌ی گفت‌وگوهای قبلی. اول هر پیام زمان همان پیام آمده؛ امروز و ساعت را از همان بفهم.

# اگر هسته‌ی برند هنوز ناقص است

هسته‌ی برند پایه‌ی همه‌ی کارهای استودیوست. اگر سؤال‌های ضروری‌اش (هویت، مخاطب، پیلرها، لحن، خط قرمزها) هنوز جواب ندارند، این را در اولین جوابت کوتاه بگو و پیشنهاد کن با هم پرش کنید: هر بار یک سؤال بپرس، جوابش را با او پخته کن، و بگو آن را در تب «هسته‌ی برند» زیر کدام سؤال بنویسد. چیزی از خودت جای او پر نکن.

# چطور حرف می‌زنی

- با خود @@NAME@@ حرف می‌زنی، نه با مخاطب‌هایش. «تو» خطابش کن.
- **محاوره‌ای بنویس، همان‌طور که حرف می‌زنی**، مثل دو همکار که رودررو نشسته‌اند: «ببین، این ایده یه مشکل داره»، نه «این ایده مشکلی دارد»؛ «می‌شه»، «نمی‌خوره»، «بذار»، «اینه که». جواب‌هایت با صدا هم خوانده می‌شوند و نوشتار رسمی بلندخوانده مصنوعی است.
- **به نثر حرف بزن، نه با فهرست.** دو سه پاراگراف کوتاه، مثل حرف زدن. فهرست، تیتر و پررنگ فقط وقتی که خودش برنامه یا فهرست خواست. جدول نکش. ایموجی نگذار. لینک خام وسط جمله نیاور؛ اگر لازم بود، آخر جواب در یک خط جدا.
- **کوتاه.** معمولاً ۸۰ تا ۱۸۰ کلمه. یک حرف اصلی را خوب بگو، نه پنج حرف را نیمه‌کاره. اگر حرف بیشتری هست، آخرش بپرس «بخوای جزئیات … رو هم می‌گم».
- **پیام خودمونی یا کوتاه** (سلام، احوال‌پرسی، «خسته‌ام»، «مرسی»): مثل یک آدم جواب بده، در یک تا سه جمله. ابزار نزن، فایل نخوان، برنامه‌ی کاری نچین و آمار نیاور.
- مقدمه و تعارف نکن («سؤال خیلی خوبیه!»، «حتماً!»). مستقیم برو سر اصل حرف. اگر جای یک تصمیم یا قدم بعدی هست، با همان تمام کن.
- عددها را کم و دقیق بیاور: یکی دو عدد که حرفت را ثابت می‌کند، نه همه‌ی آمار.

# چطور مشاوره می‌دهی

- بله‌قربان‌گو نیستی. اگر ایده ضعیف است، صریح بگو و دلیلش را بیاور (اگر آمار پیج هست، با عدد، تاریخ و لینک پست). اگر خوب است، بگو چرا و چطور قوی‌ترش کند. صراحتت از سر دلسوزی است، نه تحقیر.
- وقتی ایده‌ای آورد: اول حکمت را در یک جمله بگو، بعد دلیلش، بعد یکی دو پیشنهاد مشخص (زاویه، هوک، قالب، زمان انتشار). اگر ایده مبهم است، اول یکی دو سؤال دقیق بپرس، نه یک مقاله.
- هر ایده را با این‌ها بسنج: مخاطب و دردهایش، پیلرها و سهمشان، «سهم فروش» و «تاریخ‌های پیش رو» در هسته‌ی برند، درس‌های داده، و گزارش تحلیلگر اگر هست.
- هر عددی که می‌گویی باید از همین پرونده یا یک منبع مشخص باشد. عدد نساز. اگر داده نداری، بگو «داده‌اش را ندارم». اگر حدس می‌زنی، با برچسب «فرضیه» بگو. حرف‌های کلی درباره‌ی «الگوریتم اینستاگرام» فرضیه‌اند، نه قانون.
- وقتی از یک پست مثال می‌زنی، تاریخ و هوکش را بگو تا بشناسدش.
- خط قرمزهای هسته‌ی برند قانون‌اند. پیشنهادی که با آن‌ها نمی‌خواند (مثل وعده‌ی درآمد یا ادعایی که اثبات ندارد) نده؛ اگر خودش خواست، یادش بینداز.
- چیزی که در «سؤال‌های بی‌جواب» هسته‌ی برند آمده را از خودت پر نکن؛ اگر لازم شد از خودش بپرس.
- متن کامل ریل را خودت ننویس؛ آن کار «بانک ایده» و ویرایشگر ریلز استودیوست (آنجا «⚡ ساخت کامل» تحلیل، پژوهش و ریل را می‌سازد). تو ایده، زاویه، چند هوک پیشنهادی و ساختار را بده و پیشنهاد کن بفرستد به بانک ایده. اگر صریحاً متن خواست، کوتاه و با لحن خودش بنویس.
- زمان انتشار را به وقت مخاطب‌هایش فکر کن (از هسته‌ی برند و آمار مخاطب بفهم کجا هستند). ساعتی که اول هر پیام می‌آید ساعت کامپیوتر خود اوست.
- تاریخ را میلادی بنویس و معادل شمسی‌اش را داخل پرانتز بیاور.

# ابزارها

- پوشه‌ی دانش (@@KB@@) کپی کامل داده‌های استودیوست و خلاصه‌اش پایین همین پیام است. بیشتر جواب‌ها با همین خلاصه درمی‌آیند. فقط وقتی جوابت به جزئیاتی نیاز دارد که در خلاصه نیست (کپشن کامل یک پست، متن کامل یک ریل ساخته‌شده، پژوهش یک ایده، ترجمه‌ها)، فایلش را با Read بخوان یا با Grep در آن بگرد. هر خواندن جواب را چند ثانیه کندتر می‌کند. وقتی خواندی، اول بخوان و بعد بنویس؛ قبل از خواندن چیزی ننویس.
- برای چک کردن یک ترند، خبر یا آمار بیرونی از WebSearch و WebFetch استفاده کن و منبع و تاریخش را بگو. برای هر سؤالی سرچ نکن؛ فقط وقتی جواب به اطلاعات تازه‌ی بیرون از این پرونده بستگی دارد.
- هیچ فایلی را عوض نمی‌کنی و نمی‌توانی بکنی. پس هیچ‌وقت نگو «ذخیره کردم» یا «فرستادم».

# پیشنهاد ایده و یادداشت (دکمه‌ها)

وقتی در گفت‌وگو به یک ایده‌ی محتوایی مشخص رسیدید که ارزش ساختن دارد، آخر جوابت این بلوک را بگذار. آن را به‌صورت یک کارت با دکمه‌ی «بفرست به بانک ایده» می‌بیند، نه متن خام:

<<<IDEA
{"title": "تایتل کوتاه ایده", "pillar": "یکی از پیلرهای هسته‌ی برند", "format": "ریل یا کاروسل یا استوری", "hook": "یک هوک پیشنهادی", "angle": "زاویه و حرف اصلی در یک یا دو جمله", "why": "چرا الان و چرا برای این پیج"}
IDEA>>>

وقتی تصمیمی گرفته شد، یا چیزی درباره‌ی @@NAME@@، برندش، برنامه‌اش یا سلیقه‌اش فهمیدی که در گفت‌وگوهای بعدی هم باید یادت باشد، این بلوک را بگذار. با دکمه‌ی «یادت بمونه» نشانش می‌دهیم:

<<<MEMO
{"text": "یک جمله‌ی کوتاه و مستقل که بدون این گفت‌وگو هم فهمیده شود"}
MEMO>>>

- فقط وقتی واقعاً لازم است، نه در هر جواب. حداکثر ۳ ایده و ۲ یادداشت در یک جواب. JSON باید معتبر باشد.
- این بلوک‌ها پیشنهادند و تا خودش دکمه را نزند چیزی ذخیره نمی‌شود. درباره‌ی خود بلوک‌ها در متن چیزی نگو.

# تب‌های استودیو

شروع · داشبورد · هسته‌ی برند (پرسش‌نامه) · مشاور (همین گفت‌وگو) · بانک ایده (ثبت با متن، لینک، ویس یا فایل؛ تحلیل، جستجوی وب، ساخت ریل با شش هوک و ویرایشگر) · ترجمه‌های یوتیوب (ترجمه‌ی کامل برای خواندن، فقط برای خودش) · استودیو ریلز (یوتیوب ← ایده‌ی ریلز و متن ضبط و تله‌پرامپتر) · تدوین ویدیو (برش، زیرنویس فارسی، کاور؛ فقط روی مک) · استوری (متن ← تصویر ۱۰۸۰×۱۹۲۰) · کاروسل و پست · تحلیل اینستاگرام (اگر توکنش را وصل کرده باشد) · تنظیمات. انتشار مستقیم و دایرکت خودکار در این استودیو نیست؛ خروجی‌ها دانلود و دستی منتشر می‌شوند.
"""


def build_kb(drafts=None):
    """پوشه‌ی دانش را از نو می‌سازد و بخش‌های پرونده را برمی‌گرداند."""
    with KB_LOCK:
        tmp = DIR / "kb.tmp"
        shutil.rmtree(tmp, ignore_errors=True)
        tmp.mkdir(parents=True)
        mem = load_memory()["items"]
        drafts = clean_drafts(drafts)
        brand_md = read_text(ROOT / "brand" / "brand-core.md")
        (tmp / "brand-core.md").write_text(brand_md, encoding="utf-8")
        sec = {"brand": brand_md or "(هسته‌ی برند هنوز خالی است.)", "instagram": _instagram(tmp),
               "report": _report(tmp), "ideas": _ideas(tmp),
               "translations": _translations(tmp), "stories": _stories(tmp, drafts),
               "memory": memory_md(mem)}
        (tmp / "memory.md").write_text("# حافظه‌ی مشاور\n\n" + sec["memory"] + "\n", encoding="utf-8")
        files = sorted(str(p.relative_to(tmp)) for p in tmp.rglob("*") if p.is_file())
        (tmp / "README.md").write_text("# پوشه‌ی دانش مشاور\n\nساخته‌شده: " + stamp() + "\n\n"
                                       + "\n".join(f"- {f}" for f in files) + "\n", encoding="utf-8")
        old = DIR / "kb.old"
        shutil.rmtree(old, ignore_errors=True)
        if KB.exists():
            KB.rename(old)
        tmp.rename(KB)
        shutil.rmtree(old, ignore_errors=True)
    # مسیرهای داخل متن به پوشه‌ی نهایی اشاره کنند، نه پوشه‌ی موقت
    return {k: v.replace(str(tmp), str(KB)) for k, v in sec.items()}


def build_system(drafts=None):
    """ترتیب از ثابت به متغیر، و بدون ساعت: تا وقتی داده عوض نشده، گفت‌وگوهای پشت سر هم (در بازه‌ی ۱ ساعته‌ی کش)
    همین متن را بایت‌به‌بایت می‌فرستند و پیام اولشان پرونده را از کش می‌خواند، نه از نو."""
    s = build_kb(drafts)
    persona = (PERSONA.replace("@@KB@@", str(KB)).replace("@@OWNER@@", cfg.owner_line())
               .replace("@@NAME@@", cfg.profile()["name"] or "صاحب استودیو"))
    return "\n".join([
        persona,
        "# پرونده", "",
        "## هسته‌ی برند (منبع حقیقت؛ کامل)", "", s["brand"], "",
        "## آخرین گزارش تحلیلگر اینستاگرام", "", s["report"], "",
        "## ترجمه‌ها و ویدیوهای یوتیوب", "", s["translations"], "",
        "## عملکرد اینستاگرام", "", s["instagram"], "",
        "## بانک ایده (جدیدترین اول)", "", s["ideas"], "",
        "## استوری‌ها", "", s["stories"], "",
        "# حافظه‌ی مشاور (تصمیم‌ها و دانسته‌ها از گفت‌وگوهای قبلی)", "", s["memory"], "",
        f"# پوشه‌ی دانش\n\nفهرست فایل‌ها: `{KB / 'README.md'}`",
    ])


# ---------- گفت‌وگو ----------
def safe_id(cid):
    return isinstance(cid, str) and re.fullmatch(r"c\d{8}-\d{6}(-\d+)?", cid) is not None and (CHATS / cid / "chat.json").exists()


def load_chat(cid):
    return jread(CHATS / cid / "chat.json", None)


def save_chat(chat):
    chat["updated"] = stamp()
    jwrite(CHATS / chat["id"] / "chat.json", chat)


def new_chat(drafts=None):
    base = "c" + now().strftime("%Y%m%d-%H%M%S")
    cid, k = base, 1
    while (CHATS / cid).exists():
        k += 1
        cid = f"{base}-{k}"
    (CHATS / cid).mkdir(parents=True)
    system = build_system(drafts)
    (CHATS / cid / "system.md").write_text(system, encoding="utf-8")
    chat = {"id": cid, "title": "گفت‌وگوی تازه", "autoTitle": True, "created": stamp(), "updated": stamp(),
            "session": str(uuid.uuid4()), "started": False, "messages": [], "next": 1,
            "dossier": {"built": stamp(), "chars": len(system)}}
    with LOCK:
        save_chat(chat)
    return chat


def list_chats():
    out = []
    for f in CHATS.glob("*/chat.json"):
        c = jread(f, None)
        if not c:
            continue
        last = next((m for m in reversed(c.get("messages") or []) if m.get("text")), None)
        out.append({"id": c["id"], "title": c.get("title", ""), "updated": c.get("updated", ""),
                    "n": len(c.get("messages") or []), "preview": one_line((last or {}).get("text", ""), 90),
                    "running": c["id"] in JOBS and JOBS[c["id"]].get("state") == "running"})
    return sorted(out, key=lambda c: c["updated"], reverse=True)


def auto_title(text):
    t = " ".join(text.split())
    if len(t) <= 48:
        return t
    cut = t[:48].rsplit(" ", 1)[0]
    return (cut or t[:48]) + "…"


BLOCK_RE = re.compile(r"<<<(IDEA|MEMO)\s*(.*?)\s*\1>>>", re.S)


def parse_blocks(text):
    ideas, memos = [], []
    for kind, body in BLOCK_RE.findall(text or ""):
        try:
            obj = json.loads(body)
        except Exception:
            continue
        if not isinstance(obj, dict):
            continue
        if kind == "IDEA" and str(obj.get("title") or "").strip():
            ideas.append({k: str(obj.get(k) or "").strip()[:600] for k in ("title", "pillar", "format", "hook", "angle", "why")})
        elif kind == "MEMO" and str(obj.get("text") or "").strip():
            memos.append({"text": " ".join(str(obj["text"]).split())[:600]})
    clean = BLOCK_RE.sub("", text or "")
    clean = re.sub(r"<<<(IDEA|MEMO)[\s\S]*$", "", clean)       # بلوک ناتمام
    return clean.strip(), ideas[:3], memos[:2]


def main_text(segs):
    """متن اصلی جواب: همه‌ی تکه‌های متن، به‌جز جمله‌های کوتاهِ «الان می‌خونم» درست پیش از یک ابزار."""
    out = []
    for k, s in enumerate(segs):
        if s["t"] != "text" or not s["text"].strip():
            continue
        nxt = segs[k + 1] if k + 1 < len(segs) else None
        if nxt and nxt["t"] == "tool" and len(s["text"].strip()) < 200:
            continue
        out.append(s["text"].strip())
    return "\n\n".join(out)


def tool_label(name, inp):
    inp = inp if isinstance(inp, dict) else {}
    if name == "Read":
        return "خواند: " + Path(str(inp.get("file_path", ""))).name
    if name == "Grep":
        return "گشت در فایل‌ها: " + one_line(str(inp.get("pattern", "")), 50)
    if name == "Glob":
        return "فهرست فایل‌ها: " + one_line(str(inp.get("pattern", "")), 50)
    if name == "WebSearch":
        return "جستجو در وب: " + one_line(str(inp.get("query", "")), 70)
    if name == "WebFetch":
        u = str(inp.get("url", ""))
        return "خواندن صفحه: " + (re.sub(r"^https?://(www\.)?", "", u).split("/")[0] or u)
    return name


def save_usage(info):
    w = (info or {}).get("unifiedWindows") or {}
    u = {k: {"used": round(float(v.get("utilization") or 0), 3), "resets": v.get("resetsAt")} for k, v in w.items()}
    if u:
        jwrite(DIR / "usage.json", {"windows": u, "at": stamp(), "status": info.get("status")})


def start_turn(cid, text, deep=False, retry=False):
    text = (text or "").strip()
    with JLOCK:
        if cid in JOBS and JOBS[cid].get("state") == "running":
            return 409, {"error": "مشاور هنوز دارد جواب پیام قبلی را می‌نویسد."}
        if sum(1 for j in JOBS.values() if j.get("state") == "running") >= 3:
            return 429, {"error": "سه گفت‌وگو هم‌زمان در حال اجراست؛ کمی صبر کن."}
        with LOCK:
            chat = load_chat(cid)
            if retry:
                last = next((m for m in reversed(chat["messages"]) if m["role"] == "user"), None)
                if not last:
                    return 400, {"error": "پیامی برای تکرار نیست."}
                text = last["text"]
                if chat["messages"] and chat["messages"][-1]["role"] == "assistant" and \
                        (chat["messages"][-1].get("error") or chat["messages"][-1].get("stopped")):
                    chat["messages"].pop()
            elif not text:
                return 400, {"error": "پیام خالی است."}
            else:
                chat["messages"].append({"id": f"m{chat['next']}", "role": "user", "text": text[:20000], "at": stamp()})
                chat["next"] += 1
                if chat.get("autoTitle") and sum(1 for m in chat["messages"] if m["role"] == "user") == 1:
                    chat["title"] = auto_title(text)
            mid = f"m{chat['next']}"
            chat["next"] += 1
            chat["pending"] = {"id": mid, "deep": bool(deep), "at": stamp()}
            save_chat(chat)
        effort = EFFORT["deep" if deep else "normal"]
        prompt = f"(زمان این پیام: {now_line()})\n\n" + text
        if retry:
            prompt = f"(زمان این پیام: {now_line()})\n\n(جواب پیام قبلی‌ام کامل نشد؛ دوباره می‌فرستم:)\n\n" + text
        JOBS[cid] = {"state": "running", "msg": mid, "segs": [], "activity": "thinking", "note": "", "started": time.time(),
                     "effort": effort, "proc": None}
    threading.Thread(target=_run_turn, args=(cid, mid, prompt, effort), daemon=True).start()
    return 200, {"ok": True, "msg": mid}


def _cmd(chat, effort, resume):
    # فقط-خواندن، و فقط در پوشه‌ی دانش: --restricted ابزارهای فایل را به work و kb محدود می‌کند، و Read/Grep/Glob
    # عمداً در --allowedTools نیستند — اجازه‌ی صریح آن‌ها خواندن هر مسیری را باز می‌کند (حتی .env استودیو؛ تست ۲۰۲۶-۱۰-۰۵).
    # --safe-mode جلوی CLAUDE.md، حافظه، پلاگین‌ها و MCPها را می‌گیرد؛ --permission-prompts none هر چیزی را که اجازه بخواهد رد می‌کند.
    cmd = [claude_bin(), "-p", "--model", am.get("advisor"), "--effort", effort, "--safe-mode", "--restricted",
           "--system-prompt-file", str(CHATS / chat["id"] / "system.md"),
           "--tools", ",".join(TOOLS), "--allowedTools", "WebSearch", "WebFetch", "--add-dir", str(KB),
           "--permission-prompts", "none",
           "--output-format", "stream-json", "--include-partial-messages", "--verbose"]
    return cmd + (["--resume", chat["session"]] if resume else ["--session-id", chat["session"]])


def _recap(chat, upto_mid):
    lines = ["(این ادامه‌ی گفت‌وگوی قبلی ماست، ولی سابقه‌اش از دست رفته. خلاصه‌ی پیام‌های قبلی:)", ""]
    for m in chat["messages"]:
        if m["id"] == upto_mid:
            break
        if m.get("text"):
            who = (cfg.profile()["name"] or "من") if m["role"] == "user" else "تو"
            lines.append(f"{who}: {one_line(m['text'], 1200)}")
    return "\n".join(lines[:80])


def session_file(chat):
    """فایل سشن Claude Code همین گفت‌وگو؛ cwd ثابت work یعنی یک پوشه‌ی ثابت در ~/.claude/projects."""
    return Path.home() / ".claude" / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(WORK)) / f"{chat['session']}.jsonl"


# ---------- اینترنت ----------
# ۲۰۲۶-۱۰-۰۵ در کافه: پیام وقتی رفت که وای‌فای هنوز وصل نشده بود (ENOTFOUND api.anthropic.com). Claude Code با تأخیر
# نمایی (۰٫۵، ۱، ۲، ۴، ۸، ۱۹، ۳۶ ثانیه) دوباره تلاش کرد و جواب ۷۸ ثانیه بعد رسید، در حالی که خود جواب ۱۷ ثانیه بود.
# پس پیش از هر نوبت خودمان اتصال را چک می‌کنیم و هر ثانیه منتظر می‌مانیم؛ اگر وسط کار قطع شد و برگشت، منتظر
# نوبت بعدیِ تأخیر Claude Code نمی‌مانیم.
NET = {"ok_at": 0.0}
NET_WAIT = 180
NET_CODES = {"ENOTFOUND", "EAI_AGAIN", "ENETUNREACH", "EHOSTUNREACH", "ECONNREFUSED", "ECONNRESET", "ETIMEDOUT", "ENETDOWN"}
CONTINUE_NET = "(اینترنت چند لحظه قطع بود و جوابت به من نرسید؛ لطفاً به پیام قبلی‌ام جواب بده.)"


def net_ok(fresh=False):
    if not fresh and time.time() - NET["ok_at"] < 20:
        return True
    try:
        with socket.create_connection(("api.anthropic.com", 443), timeout=2.5):
            NET["ok_at"] = time.time()
            return True
    except OSError:
        NET["ok_at"] = 0.0
        return False


def _wait_net(job):
    """True وقتی اینترنت هست؛ اگر نیست هر ثانیه چک می‌کند تا NET_WAIT. False یعنی وصل نشد یا کاربر توقف زد."""
    if net_ok():
        return True
    job.update(activity="offline", note="اینترنت وصل نیست؛ تا وصل شود صبر می‌کنم و همان لحظه می‌فرستم…")
    t = time.time()
    while job["state"] == "running" and time.time() - t < NET_WAIT:
        time.sleep(1)
        if net_ok(fresh=True):
            job.update(activity="thinking", note="")
            return True
    return False


def _on_api_error(job, e, p):
    er = e.get("error") or {}
    code = (er.get("connection") or {}).get("code") or ""
    down = bool(er.get("isNetworkDown")) or code in NET_CODES
    blob = json.dumps(er).lower()
    wait = (e.get("retryInMs") or 0) / 1000
    if down:
        what = "اینترنت قطع است"
        NET["ok_at"] = 0.0
    elif er.get("rateLimits") or ("rate" in blob and "limit" in blob):
        what = "به سقف استفاده‌ی اشتراک Claude خوردی"
    elif "overload" in blob or "529" in blob:
        what = "سرور Claude شلوغ است"
    else:
        what = "خطای موقت سرور Claude"
    n, total = e.get("retryAttempt"), e.get("maxRetries")
    job.update(activity="retry", retry_at=time.time() + wait,
               note=f"{what}؛ دوباره تلاش می‌کنم{f' ({fa(n)} از {fa(total)})' if n and total else ''}…")
    if down and wait > 3 and not job.get("watch"):
        job["watch"] = True
        threading.Thread(target=_net_watch, args=(job, p), daemon=True).start()


def _net_watch(job, p):
    """اینترنت برگشته ولی Claude Code هنوز در تأخیر نمایی منتظر است: می‌بندیمش تا همین الان دوباره بفرستیم."""
    try:
        while p.poll() is None and job["state"] == "running" and job.get("activity") == "retry":
            if net_ok(fresh=True) and time.time() < job.get("retry_at", 0) - 2:
                job["net_rerun"] = True
                p.kill()
                return
            time.sleep(1)
    finally:
        job["watch"] = False


def _attempt(cid, chat, prompt, effort, resume, job):
    """یک بار اجرای claude؛ رویدادها را در job می‌ریزد. خروجی: (result، err)."""
    segs, cur, result = job["segs"], None, None
    errf = CHATS / cid / "last.err"
    job["net_rerun"] = False
    with open(errf, "w", encoding="utf-8") as ef:
        p = subprocess.Popen(_cmd(chat, effort, resume), cwd=str(WORK), stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE, stderr=ef, text=True, encoding="utf-8", bufsize=1)
        job["proc"] = p

        def _timeout():
            job["timeout"] = True
            p.kill()
        killer = threading.Timer(TURN_TIMEOUT, _timeout)
        killer.start()
        try:
            p.stdin.write(prompt)
            p.stdin.close()
            for line in p.stdout:
                try:
                    e = json.loads(line)
                except Exception:
                    continue
                t = e.get("type")
                if t == "stream_event":
                    ev = e.get("event") or {}
                    et = ev.get("type")
                    if et == "message_start" and job["activity"] in ("retry", "offline"):
                        job.update(activity="thinking", note="")        # تلاش دوباره جواب داد
                    elif et == "content_block_start":
                        cb = ev.get("content_block") or {}
                        if cb.get("type") == "text":
                            cur = {"t": "text", "text": ""}
                            segs.append(cur)
                            job["activity"] = "writing"
                        elif cb.get("type") == "tool_use":
                            cur = {"t": "tool", "name": cb.get("name", ""), "json": "", "label": tool_label(cb.get("name", ""), {}),
                                   "done": False}
                            segs.append(cur)
                            job["activity"] = "tool"
                        elif cb.get("type") == "thinking":
                            cur = None
                            job["activity"] = "thinking"
                    elif et == "content_block_delta":
                        d = ev.get("delta") or {}
                        if d.get("type") == "text_delta" and cur and cur["t"] == "text":
                            cur["text"] += d.get("text", "")
                        elif d.get("type") == "input_json_delta" and cur and cur["t"] == "tool":
                            cur["json"] += d.get("partial_json", "")
                    elif et == "content_block_stop" and cur and cur["t"] == "tool":
                        try:
                            cur["label"] = tool_label(cur["name"], json.loads(cur["json"] or "{}"))
                        except Exception:
                            pass
                elif t == "system" and e.get("subtype") == "api_error":
                    _on_api_error(job, e, p)
                elif t == "user":
                    for s in segs:
                        if s["t"] == "tool":
                            s["done"] = True
                    job["activity"] = "thinking"
                elif t == "rate_limit_event":
                    save_usage(e.get("rate_limit_info"))
                elif t == "result":
                    result = e
            p.wait(timeout=60)
        finally:
            killer.cancel()
    return result, read_text(errf)[-600:]


def _run_turn(cid, mid, prompt, effort):
    job = JOBS[cid]
    segs, result, err = job["segs"], None, ""
    first_prompt, recapped = prompt, False
    try:
        WORK.mkdir(parents=True, exist_ok=True)
        if not KB.exists():
            build_kb()
        for _ in range(4):
            if not _wait_net(job):
                if job["state"] == "running":
                    err = f"اینترنت تا {fa(NET_WAIT // 60)} دقیقه وصل نشد. وقتی وصل شد «دوباره بفرست» را بزن."
                break
            chat = load_chat(cid)
            # نوبتی که وسط کار قطع شده هم فایل سشن دارد و --session-id تکراری خطا می‌دهد، پس از روی فایل تصمیم می‌گیریم
            resume = bool(chat.get("started")) or session_file(chat).exists()
            result, err = _attempt(cid, chat, prompt, effort, resume, job)
            if job["state"] != "running":
                break
            if job.get("net_rerun"):                         # اینترنت برگشت: همین الان، نه ۳۶ ثانیه بعد
                segs.clear()
                job.update(activity="thinking", note="")
                prompt = (f"(زمان این پیام: {now_line()})\n\n" + CONTINUE_NET
                          if session_file(load_chat(cid)).exists() else first_prompt)
                continue
            if not recapped and resume and not segs and result is None and "No conversation found" in err:
                recapped = True                               # سشن گم شده: سشن تازه با خلاصه‌ی گفت‌وگو
                with LOCK:
                    chat = load_chat(cid)
                    chat["session"], chat["started"] = str(uuid.uuid4()), False
                    save_chat(chat)
                prompt = _recap(chat, mid) + "\n\n" + first_prompt
                continue
            break
    except Exception as ex:
        err = f"{type(ex).__name__}: {ex}"

    stopped = job.get("state") == "stopped"
    full = main_text(segs)
    text, ideas, memos = parse_blocks(full)
    ok = result is not None and result.get("subtype") == "success" and not result.get("is_error")
    if ok:
        NET["ok_at"] = time.time()
    msg = {"id": mid, "role": "assistant", "at": stamp(), "effort": effort, "model": am.get("advisor"),
           "ms": int((time.time() - job["started"]) * 1000), "text": text, "ideas": ideas, "memos": memos,
           "tools": [s["label"] for s in segs if s["t"] == "tool"]}
    if result:
        msg["cost"] = result.get("total_cost_usd")
        u = result.get("usage") or {}
        msg["tokens"] = {k: u.get(k) for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens")}
        msg["api_ms"] = result.get("duration_api_ms")
    if stopped:
        msg["stopped"] = True
    elif job.get("timeout"):
        msg["error"] = f"زمان جواب تمام شد ({fa(TURN_TIMEOUT // 60)} دقیقه)."
    elif not ok or not text:
        why = (result or {}).get("result") if result and result.get("is_error") else ""
        msg["error"] = one_line(why or err or "جوابی برنگشت.", 400)
    with LOCK:
        chat = load_chat(cid)
        if chat is None:            # گفت‌وگو وسط کار پاک شده
            JOBS.pop(cid, None)
            return
        if result is not None or segs or session_file(chat).exists():
            chat["started"] = True
        chat["messages"].append(msg)
        chat.pop("pending", None)
        save_chat(chat)
    with JLOCK:
        job.update(state="done", proc=None, done_at=time.time())


def stop_turn(cid):
    job = JOBS.get(cid)
    if not job or job.get("state") != "running":
        return 200, {"ok": True}
    job["state"] = "stopped"
    p = job.get("proc")
    if p and p.poll() is None:
        p.kill()
    return 200, {"ok": True}


def poll(cid):
    job = JOBS.get(cid)
    if not job:
        chat = load_chat(cid) or {}
        return {"state": "lost" if chat.get("pending") else "idle"}
    segs = [{k: v for k, v in s.items() if k != "json"} for s in job["segs"]]
    # «stopped» یعنی دکمه‌ی توقف زده شده ولی پیام هنوز ذخیره نشده؛ صفحه تا «done» صبر می‌کند
    return {"state": "done" if job["state"] == "done" else "running", "msg": job["msg"], "segs": segs,
            "activity": job["activity"], "note": job.get("note", ""), "elapsed": round(time.time() - job["started"], 1),
            "effort": job["effort"]}


def status():
    running = [cid for cid, j in JOBS.items() if j.get("state") == "running"]
    return {"state": "running" if running else "idle", "running": running}


def kill_orphans():
    """اگر سرور وسط یک جواب بسته شده باشد، claude آن جواب بی‌صاحب (PPID 1) ادامه می‌دهد و خروجی‌اش گم می‌شود.
    موقع شروع سرور پیدایشان می‌کنیم و می‌بندیم؛ صفحه برای آن پیام «دوباره بفرست» نشان می‌دهد. (فقط مک)"""
    if cfg.IS_WIN:
        return
    try:
        out = subprocess.run(["ps", "-axo", "pid=,ppid=,command="], capture_output=True, text=True, timeout=10).stdout
    except Exception:
        return
    mark = str(CHATS) + "/"
    for line in out.splitlines():
        bits = line.split(None, 2)
        if len(bits) == 3 and bits[1] == "1" and "--system-prompt-file" in bits[2] and mark in bits[2]:
            try:
                subprocess.run(["kill", bits[0]], timeout=5)
            except Exception:
                pass


kill_orphans()


def delete_chat(cid):
    stop_turn(cid)
    JOBS.pop(cid, None)
    shutil.rmtree(CHATS / cid, ignore_errors=True)
    return 200, {"ok": True}


# ---------- ایده ← بانک ایده ----------
def send_idea(body):
    cid, mid = body.get("chat"), body.get("msg")
    if not safe_id(cid):
        return 404, {"error": "این گفت‌وگو پیدا نشد."}
    with LOCK:
        chat = load_chat(cid)
        msgs = chat["messages"]
        k = next((n for n, m in enumerate(msgs) if m["id"] == mid and m["role"] == "assistant"), None)
        if k is None:
            return 404, {"error": "این پیام پیدا نشد."}
        m = msgs[k]
        q = next((x for x in reversed(msgs[:k]) if x["role"] == "user"), None)
        idx = body.get("index")
        idea = m["ideas"][idx] if isinstance(idx, int) and 0 <= idx < len(m.get("ideas") or []) else None
        if idea and idea.get("sent"):
            with cfg.IDEAS_LOCK:
                have = {i.get("id") for i in jread(DATA / "ideas.json", [])}
            if idea["sent"] in have:
                return 409, {"error": "این ایده قبلاً به بانک ایده رفته.", "id": idea["sent"]}
        if not idea and m.get("sentAll"):
            with cfg.IDEAS_LOCK:
                have = {i.get("id") for i in jread(DATA / "ideas.json", [])}
            if m["sentAll"] in have:
                return 409, {"error": "این گفت‌وگو قبلاً به بانک ایده رفته.", "id": m["sentAll"]}

        iid = f"i{int(time.time() * 1000)}"
        d = IDEAS / iid
        d.mkdir(parents=True, exist_ok=True)
        link = f"/?s=advisor&chat={cid}"
        try:
            when = datetime.strptime(m.get("at", ""), "%Y-%m-%d %H:%M")
            when = f"{fa_date(when)}، ساعت {fa(when.strftime('%H:%M'))}"
        except ValueError:
            when = m.get("at", "")
        lines = ["# ایده از گفت‌وگو با مشاور", "", f"- **گفت‌وگو:** [باز کن]({link}) — «{chat.get('title', '')}»",
                 f"- **تاریخ:** {when}", ""]
        if idea:
            title = idea["title"]
            for key, h in (("format", "قالب"), ("hook", "هوک پیشنهادی"), ("angle", "زاویه و حرف اصلی"), ("why", "چرا الان")):
                if idea.get(key):
                    lines += [f"## {h}", "", idea[key], ""]
        else:
            title = auto_title((q or {}).get("text") or m["text"])
        if q:
            lines += ["## حرف من به مشاور", "", q["text"], ""]
        lines += ["## جواب مشاور", "", m["text"], ""]
        (d / "raw.md").write_text("\n".join(lines), encoding="utf-8")
        pillar = (idea or {}).get("pillar", "")
        rec = {"id": iid, "title": title, "pillar": pillar if pillar in bc.pillar_names() else "", "status": "idea",
               "score": None, "source": {"kind": "advisor", "ref": cid, "msg": mid}, "note": "از گفت‌وگو با مشاور",
               "created": now().strftime("%Y-%m-%d"), "steps": {}}
        with cfg.IDEAS_LOCK:
            f = DATA / "ideas.json"
            f.write_text(json.dumps([rec] + jread(f, []), ensure_ascii=False, indent=2), encoding="utf-8")
        if idea:
            idea["sent"] = iid
        else:
            m["sentAll"] = iid
        save_chat(chat)
    return 200, {"ok": True, "id": iid}


def save_memo(body):
    cid, mid, idx = body.get("chat"), body.get("msg"), body.get("index")
    if not safe_id(cid):
        return 404, {"error": "این گفت‌وگو پیدا نشد."}
    with LOCK:
        chat = load_chat(cid)
        m = next((x for x in chat["messages"] if x["id"] == mid and x["role"] == "assistant"), None)
        if not m or not isinstance(idx, int) or not 0 <= idx < len(m.get("memos") or []):
            return 404, {"error": "این یادداشت پیدا نشد."}
        memo = m["memos"][idx]
        if memo.get("saved"):
            return 200, {"ok": True, "id": memo["saved"]}
    code, r = memory_op({"action": "add", "text": body.get("text") or memo["text"], "chat": cid})
    if code != 200:
        return code, r
    with LOCK:
        chat = load_chat(cid)
        m = next(x for x in chat["messages"] if x["id"] == mid)
        m["memos"][idx]["saved"] = r["id"]
        save_chat(chat)
    return 200, {"ok": True, "id": r["id"], "items": r["items"]}


# ---------- صدا (Gemini TTS) ----------
def gemini_key():
    return cfg.gemini_key()


EMOJI_RE = re.compile("[\U0001F000-\U0001FAFF☀-➿️‍⬀-⯿]")


def speakable(text):
    t = BLOCK_RE.sub("", text or "")
    t = re.sub(r"```[\s\S]*?```", " ", t)
    t = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", t)
    t = re.sub(r"https?://\S+|www\.\S+", " ", t)
    t = re.sub(r"\b[\w.-]+\.(com|ir|org|net|io|me|ai)(/\S*)?", " ", t)
    t = re.sub(r"`([^`]*)`", r"\1", t)
    t = re.sub(r"\*\*|__|\*", "", t)
    out = []
    for line in t.splitlines():
        l = line.strip()
        if re.match(r"^\|?\s*:?-{3,}", l):
            continue
        if l.startswith("|"):
            l = "، ".join(c.strip() for c in l.strip("|").split("|") if c.strip())
        l = re.sub(r"^#{1,6}\s*", "", l)
        l = re.sub(r"^[-+•]\s+", "", l)
        l = re.sub(r"^>\s*", "", l)
        out.append(l)
    t = "\n".join(out)
    t = EMOJI_RE.sub("", t)
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def tts_parts(text):
    """متن خواندنی را به تکه‌هایی می‌شکند که پشت سر هم ساخته و پخش شوند؛ تکه‌ی اول کوتاه است تا صدا زود شروع شود."""
    t = speakable(text)
    if not t:
        return []
    sents = []
    for para in re.split(r"\n\s*\n", t):
        para = " ".join(para.split())
        if not para:
            continue
        bits = [b for b in re.split(r"(?<=[.!؟?…:؛])\s+", para) if b.strip()]
        for b in bits:
            while len(b) > 480:                      # جمله‌ی خیلی بلند: سر ویرگول بشکن
                cut = max(b.rfind("، ", 0, 480), b.rfind(", ", 0, 480), b.rfind(" ", 0, 480))
                cut = cut if cut > 100 else 480
                sents.append((b[:cut + 1].strip(), False))
                b = b[cut + 1:].strip()
            sents.append((b, False))
        if sents:
            sents[-1] = (sents[-1][0], True)          # پایان پاراگراف
    parts, cur = [], ""
    for s, end_para in sents:
        # تکه‌ی اول کوتاه تا صدا زود شروع شود؛ بعدی‌ها بزرگ، چون سقف ۱۰ درخواست در دقیقه است و هر تکه
        # تا وقتی تکه‌ی قبلی پخش می‌شود ساخته می‌شود (ساختن ≈ ۰٫۴ برابر طول صدا)
        limit = 170 if not parts else (360 if len(parts) == 1 else 900)
        if cur and len(cur) + len(s) + 1 > limit:
            parts.append(cur.strip())
            cur = ""
        cur += (" " if cur else "") + s
        if end_para:
            cur += "\n"
    if cur.strip():
        parts.append(cur.strip())
    return parts


def _wav(pcm, rate=24000):
    return (b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVEfmt " + struct.pack("<IHHIIHH", 16, 1, 1, rate, rate * 2, 2, 16)
            + b"data" + struct.pack("<I", len(pcm)) + pcm)


def compress(wav):
    """WAV → Opus/Ogg (حدود یک‌دهم حجم)؛ اگر ffmpeg نبود یا نشد، همان WAV. خروجی: (bytes، پسوند، نوع)."""
    ff = shutil.which("ffmpeg")
    if ff:
        try:
            r = subprocess.run([ff, "-hide_banner", "-loglevel", "error", "-i", "pipe:0", "-c:a", "libopus", "-b:a", "40k",
                                "-ac", "1", "-f", "ogg", "pipe:1"], input=wav, capture_output=True, timeout=60)
            if r.returncode == 0 and len(r.stdout) > 1000:
                return r.stdout, ".ogg", "audio/ogg"
        except Exception:
            pass
    return wav, ".wav", "audio/wav"


def cached_audio(stem, make):
    """صدای ذخیره‌شده با هر پسوندی؛ اگر نبود می‌سازد. خروجی: (bytes، نوع)."""
    for ext, ctype in ((".ogg", "audio/ogg"), (".wav", "audio/wav")):
        f = stem.with_name(stem.name + ext)
        if f.exists():
            return f.read_bytes(), ctype
    data, ext, ctype = compress(make())
    stem.parent.mkdir(parents=True, exist_ok=True)
    f = stem.with_name(stem.name + ext)
    tmp = f.with_name(f.name + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(f)
    return data, ctype


class TTSLimited(Exception):
    def __init__(self, wait):
        super().__init__(f"429, retry in {wait}s")
        self.wait = wait


def _tts_call(model, key, body):
    req = urllib.request.Request(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                                 data=json.dumps(body).encode(), headers={"Content-Type": "application/json", "x-goog-api-key": key})
    try:
        d = json.load(urllib.request.urlopen(req, timeout=120))
    except urllib.error.HTTPError as e:
        if e.code == 429:
            wait = 30
            try:
                for det in json.loads(e.read()).get("error", {}).get("details", []):
                    if det.get("retryDelay"):
                        wait = int(float(str(det["retryDelay"]).rstrip("s")))
            except Exception:
                pass
            raise TTSLimited(wait)
        raise RuntimeError(f"HTTP {e.code}")
    part = d["candidates"][0]["content"]["parts"][0]["inlineData"]
    pcm = base64.b64decode(part["data"])
    m = re.search(r"rate=(\d+)", part.get("mimeType", ""))
    return _wav(pcm, int(m.group(1)) if m else 24000)


def gemini_tts(text, voice):
    """مدل اصلی؛ اگر سقف دقیقه‌ای‌اش پر بود مدل دوم؛ اگر آن هم پر بود یک بار به‌اندازه‌ی retryDelay صبر (حداکثر ۴۵ ثانیه)."""
    key = gemini_key()
    if not key:
        raise RuntimeError("کلید Gemini تنظیم نشده؛ از تب «تنظیمات» واردش کن تا جواب‌ها با صدا هم خوانده شوند.")
    body = {"contents": [{"parts": [{"text": text}]}],
            "generationConfig": {"responseModalities": ["AUDIO"],
                                 "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}}}}
    last, waited = "", False
    for attempt in range(4):
        limited, wait = False, 2 * (attempt + 1)
        for model in (TTS_MODEL, TTS_FALLBACK):
            try:
                return _tts_call(model, key, body)
            except TTSLimited as e:
                limited, wait = True, e.wait
                last = "سقف ۱۰ درخواست در دقیقه‌ی Gemini پر است"
            except Exception as e:
                limited, last = False, str(e) or type(e).__name__
                break                         # خطای دیگر: کمی بعد دوباره از مدل اصلی
        if limited:
            if waited:
                break
            waited = True
            time.sleep(min(max(wait, 3), 45))
        else:
            time.sleep(wait)
    raise RuntimeError(f"ساخت صدا نشد ({last}).")


def msg_text(cid, mid):
    chat = load_chat(cid) if safe_id(cid) else None
    m = next((x for x in (chat or {}).get("messages", []) if x["id"] == mid and x["role"] == "assistant"), None)
    return (m or {}).get("text")


def tts_plan(cid, mid):
    text = msg_text(cid, mid)
    if not text:
        return 404, {"error": "این پیام پیدا نشد."}
    parts = tts_parts(text)
    return 200, {"parts": len(parts), "voice": load_settings()["voice"], "chars": sum(len(p) for p in parts)}


def tts_audio(cid, mid, k, voice):
    text = msg_text(cid, mid)
    if not text or not re.fullmatch(r"m\d+", mid or ""):
        return 404, {"error": "این پیام پیدا نشد."}, None
    parts = tts_parts(text)
    if not 0 <= k < len(parts):
        return 404, {"error": "این تکه نیست."}, None
    voice = voice if voice in VOICE_NAMES else load_settings()["voice"]
    stem = CHATS / cid / "audio" / f"{mid}-{voice}-{k}"
    with TTS_LOCKS[str(stem)]:
        try:
            data, ctype = cached_audio(stem, lambda: gemini_tts(parts[k], voice))
        except Exception as e:
            return 502, {"error": str(e)}, None
    return 200, data, ctype


def voice_sample(voice):
    if voice not in VOICE_NAMES:
        return 404, {"error": "این صدا نیست."}, None
    stem = VOICES_DIR / voice
    with TTS_LOCKS[str(stem)]:
        try:
            data, ctype = cached_audio(stem, lambda: gemini_tts(SAMPLE_TEXT, voice))
        except Exception as e:
            return 502, {"error": str(e)}, None
    return 200, data, ctype


# ---------- رونویسی صدای کاربر ----------
def transcribe(body):
    ext = (Path(str(body.get("filename") or "")).suffix.lower() or ".webm")
    if ext not in (".webm", ".ogg", ".m4a", ".mp4", ".wav", ".mp3"):
        return 400, {"error": "قالب صدا پشتیبانی نمی‌شود."}
    try:
        blob = base64.b64decode(str(body.get("data") or "").split(",")[-1])
    except Exception:
        return 400, {"error": "فایل صدا خوانده نشد."}
    if len(blob) < 800:
        return 400, {"error": "صدا خیلی کوتاه بود."}
    tmp = Path(tempfile.gettempdir()) / f"advisor-rec-{int(time.time() * 1000)}{ext}"
    tmp.write_bytes(blob)
    try:
        text = voice.transcribe(tmp, listen_hint())
    except RuntimeError as e:
        return 502, {"error": one_line(str(e), 300)}
    finally:
        tmp.unlink(missing_ok=True)
    if not text:
        return 502, {"error": "متنی برنگشت — شاید صدا ساکت بود."}
    return 200, {"text": text}


# ---------- مسیرها ----------
def _chat_payload(cid):
    chat = load_chat(cid)
    return {**{k: v for k, v in chat.items() if k not in ("session",)}, "job": poll(cid)}


def handle_get(p, q):
    """(code, payload, ctype) — ctype=None یعنی payload جیسون است."""
    if p in STATIC:
        name, ctype = STATIC[p]
        return 200, (APP / name).read_bytes(), ctype
    if not p.startswith("/api/advisor"):
        return None
    g = lambda k, d="": (q.get(k) or [d])[0]
    if p == "/api/advisor/chats":
        return 200, {"chats": list_chats(), "usage": jread(DIR / "usage.json", {}), "settings": load_settings(),
                     "voices": [{"id": v, "label": l} for v, l in VOICES], "model": am.get("advisor"), "effort": EFFORT}, None
    if p == "/api/advisor/status":
        return 200, status(), None
    if p == "/api/advisor/memory":
        return 200, {"items": load_memory()["items"]}, None
    cid = g("id") or g("chat")
    if p == "/api/advisor/voice-sample":
        return voice_sample(g("voice"))
    if not safe_id(cid):
        return 404, {"error": "این گفت‌وگو پیدا نشد."}, None
    if p == "/api/advisor/chat":
        return 200, _chat_payload(cid), None
    if p == "/api/advisor/poll":
        return 200, {**poll(cid), "usage": jread(DIR / "usage.json", {})}, None
    if p == "/api/advisor/tts-plan":
        code, r = tts_plan(cid, g("msg"))
        return code, r, None
    if p == "/api/advisor/audio":
        try:
            k = int(g("part", "0"))
        except ValueError:
            k = -1
        return tts_audio(cid, g("msg"), k, g("voice"))
    return 404, {"error": "not found"}, None


def handle_post(p, body):
    if not p.startswith("/api/advisor"):
        return None
    if p == "/api/advisor/new":
        try:
            chat = new_chat(body.get("drafts"))
        except Exception as e:
            return 500, {"error": f"ساخت پرونده نشد: {e}"}
        return 200, {"ok": True, "id": chat["id"], "chars": chat["dossier"]["chars"]}
    if p == "/api/advisor/memory":
        return memory_op(body)
    if p == "/api/advisor/settings":
        return 200, {"ok": True, "settings": save_settings(body)}
    if p == "/api/advisor/story":
        return log_story(body.get("text"))
    if p == "/api/advisor/transcribe":
        return transcribe(body)
    if p == "/api/advisor/idea":
        return send_idea(body)
    if p == "/api/advisor/memo":
        return save_memo(body)
    cid = body.get("id")
    if not safe_id(cid):
        return 404, {"error": "این گفت‌وگو پیدا نشد."}
    if p == "/api/advisor/send":
        return start_turn(cid, body.get("text"), bool(body.get("deep")))
    if p == "/api/advisor/retry":
        return start_turn(cid, "", bool(body.get("deep")), retry=True)
    if p == "/api/advisor/stop":
        return stop_turn(cid)
    if p == "/api/advisor/rename":
        title = one_line(str(body.get("title") or ""), 80)
        if not title:
            return 400, {"error": "اسم خالی است."}
        with LOCK:
            chat = load_chat(cid)
            chat.update(title=title, autoTitle=False)
            save_chat(chat)
        return 200, {"ok": True}
    if p == "/api/advisor/delete":
        return delete_chat(cid)
    return 404, {"error": "not found"}
