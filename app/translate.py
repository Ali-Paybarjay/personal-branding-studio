"""ترجمه‌ی کامل ویدیوی یوتیوب برای خواندن، و فرستادن تکه‌های انتخاب‌شده به بانک ایده.

لینک → ترنسکریپت (get_transcript.py) → تکه‌های حدود ۹۰۰ کلمه‌ای → هر تکه جدا با claude -p ترجمه می‌شود
(اول تکه‌ی یک به‌تنهایی تا خواندن زود شروع شود و اسم گوینده‌ها جا بیفتد، بعد بقیه دوتا دوتا).

همه‌چیز در پوشه‌ی همان ویدیو در modules/reels/output/<slug>/ است:
  translation.json        منبع اصلی (هر تکه: متن انگلیسی، وضعیت، پاراگراف‌های فارسی)
  07-ترجمه-کامل.md        خودکار از روی json — دستی ویرایش نکن
  picks.json              تکه‌هایی که کاربر انتخاب کرده و هنوز به بانک ایده نفرستاده + فرستاده‌ها
  thumb.jpg               تامبنیل یوتیوب (یک بار گرفته می‌شود تا کارت‌ها بدون اینترنت هم عکس داشته باشند)
  reel-ideas.json         ایده‌های ریلزی که Claude از روی ترجمه پیشنهاد می‌دهد — فقط وقتی کاربر دکمه‌اش را بزند
  08-ایده‌های-ریلز.md      خودکار از روی reel-ideas.json

ترجمه فقط برای خواندن خود کاربر است و منتشر نمی‌شود؛ ریلز از روی ایده و با حرف خود او ساخته می‌شود.
"""
import json, re, shutil, subprocess, sys, tempfile, threading, time, urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import settings as cfg            # IDEAS_LOCK: همه‌ی نوشتن‌های ideas.json از این قفل رد می‌شوند
import ai_models as am
import brand as bc                # پیلرهای هسته‌ی برند

ROOT   = Path(__file__).resolve().parent.parent
REELS  = ROOT / "modules" / "reels"
OUTPUT = REELS / "output"
DATA   = ROOT / "data"
IDEAS  = DATA / "ideas"

MD_NAME = "07-ترجمه-کامل.md"
TARGET_WORDS = 900               # اندازه‌ی هر تکه؛ هر تکه حدود ۲ دقیقه ترجمه می‌شود
PARALLEL = 2                     # روی اشتراک Pro، چهار ترجمه‌ی هم‌زمان سهمیه را زود تمام می‌کند

JOB = {"state": "idle", "slug": "", "step": "", "done": 0, "total": 0, "error": "", "log": []}
JLOCK = threading.Lock()         # وضعیت کار
FLOCK = threading.Lock()         # نوشتن translation.json و picks.json

PROMPT = """این یک کار ترجمه است، نه تولید محتوا. هیچ فایلی نخوان و ننویس.

کاربر می‌خواهد کل این ویدیو را به فارسی بخواند — کامل. خلاصه نکن، تحلیل نکن، چیزی اضافه نکن، چیزی جا نینداز.

ویدیو: «@@TITLE@@» — کانال @@CHANNEL@@
این تکه‌ی @@N@@ از @@TOTAL@@ است.
@@SPEAKERS@@

قواعد:
۱. همه‌ی جمله‌ها را به همان ترتیب ترجمه کن؛ هر جمله‌ی انگلیسی باید در فارسی باشد. فقط این‌ها حذف می‌شوند: um، uh، you know و like پرکننده، و تکرارهای لکنتی («I I think» یعنی «فکر می‌کنم»).
۲. فارسی نوشتاری روان و طبیعی، مثل ترجمه‌ی خوب یک کتاب گفتگو — نه شکسته‌ی محاوره‌ای، نه اداری. اول‌شخص گوینده حفظ شود («من فکر می‌کنم…»).
۳. اصطلاح‌ها: اصطلاح تخصصی یا جاافتاده‌ی انگلیسی (مثل fine-tuning، open-weight، regulatory capture) را انگلیسی بنویس و معادل فارسی‌اش را جلویش در پرانتز بیاور: open-weight (وزن‌باز). فقط بار اولی که در این تکه می‌آید پرانتز بگیرد؛ دفعه‌های بعد فقط خود اصطلاح انگلیسی.
۴. اسم شرکت و محصول انگلیسی بماند (OpenAI، ChatGPT، Coursera). اسم آدم‌ها فارسی، و بار اول انگلیسی‌اش در پرانتز: اریک برینیولفسون (Erik Brynjolfsson).
۵. زیرنویس خودکار است و غلط شنیداری دارد («chai GPT» یعنی ChatGPT، «Corsera» یعنی Coursera). منظور واقعی را ترجمه کن. اگر واقعاً معلوم نیست چه گفته شده، ترجمه‌ی تحت‌اللفظی بده و بعدش [؟] بگذار.
۶. «>>» یعنی گوینده عوض شد: پاراگراف تازه شروع کن. اگر از متن قطعاً معلوم است گوینده کیست، پاراگراف را با «**مجری:**» یا «**<اسم کوتاه مهمان>:**» شروع کن؛ اگر مطمئن نیستی با «— » شروع کن. حدس نزن.
۷. تبلیغ اسپانسر («این ویدیو با حمایت … است»، معرفی محصول اسپانسر و لینکش) را ترجمه نکن؛ به جایش یک پاراگراف بگذار: (تبلیغ اسپانسر: <نام> — حذف شد). هیچ چیز دیگری را حذف نکن.
۸. پاراگراف‌های کوتاه (۲ تا ۵ جمله). هر پاراگراف با تایم‌کدِ بلوکی شروع شود که آن پاراگراف در آن شروع می‌شود، دقیقاً به این شکل: [MM:SS] و بعد متن.
۹. این تکه از وسط ویدیو بریده شده. «پیش‌زمینه»ها فقط برای فهمیدن‌اند؛ ترجمه‌شان نکن. از اولین کلمه‌ی متن اصلی شروع کن و تا آخرین کلمه‌اش برو.
۱۰. بولد (**) فقط برای اسم گوینده. توضیح مترجم نده.

خروجی: فقط پاراگراف‌های ترجمه، بین یک خط <<<FA و یک خط FA>>>. هیچ چیز دیگری ننویس.

پیش‌زمینه (پیش از این تکه — ترجمه نکن):
@@BEFORE@@

متن اصلی برای ترجمه:
<<<EN
@@TEXT@@
EN>>>

پیش‌زمینه (پس از این تکه — ترجمه نکن):
@@AFTER@@"""


