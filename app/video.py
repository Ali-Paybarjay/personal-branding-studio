"""تدوین ویدیو — مسیرهای HTTP و کارهای پس‌زمینه. موتور: video_engine.py · رابط: video.js / video.css

دو هوک زودهنگام در server.py لازم است، چون بقیه‌ی استودیو کل بدنه را JSON می‌خواند و Range ندارد:
- POST /api/video/upload   آپلود جریانی فایل ویدیو (چند گیگ هم می‌شود)، تکه‌تکه روی دیسک
- GET  /video-media/<id>/… فایل‌های پروژه با پشتیبانی Range (پخش با جلو/عقب رفتن در <video> و iframe پیش‌نمایش)
بقیه از زنجیره‌ی معمول handle_get / handle_post می‌آید.
"""
import re, shutil, threading, time
from pathlib import Path
from urllib.parse import parse_qs, urlparse, unquote
import video_engine as ve
import video_visuals as vv
import video_sites as vs
import video_screen as vsc
import video_publish as vp

APP = ve.APP
STATIC = {"/video.js": ("video.js", "text/javascript; charset=utf-8"),
          "/video.css": ("video.css", "text/css; charset=utf-8")}
VIDEO_EXT = {".mp4", ".mov", ".m4v", ".webm", ".mkv"}
MAX_UPLOAD = 8 * 1024 ** 3
CTYPE = {".mp4": "video/mp4", ".mov": "video/quicktime", ".m4v": "video/mp4", ".webm": "video/webm", ".jpg": "image/jpeg",
         ".png": "image/png", ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
         ".css": "text/css; charset=utf-8", ".woff2": "font/woff2", ".srt": "text/plain; charset=utf-8",
         ".json": "application/json; charset=utf-8", ".wav": "audio/wav", ".mp3": "audio/mpeg", ".svg": "image/svg+xml",
         ".webp": "image/webp"}
MEDIA_OK = re.compile(r"^(thumb\.jpg|proxy\.mp4|out/final\.(mp4|srt)|comp/(preview|index)\.html|comp/assets/[A-Za-z0-9_.-]+"
                      r"|media/m[0-9]{6,20}/(thumb|view)\.jpg|sites/s[0-9]{6,24}/(desktop|mobile)/(thumb|view)\.jpg|frames/f[0-9]{1,9}\.jpg"
                      r"|cover/(cover\.(html|jpg)|f[0-9]{1,9}\.jpg|upload\.jpg|Vazirmatn-Variable\.woff2|cand/c[0-9]{1,9}\.jpg))$")
STEPS = ("ingest", "faces", "transcribe", "decide", "preview", "screen", "sfx", "sites", "vis", "post")   # این‌ها بعد از پیش‌نمایش، تا برش‌ها زودتر دیده شوند
NEEDS = {"faces": {"ingest"}, "transcribe": {"ingest"}, "decide": {"transcribe"}, "screen": {"decide"}, "sfx": {"decide"}, "sites": {"decide"}, "vis": {"decide"}, "post": {"decide"}}   # هر مرحله دوباره که برود، این‌ها هم
# کارهای اختیاری «ساخت کامل» که کاربر موقع آپلود تیک می‌زند (۲۰۲۶-۱۰-۰۸، درخواست کاربر). آماده‌سازی، جای صورت، متن و
# پیش‌نمایش همیشه انجام می‌شوند. هر کار خاموش بعداً از دکمه‌ی بخش خودش ساخته می‌شود. (کلید، اسم، فقط ضبط صفحه)
PARTS = (("cuts", "برش خودکار", False), ("captions", "زیرنویس", False), ("voice", "صدای تمیز", False),
         ("sfx", "افکت صوتی", False), ("vis", "عکس و گرافیک", False), ("sites", "سایت و هایلایت", False),
         ("zooms", "زوم هوشمند", True), ("blurs", "محو اطلاعات حساس", True), ("post", "کاور و کپشن پست", False))


def parts_of(p):
    """کارهای روشن این پروژه؛ پروژه‌ی قدیمی (بی parts) یعنی همه."""
    got = p.get("parts") if isinstance(p.get("parts"), dict) else {}
    return {k: got.get(k, True) is not False for k, _, _ in PARTS}


STEP_FA = {"upload": "آپلود", "ingest": "آماده‌سازی", "faces": "جای صورت", "transcribe": "متن", "decide": "تصمیم‌های Claude",
           "preview": "پیش‌نمایش", "screen": "ضبط صفحه", "sfx": "افکت صوتی", "sites": "سایت‌ها", "vis": "عکس و گرافیک", "post": "کاور و کپشن", "render": "رندر نهایی", "regen": "بازتولید"}

JOBS, JLOCK = {}, threading.Lock()        # vid ← {state, step, msg, error, started, again}
HEAVY = threading.Semaphore(1)            # آماده‌سازی و رندر سنگین‌اند؛ یکی‌یکی
_TIMERS = {}

ve.kill_orphans()


# ---------------- کمک‌ها ----------------
def jset(vid, **kw):
    with JLOCK:
        JOBS.setdefault(vid, {}).update(kw)


def jget(vid):
    with JLOCK:
        return dict(JOBS.get(vid, {}))


def running(vid):
    return jget(vid).get("state") == "running"


def proj_update(vid, **kw):
    with ve.plock(vid):
        p = ve.jload(ve.pdir(vid) / "project.json", {})
        p.update(kw)
        ve.jsave(ve.pdir(vid) / "project.json", p)
        return p


def mark(vid, step, ok=True, err=""):
    with ve.plock(vid):
        p = ve.jload(ve.pdir(vid) / "project.json", {})
        p.setdefault("steps", {})[step] = {"ok": ok, "at": ve.now(), **({"error": err[:600]} if err else {})}
        ve.jsave(ve.pdir(vid) / "project.json", p)


def src_file(vid):
    d = ve.pdir(vid) / "src"
    return next((f for f in sorted(d.glob("original.*")) if f.suffix.lower() in VIDEO_EXT), None) if d.exists() else None


def exists(vid):
    return ve.safe_id(vid) and (ve.pdir(vid) / "project.json").exists()


# ---------------- کارها ----------------
def start(vid, step, comment="", section=""):
    with JLOCK:
        j = JOBS.get(vid, {})
        if j.get("state") == "running":
            if step == "preview":          # بعد از کار فعلی دوباره ساخته می‌شود
                j["again"] = True
            return False
        JOBS[vid] = {"state": "running", "step": step, "msg": "", "error": "", "started": time.time(), "again": False,
                     "section": section}      # رابط نتیجه‌ی «بازتولید» را زیر دکمه‌ی همان بخش نشان می‌دهد
    threading.Thread(target=_run, args=(vid, step, comment, section), daemon=True).start()
    return True


