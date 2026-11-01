"""ویرایشگر ریلزِ بانک ایده: ریلز بخش‌بخش (تایتل، هوک‌ها، بدنه، کال‌تو‌اکشن، کپشن، هشتگ‌ها).

هر ایده یک data/ideas/<id>/reel.json دارد (منبع اصلی) و هر ذخیره reel.md را از نو می‌سازد
تا هر چیزی که md را می‌خواند (ایجنت‌ها، پنل کلمه‌ی کلیدی) کار کند.
هر بخش جدا ویرایش می‌شود، جدا با نظر کاربر بازتولید می‌شود، و یک نسخه‌ی قبل برای برگشت دارد.
"""
import json, re, shutil, subprocess, threading, time
from pathlib import Path
import ai_models as am
import settings as cfg

ROOT  = Path(__file__).resolve().parent.parent
IDEAS = ROOT / "data" / "ideas"

FIELDS = ["title", "hooks", "body", "cta", "caption", "hashtags"]
LABEL = {"title": "تایتل", "hooks": "هوک‌ها", "body": "بدنه", "cta": "کال‌تو‌اکشن",
         "caption": "کپشن", "hashtags": "هشتگ‌ها"}

# قواعد هر بخش؛ هم در ساخت اول و هم در بازتولید همان بخش به مدل داده می‌شود
RULES = {
"title": "یک تایتل فارسی کوتاه (حداکثر حدود ۱۰ کلمه) برای روی کاور و صفحه. هوک‌دار ولی بدون کلیک‌بیت دروغ.",
"hooks": """شش هوک. هر هوک دقیقاً همان جمله (یا دو جمله‌ی کوتاه) است که در ۳ ثانیه‌ی اول ریلز گفته می‌شود — گفتاری و محاوره‌ای.
هر کدام با یک تکنیک متفاوت: عدد یا آمار، سؤال مستقیم، حرف خلاف انتظار، شروع داستان، هشدار یا اشتباه رایج، وعده‌ی نتیجه.
همه باید طوری باشند که «بدنه» بعد از هر کدامشان طبیعی ادامه پیدا کند. کلیک‌بیت دروغ نه، وعده‌ای که بدنه پس نمی‌دهد نه.
قالب خروجی: فهرست شماره‌دار، هر خط یک هوک، بدون گیومه دور هوک.""",
"body": """بدنه‌ی متن ضبط — فارسی گفتاری و محاوره‌ای (می‌کنه، می‌گه، یه)، حدود ۲۰۰ تا ۲۸۰ کلمه.
درست بعد از هوک شروع می‌شود؛ هوک را تکرار نکن. کال‌تو‌اکشن را هم ننویس — آن بخش جداست.
محتوای اصلی، مثال، و اگر عدد می‌آوری فقط عددی که منبع دارد (ترجیحاً از research.md) و منبعش را در متن بگو.
بدون نشانه‌ی مکث، بدون پیشنهاد تصویر یا زیرنویس صحنه. فقط **بولد** روی کلمه‌های تأکیدی. پاراگراف‌های کوتاه.""",
"cta": """کال‌تو‌اکشن پایان ریلز — یک تا سه جمله‌ی گفتاری که بعد از بدنه گفته می‌شود.
قواعد CTA و «کتابخانه‌ی CTA» در brand-core را دقیق رعایت کن؛ اگر جمله‌ی آماده‌ای برای این هدف هست، همان را بیاور.
می‌تواند با یک سؤال مستقیم از مخاطب تمام شود.""",
"caption": """کپشن پست اینستاگرام — نوشتاری، نه گفتاری. خط اول خودش هوک است (چون فقط همان قبل از «بیشتر» دیده می‌شود).
دو تا پنج پاراگراف کوتاه که حرف اصلی ریلز را خلاصه می‌کند و یک چیز اضافه می‌دهد؛ آخرش همان دعوت کال‌تو‌اکشن.
ایموجی در کپشن آزاد است (طبق brand-core)، ولی کم. هشتگ داخل کپشن نگذار — بخش جداست.""",
"hashtags": "سه تا پنج هشتگ مرتبط، نه بیشتر (اینستاگرام از دسامبر ۲۰۲۵ بیشتر از پنج هشتگ نمی‌گذارد)؛ ترکیب فارسی و انگلیسی، از خاص به عام. همه در یک خط، با فاصله از هم.",
}

