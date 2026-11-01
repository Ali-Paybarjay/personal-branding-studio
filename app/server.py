#!/usr/bin/env python3
"""Content Studio — سرور لوکال"""
import http.server, socketserver, json, re, os, sys, webbrowser, threading, subprocess, shutil, base64, time, zipfile
from pathlib import Path
from urllib.parse import urlparse, parse_qs, unquote

# ویندوز: بدون حالت UTF-8 پایتون، متن فارسیِ claude و فایل‌ها با کدگذاری ویندوز خوانده می‌شود و خراب می‌شود.
if os.name == "nt" and not sys.flags.utf8_mode:
    sys.exit(subprocess.call([sys.executable, "-X", "utf8", *sys.argv]))

sys.path.insert(0, str(Path(__file__).resolve().parent))
import settings as cfg
cfg.prepare_env()
import voice
import instagram as ig
import brand as bc
import reel_editor as rd
import ai_models as am
import translate as tr
import story as st
import advisor as adv
import carousel as cr
import video as vd

APP    = Path(__file__).resolve().parent
ROOT   = APP.parent
REELS  = ROOT / "modules" / "reels"
OUTPUT = REELS / "output"
DATA   = ROOT / "data"
BRAND  = ROOT / "brand"
IDEAS  = DATA / "ideas"

REEL_FILES = {
    "full":    "01-متن-کامل-فارسی.md",
    "reels":   "03-پیشنهاد-ریلز.md",
    "scripts": "04-متن-آماده-ضبط.md",
    "reading": "05-نسخه-خواندنی.md",
    "study":   "06-تمرین-انگلیسی.md",
    "raw":     "00-transcript-raw.txt",
}

# ---------- کار ساخت ----------
JOB = {"state": "idle", "step": "", "log": [], "url": "", "slug": "", "error": ""}
LOCK = threading.Lock()

BUILD_PROMPT = (
    "این لینک یوتیوب را کامل پردازش کن: {url}\n\n"
    "طبق modules/reels/PIPELINE.md عمل کن و brand/brand-core.md را هم اول بخوان.\n"
    "ترنسکریپت گرفته شده و در modules/reels/output/{slug}/ است.\n"
    "کل 00-transcript-raw.txt را بخوان و این فایل‌ها را در همان پوشه بساز:\n"
    "01-متن-کامل-فارسی.md · 03-پیشنهاد-ریلز.md · 04-متن-آماده-ضبط.md · 05-نسخه-خواندنی.md\n\n"
    "هیچ سؤالی نپرس. وقتی تمام شد فقط بنویس: تمام."
)


def setj(**kw):
    with LOCK:
        JOB.update(kw)


def log(line):
    with LOCK:
        JOB["log"].append(line)
        del JOB["log"][:-40]


def run_build(url):
    try:
        setj(state="running", step="استخراج ترنسکریپت", log=[], error="", slug="", url=url)
        log("▸ در حال گرفتن زیرنویس از یوتیوب…")
        p = subprocess.run([sys.executable, str(REELS / "scripts" / "get_transcript.py"), url],
                           cwd=str(REELS), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)
        for ln in (p.stderr or "").splitlines():
            if ln.strip():
                log(ln.strip())
        if p.returncode != 0:
            return setj(state="error", error="استخراج ترنسکریپت شکست خورد. لینک را چک کن.")

        out = (p.stdout or "").strip().splitlines()
        slug = Path(out[-1]).name if out else ""
        if not slug or not (OUTPUT / slug).is_dir():
            return setj(state="error", error="پوشه‌ی خروجی ساخته نشد.")
        setj(slug=slug, step="نوشتن متن‌های فارسی")
        log(f"▸ ترنسکریپت آماده شد → {slug}")
        log("▸ حالا Claude دارد فایل‌ها را می‌نویسد. چند دقیقه طول می‌کشد…")

        c = subprocess.run([cfg.claude_bin(), "-p", BUILD_PROMPT.format(url=url, slug=slug),
                            "--model", am.get("produce"),
                            "--permission-mode", "acceptEdits", "--output-format", "text"],
                           cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=5400)
        if c.returncode != 0:
            log((c.stderr or "")[-400:])
            return setj(state="error", slug=slug,
                        error="نوشتن ناتمام ماند. ترنسکریپت هست — در Claude Code ادامه بده.")
        made = sum((OUTPUT / slug / f).exists()
                   for k, f in REEL_FILES.items() if k in ("full", "reels", "scripts", "reading"))
        log(f"▸ {made} فایل از ۴ فایل ساخته شد")
        setj(state="done", step="تمام شد", slug=slug)
    except subprocess.TimeoutExpired:
        setj(state="error", error="زمان اجرا تمام شد.")
    except Exception as e:
        setj(state="error", error=f"خطای غیرمنتظره: {e}")