# ---------- ابزار ----------
def claude_bin():
    return cfg.claude_bin()


def safe_slug(slug):
    return bool(slug) and re.fullmatch(r"[\w-]{1,80}", slug) is not None and (OUTPUT / slug).is_dir()


def video_id(url):
    m = re.search(r"(?:v=|youtu\.be/|/shorts/|/live/|/embed/)([\w-]{11})", url or "")
    return m.group(1) if m else ""


def secs(t):
    """«12:34» یا «1:02:03» → ثانیه"""
    try:
        n = 0
        for p in str(t).split(":"):
            n = n * 60 + int(p)
        return n
    except ValueError:
        return 0


def yt_at(url, t):
    vid = video_id(url)
    return f"https://www.youtube.com/watch?v={vid}&t={secs(t)}s" if vid else url


def setj(**kw):
    with JLOCK:
        JOB.update(kw)


def jlog(line):
    with JLOCK:
        JOB["log"].append(line)
        del JOB["log"][:-30]


def read_json(f, default):
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        return default


def video_info(d):
    m = {"title": d.name, "channel": "", "duration": "", "url": ""}
    f = d / "video-info.md"
    if f.exists():
        t = f.read_text(encoding="utf-8")
        if x := re.search(r"^#\s+(.+)$", t, re.M):
            m["title"] = x.group(1).strip()
        for key, lab in (("channel", "کانال"), ("duration", "مدت"), ("url", "لینک")):
            if x := re.search(rf"\*\*{lab}:\*\*\s*(.+)$", t, re.M):
                m[key] = x.group(1).strip()
    return m


# ---------- تامبنیل ----------
def ensure_thumb(slug):
    """thumb.jpg پوشه‌ی ویدیو؛ اگر نیست، بهترین اندازه‌ای که یوتیوب دارد گرفته می‌شود."""
    d = OUTPUT / slug
    f = d / "thumb.jpg"
    if f.exists() and f.stat().st_size > 2000:
        return f
    tr = load(slug) or {}
    vid = tr.get("vid") or video_id(tr.get("url") or video_info(d)["url"])
    if not vid:
        return None
    # همه‌ی ویدیوها maxres ندارند؛ برای نبودنش یوتیوب 404 می‌دهد
    for name in ("maxresdefault", "sddefault", "hqdefault"):
        try:
            with urllib.request.urlopen(f"https://i.ytimg.com/vi/{vid}/{name}.jpg", timeout=10) as r:
                data = r.read()
        except Exception:
            continue
        if len(data) > 2000:
            tmp = d / f".thumb-{threading.get_ident()}.jpg"
            tmp.write_bytes(data)
            tmp.replace(f)
            return f
    return None


# ---------- تکه‌تکه کردن ترنسکریپت ----------
BLOCK = re.compile(r"^\[(\d+:\d{2}(?::\d{2})?)\]\s*(.*)$", re.S)
# جای خوب برای بریدن: پیش از «>>» (عوض شدن گوینده) یا بعد از پایان جمله
CUT = re.compile(r"\s+(?=>>)|(?<=[.?!])\s+")


def chunk_transcript(text, target=TARGET_WORDS):
    blocks = []
    for part in re.split(r"\n\s*\n", text.strip()):
        m = BLOCK.match(part.strip())
        if m:
            blocks.append([m.group(1), " ".join(m.group(2).split())])
        elif blocks and part.strip():
            blocks[-1][1] += " " + " ".join(part.split())
    chunks, cur, n, i = [], [], 0, 0
    while i < len(blocks):
        t, txt = blocks[i]
        cur.append([t, txt])
        n += len(txt.split())
        if n >= target and i < len(blocks) - 1:
            # جمله‌ی نیمه‌کاره‌ی آخر بلوک به تکه‌ی بعد می‌رود تا هیچ جمله‌ای دو نیم نشود
            cuts = [m.end() for m in CUT.finditer(txt) if m.start() > 0]
            if cuts and len(txt[cuts[-1]:].split()) >= 3:
                cur[-1][1] = txt[:cuts[-1]].strip()
                blocks[i] = [t, txt[cuts[-1]:].strip()]
                chunks.append(cur); cur, n = [], 0
                continue
            # این بلوک نقطه ندارد (زیرنویس خودکار): تا پایان اولین جمله‌ی بلوک بعد جلو برو
            nt, nxt = blocks[i + 1]
            ahead = [m.end() for m in CUT.finditer(nxt) if m.start() > 0]
            if ahead and len(nxt[:ahead[0]].split()) <= 45 and len(nxt[ahead[0]:].split()) >= 3:
                cur.append([nt, nxt[:ahead[0]].strip()])
                blocks[i + 1] = [nt, nxt[ahead[0]:].strip()]
            chunks.append(cur); cur, n = [], 0
        i += 1
    if cur:
        if chunks and n < target // 4:       # تکه‌ی آخرِ خیلی کوچک به قبلی می‌چسبد
            chunks[-1].extend(cur)
        else:
            chunks.append(cur)
    return [{"i": k, "start": c[0][0], "end": c[-1][0],
             "en": "\n\n".join(f"[{t}] {x}" for t, x in c if x),
             "state": "todo", "paras": [], "error": ""} for k, c in enumerate(chunks)]