def _plan(vid, step):
    """«ساخت کامل»: فقط مرحله‌های نکرده و هر چه به آن‌ها وابسته است؛ پیش‌نمایش همیشه.
    (مرحله‌ی تازه مثل «جای صورت» تصمیم‌های قبلی Claude را دوباره نمی‌سازد.)"""
    if step != "all":
        return [step]
    p = ve.jload(ve.pdir(vid) / "project.json", {})
    done = {k for k, v in (p.get("steps") or {}).items() if v.get("ok")}
    e = ve.jload(ve.pdir(vid) / "edit.json", {})      # افکت یا تصویری که با «بازتولید» ساخته شده هم انجام‌شده حساب می‌شود
    done |= {s for s, k in (("screen", "zoomsAt"), ("sfx", "sfxAt"), ("sites", "sitesAt"), ("vis", "visAt")) if e.get(k)}
    post = vp.load(vid)                                # کاور و کپشنی که از پنل خودش ساخته شده
    if post.get("cands") and post.get("writtenAt"):
        done.add("post")
    todo = {s for s in STEPS if s not in done} | {"preview"}
    changed = True
    while changed:
        changed = False
        for s, deps in NEEDS.items():
            if s not in todo and deps & todo:
                todo.add(s)
                changed = True
    on = parts_of(p)                                   # کارهایی که کاربر موقع آپلود نخواسته
    todo -= {s for s, need in (("sfx", on["sfx"]), ("vis", on["vis"]), ("sites", on["sites"]), ("post", on["post"]),
                               ("screen", on["zooms"] or on["blurs"]), ("decide", on["cuts"] or on["captions"])) if not need}
    return [s for s in STEPS if s in todo]


def _run(vid, step, comment, section):
    say = lambda m: jset(vid, msg=m)
    cur = step
    try:
        for cur in _plan(vid, step):
            jset(vid, step=cur, msg="")
            p = ve.jload(ve.pdir(vid) / "project.json", {})
            if cur == "ingest":
                src = src_file(vid)
                if not src:
                    raise RuntimeError("فایل ویدیو پیدا نشد؛ دوباره آپلود کن.")
                say("در صف آماده‌سازی…")
                with HEAVY:
                    info = ve.ingest(vid, src, p.get("kind", "reel"), say)
                proj_update(vid, info=info)
            elif cur == "faces":
                ve.track_faces(vid, say)
            elif cur == "transcribe":
                r = ve.transcribe(vid, say)
                proj_update(vid, engine=r.get("engine"), words=len(r.get("words") or []))
            elif cur == "decide":                  # فقط بخش‌هایی که کاربر خواسته (برش و/یا متن زیرنویس)
                on = parts_of(p)
                ve.decide(vid, ("cuts",) * on["cuts"] + ("fix", "emph") * on["captions"] or ("cuts", "fix", "emph"), step=say)
            elif cur == "regen" and section == "sfx":
                ve.suggest_sfx(vid, comment, say)
                light_preview(vid)
            elif cur == "regen" and section == "vis":
                vv.plan_visuals(vid, comment, say)
                light_preview(vid)
            elif cur == "regen" and section == "zooms":
                vsc.find_zooms(vid, comment, say)
                light_preview(vid)
            elif cur == "regen" and section == "blurs":
                vsc.scan_sensitive(vid, say)
                ve.build_preview(vid, say)             # محو در خود ویدیوی سبک پخته می‌شود
            elif cur == "regen" and section == "sites":
                vs.find_sites(vid, comment, say, site_changed)
                light_preview(vid)
            elif cur == "regen":
                secs = {"cuts": ("cuts",), "captions": ("fix", "emph")}.get(section, ("cuts", "fix", "emph"))
                ve.decide(vid, secs, comment, say)
                ve.build_preview(vid, say)
            elif cur == "preview":
                ve.build_preview(vid, say)
            elif cur == "sfx":
                ve.suggest_sfx(vid, step=say)
                light_preview(vid)
            elif cur == "vis":
                vv.plan_visuals(vid, step=say)
                light_preview(vid)
            elif cur == "sites":
                vs.find_sites(vid, step=say, on_change=site_changed)
                light_preview(vid)
            elif cur == "screen":
                if p.get("kind") == "screen":
                    on = parts_of(p)
                    if on["blurs"] and on["zooms"]:
                        vsc.analyze(vid, say)
                    elif on["blurs"]:
                        vsc.scan_sensitive(vid, say)
                    elif on["zooms"]:
                        vsc.find_zooms(vid, step=say)
                    ve.build_preview(vid, say)         # محوها در ویدیوی سبک پخته می‌شوند
            elif cur == "post":
                vp.auto(vid, say)
            elif cur == "render":
                say("در صف رندر…")
                with HEAVY:
                    res = ve.render(vid, say)
                proj_update(vid, render={**res, "at": ve.now()})
            mark(vid, cur)
        jset(vid, state="done", msg="", finished=time.time())
    except Exception as e:
        mark(vid, cur, False, str(e))
        jset(vid, state="error", error=str(e)[:600], msg="")
    again = jget(vid).get("again")
    if again and jget(vid).get("state") != "running":
        start(vid, "preview")


def light_preview(vid):
    """تغییرهای ظاهری (سبک، زیرنویس، زوم، متن و تأکید): فقط preview.html؛ ویدیوی سبک دست نمی‌خورد. زیر یک ثانیه."""
    if (ve.pdir(vid) / "comp" / "assets" / "proxy_cut.mp4").exists():
        ve.build_comp(vid, "preview")
    else:
        schedule_preview(vid)


def schedule_preview(vid, delay=0.7):
    """بعد از هر ویرایش؛ چند ویرایش پشت‌سرهم یک بار ساخته می‌شوند."""
    t = _TIMERS.pop(vid, None)
    if t:
        t.cancel()
    t = threading.Timer(delay, lambda: start(vid, "preview"))
    t.daemon = True
    _TIMERS[vid] = t
    t.start()


# ---------------- آپلود و رسانه (هوک‌های زودهنگام server.py) ----------------
def media_changed(vid, mid):
    """کارگر رسانه یک فایل را تمام کرد؛ اگر روی ویدیو هست، پیش‌نمایش تازه می‌شود."""
    e = ve.jload(ve.pdir(vid) / "edit.json", {})
    if any(v.get("mid") == mid for v in e.get("vis") or []):
        light_preview(vid)


def media_upload(h, vid, name):
    """POST /api/video/upload?id=&name=&asset=1 — عکس، PDF یا ویدیوی خود کاربر برای روی ویدیو (فاز ۳)."""
    ext = Path(name).suffix.lower()
    n = int(h.headers.get("Content-Length") or 0)
    if not exists(vid) or ext not in vv.MEDIA_EXT or not 0 < n <= vv.MAX_MEDIA:
        h.rfile.read(n) if 0 < n <= 64 * 1024 else None
        return h._json({"error": "عکس (JPG، PNG، HEIC، WebP)، PDF یا ویدیو (MP4، MOV) بفرست."}, 400)
    mid = vv.media_add(vid, Path(name).name, ext)
    part, left = vv.mdir(vid, mid) / f"orig{ext}.part", n
    with open(part, "wb") as f:
        while left > 0:
            chunk = h.rfile.read(min(4 * 1024 * 1024, left))
            if not chunk:
                break
            f.write(chunk)
            left -= len(chunk)
    if left:
        part.unlink(missing_ok=True)
        vv.media_delete(vid, mid)
        return h._json({"error": "آپلود نیمه‌کاره ماند."}, 400)
    part.replace(vv.mdir(vid, mid) / f"orig{ext}")
    vv.mupdate(vid, mid, status="queued", size=n)
    vv.media_kick(vid, media_changed)
    return h._json({"ok": True, "mid": mid})


