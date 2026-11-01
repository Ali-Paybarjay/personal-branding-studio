"""تدوین ویدیو — فاز ۴: وقتی گوینده از یک سایت، گزارش، مقاله یا پست حرف می‌زند، همان صفحه را پیدا می‌کند و همان جمله را هایلایت.
موتور اصلی video_engine.py، تصویرها video_visuals.py (vis)، مسیرها video.py.

data/videos/<id>/
  edit.json → sites   ارجاع‌ها: نشانی، جمله‌ی عین صفحه (quote)، حرف گوینده (claim)، قاب (mode: desktop|mobile)، وضعیت عکس
  edit.json → vis     kind=site: قاب مرورگر (browser) یا گوشی (phone) روی کلمه‌های w0..w1؛ هایلایت هم‌زمان با کلمه‌های hw0..hw1
  sites/<sid>/<mode>/ shot.jpg (حدود سه پنجره دور جمله، با چگالی ۲ یا ۳) · geo.json (جعبه‌ی هر خط، px CSS) · thumb.jpg · view.jpg
data/videos/.browser/  پروفایل ماندگار Chrome (تأیید کوکی یک بار)؛ عکس‌گرفتن‌ها یکی‌یکی، چون پروفایل قفل می‌شود

- پیدا کردن: Claude با WebSearch و WebFetch (فقط همین دو ابزار؛ Read هرگز) نشانی و **عین جمله‌ی صفحه** را می‌دهد.
- عکس: modules/video/capture-site.mjs (playwright-core + Chrome). سایت مسدود → Firecrawl (فقط یک بار برای هر سایت و فقط اگر
  دست‌کم ۲۵ اعتبار مانده؛ هر بار ۱ اعتبار) + OCR خود macOS برای جای جمله. آخر سر کاربر اسکرین‌شات خودش را می‌دهد و اگر جمله
  پیدا نشد، کادر هایلایت را خودش می‌کشد.
"""
import difflib, json, math, re, shutil, subprocess, threading, time, urllib.parse, urllib.request
from html import escape
from pathlib import Path
import video_engine as ve
import video_visuals as vv

CAPTURE = ve.MOD / "capture-site.mjs"
PROFILE = ve.DIR / ".browser"
MODES = ("desktop", "mobile")
FRAME = {"browser": "desktop", "phone": "mobile"}          # قالب قاب ← حالت عکس
TPL_SITE = {"browser": "قاب مرورگر", "phone": "قاب گوشی"}
# «صحنه» (۲۰۲۶-۱۰-۰۷، درخواست کاربر): گوینده پنهان می‌شود، زمینه‌ی سرمه‌ای برند صفحه را می‌پوشاند، قاب از پایین بالا می‌آید،
# تا جمله اسکرول و زوم می‌کند و جمله هایلایت می‌شود؛ آخرش صحنه کنار می‌رود و گوینده برمی‌گردد.
POS_SITE = {**vv.POS, "scene": "تمام‌صفحه (زمینه‌ی سرمه‌ای)"}
SCENE_HL = 2.45                                            # در صحنه، ماژیک دست‌کم این‌قدر بعد از شروع (ورود + اسکرول + زوم)
SCENE_ZOOM = 1.06                                          # در صحنه، خود قاب هم سر زوم این‌قدر بزرگ می‌شود


def default_pos(vid):
    """جای پیش‌فرض قاب سایت تازه (Claude یا «🌐 سایت…»). ۲۰۲۶-۱۰-۰۸، درخواست کاربر: در ریلز صحنه‌ی تمام‌صفحه، تا تصویر گوینده
    کامل برود و فقط سایت بماند. ضبط صفحه همان «خودکار» می‌ماند، چون صحنه خودِ صفحه‌ی ضبط‌شده را می‌پوشاند."""
    return "scene" if ve.jload(ve.pdir(vid) / "project.json", {}).get("kind", "reel") == "reel" else "auto"

FC_MIN = 25                                                # کمترین اعتبار Firecrawl که با آن هنوز امتحانش می‌کنیم
PRIVATE = re.compile(r"^(localhost|127\.|10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.|169\.254\.|0\.|\[?::1\]?$|"
                     r"100\.(6[4-9]|[7-9]\d|1[01]\d|12[0-7])\.)|\.(local|localhost|internal|ts\.net)$", re.I)
_CAP_L = threading.Lock()                                  # یک Chrome با این پروفایل در هر لحظه


def safe_url(u):
    """فقط http(s) عمومی؛ نشانی بی‌طرح https می‌گیرد."""
    u = (u or "").strip()
    if u and not re.match(r"^[a-z]+://", u, re.I):
        u = "https://" + u
    try:
        p = urllib.parse.urlsplit(u)
    except Exception:
        return ""
    if p.scheme not in ("http", "https") or not p.hostname or PRIVATE.search(p.hostname) or "." not in p.hostname:
        return ""
    return urllib.parse.urlunsplit(p)[:1000]


def domain(u):
    try:
        return re.sub(r"^www\.", "", urllib.parse.urlsplit(u).hostname or "")
    except Exception:
        return ""


def sdir(vid, sid, mode=None):
    d = ve.pdir(vid) / "sites" / sid
    return d / mode if mode else d


def slist(vid):
    return list(ve.jload(ve.pdir(vid) / "edit.json", {}).get("sites") or [])


def sget(vid, sid):
    return next((s for s in slist(vid) if s.get("id") == sid), None)


def supdate(vid, sid, **kw):
    with ve.plock(vid):
        e = ve.jload(ve.pdir(vid) / "edit.json", {})
        for s in e.get("sites") or []:
            if s.get("id") == sid:
                s.update(kw)
                ve.jsave(ve.pdir(vid) / "edit.json", e)
                return dict(s)
    return None


def geo(vid, sid, mode):
    return ve.jload(sdir(vid, sid, mode) / "geo.json", None)


# ---------------- عکس گرفتن ----------------
def _chrome_capture(url, quote, mode, out):
    with _CAP_L:
        PROFILE.mkdir(parents=True, exist_ok=True)
        p = subprocess.run([shutil.which("node") or "/opt/homebrew/bin/node", CAPTURE], cwd=ve.MOD, capture_output=True, timeout=180,
                           input=json.dumps({"url": url, "quote": quote, "mode": mode, "out": str(out), "profile": str(PROFILE)}).encode())
    try:
        return json.loads(p.stdout.decode("utf-8", "replace") or "{}")
    except Exception:
        return {"ok": False, "error": True, "reason": (p.stderr.decode("utf-8", "replace") or "")[-300:]}