def _tail(text, words=70):
    w = re.sub(r"\[\d+:\d{2}(?::\d{2})?\]\s*", "", text).split()
    return " ".join(w[-words:])


def _head(text, words=70):
    w = re.sub(r"\[\d+:\d{2}(?::\d{2})?\]\s*", "", text).split()
    return " ".join(w[:words])


def parse_output(out, start):
    m = re.search(r"<<<FA\s*\n(.*?)\n\s*FA>>>", out, re.S)
    if not m:
        return None
    paras, t = [], start
    for block in re.split(r"\n\s*\n", m.group(1).strip()):
        block = block.strip()
        if not block:
            continue
        x = re.match(r"^\[(\d+:\d{2}(?::\d{2})?)\]\s*", block)
        if x:
            t, block = x.group(1), block[x.end():]
        # تایم‌کدی که وسط پاراگراف مانده، به خواندن کمکی نمی‌کند
        block = re.sub(r"\s*\[\d+:\d{2}(?::\d{2})?\]\s*", " ", block).strip()
        block = re.sub(r"[ \t]*\n[ \t]*", " ", block)
        if block:
            paras.append({"t": t, "fa": block})
    return paras or None


# ---------- خواندن و نوشتن ----------
def tfile(slug):
    return OUTPUT / slug / "translation.json"


def load(slug):
    return read_json(tfile(slug), None)


def _save(slug, tr):
    tr["updated"] = time.strftime("%Y-%m-%d %H:%M")
    tfile(slug).write_text(json.dumps(tr, ensure_ascii=False, indent=1), encoding="utf-8")
    (OUTPUT / slug / MD_NAME).write_text(render_md(tr), encoding="utf-8")


def render_md(tr):
    out = [f"# ترجمه‌ی کامل — {tr.get('title', '')}", "",
           f"- **کانال:** {tr.get('channel', '')}", f"- **مدت:** {tr.get('duration', '')}",
           f"- **لینک:** {tr.get('url', '')}", "",
           "> ترجمه‌ی کامل فقط برای خواندن خود کاربر است؛ منتشر نمی‌شود.", ""]
    for c in tr.get("chunks", []):
        if c.get("state") != "done":
            out += [f"*(بخش {c['start']} تا {c['end']} هنوز ترجمه نشده)*", ""]
            continue
        for p in c["paras"]:
            out += [f"[{p['t']}] {p['fa']}", ""]
    return "\n".join(out)


def update_chunk(slug, i, **kw):
    with FLOCK:
        tr = load(slug)
        if not tr:
            return
        tr["chunks"][i].update(kw)
        _save(slug, tr)


# ---------- ترجمه ----------
def speakers_of(tr):
    """اسم‌هایی که تکه‌های قبلی برای گوینده‌ها گذاشته‌اند، تا همه‌ی تکه‌ها یکدست باشند."""
    seen = []
    for c in tr["chunks"]:
        for p in c.get("paras", []):
            if (m := re.match(r"^\*\*([^*:]{1,40}):\*\*", p["fa"])) and m.group(1) not in seen:
                seen.append(m.group(1))
    return seen


def translate_chunk(slug, i):
    tr = load(slug)
    c, chunks = tr["chunks"][i], tr["chunks"]
    names = speakers_of(tr)
    fill = {"TITLE": tr.get("title", ""), "CHANNEL": tr.get("channel", ""),
            "N": str(i + 1), "TOTAL": str(len(chunks)),
            "SPEAKERS": f"برچسب‌هایی که بخش‌های قبلی برای گوینده‌ها گذاشته‌اند (همین‌ها را به کار ببر): {'، '.join(names)}" if names else "",
            "BEFORE": _tail(chunks[i - 1]["en"]) if i > 0 else "(شروع ویدیو)",
            "AFTER": _head(chunks[i + 1]["en"]) if i + 1 < len(chunks) else "(پایان ویدیو)",
            "TEXT": c["en"]}
    # یک‌جا جایگزین می‌شود تا متن ویدیو هیچ‌وقت خودش جای‌نگهدار حساب نشود
    prompt = re.sub(r"@@(\w+)@@", lambda m: fill[m.group(1)], PROMPT)
    update_chunk(slug, i, state="running", error="")
    err = ""
    for attempt in (1, 2):
        try:
            # بیرون از پوشه‌ی استودیو اجرا می‌شود تا CLAUDE.md آن (قواعد تولید محتوا) قاطی ترجمه نشود
            r = subprocess.run([claude_bin(), "-p", "--output-format", "text", "--tools", "",
                                "--no-session-persistence", "--model", am.get("translate")],
                               input=prompt, cwd=tempfile.gettempdir(),
                               capture_output=True, text=True, timeout=1200)
            paras = parse_output(r.stdout or "", c["start"]) if r.returncode == 0 else None
            if paras:
                update_chunk(slug, i, state="done", paras=paras, error="")
                return True
            err = (r.stderr or r.stdout or "").strip()[-300:] or "خروجی قالب درستی نداشت."
        except subprocess.TimeoutExpired:
            err = "زمان ترجمه‌ی این بخش تمام شد."
        jlog(f"▸ بخش {i + 1}: تلاش {attempt} ناموفق — {err[:120]}")
    update_chunk(slug, i, state="error", error=err)
    return False