def _drop_section(text, start_re, stop_res):
    """یک بخش را از متن حذف می‌کند: از خط شروع تا خط بعدیِ هم‌سطح."""
    lines = text.split("\n")
    a = next((i for i, l in enumerate(lines) if re.match(start_re, l)), None)
    if a is None:
        return None
    b = len(lines)
    for i in range(a + 1, len(lines)):
        if any(re.match(r, lines[i]) for r in stop_res):
            b = i
            break
    while a > 0 and lines[a - 1].strip() in ("", "---"):
        a -= 1
    return "\n".join(lines[:a] + lines[b:]).replace("\n\n\n\n", "\n\n")


def delete_reel(slug, num):
    """ریلز شماره‌ی num را از فایل ۰۳ و ۰۴ حذف می‌کند."""
    d = OUTPUT / slug
    fa = "۰۱۲۳۴۵۶۷۸۹"
    n_fa = "".join(fa[int(c)] for c in str(num))
    hit = 0

    f3 = d / REEL_FILES["reels"]
    if f3.exists():
        t = f3.read_text(encoding="utf-8")
        pat = rf"^##\s+.*?(?:ریلز\s*)?(?:{re.escape(n_fa)}|{num})\s*—"
        out = _drop_section(t, pat, [r"^##\s", r"^#\s"])
        if out and out != t:
            f3.write_text(out, encoding="utf-8"); hit += 1

    f4 = d / REEL_FILES["scripts"]
    if f4.exists():
        t = f4.read_text(encoding="utf-8")
        pat = rf"^#\s*🎬\s*ریلز\s*(?:{re.escape(n_fa)}|{num})\s*—"
        out = _drop_section(t, pat, [r"^#\s*🎬"])
        if out and out != t:
            f4.write_text(out, encoding="utf-8"); hit += 1
    return hit



# ================= بانک ایده =================
IJOB = {"state": "idle", "id": "", "step": "", "log": [], "error": ""}
ILOCK = threading.Lock()

STEP_LABEL = {"transcribe": "رونویسی صدا", "analyze": "تحلیل ایده",
              "enrich": "جستجوی وب", "produce": "ساخت ریلز", "full": "ساخت کامل"}
AUDIO_EXT = (".m4a", ".mp3", ".wav", ".mp4", ".mov", ".aac", ".ogg", ".opus", ".webm", ".flac")

