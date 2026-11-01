"""کاور ریلز، کپشن و هشتگ (فاز ۶ تدوین ویدیو). انتشار دستی است: ویدیو و کاور دانلود می‌شوند.
(کد انتشار مستقیم نسخه‌ی اصلی هنوز این‌جاست ولی _site خاموش است؛ video.py هم کار publish را نمی‌پذیرد.)

- کاور: بهترین فریم‌های بخش‌های نگه‌داشته با Vision خود macOS (mediatool faceq: کیفیت عکس صورت، چشم باز، دهان، چرخش سر).
  تیتر روی یک قالب HTML می‌نشیند و Chrome از آن JPEG ۱۰۸۰×۱۹۲۰ می‌گیرد (modules/video/render-cover.mjs).
  متن فقط داخل برش ۳:۴ شبکه‌ی پروفایل (y بین ۲۴۰ و ۱۶۸۰) می‌آید، چون اینستاگرام کاور را در شبکه همان‌طور می‌بُرد.
  در ضبط صفحه، محوهای اطلاعات حساس روی فریم کاور هم اعمال می‌شوند.
- کپشن، هشتگ و پیشنهاد تیتر: Claude از متن نهایی ویدیو و هسته‌ی برند. حداکثر ۵ هشتگ: سقف خود اینستاگرام از دسامبر ۲۰۲۵
  (مرجع API هنوز ۳۰ می‌گوید، ولی خود اپ بیشتر را نمی‌گذارد).
- انتشار: ig.mp4 (H.264، صدای AAC ۴۸k، moov اول فایل، بدون edit list؛ طبق مشخصات ریلز Graph API) و cover.jpg مستقیم به
  Storage خصوصی سایت با آدرس امضاشده می‌روند (Vercel بدنه‌ی بیشتر از ۴٫۵ مگ را رد می‌کند). سایت container ریلز را می‌سازد،
  این‌جا وضعیتش تا FINISHED پرسیده می‌شود و فقط با کلیک کاربر media_publish می‌شود. توکن اینستاگرام هرگز از سایت بیرون نمی‌آید.
  هر container فقط یک بار منتشر می‌شود، پس «دوباره امتحان کن» ریلز تکراری نمی‌سازد.
  سایت سقف باکت را می‌گوید؛ اگر نامعلوم باشد (سقف کلی Storage زیر ۳۰۰ مگ، پیش‌فرض Supabase ۵۰ مگ) فایل تا ۴۵ مگ فشرده
  می‌شود، و اگر Storage باز هم فایل را بزرگ دانست، یک بار دیگر با ۴۵ مگ.
داده: data/videos/<id>/post.json و پوشه‌ی cover/ (cand/ فریم‌های پیشنهادی کوچک، f<ms>.jpg فریم کامل، cover.html، cover.jpg).
"""
import hashlib, http.client, json, re, shutil, ssl, tempfile, time
from contextlib import nullcontext
from html import escape
from pathlib import Path
from urllib.parse import urlparse
import video_engine as ve
import video_visuals as vv
import settings as cfg

RENDER_COVER = ve.MOD / "render-cover.mjs"
FONT = ve.MOD / "fonts" / "Vazirmatn-Variable.woff2"
CW, CH = 1080, 1920                        # کاور ریلز
GRID = (240, 1680)                         # برش ۳:۴ شبکه‌ی پروفایل از وسط کاور
TB = {"top": (330, 560), "bottom": (1040, 560)}             # (بالای کادر تیتر، ارتفاع بیشینه)؛ هر دو درون GRID
TPL = {"top": "تیتر بالا", "band": "کادر سرمه‌ای", "marker": "ماژیک زرد"}
POS = {"auto": "خودکار", "top": "بالا", "bottom": "پایین"}
ZOOMS = (1.0, 1.3, 1.6, 2.0)
TAG_MAX = 5                                # سقف هشتگ اینستاگرام از دسامبر ۲۰۲۵
CAP_MAX = 2200
IG_MAX = 290 * 1024 ** 2                   # سقف ریلز ۳۰۰ مگ؛ کمی حاشیه
SMALL_MAX = 45 * 1024 ** 2                 # وقتی Storage سایت فایل بزرگ را رد کرد
DUR_MIN, DUR_MAX = 3, 15 * 60              # مشخصات ریلز Graph API
PENDING_TTL = 20 * 3600                    # container منتشرنشده بعد از ۲۴ ساعت باطل می‌شود
POLL_LIMIT = 15 * 60
CANCEL = set()                             # vid هایی که کاربر «توقف» زده


def fa(s):
    return vv.fa_num(s)


# ---------------- داده ----------------
def pfile(vid):
    return ve.pdir(vid) / "post.json"


def cdir(vid):
    return ve.pdir(vid) / "cover"


def load(vid):
    return ve.jload(pfile(vid), {})


def update(vid, fn):
    with ve.plock(vid):
        p = load(vid)
        r = fn(p)
        ve.jsave(pfile(vid), p)
        return r


def tags_of(text):
    return re.findall(r"(?:^|\s)(#[^\s#]+)", text or "")


def full_caption(p):
    cap, tags = (p.get("caption") or "").strip(), " ".join((p.get("hashtags") or "").split())
    return cap + ("\n\n" + tags if cap and tags else tags)


def _img_size(f):
    out, _ = ve.run([ve.FFPROBE, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                     "-of", "json", f], timeout=30)
    s = (json.loads(out).get("streams") or [{}])[0]
    return int(s.get("width") or 0), int(s.get("height") or 0)


# ---------------- فریم‌های پیشنهادی ----------------
def face_score(faces):
    """کیفیت عکس صورت (Vision) × چشم باز × دهان نه‌چندان باز × رو به دوربین × صورت نه‌چندان ریز."""
    if not faces:
        return 0.0, None
    f = max(faces, key=lambda f: f["b"][2] * f["b"][3])
    q = float(f.get("q") or 0)
    eye, mouth = f.get("eye"), f.get("mouth")
    ef = 0.6 if eye is None else min(1.0, max(0.0, (eye - 0.12) / 0.12))
    mf = 1.0 if mouth is None else max(0.45, 1.0 - 1.6 * max(0.0, mouth - 0.06))   # وسط حرف زدن دهان باز است
    yf = 1.0 - min(0.5, max(0.0, abs(f.get("yaw") or 0) - 0.15) * 1.5)
    sf = 0.6 + 0.4 * min(1.0, f["b"][3] / 0.18)
    return q * ef * mf * yf * sf, [round(v, 4) for v in f["b"]]