def run_job(url, slug=None):
    try:
        setj(state="running", slug=slug or "", step="گرفتن زیرنویس از یوتیوب", done=0, total=0,
             error="", log=[])
        if not slug:
            p = subprocess.run([sys.executable, str(REELS / "scripts" / "get_transcript.py"), url],
                               cwd=str(REELS), capture_output=True, text=True, timeout=600)
            for ln in (p.stderr or "").splitlines():
                if ln.strip():
                    jlog(ln.strip())
            out = (p.stdout or "").strip().splitlines()
            slug = Path(out[-1]).name if p.returncode == 0 and out else ""
            if not slug or not (OUTPUT / slug).is_dir():
                return setj(state="error", error="زیرنویس گرفته نشد. لینک را چک کن (یا ویدیو زیرنویس ندارد).")
        setj(slug=slug)
        threading.Thread(target=ensure_thumb, args=(slug,), daemon=True).start()

        with FLOCK:
            tr = load(slug)
            if not tr:
                raw = OUTPUT / slug / "00-transcript-raw.txt"
                if not raw.exists():
                    return setj(state="error", error="ترنسکریپت پیدا نشد.")
                info = video_info(OUTPUT / slug)
                tr = {**info, "url": info["url"] or url, "vid": video_id(info["url"] or url),
                      "created": time.strftime("%Y-%m-%d"),
                      "chunks": chunk_transcript(raw.read_text(encoding="utf-8"))}
                if not tr["chunks"]:
                    return setj(state="error", error="ترنسکریپت خالی بود.")
            for c in tr["chunks"]:            # کار نیمه‌تمام قبلی (مثلاً سرور بسته شده بود)
                if c["state"] in ("running", "error"):
                    c["state"] = "todo"
            _save(slug, tr)

        todo = [c["i"] for c in tr["chunks"] if c["state"] != "done"]
        total = len(tr["chunks"])
        setj(step="ترجمه", total=total, done=total - len(todo))
        jlog(f"▸ {total} بخش · {len(todo)} بخش مانده")

        def one(i):
            ok = translate_chunk(slug, i)
            with JLOCK:
                JOB["done"] += 1 if ok else 0
            return ok

        if todo and todo[0] == 0:            # بخش اول تنها: خواندن زود شروع می‌شود و اسم گوینده‌ها جا می‌افتد
            one(todo.pop(0))
        with ThreadPoolExecutor(PARALLEL) as ex:
            list(ex.map(one, todo))

        tr = load(slug)
        bad = [c for c in tr["chunks"] if c["state"] != "done"]
        if bad:
            return setj(state="error", error=f"{len(bad)} بخش ترجمه نشد — «ادامه‌ی ترجمه» را بزن.")
        setj(state="done", step="تمام شد")
    except Exception as e:
        setj(state="error", error=f"خطای غیرمنتظره: {e}")


def find_existing(url):
    """اگر این ویدیو قبلاً گرفته شده، slug آن را برمی‌گرداند تا دوباره دانلود نشود."""
    vid = video_id(url)
    if not vid or not OUTPUT.is_dir():
        return None
    for d in OUTPUT.iterdir():
        if not d.is_dir():
            continue
        tr = read_json(d / "translation.json", None)
        if tr and tr.get("vid") == vid:
            return d.name
        if (d / "00-transcript-raw.txt").exists() and video_id(video_info(d)["url"]) == vid:
            return d.name
    return None


def start(url, slug=None):
    with JLOCK:
        if JOB["state"] == "running":
            return False, "یک ترجمه در حال اجراست؛ تمام که شد، بعدی را بده."
        JOB.update(state="running", slug=slug or "", step="شروع", error="", log=[])
    threading.Thread(target=run_job, args=(url, slug), daemon=True).start()
    return True, ""


# ---------- انتخاب‌ها ----------
def pfile(slug):
    return OUTPUT / slug / "picks.json"


def load_picks(slug):
    p = read_json(pfile(slug), {})
    return {"pending": p.get("pending") or [], "sent": p.get("sent") or []}


def clean_pending(items):
    out = []
    for c in items if isinstance(items, list) else []:
        if not isinstance(c, dict):
            continue
        ps = [{"pids": [str(x) for x in (p.get("pids") or [])][:60],
               "t": str(p.get("t") or ""), "text": str(p.get("text") or "").strip()[:20000]}
              for p in (c.get("passages") or []) if isinstance(p, dict) and str(p.get("text") or "").strip()]
        if ps:
            out.append({"title": str(c.get("title") or "").strip()[:200],
                        "note": str(c.get("note") or "").strip()[:4000], "passages": ps})
    return out


def save_pending(slug, items):
    with FLOCK:
        p = load_picks(slug)
        p["pending"] = clean_pending(items)
        pfile(slug).write_text(json.dumps(p, ensure_ascii=False, indent=1), encoding="utf-8")
    return p