STEP_PROMPT = {
"analyze": """اول brand/brand-core.md را بخوان.
بعد data/ideas/{id}/raw.md را بخوان — این ورودی خام کاربر است.

فایل data/ideas/{id}/analysis.md را بساز با این بخش‌ها:

## ادعای مرکزی
یک جمله. دقیقاً حرف اصلی چیست؟

## زاویه‌ی دید
چرا این حرف تازه یا برخلاف انتظار است؟ اگر نیست، صادقانه بگو.

## پیلر پیشنهادی
یکی از پیلرهای brand-core، با دلیل.

## برای چه کسی
کدام بخش مخاطب، و چه دردی از او را می‌زند.

## چه چیزی کم دارد
مهم‌ترین بخش. برای اینکه این ایده به ریلز قابل انتشار تبدیل شود چه چیزی لازم است؟ عدد؟ منبع؟ مثال؟ داستان؟ فهرست کن.

## سه عنوان پیشنهادی
سه تایتل فارسی هوک‌دار، بدون کلیک‌بیت دروغ.

## امتیاز
از ۱۰، با یک جمله دلیل.

هیچ سؤالی نپرس. وقتی فایل ساخته شد بنویس: تمام.""",

"enrich": """تو یک پژوهشگر هستی، نه نویسنده. کارت پیدا کردن **حقیقت قابل ردیابی** است.

اول این‌ها را بخوان:
- `brand/brand-core.md` (مخاطب و ادعاهای ممنوع)
- `data/ideas/{id}/raw.md` (ایده‌ی خام)
- `data/ideas/{id}/analysis.md` اگر هست (مخصوصاً بخش «چه چیزی کم دارد»)
- `data/ideas/{id}/brief.md` اگر هست — **این دستورالعمل کاربر است و بر همه‌چیز اولویت دارد**

## روش کار

**گام ۱ — طراحی جستجو.** ۴ تا ۸ کوئری بنویس. هم فارسی هم انگلیسی. از عبارت‌های دقیق و بازه‌ی زمانی استفاده کن.

**ابزارها:** با WebSearch بگرد و هر صفحه را با WebFetch بخوان.

**گام ۲ — سه لایه بگرد. هر سه لایه اجباری است:**

*لایه‌ی الف — منبع دست‌اول (برای واقعیت):*
اعلامیه‌ی رسمی شرکت، مقاله‌ی علمی، گزارش رسمی، مستندات، داده‌ی نهاد آماری.

*لایه‌ی ب — گزارش معتبر (برای زمینه):*
رسانه‌های شناخته‌شده با خبرنگار نام‌دار. اگر خبری فقط یک منبع دارد، همین را بنویس.

*لایه‌ی ج — صدای جامعه (برای زاویه و لحن، نه برای واقعیت):*
- **یوتیوب** — قابل اتکا. چه کسانی ویدیو ساخته‌اند و چه زاویه‌ای گرفته‌اند
- **Hacker News** — قابل اتکا. تجربه‌ی واقعی مهندس‌ها در بحث‌ها
- **Reddit** — اگر WebFetch نتوانست بخواند، وقت نگذار؛ در بخش Reddit بنویس «دسترسی نبود». هرگز از حافظه یا از جمع‌بندی دسته‌دوم نقل‌قول کاربر نساز.
- **X** — پست‌های مرتبط را با WebSearch پیدا کن. اگر متن پستی را نتوانستی بخوانی، لینک را بیاور و **صریح بنویس که متن تأیید نشده و کاربر باید خودش باز کند**.

**قانون طلایی:** هیچ **واقعیت یا عددی** فقط با استناد به لایه‌ی ج نوشته نمی‌شود. لایه‌ی ج فقط برای «مردم چه می‌گویند» است و باید صریح به همین شکل برچسب بخورد.

**گام ۳ — تعارض‌ها را پیدا کن.** اگر دو منبع معتبر حرف متضاد می‌زنند، هر دو را بیاور. تعارض خودش محتوای خوبی است.

**گام ۴ — بنویس.**

فایل `data/ideas/{id}/research.md` را دقیقاً با این ساختار بساز:

```
# پژوهش — <موضوع>
تاریخ پژوهش: <امروز>

## خلاصه‌ی اجرایی
سه تا پنج جمله. اگر فقط همین را بخوانم چه باید بدانم؟

## یافته‌های کلیدی
برای هر یافته:
### <عنوان یافته>
- **چه چیزی:** …
- **تاریخ:** …
- **منبع:** [نام منبع](لینک کامل) — لایه‌ی الف/ب
- **چقدر مطمئن:** بالا / متوسط / پایین — با دلیل

## اعداد قابل استفاده
| عدد | معنی | تاریخ | منبع |
|---|---|---|---|
عددی که لینک ندارد اصلاً نوشته نمی‌شود.

## صدای جامعه
### یوتیوب
- <عنوان ویدیو> — <کانال> — <زاویه‌ای که گرفته> — [لینک](…)
### Reddit
- r/<ساب> — <حرف اصلی کاربران> — [لینک](…)
### X
- <@حساب> — <حرفش> — [لینک](…)
> این بخش نظر مردم است، نه واقعیت تأییدشده.

## نظر مخالف
جدی‌ترین نقدی که پیدا کردی، با لینک. اگر نبود بنویس «نقد جدی پیدا نشد».

## تعارض‌ها
جایی که منابع با هم نمی‌خوانند.

## چه چیزی پیدا نشد
با توجه به «چه چیزی کم دارد» در analysis.md — چه چیزی را گشتی و نبود.

## زاویه‌های پیشنهادی برای ریلز
دو تا چهار زاویه که **این پژوهش** ممکن کرد، نه حرف کلی.

## همه‌ی منابع
۱. [عنوان](لینک) — تاریخ — لایه
```

## قواعد سخت

- هر ادعا لینک دارد. **لینک کامل و قابل کلیک**، نه اسم سایت.
- هیچ چیز از حافظه ننویس. اگر جستجو نتیجه نداد، در «چه چیزی پیدا نشد» بنویس.
- تاریخ هر منبع را بیاور. خبر بی‌تاریخ بی‌ارزش است.
- اگر منبعی پولی یا بسته بود، همین را بنویس.
- کوئری‌هایی که زدی را آخر فایل در یک بخش `## کوئری‌های استفاده‌شده` فهرست کن تا کاربر بتواند خودش تکرار کند.
- اگر به هر دلیل دسترسی وب نداشتی، فایل را **نساز** و صریح گزارش بده.

هیچ سؤالی نپرس. آخرش بنویس: تمام.""",

# ساخت ریلز بخش‌بخش است و پرامپتش در reel_editor.py (PRODUCE_PROMPT)
"produce": rd.PRODUCE_PROMPT,
}


def isetj(**kw):
    with ILOCK:
        IJOB.update(kw)


def ilog(line):
    with ILOCK:
        IJOB["log"].append(line)
        del IJOB["log"][:-30]