PRODUCE_PROMPT = """اول brand/brand-core.md را کامل بخوان — لحن، مخاطب، پیلرها، خط قرمزها، ادعاهای ممنوع و قواعد CTA.
بعد پوشه‌ی data/ideas/ID/ را بخوان: raw.md (ایده‌ی خام کاربر) و اگر هستند analysis.md و research.md و brief.md.

از این ایده یک ریلز اینستاگرام بساز. در هیچ فایلی ننویس؛ کل خروجی را فقط در پاسخت بده،
بین یک خط <<<REEL و یک خط REEL>>>، دقیقاً با همین عنوان‌ها و به همین ترتیب:

<<<REEL
## تایتل
## هوک‌ها
## بدنه
## کال‌تو‌اکشن
## کپشن
## هشتگ‌ها
## یادداشت
REEL>>>

قواعد هر بخش:

### تایتل
RULE_title

### هوک‌ها
RULE_hooks

### بدنه
RULE_body

### کال‌تو‌اکشن
RULE_cta

### کپشن
RULE_caption

### هشتگ‌ها
RULE_hashtags

### یادداشت
یک خط: «امتیاز: X/۱۰ — » و یک جمله که چرا این ریلز کار می‌کند.

قواعد کلی: هیچ ادعای ممنوعی از brand-core نزن. هر عددی منبع داشته باشد. هیچ نقل‌قولی نساز.
هیچ سؤالی نپرس."""
for _k, _v in RULES.items():
    PRODUCE_PROMPT = PRODUCE_PROMPT.replace("RULE_" + _k, _v)

REGEN_PROMPT = """اول brand/brand-core.md را بخوان (لحن، خط قرمزها، ادعاهای ممنوع، قواعد CTA).
اگر برای این کار لازم شد، data/ideas/ID/ را هم بخوان (raw.md، analysis.md، research.md).
اگر نظر کاربر عدد، منبع یا خبر تازه می‌خواهد، با WebSearch و WebFetch بگرد (رایگان) و منبع را در متن بگو؛ هیچ عددی از حافظه نیاور.

این ریلز فعلی است. کاربر ممکن است بخش‌هایی را دستی ویرایش کرده باشد؛ آن ویرایش‌ها تصمیم خود اوست، به آن‌ها احترام بگذار:
<<<CURRENT
CURRENT_MD
CURRENT>>>

فقط بخش «SEC_LABEL» را از نو بنویس. بقیه‌ی بخش‌ها دست نمی‌خورند، پس بخش تازه باید با آن‌ها جور باشد.

متن فعلی همین بخش:
<<<SECTION
SEC_TEXT
SECTION>>>

NOTE_BLOCK

قواعد این بخش:
SEC_RULES

در هیچ فایلی ننویس. فقط متن تازه‌ی همین بخش را بده، بین یک خط <<<OUT و یک خط OUT>>> —
بدون عنوان بخش، بدون توضیح قبل یا بعد."""


def five_tags(s):
    """اینستاگرام از دسامبر ۲۰۲۵ بیشتر از ۵ هشتگ نمی‌گذارد (مرجع API هنوز ۳۰ می‌گوید)؛ اگر Claude بیشتر داد، پنج‌تای اول
    که خاص‌ترها هستند می‌ماند. ویرایش دستی کاربر کوتاه نمی‌شود؛ شمارنده و بررسی پیش از انتشار خبر می‌دهند."""
    words = str(s or "").split()
    tags = [w for w in words if w.startswith("#")]
    return " ".join(tags[:5]) if tags else " ".join(words)

def claude_bin():
    return cfg.claude_bin()


def safe(iid):
    return bool(iid) and re.fullmatch(r"[\w-]{1,80}", iid) is not None and (IDEAS / iid).is_dir()


LOCK = threading.Lock()          # همه‌ی نوشتن‌های reel.json از این قفل رد می‌شوند


def load(iid):
    f = IDEAS / iid / "reel.json"
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        return None