def english_for(tr, passages):
    """متن اصلی انگلیسیِ بازه‌ی هر تکه‌ی انتخاب‌شده (برای دقت ایجنت‌های بعدی)."""
    t_of = {f"{c['i']}.{k}": p["t"] for c in tr["chunks"] for k, p in enumerate(c.get("paras", []))}
    spans = []
    for p in passages:
        ts = [secs(t_of[x]) for x in p["pids"] if x in t_of] + [secs(p["t"])]
        spans.append((min(ts) - 30, max(ts) + 30))
    out = []
    for c in tr["chunks"]:
        for part in c["en"].split("\n\n"):
            m = BLOCK.match(part)
            if m and any(a <= secs(m.group(1)) <= b for a, b in spans):
                out.append(part)
    return "\n\n".join(out)


def send_to_ideas(slug, items):
    tr = load(slug)
    if not tr:
        return False, "ترجمه پیدا نشد."
    cards = clean_pending(items)
    if not cards:
        return False, "چیزی انتخاب نشده."
    made, stamp, speakers = [], int(time.time() * 1000), speakers_of(tr)
    for k, c in enumerate(cards):
        iid = f"i{stamp}{k}"
        d = IDEAS / iid
        d.mkdir(parents=True, exist_ok=True)
        first = c["passages"][0]
        lines = [f"# ایده از ویدیوی یوتیوب", "",
                 f"- **ویدیو:** {tr.get('title', '')} — {tr.get('channel', '')}",
                 f"- **لینک:** [باز کردن در یوتیوب از دقیقه‌ی {first['t']}]({yt_at(tr.get('url', ''), first['t'])})",
                 f"- **متن کامل ترجمه در استودیو:** [باز کن](/?s=translations&read={slug})", "",
                 "> این‌ها حرف‌های گوینده‌ی ویدیوست، نه حرف من. اگر در ریلز از آن‌ها استفاده می‌شود، "
                 "اسم گوینده برده شود و چیزی به دهانش گذاشته نشود.", ""]
        if c["note"]:
            lines += ["## زاویه‌ی من", "", c["note"], ""]
        lines += ["## بخش‌هایی که انتخاب کردم (ترجمه‌ی فارسی)", ""]
        for p in c["passages"]:
            lines += [f"### دقیقه‌ی {p['t']}", "", p["text"], ""]
        en = english_for(tr, c["passages"])
        if en:
            lines += ["## متن اصلی همین بازه‌ها (زیرنویس ویدیو)", "", en, ""]
        (d / "raw.md").write_text("\n".join(lines), encoding="utf-8")
        auto = not c["title"]
        head = re.sub(r"^—\s*", "", " ".join(first["text"].split()))
        for name in speakers:                 # «اندرو: …» → «…»
            if head.startswith(name + ":"):
                head = head[len(name) + 1:].strip()
        title = c["title"] or head[:70]
        made.append({"id": iid, "title": title, **({"autoTitle": True} if auto else {}),
                     "pillar": "", "status": "idea", "score": None,
                     "source": {"kind": "youtube", "ref": slug, "at": first["t"],
                                "url": yt_at(tr.get("url", ""), first["t"]), "video": tr.get("title", "")},
                     "note": f"از ویدیوی «{tr.get('title', '')}»",
                     "created": time.strftime("%Y-%m-%d"), "steps": {}})
    with cfg.IDEAS_LOCK:
        f = DATA / "ideas.json"
        ideas = read_json(f, [])
        f.write_text(json.dumps(made + ideas, ensure_ascii=False, indent=2), encoding="utf-8")
    with FLOCK:
        p = load_picks(slug)
        p["pending"] = []
        p["sent"] += [{"idea": m["id"], "title": m["title"], "at": time.strftime("%Y-%m-%d"),
                       "pids": [x for ps in c["passages"] for x in ps["pids"]]}
                      for m, c in zip(made, cards)]
        pfile(slug).write_text(json.dumps(p, ensure_ascii=False, indent=1), encoding="utf-8")
    return True, [m["id"] for m in made]


# ---------- ایده‌های ریلز از روی ترجمه (فقط با دکمه‌ی کاربر) ----------
IDEAS_JSON, IDEAS_MD = "reel-ideas.json", "08-ایده‌های-ریلز.md"
IJOBS = {}                       # slug → {"state": running|done|error, "error": ""}
IJLOCK = threading.Lock()

IDEAS_PROMPT = """تو استراتژیست محتوای اینستاگرام صاحب این برند هستی. هیچ فایلی نخوان و ننویس؛ هر چه لازم است همین‌جاست.

هسته‌ی برند (مخاطب، لحن، پیلرها، خط قرمزها، ادعاهای ممنوع):
<<<BRAND
@@BRAND@@
BRAND>>>

پیلرهای مجاز: @@PILLARS@@

این ترجمه‌ی کامل فارسی ویدیوی یوتیوب «@@TITLE@@» از کانال @@CHANNEL@@ است. هر پاراگراف با زمانش [MM:SS] شروع می‌شود:
<<<TEXT
@@TEXT@@
TEXT>>>

از دل همین متن، ایده‌های ریلز اینستاگرام برای صاحب برند پیدا کن: ۵ تا ۱۰ ایده، بسته به اینکه متن چقدر حرف به‌دردبخور برای مخاطب او دارد. کیفیت مهم‌تر از تعداد است؛ اگر فقط ۳ ایده‌ی واقعاً خوب هست، همان ۳ تا.

برای هر ایده:
- "title": تایتل فارسی هوک‌دار برای ریلز (حداکثر حدود ۱۰ کلمه)، بدون کلیک‌بیت دروغ.
- "hook": جمله‌ی سه ثانیه‌ی اول ریلز، گفتاری و محاوره‌ای، به لحن هسته‌ی برند.
- "points": نکته‌هایی که گوینده درباره‌ی همین موضوع گفته؛ ۳ تا ۶ نکته، هر کدام {"t": "MM:SS", "text": "یک جمله‌ی کوتاه فارسی"}. فقط چیزی که واقعاً در متن آمده. "t" باید زمان یکی از پاراگراف‌های متن باشد، همانی که نکته در آن گفته شده.
- "angle": خطاب به خود صاحب برند و با «تو» (نه سوم‌شخص، نه با اسمش): چطور این را حرف خودت کنی و چرا برای مخاطبت مهم است؛ یک یا دو جمله.
- "pillar": دقیقاً یکی از پیلرهای مجاز بالا، یا "" اگر به هیچ‌کدام نمی‌خورد.
- "score": عدد ۱ تا ۱۰ (توقف اسکرول × ارزش برای مخاطب × سادگی ساخت).
- "caution": اگر عدد یا ادعایی هست که باید قبل از گفتن چک شود، یا گوینده خودش مطمئن نبوده، یا به خط قرمزهای برند نزدیک است، یک جمله؛ وگرنه "".

قواعد: نقل‌قول نساز و چیزی به دهان گوینده نگذار. ایده‌ها با هم هم‌پوشانی نداشته باشند. از بیشترین امتیاز به کمترین مرتب کن.

خروجی: فقط یک آرایه‌ی JSON معتبر، بین یک خط <<<IDEAS و یک خط IDEAS>>>. هیچ چیز دیگری ننویس."""