def extract_text(path: Path) -> str:
    """متن را از فایل بیرون می‌کشد."""
    ext = path.suffix.lower()
    try:
        if ext in (".txt", ".md", ".csv", ".json"):
            return path.read_text(encoding="utf-8", errors="replace")
        if ext == ".pdf" and shutil.which("pdftotext"):
            r = subprocess.run(["pdftotext", "-layout", str(path), "-"],
                               capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
            return r.stdout
        if ext == ".docx":
            return docx_text(path)
        if ext in (".doc", ".rtf", ".html") and shutil.which("textutil"):
            r = subprocess.run(["textutil", "-convert", "txt", "-stdout", str(path)],
                               capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
            return r.stdout
        if ext in (".m4a", ".mp3", ".wav", ".mp4", ".mov", ".aac", ".ogg"):
            return "__AUDIO__"
    except Exception as e:
        return f"(خطا در خواندن فایل: {e})"
    return ""


def docx_text(path: Path) -> str:
    """متن یک فایل Word (.docx) بدون هیچ برنامه‌ی جانبی؛ هر پاراگراف یک خط."""
    with zipfile.ZipFile(path) as z:
        xml = z.read("word/document.xml").decode("utf-8", "replace")
    paras = re.findall(r"<w:p[ >].*?</w:p>", xml, flags=re.S)
    lines = ["".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", p)) for p in paras]
    import html as _html
    return "\n".join(_html.unescape(l) for l in lines).strip()


def run_transcribe(idea_id):
    """صدا را با Gemini (کلید خود کاربر) رونویسی می‌کند."""
    d = IDEAS / idea_id
    audio = next((f for f in sorted(d.iterdir()) if f.suffix.lower() in AUDIO_EXT), None)
    if not audio:
        return False, "فایل صوتی در این ایده پیدا نشد."
    ilog(f"▸ {audio.name} — در حال فشرده‌سازی و ارسال…")
    try:
        text = voice.transcribe(audio).strip()
    except RuntimeError as e:
        return False, str(e)[:300]
    if not text:
        return False, "متنی برنگشت — شاید کلیپ ساکت بوده."
    (d / "raw.md").write_text(text, encoding="utf-8")
    ilog(f"▸ {len(text.split())} کلمه رونویسی شد")

    ideas = jread("ideas.json", [])
    for it in ideas:
        if it.get("id") == idea_id:
            it.setdefault("steps", {})["transcribe"] = True
            it["note"] = ""
            first = text.strip().split("\n")[0][:70]
            if it.get("title", "").lower().endswith(AUDIO_EXT) and first:
                it["title"] = first
    (DATA / "ideas.json").write_text(json.dumps(ideas, ensure_ascii=False, indent=2), encoding="utf-8")
    return True, ""


def fa(n):
    return str(n).translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))


def _full_plan(idea_id):
    """«ساخت کامل»: مرحله‌های انجام‌نشده به ترتیب، و همیشه ساخت ریلز در آخر."""
    it = next((i for i in jread("ideas.json", []) if i.get("id") == idea_id), {})
    done = it.get("steps") or {}
    plan = ["transcribe"] if it.get("audio") and not done.get("transcribe") else []
    plan += [s for s in ("analyze", "enrich") if not done.get(s)]
    return plan + ["produce"]


def _run_one(idea_id, step):
    """یک مرحله را اجرا می‌کند؛ (ok, پیام خطا)."""
    if step == "transcribe":
        return run_transcribe(idea_id)
    if step == "produce":
        return rd.produce(idea_id, ilog, model=am.get("produce"))
    out = {"analyze": "analysis.md", "enrich": "research.md"}[step]
    f = IDEAS / idea_id / out
    before = f.stat().st_mtime if f.exists() else 0
    cmd = [cfg.claude_bin(), "-p", STEP_PROMPT[step].format(id=idea_id), "--model", am.get(step),
           "--permission-mode", "acceptEdits", "--output-format", "text",
           # ابزارهای وب باید صریح مجاز شوند — acceptEdits فقط ویرایش فایل را باز می‌کند
           "--allowedTools", "WebSearch", "WebFetch"]
    ilog(f"▸ مدل: {am.CHOICES.get(am.get(step), am.get(step))}")
    r = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=3600)
    if r.returncode != 0:
        ilog((r.stderr or r.stdout or "")[-300:])
        return False, "اجرا ناتمام ماند. اگر پیام بالا درباره‌ی سهمیه یا ورود است، Claude Code را چک کن."
    if not f.exists() or f.stat().st_mtime <= before:
        return False, f"فایل {out} ساخته نشد."
    ilog(f"▸ {out} ساخته شد")
    return True, ""


def run_idea_step(idea_id, step):
    try:
        plan = _full_plan(idea_id) if step == "full" else [step]
        isetj(state="running", id=idea_id, step=STEP_LABEL.get(step, step), log=[], error="")
        if len(plan) > 1:
            ilog("▸ مرحله‌ها: " + " ← ".join(STEP_LABEL[x] for x in plan))
        for n, st in enumerate(plan, 1):
            label = STEP_LABEL.get(st, st)
            if len(plan) > 1:
                isetj(step=f"{label} — مرحله‌ی {fa(n)} از {fa(len(plan))}")
            ilog(f"▸ {label}…")
            ok, err = _run_one(idea_id, st)
            if not ok:
                return isetj(state="error", error=(f"«{label}»: " if len(plan) > 1 else "") + err)
            _mark_step(idea_id, st)
        isetj(state="done", step="تمام شد")
    except subprocess.TimeoutExpired:
        isetj(state="error", error="زمان اجرا تمام شد.")
    except Exception as e:
        isetj(state="error", error=f"خطا: {e}")


