"""تدوین ویدیو — فاز ۳: عکس و ویدیوی خود کاربر، گرافیک خودکار (لوگو، قیمت، شمارنده، جمع، نقل‌قول) و لوگوی سرویس‌ها.
موتور اصلی video_engine.py است؛ مسیرها و کارها video.py.

data/videos/<id>/
  media.json          فهرست عکس‌ها و ویدیوهای کاربر: توضیح کاربر (note)، تحلیل Claude (an)، جعبه‌های محو/هایلایت/زوم (boxes)
  media/<mid>/        orig.<ext> · src.jpg|png (عکس استاندارد تا ۲۴۰۰px) · view.jpg (۱۲۰۰px، رابط و Claude) · thumb.jpg · ocr.json ·
                      clip.mp4 + prev.mp4 (ویدیو) · out.* (با محوها؛ همین در ویدیو می‌آید) · cut.png (سوژه بدون پس‌زمینه)
  edit.json → vis     جای هر تصویر روی کلمه‌ها (w0..w1)، مثل بقیه‌ی تصمیم‌ها؛ با برش‌ها جابه‌جا نمی‌شود
data/videos/logos/    لوگوی سرویس‌ها (کش مشترک همه‌ی پروژه‌ها) + logos.json

- همه‌ی جعبه‌ها کسری از عرض و ارتفاع تصویرند، مبدأ بالا-چپ: [x, y, w, h].
- متن تصویر را Vision خود macOS می‌خواند (modules/video/bin/mediatool، از mediatool.swift خودکار ساخته می‌شود)؛
  Claude خود تصویر را می‌بیند (stream-json، بدون هیچ ابزاری؛ Read هرگز) و می‌گوید چه چیزی محو، هایلایت یا بزرگ شود.
- اطلاعات شخصی (ایمیل، اسم و آدرس، شماره‌ی کارت، شماره‌ی فاکتور) خودکار محو می‌شود، حتی اگر کاربر نگفته باشد؛
  اگر Claude جواب ندهد، الگوهای ساده‌ی همین فایل (PII_RE) جایش را می‌گیرند. محو با ffmpeg (pixelize + blur) در خود فایل پخته می‌شود.
"""
import base64, json, math, re, shutil, tempfile, threading, time, urllib.parse, urllib.request
from html import escape
from pathlib import Path
import video_engine as ve
import ai_models as am

MEDIATOOL_SRC = ve.MOD / "mediatool.swift"
MEDIATOOL = ve.MOD / "bin" / "mediatool"
LOGOS = ve.DIR / "logos"
IMG_EXT = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif", ".gif", ".tif", ".tiff", ".bmp"}
VID_EXT = {".mp4", ".mov", ".m4v", ".webm"}
DOC_EXT = {".pdf"}
MEDIA_EXT = IMG_EXT | VID_EXT | DOC_EXT
MAX_MEDIA = 2 * 1024 ** 3
TPL_MEDIA = {"doc": "سند و فاکتور (زوم و هایلایت)", "card": "کارت شناور", "full": "تمام‌صفحه", "top": "نیمه‌ی بالا",
             "polaroid": "پولاروید", "phone": "قاب گوشی", "cutout": "دوربُرش", "scene": "تمام‌صفحه (زمینه‌ی سرمه‌ای)"}
TPL_VIDEO = ("card", "full", "top", "phone", "polaroid", "scene")  # برای ویدیو: سند و دوربُرش نه
TPL_GFX = {"logo": "کارت لوگو و قیمت", "price": "قیمت", "counter": "شمارنده‌ی فهرست", "total": "جمع", "quote": "نقل‌قول"}
POS = {"auto": "خودکار", "top": "بالا", "mid": "وسط", "bot": "پایین"}
VSIZE = {"s": 0.82, "m": 1.0, "l": 1.15}
VSIZE_FA = {"s": "کوچک", "m": "معمولی", "l": "بزرگ"}
GFX_FIELDS = {"logo": ("name", "domain", "price", "cur", "per", "stamp", "strike"), "price": ("value", "cur", "per", "strike"),
              "counter": ("n", "of"), "total": ("value", "cur", "label"), "quote": ("text", "by")}
# افکت ورود هر قالب (اگر افکت دیگری تا ۰٫۶ ثانیه‌اش نباشد)؛ کلید کتابخانه‌ی modules/video/sfx
TPL_SFX = {"doc": "page", "card": "swipe", "full": "whoosh", "top": "whoosh", "scene": "whoosh", "polaroid": "shutter", "phone": "pop-soft",
           "cutout": "pop", "logo": "pop-soft", "price": "coin", "total": "coin-win", "quote": "ding"}
LEAD = 0.08                      # تصویر کمی پیش از کلمه‌اش می‌آید
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0 Safari/537.36"
FA_DIG = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def fa_num(s):
    return str(s if s is not None else "").translate(FA_DIG)


# ---------------- فهرست رسانه‌ها (media.json) ----------------
def mfile(vid):
    return ve.pdir(vid) / "media.json"


def mdir(vid, mid):
    return ve.pdir(vid) / "media" / mid


def mlist(vid):
    return list(ve.jload(mfile(vid), {}).get("items") or [])


def msave(vid, items):
    ve.jsave(mfile(vid), {"items": items})


def mget(vid, mid):
    return next((m for m in mlist(vid) if m.get("id") == mid), None)


def mupdate(vid, mid, **kw):
    with ve.plock(vid):
        items = mlist(vid)
        for m in items:
            if m.get("id") == mid:
                m.update(kw)
                msave(vid, items)
                return dict(m)
    return None


def media_add(vid, name, ext):
    """پوشه و ردیف تازه؛ فایل را handle_upload در orig.<ext> می‌ریزد."""
    mid = "m" + str(int(time.time() * 1000))
    mdir(vid, mid).mkdir(parents=True, exist_ok=True)
    kind = "video" if ext in VID_EXT else "pdf" if ext in DOC_EXT else "image"
    with ve.plock(vid):
        items = mlist(vid)
        items.append({"id": mid, "name": name[:160], "ext": ext, "type": "video" if kind == "video" else "image", "src": kind,
                      "status": "upload", "note": "", "rev": 0, "boxes": {"blur": [], "hl": [], "focus": None},
                      "boxesBy": "claude", "created": ve.now()})
        msave(vid, items)
    return mid


def media_delete(vid, mid):
    """به سطل پروژه می‌رود؛ جای آن در vis و افکت‌های وابسته هم پاک می‌شود."""
    with ve.plock(vid):
        msave(vid, [m for m in mlist(vid) if m.get("id") != mid])
        e = ve.jload(ve.pdir(vid) / "edit.json", {})
        gone = {v["id"] for v in e.get("vis") or [] if v.get("mid") == mid}
        if gone:
            e["vis"] = [v for v in e.get("vis") or [] if v["id"] not in gone]
            e["sfx"] = [x for x in e.get("sfx") or [] if x.get("link") not in gone]
            ve.jsave(ve.pdir(vid) / "edit.json", e)
    src = mdir(vid, mid)
    if src.exists():
        trash = ve.pdir(vid) / "media" / ".trash"
        trash.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(trash / f"{mid}-{int(time.time())}"))


# ---------------- ابزار Swift ----------------
def ensure_mediatool(vid=None):
    if MEDIATOOL.exists() and MEDIATOOL.stat().st_mtime >= MEDIATOOL_SRC.stat().st_mtime:
        return
    MEDIATOOL.parent.mkdir(parents=True, exist_ok=True)
    ve.run(["swiftc", "-O", "-parse-as-library", "-swift-version", "5", MEDIATOOL_SRC, "-o", MEDIATOOL], vid, timeout=900)


def mtool(*args, vid=None, timeout=300):
    ensure_mediatool(vid)
    out, _ = ve.run([MEDIATOOL, *args], vid, timeout=timeout)
    return json.loads(out.decode("utf-8", "replace").strip() or "{}")


# ---------------- آماده‌سازی ----------------
def _even_scale(maxpx):
    return (f"scale='if(gte(iw,ih),min({maxpx},iw),-2)':'if(gte(iw,ih),-2,min({maxpx},ih))':flags=lanczos")


def ingest_media(vid, mid):
    d = mdir(vid, mid)
    orig = next(iter(sorted(d.glob("orig.*"))), None)
    if not orig:
        raise RuntimeError("فایل پیدا نشد؛ دوباره آپلود کن.")
    ext = orig.suffix.lower()
    if ext in VID_EXT:
        info = ve.probe(orig)
        dur = info["dur"] or 0
        if dur < 0.3:
            raise RuntimeError("ویدیو خیلی کوتاه است.")
        enc = ["-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-an"]
        ve.run([ve.FFMPEG, "-v", "error", "-y", "-i", orig, "-map", "0:v:0", "-vf", _even_scale(1920) + f",fps={ve.FPS}",
                *enc, "-crf", "18", "-g", str(ve.FPS), "-keyint_min", str(ve.FPS), "-sc_threshold", "0", d / "clip.mp4"], vid)
        ve.run([ve.FFMPEG, "-v", "error", "-y", "-i", d / "clip.mp4", "-vf", _even_scale(640), *enc, "-crf", "30", "-g", "10",
                d / "prev.mp4"], vid)
        for k, f in enumerate((0.15, 0.5, 0.85), 1):
            ve.run([ve.FFMPEG, "-v", "error", "-y", "-ss", f"{dur * f:.2f}", "-i", d / "clip.mp4", "-frames:v", "1",
                    "-vf", _even_scale(1024), "-q:v", "3", d / f"f{k}.jpg"], vid)
        ve.run([ve.FFMPEG, "-v", "error", "-y", "-ss", f"{dur * 0.3:.2f}", "-i", d / "clip.mp4", "-frames:v", "1",
                "-vf", _even_scale(1200), "-q:v", "3", d / "view.jpg"], vid)
        ve.run([ve.FFMPEG, "-v", "error", "-y", "-i", d / "view.jpg", "-vf", _even_scale(320), "-q:v", "4", d / "thumb.jpg"], vid)
        p = ve.probe(d / "clip.mp4")
        ocr = mtool("ocr", d / "view.jpg", vid=vid)
        ve.jsave(d / "ocr.json", ocr)
        mupdate(vid, mid, type="video", w=p["w"], h=p["h"], dur=round(p["dur"], 3), ocrN=len(ocr.get("lines") or []))
        return
    if ext in DOC_EXT:
        r = mtool("pdf", orig, d / "src.png", "2400", vid=vid)
        src, extra = d / "src.png", {"pages": r.get("pages", 1)}
    elif ext in IMG_EXT:
        src = d / ("src.png" if ext in (".png", ".webp", ".gif", ".tif", ".tiff", ".bmp") else "src.jpg")
        r = mtool("norm", orig, src, "2400", vid=vid)
        extra = {"alpha": bool(r.get("alpha"))}
    else:
        raise RuntimeError("این نوع فایل پشتیبانی نمی‌شود.")
    mtool("norm", src, d / "view.jpg", "1200", vid=vid)
    mtool("norm", src, d / "thumb.jpg", "320", vid=vid)
    ocr = mtool("ocr", src, vid=vid, timeout=600)
    ve.jsave(d / "ocr.json", ocr)
    faces = mtool("faces", src, vid=vid).get("faces") or []
    mupdate(vid, mid, type="image", w=r.get("w"), h=r.get("h"), faces=faces, ocrN=len(ocr.get("lines") or []), **extra)