FA_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def load_ideas(slug):
    return read_json(OUTPUT / slug / IDEAS_JSON, None)


def ideas_state(slug):
    with IJLOCK:
        return dict(IJOBS.get(slug) or {"state": "idle", "error": ""})


def parse_ideas(out):
    m = re.search(r"<<<IDEAS\s*\n(.*?)\n\s*IDEAS>>>", out, re.S)
    if not m:
        return None
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", m.group(1).strip())
    try:
        data = json.loads(raw)
    except Exception:
        return None
    items = []
    for it in data if isinstance(data, list) else []:
        if not isinstance(it, dict) or not str(it.get("title") or "").strip():
            continue
        pts = []
        for p in it.get("points") or []:
            if isinstance(p, dict) and str(p.get("text") or "").strip():
                t = str(p.get("t") or "").strip().translate(FA_DIGITS)
                pts.append({"t": t if re.fullmatch(r"\d+:\d{2}(?::\d{2})?", t) else "",
                            "text": str(p["text"]).strip()})
            elif isinstance(p, str) and p.strip():
                pts.append({"t": "", "text": p.strip()})
        try:
            score = round(max(1.0, min(10.0, float(str(it.get("score") or 0).translate(FA_DIGITS)))), 1)
        except ValueError:
            score = None
        items.append({k: str(it.get(k) or "").strip() for k in ("title", "hook", "angle", "pillar", "caution")}
                     | {"points": pts, "score": score})
    return items or None


def render_ideas_md(tr, data):
    out = [f"# ایده‌های ریلز — {tr.get('title', '')}", "",
           f"پیشنهاد Claude از روی ترجمه‌ی کامل · ساخته‌شده {data.get('created', '')}", ""]
    for k, it in enumerate(data["items"], 1):
        meta = " · ".join(x for x in (f"امتیاز {it['score']}/۱۰" if it["score"] else "", it["pillar"]) if x)
        out += [f"## {k}. {it['title']}", ""] + ([f"*{meta}*", ""] if meta else [])
        if it["hook"]:
            out += [f"**هوک:** {it['hook']}", ""]
        if it["points"]:
            out += ["**گوینده چه گفته:**"] + [f"- [{p['t']}] {p['text']}" if p["t"] else f"- {p['text']}"
                                              for p in it["points"]] + [""]
        if it["angle"]:
            out += [f"**زاویه‌ی تو:** {it['angle']}", ""]
        if it["caution"]:
            out += [f"**احتیاط:** {it['caution']}", ""]
    return "\n".join(out)


def run_ideas(slug):
    def fail(msg):
        with IJLOCK:
            IJOBS[slug] = {"state": "error", "error": msg}
    try:
        tr = load(slug)
        bf = ROOT / "brand" / "brand-core.md"
        fill = {"BRAND": bf.read_text(encoding="utf-8") if bf.exists() else "(هسته‌ی برند پیدا نشد)",
                "PILLARS": "، ".join(bc.pillar_names()),
                "TITLE": tr.get("title", ""), "CHANNEL": tr.get("channel", ""),
                "TEXT": "\n\n".join(f"[{p['t']}] {p['fa']}" for c in tr["chunks"] for p in c["paras"])}
        prompt = re.sub(r"@@(\w+)@@", lambda m: fill[m.group(1)], IDEAS_PROMPT)
        err = ""
        for _ in (1, 2):
            try:
                # مثل ترجمه، بیرون از پوشه‌ی استودیو؛ هسته‌ی برند همین‌جا در پرامپت است
                r = subprocess.run([claude_bin(), "-p", "--output-format", "text", "--tools", "",
                                    "--no-session-persistence", "--model", am.get("translate")],
                                   input=prompt, cwd=tempfile.gettempdir(),
                                   capture_output=True, text=True, timeout=1800)
            except subprocess.TimeoutExpired:
                err = "زمان ساخت ایده‌ها تمام شد."
                continue
            items = parse_ideas(r.stdout or "") if r.returncode == 0 else None
            if items:
                d = OUTPUT / slug
                old = d / IDEAS_JSON
                if old.exists():                      # ساخت دوباره: نسخه‌ی قبلی کنار گذاشته می‌شود
                    old.replace(d / "reel-ideas.prev.json")
                data = {"created": time.strftime("%Y-%m-%d %H:%M"), "model": am.get("translate"), "items": items}
                old.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
                (d / IDEAS_MD).write_text(render_ideas_md(tr, data), encoding="utf-8")
                with IJLOCK:
                    IJOBS[slug] = {"state": "done", "error": ""}
                return
            err = (r.stderr or "").strip()[-300:] or "خروجی قالب درستی نداشت."
            (OUTPUT / slug / "reel-ideas.last-output.txt").write_text(r.stdout or "", encoding="utf-8")
        fail(err)
    except Exception as e:
        fail(f"خطای غیرمنتظره: {e}")