def media_edit(vid, body):
    """POST /api/video/media — توضیح (note)، جعبه‌های دستی (boxes)، برگشت به پیشنهاد Claude (reset)، دوباره (retry)، حذف (del)."""
    mid, act = body.get("mid"), body.get("act")
    ok = lambda b: isinstance(b, list) and len(b) == 4 and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in b)
    with ve.plock(vid):
        m = vv.mget(vid, mid)
        if not m:
            return 404, {"error": "این فایل پیدا نشد."}
        idle = m.get("status") in ("ready", "error")
        has_view = (vv.mdir(vid, mid) / "view.jpg").exists()
        if act == "note":
            kw = {"note": str(body.get("note") or "").strip()[:2000], "rev": m.get("rev", 0) + 1}
            if idle:
                kw["status"] = "analyze" if has_view else "queued"
            vv.mupdate(vid, mid, **kw)
        elif act == "boxes":
            bx = body.get("boxes") or {}
            boxes = {"blur": [vv._clip(b) for b in bx.get("blur") or [] if ok(b)][:80],
                     "hl": [vv._clip(b) for b in bx.get("hl") or [] if ok(b)][:12],
                     "focus": vv._clip(bx["focus"]) if ok(bx.get("focus")) else None}
            kw = {"boxes": boxes, "boxesBy": "user", "boxesRev": m.get("boxesRev", 0) + 1}
            if idle and has_view:
                kw["status"] = "process"
            vv.mupdate(vid, mid, **kw)
        elif act == "reset":
            kw = {"boxesBy": "claude", "rev": m.get("rev", 0) + 1}
            if idle:
                kw["status"] = "analyze" if has_view else "queued"
            vv.mupdate(vid, mid, **kw)
        elif act == "retry":
            if not idle:
                return 409, {"error": "هنوز در حال کار است."}
            vv.mupdate(vid, mid, status="analyze" if has_view else "queued", err="")
        elif act == "del":
            vv.media_delete(vid, mid)
        else:
            return 400, {"error": "عمل نامعتبر."}
    if act == "del":
        light_preview(vid)
    else:
        vv.media_kick(vid, media_changed)
    return 200, {"ok": True}


def site_changed(vid, sid):
    """عکس یک سایت آماده شد (یا نشد)؛ پیش‌نمایش تازه می‌شود."""
    light_preview(vid)


def site_upload(h, vid, sid, name):
    """POST /api/video/upload?id=&name=&site=<sid> — اسکرین‌شات خود کاربر برای سایتی که عکسش گرفته نشد."""
    ext = Path(name).suffix.lower()
    n = int(h.headers.get("Content-Length") or 0)
    if not exists(vid) or not vs.sget(vid, sid) or ext not in vv.IMG_EXT or not 0 < n <= 60 * 1024 ** 2:
        h.rfile.read(n) if 0 < n <= 64 * 1024 else None
        return h._json({"error": "اسکرین‌شات (PNG، JPG، HEIC) بفرست."}, 400)
    d = vs.sdir(vid, sid)
    d.mkdir(parents=True, exist_ok=True)
    for old in d.glob("upload.*"):
        old.unlink()
    data, left = bytearray(), n
    while left > 0:
        chunk = h.rfile.read(min(4 * 1024 * 1024, left))
        if not chunk:
            break
        data += chunk
        left -= len(chunk)
    if left:
        return h._json({"error": "آپلود نیمه‌کاره ماند."}, 400)
    (d / f"upload{ext}").write_bytes(bytes(data))
    vs.supdate(vid, sid, status="upload", err="")
    vs.sites_kick(vid, site_changed)
    return h._json({"ok": True})


def site_api(vid, body):
    """POST /api/video/site — add (نشانی و جمله روی کلمه‌های انتخاب‌شده)، edit (نشانی یا جمله)، recapture، boxes (کادر دستی)، del."""
    act, sid = body.get("act"), body.get("sid")
    n = len(ve.jload(ve.pdir(vid) / "transcript.json", {}).get("words") or [])
    ok = lambda b: isinstance(b, list) and len(b) == 4 and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in b)
    boxes = []
    with ve.plock(vid):
        e = ve.jload(ve.pdir(vid) / "edit.json", {})
        sites = e.setdefault("sites", [])
        s = next((x for x in sites if x.get("id") == sid), None)
        if act == "add":
            url = vs.safe_url(str(body.get("url") or ""))
            w0, w1 = body.get("w0"), body.get("w1")
            if not url:
                return 400, {"error": "نشانی سایت معتبر نیست."}
            if not isinstance(w0, int) or not isinstance(w1, int) or not 0 <= w0 <= w1 < n:
                return 400, {"error": "کلمه‌ها نامعتبر است."}
            tpl = body.get("tpl") if body.get("tpl") in vs.TPL_SITE else "browser"
            stamp = int(time.time() * 1000)
            sid = f"s{stamp}"
            sites.append({"id": sid, "url": url, "quote": str(body.get("quote") or "").strip()[:400], "claim": "", "title": "",
                          "mode": vs.FRAME[tpl], "status": "queued", "src": "user", "rev": 0, "created": ve.now()})
            e.setdefault("vis", []).append({"id": f"w{stamp}", "kind": "site", "sid": sid, "tpl": tpl, "w0": w0, "w1": w1, "hw0": w0,
                                            "hw1": w1, "on": True, "src": "user", "pos": vs.default_pos(vid), "size": "m", "why": ""})
            e["vis"].sort(key=lambda v: v["w0"])
        elif not s:
            return 404, {"error": "این سایت پیدا نشد."}
        elif act in ("edit", "recapture"):
            if act == "edit" and "url" in body:
                url = vs.safe_url(str(body.get("url") or ""))
                if not url:
                    return 400, {"error": "نشانی سایت معتبر نیست."}
                s["url"] = url
            if act == "edit" and "quote" in body:
                s["quote"] = str(body.get("quote") or "").strip()[:400]
            s["rev"], s["fcTried"] = s.get("rev", 0) + 1, {}
            if s.get("status") not in ("queued", "capturing"):
                s["status"], s["err"] = "queued", ""
        elif act == "boxes":
            boxes = [vv._clip(b) for b in body.get("boxes") or [] if ok(b)][:12]
        elif act == "del":
            e["sites"] = [x for x in sites if x.get("id") != sid]
            gone = {v["id"] for v in e.get("vis") or [] if v.get("sid") == sid}
            e["vis"] = [v for v in e.get("vis") or [] if v["id"] not in gone]
            e["sfx"] = [x for x in e.get("sfx") or [] if x.get("link") not in gone]
        else:
            return 400, {"error": "عمل نامعتبر."}
        ve.jsave(ve.pdir(vid) / "edit.json", e)
    if act == "boxes":
        vs.set_boxes(vid, sid, boxes)
    elif act == "del":
        shutil.rmtree(vs.sdir(vid, sid), ignore_errors=True)
    elif act == "add":
        vs._add_sfx(vid)
    vs.sites_kick(vid, site_changed)
    light_preview(vid)
    return 200, {"ok": True, **({"sid": sid} if act == "add" else {})}