# ---------------- تحلیل با Claude (خود تصویر + خط‌های متن) ----------------
def ask_vision(text, images, vid=None, timeout=900, effort="medium"):
    """claude -p با تصویر: پیام stream-json با بلوک‌های image (base64)؛ هیچ ابزاری روشن نیست (--tools "")."""
    content = []
    for f in images:
        mt = "image/png" if str(f).lower().endswith(".png") else "image/jpeg"
        content.append({"type": "image", "source": {"type": "base64", "media_type": mt,
                                                    "data": base64.b64encode(Path(f).read_bytes()).decode()}})
    content.append({"type": "text", "text": text})
    msg = {"type": "user", "message": {"role": "user", "content": content}}
    cmd = [ve.claude_bin(), "-p", "--input-format", "stream-json", "--output-format", "stream-json", "--verbose",
           "--model", am.get("video"), "--no-session-persistence", "--safe-mode", "--tools", ""]
    if effort:
        cmd += ["--effort", effort]
    out, _ = ve.run(cmd, vid, timeout=timeout, input=(json.dumps(msg) + "\n").encode("utf-8"), cwd=tempfile.gettempdir())
    for line in reversed(out.decode("utf-8", "replace").splitlines()):
        try:
            j = json.loads(line)
        except Exception:
            continue
        if j.get("type") == "result":
            return (j.get("result") or "").strip()
    return ""


AN_RULES = """کار تو، خروجی فقط JSON:
- label: اسم کوتاه فارسی برای این تصویر (حداکثر ۵ کلمه)، مثل «فاکتور ManyChat» یا «اسکرین‌شات داشبورد Canva».
- desc: یک جمله‌ی فارسی ساده: این چیست.
- kind: invoice | screenshot | photo | logo | chart | document | other
- blur: هر اطلاعات شخصی را محو کن، حتی اگر کاربر نگفته: ایمیل، اسم و آدرس شخص، شماره‌ی تلفن، شماره‌ی کارت یا حساب (حتی ۴ رقم آخر)، شماره‌ی فاکتور، سفارش یا مشتری، و هر چیزی که کاربر گفته محو شود. اسم شرکت یا سرویس، مبلغ و تاریخ را محو نکن، مگر کاربر بخواهد.
  هر مورد یکی از این‌ها: {"l": شماره‌ی خط} برای کل خط؛ {"l": شماره‌ی خط، "text": "همان بخش از متن خط"} اگر فقط بخشی از خط شخصی است (مثلاً فقط ایمیل در «Billed to: x@y.com»)؛ {"box": [x,y,w,h]} برای جایی که متن نیست (مثل صورت آدم دیگر).
- hl: آن‌چه باید در ویدیو هایلایت شود (مثل مبلغ کل یا قیمت)، یا هر چه کاربر گفته؛ همان قالب. کم: معمولاً ۱ یا ۲ مورد.
- focus: [x,y,w,h] بخشی از تصویر که مهم است و ویدیو رویش زوم می‌کند (مثلاً دور اسم سرویس و مبلغ)، یا null یعنی کل تصویر.
- tpl: بهترین قالب برای این تصویر: doc (سند، فاکتور یا رسید: اول کل سند، بعد زوم و هایلایت)، card (کارت شناور)، full (تمام‌صفحه)، top (نیمه‌ی بالای کادر)، polaroid (عکس یادگاری)، phone (اسکرین‌شات گوشی)، cutout (فقط عکس آدم یا شیء: سوژه بدون پس‌زمینه).
- keywords: کلمه‌ها، اسم‌ها یا عددهایی که اگر در صحبت ویدیو بیایند، لحظه‌ی نشان دادن این تصویر است (مثل "ManyChat" و "۱۷۳").
- when: اگر کاربر گفته کی نشان داده شود، خلاصه‌اش به فارسی؛ وگرنه "".
- trim: فقط برای ویدیو: [شروع، پایان] به ثانیه برای بخشی که باید نشان داده شود، یا null یعنی کل ویدیو.
- rtl: true اگر متن اصلی تصویر فارسی یا عربی است.
توضیح کاربر مهم‌ترین دستور است."""


def _norm_txt(s):
    return re.sub(r"[^\w@.$€£%]+", "", (s or "").lower())


def _box_for(lines, li, text, W, H):
    """جعبه‌ی یک خط یا فقط کلمه‌هایی از آن که با text جورند؛ با حاشیه تا لبه‌ی حروف هم پوشیده شود."""
    if not 0 <= li < len(lines):
        return None
    ln = lines[li]
    b = ln["b"]
    if text:
        ws, want = ln.get("w") or [], _norm_txt(text)
        best = None
        for i in range(len(ws)):
            acc = ""
            for j in range(i, len(ws)):
                acc += _norm_txt(ws[j]["t"])
                if acc == want or (want and want in acc and len(acc) <= len(want) + 4):
                    best = (i, j)
                    break
                if len(acc) > len(want) + 4:
                    break
            if best:
                break
        if best:
            bs = [ws[k]["b"] for k in range(best[0], best[1] + 1)]
            x0, y0 = min(q[0] for q in bs), min(q[1] for q in bs)
            x1, y1 = max(q[0] + q[2] for q in bs), max(q[1] + q[3] for q in bs)
            b = [x0, y0, x1 - x0, y1 - y0]
    return _pad(b, W, H)


def _pad(b, W, H, k=0.35):
    x, y, w, h = b
    ph = h * k
    pw = h * H / max(1, W) * 0.6
    return _clip([x - pw, y - ph, w + 2 * pw, h + 2 * ph])


def _clip(b):
    x, y, w, h = (float(v) for v in b)
    x0, y0, x1, y1 = max(0.0, x), max(0.0, y), min(1.0, x + w), min(1.0, y + h)
    return [round(x0, 4), round(y0, 4), round(max(0.0, x1 - x0), 4), round(max(0.0, y1 - y0), 4)]


def _union(bs, pad=0.0):
    bs = [b for b in bs if b]
    if not bs:
        return None
    x0, y0 = min(b[0] for b in bs), min(b[1] for b in bs)
    x1, y1 = max(b[0] + b[2] for b in bs), max(b[1] + b[3] for b in bs)
    return _clip([x0 - pad, y0 - pad, x1 - x0 + 2 * pad, y1 - y0 + 2 * pad])


PII_RE = [re.compile(p, re.I) for p in (
    r"[\w.+-]+@[\w-]+\.[\w.]+",                                     # ایمیل
    r"(visa|mastercard|amex|card|ending in|•{2,}|\*{2,})\D{0,12}\d{4}",  # کارت
    r"\+?\d[\d\s().-]{8,}\d",                                       # تلفن یا شماره‌ی بلند
    r"(invoice|receipt|order|customer|account)\s*(no\.?|number|#|id)\s*[:#]?\s*[\w-]{4,}")]


def _fallback_blur(lines):
    """وقتی Claude جواب نداد: الگوهای ساده (ایمیل، کارت، تلفن، شماره‌ی فاکتور) — بهتر از هیچ."""
    return [{"l": i} for i, ln in enumerate(lines) if any(r.search(ln.get("t") or "") for r in PII_RE)]


def analyze_media(vid, mid):
    m, d = mget(vid, mid), mdir(vid, mid)
    ocr = ve.jload(d / "ocr.json", {})
    lines = ocr.get("lines") or []
    W, H = m.get("w") or 1000, m.get("h") or 1000
    rows = [f"L{i}|{ln['t']}|{','.join(f'{v:.3f}' for v in ln['b'])}" for i, ln in enumerate(lines[:220])]
    is_vid = m.get("type") == "video"
    parts = [f"تو دستیار تدوین ویدیوهای کوتاه فارسی هستی. کاربر این {'ویدیو' if is_vid else 'تصویر'} را فرستاده تا در ویدیویش بیاید."
             + (f" طولش {m.get('dur', 0):.1f} ثانیه است؛ سه فریم از ۱۵٪، ۵۰٪ و ۸۵٪ آن را می‌بینی." if is_vid else ""),
             "توضیح کاربر زیر آن: «" + ((m.get("note") or "").strip() or "توضیحی ننوشته") + "»",
             f"اسم فایل: {m.get('name', '')}",
             "خط‌های متنی که Vision در " + ("فریم وسط" if is_vid else "تصویر") + " پیدا کرده (قالب: L<شماره>|متن|x,y,w,h کسری از عرض و ارتفاع، مبدأ بالا-چپ):\n"
             + ("\n".join(rows) or "(متنی پیدا نشد)"),
             AN_RULES,
             "قالب خروجی، بین دو نشانه:\n<<<AN\n"
             '{"label": "", "desc": "", "kind": "invoice", "blur": [{"l": 3}, {"l": 8, "text": "x@y.com"}], "hl": [{"l": 14}], '
             '"focus": [0.1, 0.4, 0.8, 0.2], "tpl": "doc", "keywords": [], "when": "", "trim": null, "rtl": false}\nAN>>>']
    imgs = [d / f"f{k}.jpg" for k in (1, 2, 3)] if is_vid else [d / "view.jpg"]
    data = None
    try:
        res = ask_vision("\n\n".join(parts), [f for f in imgs if f.exists()], vid)
        data = ve.json_block(res, "<<<AN", "AN>>>")
        if not data:
            (d / "an.last-output.txt").write_text(res or "", encoding="utf-8")
    except Exception as e:
        (d / "an.last-output.txt").write_text(str(e)[:2000], encoding="utf-8")
    fallback = data is None
    data = data or {"label": Path(m.get("name") or "تصویر").stem[:40], "desc": "", "kind": "other",
                    "blur": _fallback_blur(lines), "hl": [], "focus": None,
                    "tpl": "card" if is_vid else ("doc" if len(lines) > 6 else "card")}

    def boxes(key):
        out = []
        for it in data.get(key) or []:
            if isinstance(it, dict) and "l" in it:
                try:
                    b = _box_for(lines, int(it["l"]), str(it.get("text") or ""), W, H)
                except Exception:
                    b = None
            elif isinstance(it, dict) and isinstance(it.get("box"), list) and len(it["box"]) == 4:
                b = _clip(it["box"])
            else:
                b = None
            if b and b[2] > 0.002 and b[3] > 0.002:
                out.append(b)
        return out

    blur, hl = boxes("blur"), boxes("hl")
    focus = data.get("focus")
    focus = _clip(focus) if isinstance(focus, list) and len(focus) == 4 else None
    if not focus and hl:
        focus = _union(hl, 0.06)
    tpls = TPL_VIDEO if is_vid else tuple(TPL_MEDIA)
    tpl = data.get("tpl") if data.get("tpl") in tpls else ("card" if is_vid else "doc" if len(lines) > 6 else "card")
    trim = data.get("trim")
    dur = m.get("dur") or 0
    if is_vid and isinstance(trim, list) and len(trim) == 2:
        try:
            a, b = max(0.0, float(trim[0])), min(dur, float(trim[1]))
            trim = [round(a, 2), round(b, 2)] if b - a >= 0.8 else None
        except Exception:
            trim = None
    else:
        trim = None
    an = {"label": str(data.get("label") or "")[:60], "desc": str(data.get("desc") or "")[:300],
          "kind": str(data.get("kind") or "other")[:20], "tpl": tpl, "trim": trim, "rtl": bool(data.get("rtl")),
          "keywords": [str(k)[:40] for k in (data.get("keywords") or [])][:12], "when": str(data.get("when") or "")[:200],
          "at": ve.now(), "fallback": fallback}
    return an, {"blur": blur, "hl": hl, "focus": focus}