def _fc_credits():
    fc = shutil.which("firecrawl")
    if not fc:
        return None
    try:
        r = subprocess.run([fc, "credit-usage", "--json"], capture_output=True, text=True, timeout=30)
        return (json.loads(r.stdout).get("data") or {}).get("remainingCredits")
    except Exception:
        return None


# OCR خود macOS فارسی را با الفبای عربی می‌خواند (ى، ك به جای ی و ک و گ، ج به جای چ…) و نیم‌فاصله را فاصله می‌کند؛
# پس مقایسه حرف‌به‌حرف است، بدون فاصله و نشانه، با این حرف‌ها یکسان‌شده در هر دو طرف.
_OKEY = str.maketrans({"ي": "ی", "ى": "ی", "ئ": "ی", "ك": "ک", "گ": "ک", "چ": "ج", "پ": "ب", "ژ": "ز", "ة": "ه", "ۀ": "ه",
                       "أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ؤ": "و", **{c: str(i) for i, c in enumerate("۰۱۲۳۴۵۶۷۸۹")},
                       **{c: str(i) for i, c in enumerate("٠١٢٣٤٥٦٧٨٩")}})


def _okey(s):
    return re.sub(r"[\W_]+", "", (s or "").lower().translate(_OKEY))


def _ocr_locate(ocr, quote):
    """جای جمله روی کلمه‌های OCR، حرف‌به‌حرف (difflib): فشرده‌ترین خوشه‌ی بلوک‌های جور که دست‌کم ۷۰٪ جمله را بپوشاند و
    پهنایش از ۱٫۵ برابر جمله بیشتر نباشد. خروجی: جعبه‌ی هر خط (کسری) و امتیاز."""
    # ترتیب خواندن: تکه‌های هم‌ارتفاع یک خط دیداری‌اند (Vision خط را کنار پانویس‌ها می‌شکند)؛ فارسی راست‌به‌چپ، انگلیسی چپ‌به‌راست
    obs = list(enumerate(ocr.get("lines") or []))
    rows = []
    for li, ln in sorted(obs, key=lambda x: x[1]["b"][1]):
        y, h = ln["b"][1], ln["b"][3]
        r = next((r for r in rows if abs((r["y"] + r["h"] / 2) - (y + h / 2)) < 0.5 * min(h, r["h"])), None)
        if r:
            r["items"].append((li, ln))
        else:
            rows.append({"y": y, "h": h, "items": [(li, ln)]})
    chars, owner = [], []
    for r in rows:
        txt = "".join(ln["t"] for _, ln in r["items"])
        rtl = len(re.findall(r"[\u0600-\u06FF]", txt)) > len(re.findall(r"[A-Za-z]", txt))
        for li, ln in sorted(r["items"], key=lambda x: -x[1]["b"][0] if rtl else x[1]["b"][0]):
            ws = list(enumerate(ln.get("w") or []))
            for wi, w in (sorted(ws, key=lambda x: -x[1]["b"][0]) if rtl else ws):
                for ch in _okey(w["t"]):
                    chars.append(ch)
                    owner.append((li, wi))
    page, q = "".join(chars), _okey(quote)
    if len(q) < 6 or not page:
        return None, 0.0
    blocks = [b for b in difflib.SequenceMatcher(None, page, q, autojunk=False).get_matching_blocks() if b.size >= 2]
    best, j, acc = (0, 0, -1), 0, 0
    for i in range(len(blocks)):               # پنجره‌ی لغزان روی بلوک‌ها (به ترتیب جای‌شان در صفحه)
        if i > 0:
            acc -= blocks[i - 1].size
        j = max(j, i)
        if j == i:
            acc = blocks[i].size
            j = i + 1
        while j < len(blocks) and blocks[j].a + blocks[j].size - blocks[i].a <= 1.5 * len(q):
            acc += blocks[j].size
            j += 1
        if acc > best[0]:
            best = (acc, i, j - 1)
    score = best[0] / len(q)
    if best[2] < 0 or score < 0.7:
        return None, score
    hit = {owner[k] for bl in blocks[best[1]:best[2] + 1] for k in range(bl.a, bl.a + bl.size)}   # فقط کلمه‌هایی که واقعاً جورند
    lines = {}
    for li, wi in sorted(hit):
        x, y, w, h = ocr["lines"][li]["w"][wi]["b"]
        L = lines.setdefault(li, [x, y, x + w, y + h])
        L[0], L[1], L[2], L[3] = min(L[0], x), min(L[1], y), max(L[2], x + w), max(L[3], y + h)
    return [[x0, y0, x1 - x0, y1 - y0] for x0, y0, x1, y1 in sorted(lines.values(), key=lambda r: r[1])], score


def _ocr_tiled(vid, img, W, H):
    """OCR روی تصویر خیلی بلند (اسکرین‌شات کل صفحه): Vision آن را کوچک می‌کند و خط‌های ریز گم می‌شوند،
    پس برش‌های هم‌پوشان (۱٫۲ برابر عرض، ۱۵٪ هم‌پوشانی) جدا خوانده و جعبه‌ها به کل تصویر برگردانده می‌شوند."""
    if H <= 2.2 * W:
        return vv.mtool("ocr", img, vid=vid, timeout=600)
    th, lines = int(W * 1.2), []
    step = int(th * 0.85)
    tmp = Path(img).with_name("tile.png")
    y = 0
    while y < H:
        h = min(th, H - y)
        ve.run([ve.FFMPEG, "-v", "error", "-y", "-i", img, "-vf", f"crop={W}:{h}:0:{y}", tmp], vid)
        o = vv.mtool("ocr", tmp, vid=vid, timeout=600)
        for ln in o.get("lines") or []:
            fix = lambda b: [b[0], round((y + b[1] * h) / H, 5), b[2], round(b[3] * h / H, 5)]
            nb = fix(ln["b"])
            if any(abs(nb[1] - q["b"][1]) < 0.6 * nb[3] and q["t"] == ln["t"] for q in lines):   # همان خط در دو برش
                continue
            lines.append({"t": ln["t"], "c": ln.get("c"), "b": nb, "w": [{"t": w["t"], "b": fix(w["b"])} for w in ln.get("w") or []]})
        if y + h >= H:
            break
        y += step
    tmp.unlink(missing_ok=True)
    return {"w": W, "h": H, "lines": sorted(lines, key=lambda l: (l["b"][1], l["b"][0]))}