def screen_api(vid, body):
    """POST /api/video/screen — زوم (zoom_add روی کلمه‌های انتخاب‌شده، zoom برای جعبه/هایلایت/شدت/روشن، zoom_del) و
    محو اطلاعات حساس (blur_add، blur، blur_del). زوم فقط HTML را عوض می‌کند؛ محو در ویدیوی سبک پخته می‌شود."""
    act = body.get("act")
    ok = lambda b: isinstance(b, list) and len(b) == 4 and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in b)
    words = ve.jload(ve.pdir(vid) / "transcript.json", {}).get("words") or []
    n, res, heavy, frame_t = len(words), {"ok": True}, act.startswith("blur") if isinstance(act, str) else False, None
    with ve.plock(vid):
        e = ve.jload(ve.pdir(vid) / "edit.json", {})
        if act in ("zoom_add", "blur_add"):
            w0, w1 = body.get("w0"), body.get("w1")
            if not isinstance(w0, int) or not isinstance(w1, int) or not 0 <= w0 <= w1 < n:
                return 400, {"error": "کلمه‌ها نامعتبر است."}
            stamp = int(time.time() * 1000)
            if act == "zoom_add":
                frame_t = round(min(words[w1]["e"], words[w0]["s"] + 0.7), 3)
                e.setdefault("zooms", []).append({"id": f"u{stamp}", "w0": w0, "w1": w1, "t": frame_t, "box": [0.3, 0.3, 0.4, 0.4], "z": "m",
                                                  "hl": [], "target": "", "why": "", "on": True, "src": "user"})
                e["zooms"].sort(key=lambda z: z["w0"])
                res["zid"] = f"u{stamp}"
            else:
                s0, e0 = max(0.0, words[w0]["s"] - 0.3), words[w1]["e"] + 0.3
                frame_t = (s0 + e0) / 2
                e.setdefault("blurs", []).append({"id": f"u{stamp}", "s": round(s0, 2), "e": round(e0, 2), "box": [0.35, 0.42, 0.3, 0.08],
                                                  "type": "manual", "label": "دستی", "on": True, "src": "user"})
                res["bid"] = f"u{stamp}"
        elif act in ("zoom", "zoom_del"):
            z = next((x for x in e.get("zooms") or [] if x.get("id") == body.get("zid")), None)
            if not z:
                return 404, {"error": "این زوم پیدا نشد."}
            if act == "zoom_del":
                e["zooms"].remove(z)
            else:
                if ok(body.get("box")):
                    z["box"] = vv._clip(body["box"])
                if isinstance(body.get("hl"), list):
                    z["hl"] = [vv._clip(b) for b in body["hl"] if ok(b)][:6]
                if body.get("z") in vsc.ZOOM_CAP:
                    z["z"] = body["z"]
                if "on" in body:
                    z["on"] = bool(body["on"])
        elif act in ("blur", "blur_del"):
            b = next((x for x in e.get("blurs") or [] if x.get("id") == body.get("bid")), None)
            if not b:
                return 404, {"error": "این محو پیدا نشد."}
            if act == "blur_del":
                e["blurs"].remove(b)
            else:
                if ok(body.get("box")):
                    b["box"] = vv._clip(body["box"])
                if "on" in body:
                    b["on"] = bool(body["on"])
        else:
            return 400, {"error": "عمل نامعتبر."}
        ve.jsave(ve.pdir(vid) / "edit.json", e)
    if frame_t is not None:
        vsc.ensure_frame(vid, frame_t)
    if heavy:
        schedule_preview(vid, 0.3)
    else:
        light_preview(vid)
    return 200, res


def handle_upload(h):
    """POST /api/video/upload?id=&name= — بدنه خودِ فایل است، نه JSON. با &asset=1 عکس یا ویدیوی روی ویدیو است."""
    q = parse_qs(urlparse(h.path).query)
    vid, name = q.get("id", [""])[0], unquote(q.get("name", [""])[0])
    if q.get("asset", [""])[0] == "1":
        return media_upload(h, vid, name)
    if q.get("site", [""])[0]:
        return site_upload(h, vid, q["site"][0], name)
    if q.get("cover", [""])[0] == "1":
        return cover_upload(h, vid, name)
    ext = Path(name).suffix.lower()
    n = int(h.headers.get("Content-Length") or 0)
    if not exists(vid) or ext not in VIDEO_EXT or not 0 < n <= MAX_UPLOAD:
        h.rfile.read(n) if 0 < n <= 64 * 1024 else None
        return h._json({"error": "فایل ویدیو (mp4/mov/m4v/webm) بفرست."}, 400)
    d = ve.pdir(vid) / "src"
    d.mkdir(parents=True, exist_ok=True)
    part = d / f"upload{ext}.part"
    left = n
    with open(part, "wb") as f:
        while left > 0:
            chunk = h.rfile.read(min(4 * 1024 * 1024, left))
            if not chunk:
                break
            f.write(chunk)
            left -= len(chunk)
    if left:
        part.unlink(missing_ok=True)
        return h._json({"error": "آپلود نیمه‌کاره ماند."}, 400)
    for old in d.glob("original.*"):
        old.unlink()
    part.replace(d / f"original{ext}")
    proj_update(vid, srcName=name[:200], srcSize=n, uploaded=ve.now(), steps={})
    start(vid, "all")
    return h._json({"ok": True})


def cover_upload(h, vid, name):
    """POST /api/video/upload?id=&name=&cover=1 — عکس خود کاربر برای کاور ریلز (فاز ۶)."""
    ext = Path(name).suffix.lower()
    n = int(h.headers.get("Content-Length") or 0)
    if not exists(vid) or ext not in vv.IMG_EXT or not 0 < n <= 40 * 1024 ** 2:
        h.rfile.read(n) if 0 < n <= 64 * 1024 else None
        return h._json({"error": "عکس (JPG، PNG، HEIC) تا ۴۰ مگ بفرست."}, 400)
    data, left = bytearray(), n
    while left > 0:
        chunk = h.rfile.read(min(4 * 1024 * 1024, left))
        if not chunk:
            break
        data += chunk
        left -= len(chunk)
    if left:
        return h._json({"error": "آپلود نیمه‌کاره ماند."}, 400)
    try:
        vp.cover_upload(vid, bytes(data), ext)
    except Exception as e:
        return h._json({"error": str(e)[:300]}, 400)
    return h._json({"ok": True})