def start_ideas(slug):
    tr = load(slug)
    if not tr or any(c["state"] != "done" for c in tr["chunks"]):
        return False, "اول ترجمه باید کامل شود."
    with IJLOCK:
        if (IJOBS.get(slug) or {}).get("state") == "running":
            return False, "ایده‌های این ویدیو در حال ساخت است."
        IJOBS[slug] = {"state": "running", "error": ""}
    threading.Thread(target=run_ideas, args=(slug,), daemon=True).start()
    return True, ""


def send_suggested(slug, k):
    """ایده‌ی پیشنهادی شماره‌ی k را یک ایده‌ی تازه در بانک ایده می‌کند. خروجی: (کد، پاسخ)."""
    tr, data = load(slug), load_ideas(slug)
    items = (data or {}).get("items") or []
    if not tr or not isinstance(k, int) or not 0 <= k < len(items):
        return 400, {"error": "این ایده پیدا نشد."}
    it = items[k]
    with cfg.IDEAS_LOCK:
        have = {i.get("id") for i in read_json(DATA / "ideas.json", [])}
    if it.get("sent") in have:               # اگر کاربر آن را از بانک پاک کرده باشد، دوباره فرستادنش آزاد است
        return 409, {"error": "این ایده قبلاً به بانک ایده رفته.", "id": it["sent"]}

    # پاراگراف‌هایی که نکته‌های گوینده در آن‌ها گفته شده (زمان هر نکته = زمان یک پاراگراف)
    paras = [(f"{c['i']}.{n}", p["t"], p["fa"]) for c in tr["chunks"] for n, p in enumerate(c.get("paras", []))]
    pids = []
    for pt in it["points"]:
        if not pt["t"]:
            continue
        want = secs(pt["t"])
        hit = [x for x in paras if secs(x[1]) == want] or [x for x in paras if secs(x[1]) <= want][-1:]
        pids += [x[0] for x in hit if x[0] not in pids]
    by_id = {x[0]: x for x in paras}
    first_t = next((p["t"] for p in it["points"] if p["t"]), "0:00")

    iid = f"i{int(time.time() * 1000)}{k}"
    d = IDEAS / iid
    d.mkdir(parents=True, exist_ok=True)
    lines = ["# ایده‌ی پیشنهادی از ویدیوی یوتیوب", "",
             f"- **ویدیو:** {tr.get('title', '')} — {tr.get('channel', '')}",
             f"- **لینک:** [باز کردن در یوتیوب از دقیقه‌ی {first_t}]({yt_at(tr.get('url', ''), first_t)})",
             f"- **متن کامل ترجمه در استودیو:** [باز کن](/?s=translations&read={slug})", "",
             "> این ایده را Claude از روی ترجمه پیشنهاد داده و حرف‌های داخلش حرف گوینده‌ی ویدیوست، نه حرف من. "
             "اگر در ریلز از آن‌ها استفاده می‌شود، اسم گوینده برده شود و چیزی به دهانش گذاشته نشود.", "",
             "## تایتل پیشنهادی", "", it["title"], ""]
    if it["hook"]:
        lines += ["## هوک پیشنهادی", "", it["hook"], ""]
    if it["points"]:
        lines += ["## گوینده چه گفته", ""] + [f"- [{p['t']}] {p['text']}" if p["t"] else f"- {p['text']}"
                                              for p in it["points"]] + [""]
    if it["angle"]:
        lines += ["## زاویه‌ی پیشنهادی", "", it["angle"], ""]
    if it["caution"]:
        lines += ["## احتیاط", "", it["caution"], ""]
    if pids:
        lines += ["## متن ترجمه‌ی همین لحظه‌ها", ""]
        last = None
        for x in sorted(pids, key=lambda i: tuple(map(int, i.split(".")))):
            if by_id[x][1] != last:           # چند پاراگراف هم‌زمان زیر یک تیتر
                lines += [f"### دقیقه‌ی {by_id[x][1]}", ""]
                last = by_id[x][1]
            lines += [by_id[x][2], ""]
    en = english_for(tr, [{"pids": pids, "t": first_t}] if pids else [])
    if en:
        lines += ["## متن اصلی همین بازه‌ها (زیرنویس ویدیو)", "", en, ""]
    (d / "raw.md").write_text("\n".join(lines), encoding="utf-8")

    pillar = it["pillar"] if it["pillar"] in bc.pillar_names() else ""
    rec = {"id": iid, "title": it["title"], "pillar": pillar, "status": "idea", "score": it["score"],
           "source": {"kind": "youtube", "ref": slug, "at": first_t, "url": yt_at(tr.get("url", ""), first_t),
                      "video": tr.get("title", ""), "suggested": True},
           "note": f"پیشنهاد Claude از ویدیوی «{tr.get('title', '')}»",
           "created": time.strftime("%Y-%m-%d"), "steps": {}}
    with cfg.IDEAS_LOCK:
        f = DATA / "ideas.json"
        f.write_text(json.dumps([rec] + read_json(f, []), ensure_ascii=False, indent=2), encoding="utf-8")
    with FLOCK:
        data = load_ideas(slug) or {}
        if k < len(data.get("items") or []):
            data["items"][k]["sent"] = iid
            (OUTPUT / slug / IDEAS_JSON).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        p = load_picks(slug)                  # در متن هم ✓ می‌خورد و در «قبلاً فرستاده‌شده» می‌آید
        p["sent"].append({"idea": iid, "title": it["title"], "at": time.strftime("%Y-%m-%d"), "pids": pids})
        pfile(slug).write_text(json.dumps(p, ensure_ascii=False, indent=1), encoding="utf-8")
    return 200, {"ok": True, "id": iid, "picks": load_picks(slug)}