def _from_image(vid, sid, mode, img, quote, how, view_w, view_h):
    """یک تصویر کامل صفحه (Firecrawl یا اسکرین‌شات کاربر) → shot.jpg دور جمله + geo.json با OCR.
    view_w × view_h: اندازه‌ی پنجره‌ای که عکس با آن گرفته شده، بر حسب px CSS."""
    out = sdir(vid, sid, mode)
    out.mkdir(parents=True, exist_ok=True)
    norm = out / "full.png"
    r = vv.mtool("norm", img, norm, "4000", vid=vid)
    W, H = r.get("w") or 1, r.get("h") or 1
    ocr = _ocr_tiled(vid, norm, W, H)
    lines, score = _ocr_locate(ocr, quote)
    dpr = W / view_w
    vh = view_h
    css_h = H / dpr
    if lines:
        t0 = lines[0][1] * css_h
        y0 = max(0.0, t0 - 1.6 * vh)
        y1 = min(css_h, t0 + 1.4 * vh)
    else:
        y0, y1 = 0.0, min(css_h, 1.4 * vh)
    y1 = max(y1, min(css_h, y0 + vh))
    ve.run([ve.FFMPEG, "-v", "error", "-y", "-i", norm, "-vf", f"crop={W}:{int((y1 - y0) * dpr) // 2 * 2}:0:{int(y0 * dpr)}",
            "-q:v", "3", out / "shot.jpg"], vid)
    rel = [[round(x * view_w, 1), round(y * css_h - y0, 1), round(w * view_w, 1), round(h * css_h, 1)] for x, y, w, h in lines or []]
    g = {"ok": bool(rel), "how": how if rel else "manual", "score": round(score, 2), "dir": "rtl" if re.search(r"[؀-ۿ]", quote or "") else "ltr",
         "lines": rel, "target": rel[0][1] if rel else 0, "y0": round(y0, 1), "shot": {"w": view_w, "h": round(y1 - y0, 1)},
         "view": {"w": view_w, "h": round(vh), "dpr": round(dpr, 3)}, "viewportOnly": False, "mode": mode}
    norm.unlink(missing_ok=True)
    return g


def _firecrawl(vid, sid, mode, url, quote):
    left = _fc_credits()
    if left is None or left < FC_MIN:
        return None, f"Firecrawl در دسترس نیست یا اعتبارش کم است ({left if left is not None else '—'})"
    out = sdir(vid, sid, mode)
    out.mkdir(parents=True, exist_ok=True)
    js = out / "fc.json"
    # Firecrawl همیشه نمای دسکتاپ ۱۹۲۰×۱۰۸۰ می‌گیرد (حتی برای قاب گوشی)؛ هر بار ۱ اعتبار
    ve.run([shutil.which("firecrawl"), "scrape", url, "--format", "markdown", "--full-page-screenshot", "--json", "-o", js],
           vid, timeout=180, cwd=out)
    d = ve.jload(js, {})
    shot = d.get("screenshot") or (d.get("data") or {}).get("screenshot")
    if not shot or not str(shot).startswith("https://"):
        return None, "Firecrawl عکسی برنگرداند"
    tmp = out / "fc.png"
    req = urllib.request.Request(shot, headers={"User-Agent": vv.UA})
    with urllib.request.urlopen(req, timeout=60) as r, open(tmp, "wb") as f:
        f.write(r.read(80 * 1024 * 1024))
    g = _from_image(vid, sid, mode, tmp, quote, "firecrawl", 1920, 1080)
    tmp.unlink(missing_ok=True)
    g.update(title=((d.get("metadata") or {}).get("title") or "")[:200], finalUrl=url, via="firecrawl")
    return g, ""


def capture(vid, sid, mode):
    """عکس یک حالت: Chrome؛ مسدود → Firecrawl؛ وضعیت و geo.json در دیسک."""
    s = sget(vid, sid)
    if not s:
        return
    out = sdir(vid, sid, mode)
    out.mkdir(parents=True, exist_ok=True)
    r = _chrome_capture(s["url"], s.get("quote") or "", mode, out)
    note = ""
    if r.get("blocked") or (r.get("error") and not r.get("notFound")):
        g, why = _firecrawl(vid, sid, mode, s["url"], s.get("quote") or "") if not s.get("fcTried", {}).get(mode) else (None, "")
        supdate(vid, sid, fcTried={**(s.get("fcTried") or {}), mode: True})
        if g:
            r = g
        else:
            note = why
    if (out / "shot.jpg").exists() and (r.get("ok") or r.get("notFound") or r.get("lines") is not None):
        g = {k: r.get(k) for k in ("ok", "how", "score", "dir", "lines", "target", "y0", "shot", "view", "viewportOnly", "mode", "via")}
        g["lines"] = g.get("lines") or []
        g["shot"] = g.get("shot") or {"w": (r.get("view") or {}).get("w", 1024), "h": (r.get("view") or {}).get("h", 768)}
        g["view"] = g.get("view") or {"w": 1024, "h": 768, "dpr": 2}
        ve.jsave(out / "geo.json", g)
        _thumbs(vid, sid, mode)
        st = "ready" if g["lines"] else "nomatch"
        supdate(vid, sid, status=st, err="" if st == "ready" else "جمله در صفحه پیدا نشد؛ متن جمله را اصلاح کن یا روی عکس کادر بکش.",
                title=(r.get("title") or s.get("title") or "")[:200], finalUrl=(r.get("finalUrl") or s["url"])[:1000],
                how=g.get("how") or "", via=g.get("via") or "chrome")
    else:
        why = r.get("reason") or "صفحه باز نشد"
        supdate(vid, sid, status="blocked" if r.get("blocked") else "error",
                err=(f"سایت جلوی عکس گرفتن را گرفت ({why})" if r.get("blocked") else why)[:300] + (f"؛ {note}" if note else "")
                + "؛ اسکرین‌شات خودت را بده.")


def _thumbs(vid, sid, mode):
    out = sdir(vid, sid, mode)
    g = ve.jload(out / "geo.json", {})
    vv.mtool("norm", out / "shot.jpg", out / "view.jpg", "1400", vid=vid)
    # بندانگشتی: یک پنجره دور جمله
    try:
        dpr = (g.get("view") or {}).get("dpr") or 2
        sw = (g.get("shot") or {}).get("w") or 1024
        vh = (g.get("view") or {}).get("h") or 768
        t = max(0.0, (g.get("target") or 0) - 0.35 * vh)
        h = min(((g.get("shot") or {}).get("h") or vh) - t, vh)
        ve.run([ve.FFMPEG, "-v", "error", "-y", "-i", out / "shot.jpg", "-vf",
                f"crop={int(sw * dpr) // 2 * 2}:{max(2, int(h * dpr) // 2 * 2)}:0:{int(t * dpr)},scale=480:-2", "-q:v", "4", out / "thumb.jpg"], vid)
    except Exception:
        vv.mtool("norm", out / "shot.jpg", out / "thumb.jpg", "480", vid=vid)