# ---------------- کاور، کپشن و انتشار (فاز ۶) ----------------
def post_start(vid, task, **kw):
    """کارهای پنل انتشار جدا از کار اصلی پروژه (JOBS[vid:post])؛ انتشار جلوی ویرایش را نمی‌گیرد و در /api/video/status دیده می‌شود."""
    key = vid + ":post"
    with JLOCK:
        if JOBS.get(key, {}).get("state") == "running":
            return False
        JOBS[key] = {"state": "running", "task": task, "msg": "", "error": "", "started": time.time(), "pct": None,
                     "dry": kw.get("dry"), "permalink": "", "retry": False}

    def go():
        js = lambda **x: jset(key, **x)
        say = lambda m: js(msg=m)
        try:
            if task == "cands":
                vp.find_cands(vid, say)
            elif task == "write":
                vp.write_post(vid, kw.get("what", "all"), kw.get("comment", ""), say)
            elif task == "cover":
                vp.render_cover(vid)
            elif task == "publish":
                vp.publish(vid, js, kw.get("dry", True), HEAVY)
            elif task == "resume":
                vp.resume(vid, js, kw.get("now", False))
            if jget(key).get("state") == "running":
                jset(key, state="done", msg=jget(key).get("msg", "") if task in ("publish", "resume") else "", finished=time.time())
        except Exception as e:
            jset(key, state="error", error=str(e)[:600], msg="", pct=None)

    threading.Thread(target=go, daemon=True).start()
    return True


def post_run(vid, body):
    task = body.get("task")
    if task in ("publish", "resume"):
        return 410, {"error": "انتشار مستقیم در این استودیو نیست؛ ویدیو و کاور را دانلود کن و خودت منتشر کن."}
    if task not in ("cands", "write", "cover"):
        return 400, {"error": "کار نامعتبر."}
    kw = {}
    if task == "write":
        if body.get("what") not in ("all", "caption", "titles"):
            return 400, {"error": "بخش نامعتبر."}
        if running(vid) and jget(vid).get("step") == "post":
            return 409, {"error": "ساخت کامل همین حالا دارد کپشن را می‌نویسد."}
        kw = {"what": body["what"], "comment": str(body.get("comment") or "").strip()[:1500]}
    elif task == "publish":
        dry = body.get("dry") is not False
        if not dry and body.get("sure") is not True:          # انتشار واقعی فقط با تیک «مطمئنم»
            return 400, {"error": "برای انتشار واقعی تأیید لازم است."}
        kw = {"dry": dry}
    elif task == "resume":
        kw = {"now": body.get("now") is True and body.get("sure") is True}
    return (200, {"ok": True}) if post_start(vid, task, **kw) else (409, {"error": "یک کار انتشار روی این ویدیو در حال اجراست."})


def serve_media(h, p):
    """GET /video-media/<id>/<path> با Range (برای <video> و iframe پیش‌نمایش)."""
    m = re.match(r"^/video-media/([A-Za-z0-9_-]{1,64})/(.+)$", p)
    if not m or not exists(m.group(1)) or not MEDIA_OK.match(m.group(2)):
        return h._json({"error": "not found"}, 404)
    f = ve.pdir(m.group(1)) / m.group(2)
    if not f.is_file():
        return h._json({"error": "not found"}, 404)
    size = f.stat().st_size
    ctype = CTYPE.get(f.suffix.lower(), "application/octet-stream")
    start_b, end_b, code = 0, size - 1, 200
    rng = h.headers.get("Range") or ""
    mm = re.match(r"bytes=(\d*)-(\d*)", rng)
    if mm and size:
        if mm.group(1):
            start_b = int(mm.group(1))
            end_b = int(mm.group(2)) if mm.group(2) else size - 1
        elif mm.group(2):
            start_b = max(0, size - int(mm.group(2)))
        end_b = min(end_b, size - 1)
        if start_b > end_b:
            h.send_response(416)
            h.send_header("Content-Range", f"bytes */{size}")
            h.end_headers()
            return
        code = 206
    length = end_b - start_b + 1 if size else 0
    h.send_response(code)
    h.send_header("Content-Type", ctype)
    h.send_header("Accept-Ranges", "bytes")
    h.send_header("Content-Length", str(length))
    h.send_header("Cache-Control", "no-store")
    if code == 206:
        h.send_header("Content-Range", f"bytes {start_b}-{end_b}/{size}")
    if m.group(2) == "out/final.mp4" and "dl=1" in (urlparse(h.path).query or ""):
        h.send_header("Content-Disposition", f'attachment; filename="{m.group(1)}.mp4"')
    h.end_headers()
    try:
        with open(f, "rb") as fh:
            fh.seek(start_b)
            left = length
            while left > 0:
                b = fh.read(min(1024 * 1024, left))
                if not b:
                    break
                h.wfile.write(b)
                left -= len(b)
    except (BrokenPipeError, ConnectionResetError):
        pass


# ---------------- داده برای صفحه ----------------
def summary(vid):
    p = ve.jload(ve.pdir(vid) / "project.json", {})
    info = p.get("info") or {}
    d = ve.pdir(vid)
    return {"id": vid, "title": p.get("title") or "بی‌نام", "kind": p.get("kind", "reel"), "created": p.get("created", ""),
            "dur": info.get("masterDur") or info.get("dur"), "outDur": (p.get("render") or {}).get("dur"),
            "thumb": (d / "thumb.jpg").exists(), "final": (d / "out" / "final.mp4").exists(),
            "steps": p.get("steps") or {}, "job": jget(vid)}


def list_projects():
    if not ve.DIR.exists():
        return []
    out = [summary(f.parent.name) for f in ve.DIR.glob("*/project.json") if ve.safe_id(f.parent.name)]
    return sorted(out, key=lambda x: x["created"], reverse=True)