def _mark_step(idea_id, step):
    with cfg.IDEAS_LOCK:
        ideas = jread("ideas.json", [])
        for it in ideas:
            if it.get("id") == idea_id:
                it.setdefault("steps", {})[step] = True
                if step == "produce":
                    it["status"] = "producing"
        (DATA / "ideas.json").write_text(json.dumps(ideas, ensure_ascii=False, indent=2), encoding="utf-8")


def list_videos():
    if not OUTPUT.is_dir():
        return []
    out = []
    for d in sorted(OUTPUT.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if not d.is_dir():
            continue
        m = {"slug": d.name, "title": d.name, "channel": "", "duration": "", "url": ""}
        info = d / "video-info.md"
        if info.exists():
            t = info.read_text(encoding="utf-8")
            if x := re.search(r"^#\s+(.+)$", t, re.M):
                m["title"] = x.group(1).strip()
            for key, lab in (("channel", "کانال"), ("duration", "مدت"), ("url", "لینک")):
                if x := re.search(rf"\*\*{lab}:\*\*\s*(.+)$", t, re.M):
                    m[key] = x.group(1).strip()
        m["has"] = {k: (d / v).exists() for k, v in REEL_FILES.items()}
        out.append(m)
    return out


def jread(f, default):
    try:
        return json.loads((DATA / f).read_text(encoding="utf-8"))
    except Exception:
        return default


# The idea bank's unsent capture box (text / link / pillar). Kept here rather
# than in the browser so every browser that opens the studio sees the same one.
DRAFT_LOCK = threading.Lock()
DRAFT_KEYS = ("text", "url", "pillar")


def save_draft(patch):
    """Merges only the fields the page sent, so a stale second tab editing the
    link can't wipe text typed in another browser."""
    if not isinstance(patch, dict):
        return None
    clean = {k: patch[k] for k in DRAFT_KEYS if isinstance(patch.get(k), str)}
    if any(len(v) > 200_000 for v in clean.values()):
        return None
    with DRAFT_LOCK:
        d = {**jread("idea-draft.json", {}), **clean}
        DATA.mkdir(exist_ok=True)
        tmp = DATA / "idea-draft.json.tmp"
        tmp.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(DATA / "idea-draft.json")
    return d


IDEA_STATUSES = ("idea", "approved", "producing", "done")
# made from raw.md; raw edited after them means they describe the old text
IDEA_DOWNSTREAM = (("analysis.md", "تحلیل"), ("research.md", "جستجوی وب"), ("reel.json", "ریلز"))


def edit_idea(body):
    """One idea's own fields (title / pillar / status / raw text), merged into
    the record on disk. Never a whole-list save, so a stale tab — or the phone
    — can't undo what the other one just changed."""
    iid = str(body.get("id") or "")
    if not iid or "/" in iid or ".." in iid:
        return 400, {"error": "شناسه‌ی نامعتبر"}
    raw = body.get("raw")
    if isinstance(raw, str):
        raw = raw.strip()
        if not raw:
            return 400, {"error": "متن ایده خالی است."}
        with ILOCK:
            if IJOB.get("state") == "running" and IJOB.get("id") == iid:
                return 409, {"error": "یک مرحله روی همین ایده در حال اجراست؛ بگذار تمام شود، بعد متن را عوض کن."}
    with cfg.IDEAS_LOCK:
        ideas = jread("ideas.json", [])
        it = next((i for i in ideas if i.get("id") == iid), None)
        if not it:
            return 404, {"error": "این ایده پیدا نشد."}
        if isinstance(body.get("title"), str) and body["title"].strip():
            it["title"] = body["title"].strip()[:200]
        if isinstance(body.get("pillar"), str):
            it["pillar"] = body["pillar"].strip()
        if body.get("status") in IDEA_STATUSES:
            it["status"] = body["status"]
        if isinstance(raw, str):
            f = IDEAS / iid / "raw.md"
            # rewrite only on a real change: raw.md's mtime is what marks analysis/reel as stale
            if not f.exists() or f.read_text(encoding="utf-8").strip() != raw:
                f.parent.mkdir(parents=True, exist_ok=True)
                f.write_text(raw, encoding="utf-8")
        (DATA / "ideas.json").write_text(json.dumps(ideas, ensure_ascii=False, indent=2), encoding="utf-8")
    return 200, {"ok": True, "idea": it}


def idea_stale(d):
    """Labels of the outputs that were built before raw.md was last edited."""
    raw = d / "raw.md"
    if not raw.exists():
        return []
    t = raw.stat().st_mtime
    return [label for f, label in IDEA_DOWNSTREAM if (d / f).exists() and (d / f).stat().st_mtime < t]


class H(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass

    def _send(self, body, ctype="application/json; charset=utf-8", code=200, cache="no-store"):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(json.dumps(obj, ensure_ascii=False), code=code)

    def do_GET(self):
        u = urlparse(self.path); p, q = unquote(u.path), parse_qs(u.query)
        if p.startswith("/video-media/"):   # تدوین ویدیو: فایل‌های پروژه با Range (پخش با جلو/عقب رفتن)
            return vd.serve_media(self, p)

        if p == "/api/state":
            with LOCK: job = dict(JOB)
            return self._json({
                "job": job,
                "videos": list_videos(),
                "ideas": jread("ideas.json", []),
                "sources": jread("sources.json", []),
                "modules": [m for m in MODULES if m.get("ready")],
                "pillars": bc.pillar_names(),
                "profile": cfg.profile(),
                "platform": "mac" if cfg.IS_MAC else "windows" if cfg.IS_WIN else "linux",
            })
        if p == "/api/idea/status":
            with ILOCK: return self._json(dict(IJOB))
        if p == "/api/idea/draft":
            with DRAFT_LOCK: return self._json(jread("idea-draft.json", {}))
        if p == "/api/idea/files":
            iid = q.get("id", [""])[0]
            if "/" in iid or ".." in iid: return self._json({"error":"bad"}, 400)
            d = IDEAS / iid
            got = {}
            for k, f in (("raw","raw.md"),("brief","brief.md"),("analysis","analysis.md"),
                         ("research","research.md"),("reel","reel.md")):
                got[k] = (d / f).read_text(encoding="utf-8") if (d / f).exists() else None
            got["stale"] = idea_stale(d)
            return self._json(got)

        if p == "/api/brand":
            return self._json(bc.payload())
        if p.startswith("/brand-assets/"):
            a = bc.read_asset(unquote(p[len("/brand-assets/"):]))
            # asset names carry a timestamp, so a cached copy can never be stale
            return self._send(a[0], a[1], cache="max-age=31536000, immutable") if a else self._json({"error": "not found"}, 404)
        if p == "/api/file":
            slug, name = q.get("video", [""])[0], q.get("name", [""])[0]
            if name not in REEL_FILES or "/" in slug or ".." in slug:
                return self._json({"error": "bad request"}, 400)
            f = OUTPUT / slug / REEL_FILES[name]
            if not f.exists():
                return self._json({"error": "not found"}, 404)
            return self._json({"text": f.read_text(encoding="utf-8")})

        r = rd.handle_get(p, q) or am.handle_get(p, q) or cfg.handle_get(p, q)
        if r is not None:
            return self._json(r[1], r[0])

        r = tr.handle_get(p, q)
        if r is not None:      # (code, json) یا برای تصویر (code, bytes, ctype)
            return self._send(r[1], r[2], r[0], cache="max-age=86400") if len(r) > 2 else self._json(r[1], r[0])

        r = st.handle_get(p, q)
        if r is not None:
            code, payload, ctype = r
            return self._send(payload, ctype, code) if ctype else self._json(payload, code)

        r = adv.handle_get(p, q)
        if r is not None:
            code, payload, ctype = r
            return self._send(payload, ctype, code, cache="max-age=86400" if ctype.startswith("audio/") else "no-store") if ctype else self._json(payload, code)

        r = cr.handle_get(p, q)
        if r is not None:      # تصویرهای کتابخانه اسم یکتا دارند و هرگز بازنویسی نمی‌شوند
            code, payload, ctype = r
            return self._send(payload, ctype, code, cache="max-age=31536000, immutable" if ctype.startswith("image/") else "no-store") if ctype else self._json(payload, code)

        r = vd.handle_get(p, q)
        if r is not None:
            code, payload, ctype = r
            return self._send(payload, ctype, code) if ctype else self._json(payload, code)

        r = ig.handle_get(p, q)
        if r is not None:
            code, payload, ctype = r
            return self._send(payload, ctype, code) if ctype else self._json(payload, code)

        static = {"/": "index.html", "/index.html": "index.html",
                  "/style.css": "style.css", "/app.js": "app.js", "/instagram.js": "instagram.js",
                  "/brand.js": "brand.js", "/reel-editor.js": "reel-editor.js", "/translate.js": "translate.js",
                  "/onboarding.js": "onboarding.js", "/onboarding.css": "onboarding.css",
                  "/fonts/Vazirmatn-Variable.woff2": "fonts/Vazirmatn-Variable.woff2"}
        if p in static:
            f = APP / static[p]
            if f.suffix in (".otf", ".woff2"):
                return self._send(f.read_bytes(), "font/" + f.suffix[1:])
            ct = {"html": "text/html", "css": "text/css"}.get(f.suffix[1:], "text/javascript")
            return self._send(f.read_bytes(), f"{ct}; charset=utf-8")
        self._json({"error": "not found"}, 404)

    def do_POST(self):
        p = urlparse(self.path).path
        if p == "/api/video/upload":   # تدوین ویدیو: بدنه خودِ فایل است (جریانی)، نه JSON
            return vd.handle_upload(self)
        n = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            body = {}

        if p == "/api/build":
            url = (body.get("url") or "").strip()
            if not re.match(r"^https?://(www\.)?(youtube\.com|youtu\.be)/", url):
                return self._json({"error": "لینک یوتیوب معتبر نیست."}, 400)
            with LOCK:
                if JOB["state"] == "running":
                    return self._json({"error": "یک ساخت در حال اجراست."}, 409)
            threading.Thread(target=run_build, args=(url,), daemon=True).start()
            return self._json({"ok": True})

        if p == "/api/idea/capture":
            kind = body.get("kind", "text")
            title = (body.get("title") or "").strip()
            iid = "i" + str(int(time.time() * 1000))
            d = IDEAS / iid; d.mkdir(parents=True, exist_ok=True)
            raw, note, audio_name = "", "", ""

            if kind == "file":
                name = re.sub(r"[^\w.\-]", "_", body.get("filename") or "file")
                try:
                    blob = base64.b64decode((body.get("data") or "").split(",")[-1])
                except Exception:
                    return self._json({"error": "فایل خوانده نشد."}, 400)
                fp = d / name; fp.write_bytes(blob)
                raw = extract_text(fp)
                if raw == "__AUDIO__":
                    raw = "(هنوز رونویسی نشده)"
                    note = "فایل صوتی ثبت شد — دکمه‌ی «رونویسی صدا» را بزن."
                    audio_name = name
                elif not raw.strip():
                    note = "متنی از این فایل بیرون نیامد."
                title = title or name
            elif kind == "url":
                u = (body.get("url") or "").strip()
                if not re.match(r"^https?://", u):
                    return self._json({"error": "آدرس معتبر نیست."}, 400)
                raw = f"# لینک\n\n{u}\n\n(محتوای این آدرس در مرحله‌ی تحلیل خوانده می‌شود.)"
                title = title or u
            else:
                raw = (body.get("text") or "").strip()
                if not raw: return self._json({"error": "متن خالی است."}, 400)
                title = title or (raw.split("\n")[0][:70])

            (d / "raw.md").write_text(raw or "(خالی)", encoding="utf-8")
            with cfg.IDEAS_LOCK:
                ideas = jread("ideas.json", [])
                ideas.insert(0, {"id": iid, "title": title, "pillar": body.get("pillar") or "",
                                 "status": "idea", "score": None,
                                 "source": {"kind": kind}, "note": note,
                                 **({"audio": audio_name} if audio_name else {}),
                                 "created": time.strftime("%Y-%m-%d"), "steps": {}})
                DATA.mkdir(exist_ok=True)
                (DATA / "ideas.json").write_text(json.dumps(ideas, ensure_ascii=False, indent=2), encoding="utf-8")
            return self._json({"ok": True, "id": iid, "note": note})

        if p == "/api/idea/run":
            iid, step = body.get("id", ""), body.get("step", "")
            brief = (body.get("brief") or "").strip()
            if brief and (IDEAS / iid).is_dir():
                (IDEAS / iid / "brief.md").write_text(brief, encoding="utf-8")
            if step not in ({"transcribe", "full"} | set(STEP_PROMPT)) or not (IDEAS / iid).is_dir():
                return self._json({"error": "bad request"}, 400)
            with ILOCK:
                if IJOB["state"] == "running":
                    return self._json({"error": "یک کار در حال اجراست."}, 409)
            threading.Thread(target=run_idea_step, args=(iid, step), daemon=True).start()
            return self._json({"ok": True})

        if p == "/api/reel/delete":
            slug, num = body.get("slug", ""), str(body.get("num", ""))
            if "/" in slug or ".." in slug or not num or not (OUTPUT / slug).is_dir():
                return self._json({"error": "bad request"}, 400)
            hit = delete_reel(slug, num)
            if not hit:
                return self._json({"error": "این ریلز پیدا نشد."}, 404)
            return self._json({"ok": True, "files": hit})

        if p == "/api/idea/edit":
            code, res = edit_idea(body)
            return self._json(res, code)

        if p == "/api/idea/draft":
            d = save_draft(body)
            return self._json(d) if d is not None else self._json({"error": "bad payload"}, 400)

        if p == "/api/ideas":
            ideas = body.get("ideas")
            if not isinstance(ideas, list):
                return self._json({"error": "bad payload"}, 400)
            # The page sends the list it loaded; ideas added since (from the
            # Telegram bot) are kept unless this save is the one deleting them.
            deleted = set(body.get("deleted") or [])
            with cfg.IDEAS_LOCK:
                given = {i.get("id") for i in ideas if isinstance(i, dict)}
                extra = [i for i in jread("ideas.json", [])
                         if i.get("id") not in given and i.get("id") not in deleted]
                merged = extra + ideas
                DATA.mkdir(exist_ok=True)
                (DATA / "ideas.json").write_text(
                    json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
            return self._json({"ok": True, "count": len(merged), "added": len(extra)})

        if p == "/api/brand":
            if not isinstance(body.get("changed"), list):
                # a tab still running the old page would overwrite newer answers wholesale
                return self._json({"error": "این صفحه نسخه‌ی قدیمی است؛ یک بار تازه‌اش کن."}, 409)
            ok, res = bc.save(body.get("fields"), body.get("changed"))
            return self._json(res, 200 if ok else 400)
        if p == "/api/brand/asset":
            ok, res = bc.save_asset(body.get("filename"), body.get("data"))
            return self._json(res, 200 if ok else 400)
        if p == "/api/brand/asset/delete":
            ok, res = bc.delete_asset(body.get("file"))
            return self._json(res, 200 if ok else 404)

        r = rd.handle_post(p, body) or am.handle_post(p, body) or cfg.handle_post(p, body)
        if r is not None:
            return self._json(r[1], r[0])

        r = tr.handle_post(p, body)
        if r is not None:
            return self._json(r[1], r[0])

        r = st.handle_post(p, body)
        if r is not None:
            return self._json(r[1], r[0])

        r = adv.handle_post(p, body)
        if r is not None:
            return self._json(r[1], r[0])

        r = cr.handle_post(p, body)
        if r is not None:
            return self._json(r[1], r[0])

        r = vd.handle_post(p, body)
        if r is not None:
            return self._json(r[1], r[0])

        r = ig.handle_post(p, body)
        if r is not None:
            return self._json(r[1], r[0])

        self._json({"error": "not found"}, 404)


# ترتیب همان مسیری است که دانشجو طی می‌کند. تب تازه: اینجا ثبتش کن، یک view در go() (app.js) بگذار
# و راهنمای کوتاهش را در GUIDES (onboarding.js) بنویس.
MODULES = [
    {"key": "start",     "label": "شروع",          "ready": True},
    {"key": "dashboard", "label": "داشبورد",       "ready": True},
    {"key": "brand",     "label": "هسته‌ی برند",   "ready": True},
    {"key": "advisor",   "label": "مشاور",         "ready": True},
    {"key": "ideas",     "label": "بانک ایده",     "ready": True},
    {"key": "translations", "label": "ترجمه‌های یوتیوب", "ready": True},
    {"key": "reels",     "label": "استودیو ریلز",  "ready": True},
    {"key": "video",     "label": "تدوین ویدیو",   "ready": True},
    {"key": "story",     "label": "استوری",        "ready": True},
    {"key": "carousel",  "label": "کاروسل و پست",  "ready": True},
    {"key": "analytics", "label": "تحلیل اینستاگرام",  "ready": True},
    {"key": "settings",  "label": "تنظیمات",       "ready": True},
]


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 7788
    # Threaded: the Instagram pages load dozens of thumbnails at once, and a
    # single-threaded server with a 5-slot backlog refused some of them.
    socketserver.ThreadingTCPServer.allow_reuse_address = os.name != "nt"   # روی ویندوز یعنی دو سرور روی یک پورت
    socketserver.ThreadingTCPServer.daemon_threads = True
    # An explicit port is strict: if it's taken, a studio is already running there.
    for _ in range(1 if len(sys.argv) > 1 else 12):
        try:
            httpd = socketserver.ThreadingTCPServer(("127.0.0.1", port), H); break
        except OSError:
            port += 1
    else:
        sys.exit(f"پورت {port - 1} گرفته است؛ استودیو احتمالاً همین حالا در حال اجراست."
                 if len(sys.argv) > 1 else "پورت آزاد پیدا نشد.")
    url = f"http://127.0.0.1:{port}"
    print(f"\n  🎬  Content Studio\n  ▸  {url}")
    print(f"  ▸  {len(list_videos())} ویدیو · {len(jread('ideas.json', []))} ایده")
    print("  ▸  این پنجره را تا وقتی با استودیو کار می‌کنی باز نگه دار. برای بستن: Ctrl+C\n")
    DATA.mkdir(exist_ok=True); BRAND.mkdir(exist_ok=True)
    threading.Thread(target=ig.token_keeper, daemon=True).start()
    if not os.environ.get("STUDIO_NO_BROWSER"):
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  بسته شد.\n")


if __name__ == "__main__":
    main()