def from_upload(vid, sid, img):
    """اسکرین‌شات خود کاربر برای این سایت: OCR → جای جمله؛ اگر پیدا نشد، کاربر کادر می‌کشد."""
    s = sget(vid, sid)
    r = vv.mtool("norm", img, sdir(vid, sid) / "up.png", "4000", vid=vid)
    w, h = r.get("w") or 1080, r.get("h") or 1080
    if w / h < 0.75:                    # اسکرین‌شات گوشی → قاب گوشی
        mode, view_w, view_h = "mobile", 390, 844
    else:                               # اسکرین‌شات مک (Retina: دو برابر) → قاب مرورگر
        mode, view_w = "desktop", min(1440, max(800, int(w / 2)))
        view_h = int(view_w * 0.62)
    if mode != (s.get("mode") or "desktop"):   # قاب با شکل اسکرین‌شات جور می‌شود
        with ve.plock(vid):
            e = ve.jload(ve.pdir(vid) / "edit.json", {})
            for x in e.get("sites") or []:
                if x.get("id") == sid:
                    x["mode"] = mode
            for v in e.get("vis") or []:
                if v.get("kind") == "site" and v.get("sid") == sid:
                    v["tpl"] = "phone" if mode == "mobile" else "browser"
            ve.jsave(ve.pdir(vid) / "edit.json", e)
    g = _from_image(vid, sid, mode, sdir(vid, sid) / "up.png", s.get("quote") or "", "ocr", view_w, view_h)
    g["via"] = "upload"
    ve.jsave(sdir(vid, sid, mode) / "geo.json", g)
    _thumbs(vid, sid, mode)
    supdate(vid, sid, status="ready" if g["lines"] else "nomatch", via="upload", how=g["how"],
            err="" if g["lines"] else "جمله روی اسکرین‌شات پیدا نشد؛ روی عکس کادر هایلایت بکش.")


def set_boxes(vid, sid, boxes):
    """کادرهای هایلایت دستی (کسری از view.jpg) → خط‌ها بر حسب px CSS همان shot."""
    s = sget(vid, sid)
    mode = s.get("mode") or "desktop"
    g = geo(vid, sid, mode) or {}
    sw, sh = (g.get("shot") or {}).get("w") or 1024, (g.get("shot") or {}).get("h") or 768
    g["lines"] = [[round(x * sw, 1), round(y * sh, 1), round(w * sw, 1), round(h * sh, 1)] for x, y, w, h in boxes][:12]
    g["lines"].sort(key=lambda r: r[1])
    g["target"] = g["lines"][0][1] if g["lines"] else 0
    g["how"], g["ok"] = "manual", bool(g["lines"])
    ve.jsave(sdir(vid, sid, mode) / "geo.json", g)
    supdate(vid, sid, status="ready" if g["lines"] else "nomatch", how="manual", err="")


# ---------------- کارگر عکس‌ها ----------------
_SW, _SWL = {}, threading.Lock()


def sites_kick(vid, on_change=None):
    with _SWL:
        t = _SW.get(vid)
        if t and t.is_alive():
            return
        t = threading.Thread(target=_site_worker, args=(vid, on_change), daemon=True)
        _SW[vid] = t
        t.start()


def sites_busy(vid):
    with _SWL:
        t = _SW.get(vid)
        return bool(t and t.is_alive())


def _site_worker(vid, on_change):
    while True:
        s = next((x for x in slist(vid) if x.get("status") in ("queued", "upload")), None)
        if not s:
            return
        sid, st, rev = s["id"], s["status"], s.get("rev", 0)
        supdate(vid, sid, status="capturing", err="")
        try:
            if st == "upload":
                up = next(iter(sorted(sdir(vid, sid).glob("upload.*"))), None)
                from_upload(vid, sid, up)
            else:
                capture(vid, sid, s.get("mode") or "desktop")
        except Exception as e:
            supdate(vid, sid, status="error", err=str(e)[:300])
        cur = sget(vid, sid)
        if cur and cur.get("rev", 0) != rev:              # نشانی یا جمله وسط کار عوض شد
            supdate(vid, sid, status="queued")
        if on_change:
            try:
                on_change(vid, sid)
            except Exception:
                pass


# ---------------- پیدا کردن با Claude (وب) ----------------
SITE_RULES = """کار تو:
۱) جاهایی را پیدا کن که گوینده به یک منبع مشخص اشاره می‌کند: گزارش یا آمار یک سایت (مثل «طبق گزارش لینکدین»)، صفحه‌ی قیمت یک سرویس، مقاله، خبر، پست یک آدم مشهور در X، یا جمله‌ای که از کسی نقل می‌کند. فقط جاهایی که نشان دادن خود منبع واقعاً به بیننده کمک می‌کند؛ حداکثر ۴ مورد.
۲) برای هر کدام با WebSearch منبع اصلی و معتبر را پیدا کن (خود سایت لینکدین، خود صفحه‌ی قیمت، خود پست؛ نه وبلاگ دست‌دوم، مگر منبع اصلی در دسترس نباشد) و با WebFetch همان صفحه را بخوان.
۳) از متن همان صفحه **عین یک جمله یا بخش کوتاه** (حداکثر ۲۵۰ حرف) را کپی کن که حرف گوینده را نشان می‌دهد: کلمه‌به‌کلمه، با همان زبان صفحه، بدون ترجمه، بدون خلاصه و بدون تغییر حتی یک حرف. این جمله بعداً در خود صفحه جست‌وجو و هایلایت می‌شود. اگر جمله‌ای که حرف گوینده را تأیید کند پیدا نکردی، آن مورد را نیاور.
۴) url نشانی دقیق همان صفحه است (نه صفحه‌ی جست‌وجو یا خلاصه‌ی گوگل).
۵) w0..w1 بازه‌ی کلمه‌هایی است که قاب سایت روی ویدیو می‌ماند (حدود ۴ تا ۸ ثانیه، از همان جایی که اسم منبع می‌آید). hw0..hw1 کلمه‌هایی داخل همین بازه است که هم‌زمان با گفتنشان، ماژیک روی جمله کشیده می‌شود (همان‌جا که گوینده محتوای جمله را می‌گوید).
۶) frame: phone برای پست X یا اینستاگرام و صفحه‌هایی که روی گوشی دیده می‌شوند، browser برای بقیه.
۷) منبع ساختگی، حدسی یا از حافظه ممنوع است؛ فقط چیزی که خودت در صفحه دیدی.
summary یک جمله به فارسی ساده: چه منبع‌هایی پیدا شد (یا چرا هیچ)."""