def payload(vid):
    s = summary(vid)
    d = ve.pdir(vid)
    if not vv.media_busy(vid) and any(m.get("status") in vv.WORK for m in vv.mlist(vid)):
        vv.media_kick(vid, media_changed)          # بعد از ری‌استارت سرور، کار نیمه‌تمام فایل‌ها ادامه پیدا می‌کند
    if not vs.sites_busy(vid) and any(st.get("status") in ("queued", "upload", "capturing") for st in vs.slist(vid)):
        for st in vs.slist(vid):
            if st.get("status") == "capturing":    # کارگر قبلی با ری‌استارت مرد
                vs.supdate(vid, st["id"], status="queued")
        vs.sites_kick(vid, site_changed)
    res = {**s, "project": ve.jload(d / "project.json", {}), "styles": ve.STYLES, "rhythms": list(ve.RHYTHM)}
    if not (d / "transcript.json").exists():
        return {**res, "media": vv.media_view(vid), "mediaBusy": vv.media_busy(vid)}
    dv = ve.derive(vid)
    tm, edit = dv["tmap"], dv["edit"]
    words = [{"i": w["i"], "w": ve.disp(dv["words"], edit.get("fix"), w["i"]), "raw": w["w"], "alt": w.get("alt"),
              "s": w["s"], "e": w["e"], "o": None if w["i"] in dv["cut"] else round(tm.out(w["s"]), 3)}
             for w in dv["words"]]
    pv = d / "comp" / "preview.html"
    lib = ve.sfx_lib()
    res.update({
        "edit": {k: edit.get(k) for k in ("cuts", "fix", "fixUser", "emph", "manual", "pauses", "capPos", "summary", "notes", "decidedAt",
                                          "sfxSummary", "visSummary", "sitesSummary", "zoomSummary")},
        "faces": (d / "faces.json").exists(), "posNames": ve.POS_FA, "sizes": ve.SIZE_FA,
        "prevSections": sorted((edit.get("prev") or {}).keys()),
        "opts": dv["opts"], "words": words, "cut": sorted(dv["cut"]), "keeps": dv["keeps"],
        "outDur": round(tm.dur, 2), "srcDur": dv["dur"],
        "caps": [{"id": c["id"], "s": c["s"], "e": c["e"], "text": ve.clean_caption_text(c["text"]),
                  "w": [w["i"] for w in c["words"]], "pos": c.get("pos"), "auto": c.get("auto", True)} for c in dv["caps"]],
        "preview": int(pv.stat().st_mtime * 1000) if pv.exists() and (d / "comp" / "assets" / "proxy_cut.mp4").exists() else 0,
        "finalAt": int((d / "out" / "final.mp4").stat().st_mtime * 1000) if s["final"] else 0,
        "editAt": int((d / "edit.json").stat().st_mtime * 1000) if (d / "edit.json").exists() else 0,
        "render": res["project"].get("render"),
        "engine": ve.jload(d / "transcript.json", {}).get("engine"),
        "sfx": [{k: c.get(k) for k in ("id", "w", "snd", "cat", "why", "on", "src", "g", "at", "skip")} for c in dv["sfx"]],
        "sfxLib": {k: {"fa": v["fa"], "cat": v["cat"], "dur": v["dur"]} for k, v in lib["sounds"].items()},
        "sfxCats": {k: v["fa"] for k, v in lib["cats"].items()}, "sfxLevels": ve.SFX_LEVEL_FA,
        "media": vv.media_view(vid), "mediaBusy": vv.media_busy(vid), "vis": vv.vis_view(dv),
        "visTpls": {"media": vv.TPL_MEDIA, "video": list(vv.TPL_VIDEO), "gfx": vv.TPL_GFX, "site": vs.TPL_SITE, "pos": vv.POS,
                    "sitePos": vs.POS_SITE, "size": vv.VSIZE_FA},
        "sites": vs.sites_view(vid), "sitesBusy": vs.sites_busy(vid),
        "canvas": dv["kind"], **vsc.views(vid, dv),
        "post": vp.view(vid, jget(vid + ":post"), dv["kind"]),
    })
    return res