def _write(iid, reel):
    reel["updated"] = time.strftime("%Y-%m-%d %H:%M")
    d = IDEAS / iid
    (d / "reel.json").write_text(json.dumps(reel, ensure_ascii=False, indent=2), encoding="utf-8")
    (d / "reel.md").write_text(render_md(reel), encoding="utf-8")


def final_text(reel):
    hooks = reel.get("hooks") or []
    pick = reel.get("pick") or 0
    hook = hooks[pick] if 0 <= pick < len(hooks) else (hooks[0] if hooks else "")
    return "\n\n".join(x.strip() for x in (hook, reel.get("body", ""), reel.get("cta", "")) if x and x.strip())


def render_md(reel):
    hooks = reel.get("hooks") or []
    pick = reel.get("pick") or 0
    hl = "\n".join(f"{i + 1}. {h}{'  ← انتخاب‌شده' if i == pick else ''}" for i, h in enumerate(hooks))
    parts = [f"# 🎬 {reel.get('title') or 'ریلز'}"]
    if reel.get("note"):
        parts.append(reel["note"])
    parts += ["## هوک‌ها", hl, "## بدنه", reel.get("body", ""), "## کال‌تو‌اکشن", reel.get("cta", ""),
              "## کپشن", reel.get("caption", ""), "## هشتگ‌ها", reel.get("hashtags", ""),
              "---", "## متن آماده‌ی ضبط", final_text(reel)]
    return "\n\n".join(p for p in parts if p is not None) + "\n"


def _between(text, a, b):
    """متن بین دو نشانه؛ اگر نشانه نبود همه‌ی متن."""
    text = text or ""
    i = text.find(a)
    if i < 0:
        return text.strip()
    j = text.find(b, i + len(a))
    return text[i + len(a): j if j >= 0 else None].strip()


def _clean_hook(h):
    h = h.strip()
    if len(h) > 2 and h[0] in "«\"“" and h[-1] in "»\"”":
        h = h[1:-1].strip()
    return h


def parse_hooks(text):
    out = []
    for ln in (text or "").splitlines():
        m = re.match(r"^\s*(?:[-*•]|[0-9۰-۹]+\s*[.)\-–:])\s*(.+)$", ln)
        if m and m.group(1).strip():
            out.append(_clean_hook(m.group(1)))
        elif ln.strip() and out:                 # ادامه‌ی هوک قبلی در خط بعد
            out[-1] = (out[-1] + " " + ln.strip()).strip()
    if not out and (text or "").strip():
        out = [_clean_hook(x) for x in re.split(r"\n\s*\n", text.strip()) if x.strip()]
    return [h for h in out if h][:10]


def _key(head):
    h = head.replace("‌", "").replace(" ", "")
    for k, words in (("title", ("تایتل", "عنوان")), ("hooks", ("هوک",)), ("body", ("بدنه", "متناصلی")),
                     ("cta", ("کال", "CTA", "cta", "دعوت")), ("caption", ("کپشن",)),
                     ("hashtags", ("هشتگ",)), ("note", ("یادداشت",))):
        if any(w in h for w in words):
            return k
    return None


def parse_produced(stdout):
    """خروجی ساخت ریلز ← dict؛ اگر هوک یا بدنه نبود None."""
    text = _between(stdout, "<<<REEL", "REEL>>>")
    secs, cur, buf = {}, None, []
    for ln in text.splitlines():
        m = re.match(r"^\s*##\s+(.+?)\s*$", ln)
        if m and _key(m.group(1)):
            if cur:
                secs[cur] = "\n".join(buf).strip()
            cur, buf = _key(m.group(1)), []
        elif cur:
            buf.append(ln)
    if cur:
        secs[cur] = "\n".join(buf).strip()
    hooks = parse_hooks(secs.get("hooks", ""))
    if not hooks or not secs.get("body"):
        return None
    return {"v": 1, "title": secs.get("title", "").strip().strip("«»\""), "hooks": hooks, "pick": 0,
            "body": secs["body"], "cta": secs.get("cta", ""), "caption": secs.get("caption", ""),
            "hashtags": five_tags(secs.get("hashtags", "")), "note": secs.get("note", ""),
            "prev": {}, "notes": {}}