# ---------------- محو (پخته در فایل) ----------------
def _redact_graph(boxes, W, H):
    n = len(boxes)
    g = f"[0:v]split={n + 1}[b0]" + "".join(f"[c{i}]" for i in range(n)) + ";"
    for i, (x, y, w, h) in enumerate(boxes):
        X, Y = max(0, int(x * W)), max(0, int(y * H))
        BW, BH = max(4, min(W - X, int(math.ceil(w * W)))), max(4, min(H - Y, int(math.ceil(h * H))))
        X, Y, BW, BH = X - X % 2, Y - Y % 2, BW - BW % 2, BH - BH % 2
        blk = max(6, min(64, BH // 2))
        g += (f"[c{i}]crop={BW}:{BH}:{X}:{Y},pixelize=width={blk}:height={blk},boxblur={max(2, blk // 3)}:1[p{i}];"
              f"[b{i}][p{i}]overlay={X}:{Y}[b{i + 1}];")
    return g.rstrip(";"), f"[b{n}]"


def process_media(vid, mid):
    """فایل‌هایی که در ویدیو می‌آیند، با محوهای پخته: out.jpg|png (عکس) یا out.mp4 + outp.mp4 (ویدیو و نسخه‌ی سبکش)."""
    m, d = mget(vid, mid), mdir(vid, mid)
    blur = (m.get("boxes") or {}).get("blur") or []
    if m.get("type") == "video":
        pairs = [(d / "clip.mp4", d / "out.mp4", "18", str(ve.FPS)), (d / "prev.mp4", d / "outp.mp4", "30", "10")]
        for src, dst, crf, g in pairs:
            if not blur:
                shutil.copy2(src, dst)
                continue
            p = ve.probe(src)
            graph, last = _redact_graph(blur, p["w"], p["h"])
            ve.run([ve.FFMPEG, "-v", "error", "-y", "-i", src, "-filter_complex", graph, "-map", last, "-an", "-c:v", "libx264",
                    "-preset", "veryfast", "-crf", crf, "-g", g, "-pix_fmt", "yuv420p", "-movflags", "+faststart", dst], vid)
        return
    src = next((f for f in (d / "src.png", d / "src.jpg") if f.exists()), None)
    if not src:
        raise RuntimeError("تصویر آماده نیست.")
    dst = d / ("out.png" if src.suffix == ".png" else "out.jpg")
    for old in d.glob("out.*"):
        if old != dst:
            old.unlink()
    if not blur:
        shutil.copy2(src, dst)
    else:
        graph, last = _redact_graph(blur, m.get("w") or 1000, m.get("h") or 1000)
        ve.run([ve.FFMPEG, "-v", "error", "-y", "-i", src, "-filter_complex", graph, "-map", last, "-frames:v", "1",
                *(["-q:v", "2"] if dst.suffix == ".jpg" else []), dst], vid)
    (d / "cut.png").unlink(missing_ok=True)      # دوربُرش از روی نسخه‌ی محوشده دوباره ساخته می‌شود


def media_out(vid, mid, preview=False):
    d = mdir(vid, mid)
    for f in ((d / "outp.mp4",) if preview else ()) + (d / "out.mp4", d / "out.png", d / "out.jpg"):
        if f.exists():
            return f
    return None


def cutout(vid, mid):
    """سوژه بدون پس‌زمینه (Vision)؛ یک بار، از روی عکس محوشده. None اگر سوژه‌ای پیدا نشد."""
    d = mdir(vid, mid)
    src, dst = media_out(vid, mid), d / "cut.png"
    if not src or src.suffix == ".mp4":
        return None
    if not dst.exists() or dst.stat().st_mtime < src.stat().st_mtime:
        try:
            if not mtool("cutout", src, dst, vid=vid, timeout=300).get("ok"):
                return None
        except Exception:
            return None
    return dst


# ---------------- کارگر پس‌زمینه‌ی رسانه‌ها ----------------
_MW, _MWL = {}, threading.Lock()
WORK = ("queued", "analyze", "process")


def media_kick(vid, on_change=None):
    """یک thread برای هر پروژه؛ ردیف‌های queued/analyze/process را یکی‌یکی جلو می‌برد. on_change بعد از هر ردیف."""
    with _MWL:
        t = _MW.get(vid)
        if t and t.is_alive():
            return
        t = threading.Thread(target=_media_worker, args=(vid, on_change), daemon=True)
        _MW[vid] = t
        t.start()


def media_busy(vid):
    with _MWL:
        t = _MW.get(vid)
        return bool(t and t.is_alive())


def _media_worker(vid, on_change):
    """rev با هر ویرایش توضیح و boxesRev با هر ویرایش دستی جعبه‌ها بالا می‌رود؛ اگر وسط کار عوض شدند، همان ردیف دوباره می‌رود."""
    while True:
        m = next((x for x in mlist(vid) if x.get("status") in WORK), None)
        if not m:
            return
        mid, st, rev, brev = m["id"], m["status"], m.get("rev", 0), m.get("boxesRev", 0)
        try:
            if st == "queued":
                mupdate(vid, mid, step="آماده‌سازی…")
                ingest_media(vid, mid)
            if st in ("queued", "analyze"):
                mupdate(vid, mid, step="Claude دارد تصویر و توضیحت را می‌خواند…")
                an, boxes = analyze_media(vid, mid)
                with ve.plock(vid):
                    cur = mget(vid, mid) or {}
                    kw = {"an": an, "anRev": rev}
                    if cur.get("boxesBy") != "user":
                        kw["boxes"] = boxes
                    mupdate(vid, mid, **kw)
            mupdate(vid, mid, step="محو کردن اطلاعات شخصی…")
            process_media(vid, mid)
            with ve.plock(vid):
                cur = mget(vid, mid)
                if cur is not None:
                    nxt = ("analyze" if cur.get("rev", 0) != rev else "process" if cur.get("boxesRev", 0) != brev else "ready")
                    mupdate(vid, mid, status=nxt, step="", err="")
        except Exception as e:
            mupdate(vid, mid, status="error", step="", err=str(e)[:400])
        if on_change:
            try:
                on_change(vid, mid)
            except Exception:
                pass


# ---------------- لوگوی سرویس‌ها ----------------
_LOGO_L = threading.Lock()


def _domain(s):
    s = (s or "").strip().lower()
    s = re.sub(r"^[a-z]+://", "", s).split("/")[0].split("?")[0]
    s = re.sub(r"^www\.", "", s)
    return s if re.fullmatch(r"[a-z0-9-]+(\.[a-z0-9-]+)+", s) else ""


def _get(url, limit=3_000_000, timeout=15):
    r = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*", "Accept-Language": "en-US,en;q=0.9"})
    with urllib.request.urlopen(r, timeout=timeout) as resp:
        return resp.geturl(), (resp.headers.get("Content-Type") or "").lower(), resp.read(limit)


def _img_px(data, ctype, url):
    """اندازه‌ی تقریبی: SVG بی‌نهایت؛ PNG از سرآیند؛ بقیه از sips."""
    if "svg" in ctype or url.lower().split("?")[0].endswith(".svg"):
        return 10_000 if b"<svg" in data[:2000].lower() else 0
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return min(int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big"))
    with tempfile.NamedTemporaryFile(suffix=".img", delete=False) as f:
        f.write(data)
        p = f.name
    try:
        o = ve.run(["sips", "-g", "pixelWidth", "-g", "pixelHeight", p])[0].decode()
        n = [int(x) for x in re.findall(r"pixel(?:Width|Height):\s*(\d+)", o)]
        return min(n) if len(n) == 2 else 0
    except Exception:
        return 0
    finally:
        Path(p).unlink(missing_ok=True)


def fetch_logo(domain):
    """لوگوی سایت خود سرویس: آیکن SVG، apple-touch-icon یا آیکن manifest؛ آخر سر سرویس آیکن گوگل. نتیجه در data/videos/logos."""
    dom = _domain(domain)
    if not dom:
        return None
    LOGOS.mkdir(parents=True, exist_ok=True)
    idx_f = LOGOS / "logos.json"
    with _LOGO_L:
        idx = ve.jload(idx_f, {})
        hit = idx.get(dom) or {}
        if hit.get("file") and (LOGOS / hit["file"]).exists():
            return LOGOS / hit["file"]
        if hit.get("fail") and time.time() - hit.get("t", 0) < 86400:
            return None
    cands = []
    try:
        base, ctype, body = _get(f"https://{dom}/", 2_000_000)
        page = body.decode("utf-8", "replace")
        for tag in re.findall(r"<link\b[^>]*>", page, flags=re.I):
            rel = (re.search(r'rel\s*=\s*["\']([^"\']+)', tag, re.I) or [None, ""])[1].lower()
            href = (re.search(r'href\s*=\s*["\']([^"\']+)', tag, re.I) or [None, ""])[1]
            if not href:
                continue
            url = urllib.parse.urljoin(base, href.replace("&amp;", "&"))
            if "manifest" in rel:
                try:
                    _, _, mb = _get(url, 300_000)
                    for ic in (json.loads(mb.decode("utf-8", "replace")).get("icons") or [])[:12]:
                        if ic.get("src"):
                            cands.append(urllib.parse.urljoin(url, ic["src"]))
                except Exception:
                    pass
            elif "icon" in rel and not url.lower().split("?")[0].endswith(".ico"):
                if url.lower().split("?")[0].endswith(".svg"):
                    cands.insert(0, url)
                else:
                    cands.append(url)
    except Exception:
        pass
    cands.append(f"https://www.google.com/s2/favicons?domain={dom}&sz=256")
    best = None
    for url in cands[:14]:
        try:
            final, ctype, data = _get(url, 3_000_000)
        except Exception:
            continue
        px = _img_px(data, ctype, final)
        if px >= 96 and (not best or px > best[0]):
            ext = "svg" if px == 10_000 else "png" if data[:8] == b"\x89PNG\r\n\x1a\n" else "jpg" if data[:3] == b"\xff\xd8\xff" else "webp" if data[8:12] == b"WEBP" else ""
            if ext:
                best = (px, data, ext, final)
        if best and best[0] >= 10_000:
            break
    with _LOGO_L:
        idx = ve.jload(idx_f, {})
        if not best:
            idx[dom] = {"fail": True, "t": time.time()}
            ve.jsave(idx_f, idx)
            return None
        name = re.sub(r"[^a-z0-9]+", "_", dom) + "." + best[2]
        (LOGOS / name).write_bytes(best[1])
        idx[dom] = {"file": name, "src": best[3][:300], "px": best[0], "at": ve.now()}
        ve.jsave(idx_f, idx)
        return LOGOS / name


# ---------------- چیدن با Claude ----------------
VIS_RULES = """دو نوع تصویر روی ویدیو می‌گذاری:
۱) عکس و ویدیوهایی که کاربر فرستاده (فهرست MEDIA). مهم‌ترین‌اند: هر کدام را که به حرفی در ویدیو مربوط است، دقیقاً همان لحظه نشان بده و دستور توضیح کاربر را دقیق رعایت کن (او گفته چه چیزی است و کی و چطور بیاید).
۲) گرافیک خودکار که خودت می‌سازی (kind=gfx):
- logo: کارت لوگوی یک سرویس، اپ یا سایت وقتی اسمش در حرف می‌آید. data = {"name": "ManyChat", "domain": "manychat.com", "price": "۱۷۳", "cur": "دلار", "per": "ماهانه", "strike": true اگر کنسل یا کنار گذاشته شده، "stamp": "کنسل شد" یا ""}؛ price و cur و per اگر قیمتی گفته نشده خالی.
- price: یک قیمت یا مبلغ مهم که به سرویس خاصی وصل نیست. data = {"value": "۱۹", "cur": "دلار کانادا", "per": "ماهانه", "strike": false}
- counter: شمارنده‌ی فهرست وقتی گوینده موردها را می‌شمارد («اولیش»، «دومیش»…). data = {"n": 1, "of": 5}؛ بازه از اولین کلمه‌ی همان مورد تا آخرین کلمه‌اش.
- total: جمع یا نتیجه‌ی عددی. data = {"value": "۳۱۶", "cur": "دلار", "label": "صرفه‌جویی ماهانه"}
- quote: نقل‌قول مهم از یک آدم شناخته‌شده. data = {"text": "متن کوتاه نقل‌قول به فارسی (حداکثر ۱۲۰ حرف)", "by": "سم آلتمن"}
قالب عکس و ویدیوی کاربر (tpl): doc (سند و فاکتور: کل سند، بعد زوم و هایلایت؛ فقط عکس)، card (کارت شناور)، full (تمام‌صفحه)، top (نیمه‌ی بالا)، polaroid (عکس یادگاری)، phone (اسکرین‌شات گوشی)، cutout (سوژه بدون پس‌زمینه؛ فقط عکس آدم یا شیء). معمولاً همان قالب پیشنهادی هر عکس.
قاعده‌ها:
- هر مورد یک بازه‌ی کلمه‌ای دارد: w0 تا w1 (اندیس، هر دو شامل)، از فهرست کلمه‌های بالا. عکس و ویدیوی کاربر حدود ۲٫۵ تا ۶ ثانیه؛ گرافیک ۱٫۵ تا ۴ ثانیه؛ شمارنده تا آخر همان مورد.
- در هر لحظه فقط یک تصویر یا گرافیک اصلی؛ شمارنده می‌تواند هم‌زمان با بقیه باشد. اگر عکس کاربر و گرافیک برای یک لحظه رقیب‌اند، عکس کاربر برنده است (گرافیک را جای دیگری بگذار یا نگذار).
- کم و دقیق: به‌طور میانگین حداکثر یکی در هر ۶ ثانیه (بدون شمارنده). فقط جایی که تصویر چیزی به حرف اضافه می‌کند.
- عددها با رقم فارسی؛ اسم برندها لاتین. domain دامنه‌ی رسمی سرویس است (مثل canva.com).
- هر مورد یک دلیل کوتاه فارسی (why) دارد.
- summary یک جمله به فارسی ساده است، بدون اسم انگلیسی قالب‌ها."""


def vis_prompt(dv, media, comment="", current=None, notes=(), busy=()):
    words, fix, tm = dv["words"], dv["edit"].get("fix") or {}, dv["tmap"]
    rows = []
    for w in words:
        t = ve.disp(words, fix, w["i"]).strip()
        if w["i"] not in dv["cut"] and t:
            rows.append(f"{w['i']}|{t}|{tm.out(w['s']):.1f}")
    kind = "ریلز عمودی (حرف زدن جلوی دوربین)" if dv.get("src_kind", dv["kind"]) == "reel" else "ضبط صفحه‌ی کامپیوتر (آموزش یا دمو)"
    mrows = []
    for m in media:
        an = m.get("an") or {}
        mrows.append(f"- id: {m['id']} | نوع: {'ویدیو ' + format(m.get('dur') or 0, '.0f') + ' ثانیه' if m.get('type') == 'video' else 'عکس'}"
                     f" | برچسب: {an.get('label') or m.get('name')} | چیست: {an.get('desc') or ''}"
                     f" | توضیح کاربر: «{(m.get('note') or '').strip() or '—'}» | کلیدواژه‌ها: {', '.join(an.get('keywords') or [])}"
                     f" | کی: {an.get('when') or '—'} | قالب پیشنهادی: {an.get('tpl') or 'card'}")
    parts = [f"تو کارگردان گرافیک ویدیوهای کوتاه فارسی این برند هستی. ویدیو: {kind}، {tm.dur:.0f} ثانیه بعد از برش.",
             "کلمه‌های ویدیو بعد از برش. قالب هر خط: اندیس|کلمه|زمان در خروجی (ثانیه):\n<<<WORDS\n" + "\n".join(rows) + "\nWORDS>>>",
             "عکس و ویدیوهای کاربر:\n<<<MEDIA\n" + ("\n".join(mrows) or "(هیچ؛ فقط گرافیک خودکار)") + "\nMEDIA>>>",
             "کار تو:\n" + VIS_RULES]
    if busy:                                   # قاب سایت (فاز ۴) آن‌جاست
        parts.append("در این بازه‌ها قاب یک سایت روی ویدیوست؛ آن‌جا تصویر یا گرافیک اصلی نگذار (شمارنده اشکالی ندارد): "
                     + "، ".join(f"{a:.1f} تا {b:.1f} ثانیه" for a, b in busy))
    if current is not None:
        parts.append("چیدمان فعلی (برای بازنویسی):\n" + json.dumps(current, ensure_ascii=False))
    if notes:
        parts.append("نظرهای قبلی کاربر درباره‌ی تصویرها (رعایت کن):\n" + "\n".join("- " + n for n in notes))
    if comment:
        parts.append("نظر تازه‌ی کاربر (مهم‌ترین دستور): " + comment)
    parts.append('خروجی فقط یک JSON بین این دو نشانه، بدون هیچ توضیح دیگر:\n<<<VIS\n'
                 '{"vis": [{"w0": 120, "w1": 131, "kind": "media", "mid": "m123", "tpl": "doc", "why": ""}, '
                 '{"w0": 150, "w1": 158, "kind": "gfx", "tpl": "logo", "data": {"name": "", "domain": "", "price": "", "cur": "", "per": "", '
                 '"strike": false, "stamp": ""}, "why": ""}], "summary": ""}\nVIS>>>')
    return "\n\n".join(parts)


def _gfx_data(tpl, data):
    data = data if isinstance(data, dict) else {}
    out = {}
    for k in GFX_FIELDS.get(tpl, ()):
        v = data.get(k)
        if k == "strike":
            out[k] = bool(v)
        elif k in ("n", "of"):
            try:
                out[k] = max(0, min(99, int(str(v).translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")))))
            except Exception:
                out[k] = 0
        elif k == "domain":
            out[k] = _domain(str(v or ""))
        else:
            out[k] = fa_num(str(v or "").strip())[:160 if k == "text" else 40]
    return out


def _kept_span(w0, w1, dv):
    """اولین و آخرین کلمه‌ی نبریده در بازه؛ None اگر همه بریده شده‌اند."""
    ks = [i for i in range(max(0, w0), min(len(dv["words"]), w1 + 1)) if i not in dv["cut"]]
    return (ks[0], ks[-1]) if ks else None


def _span_time(dv, a, b):
    tm, ws = dv["tmap"], dv["words"]
    return tm.out(ws[a]["s"]), tm.out(ws[b]["e"])


def clean_vis(data, dv, media, busy=()):
    """پیشنهاد Claude را امن می‌کند: کلمه‌ها، قالب‌ها، طول، و یک تصویر اصلی در هر لحظه (عکس کاربر برنده است)."""
    mids = {m["id"]: m for m in media}
    n = len(dv["words"])
    cand = []
    for x in data.get("vis") or []:
        try:
            w0, w1 = int(x.get("w0")), int(x.get("w1"))
        except Exception:
            continue
        w0, w1 = max(0, min(w0, w1)), min(n - 1, max(w0, w1))
        span = _kept_span(w0, w1, dv)
        if not span:
            continue
        kind, tpl = x.get("kind"), str(x.get("tpl") or "")
        it = {"w0": span[0], "w1": span[1], "kind": kind, "why": str(x.get("why") or "")[:160], "on": True, "src": "claude",
              "pos": "auto", "size": "m"}
        if kind == "media":
            m = mids.get(x.get("mid"))
            if not m:
                continue
            ok = TPL_VIDEO if m.get("type") == "video" else tuple(TPL_MEDIA)
            it.update(mid=m["id"], tpl=tpl if tpl in ok else ((m.get("an") or {}).get("tpl") or "card"))
        elif kind == "gfx" and tpl in TPL_GFX:
            it.update(tpl=tpl, data=_gfx_data(tpl, x.get("data")))
        else:
            continue
        s, e = _span_time(dv, *span)
        it["_s"], it["_e"] = s, e
        cand.append(it)
    cand.sort(key=lambda c: c["_s"])
    out = []
    for c in cand:
        if c.get("tpl") == "counter":
            out.append(c)
            continue
        if any(c["_s"] < b - 0.05 and a < c["_e"] - 0.05 for a, b in busy):     # هم‌زمان با قاب سایت
            continue
        clash = next((o for o in out if o.get("tpl") != "counter" and c["_s"] < o["_e"] - 0.05 and o["_s"] < c["_e"] - 0.05), None)
        if clash:
            if c["kind"] == "media" and clash["kind"] == "gfx":
                out.remove(clash)
            else:
                continue
        out.append(c)
    res = []
    for k, c in enumerate(sorted(out, key=lambda c: c["_s"])):
        c = {kk: v for kk, v in c.items() if not kk.startswith("_")}
        c["id"] = f"v{k}"
        res.append(c)
    return res


def _vis_sfx(vis, dv):
    """افکت ورود هر تصویر (و ماژیک هایلایت فاکتور، و مُهر «کنسل شد»)؛ اگر افکت دیگری تا ۱٫۲ ثانیه‌اش هست (مثل ووشِ مورد
    بعدی فهرست)، نه؛ مُهر و ماژیک با فاصله‌ی ۰٫۸، چون لحظه‌ی خودشان را دارند."""
    lib = ve.sfx_lib()["sounds"]
    tm, ws = dv["tmap"], dv["words"]
    taken = [tm.out(ws[x["w"]]["s"]) + float(x.get("dt") or 0) for x in dv["edit"].get("sfx") or []
             if x.get("src") != "vis" and x.get("on") is not False and isinstance(x.get("w"), int) and x["w"] not in dv["cut"]]
    out = []

    def add(v, snd, dt, why, gap=1.2):
        at = tm.out(ws[v["w0"]]["s"]) + dt
        if snd in lib and not any(abs(at - t) < gap for t in taken):
            out.append({"id": f"y{len(out)}", "w": v["w0"], "dt": round(dt, 2), "snd": snd, "cat": lib[snd]["cat"], "why": why,
                        "on": True, "src": "vis", "link": v["id"]})
            taken.append(at)

    for v in vis:
        tpl = v.get("tpl")
        if tpl == "counter":
            continue
        if v.get("kind") == "site":            # قاب سایت: ووش ورود و ماژیک سر کلمه‌ی hw0 (مثل resolve_site، دست‌کم ۱٫۶ ثانیه بعد)
            hw = v.get("hw0") if isinstance(v.get("hw0"), int) and v.get("hw0") not in dv["cut"] else None
            dt = tm.out(ws[hw]["s"]) - tm.out(ws[v["w0"]]["s"]) if hw is not None else 0.0
            add(v, "whoosh", -LEAD, "ورود قاب سایت")
            import video_sites as vs
            add(v, "marker", max((vs.SCENE_HL if v.get("pos") == "scene" else 1.6) - LEAD, dt), "ماژیک روی جمله‌ی سایت", 0.8)
            continue
        name = (v.get("data") or {}).get("name") or ""
        add(v, TPL_SFX.get(tpl, "pop"), -LEAD, f"ورود تصویر{(' ' + name) if name else ''}")
        if tpl == "doc":
            add(v, "marker", 1.45 - LEAD, "هایلایت روی سند", 0.8)
        if tpl == "logo" and (v.get("data") or {}).get("stamp"):
            add(v, "remove", 1.05 - LEAD, "مُهر «" + v["data"]["stamp"] + "»", 0.8)
    return out


def plan_visuals(vid, comment="", step=lambda s: None):
    """Claude جای عکس‌های کاربر و گرافیک خودکار را می‌چیند؛ لوگوها گرفته می‌شوند؛ افکت ورودشان اضافه می‌شود.
    مواردی که کاربر خودش گذاشته (src=user) دست نمی‌خورند."""
    dv = ve.derive(vid)
    media = [m for m in mlist(vid) if m.get("status") == "ready"]
    e0 = dv["edit"]
    vis, summary = [], "حرفی در این ویدیو نیست؛ تصویری چیده نشد."
    if any(w["i"] not in dv["cut"] for w in dv["words"]):
        step("Claude دارد عکس‌ها و گرافیک‌ها را کنار حرف‌هایت می‌چیند…")
        current = [{k: v.get(k) for k in ("w0", "w1", "kind", "mid", "tpl", "data")} for v in e0.get("vis") or []
                   if v.get("src") != "user" and v.get("kind") != "site"]
        notes = ((e0.get("notes") or {}).get("vis") or [])[-6:]
        busy = [_span_time(dv, *sp) for v in e0.get("vis") or [] if v.get("kind") == "site" and v.get("on") is not False
                for sp in [_kept_span(int(v.get("w0", 0)), int(v.get("w1", 0)), dv)] if sp]
        res = ve.ask(vis_prompt(dv, media, comment, current if comment else None, notes, busy), vid, timeout=1200, effort="high")
        data = ve.json_block(res, "<<<VIS", "VIS>>>")
        if not data:
            (ve.pdir(vid) / "vis.last-output.txt").write_text(res or "", encoding="utf-8")
            raise RuntimeError("جواب Claude برای چیدن تصویرها قابل خواندن نبود.")
        vis, summary = clean_vis(data, dv, media, busy), str(data.get("summary") or "")[:400]
    doms = sorted({(v.get("data") or {}).get("domain") for v in vis if v.get("tpl") == "logo"} - {"", None})
    if doms:
        step("گرفتن لوگوی سرویس‌ها از سایت خودشان…")
        th = [threading.Thread(target=fetch_logo, args=(dm,), daemon=True) for dm in doms]
        for t in th:
            t.start()
        for t in th:
            t.join(60)
    with ve.plock(vid):
        e = ve.jload(ve.pdir(vid) / "edit.json", {})
        if "vis" in e:                     # «نسخه‌ی قبل»: چیدمان و افکت‌های ورودش با هم
            prev = e.setdefault("prev", {})
            prev["vis"], prev["visSfx"] = e["vis"], [x for x in e.get("sfx") or [] if x.get("src") == "vis"]
        user = [v for v in e.get("vis") or [] if v.get("src") == "user" or v.get("kind") == "site"]
        for k, v in enumerate(vis):
            v["id"] = f"v{int(time.time())}{k}"
        e["vis"] = sorted(user + vis, key=lambda v: v["w0"])
        e["visSummary"] = summary
        if comment:
            e.setdefault("notes", {}).setdefault("vis", []).append(comment[:500])
        e["visAt"] = ve.now()
        e["sfx"] = [x for x in e.get("sfx") or [] if x.get("src") != "vis"]
        ve.jsave(ve.pdir(vid) / "edit.json", e)
    dv = ve.derive(vid)
    with ve.plock(vid):
        e = ve.jload(ve.pdir(vid) / "edit.json", {})
        e["sfx"] = sorted((e.get("sfx") or []) + _vis_sfx([v for v in e.get("vis") or [] if v.get("on") is not False], dv),
                          key=lambda x: (x["w"], float(x.get("dt") or 0)))
        ve.jsave(ve.pdir(vid) / "edit.json", e)


# ---------------- جای هر تصویر روی کادر ----------------
def _free_band(dv, faces, a_src, b_src, s, e):
    """بازه‌های عمودی خالی (px): بیرون از صورت و زیرنویس‌های همین بازه، داخل محدوده‌ی امن ریلز."""
    W, H = ve.CANVAS[dv["kind"]]
    if dv["kind"] == "reel":
        lo, hi = 290, 1440
    else:
        lo, hi = 40, H - 160
    blocks, fxs = [], []
    for smp in faces.get("s") or []:
        if a_src - 0.2 <= smp["t"] <= b_src + 0.2:
            for x, y, w, h in smp["f"]:
                blocks.append(((y - 0.18 * h) * H - 30, (y + h + 0.18 * h) * H + 30))
                fxs.append((x * W, (x + w) * W))
    bh = ve.cap_box_h(dv["kind"], dv["opts"]["style"], dv["opts"].get("size", "m")) * H
    for c in dv["caps"]:
        if c["s"] < e and s < c["e"] and c.get("y") is not None:
            blocks.append((c["y"] - 24, c["y"] + bh + 24))
    ivs = [(lo, hi)]
    for b0, b1 in blocks:
        nxt = []
        for a, b in ivs:
            if b1 <= a or b0 >= b:
                nxt.append((a, b))
                continue
            if b0 > a:
                nxt.append((a, b0))
            if b1 < b:
                nxt.append((b1, b))
        ivs = nxt
    fx = (min(a for a, _ in fxs), max(b for _, b in fxs)) if fxs else None
    return [(a, b) for a, b in ivs if b - a > 40], (lo, hi), fx


GFX_SIZE = {"logo": (800, 290), "price": (620, 230), "total": (780, 330), "quote": (880, 400)}
MEDIA_MAX = {"card": (820, 900), "doc": (880, 940), "polaroid": (620, 760), "phone": (440, 900), "cutout": (760, 900)}


def _layout(v, dv, faces, aspect, a_src, b_src):
    """جعبه‌ی px روی کادر: x, y, w, h."""
    W, H = ve.CANVAS[dv["kind"]]
    tpl, k = v.get("tpl"), VSIZE.get(v.get("size") or "m", 1.0)
    reel = dv["kind"] == "reel"
    sc = 1.0 if reel else 0.78
    if tpl == "full":
        return {"x": 0, "y": 0, "w": W, "h": H}
    if tpl == "scene":                          # صحنه: عکس یا ویدیو تا جای ممکن بزرگ، همان ناحیه‌ی آزاد قاب سایت در صحنه
        if reel:                                # زیر نوار بالای اینستاگرام، بالای زیرنویس پایین، چپِ ستون لایک و کامنت
            o = dv["opts"]
            x0, x1, y0 = 40, 950, 270
            y1 = int(H * ve.zones_for("reel", ve.cap_box_h("reel", o.get("style"), o.get("size", "m")))["bot"]) - 22
        else:
            x0, x1, y0, y1 = 80, W - 80, int(H * 0.06), int(H * 0.82)
        aw, ah = min(x1 - x0, (x1 - x0) * k), min(y1 - y0, (y1 - y0) * k)
        bw, bh = (aw, aw / aspect) if aw / aspect <= ah else (ah * aspect, ah)
        return {"x": int(x0 + (x1 - x0 - bw) / 2), "y": int(y0 + (y1 - y0 - bh) / 2), "w": int(bw), "h": int(bh)}
    if tpl == "top":
        return {"x": 0, "y": 0, "w": W, "h": int(H * (0.5 if reel else 0.55))}
    if tpl == "counter":
        bw, bh = int(250 * sc), int(96 * sc)
        return {"x": W - bw - (54 if reel else 40), "y": 300 if reel else 36, "w": bw, "h": bh}
    if v["kind"] == "gfx":
        bw, bh = GFX_SIZE.get(tpl, (760, 300))
        if tpl == "quote":
            bh = 300 + 62 * max(0, math.ceil(len((v.get("data") or {}).get("text") or "") / 30) - 2)
        bw, bh = int(bw * k * sc), int(min(bh * k * sc, H * 0.5))
    else:
        mw, mh = MEDIA_MAX.get(tpl, (820, 900))
        mw, mh = mw * k * sc, mh * k * sc
        if tpl == "phone":
            bw, bh = mw, mw * 2.05
        elif tpl == "polaroid":
            bw, bh = mw, mw * 1.2
        else:
            bw, bh = (mw, mw / aspect) if mw / aspect <= mh else (mh * aspect, mh)
    ivs, (lo, hi), fx = _free_band(dv, faces, a_src, b_src, v["_s"], v["_e"])
    pos = v.get("pos") or "auto"
    if pos == "top":
        band = (lo, max(lo + bh, H * 0.55))
    elif pos == "mid":
        band = (H / 2 - bh / 2 - 20, H / 2 + bh / 2 + 20)
    elif pos == "bot":
        band = (max(lo, hi - bh - 40), hi)
    else:
        band = max(ivs, key=lambda iv: iv[1] - iv[0]) if ivs else (lo, hi)
    room = band[1] - band[0] - 30
    if reel and pos == "auto" and tpl in ("phone", "polaroid", "cutout") and room < 0.6 * bh:
        # قاب ایستاده جای کافی بالای صورت ندارد (مثلاً نمای باز): کنار صورت، در سمتی که جای بیشتری دارد
        f0, f1 = fx or (W * 0.4, W * 0.6)
        left, right = f0 - 70, 950 - f1 - 30
        avail = max(left, right)
        if avail >= 240:
            f = min(1.0, avail / bw, (hi - lo - 20) / bh)
            bw2, bh2 = bw * f, bh * f
            x = 40 + (left - bw2) / 2 if left >= right else f1 + 30 + (right - bw2) / 2
            return {"x": int(x), "y": int(lo + (hi - lo - bh2) / 2), "w": int(bw2), "h": int(bh2)}
    if tpl == "doc":                            # سند: تمام عرض؛ ارتفاع همان جای خالی (حداقل ۴۲۰)
        bw, bh = min(W - 120, 880 * k) if reel else 760 * k, max(420.0, min(room, 900 * k * sc))
    elif bh > room >= 280:                      # کوچک‌تر تا در جای خالی جا شود، نه روی صورت و زیرنویس
        f = room / bh
        bw, bh = bw * f, bh * f
    y = band[0] + max(0.0, (band[1] - band[0] - bh) / 2) if room >= bh else band[0] + 10
    y = min(max(lo - 20, y), H - bh - 20)
    x = (W - bw) / 2 if reel else W - bw - 90
    if reel and y + bh > 1000:                                # ستون لایک و کامنت سمت راست
        x = min(x, 950 - bw)
    return {"x": int(x), "y": int(y), "w": int(bw), "h": int(bh)}


def resolve(vid, dv):
    """vis روی زمان خروجی و کادر. هر مورد: s، e، جعبه (box)، فایل (file)، و skip اگر پخش نمی‌شود."""
    items = {m["id"]: m for m in mlist(vid)}
    faces = ve.jload(ve.pdir(vid) / "faces.json", {})
    out = []
    dur = dv["tmap"].dur
    for v in dv["edit"].get("vis") or []:
        c = dict(v, skip=None)
        if v.get("kind") == "site":            # فاز ۴: قاب سایت (video_sites.py)
            import video_sites as vs
            r, why = vs.resolve_site(vid, dv, v, faces)
            if r:
                c.update(r)
            else:
                c["skip"] = why
            out.append(c)
            continue
        span = _kept_span(int(v.get("w0", 0)), int(v.get("w1", 0)), dv) if isinstance(v.get("w0"), int) else None
        m = items.get(v.get("mid")) if v.get("kind") == "media" else None
        if not span:
            c["skip"] = "cut"
        elif v.get("kind") == "media" and (not m or m.get("status") not in ("ready", "process", "analyze")):
            c["skip"] = "media"
        elif v.get("kind") == "media" and not media_out(vid, m["id"]):
            c["skip"] = "media"
        if c["skip"]:
            out.append(c)
            continue
        s, e = _span_time(dv, *span)
        s = max(0.0, s - LEAD)
        mn = 1.2 if v["kind"] == "media" else 1.0
        e = min(dur, max(e + 0.25, s + mn))
        if m and m.get("type") == "video":         # ویدیو کوتاه‌تر از بازه: تصویر با آخر ویدیو تمام می‌شود
            tr = (m.get("an") or {}).get("trim") or [0, m.get("dur") or 0]
            e = min(e, s + max(0.8, tr[1] - tr[0]))
        c["_s"], c["_e"] = s, e
        c.update(s=round(s, 3), e=round(e, 3))
        aspect = 1.0
        if m:
            c["media"] = {k: m.get(k) for k in ("type", "w", "h", "dur", "boxes", "an")}
            aspect = (m.get("w") or 1) / max(1, m.get("h") or 1)
            if m.get("type") == "video" and c.get("tpl") not in TPL_VIDEO:
                c["tpl"] = "card"
        c["box"] = _layout(c, dv, faces, aspect, dv["words"][span[0]]["s"], dv["words"][span[1]]["e"])
        if c.get("tpl") == "scene":
            c["scene"] = True
        out.append({k: val for k, val in c.items() if not k.startswith("_")})
    if any(c.get("scene") for c in out):           # صحنه‌های پشت‌سرهم یک زمینه‌ی پیوسته می‌گیرند
        import video_sites as vs
        vs.join_scenes(out)
    return out


# ---------------- ترکیب HTML ----------------
CSS = """
.ov{position:absolute;z-index:5}
.ov.badge{z-index:6}
.ov .ovi{position:relative;width:100%;height:100%}
.ov img,.ov video{display:block}
.ov-card .ovi{border-radius:30px;overflow:hidden;border:9px solid #fff;box-shadow:0 28px 70px rgba(0,0,0,.45);background:#fff}
.ov-card img,.ov-card video,.ov-full img,.ov-full video,.ov-top img,.ov-top video,.ov-pol img,.ov-pol video{width:100%;height:100%;object-fit:cover}
.ov-doc .ovi{border-radius:20px;overflow:hidden;background:#fff;box-shadow:0 26px 70px rgba(0,0,0,.5),0 0 0 2px rgba(255,255,255,.55)}
.ov-doc .dz{position:absolute;left:0;top:0;transform-origin:0 0}
.ov-doc .dz img{width:100%;height:100%}
.ov-doc .hl{position:absolute;background:rgba(255,219,88,.62);mix-blend-mode:multiply;border-radius:7px}
.ov-full .ovi,.ov-top .ovi{overflow:hidden;background:#000}
.ov-full .shade{position:absolute;inset:0;background:linear-gradient(180deg,rgba(0,0,0,.28) 0%,rgba(0,0,0,0) 20%,rgba(0,0,0,0) 58%,rgba(0,0,0,.5) 100%)}
.ov-top .ovi{box-shadow:0 18px 44px rgba(0,0,0,.5)}
.ov-pol .ovi{background:#fbfaf5;padding:22px 22px 0;border-radius:6px;box-shadow:0 26px 60px rgba(0,0,0,.45)}
.ov-pol .ph{width:100%;height:calc(100% - 118px);overflow:hidden;background:#ddd}
.ov-pol .pc{height:118px;display:flex;align-items:center;justify-content:center;font-weight:800;font-size:42px;color:#1a3c64;padding:0 12px}
.ov-pol .pc span{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;min-width:0}
.ov-phone .ovi{background:#0b0f14;border-radius:70px;padding:18px;box-shadow:0 30px 80px rgba(0,0,0,.55),inset 0 0 0 3px #2c3644}
.ov-phone .scr{position:relative;width:100%;height:100%;border-radius:54px;overflow:hidden;background:#fff}
.ov-phone .scr img{position:absolute;left:0;top:0;width:100%;height:auto}
.ov-phone .scr video{width:100%;height:100%;object-fit:cover}
.ov-phone .isl{position:absolute;top:36px;left:50%;width:126px;height:36px;margin-left:-63px;background:#000;border-radius:20px}
.ov.ov-scene{z-index:7}
.ov-scene .sc-bg{position:absolute;inset:0;background:radial-gradient(120% 75% at 50% 40%,#24507f 0%,#1a3c64 55%,#0f2540 100%)}
.ov-scene .sc-bg::after{content:"";position:absolute;inset:0;background-image:radial-gradient(rgba(255,255,255,.07) 1.6px,transparent 1.8px);background-size:38px 38px}
.ov-scene .sc-fr{position:absolute}
.ov-scm .ovi{border-radius:34px;overflow:hidden;background:#0b1a2c;box-shadow:0 30px 80px rgba(0,0,0,.5),0 0 0 3px rgba(255,255,255,.16)}
.ov-scm img,.ov-scm video{width:100%;height:100%;object-fit:cover}
.ov-cut .blob{position:absolute;left:10%;top:14%;width:80%;height:78%;border-radius:50%;background:radial-gradient(circle at 38% 32%,#2f6aa6,#1a3c64 72%)}
.ov-cut img{position:absolute;inset:0;width:100%;height:100%;object-fit:contain;filter:drop-shadow(0 0 2px #fff) drop-shadow(0 0 2px #fff) drop-shadow(0 0 2px #fff) drop-shadow(0 22px 34px rgba(0,0,0,.45))}
.gx .ovi{background:#fff;border-radius:34px;box-shadow:0 26px 64px rgba(0,0,0,.42);direction:rtl;display:flex;align-items:center}
.gx-logo .ovi{gap:30px;padding:0 40px}
.gx-logo .lg{flex:0 0 auto;width:150px;height:150px;border-radius:36px;background:#f3f5f8;display:flex;align-items:center;justify-content:center;overflow:hidden}
.gx-logo .lg img{width:74%;height:74%;object-fit:contain}
.gx-logo .lg b{font-size:84px;font-weight:900;color:#1a3c64}
.gx-logo .tx{flex:1;min-width:0;display:flex;flex-direction:column;gap:4px}
.gx-logo .nm{font-size:62px;font-weight:900;color:#0f1f33;line-height:1.2;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.gx .pr{position:relative;align-self:flex-start;display:flex;gap:12px;align-items:baseline;font-size:46px;font-weight:800;color:#33475e;white-space:nowrap}
.gx .pr small{font-size:31px;font-weight:600;color:#7a8696}
.gx .amt{position:relative;white-space:nowrap}
.gx .st{position:absolute;left:-8px;right:-8px;top:50%;height:8px;margin-top:-2px;background:#e5484d;border-radius:4px;transform-origin:100% 50%}
.gx-logo .stamp{position:absolute;left:30px;top:-30px;border:7px solid #e5484d;color:#e5484d;font-size:40px;font-weight:900;padding:0 22px;border-radius:14px;background:rgba(255,255,255,.94);white-space:nowrap}
.gx-price .ovi{flex-direction:column;justify-content:center;gap:2px}
.gx-price .pr{align-self:center;font-size:96px;font-weight:900;color:#0f1f33}
.gx-price .pr small{font-size:40px}
.gx-price .per{font-size:34px;font-weight:700;color:#7a8696}
.gx-total .ovi{background:#1a3c64;flex-direction:column;justify-content:center;gap:4px;box-shadow:0 26px 64px rgba(0,0,0,.5),inset 0 0 0 3px rgba(255,219,88,.55)}
.gx-total .lb{font-size:40px;font-weight:700;color:#cfe0f5}
.gx-total .v{font-size:120px;font-weight:900;color:#ffdb58;line-height:1.15;white-space:nowrap}
.gx-total .v small{font-size:48px;color:#fff;font-weight:800}
.gx-quote .ovi{background:#1a3c64;flex-direction:column;align-items:stretch;justify-content:center;padding:36px 52px;gap:16px;box-shadow:0 26px 64px rgba(0,0,0,.5)}
.gx-quote .qm{position:absolute;right:26px;top:-34px;font-size:150px;line-height:1;color:#ffdb58;font-weight:900}
.gx-quote .qt{font-size:46px;font-weight:700;color:#fff;line-height:1.7}
.gx-quote .by{font-size:36px;font-weight:800;color:#ffdb58;text-align:left}
.gx-count .ovi{background:#1a3c64;border-radius:999px;justify-content:center;gap:12px;box-shadow:0 10px 30px rgba(0,0,0,.4);color:#fff;font-weight:800;font-size:38px;direction:rtl}
.gx-count b{color:#ffdb58;font-size:60px;font-weight:900}
"""


def _copy(src, assets, name):
    dst = assets / name
    if src and src.exists() and (not dst.exists() or dst.stat().st_mtime < src.stat().st_mtime or dst.stat().st_size != src.stat().st_size):
        shutil.copy2(src, dst)
    return f"assets/{name}"


def _media_tag(vid, v, mode, assets, cls="", style=""):
    """<img> یا <video> برای یک رسانه‌ی کاربر (نسخه‌ی محوشده)."""
    m = v["media"]
    mid = v["mid"]
    if m["type"] == "video":
        f = media_out(vid, mid, preview=(mode == "preview"))
        src = _copy(f, assets, f"m-{mid}{'-p' if mode == 'preview' else ''}.mp4")
        an = m.get("an") or {}
        trim = an.get("trim") or [0, m.get("dur") or 0]
        dur = round(v["e"] - v["s"], 3)
        ms = trim[0]
        return (f'<video class="ovv {cls}" id="{v["id"]}m" src="{src}" data-start="{v["s"]}" data-duration="{dur}" '
                f'data-media-start="{round(ms, 3)}" data-track-index="3" muted playsinline preload="auto" style="{style}"></video>')
    f = media_out(vid, mid)
    return f'<img class="{cls}" id="{v["id"]}m" src="{_copy(f, assets, f"m-{mid}{f.suffix}")}" style="{style}" alt="">'


def _focus_pos(m):
    f = (m.get("boxes") or {}).get("focus")
    if not f:
        return "50% 50%"
    return f"{round((f[0] + f[2] / 2) * 100, 1)}% {round((f[1] + f[3] / 2) * 100, 1)}%"


def comp_parts(vid, dv, mode, assets):
    """(html، css، خط‌های تایم‌لاین) برای همه‌ی تصویرهای روشن."""
    html, tl = [], []
    for v in dv.get("vis") or []:
        if v.get("skip") or v.get("on") is False:
            continue
        if v.get("kind") == "site":
            import video_sites as vs
            h, t = vs.comp_site(vid, dv, v, mode, assets)
            html.append(h)
            tl += t
            continue
        b, i, s, e = v["box"], v["id"], v["s"], v["e"]
        d = round(e - s, 3)
        tpl = v["tpl"]
        box = f'left:{b["x"]}px;top:{b["y"]}px;width:{b["w"]}px;height:{b["h"]}px'
        head = f'<div id="{i}" class="clip ov {{cls}}" data-start="{s}" data-duration="{d}" data-track-index="1" style="{box}">'
        pop = (f'tl.fromTo("#{i}",{{opacity:0,scale:.84,y:36}},{{opacity:1,scale:1,y:0,duration:.42,ease:"back.out(1.6)"}},{s});')
        out_ = f'tl.to("#{i}",{{opacity:0,scale:.94,y:-18,duration:.22,ease:"power2.in"}},{round(max(s + .3, e - .22), 3)});'
        if v["kind"] == "media":
            m = v["media"]
            if tpl == "doc":
                f = media_out(vid, v["mid"])
                iw, ih = m.get("w") or 1000, m.get("h") or 1000
                vw, vh = b["w"], b["h"]
                s0 = min(vw / iw, vh / ih)
                tx0, ty0 = (vw - iw * s0) / 2, (vh - ih * s0) / 2
                hls = (m.get("boxes") or {}).get("hl") or []
                fb = _union(hls) if hls else (m.get("boxes") or {}).get("focus")
                if fb and hls:                  # زمینه‌ی کمی دور مبلغ، بیشتر به سمت برچسبش (چپ در انگلیسی، راست در فارسی)
                    rtl0 = bool((m.get("an") or {}).get("rtl"))
                    px, py = 0.16, 0.035
                    fb = _clip([fb[0] - (px * 0.4 if rtl0 else px), fb[1] - py, fb[2] + px * 1.4, fb[3] + 2 * py])
                if fb:
                    s1 = min(0.94 * vw / max(1, fb[2] * iw), 0.6 * vh / max(1, fb[3] * ih), s0 * 6, 1.6)
                    s1 = max(s1, s0)
                    cx, cy = (fb[0] + fb[2] / 2) * iw * s1, (fb[1] + fb[3] / 2) * ih * s1
                    tx1, ty1 = vw / 2 - cx, vh / 2 - cy      # بی‌قید: زمینه‌ی کارت هم سفید است، پس مبلغ وسط می‌آید
                else:
                    s1, tx1, ty1 = s0, tx0, ty0
                rtl = bool((m.get("an") or {}).get("rtl"))
                marks = "".join(
                    f'<i class="hl" id="{i}h{k}" style="left:{q[0] * iw:.0f}px;top:{q[1] * ih:.0f}px;width:{q[2] * iw:.0f}px;'
                    f'height:{q[3] * ih:.0f}px;transform-origin:{"100%" if rtl else "0%"} 50%"></i>' for k, q in enumerate(hls))
                src = _copy(f, assets, f"m-{v['mid']}{f.suffix}")
                html.append(head.format(cls="ov-doc") + f'<div class="ovi"><div class="dz" id="{i}z" style="width:{iw}px;height:{ih}px">'
                            f'<img src="{src}" alt="">{marks}</div></div></div>')
                tl.append(f'tl.set("#{i}z",{{x:{tx0:.1f},y:{ty0:.1f},scale:{s0:.5f},transformOrigin:"0 0"}},{s});')
                tl.append(pop)
                if fb:
                    tl.append(f'tl.to("#{i}z",{{x:{tx1:.1f},y:{ty1:.1f},scale:{s1:.5f},duration:.9,ease:"power2.inOut"}},{round(s + .6, 3)});')
                for k in range(len(hls)):
                    tl.append(f'tl.fromTo("#{i}h{k}",{{scaleX:0}},{{scaleX:1,duration:.45,ease:"power2.out"}},{round(s + 1.45 + .12 * k, 3)});')
                tl.append(out_)
            elif tpl in ("full", "top"):
                tag = _media_tag(vid, v, mode, assets, style=f"object-position:{_focus_pos(m)};transform-origin:{_focus_pos(m)}")
                html.append(head.format(cls=f"ov-{tpl}") + f'<div class="ovi">{tag}{"<i class=shade></i>" if tpl == "full" else ""}</div></div>')
                if tpl == "full":
                    tl.append(f'tl.fromTo("#{i}",{{opacity:0}},{{opacity:1,duration:.25,ease:"power1.out"}},{s});')
                else:
                    tl.append(f'tl.fromTo("#{i}",{{opacity:0,y:-80}},{{opacity:1,y:0,duration:.4,ease:"power3.out"}},{s});')
                if m["type"] != "video":
                    tl.append(f'tl.fromTo("#{i}m",{{scale:1}},{{scale:1.08,duration:{d},ease:"none"}},{s});')
                tl.append(f'tl.to("#{i}",{{opacity:0,duration:.22,ease:"power2.in"}},{round(max(s + .3, e - .22), 3)});')
            elif tpl == "scene":                # مثل صحنه‌ی سایت: زمینه از پایین بالا می‌آید و گوینده را می‌پوشاند، بعد قاب
                W, H = ve.CANVAS[dv["kind"]]
                tag = _media_tag(vid, v, mode, assets)
                html.append(f'<div id="{i}" class="clip ov ov-scene ov-scm" data-start="{s}" data-duration="{d}" data-track-index="1" '
                            f'style="left:0;top:0;width:{W}px;height:{H}px"><i class="sc-bg" id="{i}g"></i>'
                            f'<div class="sc-fr" id="{i}f" style="{box}"><div class="ovi">{tag}</div></div></div>')
                tl.append(f'tl.set("#{i}g",{{clipPath:"inset(0% 0% 0% 0%)"}},{s});' if v.get("joinPrev") else
                          f'tl.fromTo("#{i}g",{{clipPath:"inset(100% 0% 0% 0%)"}},{{clipPath:"inset(0% 0% 0% 0%)",duration:.45,ease:"power3.inOut"}},{s});')
                tl.append(f'tl.fromTo("#{i}f",{{opacity:0,y:80,scale:.92}},{{opacity:1,y:0,scale:1,duration:.6,ease:"power3.out"}},'
                          f'{round(s + (0 if v.get("joinPrev") else .2), 3)});')
                if m["type"] != "video":
                    tl.append(f'tl.fromTo("#{i}m",{{scale:1}},{{scale:1.04,duration:{d},ease:"none"}},{s});')
                tl.append(f'tl.to("#{i}f",{{opacity:0,y:-70,scale:.96,duration:.3,ease:"power2.in"}},'
                          f'{round(max(s + .8, e - (.35 if v.get("joinNext") else .55)), 3)});')
                if not v.get("joinNext"):      # صحنه‌ی بعدی بلافاصله می‌آید: زمینه می‌ماند تا گوینده وسطشان پیدا نشود
                    tl.append(f'tl.to("#{i}g",{{clipPath:"inset(0% 0% 100% 0%)",duration:.4,ease:"power3.inOut"}},{round(max(s + 1, e - .4), 3)});')
            elif tpl == "polaroid":
                tag = _media_tag(vid, v, mode, assets, style=f"object-position:{_focus_pos(m)}")
                lab = escape(((m.get("an") or {}).get("label") or "")[:40])
                ph = int(max(56, min(118, b["w"] * 0.19)))
                fz = int(max(18, min(42, b["w"] / 14)))
                html.append(head.format(cls="ov-pol") + f'<div class="ovi"><div class="ph" style="height:calc(100% - {ph}px)">{tag}</div>'
                            f'<div class="pc" style="height:{ph}px;font-size:{fz}px"><span>{lab}</span></div></div></div>')
                tl.append(f'tl.fromTo("#{i}",{{opacity:0,y:-120,rotation:-9}},{{opacity:1,y:0,rotation:3,duration:.5,ease:"back.out(1.4)"}},{s});')
                tl.append(out_)
            elif tpl == "phone":
                tag = _media_tag(vid, v, mode, assets)
                html.append(head.format(cls="ov-phone") + f'<div class="ovi"><div class="scr">{tag}</div><i class="isl"></i></div></div>')
                tl.append(pop)
                if m["type"] != "video":      # اسکرین‌شات بلند: آرام تا جای مهمش پایین می‌رود
                    sw, sh = b["w"] - 36, b["h"] - 36
                    disp_h = sw * (m.get("h") or 1) / max(1, m.get("w") or 1)
                    fb = (m.get("boxes") or {}).get("focus")
                    cy = ((fb[1] + fb[3] / 2) if fb else 0.0) * disp_h
                    ty = -min(max(0.0, disp_h - sh), max(0.0, cy - sh / 2))
                    if ty < -2:
                        tl.append(f'tl.fromTo("#{i}m",{{y:0}},{{y:{ty:.0f},duration:{max(.8, d - 1.2):.2f},ease:"power1.inOut"}},{round(s + .6, 3)});')
                tl.append(out_)
            elif tpl == "cutout":
                cut = cutout(vid, v["mid"])
                if cut:
                    src = _copy(cut, assets, f"m-{v['mid']}-cut.png")
                    html.append(head.format(cls="ov-cut") + f'<div class="ovi"><i class="blob"></i><img src="{src}" alt=""></div></div>')
                else:
                    html.append(head.format(cls="ov-card") + f'<div class="ovi">{_media_tag(vid, v, mode, assets)}</div></div>')
                tl.append(f'tl.fromTo("#{i}",{{opacity:0,scale:.6}},{{opacity:1,scale:1,duration:.45,ease:"back.out(2)"}},{s});')
                tl.append(out_)
            else:   # card
                tag = _media_tag(vid, v, mode, assets, style=f"object-position:{_focus_pos(m)}")
                html.append(head.format(cls="ov-card") + f'<div class="ovi">{tag}</div></div>')
                tl.append(f'tl.fromTo("#{i}",{{opacity:0,scale:.82,y:40,rotation:-6}},{{opacity:1,scale:1,y:0,rotation:-2,duration:.45,ease:"back.out(1.7)"}},{s});')
                tl.append(out_)
            continue
        dt = v.get("data") or {}
        if tpl == "logo":
            lf = None
            if dt.get("domain"):
                idx = ve.jload(LOGOS / "logos.json", {}).get(dt["domain"]) or {}
                lf = LOGOS / idx["file"] if idx.get("file") else None
            name = dt.get("name") or dt.get("domain") or ""
            logo = (f'<img src="{_copy(lf, assets, "logo-" + lf.name)}" alt="">' if lf and lf.exists()
                    else f'<b>{escape(name[:1].upper())}</b>')
            price = ""
            if dt.get("price"):
                ln = len(f'{dt["price"]} {dt.get("cur") or ""} {dt.get("per") or ""}')
                fz = 46 if ln <= 16 else 40 if ln <= 21 else 34
                price = (f'<div class="pr" style="font-size:{fz}px"><span class="amt">{escape(dt["price"])} {escape(dt.get("cur") or "")}'
                         + (f'<i class="st" id="{i}s"></i>' if dt.get("strike") else "") + '</span>'
                         + (f'<small>{escape(dt["per"])}</small>' if dt.get("per") else "") + '</div>')
            stamp = f'<div class="stamp" id="{i}p">{escape(dt["stamp"])}</div>' if dt.get("stamp") else ""
            html.append(head.format(cls="gx gx-logo") + f'<div class="ovi"><div class="lg">{logo}</div><div class="tx">'
                        f'<bdi class="nm">{escape(name)}</bdi>{price}</div>{stamp}</div></div>')
            tl.append(pop)
            if dt.get("price") and dt.get("strike"):
                tl.append(f'tl.fromTo("#{i}s",{{scaleX:0}},{{scaleX:1,duration:.35,ease:"power2.out"}},{round(s + .75, 3)});')
            if dt.get("stamp"):
                tl.append(f'tl.fromTo("#{i}p",{{opacity:0,scale:1.9,rotation:-12}},{{opacity:1,scale:1,rotation:-12,duration:.26,ease:"power3.in"}},{round(s + 1.05, 3)});')
            tl.append(out_)
        elif tpl == "price":
            st = f'<i class="st" id="{i}s"></i>' if dt.get("strike") else ""
            html.append(head.format(cls="gx gx-price") + f'<div class="ovi"><div class="pr"><span class="amt">{escape(dt.get("value") or "")} '
                        f'<small>{escape(dt.get("cur") or "")}</small>{st}</span></div>'
                        + (f'<div class="per">{escape(dt["per"])}</div>' if dt.get("per") else "") + '</div></div>')
            tl.append(pop)
            if dt.get("strike"):
                tl.append(f'tl.fromTo("#{i}s",{{scaleX:0}},{{scaleX:1,duration:.35,ease:"power2.out"}},{round(s + .7, 3)});')
            tl.append(out_)
        elif tpl == "total":
            val = dt.get("value") or ""
            html.append(head.format(cls="gx gx-total") + f'<div class="ovi"><div class="lb">{escape(dt.get("label") or "")}</div>'
                        f'<div class="v"><span id="{i}n">{escape(val)}</span> <small>{escape(dt.get("cur") or "")}</small></div></div></div>')
            tl.append(pop)
            num = val.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")).replace(",", "").replace("٬", "")
            if num.isdigit() and int(num) > 1:      # شمارش از صفر تا عدد، پله‌پله (بدون callback؛ رندر تایم‌لاین را seek می‌کند)
                n, steps = int(num), 14
                for k in range(steps + 1):
                    tl.append(f'tl.set("#{i}n",{{textContent:"{fa_num(round(n * (k / steps) ** 0.6))}"}},{round(s + .2 + .06 * k, 3)});')
            tl.append(out_)
        elif tpl == "quote":
            html.append(head.format(cls="gx gx-quote") + f'<div class="ovi"><i class="qm">«</i><div class="qt">{escape(dt.get("text") or "")}</div>'
                        f'<div class="by">— {escape(dt.get("by") or "")}</div></div></div>')
            tl.append(pop)
            tl.append(out_)
        elif tpl == "counter":
            html.append(head.format(cls="gx-count badge") + f'<div class="ovi"><b>{fa_num(dt.get("n") or "")}</b><span>از {fa_num(dt.get("of") or "")}</span></div></div>')
            tl.append(f'tl.fromTo("#{i}",{{opacity:0,x:40}},{{opacity:1,x:0,duration:.3,ease:"power3.out"}},{s});')
            tl.append(f'tl.to("#{i}",{{opacity:0,duration:.2}},{round(max(s + .3, e - .2), 3)});')
    if any(v.get("kind") == "site" and not v.get("skip") for v in dv.get("vis") or []):
        import video_sites as vs
        return html, ve.brandify(CSS + vs.CSS), tl
    return html, ve.brandify(CSS), tl


# ---------------- برای صفحه ----------------
def media_view(vid):
    out = []
    for m in mlist(vid):
        d = mdir(vid, m["id"])
        th = d / "thumb.jpg"
        an = m.get("an") or {}
        bx = m.get("boxes") or {}
        out.append({"id": m["id"], "name": m.get("name"), "type": m.get("type"), "src": m.get("src"), "status": m.get("status"),
                    "step": m.get("step", ""), "err": m.get("err", ""), "w": m.get("w"), "h": m.get("h"), "dur": m.get("dur"),
                    "pages": m.get("pages"), "note": m.get("note", ""), "label": an.get("label") or "", "desc": an.get("desc") or "",
                    "tpl": an.get("tpl") or "", "when": an.get("when") or "", "fallback": an.get("fallback", False),
                    "boxes": {"blur": bx.get("blur") or [], "hl": bx.get("hl") or [], "focus": bx.get("focus")},
                    "boxesBy": m.get("boxesBy", "claude"), "v": int(th.stat().st_mtime) if th.exists() else 0})
    return out


def vis_view(dv):
    out = []
    for v in dv.get("vis") or []:
        dt = v.get("data") or {}
        if v.get("kind") == "site":
            st = next((x for x in dv["edit"].get("sites") or [] if x.get("id") == v.get("sid")), {})
            dom = re.sub(r"^https?://(www\.)?", "", st.get("url") or "").split("/")[0]
            q = st.get("quote") or ""
            lab = f"{dom} — «{q[:60]}{'…' if len(q) > 60 else ''}»"
        elif v.get("kind") == "media":
            lab = ((v.get("media") or {}).get("an") or {}).get("label") or ""
        elif v.get("tpl") == "logo":
            lab = " · ".join(x for x in (dt.get("name"), (dt.get("price") or "") + (" " + dt["cur"] if dt.get("cur") and dt.get("price") else ""),
                                          dt.get("stamp")) if x)
        elif v.get("tpl") == "counter":
            lab = f"{fa_num(dt.get('n'))} از {fa_num(dt.get('of'))}"
        elif v.get("tpl") == "quote":
            lab = f"«{(dt.get('text') or '')[:40]}» — {dt.get('by') or ''}"
        else:
            lab = " ".join(x for x in (dt.get("value"), dt.get("cur"), dt.get("label") or dt.get("per")) if x)
        out.append({k: v.get(k) for k in ("id", "kind", "mid", "sid", "tpl", "w0", "w1", "s", "e", "on", "src", "pos", "size", "why", "data", "skip")}
                   | {"label": lab})
    return out