def _faceq(paths, vid=None):
    rows = {}
    for i in range(0, len(paths), 120):                # آرگومان‌های خط فرمان کوتاه بماند
        part = [str(p) for p in paths[i:i + 120]]
        vv.ensure_mediatool(vid)
        out, _ = ve.run([vv.MEDIATOOL, "faceq", *part], vid, timeout=900)
        for ln in out.decode("utf-8", "replace").splitlines():
            if ln.startswith("{"):
                try:
                    r = json.loads(ln)
                    rows[r.get("f")] = r
                except Exception:
                    pass
    return rows


def find_cands(vid, say=lambda s: None):
    """هشت فریم: بهترین‌ها با دست‌کم ۳ ثانیه فاصله، و اگر نمای دیگری (دور/نزدیک) هست دو تا از آن هم."""
    dv = ve.derive(vid)
    d = ve.pdir(vid)
    src = d / "proxy.mp4"
    if not src.exists():
        raise RuntimeError("اول آماده‌سازی ویدیو باید تمام شود.")
    say("پیدا کردن بهترین فریم‌ها برای کاور…")
    dur = dv["dur"] or 1.0
    # هر N امین فریم proxy (۳۰ فریم ثابت)، با شماره‌ی فریم؛ فیلتر fps فریم را تا ربع ثانیه جابه‌جا برمی‌دارد و
    # کاور با فریمی که امتیاز گرفته فرق می‌کرد (یک بار چشم بسته).
    n = max(15, -(-int(dur * ve.FPS) // 600))
    screen = dv.get("src_kind") == "screen"
    with tempfile.TemporaryDirectory() as td:
        ve.run([ve.FFMPEG, "-v", "error", "-y", "-i", src, "-vf", f"select='not(mod(n,{n}))',scale=-2:'min(960,ih)'",
                "-fps_mode", "vfr", "-q:v", "4", f"{td}/%05d.jpg"], vid, timeout=1800)
        files = sorted(Path(td).glob("*.jpg"))
        at = lambda k: k * n / ve.FPS
        frames = [(at(k), f) for k, f in enumerate(files)
                  if any(a + 0.3 <= at(k) <= b - 0.3 for a, b in dv["keeps"])] or [(at(k), f) for k, f in enumerate(files)]
        if not frames:
            raise RuntimeError("فریمی از ویدیو خوانده نشد.")
        scored = []
        if not screen:
            rows = _faceq([f for _, f in frames], vid)
            for t, f in frames:
                s, face = face_score((rows.get(str(f)) or {}).get("faces") or [])
                scored.append((s, t, f, face))
        if not any(s > 0 for s, *_ in scored):        # ضبط صفحه یا بی‌صورت: فاصله‌ی برابر
            n = min(8, len(frames))
            scored = [(1.0 - i * 0.01, *frames[int((i + 0.5) * len(frames) / n)], None) for i in range(n)]
        picks = []

        def take(pool, k):
            for s in sorted(pool, key=lambda x: -x[0]):
                if len(picks) >= k:
                    return
                if s[0] > 0 and all(abs(s[1] - p[1]) >= 3.0 for p in picks):
                    picks.append(s)

        take(scored, 6)
        big = lambda s: s[3] is not None and s[3][3] >= 0.13
        if picks and picks[0][3] is not None:         # نمای دیگر (اگر بهترین‌ها نزدیک‌اند، دو تا از دورها؛ برعکس)
            take([s for s in scored if big(s) != big(picks[0])], len(picks) + 2)
        take(scored, 8)
        best = picks[0][1] if picks else None
        picks.sort(key=lambda s: s[1])
        cd = cdir(vid) / "cand"
        shutil.rmtree(cd, ignore_errors=True)
        cd.mkdir(parents=True, exist_ok=True)
        cands = []
        for s, t, f, face in picks:
            name = f"c{int(round(t * 1000))}.jpg"
            shutil.copy(f, cd / name)
            cands.append({"t": round(t, 3), "score": round(s, 3), "img": f"cand/{name}", "face": face,
                          "o": round(dv["tmap"].out(t), 2), "best": t == best})

    def put(p):
        p["cands"], p["candsAt"] = cands, ve.now()
        c = p.setdefault("cover", {})
        return not c.get("img")

    if update(vid, put):                               # هنوز کاوری انتخاب نشده: بهترین فریم
        b = next((c for c in cands if c["best"]), cands[0] if cands else None)
        if b:
            pick_frame(vid, b["t"])
    return cands


def frame_rel(t):
    return f"f{int(round(max(0.0, t) * 1000))}.jpg"


def ensure_frame(vid, t):
    """فریم کامل از master؛ در ضبط صفحه با همان محوهایی که در ویدیو هست (اطلاعات حساس روی کاور نیاید)."""
    d = ve.pdir(vid)
    f = cdir(vid) / frame_rel(t)
    if f.exists():
        return f
    f.parent.mkdir(parents=True, exist_ok=True)
    dv = ve.derive(vid)
    blurs = [(0.0, 1e6, box) for s, e, box in ve.screen_blurs(dv) if s - 0.05 <= t <= e + 0.05]
    cmd = [ve.FFMPEG, "-v", "error", "-y", "-ss", f"{max(0.0, t - 0.5 / ve.FPS):.4f}", "-i", d / "master.mp4", "-frames:v", "1"]
    if blurs:
        import video_screen as vsc
        W, H = _img_size(d / "master.mp4")
        g, last = vsc.blur_graph(blurs, W, H)
        cmd += ["-filter_complex", g.rstrip(";"), "-map", last]
    ve.run(cmd + ["-q:v", "2", f], vid, timeout=120)
    return f


def pick_frame(vid, t):
    p = load(vid)
    face = next((c.get("face") for c in p.get("cands") or [] if abs(c["t"] - t) < 0.01), None)
    ensure_frame(vid, t)

    def put(p):
        c = p.setdefault("cover", {})
        c.update({"src": "frame", "t": round(t, 3), "img": frame_rel(t), "face": face})
    update(vid, put)
    build_cover(vid)


def cover_upload(vid, data, ext):
    """عکس خود کاربر برای کاور: با mediatool به JPEG (چرخش EXIF اعمال‌شده) و جای صورتش."""
    cd = cdir(vid)
    cd.mkdir(parents=True, exist_ok=True)
    raw = cd / f"upload-raw{ext}"
    raw.write_bytes(data)
    try:
        vv.mtool("norm", raw, cd / "upload.tmp.jpg", "2600", vid=vid, timeout=120)   # JPEG؛ شفافیت روی سفید
        (cd / "upload.tmp.jpg").replace(cd / "upload.jpg")
    except Exception:
        raise RuntimeError("این عکس خوانده نشد؛ JPG، PNG یا HEIC بفرست.")
    finally:
        raw.unlink(missing_ok=True)
    rows = _faceq([cd / "upload.jpg"], vid)
    _, face = face_score((rows.get(str(cd / "upload.jpg")) or {}).get("faces") or [])

    def put(p):
        c = p.setdefault("cover", {})
        c.update({"src": "upload", "t": None, "img": "upload.jpg", "face": face, "v": int(time.time())})
    update(vid, put)
    build_cover(vid)


# ---------------- قالب کاور ----------------
COVER_CSS = """@font-face{font-family:"Vazirmatn";src:url("Vazirmatn-Variable.woff2") format("woff2");font-weight:100 900;font-display:block}
*{box-sizing:border-box}
html,body{margin:0;width:1080px;height:1920px;overflow:hidden;background:#0b1c24}
body{position:relative;font-family:"Vazirmatn",sans-serif}
img{display:block;max-width:none}
.bg{position:absolute}
.blur{position:absolute;left:-90px;top:-90px;width:1260px;height:2100px;object-fit:cover;filter:blur(48px) brightness(.5) saturate(1.1)}
.tint{position:absolute;inset:0;background:rgba(26,60,100,.5)}
.card{position:absolute;border-radius:28px;box-shadow:0 30px 80px rgba(0,0,0,.45)}
.shade{position:absolute;left:0;right:0;height:1150px}
.shade.top{top:0;background:linear-gradient(180deg,rgba(11,28,36,.94) 0%,rgba(11,28,36,.86) 46%,rgba(11,28,36,0) 100%)}
.shade.bottom{bottom:0;background:linear-gradient(0deg,rgba(11,28,36,.94) 0%,rgba(11,28,36,.86) 46%,rgba(11,28,36,0) 100%)}
.shade.soft{opacity:.85}
.tb{position:absolute;left:84px;right:84px;display:flex;justify-content:center}
.tb.at-top{align-items:flex-start}
.tb.at-bottom{align-items:flex-end}
.t{margin:0;direction:rtl;text-align:center;font-weight:900;line-height:1.36;color:#fff;letter-spacing:0;text-wrap:balance}
.t em{font-style:normal;color:#ffdb58}
.t bdi{unicode-bidi:isolate}
.tpl-top .t{text-shadow:0 4px 26px rgba(0,0,0,.45)}
.tpl-band .t{background:#1a3c64;padding:.4em .72em .5em;border-radius:30px;box-shadow:0 22px 60px rgba(0,0,0,.4)}
.tpl-marker .t{text-shadow:0 3px 0 rgba(11,28,36,.6),0 8px 30px rgba(0,0,0,.5)}
.tpl-marker .t em{color:#1a3c64;background:#ffdb58;padding:0 .2em;border-radius:12px;text-shadow:none;
  -webkit-box-decoration-break:clone;box-decoration-break:clone}
"""

COVER_JS = """(async()=>{
try{await document.fonts.ready}catch(e){}
await Promise.all([...document.images].map(i=>i.decode?i.decode().catch(()=>0):0));
const t=document.getElementById('t'),tb=document.getElementById('tb');
if(t){let fs=__FS__;t.style.fontSize=fs+'px';
while(fs>56&&(t.offsetHeight>tb.clientHeight||t.scrollWidth>tb.clientWidth)){fs-=3;t.style.fontSize=fs+'px'}}
document.body.dataset.ready='1';
})();"""

LATIN_RUN = re.compile(r"[A-Za-z0-9][A-Za-z0-9 .+#&'’:/_-]*[A-Za-z0-9+#]|[A-Za-z0-9]")


def title_html(title):
    """**کلمه** → زرد؛ تکه‌های لاتین در <bdi> تا علامت‌های کنارشان در متن راست‌به‌چپ جابه‌جا نشوند."""
    out = []
    for k, part in enumerate(re.split(r"\*\*(.+?)\*\*", (title or "").strip())):
        h = LATIN_RUN.sub(lambda m: f"<bdi>{m.group(0)}</bdi>", escape(part))
        h = h.replace("\n", "<br>")
        out.append(f"<em>{h}</em>" if k % 2 else h)
    return "".join(out)


def resolve_pos(c, portrait):
    pos = c.get("pos") or "auto"
    if pos in ("top", "bottom"):
        return pos
    face = c.get("face")
    if portrait and face:                       # تیتر جایی که صورت نیست
        return "bottom" if face[1] + face[3] / 2 < 0.5 else "top"
    return "top"


def cover_layout(vid, p=None):
    """(html بدنه، جای تیتر) — جای عکس پس‌زمینه با زوم روی صورت و بدون بیرون‌زدگی."""
    p = p or load(vid)
    c = p.get("cover") or {}
    img = c.get("img")
    if not img or not (cdir(vid) / img).exists():
        return "", "top"
    iw, ih = _img_size(cdir(vid) / img)
    if not iw or not ih:
        return "", "top"
    src = escape(img) + (f"?v={int(c['v'])}" if c.get("v") else "")
    portrait = ih / iw >= 1.2
    pos = resolve_pos(c, portrait)
    if portrait:                                 # تمام‌قد: cover، زوم به مرکز صورت، صورت سمت مخالف تیتر
        z = float(c.get("zoom") or 1.0)
        s = max(CW / iw, CH / ih) * z
        w, h = iw * s, ih * s
        face = c.get("face")
        if face:
            cx, cy = face[0] + face[2] / 2, face[1] + face[3] / 2
            ty = 1240 if pos == "top" else 720
            left, top = CW / 2 - cx * w, ty - cy * h
        else:
            left, top = (CW - w) / 2, (CH - h) / 2
        left, top = min(0.0, max(CW - w, left)), min(0.0, max(CH - h, top))
        body = f'<img class="bg" src="{src}" style="left:{left:.1f}px;top:{top:.1f}px;width:{w:.1f}px;height:{h:.1f}px" alt="">'
    else:                                        # افقی (ضبط صفحه، عکس افقی): کارت روی همان عکس تار
        w = min(960.0, 680.0 * iw / ih)
        h = w * ih / iw
        band = (920, 1600) if pos == "top" else (320, 1000)
        top = band[0] + (band[1] - band[0] - h) / 2
        body = (f'<img class="blur" src="{src}" alt=""><div class="tint"></div>'
                f'<img class="card" src="{src}" style="left:{(CW - w) / 2:.1f}px;top:{top:.1f}px;width:{w:.1f}px;height:{h:.1f}px" alt="">')
    return body, pos


def build_cover(vid):
    """cover/cover.html از روی post.json؛ پیش‌نمایش رابط و عکس نهایی هر دو همین صفحه‌اند."""
    p = load(vid)
    c = p.get("cover") or {}
    cd = cdir(vid)
    cd.mkdir(parents=True, exist_ok=True)
    if not (cd / FONT.name).exists():
        shutil.copy(FONT, cd / FONT.name)
    body, pos = cover_layout(vid, p)
    tpl = c.get("tpl") if c.get("tpl") in TPL else "top"
    title = (c.get("title") or "").strip()
    top, hmax = TB[pos]
    over = ""
    if title:
        shade = {"top": f'<div class="shade {pos}"></div>', "marker": f'<div class="shade soft {pos}"></div>'}.get(tpl, "")
        over = (f'{shade}<div class="tb at-{pos}" id="tb" style="top:{top}px;height:{hmax}px">'
                f'<p class="t" id="t">{title_html(title)}</p></div>')
    fs = {"top": 124, "band": 104, "marker": 116}[tpl]
    html = (f'<!doctype html><html lang="fa" dir="rtl"><head><meta charset="utf-8"><title>کاور</title>'
            f'<style>{ve.brandify(COVER_CSS)}</style></head><body class="tpl-{tpl}">{body}{over}'
            f'<script>{COVER_JS.replace("__FS__", str(fs))}</script></body></html>')
    tmp = cd / "cover.html.tmp"
    tmp.write_text(html, encoding="utf-8")
    tmp.replace(cd / "cover.html")
    return int((cd / "cover.html").stat().st_mtime * 1000)


def render_cover(vid):
    """cover.jpg با Chrome؛ همان cover.html پیش‌نمایش."""
    p = load(vid)
    if not (p.get("cover") or {}).get("img"):
        raise RuntimeError("هنوز فریمی برای کاور انتخاب نشده.")
    build_cover(vid)
    cd = cdir(vid)
    out = cd / "cover.tmp.jpg"
    o, _ = ve.run([shutil.which("node") or "/opt/homebrew/bin/node", RENDER_COVER], vid, timeout=180, cwd=ve.MOD,
                  input=json.dumps({"html": str(cd / "cover.html"), "out": str(out), "w": CW, "h": CH}).encode("utf-8"))
    r = json.loads((o or b"{}").decode("utf-8", "replace") or "{}")
    if not r.get("ok") or not out.exists():
        raise RuntimeError("عکس کاور ساخته نشد: " + str(r.get("error") or "")[:200])
    out.replace(cd / "cover.jpg")
    update(vid, lambda p: p.setdefault("cover", {}).update({"jpgAt": ve.now()}))
    return cd / "cover.jpg"


def cover_stale(vid):
    cd = cdir(vid)
    h, j = cd / "cover.html", cd / "cover.jpg"
    return not j.exists() or not h.exists() or h.stat().st_mtime > j.stat().st_mtime


# ---------------- کپشن، هشتگ و تیتر با Claude ----------------
TITLE_RULES = """تیتر کاور (titles): سه یا چهار گزینه‌ی واقعاً متفاوت.
- هر کدام حداکثر ۷ کلمه؛ کاور در شبکه‌ی پروفایل کوچک دیده می‌شود.
- بگوید بیننده با دیدن این ریلز دقیقاً چه می‌گیرد: اسم مشخص، نتیجه‌ی مشخص، یا فهرست با عدد اگر ویدیو واقعاً فهرست است؛ و به کار یا آینده‌ی شغلی خود بیننده وصل باشد.
- فقط چیزی که در خود ویدیو هست. عدد، قیمت یا ادعایی که در متن ویدیو نیست نساز. کلیک‌بیت دروغ نه.
- لحن محاوره‌ای خود او. اسم ابزار و اصطلاح انگلیسی به خط لاتین بماند (ChatGPT، AI).
- در هر تیتر یک یا دو کلمه‌ی کلیدی را بین ** بگذار (روی کاور زرد می‌شود)؛ هرگز کل تیتر.
- بدون ایموجی، بدون نقطه‌ی آخر."""

CAPTION_RULES = """کپشن (caption): نوشتاری، نه گفتاری. خط اول خودش هوک است (فقط همان قبل از «بیشتر» دیده می‌شود) و عین جمله‌ی اول ویدیو نیست. دو تا پنج پاراگراف کوتاه که حرف اصلی ریلز را خلاصه می‌کند و چیزی به آن اضافه می‌کند؛ آخرش دعوت به اقدام دقیقاً طبق قواعد CTA و «کتابخانه‌ی CTA» هسته‌ی برند؛ اگر هسته‌ی برند CTA مشخصی ندارد، «سیو کنین» یا «برای کسی که لازمش داره بفرستین». ایموجی کم. هشتگ داخل کپشن نه.
- هیچ عدد، آمار، تاریخ، قیمت یا نقل‌قولی که در متن ویدیو یا هسته‌ی برند نیست نساز.
- اصطلاح فنی انگلیسی به خط لاتین بماند و بار اول یک توضیح کوتاه فارسی بگیرد.
- خطاب همه‌جا «شما» (محاوره‌ای: «سیو کنین»، «بسازین»)؛ هیچ‌جا «تو».
هشتگ‌ها (hashtags): سه تا پنج، نه بیشتر (اینستاگرام از دسامبر ۲۰۲۵ بیشتر از پنج هشتگ نمی‌گذارد). مشخص و مربوط به موضوع همین ریلز، ترکیب فارسی و انگلیسی، از خاص به عام، همه در یک خط با فاصله. هشتگ بی‌معنا و خیلی عام مثل #reels یا #explore نه."""

POST_PROMPT = """تو نویسنده‌ی پست‌های اینستاگرام __OWNER__ هستی.
این متن یک ریلز اوست که تدوین شده و آماده‌ی انتشار است. __TASK__

هسته‌ی برند او این است. «خط قرمزها» و قواعد CTA قانون‌اند، نه سلیقه:
<<<BRAND
__BRAND__
BRAND>>>

اسم ویدیو: __TITLE__
متن کامل ریلز، همان چیزی که بیننده می‌شنود (برش‌خورده و اصلاح‌شده):
<<<VIDEO
__TEXT__
VIDEO>>>
__EXTRA__
__RULES__

__NOTE__

جواب فقط یک JSON بین این دو نشانه، بدون هیچ توضیحی بیرون از آن:
<<<POST
__SHAPE__
POST>>>"""


def spoken(dv):
    fix = dv["edit"].get("fix") or {}
    return " ".join(t for t in (ve.disp(dv["words"], fix, w["i"]) for w in dv["words"] if w["i"] not in dv["cut"]) if t)


def _extra(vid, dv):
    """گرافیک‌ها و سایت‌های روی ویدیو، تا کپشن اسم‌ها و قیمت‌ها را همان‌طور بنویسد که روی تصویر آمده."""
    lines = []
    for v in dv["edit"].get("vis") or []:
        if v.get("on") is False:
            continue
        dat = {k: x for k, x in (v.get("data") or {}).items() if x not in ("", None, [], {})}
        if v.get("kind") == "gfx" and dat:
            lines.append("- گرافیک روی تصویر: " + json.dumps(dat, ensure_ascii=False)[:300])
    try:
        import video_sites as vs
        for st in vs.slist(vid):
            if st.get("url"):
                lines.append(f"- صفحه‌ای که نشان داده شد: {st.get('title') or ''} {st.get('url')}"
                             + (f" — جمله‌ی هایلایت‌شده: «{str(st.get('quote'))[:200]}»" if st.get("quote") else ""))
    except Exception:
        pass
    return ("\nچیزهایی که روی تصویر ویدیو نشان داده می‌شوند:\n" + "\n".join(lines[:20]) + "\n") if lines else ""


def clean_tags(tags, caption):
    seen, out = set(), []
    for t in re.findall(r"#[^\s#،,]+", tags or ""):
        t = t.rstrip(".،,؛;")
        if len(t) > 1 and t.lower() not in seen:
            seen.add(t.lower())
            out.append(t)
    return " ".join(out[:max(0, TAG_MAX - len(tags_of(caption)))])


def write_post(vid, what="all", comment="", say=lambda s: None):
    """what: all | caption | titles. نسخه‌ی قبلی برای «↶» می‌ماند."""
    dv = ve.derive(vid)
    text = spoken(dv)
    if not text.strip():
        raise RuntimeError("حرفی در این ویدیو نمانده که کپشن از آن نوشته شود.")
    p = load(vid)
    notes = (p.get("notes") or {}).get(what if what != "all" else "caption") or []
    if what == "titles":
        task, rules, shape = ("فقط چند گزینه‌ی تیتر برای کاور ریلز بنویس.", TITLE_RULES,
                              '{"titles": ["...", "...", "..."]}')
    elif what == "caption":
        task, rules, shape = ("فقط کپشن و هشتگ‌های پستش را بنویس.", CAPTION_RULES, '{"caption": "...", "hashtags": "#... #..."}')
    else:
        task, rules, shape = ("برایش چند گزینه‌ی تیتر کاور، کپشن پست و هشتگ بنویس.", TITLE_RULES + "\n\n" + CAPTION_RULES,
                              '{"titles": ["...", "...", "..."], "caption": "...", "hashtags": "#... #..."}')
    cur = ""
    if comment and what in ("caption", "titles"):
        cur_v = full_caption(p) if what == "caption" else "\n".join(p.get("titles") or [])
        cur = f"نسخه‌ی فعلی:\n<<<CURRENT\n{cur_v}\nCURRENT>>>\n"
    note = (cur + "نظر کاربر برای این بازنویسی؛ مهم‌ترین ورودی است، دقیقاً اجرایش کن:\n<<<NOTE\n" + comment + "\nNOTE>>>"
            if comment else "")
    if notes:
        note += "\n\nنظرهای قبلی کاربر درباره‌ی همین بخش (تا خواسته‌هایش گم نشود):\n" + "\n".join(f"- {n}" for n in notes[-4:])
    prompt = (POST_PROMPT.replace("__OWNER__", cfg.owner_line()).replace("__TASK__", task).replace("__BRAND__", ve.brand_text())
              .replace("__TITLE__", str(dv["proj"].get("title") or "")).replace("__TEXT__", text[:24000])
              .replace("__EXTRA__", _extra(vid, dv)).replace("__RULES__", rules).replace("__NOTE__", note)
              .replace("__SHAPE__", shape))
    say("Claude دارد کپشن و تیتر کاور را می‌نویسد…" if what == "all" else
        "Claude دارد کپشن را از نو می‌نویسد…" if what == "caption" else "Claude دارد تیترهای تازه می‌نویسد…")
    res = ve.ask(prompt, vid, timeout=900, effort="high")
    data = ve.json_block(res, "<<<POST", "POST>>>")
    if not data:
        (ve.pdir(vid) / "post.last-output.txt").write_text(res or "", encoding="utf-8")
        raise RuntimeError("جواب Claude برای کپشن قابل خواندن نبود.")
    titles = [re.sub(r"[.!،؛]+$", "", str(t).strip())[:90] for t in data.get("titles") or [] if str(t).strip()][:4]
    caption = str(data.get("caption") or "").strip()[:CAP_MAX]
    tags = clean_tags(str(data.get("hashtags") or ""), caption)
    if what in ("all", "titles") and not titles:
        raise RuntimeError("Claude تیتری نداد.")
    if what in ("all", "caption") and not caption:
        raise RuntimeError("Claude کپشنی نداد.")

    def put(p):
        prev = p.setdefault("prev", {})
        if what in ("all", "caption"):
            if p.get("caption"):
                prev["caption"] = {"caption": p.get("caption", ""), "hashtags": p.get("hashtags", "")}
            p["caption"], p["hashtags"] = caption, tags
        if what in ("all", "titles"):
            if p.get("titles"):
                prev["titles"] = p["titles"]
            p["titles"] = titles
            c = p.setdefault("cover", {})
            if not c.get("titleSet") and titles:      # تیتر را کاربر ننوشته: اولین پیشنهاد
                c["title"] = titles[0]
        if comment:
            p.setdefault("notes", {}).setdefault("titles" if what == "titles" else "caption", []).append(comment[:500])
        p["writtenAt"] = ve.now()
    update(vid, put)
    build_cover(vid)


def auto(vid, say=lambda s: None):
    """مرحله‌ی «کاور و کپشن» در ساخت کامل: فقط چیزی که هنوز نیست."""
    p = load(vid)
    if not p.get("cands"):
        find_cands(vid, say)
    if not p.get("writtenAt"):
        write_post(vid, "all", "", say)


# ---------------- بررسی پیش از انتشار ----------------
def problems(vid, p=None, canvas=None):
    """[{t, block}] — block یعنی انتشار ممکن نیست. canvas: کادر خروجی (reel یا screen)."""
    p = p or load(vid)
    d = ve.pdir(vid)
    out = []
    final = d / "out" / "final.mp4"
    proj = ve.jload(d / "project.json", {})
    if not final.exists():
        out.append({"t": "هنوز رندر نهایی نگرفته‌ای.", "block": True})
    else:
        dur = (proj.get("render") or {}).get("dur") or 0
        if dur and not DUR_MIN <= dur <= DUR_MAX:
            out.append({"t": f"ریلز باید بین ۳ ثانیه و ۱۵ دقیقه باشد؛ این ویدیو {fa(round(dur))} ثانیه است.", "block": True})
        ed = d / "edit.json"
        if ed.exists() and ed.stat().st_mtime > final.stat().st_mtime + 1:
            out.append({"t": "بعد از آخرین رندر ویدیو را تغییر داده‌ای؛ چیزی که منتشر می‌شود همان رندر قبلی است.", "block": False})
        if canvas == "screen":
            out.append({"t": "ویدیو افقی است و در ریلز با نوار خالی بالا و پایین دیده می‌شود؛ برای ریلز «خروجی عمودی» را در بخش ضبط صفحه روشن کن و دوباره رندر بگیر.",
                        "block": False})
    cap = full_caption(p)
    if len(cap) > CAP_MAX:
        out.append({"t": f"کپشن و هشتگ‌ها از {fa(CAP_MAX)} حرف بیشترند.", "block": True})
    if len(tags_of(cap)) > TAG_MAX:
        out.append({"t": f"بیشتر از {fa(TAG_MAX)} هشتگ؛ اینستاگرام نمی‌گذارد.", "block": True})
    if not (p.get("caption") or "").strip():
        out.append({"t": "کپشن خالی است.", "block": False})
    if not (p.get("cover") or {}).get("img"):
        out.append({"t": "کاوری انتخاب نشده؛ اینستاگرام خودش یک فریم برمی‌دارد.", "block": False})
    return out


# ---------------- فایل اینستاگرام ----------------
def ig_export(vid, cap, say=lambda s: None):
    """out/ig.mp4: تصویر همان رندر (اگر جا می‌شود، بی‌تغییر)، صدا AAC ۱۲۸k ۴۸k، moov اول، بدون edit list."""
    d = ve.pdir(vid)
    final, dst, tmp = d / "out" / "final.mp4", d / "out" / "ig.mp4", d / "out" / "ig.tmp.mp4"
    info = ve.probe(final)
    dur = max(1.0, float(info.get("dur") or 1))
    tail = ["-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-movflags", "+faststart", "-use_editlist", "0", tmp]
    if final.stat().st_size <= cap * 0.97 and info.get("vcodec") == "h264" and 23 <= (info.get("fps") or 30) <= 60:
        say("آماده کردن فایل برای اینستاگرام…")
        ve.run([ve.FFMPEG, "-v", "error", "-y", "-i", final, "-map", "0:v:0", "-map", "0:a:0?", "-c:v", "copy", *tail], vid, timeout=900)
    else:
        kb = max(700, min(12000, int(cap * 0.9 * 8 / dur / 1000) - 128))
        say(f"فشرده کردن ویدیو برای اینستاگرام ({fa(round(cap / 1048576))} مگ)…")
        ve.run([ve.FFMPEG, "-v", "error", "-y", "-i", final, "-map", "0:v:0", "-map", "0:a:0?", "-c:v", "libx264",
                "-preset", "medium", "-b:v", f"{kb}k", "-maxrate", f"{int(kb * 1.5)}k", "-bufsize", f"{kb * 2}k",
                "-pix_fmt", "yuv420p", "-profile:v", "high", "-g", "60", *tail], vid, timeout=4 * 3600)
    tmp.replace(dst)
    return dst


# ---------------- آپلود مستقیم به Storage سایت ----------------
def put_file(url, path, ctype, anon="", on_pct=lambda x: None, vid=None):
    """PUT خام به آدرس امضاشده‌ی Supabase، تکه‌تکه با درصد. (کد، متن جواب)"""
    u = urlparse(url)
    if u.scheme not in ("https", "http") or not u.hostname:
        raise RuntimeError("آدرس آپلود نامعتبر است.")
    conn = (http.client.HTTPSConnection(u.hostname, u.port or 443, timeout=120, context=ssl.create_default_context())
            if u.scheme == "https" else http.client.HTTPConnection(u.hostname, u.port or 80, timeout=120))
    size = Path(path).stat().st_size
    try:
        conn.putrequest("PUT", u.path + (f"?{u.query}" if u.query else ""), skip_accept_encoding=True)
        conn.putheader("Content-Type", ctype)
        conn.putheader("Content-Length", str(size))
        conn.putheader("x-upsert", "false")
        conn.putheader("Cache-Control", "max-age=3600")
        if anon:
            conn.putheader("apikey", anon)
        conn.endheaders()
        sent = 0
        with open(path, "rb") as f:
            while True:
                if vid in CANCEL:
                    raise RuntimeError("متوقف شد.")
                b = f.read(1024 * 1024)
                if not b:
                    break
                conn.send(b)
                sent += len(b)
                on_pct(sent / max(1, size))
        r = conn.getresponse()
        return r.status, r.read(4000).decode("utf-8", "replace")
    finally:
        conn.close()


def too_large(code, body):
    return code == 413 or (code in (400, 413) and re.search(r"maximum allowed size|payload too large|entitytoolarge", body or "", re.I))


def _site(body, timeout=40):
    # انتشار مستقیم در نسخه‌ی دانشجو نیست؛ ویدیو و کاور دانلود و دستی منتشر می‌شوند.
    raise RuntimeError("انتشار مستقیم در این استودیو نیست؛ ویدیو را دانلود کن و خودت منتشر کن.")
    code, d = None, None
    return code, (d if isinstance(d, dict) else {})


def _upload_url(ext, label):
    """{path, url, anonKey, maxBytes} — maxBytes سقف باکت است؛ null یعنی سقف کلی Storage کمتر از ۳۰۰ مگ است."""
    code, d = _site({"action": "publish-reel-upload-url", "ext": ext})
    if code == 400 and d.get("error") == "unknown action":
        raise RuntimeError("سایت هنوز انتشار ریلز را ندارد؛ اول باید نسخه‌ی تازه‌ی سایت منتشر شود.")
    if code != 200 or not d.get("url") or not d.get("path"):
        raise RuntimeError(f"سایت آدرس آپلود {label} را نداد: {d.get('error') or code}")
    return d


def _put(vid, js, d, f, ctype, label):
    mb = f.stat().st_size / 1048576
    anon = str(d.get("anonKey") or "").strip()        # متغیر محیطی Vercel با «\n» آخرش ذخیره شده؛ http.client سرآیند با خط تازه را رد می‌کند
    if not re.fullmatch(r"[A-Za-z0-9._-]{20,4000}", anon):
        anon = ""
    try:
        return put_file(d["url"], f, ctype, anon, lambda x: js(pct=round(x * 100),
                        msg=f"آپلود {label} ({fa(round(mb * x))} از {fa(max(1, round(mb)))} مگ)…"), vid)
    except (OSError, http.client.HTTPException) as e:
        raise RuntimeError(f"آپلود {label} نشد (شبکه): {str(e)[:160]}")
    except ValueError:                                  # مقدار سرآیند؛ متنش را در پیام نمی‌آوریم
        raise RuntimeError(f"آپلود {label} نشد: سرآیند نامعتبر.")


def signature(vid, caption, feed):
    d = ve.pdir(vid)
    h = hashlib.sha1()
    st = (d / "out" / "final.mp4").stat()
    h.update(f"{st.st_size}:{st.st_mtime_ns}|{caption}|{feed}|".encode("utf-8"))
    cj = cdir(vid) / "cover.jpg"
    h.update(cj.read_bytes() if (load(vid).get("cover") or {}).get("img") and cj.exists() else b"-")
    return h.hexdigest()


def _cleanup(paths):
    if paths:
        _site({"action": "publish-reel-cleanup", "paths": paths}, timeout=40)


def set_pend(vid, **kw):
    """فیلدهای کار نیمه‌تمام؛ اگر کاربر وسط کار «فراموش کن» زده باشد، چیزی نمی‌سازد."""
    def put(p):
        if p.get("pending"):
            p["pending"].update(kw)
    update(vid, put)


class Dead(RuntimeError):
    """container خراب یا باطل شد؛ ادامه‌دادنش فایده ندارد."""


def _poll(vid, js, cid):
    t0 = time.time()
    while time.time() - t0 < POLL_LIMIT:
        if vid in CANCEL:
            raise RuntimeError("متوقف شد. ریلز ساخته شده ولی منتشر نشده؛ «ادامه» همان را دنبال می‌کند.")
        code, d = _site({"action": "publish-reel-status", "containerId": cid})
        sc = d.get("statusCode") if code == 200 else ""
        if sc == "FINISHED":
            return
        if sc in ("ERROR", "EXPIRED"):
            raise Dead(f"اینستاگرام ویدیو را پردازش نکرد ({sc}{': ' + str(d.get('status'))[:200] if d.get('status') else ''}).")
        if code in (401, 403) or d.get("setup"):
            raise RuntimeError(f"سایت جواب نداد: {d.get('error') or code}")
        js(msg=f"اینستاگرام دارد ویدیو را پردازش می‌کند… ({fa(int(time.time() - t0))} ثانیه)", pct=None)
        time.sleep(5)
    raise RuntimeError("پردازش اینستاگرام بیشتر از ۱۵ دقیقه طول کشید؛ کمی بعد «ادامه» را بزن.")


def publish(vid, js, dry=False, heavy=None):
    """dry: آپلود، ساخت container و صبر تا پردازش؛ چیزی منتشر نمی‌شود. بعد تا ۲۰ ساعت «انتشار» همان را بی‌آپلود منتشر می‌کند."""
    CANCEL.discard(vid)
    p = load(vid)
    block = [x["t"] for x in problems(vid, p) if x["block"]]
    if block:
        raise RuntimeError(block[0])
    caption, feed = full_caption(p), p.get("feed", True) is not False
    has_cover = bool((p.get("cover") or {}).get("img"))
    if has_cover:
        js(msg="ساخت عکس کاور…")
        render_cover(vid)
    sig = signature(vid, caption, feed)
    old = p.get("pending") or {}
    if old.get("sig") == sig and old.get("state") == "ready" and time.time() - old.get("ts", 0) < PENDING_TTL:
        if dry:
            return js(state="done", dry=True, msg="همین ریلز قبلاً آزمایش شده و آماده‌ی انتشار است؛ چیزی منتشر نشد.")
        return commit(vid, js, old["containerId"])
    if old:                                              # نسخه‌ی قدیمی‌تر کنار می‌رود (container خودش ۲۴ ساعته باطل می‌شود)
        forget(vid)
    paths, cid = [], None
    try:
        ud = _upload_url("mp4", "ویدیو")
        mx = ud.get("maxBytes")
        cap = min(IG_MAX, int(mx)) if mx else SMALL_MAX   # سقف باکت نامعلوم: سقف پیش‌فرض Supabase (۵۰ مگ)
        for attempt in (1, 2):
            with heavy or nullcontext():
                f = ig_export(vid, cap, lambda m: js(msg=m))
            st, body = _put(vid, js, ud, f, "video/mp4", "ویدیو")
            if too_large(st, body) and attempt == 1 and cap > SMALL_MAX:
                cap, ud = SMALL_MAX, _upload_url("mp4", "ویدیو")
                continue
            if st not in (200, 201):
                raise RuntimeError(f"آپلود ویدیو نشد ({st}): {body[:200]}")
            paths.append(ud["path"])
            break
        cpath = None
        if has_cover:
            cd_ = _upload_url("jpg", "کاور")
            st, body = _put(vid, js, cd_, cdir(vid) / "cover.jpg", "image/jpeg", "کاور")
            if st not in (200, 201):
                raise RuntimeError(f"آپلود کاور نشد ({st}): {body[:200]}")
            cpath = cd_["path"]
            paths.append(cpath)
        js(msg="ساخت ریلز در اینستاگرام…", pct=None)
        code, d = _site({"action": "publish-reel-prepare", "video": paths[0], "cover": cpath, "caption": caption,
                         "shareToFeed": feed}, timeout=120)
        if code != 200 or not d.get("containerId"):
            raise RuntimeError(f"اینستاگرام ریلز را نساخت: {d.get('error') or code}")
        cid = d["containerId"]
        update(vid, lambda p: p.update({"pending": {"containerId": cid, "sig": sig, "state": "processing", "dry": dry,
                                                    "paths": paths, "at": ve.now(), "ts": time.time()}}))
        _poll(vid, js, cid)
    except Dead:
        forget(vid)
        raise
    except Exception:
        if not cid:                                      # container ساخته نشد: فایل‌ها پاک
            _cleanup(paths)
        raise                                            # ساخته شد: فایل‌ها تا «ادامه» یا «فراموش کن» می‌مانند
    set_pend(vid, state="ready")
    if dry:
        _cleanup(paths)
        set_pend(vid, paths=[])
        return js(state="done", dry=True, pct=None,
                  msg="آزمایش موفق بود: ویدیو و کاور آپلود شد و اینستاگرام ریلز را ساخت و پردازش کرد. چیزی منتشر نشد. "
                      "تا ۲۰ ساعت «انتشار» همین را بدون آپلود دوباره منتشر می‌کند، مگر چیزی را عوض کنی.")
    commit(vid, js, cid)


def commit(vid, js, cid):
    """فقط media_publish. یک container دو بار منتشر نمی‌شود، پس «دوباره امتحان کن» ریلز تکراری نمی‌سازد."""
    js(msg="انتشار…", pct=None)
    set_pend(vid, dry=False)                             # از این‌جا «ادامه» یعنی انتشار؛ کاربر خودش «منتشر کن» زده
    code, d = _site({"action": "publish-commit", "containerId": cid}, timeout=120)
    if code != 200 or not d.get("mediaId"):
        return js(state="error", retry=True, error=f"انتشار نشد: {d.get('error') or code}. قبل از «دوباره امتحان کن» پیجت را نگاه کن؛ "
                  "دوباره امتحان کردن همان ریلز را منتشر می‌کند، نه یک ریلز تازه.")
    paths = (load(vid).get("pending") or {}).get("paths") or []

    def put(p):
        p.setdefault("published", []).append({"mediaId": d["mediaId"], "permalink": d.get("permalink") or "", "at": ve.now()})
        p["pending"] = None
    update(vid, put)
    _cleanup(paths)
    js(state="done", dry=False, retry=False, pct=None, permalink=d.get("permalink") or "", msg="منتشر شد.")


def resume(vid, js, publish_now=False):
    """کار نیمه‌تمام (ری‌استارت، توقف، پردازش طولانی، خطای انتشار): همان container.
    publish_now فقط وقتی است که کاربر همین حالا «منتشر کن» یا «دوباره امتحان کن» زده."""
    CANCEL.discard(vid)
    pend = load(vid).get("pending") or {}
    cid = pend.get("containerId")
    if not cid:
        raise RuntimeError("کار نیمه‌تمامی نیست.")
    if time.time() - pend.get("ts", 0) > PENDING_TTL:
        forget(vid)
        raise RuntimeError("این ریلز آماده بیشتر از ۲۰ ساعت مانده و باطل شده؛ دوباره «انتشار» بزن.")
    if pend.get("state") != "ready":
        try:
            _poll(vid, js, cid)
        except Dead:
            forget(vid)
            raise
        set_pend(vid, state="ready")
    if not publish_now:
        if pend.get("dry"):
            _cleanup(pend.get("paths") or [])
            set_pend(vid, paths=[])
        return js(state="done", dry=True, pct=None, msg="اینستاگرام ریلز را پردازش کرد و آماده‌ی انتشار است. چیزی منتشر نشد.")
    commit(vid, js, cid)


def forget(vid):
    pend = load(vid).get("pending") or {}
    _cleanup(pend.get("paths") or [])
    update(vid, lambda p: p.update({"pending": None}))


# ---------------- برای صفحه ----------------
def view(vid, job, canvas=None):
    p = load(vid)
    cd = cdir(vid)
    c = dict(p.get("cover") or {})
    pend = p.get("pending") or None
    if pend:
        pend = {k: pend.get(k) for k in ("state", "dry", "at")}
        pend["fresh"] = time.time() - (p.get("pending") or {}).get("ts", 0) < PENDING_TTL
    mt = lambda f: int(f.stat().st_mtime * 1000) if f.exists() else 0
    return {
        "cover": {k: c.get(k) for k in ("src", "t", "img", "title", "tpl", "pos", "zoom", "face")},
        "coverAt": mt(cd / "cover.html") if c.get("img") else 0, "jpgAt": mt(cd / "cover.jpg"),
        "jpgStale": cover_stale(vid), "cands": p.get("cands") or [], "titles": p.get("titles") or [],
        "caption": p.get("caption") or "", "hashtags": p.get("hashtags") or "", "feed": p.get("feed", True) is not False,
        "writtenAt": p.get("writtenAt"), "prev": sorted((p.get("prev") or {}).keys()),
        "notes": {k: (v or [])[-1:] for k, v in (p.get("notes") or {}).items()},
        "pending": pend, "published": p.get("published") or [], "problems": problems(vid, p, canvas), "job": job,
        "tpls": TPL, "poses": POS, "zooms": list(ZOOMS), "tagMax": TAG_MAX, "capMax": CAP_MAX, "grid": list(GRID),
    }


def edit(vid, body):
    """POST /api/video/post (op): pick، title، tpl، pos، zoom، caption، feed، undo، forget، cancel."""
    op = body.get("op")
    if op == "pick":
        t = float(body.get("t") or 0)
        if not any(abs(c["t"] - t) < 0.01 for c in load(vid).get("cands") or []):
            return 400, {"error": "این فریم در پیشنهادها نیست."}
        pick_frame(vid, t)
    elif op in ("title", "tpl", "pos", "zoom"):
        v = body.get("value")
        if op == "title":
            v = str(v or "")[:160]
        elif op == "tpl" and v not in TPL or op == "pos" and v not in POS:
            return 400, {"error": "مقدار نامعتبر."}
        elif op == "zoom":
            v = float(v) if v in ZOOMS or (isinstance(v, (int, float)) and float(v) in ZOOMS) else 1.0

        def put(p):
            c = p.setdefault("cover", {})
            c[op] = v
            if op == "title":
                c["titleSet"] = True
        update(vid, put)
        build_cover(vid)
    elif op == "caption":
        cap = str(body.get("caption") or "")[:CAP_MAX + 200]
        tags = str(body.get("hashtags") or "")[:600]
        update(vid, lambda p: p.update({"caption": cap, "hashtags": " ".join(tags.split())}))
    elif op == "feed":
        update(vid, lambda p: p.update({"feed": bool(body.get("value"))}))
    elif op == "undo":
        sec = body.get("section")
        p = load(vid)
        prev = (p.get("prev") or {}).get(sec)
        if sec not in ("caption", "titles") or prev is None:
            return 404, {"error": "نسخه‌ی قبلی نیست."}

        def put(p):
            if sec == "caption":
                now = {"caption": p.get("caption", ""), "hashtags": p.get("hashtags", "")}
                p["caption"], p["hashtags"] = prev.get("caption", ""), prev.get("hashtags", "")
            else:
                now = p.get("titles") or []
                p["titles"] = prev
            p["prev"][sec] = now
        update(vid, put)
    elif op == "forget":
        forget(vid)
    elif op == "cancel":
        CANCEL.add(vid)
    else:
        return 400, {"error": "عمل نامعتبر."}
    return 200, {"ok": True, "post": view(vid, None)}