def _ask(prompt, timeout, model, web=False):
    # پرامپت از stdin می‌رود: خط فرمان ویندوز حداکثر ۳۲ هزار حرف جا دارد
    cmd = [claude_bin(), "-p", "--output-format", "json", "--model", model]
    if web:
        cmd += ["--allowedTools", "WebSearch", "WebFetch"]
    r = subprocess.run(cmd, input=prompt, cwd=str(ROOT), capture_output=True, text=True, timeout=timeout)
    try:
        out = json.loads(r.stdout)
    except Exception:
        out = {}
    return r.returncode, (out.get("result") or "").strip(), (r.stderr or "")[-300:]


# ---------------- ساخت اول (از run_idea_step در server.py) ----------------
def produce(iid, log, model=None):
    """ریلز تازه می‌سازد. (ok, پیام خطا)"""
    model = model or am.get("produce")
    log(f"▸ مدل: {am.CHOICES.get(model, model)} — Claude دارد ریلز را بخش‌به‌بخش می‌نویسد…")
    code, res, err = _ask(PRODUCE_PROMPT.replace("ID", iid), 3600, model)
    if code != 0 or not res:
        if err:
            log(err)
        return False, "اجرا ناتمام ماند."
    reel = parse_produced(res)
    if not reel:
        (IDEAS / iid / "reel.last-output.txt").write_text(res, encoding="utf-8")
        return False, "خروجی قالب درستی نداشت (فایل reel.last-output.txt را ببین)."
    with LOCK:
        for name in ("reel.json", "reel.md"):    # ریلز قبلی (با ویرایش‌هایش، یا قالب قدیمی) دور ریخته نمی‌شود
            if (IDEAS / iid / name).exists():
                shutil.copy(IDEAS / iid / name, IDEAS / iid / name.replace("reel.", "reel.prev."))
        _write(iid, reel)
    log(f"▸ {len(reel['hooks'])} هوک، بدنه، کال‌تو‌اکشن، کپشن و هشتگ‌ها ساخته شد")
    return True, ""


# ---------------- بازتولید یک بخش ----------------
RJOBS = {}                       # (id, field) → {"state", "error"}
RJLOCK = threading.Lock()


def _section_text(reel, field):
    if field == "hooks":
        pick = reel.get("pick") or 0
        return "\n".join(f"{i + 1}. {h}{'   (انتخاب فعلی کاربر)' if i == pick else ''}"
                         for i, h in enumerate(reel.get("hooks") or []))
    return reel.get(field, "")


def _note_block(note, history):
    lines = []
    if note:
        lines.append("نظر کاربر برای این بازنویسی — مهم‌ترین ورودی است، دقیقاً اجرایش کن:\n<<<NOTE\n"
                     + note + "\nNOTE>>>")
    else:
        lines.append("کاربر نظر خاصی ننوشته؛ یک نسخه‌ی تازه و بهتر بنویس که با نسخه‌ی فعلی فرق واقعی داشته باشد.")
    if history:
        lines.append("نظرهای قبلی کاربر درباره‌ی همین بخش (برای اینکه خواسته‌های قبلی‌اش گم نشود):\n"
                     + "\n".join(f"- {h['t']}" for h in history[-4:]))
    return "\n\n".join(lines)