# ---------------- ویرایش‌ها ----------------
def edit(vid, body):
    op = body.get("op")
    rebuild, kick_sites = "full", False           # full = برش/صدا عوض شده؛ light = فقط ظاهر
    with ve.plock(vid):
        e = ve.jload(ve.pdir(vid) / "edit.json", {})
        n = len(ve.jload(ve.pdir(vid) / "transcript.json", {}).get("words") or [])
        if op == "words":                  # حذف/برگرداندن دستی کلمه‌ها (برنده بر برش‌های Claude)
            ids = [int(i) for i in body.get("ids") or [] if str(i).isdigit() and int(i) < n]
            man = e.setdefault("manual", {})
            for i in ids:
                if body.get("cut") is None:
                    man.pop(str(i), None)
                else:
                    man[str(i)] = 1 if body.get("cut") else 0
        elif op == "cut":                  # روشن/خاموش یک برش Claude
            for c in e.get("cuts") or []:
                if c.get("id") == body.get("cutId"):
                    c["on"] = bool(body.get("on"))
                    for i in range(c["w0"], c["w1"] + 1):
                        (e.get("manual") or {}).pop(str(i), None)
        elif op == "fix":                  # متن یک کلمه در زیرنویس
            i = int(body.get("i", -1))
            if not 0 <= i < n:
                return 400, {"error": "کلمه پیدا نشد."}
            t = ve.norm_fa(str(body.get("text") or ""))[:80]
            e.setdefault("fix", {})[str(i)] = t
            e["fixUser"] = sorted(set(e.get("fixUser") or []) | {str(i)}, key=int)
            rebuild = "light"
        elif op == "capfix":               # متن یک تکه‌ی زیرنویس، یک‌جا؛ روی همان کلمه‌ها پخش می‌شود
            ids = sorted({int(i) for i in body.get("ids") or [] if str(i).isdigit() and int(i) < n})
            t = str(body.get("text") or "").strip()[:400]
            if not ids:
                return 400, {"error": "تکه پیدا نشد."}
            if not t:
                return 400, {"error": "متن خالی است. برای حذف این حرف از «✂ حذف» در «متن و برش» استفاده کن."}
            words = ve.jload(ve.pdir(vid) / "transcript.json", {}).get("words") or []
            ch = ve.cap_fix(words, e.get("fix") or {}, ids, t)
            if not ch:
                return 200, {"ok": True, "changed": 0}
            e.setdefault("fix", {}).update(ch)
            e["fixUser"] = sorted(set(e.get("fixUser") or []) | set(ch), key=int)
            rebuild = "light"
        elif op == "emph":
            s = set(e.get("emph") or [])
            for i in body.get("ids") or []:
                if str(i).isdigit() and int(i) < n:
                    (s.add if body.get("on") else s.discard)(int(i))
            e["emph"] = sorted(s)
            rebuild = "light"
        elif op == "cappos":               # جای زیرنویس برای این کلمه‌ها: auto | top | mid | bot | عدد (کسری از ارتفاع، از کشیدن)
            pos = body.get("pos")
            if isinstance(pos, (int, float)) and not isinstance(pos, bool):
                pos = round(min(0.9, max(0.02, float(pos))), 3)
            elif pos not in ("auto", "top", "mid", "bot"):
                return 400, {"error": "جای نامعتبر."}
            cp = e.setdefault("capPos", {})
            for i in body.get("ids") or []:
                if str(i).isdigit() and int(i) < n:
                    if pos == "auto":
                        cp.pop(str(i), None)
                    else:
                        cp[str(i)] = pos
            rebuild = "light"
        elif op == "sfx":                  # افکت صوتی: روشن/خاموش، عوض کردن صدا، بلندی، افزودن روی شروع یک کلمه، حذف
            lib, lst, act = ve.sfx_lib()["sounds"], e.setdefault("sfx", []), body.get("act")
            x = next((c for c in lst if c.get("id") == body.get("sid")), None)
            if act == "add":
                i, snd = body.get("w"), body.get("snd")
                if not isinstance(i, int) or not 0 <= i < n or snd not in lib:
                    return 400, {"error": "کلمه یا صدا نامعتبر است."}
                lst.append({"id": f"u{int(time.time() * 1000)}", "w": i, "snd": snd, "cat": lib[snd]["cat"], "why": "",
                            "on": True, "src": "user"})
                lst.sort(key=lambda c: c["w"])
            elif not x:
                return 404, {"error": "این افکت پیدا نشد."}
            elif act == "on":
                x["on"] = bool(body.get("on"))
            elif act == "snd" and body.get("snd") in lib:
                x["snd"] = body["snd"]
            elif act == "gain" and isinstance(body.get("g"), (int, float)) and not isinstance(body.get("g"), bool):
                x["g"] = max(-12.0, min(9.0, float(body["g"])))
            elif act == "del":
                lst.remove(x)
            else:
                return 400, {"error": "عمل نامعتبر."}
            rebuild = "light"
        elif op == "vis":                  # تصویرها: روشن/خاموش، قالب، جا، اندازه، متن گرافیک، حذف، افزودن روی کلمه‌های انتخاب‌شده
            lst, act = e.setdefault("vis", []), body.get("act")
            x = next((v for v in lst if v.get("id") == body.get("oid")), None)
            if act == "add":
                m = vv.mget(vid, body.get("mid"))
                w0, w1 = body.get("w0"), body.get("w1")
                if not m or not isinstance(w0, int) or not isinstance(w1, int) or not 0 <= w0 <= w1 < n:
                    return 400, {"error": "فایل یا کلمه‌ها نامعتبر است."}
                tpl = (m.get("an") or {}).get("tpl") or "card"
                lst.append({"id": f"u{int(time.time() * 1000)}", "kind": "media", "mid": m["id"], "tpl": tpl, "w0": w0, "w1": w1,
                            "on": True, "src": "user", "pos": "auto", "size": "m", "why": ""})
                lst.sort(key=lambda v: v["w0"])
            elif not x:
                return 404, {"error": "این تصویر پیدا نشد."}
            elif act == "on":
                x["on"] = bool(body.get("on"))
            elif act == "tpl" and x.get("kind") == "site":
                if body.get("tpl") not in vs.TPL_SITE:
                    return 400, {"error": "قالب نامعتبر."}
                x["tpl"] = body["tpl"]
                md = vs.FRAME[x["tpl"]]
                for st in e.get("sites") or []:          # قاب گوشی عکس موبایل لازم دارد و برعکس
                    if st.get("id") == x.get("sid"):
                        st["mode"] = md
                        if not (vs.sdir(vid, st["id"], md) / "geo.json").exists() and st.get("status") not in ("queued", "capturing"):
                            st["status"], kick_sites = "queued", True
            elif act == "tpl" and x.get("kind") == "media":
                m = vv.mget(vid, x.get("mid")) or {}
                if body.get("tpl") not in (vv.TPL_VIDEO if m.get("type") == "video" else vv.TPL_MEDIA):
                    return 400, {"error": "قالب نامعتبر."}
                x["tpl"] = body["tpl"]
            elif act == "pos" and body.get("pos") in (vs.POS_SITE if x.get("kind") == "site" else vv.POS):
                x["pos"] = body["pos"]
                if x.get("kind") == "site":    # در «صحنه» ماژیک دیرتر شروع می‌شود؛ صدای ماژیک هم با آن جابه‌جا شود
                    threading.Thread(target=lambda: (vs._add_sfx(vid), light_preview(vid)), daemon=True).start()
            elif act == "size" and body.get("size") in vv.VSIZE:
                x["size"] = body["size"]
            elif act == "data" and x.get("kind") == "gfx" and isinstance(body.get("data"), dict):
                old = (x.get("data") or {}).get("domain")
                x["data"] = vv._gfx_data(x["tpl"], {**(x.get("data") or {}), **body["data"]})
                dom = x["data"].get("domain")
                if dom and dom != old:          # لوگوی تازه در پس‌زمینه؛ بعد پیش‌نمایش
                    threading.Thread(target=lambda: (vv.fetch_logo(dom), light_preview(vid)), daemon=True).start()
            elif act == "del":
                lst.remove(x)
                e["sfx"] = [c for c in e.get("sfx") or [] if c.get("link") != x["id"]]
                if x.get("kind") == "site":
                    e["sites"] = [st for st in e.get("sites") or [] if st.get("id") != x.get("sid")]
            else:
                return 400, {"error": "عمل نامعتبر."}
            rebuild = "light"
        elif op == "pause":                # مکث بعد از این کلمه بماند
            s = set(e.get("pauses") or [])
            i = int(body.get("i", -1))
            (s.add if body.get("on") else s.discard)(i)
            e["pauses"] = sorted(x for x in s if 0 <= x < n)
        elif op == "opts":
            k, v = body.get("key"), body.get("value")
            ok = {"style": lambda x: x in ve.STYLES, "rhythm": lambda x: x in ve.RHYTHM, "size": lambda x: x in ve.SIZE,
                  "punch": lambda x: isinstance(x, bool), "captions": lambda x: isinstance(x, bool),
                  "voiceClean": lambda x: isinstance(x, bool), "sfx": lambda x: isinstance(x, bool),
                  "sfxLevel": lambda x: x in ve.SFX_LEVEL, "vertical": lambda x: isinstance(x, bool),
                  "vlayout": lambda x: x in vsc.VLAYOUT, "vbg": lambda x: x in vsc.VBG,
                  "autoCut": lambda x: isinstance(x, bool), "capsOver": lambda x: isinstance(x, bool)}
            if k not in ok or not ok[k](v):
                return 400, {"error": "تنظیم نامعتبر."}
            kind = ve.jload(ve.pdir(vid) / "project.json", {}).get("kind", "reel")
            e.setdefault("opts", ve.default_opts(kind))[k] = v
            if k in ("style", "size", "captions", "capsOver", "punch", "sfx", "sfxLevel", "vertical", "vlayout", "vbg"):
                rebuild = "light"
        elif op == "title":
            t = str(body.get("title") or "").strip()[:80]
            if t:
                proj_update(vid, title=t, titleSet=True)
            return 200, {"ok": True}
        else:
            return 400, {"error": "عمل نامعتبر."}
        ve.jsave(ve.pdir(vid) / "edit.json", e)
    if rebuild == "light":
        light_preview(vid)
    else:
        schedule_preview(vid)
    if kick_sites:
        vs.sites_kick(vid, site_changed)
    return 200, {"ok": True}