def site_prompt(dv, comment="", current=None):
    words, fix, tm = dv["words"], dv["edit"].get("fix") or {}, dv["tmap"]
    rows = []
    for w in words:
        t = ve.disp(words, fix, w["i"]).strip()
        if w["i"] not in dv["cut"] and t:
            rows.append(f"{w['i']}|{t}|{tm.out(w['s']):.1f}")
    kind = "ریلز عمودی (حرف زدن جلوی دوربین)" if dv.get("src_kind", dv["kind"]) == "reel" else "ضبط صفحه‌ی کامپیوتر (آموزش یا دمو)"
    parts = [f"تو پژوهشگر و تدوینگر ویدیوهای کوتاه فارسی هستی. امروز {time.strftime('%Y-%m-%d')} است. ویدیو: {kind}، "
             f"{tm.dur:.0f} ثانیه بعد از برش. وقتی گوینده از یک منبع حرف می‌زند، خود صفحه‌ی آن منبع با هایلایت همان جمله روی ویدیو می‌آید.",
             "کلمه‌های ویدیو بعد از برش. قالب هر خط: اندیس|کلمه|زمان در خروجی (ثانیه):\n<<<WORDS\n" + "\n".join(rows) + "\nWORDS>>>",
             SITE_RULES]
    if current:
        parts.append("ارجاع‌های فعلی (برای بازنویسی):\n" + json.dumps(current, ensure_ascii=False))
    if comment:
        parts.append("نظر کاربر (مهم‌ترین دستور): " + comment)
    parts.append('خروجی فقط یک JSON بین این دو نشانه، بدون هیچ توضیح دیگر:\n<<<SITES\n'
                 '{"sites": [{"w0": 40, "w1": 62, "hw0": 47, "hw1": 55, "claim": "حرف گوینده، کوتاه", "url": "https://…", '
                 '"quote": "exact sentence copied from the page", "title": "", "frame": "browser", "why": ""}], "summary": ""}\nSITES>>>')
    return "\n\n".join(parts)


def _clean_sites(data, dv):
    n, out = len(dv["words"]), []
    for x in (data.get("sites") or [])[:6]:
        try:
            w0, w1 = int(x.get("w0")), int(x.get("w1"))
        except Exception:
            continue
        url, quote = safe_url(str(x.get("url") or "")), str(x.get("quote") or "").strip()
        if not url or len(quote) < 6:
            continue
        w0, w1 = max(0, min(w0, w1)), min(n - 1, max(w0, w1))
        span = vv._kept_span(w0, w1, dv)
        if not span:
            continue
        try:
            hw0, hw1 = int(x.get("hw0")), int(x.get("hw1"))
            hw0, hw1 = max(span[0], min(hw0, hw1)), min(span[1], max(hw0, hw1))
        except Exception:
            hw0 = hw1 = None
        out.append({"w0": span[0], "w1": span[1], "hw0": hw0, "hw1": hw1, "url": url, "quote": quote[:400],
                    "claim": str(x.get("claim") or "")[:200], "title": str(x.get("title") or "")[:200],
                    "tpl": "phone" if x.get("frame") == "phone" else "browser", "why": str(x.get("why") or "")[:200]})
    out.sort(key=lambda c: c["w0"])
    res = []
    for c in out:                                            # دو قاب سایت روی هم نمی‌افتند
        if res and c["w0"] <= res[-1]["w1"]:
            continue
        res.append(c)
    return res


def find_sites(vid, comment="", step=lambda s: None, on_change=None):
    """Claude منبع‌ها را با وب پیدا می‌کند؛ هر کدام یک ارجاع (sites) و یک قاب (vis، kind=site) می‌شود؛ بعد عکس‌ها در صف.
    ارجاع‌هایی که کاربر خودش گذاشته دست نمی‌خورند. گرافیک خودکاری که با قاب سایت هم‌زمان است، کنار می‌رود."""
    dv = ve.derive(vid)
    found, summary = [], "حرفی در این ویدیو نیست."
    if any(w["i"] not in dv["cut"] for w in dv["words"]):
        step("Claude دارد منبع‌هایی را که درباره‌شان حرف می‌زنی در وب پیدا می‌کند…")
        cur = [{k: s.get(k) for k in ("url", "quote", "claim")} for s in slist(vid) if s.get("src") != "user"]
        res = ve.ask(site_prompt(dv, comment, cur if comment else None), vid, timeout=2400, web=True, effort="high")
        data = ve.json_block(res, "<<<SITES", "SITES>>>")
        if not data:
            (ve.pdir(vid) / "sites.last-output.txt").write_text(res or "", encoding="utf-8")
            raise RuntimeError("جواب Claude برای منبع‌ها قابل خواندن نبود.")
        found, summary = _clean_sites(data, dv), str(data.get("summary") or "")[:400]
    stamp = int(time.time() * 1000)
    with ve.plock(vid):
        e = ve.jload(ve.pdir(vid) / "edit.json", {})
        old = {s["id"] for s in e.get("sites") or [] if s.get("src") != "user"}
        e["sites"] = [s for s in e.get("sites") or [] if s.get("src") == "user"]
        vis = [v for v in e.get("vis") or [] if not (v.get("kind") == "site" and v.get("sid") in old)]
        new_vis, pos = [], default_pos(vid)
        for k, c in enumerate(found):
            sid, oid = f"s{stamp}{k}", f"w{stamp}{k}"
            e["sites"].append({"id": sid, "url": c["url"], "quote": c["quote"], "claim": c["claim"], "title": c["title"],
                               "mode": FRAME[c["tpl"]], "status": "queued", "src": "claude", "rev": 0, "created": ve.now()})
            new_vis.append({"id": oid, "kind": "site", "sid": sid, "tpl": c["tpl"], "w0": c["w0"], "w1": c["w1"], "hw0": c["hw0"],
                            "hw1": c["hw1"], "on": True, "src": "claude", "pos": pos, "size": "m", "why": c["why"] or c["claim"]})
        # گرافیک خودکار Claude که با قاب سایت تازه هم‌زمان است کنار می‌رود (شمارنده می‌ماند)
        def clash(v):
            return (v.get("src") == "claude" and v.get("kind") == "gfx" and v.get("tpl") != "counter"
                    and any(v["w0"] <= n["w1"] and n["w0"] <= v["w1"] for n in new_vis))
        vis = [v for v in vis if not clash(v)]
        e["vis"] = sorted(vis + new_vis, key=lambda v: v["w0"])
        gone = {v["id"] for v in e.get("vis") or []}
        e["sfx"] = [x for x in e.get("sfx") or [] if not x.get("link") or x["link"] in gone]
        e["sitesSummary"], e["sitesAt"] = summary, ve.now()
        if comment:
            e.setdefault("notes", {}).setdefault("sites", []).append(comment[:500])
        ve.jsave(ve.pdir(vid) / "edit.json", e)
    for sid in old:
        shutil.rmtree(sdir(vid, sid), ignore_errors=True)
    _add_sfx(vid)
    sites_kick(vid, on_change)