# ---------- فهرست ----------
def list_all():
    if not OUTPUT.is_dir():
        return []
    with JLOCK:
        live = JOB["slug"] if JOB["state"] == "running" else ""
    out = []
    for d in OUTPUT.iterdir():
        tr = read_json(d / "translation.json", None) if d.is_dir() else None
        if not tr:
            continue
        p = load_picks(d.name)
        out.append({"slug": d.name, "title": tr.get("title", ""), "channel": tr.get("channel", ""),
                    "duration": tr.get("duration", ""), "url": tr.get("url", ""),
                    "created": tr.get("created", ""), "updated": tr.get("updated", ""),
                    "total": len(tr["chunks"]), "done": sum(c["state"] == "done" for c in tr["chunks"]),
                    "words": sum(len(x["fa"].split()) for c in tr["chunks"] for x in c.get("paras", [])),
                    "live": d.name == live, "pending": len(p["pending"]), "sent": len(p["sent"]),
                    "ideas": len((load_ideas(d.name) or {}).get("items") or [])})
    # تازه‌ترین اول: آخرین ترجمه یا آخرین بخشی که تمام شد
    return sorted(out, key=lambda x: x["updated"], reverse=True)


# ---------- مسیرها ----------
def handle_get(p, q):
    if p == "/api/tr/status":
        with JLOCK:
            return 200, dict(JOB)
    if p == "/api/tr/list":
        return 200, {"items": list_all()}
    if p == "/api/tr/thumb":
        slug = q.get("slug", [""])[0]
        f = ensure_thumb(slug) if safe_slug(slug) else None
        return (200, f.read_bytes(), "image/jpeg") if f else (404, {"error": "تامبنیل نیست"})
    if p == "/api/tr/get":
        slug = q.get("slug", [""])[0]
        if not safe_slug(slug):
            return 400, {"error": "bad request"}
        tr = load(slug)
        if not tr:
            return 404, {"error": "ترجمه‌ای برای این ویدیو نیست."}
        with JLOCK:
            live = JOB["state"] == "running" and JOB["slug"] == slug
        chunks = [{k: v for k, v in c.items() if k != "en"} for c in tr["chunks"]]
        if not live:                         # «در حال ترجمه» از یک اجرای قطع‌شده
            for c in chunks:
                if c["state"] == "running":
                    c["state"] = "todo"
        return 200, {**{k: v for k, v in tr.items() if k != "chunks"}, "chunks": chunks,
                     "live": live, "picks": load_picks(slug),
                     "ideas": load_ideas(slug), "ideas_job": ideas_state(slug)}
    if p == "/api/tr/ideas":
        slug = q.get("slug", [""])[0]
        if not safe_slug(slug):
            return 400, {"error": "bad request"}
        return 200, {"job": ideas_state(slug), "ideas": load_ideas(slug)}
    return None


def handle_post(p, body):
    if p == "/api/tr/start":
        url = (body.get("url") or "").strip()
        if not re.match(r"^https?://(www\.|m\.)?(youtube\.com|youtu\.be)/", url) or not video_id(url):
            return 400, {"error": "لینک یوتیوب معتبر نیست."}
        slug = find_existing(url)
        if slug:
            tr = load(slug)
            if tr and all(c["state"] == "done" for c in tr["chunks"]):
                return 200, {"ok": True, "slug": slug, "existing": True}
        ok, err = start(url, slug)
        return (200, {"ok": True, "slug": slug or ""}) if ok else (409, {"error": err})
    if p == "/api/tr/resume":
        slug = body.get("slug", "")
        if not safe_slug(slug) or not load(slug):
            return 400, {"error": "bad request"}
        ok, err = start(load(slug).get("url", ""), slug)
        return (200, {"ok": True, "slug": slug}) if ok else (409, {"error": err})
    if p == "/api/tr/ideas":
        slug = body.get("slug", "")
        if not safe_slug(slug) or not load(slug):
            return 400, {"error": "bad request"}
        ok, err = start_ideas(slug)
        return (200, {"ok": True}) if ok else (409, {"error": err})
    if p == "/api/tr/ideas/send":
        slug = body.get("slug", "")
        if not safe_slug(slug):
            return 400, {"error": "bad request"}
        return send_suggested(slug, body.get("index"))
    if p == "/api/tr/picks":
        slug = body.get("slug", "")
        if not safe_slug(slug):
            return 400, {"error": "bad request"}
        return 200, {"ok": True, "picks": save_pending(slug, body.get("pending"))}
    if p == "/api/tr/send":
        slug = body.get("slug", "")
        if not safe_slug(slug):
            return 400, {"error": "bad request"}
        ok, res = send_to_ideas(slug, body.get("pending"))
        return (200, {"ok": True, "ids": res, "picks": load_picks(slug)}) if ok else (400, {"error": res})
    return None