def undo(vid, section):
    secs = {"cuts": ("cuts",), "captions": ("fix", "emph", "breaks"), "sfx": ("sfx",), "vis": ("vis",), "zooms": ("zooms",),
            "blurs": ("blurs",)}.get(section)
    if not secs:
        return 400, {"error": "بخش نامعتبر."}
    with ve.plock(vid):
        e = ve.jload(ve.pdir(vid) / "edit.json", {})
        prev = e.get("prev") or {}
        if not any(s in prev for s in secs):
            return 404, {"error": "نسخه‌ی قبلی نیست."}
        for s in secs:
            if s in prev:
                e[s], prev[s] = prev[s], e.get(s)
        if section == "captions":          # اصلاح‌های دستی کاربر با «نسخه‌ی قبل» هم نمی‌روند
            now = prev.get("fix") or {}
            for k in e.get("fixUser") or []:
                if k in now:
                    e.setdefault("fix", {})[k] = now[k]
        if section == "vis":               # افکت‌های ورود همان چیدمان هم برمی‌گردند
            now_vis_sfx = [x for x in e.get("sfx") or [] if x.get("src") == "vis"]
            e["sfx"] = [x for x in e.get("sfx") or [] if x.get("src") != "vis"] + (prev.get("visSfx") or [])
            prev["visSfx"] = now_vis_sfx
        ve.jsave(ve.pdir(vid) / "edit.json", e)
    if section in ("sfx", "vis", "zooms"):
        light_preview(vid)
    else:
        schedule_preview(vid, 0.1)
    return 200, {"ok": True}


def new_project(body):
    kind = body.get("kind") if body.get("kind") in ve.CANVAS else "reel"
    vid = "v" + str(int(time.time() * 1000))
    title = str(body.get("title") or "").strip()[:80]
    raw = body.get("parts") if isinstance(body.get("parts"), dict) else {}
    parts = {k: raw.get(k, True) is not False for k, _, _ in PARTS}
    ve.jsave(ve.pdir(vid) / "project.json", {"id": vid, "title": title or "ویدیوی تازه", "titleSet": bool(title),
                                             "kind": kind, "created": ve.now(), "steps": {}, "parts": parts})
    # زیرنویس، صدای تمیز و برش خودکار تنظیم‌اند (خاموش یعنی در خروجی نیست)؛ بقیه فقط در «ساخت کامل» اجرا نمی‌شوند
    ve.jsave(ve.pdir(vid) / "edit.json", {"opts": {**ve.default_opts(kind), "captions": parts["captions"],
                                                   "voiceClean": parts["voice"], "autoCut": parts["cuts"]}})
    st = ve.jload(ve.SETTINGS, {})                     # انتخاب این بار، پیش‌فرض آپلود بعدی
    st["parts"] = {**st.get("parts", {}), **{k: v for k, v in parts.items() if k in raw}}
    ve.jsave(ve.SETTINGS, st)
    return vid


def delete(vid):
    """به سطل می‌رود، پاک نمی‌شود: data/videos/.trash/<id>"""
    if running(vid) or running(vid + ":post"):
        return 409, {"error": "اول کار در حال اجرا را متوقف کن."}
    trash = ve.DIR / ".trash"
    trash.mkdir(parents=True, exist_ok=True)
    shutil.move(str(ve.pdir(vid)), str(trash / f"{vid}-{int(time.time())}"))
    return 200, {"ok": True}


# ---------------- مسیرها ----------------
def handle_get(p, q):
    """(code, payload, ctype) — ctype=None یعنی payload جیسون است."""
    if p in STATIC:
        name, ctype = STATIC[p]
        return 200, (APP / name).read_bytes(), ctype
    if p == "/api/video/list":
        last = ve.jload(ve.SETTINGS, {}).get("parts") or {}
        return 200, {"videos": list_projects(), "styles": ve.STYLES,
                     "parts": [{"k": k, "fa": fa, "screen": sc, "on": last.get(k, True) is not False} for k, fa, sc in PARTS]}, None
    if p == "/api/video/status":
        with JLOCK:
            jobs = {k: dict(v) for k, v in JOBS.items()}
        return 200, {"jobs": jobs, "running": sorted(k for k, v in jobs.items() if v.get("state") == "running")}, None
    if p == "/api/video/sfx-file":           # شنیدن یک صدای کتابخانه در رابط
        snd = ve.sfx_lib()["sounds"].get(q.get("k", [""])[0])
        f = ve.SFX_DIR / snd["file"] if snd else None
        if not f or not f.is_file():
            return 404, {"error": "not found"}, None
        return 200, f.read_bytes(), "audio/mpeg"
    if p == "/api/video/project":
        vid = q.get("id", [""])[0]
        if not exists(vid):
            return 404, {"error": "این ویدیو پیدا نشد."}, None
        return 200, payload(vid), None
    return None


def handle_post(p, body):
    if not p.startswith("/api/video/"):
        return None
    if p == "/api/video/new":
        return 200, {"ok": True, "id": new_project(body)}
    vid = body.get("id", "")
    if p == "/api/video/style-default":      # «پیش‌فرض من»: سبک و اندازه برای ویدیوهای بعدی
        if body.get("style") not in ve.STYLES or body.get("size", "m") not in ve.SIZE:
            return 400, {"error": "سبک نامعتبر."}
        st = ve.jload(ve.SETTINGS, {})
        st["style"], st["size"] = body["style"], body.get("size", "m")
        ve.jsave(ve.SETTINGS, st)
        return 200, {"ok": True}
    if not exists(vid):
        return 404, {"error": "این ویدیو پیدا نشد."}
    if p == "/api/video/run":
        step = body.get("step")
        if step not in ("all", "render", "preview", "decide", "transcribe", "faces", "ingest", "screen", "sfx", "sites", "vis", "post"):
            return 400, {"error": "مرحله‌ی نامعتبر."}
        if step == "render" and not (ve.pdir(vid) / "transcript.json").exists():
            return 409, {"error": "اول باید آماده‌سازی و متن تمام شود."}
        return (200, {"ok": True}) if start(vid, step) else (409, {"error": "یک کار روی این ویدیو در حال اجراست."})
    if p == "/api/video/regen":
        sec = body.get("section")
        if sec not in ("cuts", "captions", "sfx", "vis", "sites", "zooms", "blurs"):
            return 400, {"error": "بخش نامعتبر."}
        comment = str(body.get("comment") or "").strip()[:1500]
        return (200, {"ok": True}) if start(vid, "regen", comment, sec) else (409, {"error": "یک کار روی این ویدیو در حال اجراست."})
    if p == "/api/video/edit":
        return edit(vid, body)
    if p == "/api/video/media":
        return media_edit(vid, body)
    if p == "/api/video/site":
        return site_api(vid, body)
    if p == "/api/video/screen":
        return screen_api(vid, body)
    if p == "/api/video/undo":
        return undo(vid, body.get("section"))
    if p == "/api/video/post":
        return vp.edit(vid, body)
    if p == "/api/video/post-run":
        return post_run(vid, body)
    if p == "/api/video/cancel":
        ve.kill_project(vid)
        return 200, {"ok": True}
    if p == "/api/video/delete":
        return delete(vid)
    return 404, {"error": "not found"}