def _add_sfx(vid):
    """افکت ورود قاب سایت و صدای ماژیک سر هایلایت (src=vis، link به همان قاب)."""
    dv = ve.derive(vid)
    with ve.plock(vid):
        e = ve.jload(ve.pdir(vid) / "edit.json", {})
        site_ids = {v["id"] for v in e.get("vis") or [] if v.get("kind") == "site"}
        e["sfx"] = [x for x in e.get("sfx") or [] if x.get("link") not in site_ids]
        dv["edit"] = e
        e["sfx"] = sorted(e["sfx"] + vv._vis_sfx([v for v in e.get("vis") or [] if v.get("kind") == "site" and v.get("on") is not False], dv),
                          key=lambda x: (x["w"], float(x.get("dt") or 0)))
        ve.jsave(ve.pdir(vid) / "edit.json", e)


# ---------------- روی کادر و در ترکیب ----------------
def resolve_site(vid, dv, v, faces):
    """زمان و جعبه‌ی قاب سایت؛ None اگر عکسش آماده نیست (skip)."""
    s = sget(vid, v.get("sid"))
    if not s:
        return None, "site"
    mode = FRAME.get(v.get("tpl"), "desktop")
    g = geo(vid, v["sid"], mode)
    if not g or not (sdir(vid, v["sid"], mode) / "shot.jpg").exists():
        return None, "site"
    span = vv._kept_span(int(v.get("w0", 0)), int(v.get("w1", 0)), dv)
    if not span:
        return None, "cut"
    scene = v.get("pos") == "scene"
    s0, e0 = vv._span_time(dv, *span)
    s0 = max(0.0, s0 - vv.LEAD)
    e0 = min(dv["tmap"].dur, max(e0 + 0.25, s0 + (4.2 if scene else 3.0)))
    hs = he = None
    if isinstance(v.get("hw0"), int) and isinstance(v.get("hw1"), int):
        hsp = vv._kept_span(v["hw0"], v["hw1"], dv)
        if hsp:
            hs, he = vv._span_time(dv, *hsp)
    lead = SCENE_HL if scene else 1.6
    if hs is None or hs < s0 + lead - 0.1:                # هایلایت بعد از ورود و اسکرول (در صحنه، بعد از زوم)
        hs = s0 + lead
    he = min(e0 - (0.6 if scene else 0.4), max(he or 0, hs + 0.7))
    c = {"_s": s0, "_e": e0, "tpl": v.get("tpl") or "browser", "kind": "site", "pos": v.get("pos"), "size": v.get("size")}
    W, H = ve.CANVAS[dv["kind"]]
    box = _site_box(c, dv, faces, dv["words"][span[0]]["s"], dv["words"][span[1]]["e"])
    return {"s": round(s0, 3), "e": round(e0, 3), "hs": round(hs, 3), "he": round(he, 3), "box": box, "geo": g, "site": s,
            "scene": scene}, None


def join_scenes(vis, gap=1.0):
    """دو صحنه‌ی پشت‌سرهم (فاصله‌ی کمتر از gap ثانیه، یا هم‌پوشان) یک زمینه‌ی سرمه‌ای پیوسته دارند: اولی تا شروع دومی می‌ماند
    و زمینه‌اش جمع نمی‌شود (joinNext)، دومی بی‌انیمیشن ورود زمینه شروع می‌شود (joinPrev). وگرنه زمینه‌ی اولی جمع می‌شد و
    دومی دوباره بالا می‌آمد و گوینده نیم ثانیه وسطشان پیدا می‌شد (۲۰۲۶-۱۰-۰۸، کاربر می‌خواهد در سایت‌ها تصویرش کامل برود)."""
    sc = sorted((x for x in vis if x.get("scene") and not x.get("skip") and x.get("on") is not False), key=lambda x: x["s"])
    for a, b in zip(sc, sc[1:]):
        if b["s"] - a["e"] < gap and b["s"] - a["s"] >= 2.0:
            a["e"] = b["s"]
            if "hs" in a:                  # قاب سایت؛ صحنه‌ی عکس و ویدیو (قالب scene) ماژیک ندارد
                a["he"] = round(max(a["hs"] + 0.3, min(a["he"], a["e"] - 0.6)), 3)
            a["joinNext"] = b["joinPrev"] = True


def _site_box(c, dv, faces, a_src, b_src):
    W, H = ve.CANVAS[dv["kind"]]
    k = vv.VSIZE.get(c.get("size") or "m", 1.0)
    if c.get("pos") == "scene":            # صحنه: قاب بزرگ وسط کادر؛ زیر نوار بالای اینستاگرام و بالای زیرنویس پایین
        reel = dv["kind"] == "reel"
        if reel:
            # ۲۰۲۶-۱۰-۰۸، درخواست کاربر: گوشی با نسبت واقعی ۹:۱۹٫۵ فقط ۴۵۶px پهنا داشت. حالا قاب (گوشی و مرورگر) کل ناحیه‌ی آزاد
            # ریلز را می‌گیرد: زیر نوار بالا (۲۵۰px)، بالای زیرنویس، چپِ ستون لایک و کامنت (x≈۹۶۰، «راهنمای اینستاگرام»).
            # قاب با زوم صحنه (SCENE_ZOOM) بزرگ می‌شود، پس از اول کوچک‌تر است تا بعد از زوم هم روی زیرنویس و ستون لایک نیفتد.
            o = dv["opts"]
            x0, x1, y0 = 40, 950, 270
            y1 = int(H * ve.zones_for("reel", ve.cap_box_h("reel", o.get("style"), o.get("size", "m")))["bot"]) - 22
            w, h = (x1 - x0) / SCENE_ZOOM, (y1 - y0) / SCENE_ZOOM
            return {"x": int(x0 + (x1 - x0 - w) / 2), "y": int(y0 + (y1 - y0 - h) / 2), "w": int(w), "h": int(h)}
        else:
            top, bot = int(H * 0.06), int(H * 0.82)
        h = bot - top
        if c["tpl"] == "phone":
            w = min(W - 80, int(h * 9 / 19.5))
            h = min(h, int(w * 19.5 / 9))
        else:
            w = min(W - 160, int(h * 1.5))
        return {"x": int((W - w) / 2), "y": int(top + (bot - top - h) / 2), "w": int(w), "h": int(h)}
    if c["tpl"] == "phone":
        return vv._layout({**c, "kind": "media", "tpl": "phone"}, dv, faces, 9 / 19.5, a_src, b_src)
    ivs, (lo, hi), fx = vv._free_band(dv, faces, a_src, b_src, c["_s"], c["_e"])
    pos = c.get("pos") or "auto"
    if pos == "top":
        band = (lo, H * 0.6)
    elif pos == "mid":
        band = (H * 0.22, H * 0.78)
    elif pos == "bot":
        band = (H * 0.4, hi)
    else:
        band = max(ivs, key=lambda iv: iv[1] - iv[0]) if ivs else (lo, hi)
    if dv["kind"] == "reel":
        bw = min(W - 60, 1000) * min(1.0, k)
        bh = max(520.0, min(band[1] - band[0] - 30, 1000 * k))
        y = band[0] + max(0.0, (band[1] - band[0] - bh) / 2) if band[1] - band[0] - 30 >= bh else band[0] + 10
        y = min(max(lo - 20, y), H - bh - 20)
        return {"x": int((W - bw) / 2), "y": int(y), "w": int(bw), "h": int(bh)}
    bw, bh = W * 0.56 * k, H * 0.78 * k
    return {"x": int(W - bw - 70), "y": int((H - bh) / 2), "w": int(bw), "h": int(bh)}