def _regen(iid, field, note):
    try:
        reel = load(iid) or {}
        prompt = (REGEN_PROMPT.replace("ID", iid)
                  .replace("CURRENT_MD", render_md(reel))
                  .replace("SEC_LABEL", LABEL[field])
                  .replace("SEC_TEXT", _section_text(reel, field) or "(خالی)")
                  .replace("NOTE_BLOCK", _note_block(note, (reel.get("notes") or {}).get(field, [])))
                  .replace("SEC_RULES", RULES[field]
                           + ("\nاگر نظر کاربر درباره‌ی یک هوک مشخص است، ترتیب را حفظ کن تا آن هوک سر جای خودش بماند."
                              if field == "hooks" else "")))
        code, res, err = _ask(prompt, 1500, am.get("regen"), web=True)
        text = _between(res, "<<<OUT", "OUT>>>") if res else ""
        value = parse_hooks(text) if field == "hooks" else text.strip()
        if field == "hashtags":
            value = five_tags(value)
        if field == "title":
            value = value.strip("«»\"")
        if code != 0 or not value:
            with RJLOCK:
                RJOBS[(iid, field)] = {"state": "error", "error": "بازتولید ناتمام ماند." + (f" {err}" if err else "")}
            return
        with LOCK:
            cur = load(iid) or reel
            cur.setdefault("prev", {})[field] = cur.get(field)
            if field == "hooks":
                cur["prev"]["pick"] = cur.get("pick", 0)
                cur["pick"] = min(cur.get("pick", 0), len(value) - 1)
            cur[field] = value
            if note:
                cur.setdefault("notes", {}).setdefault(field, []).append(
                    {"t": note, "at": time.strftime("%Y-%m-%d %H:%M")})
            _write(iid, cur)
        with RJLOCK:
            RJOBS[(iid, field)] = {"state": "done", "error": ""}
    except subprocess.TimeoutExpired:
        with RJLOCK:
            RJOBS[(iid, field)] = {"state": "error", "error": "زمان بازتولید تمام شد."}
    except Exception as e:
        with RJLOCK:
            RJOBS[(iid, field)] = {"state": "error", "error": f"خطا: {e}"}


# ---------------- مسیرهای HTTP ----------------
def handle_get(p, q):
    if p == "/api/idea/reel":
        iid = q.get("id", [""])[0]
        if not safe(iid):
            return 400, {"error": "bad request"}
        with RJLOCK:
            jobs = {f: dict(j) for (i, f), j in RJOBS.items() if i == iid}
        return 200, {"reel": load(iid), "jobs": jobs}
    return None


def handle_post(p, body):
    iid, field = body.get("id", ""), body.get("field", "")
    if p == "/api/idea/reel/save":
        if not safe(iid) or field not in FIELDS + ["pick"]:
            return 400, {"error": "bad request"}
        v = body.get("value")
        if field == "hooks":
            if not isinstance(v, list):
                return 400, {"error": "bad value"}
            v = [str(x) for x in v][:12]
        elif field == "pick":
            if not isinstance(v, int):
                return 400, {"error": "bad value"}
        else:
            v = str(v or "")
        with LOCK:
            reel = load(iid)
            if reel is None:
                return 404, {"error": "این ایده هنوز ریلز ندارد."}
            with RJLOCK:
                busy = RJOBS.get((iid, field if field != "pick" else "hooks"), {}).get("state") == "running"
            if busy:
                return 409, {"error": "این بخش در حال بازتولید است."}
            reel[field] = v
            if field == "hooks":
                reel["pick"] = min(reel.get("pick", 0), max(len(v) - 1, 0))
            _write(iid, reel)
        return 200, {"ok": True, "updated": reel["updated"]}

    if p == "/api/idea/reel/regen":
        if not safe(iid) or field not in FIELDS or load(iid) is None:
            return 400, {"error": "bad request"}
        note = str(body.get("note") or "").strip()[:4000]
        with RJLOCK:
            if RJOBS.get((iid, field), {}).get("state") == "running":
                return 409, {"error": "همین بخش در حال بازتولید است."}
            RJOBS[(iid, field)] = {"state": "running", "error": ""}
        threading.Thread(target=_regen, args=(iid, field, note), daemon=True).start()
        return 200, {"ok": True}

    if p == "/api/idea/reel/undo":
        if not safe(iid) or field not in FIELDS:
            return 400, {"error": "bad request"}
        with LOCK:
            reel = load(iid)
            prev = (reel or {}).get("prev", {})
            if not reel or prev.get(field) is None:
                return 404, {"error": "نسخه‌ی قبلی نیست."}
            # جابه‌جا می‌کند: دوباره زدن، برمی‌گرداند به نسخه‌ی بازتولیدشده
            reel[field], prev[field] = prev[field], reel[field]
            if field == "hooks" and "pick" in prev:
                reel["pick"], prev["pick"] = prev["pick"], reel.get("pick", 0)
            _write(iid, reel)
        return 200, {"ok": True}
    return None