CSS = """
.ov-web .ovi{border-radius:26px;overflow:hidden;background:#fff;box-shadow:0 30px 80px rgba(0,0,0,.5),0 0 0 2px rgba(255,255,255,.35)}
.ov-web .wb-bar{height:62px;background:#eef1f5;display:flex;align-items:center;gap:16px;padding:0 22px;direction:ltr;border-bottom:1px solid #d9dee6}
.ov-web .wb-dots{display:flex;gap:9px}
.ov-web .wb-dots b{width:15px;height:15px;border-radius:50%;background:#ff5f57}
.ov-web .wb-dots b+b{background:#febc2e}
.ov-web .wb-dots b+b+b{background:#28c840}
.ov-web .wb-url{flex:1;min-width:0;height:40px;border-radius:20px;background:#fff;display:flex;align-items:center;gap:10px;padding:0 18px;
  font-family:"Vazirmatn",sans-serif;font-size:24px;font-weight:600;color:#34404f;white-space:nowrap;overflow:hidden}
.ov-web .wb-url i{width:14px;height:17px;border:3px solid #6b7686;border-radius:4px;position:relative;flex:0 0 auto;margin-top:5px}
.ov-web .wb-url i::before{content:"";position:absolute;left:1px;top:-11px;width:6px;height:9px;border:3px solid #6b7686;border-bottom:0;border-radius:6px 6px 0 0}
.ov-web .wb-view,.ov-sph .scr{position:relative;overflow:hidden;background:#fff}
.ov-web .wb-view{height:calc(100% - 62px)}
.wb-page{position:absolute;left:0;top:0;transform-origin:0 0}
.wb-page img{position:absolute;left:0;top:0;width:100%;height:100%}
.wb-page .dim{position:absolute;inset:0;background:rgba(9,18,28,.58);opacity:0}
.wb-page .lit{position:absolute;background-repeat:no-repeat;opacity:0;border-radius:4px}
.wb-page .mk{position:absolute;background:rgba(255,219,88,.7);mix-blend-mode:multiply;border-radius:5px}
.ov-sph .ovi{background:#0b0f14;border-radius:70px;padding:18px;box-shadow:0 30px 80px rgba(0,0,0,.55),inset 0 0 0 3px #2c3644}
.ov-sph .scr{width:100%;height:100%;border-radius:54px}
.ov-sph .isl{position:absolute;top:36px;left:50%;width:126px;height:36px;margin-left:-63px;background:#000;border-radius:20px;z-index:2}
.ov.ov-scene{z-index:7}
.ov-scene .sc-bg{position:absolute;inset:0;background:radial-gradient(120% 75% at 50% 40%,#24507f 0%,#1a3c64 55%,#0f2540 100%)}
.ov-scene .sc-bg::after{content:"";position:absolute;inset:0;background-image:radial-gradient(rgba(255,255,255,.07) 1.6px,transparent 1.8px);background-size:38px 38px}
.ov-scene .sc-fr{position:absolute}
"""


def comp_site(vid, dv, v, mode, assets):
    """(html، خط‌های تایم‌لاین): قاب وارد می‌شود، صفحه تا جمله اسکرول می‌کند، بقیه‌ی صفحه تیره و جمله بزرگ می‌شود، ماژیک
    هم‌زمان با کلمه‌های hw0..hw1 روی خط‌ها کشیده می‌شود (انگلیسی چپ‌به‌راست، فارسی راست‌به‌چپ)."""
    g, b, i, s, e = v["geo"], v["box"], v["id"], v["s"], v["e"]
    hs, he = v["hs"], v["he"]
    phone = v["tpl"] == "phone"
    md = FRAME[v["tpl"]]
    shot = vv._copy(sdir(vid, v["sid"], md) / "shot.jpg", assets, f"site-{v['sid']}-{md}.jpg")
    sw, sh = g["shot"]["w"], g["shot"]["h"]
    rtl = g.get("dir") == "rtl"
    lines = g.get("lines") or []
    bar = 0 if phone else 62
    aw, ah = (b["w"] - 36, b["h"] - 36) if phone else (b["w"], b["h"] - bar)
    sv = aw / sw                                            # px CSS صفحه → px کادر
    vis_h = ah / sv
    tgt = g.get("target") or (lines[0][1] if lines else 0)
    y_end = -min(max(0.0, sh * sv - ah), max(0.0, (tgt - 0.36 * vis_h) * sv))
    pad = 3
    marks, lits = [], []
    for k, (x, y, w, h) in enumerate(lines):
        x0, y0, w0, h0 = x - pad, y - pad, w + 2 * pad, h + 2 * pad
        lits.append(f'<i class="lit" id="{i}l{k}" style="left:{x0:.1f}px;top:{y0:.1f}px;width:{w0:.1f}px;height:{h0:.1f}px;'
                    f'background-image:url({shot});background-size:{sw}px {sh}px;background-position:{-x0:.1f}px {-y0:.1f}px"></i>')
        marks.append(f'<i class="mk" id="{i}k{k}" style="left:{x0:.1f}px;top:{y0:.1f}px;width:{w0:.1f}px;height:{h0:.1f}px;'
                     f'transform-origin:{"100%" if rtl else "0%"} 50%"></i>')
    page = (f'<div class="wb-page" id="{i}p" style="width:{sw}px;height:{sh}px"><img src="{shot}" alt="">'
            f'<i class="dim" id="{i}d"></i>{"".join(lits)}{"".join(marks)}</div>')
    dom = escape(domain(v["site"].get("finalUrl") or v["site"].get("url") or ""))
    scene = v.get("scene")
    cls = "ov-sph" if phone else "ov-web"
    if phone:
        inner = f'<div class="ovi"><div class="scr">{page}</div><i class="isl"></i></div>'
    else:
        inner = (f'<div class="ovi"><div class="wb-bar"><span class="wb-dots"><b></b><b></b><b></b></span>'
                 f'<span class="wb-url"><i></i><bdi>{dom}</bdi></span></div><div class="wb-view">{page}</div></div>')
    timing = f'data-start="{s}" data-duration="{round(e - s, 3)}" data-track-index="1"'
    tl = [f'tl.set("#{i}p",{{x:0,y:0,scale:{sv:.5f},transformOrigin:"0 0"}},{s});']
    if scene:                              # زمینه از پایین بالا می‌آید و گوینده را می‌پوشاند، بعد قاب از پایین بالا می‌آید
        W, H = ve.CANVAS[dv["kind"]]
        html = (f'<div id="{i}" class="clip ov ov-scene" {timing} style="left:0;top:0;width:{W}px;height:{H}px"><i class="sc-bg" id="{i}g"></i>'
                f'<div class="sc-fr {cls}" id="{i}f" style="left:{b["x"]}px;top:{b["y"]}px;width:{b["w"]}px;height:{b["h"]}px">{inner}</div></div>')
        tl += [f'tl.set("#{i}g",{{clipPath:"inset(0% 0% 0% 0%)"}},{s});' if v.get("joinPrev") else   # صحنه‌ی قبلی زمینه را نگه داشته
               f'tl.fromTo("#{i}g",{{clipPath:"inset(100% 0% 0% 0%)"}},{{clipPath:"inset(0% 0% 0% 0%)",duration:.45,ease:"power3.inOut"}},{s});',
               # ورود با بالا آمدن کوتاه (نه از پایین کادر)، تا قاب بزرگ وسط ورود از پشت زیرنویس رد نشود (۲۰۲۶-۱۰-۰۸)
               f'tl.fromTo("#{i}f",{{opacity:0,y:80,scale:.92}},{{opacity:1,y:0,scale:1,duration:.7,ease:"power3.out"}},'
               f'{round(s + (0 if v.get("joinPrev") else .2), 3)});']
        t_scroll = round(s + .95, 3)
    else:
        html = (f'<div id="{i}" class="clip ov {cls}" {timing} style="left:{b["x"]}px;top:{b["y"]}px;width:{b["w"]}px;height:{b["h"]}px">'
                f'{inner}</div>')
        tl.append(f'tl.fromTo("#{i}",{{opacity:0,y:70,scale:.94}},{{opacity:1,y:0,scale:1,duration:.45,ease:"power3.out"}},{s});')
        t_scroll = round(s + .5, 3)
    if y_end < -2:
        tl.append(f'tl.to("#{i}p",{{y:{y_end:.1f},duration:.85,ease:"power2.inOut"}},{t_scroll});')
    if lines:
        ux0, uy0 = min(l[0] for l in lines), min(l[1] for l in lines)
        ux1, uy1 = max(l[0] + l[2] for l in lines), max(l[1] + l[3] for l in lines)
        z = min(2.6, max(1.0, (0.95 if scene else 0.9) * aw / max(1.0, (ux1 - ux0) * sv)), 0.6 * ah / max(1.0, (uy1 - uy0) * sv))
        sz = sv * max(1.0, z)
        cx, cy = (ux0 + ux1) / 2, (uy0 + uy1) / 2
        tx, ty = aw / 2 - cx * sz, ah / 2 - cy * sz
        t_zoom = round(max(t_scroll + .95, hs - .6), 3)
        tl.append(f'tl.to("#{i}p",{{x:{tx:.1f},y:{ty:.1f},scale:{sz:.5f},duration:.55,ease:"power2.inOut"}},{t_zoom});')
        if scene:                          # دوربین هم کمی به خود قاب نزدیک می‌شود تا زوم حس شود (لبه‌ها هنوز در کادر)
            tl.append(f'tl.to("#{i}f",{{scale:{SCENE_ZOOM},duration:.7,ease:"power2.inOut"}},{t_zoom});')
        tl.append(f'tl.to("#{i}d",{{opacity:1,duration:.4}},{t_zoom});')
        for k in range(len(lines)):
            tl.append(f'tl.to("#{i}l{k}",{{opacity:1,duration:.4}},{t_zoom});')
        tot = max(0.6, min(3.2, he - hs))
        widths = [max(1.0, l[2]) for l in lines]
        acc = hs
        for k, w in enumerate(widths):
            d = tot * w / sum(widths)
            tl.append(f'tl.fromTo("#{i}k{k}",{{scaleX:0}},{{scaleX:1,duration:{max(.12, d):.2f},ease:"none"}},{round(acc, 3)});')
            acc += d
    if scene:                              # قاب بالا می‌رود و محو می‌شود، بعد زمینه رو به بالا جمع می‌شود و گوینده برمی‌گردد
        tl.append(f'tl.to("#{i}f",{{opacity:0,y:-70,scale:.96,duration:.3,ease:"power2.in"}},'
                  f'{round(max(s + 1, e - (.35 if v.get("joinNext") else .55)), 3)});')
        if not v.get("joinNext"):          # صحنه‌ی بعدی بلافاصله می‌آید: زمینه می‌ماند تا گوینده وسطشان پیدا نشود
            tl.append(f'tl.to("#{i}g",{{clipPath:"inset(0% 0% 100% 0%)",duration:.4,ease:"power3.inOut"}},{round(max(s + 1.2, e - .4), 3)});')
    else:
        tl.append(f'tl.to("#{i}",{{opacity:0,y:-24,duration:.25,ease:"power2.in"}},{round(max(s + .5, e - .25), 3)});')
    return html, tl


def sites_view(vid):
    out = []
    for s in slist(vid):
        md = s.get("mode") or "desktop"
        th = sdir(vid, s["id"], md) / "thumb.jpg"
        g = geo(vid, s["id"], md) or {}
        sw, sh = (g.get("shot") or {}).get("w") or 1, (g.get("shot") or {}).get("h") or 1
        out.append({k: s.get(k) for k in ("id", "url", "quote", "claim", "title", "status", "err", "mode", "how", "via", "src")}
                   | {"domain": domain(s.get("finalUrl") or s.get("url") or ""), "v": int(th.stat().st_mtime) if th.exists() else 0,
                      "boxes": [[round(x / sw, 4), round(y / sh, 4), round(w / sw, 4), round(h / sh, 4)] for x, y, w, h in g.get("lines") or []]})
    return out
