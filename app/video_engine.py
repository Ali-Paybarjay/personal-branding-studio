"""تدوین ویدیو — موتور (بدون HTTP؛ سرورش app/video.py است).

مسیر: ویدیوی خام → آماده‌سازی با ffmpeg → متن با زمان هر کلمه (Gemini 3.5 Transcribe، دو بار) →
تصمیم‌های Claude (برش، اصلاح متن، تأکید، جای افکت صوتی، عکس و گرافیک) → نقشه‌ی زمان → ترکیب HTML (HyperFrames) → رندر.

- همه‌چیز به اندیس کلمه گره خورده، نه ثانیه. با هر تغییر برش، زمان خروجی همه‌چیز از نو حساب می‌شود.
- متن فارسی را Chrome می‌نویسد؛ ffmpeg این مک libass و drawtext ندارد.
- پیش‌نمایش همان ترکیب رندر است؛ فقط ویدیوی سبک و یک shim برای هم‌گام‌کردن دارد.

data/videos/<id>/
  project.json     اسم، نوع (reel|screen)، مشخصات فایل، وضعیت مرحله‌ها
  edit.json        تصمیم‌ها: برش‌ها، اصلاح کلمه‌ها، تأکید، افکت‌ها (sfx)، تصویرها (vis)، تنظیم‌ها، نظرها، نسخه‌ی قبل
  media.json + media/<mid>/  عکس و ویدیوی خود کاربر (فاز ۳، video_visuals.py)
  transcript.json  کلمه‌ها با زمان (منبع)
  master.mp4 · voice.wav · stt.ogg · env.json · proxy.mp4 · thumb.jpg
  comp/            index.html (رندر)، preview.html، assets/
  out/             final.mp4 · final.srt · mix.wav (صدای گوینده + افکت‌ها)
"""
import array, base64, bisect, difflib, json, math, os, re, shutil, signal, subprocess, sys, tempfile, threading, time, urllib.error, urllib.request
from html import escape
from pathlib import Path
import ai_models as am
import settings as cfg

APP = Path(__file__).resolve().parent
ROOT = APP.parent
DIR = ROOT / "data" / "videos"
MOD = ROOT / "modules" / "video"
BRAND_MD = ROOT / "brand" / "brand-core.md"
SETTINGS = DIR / "settings.json"

STT_MODEL = "gemini-3.5-transcribe"     # fa-IR، زمان کلمه‌ها؛ از ۲۶ اوت ۲۰۲۶
FPS = 30
CANVAS = {"reel": (1080, 1920), "screen": (1920, 1080)}
FR = 0.01                                # گام پوشش صدا (۱۰ میلی‌ثانیه)
RHYTHM = {"slow": (0.55, 0.14), "normal": (0.35, 0.10), "fast": (0.22, 0.07), "tight": (0.22, 0.07)}   # (بیشترین مکث، حاشیه‌ی دو طرف برش)
# «خیلی تند (بدون نفس)» (۲۰۲۶-۱۰-۰۹، درخواست کاربر): مکث‌های کوتاه و نفس‌ها هم بریده می‌شوند. فاصله‌های بین کلمه‌ها مثل
# «تند»؛ ولی سکوت واقعی و نفس (breath_runs) از ۰٫۲ ثانیه به بالا تا ۰٫۱۲ ثانیه کوتاه می‌شوند. حاشیه‌ی ۶۰ میلی‌ثانیه از لبه‌ی صدا،
# نه ۴۰: آغاز «ف»ِ «فقط» زیر آستانه‌ی سکوت است و با ۴۰ فقط ۲۰ میلی‌ثانیه جا داشت.
TIGHT = (0.08, 0.06)
STYLES = {"clean": "سفید ساده", "pill": "کپسول سرمه‌ای", "punch": "درشت و ضربه‌ای", "karaoke": "کارائوکه"}
NAVY, YELLOW, BG = "#1f2b3a", "#ffcc4d", "#0f151d"     # پیش‌فرض؛ brand_colors() از هسته‌ی برند پرشان می‌کند


def brand_colors():
    """(رنگ اصلی تیره، رنگ تأکید روشن) از «هسته‌ی برند ← هویت بصری»؛ اگر نبود، پیش‌فرض خنثی.
    زیرنویس و گرافیک‌ها با همین دو رنگ کشیده می‌شوند."""
    try:
        d = json.loads((ROOT / "brand" / "brand-core.json").read_text(encoding="utf-8"))
        pal = [c for c in (d["fields"].get("colors") or {}).get("v") or []
               if isinstance(c, dict) and re.fullmatch(r"#[0-9a-fA-F]{6}", c.get("hex") or "")]
    except Exception:
        pal = []
    def lum(h):
        r, g, b = (int(h[i:i + 2], 16) / 255 for i in (1, 3, 5))
        return 0.2126 * r + 0.7152 * g + 0.0722 * b
    dark = [c for c in pal if lum(c["hex"]) < 0.35]
    main = next((c for c in dark if c.get("role") == "اصلی"), dark[0] if dark else None)
    acc = next((c for c in pal if c.get("role") == "تأکیدی" and lum(c["hex"]) > 0.4), None) \
        or next((c for c in pal if 0.45 < lum(c["hex"]) < 0.9), None)
    return (main["hex"] if main else "#1f2b3a"), (acc["hex"] if acc else "#ffcc4d")


def brandify(css):
    """رنگ‌های ثابت قالب‌ها (سرمه‌ای و زرد نسخه‌ی اصلی) ← رنگ‌های برند کاربر."""
    navy, yellow = brand_colors()
    return (css.replace("#1a3c64", navy).replace("#1A3C64", navy)
               .replace("#ffdb58", yellow).replace("#FFDB58", yellow)
               .replace("rgba(255,219,88", "rgba({},{},{}".format(*(int(yellow[i:i + 2], 16) for i in (1, 3, 5)))))
STT_CHUNK = 20 * 60                      # Gemini با زمان کلمه‌ها تا ۳۰ دقیقه؛ تکه‌های ۲۰ دقیقه‌ای


def ffbin(n):
    return shutil.which(n) or f"/opt/homebrew/bin/{n}"


FFMPEG, FFPROBE = ffbin("ffmpeg"), ffbin("ffprobe")
HF_BIN = MOD / "node_modules" / ".bin" / "hyperframes"
FACETRACK_SRC = MOD / "facetrack.swift"
FACETRACK = MOD / "bin" / "facetrack"
# ناحیه‌های امن ریلز ۱۰۸۰×۱۹۲۰ (جست‌وجوی ۲۰۲۶-۱۰-۰۶): بالا حدود ۲۵۰px نوار اینستاگرام؛ پایین ۳۱۰ تا ۴۵۰px اسم، کپشن و
# ردیف صدا (اواخر ۲۰۲۵ حدود ۵۰px بزرگ‌تر شد)؛ راست حدود ۱۲۰px ستون لایک، کامنت، اشتراک و ذخیره در نیمه‌ی پایین.
# پایین زیرنویس باید دست‌کم ۴۵۰ تا ۴۸۰px بالاتر از لبه بماند. اندازه‌ی متن ۶۰ تا ۷۵px (پیش‌فرض ۶۵ تا ۷۰)؛ زیر ۵۵ برای تماشای بی‌صدا ضعیف است.
SAFE = {"reel": (0.14, 0.745), "screen": (0.02, 0.98)}      # بالای کادر زیرنویس ≥ اولی و پایینش ≤ دومی (کسری از ارتفاع)
CAP = {"reel": {"clean": (68, 800), "pill": (60, 800), "punch": (86, 900), "karaoke": (66, 800)},
       "screen": {"clean": (46, 800), "pill": (42, 800), "punch": (58, 900), "karaoke": (46, 800)}}   # (اندازه‌ی پایه px، وزن)
CAP_W = {"reel": 780, "screen": 1500}    # پهنای بیشینه‌ی یک خط؛ ریلز وسط‌چین از x=۱۵۰ تا ۹۳۰، پیش از ستون دکمه‌های راست
PILL_PAD = {"reel": (14, 30), "screen": (10, 24)}           # (عمودی، افقی)
SIZE = {"s": 0.88, "m": 1.0, "l": 1.14}
SIZE_FA = {"s": "کوچک", "m": "معمولی", "l": "بزرگ"}
WIDTH_SAFETY = 1.06                       # پهنای fontkit تا حدود ۵٪ با Chrome فرق دارد
MEASURE = MOD / "measure.mjs"
POS_FA = {"auto": "خودکار", "top": "بالا", "mid": "وسط", "bot": "پایین", "above": "بالای صورت", "below": "زیر صورت"}
SFX_DIR = MOD / "sfx"                     # کتابخانه‌ی افکت: manifest.json (اسم، دسته، hit، gain، مجوز) + MP3ها + CREDITS.md
SFX_LEVEL = {"low": -6.0, "mid": 0.0, "high": 4.0}         # بلندی کل افکت‌ها (dB)
SFX_LEVEL_FA = {"low": "آرام", "mid": "معمولی", "high": "بلند"}
SFX_GAP, SFX_POP_GAP, SFX_MAX_IMPACT = 1.2, 4.0, 2         # کمترین فاصله‌ی دو افکت و دو تأکید (ثانیه)؛ سقف ضربه‌ها
# دسته‌هایی که Claude پیشنهاد می‌دهد (عکس و ماژیک مال فاز ۳ و ۴اند)؛ دو افکت نزدیک به هم: مهم‌تر می‌ماند
SFX_PRI = {"money": 9, "whoosh": 8, "notify": 7, "negative": 7, "impact": 6, "ding": 6, "typing": 5, "click": 5,
           "sparkle": 4, "pop": 3}
WHISPER_MODEL = MOD / "models" / "ggml-large-v3-turbo.bin"   # اختیاری: فقط اگر کاربر خودش دانلودش کرده باشد


# ---------------- کمک‌ها ----------------
def now():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def safe_id(s):
    return isinstance(s, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,64}", s) is not None


def jload(p, default):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:
        return default


def jsave(p, obj):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(p)


def read_text(p, limit=None):
    try:
        t = Path(p).read_text(encoding="utf-8")
    except Exception:
        return ""
    return t[:limit] if limit else t


_LOCKS, _LOCKS_G = {}, threading.Lock()


def plock(vid):
    """قفل هر پروژه برای نوشتن edit.json/project.json."""
    with _LOCKS_G:
        return _LOCKS.setdefault(vid, threading.RLock())


def pdir(vid):
    return DIR / vid


# ---------------- پردازه‌ها (قابل‌کشتن، بدون یتیم) ----------------
_PIDS_G = threading.Lock()


def _pids_file(vid):
    return pdir(vid) / "job.json"


def _pid_add(vid, pid):
    with _PIDS_G:
        d = jload(_pids_file(vid), {})
        d["pids"] = sorted(set(d.get("pids", []) + [pid]))
        jsave(_pids_file(vid), d)


def _pid_del(vid, pid):
    with _PIDS_G:
        d = jload(_pids_file(vid), {})
        d["pids"] = [x for x in d.get("pids", []) if x != pid]
        jsave(_pids_file(vid), d)


def _killpg(pid, sig=signal.SIGTERM):
    try:
        os.killpg(pid, sig)
    except Exception:
        pass


def run(cmd, vid=None, timeout=None, input=None, cwd=None, env=None):
    """هر فرزند گروه پردازه‌ی خودش را دارد و PIDش در job.json ثبت می‌شود تا بعد از ری‌استارت کشته شود."""
    p = subprocess.Popen([str(c) for c in cmd], stdin=subprocess.PIPE if input is not None else subprocess.DEVNULL,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=cwd, env=env, start_new_session=True)
    if vid:
        _pid_add(vid, p.pid)
    try:
        out, err = p.communicate(input, timeout=timeout)
    except subprocess.TimeoutExpired:
        _killpg(p.pid, signal.SIGKILL)
        p.communicate()
        raise RuntimeError(f"{Path(str(cmd[0])).name}: وقت تمام شد")
    finally:
        if vid:
            _pid_del(vid, p.pid)
    if p.returncode != 0:
        tail = (err or b"").decode("utf-8", "replace").strip()[-900:]
        raise RuntimeError(f"{Path(str(cmd[0])).name} (کد {p.returncode}): {tail}")
    return out, err


def kill_project(vid):
    for pid in jload(_pids_file(vid), {}).get("pids", []):
        _killpg(pid)
    time.sleep(1.5)
    for pid in jload(_pids_file(vid), {}).get("pids", []):
        _killpg(pid, signal.SIGKILL)
    jsave(_pids_file(vid), {"pids": []})


def kill_orphans():
    """بعد از ری‌استارت سرور: هر ffmpeg/hyperframes/claude نیمه‌کاره‌ای که ثبت شده بود کشته می‌شود. (تدوین ویدیو فقط مک است)"""
    if os.name == "nt" or not DIR.exists():
        return
    for f in DIR.glob("*/job.json"):
        pids = jload(f, {}).get("pids", [])
        for pid in pids:
            _killpg(pid, signal.SIGKILL)
        if pids:
            jsave(f, {"pids": []})


# ---------------- ffprobe / آماده‌سازی ----------------
def _rate(x):
    try:
        n, d = str(x).split("/")
        return float(n) / float(d) if float(d) else 0.0
    except Exception:
        return 0.0


def probe(path):
    out, _ = run([FFPROBE, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", path])
    d = json.loads(out)
    ss = d.get("streams", [])
    v = next((s for s in ss if s.get("codec_type") == "video" and not (s.get("disposition") or {}).get("attached_pic")), None)
    a = next((s for s in ss if s.get("codec_type") == "audio"), None)
    if not v:
        raise ValueError("این فایل تصویر ندارد.")
    w, h = int(v.get("width") or 0), int(v.get("height") or 0)
    rot = 0
    for sd in v.get("side_data_list") or []:
        if "rotation" in sd:
            rot = int(float(sd["rotation"]))
    rot = rot or int(float((v.get("tags") or {}).get("rotate") or 0))
    if abs(rot) % 180 == 90:
        w, h = h, w
    fps = _rate(v.get("avg_frame_rate")) or _rate(v.get("r_frame_rate"))
    dur = float((d.get("format") or {}).get("duration") or v.get("duration") or 0)
    return {"w": w, "h": h, "fps": round(fps, 3), "dur": round(dur, 3), "vcodec": v.get("codec_name"),
            "audio": bool(a), "hdr": (v.get("color_transfer") or "") in ("arib-std-b67", "smpte2084"), "rotation": rot}


def ingest(vid, src, kind, step=lambda s: None):
    """master (۳۰ فریم ثابت، SDR، GOP ۳۰ برای جست‌وجوی HyperFrames)، voice.wav، stt.ogg، env.json، proxy، thumb."""
    d = pdir(vid)
    info = probe(src)
    W, H = CANVAS[kind]
    if kind == "reel":
        vf = f"scale={W}:{H}:force_original_aspect_ratio=increase:flags=lanczos,crop={W}:{H}"
    else:   # ضبط صفحه: نسبت خودش می‌ماند؛ تا ۲۵۶۰ پیکسل برای زوم‌های بعدی
        vf = "scale='min(2560,iw)':-2:flags=lanczos"
    vf += f",fps={FPS},format=yuv420p"
    enc = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "17", "-g", str(FPS), "-keyint_min", str(FPS),
           "-sc_threshold", "0", "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709", "-movflags", "+faststart"]
    step("آماده‌سازی تصویر (نسخه‌ی اصلی)…")
    master = d / "master.mp4"
    info["hdrNote"] = ""
    if info["hdr"]:
        try:   # HDR آیفون → SDR با VideoToolbox (هنوز با فایل واقعی آزموده نشده)
            run([FFMPEG, "-v", "error", "-y", "-hwaccel", "videotoolbox", "-hwaccel_output_format", "videotoolbox_vld", "-i", src,
                 "-map", "0:v:0", "-an", "-vf", "scale_vt=color_matrix=bt709:color_primaries=bt709:color_transfer=bt709,hwdownload,format=nv12," + vf,
                 *enc, master], vid)
            info["hdrNote"] = "HDR به SDR تبدیل شد."
        except RuntimeError:
            info["hdrNote"] = "تبدیل HDR نشد؛ رنگ‌ها ممکن است کم‌رنگ باشند."
    if not master.exists() or not info["hdrNote"].startswith("HDR به"):
        run([FFMPEG, "-v", "error", "-y", "-i", src, "-map", "0:v:0", "-an", "-vf", vf, *enc, master], vid)
    step("جدا کردن صدا…")
    if info["audio"]:
        run([FFMPEG, "-v", "error", "-y", "-i", src, "-map", "0:a:0", "-vn", "-ac", "1", "-ar", "48000", "-c:a", "pcm_s16le", d / "voice.wav"], vid)
    else:
        run([FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono", "-t", str(info["dur"]), "-c:a", "pcm_s16le", d / "voice.wav"], vid)
    run([FFMPEG, "-v", "error", "-y", "-i", d / "voice.wav", "-ac", "1", "-ar", "16000", "-c:a", "libopus", "-b:a", "32k",
         "-application", "voip", d / "stt.ogg"], vid)
    jsave(d / "env.json", envelope(d / "voice.wav", vid))
    step("ساخت نسخه‌ی سبک برای پیش‌نمایش…")
    pw = 540 if kind == "reel" else 960
    run([FFMPEG, "-v", "error", "-y", "-i", master, "-vf", f"scale={pw}:-2", "-c:v", "libx264", "-preset", "veryfast",
         "-crf", "30", "-g", "10", "-an", "-movflags", "+faststart", d / "proxy.mp4"], vid)
    run([FFMPEG, "-v", "error", "-y", "-ss", f"{min(1.0, info['dur'] / 2):.2f}", "-i", master, "-frames:v", "1",
         "-vf", "scale=360:-2", "-q:v", "4", d / "thumb.jpg"], vid)
    info["masterDur"] = probe(master)["dur"]
    return info


def envelope(wav, vid=None):
    """بلندی صدا در هر ۱۰ میلی‌ثانیه (dB)؛ برای پیدا کردن سکوت و جای دقیق برش."""
    raw, _ = run([FFMPEG, "-v", "error", "-i", wav, "-ac", "1", "-ar", "16000", "-f", "s16le", "-"], vid)
    a = array.array("h")
    a.frombytes(raw[: len(raw) // 2 * 2])
    n, out, full = 160, [], 32768.0 ** 2
    for i in range(0, len(a), n):
        ch = a[i:i + n]
        ms = math.sumprod(ch, ch) / len(ch) if len(ch) else 0
        out.append(round(10 * math.log10(ms / full + 1e-12), 1))
    return out


BREATH_V = 3


def breath_runs(vid, env=None):
    """بازه‌های نفس (برای ریتم «خیلی تند»)، کش در breath.json؛ روی ۱۵ دقیقه حدود ۲ ثانیه.
    نفس صدای بی‌زیروبمی است: آرام (بالای سکوت، زیر ‎-38dB)، نویزی (flatness ≥ ۰٫۴۵)، تیز (centroid ≥ ۱۸۰۰Hz) و دست‌کم
    ۰٫۱۲ ثانیه پشت‌سرهم با میانگین زیر ‎-40dB. حرف بی‌صدا مثل «س» و «ش» همین شکل را دارد ولی بلندتر (‎-36 تا ‎-40) و کوتاه‌تر
    است، پس نمی‌افتد. اندازه‌گیری روی ویدیوی کاربر (۲۰۲۶-۱۰-۰۹): نفس عمیق ‎-44 تا ‎-49dB، flatness ۰٫۶۵ تا ۰٫۷۸، centroid
    ۳۰۰۰ تا ۳۹۰۰؛ گفتار ‎-20 تا ‎-30dB، flatness ۰٫۰۶ تا ۰٫۳."""
    d = pdir(vid)
    c = jload(d / "breath.json", {})
    if c.get("v") == BREATH_V:
        return c.get("runs") or []
    env = env if env is not None else jload(d / "env.json", [])
    if not env or not (d / "voice.wav").exists():
        return []
    af = ("aresample=16000,asetnsamples=n=160:p=0,astats=metadata=1:reset=1:measure_overall=none:measure_perchannel=RMS_level,"
          "aspectralstats=win_size=256:overlap=0:measure=flatness+centroid,ametadata=print:file=-")
    raw, _ = run([FFMPEG, "-v", "error", "-i", d / "voice.wav", "-ac", "1", "-af", af, "-f", "null", "-"], vid)
    frames, cur = [], None                       # (زمان، rms، flatness، centroid)؛ فریم‌های aspectralstats ۱۶ میلی‌ثانیه‌اند
    for line in raw.decode("utf-8", "replace").splitlines():
        if line.startswith("frame:"):
            if cur:
                frames.append(cur)
            m = re.search(r"pts_time:([0-9.]+)", line)
            cur = [float(m.group(1)) if m else 0.0, -120.0, 0.0, 0.0]
        elif cur and "=" in line:
            k, v = line.rsplit("=", 1)
            try:
                x = float(v)
            except ValueError:
                x = -120.0
            if k.endswith("RMS_level"):
                cur[1] = x
            elif k.endswith("flatness"):
                cur[2] = x
            elif k.endswith("centroid"):
                cur[3] = x
    if cur:
        frames.append(cur)
    thr, b, j = env_threshold(env), [], 0
    for k in range(len(env)):                    # روی شبکه‌ی ۱۰ میلی‌ثانیه‌ای env
        while j + 1 < len(frames) and frames[j + 1][0] <= k * FR:
            j += 1
        _, r, f, cen = frames[j] if frames else (0, -120.0, 0, 0)
        b.append(thr <= r < -38 and f >= 0.45 and cen >= 1800)
    runs, k, n = [], 0, len(b)
    while k < n:
        if not b[k]:
            k += 1
            continue
        j, hole = k, 0                           # تا ۳ فریم سکوت وسط نفس مجاز است
        while j + 1 < n and (b[j + 1] or (hole < 3 and env[j + 1] < thr)):
            hole = 0 if b[j + 1] else hole + 1
            j += 1
        loud = [env[x] for x in range(k, j + 1) if b[x]]
        # حرف بی‌صدای اول یا آخر کلمه («ف»ِ «فقط»، «ح»ِ «حتی»، «ه»ِ «هم») هم آرام و نویزی است، ولی تقریباً بی‌فاصله به واکه
        # می‌چسبد؛ نفس واقعی پیش و پسش کمی سکوت دارد. پس اگر تا ۶۰ میلی‌ثانیه پیش یا ۱۰۰ میلی‌ثانیه پسش صدای بلند (≥ ‎-38dB)
        # هست، نفس نیست. («ف»ِ «فقط» با ۶۰ میلی‌ثانیه هنوز نفس حساب می‌شد: بین آن و واکه حدود ۸۰ میلی‌ثانیه افت بود.)
        near = env[max(0, k - 6):k] + env[j + 1:j + 11]
        if (j - k + 1) * FR >= 0.15 and sum(loud) / len(loud) < -40 and max(near, default=-120) < -38:
            runs.append([round(k * FR, 2), round((j + 1) * FR, 2)])
        k = j + 1
    jsave(d / "breath.json", {"v": BREATH_V, "runs": runs})
    return runs


def ensure_facetrack(vid=None):
    """ابزار Swift یک بار ساخته می‌شود (حدود ۳۰ ثانیه)؛ هر بار که سورسش عوض شود دوباره."""
    if FACETRACK.exists() and FACETRACK.stat().st_mtime >= FACETRACK_SRC.stat().st_mtime:
        return
    FACETRACK.parent.mkdir(parents=True, exist_ok=True)
    run(["swiftc", "-O", "-parse-as-library", "-swift-version", "5", FACETRACK_SRC, "-o", FACETRACK], vid, timeout=900)


def track_faces(vid, step=lambda s: None):
    """جای صورت ۴ بار در ثانیه با Vision خود macOS → faces.json؛ تا زیرنویس روی صورت نیفتد.
    صورت‌های ریز (عکس پروفایل روی صفحه‌ی سایت و…) و کم‌اطمینان کنار گذاشته می‌شوند."""
    d = pdir(vid)
    if jload(d / "project.json", {}).get("kind") != "reel":
        jsave(d / "faces.json", {"fps": 0, "s": []})
        return
    step("پیدا کردن جای صورت در طول ویدیو…")
    ensure_facetrack(vid)
    out, _ = run([FACETRACK, d / "master.mp4", "4"], vid, timeout=3600)
    samples = []
    for line in out.decode("utf-8", "replace").splitlines():
        try:
            x = json.loads(line)
        except Exception:
            continue
        fs = [f for f in x.get("f") or [] if len(f) >= 5 and f[4] >= 0.5 and f[3] >= 0.06]
        if fs:
            big = max(f[3] for f in fs)
            fs = [f for f in fs if f[3] >= 0.4 * big]
        samples.append({"t": round(float(x.get("t", 0)), 3), "f": [[round(v, 3) for v in f[:4]] for f in fs]})
    jsave(d / "faces.json", {"fps": 4, "s": samples})


def cap_font(kind, style, size="m"):
    fs, wt = CAP[kind].get(style, CAP[kind]["clean"])
    return int(round(fs * SIZE.get(size, 1.0))), wt


def cap_box_h(kind, style, size="m"):
    """ارتفاع کادر زیرنویس یک‌خطی (کسری از ارتفاع قاب)."""
    fs, _ = cap_font(kind, style, size)
    return (fs * 1.5 + (2 * PILL_PAD[kind][0] if style == "pill" else 0)) / CANVAS[kind][1]


def zones_for(kind, bh):
    """جای ثابت بالای کادر زیرنویس: پایین (لبه‌ی پایینش روی مرز امن)، بالا (زیر نوار اینستاگرام)، وسط."""
    lo, hi = SAFE[kind]
    if kind == "reel":
        return {"bot": hi - bh, "top": lo, "mid": 0.5 - bh / 2}
    return {"bot": 0.86, "top": 0.03, "mid": 0.5 - bh / 2}     # ضبط صفحه: زیر قاب ویدیو


_MLOCK = threading.Lock()


def text_em(texts, weight):
    """پهنای هر متن بر حسب em با فونت زیرنویس (modules/video/measure.mjs، fontkit)؛ کش روی دیسک."""
    cf = DIR / "measure-cache.json"
    with _MLOCK:
        cache = jload(cf, {})
        miss = sorted({t for t in texts if f"{weight}|{t}" not in cache})
        if miss:
            try:
                out, _ = run([shutil.which("node") or "/opt/homebrew/bin/node", MEASURE], cwd=MOD, timeout=120,
                             input=json.dumps({"weight": weight, "texts": miss}, ensure_ascii=False).encode("utf-8"))
                for t, w in json.loads(out).items():
                    cache[f"{weight}|{t}"] = w
                jsave(cf, cache)
            except Exception as e:       # بدون اندازه‌گیری: تخمین محافظه‌کارانه‌ی پایین (تکه‌ها کوتاه‌تر می‌شوند)
                print(f"[video] measure.mjs failed: {str(e)[:300]}", flush=True)
        return {t: cache.get(f"{weight}|{t}", 0.62 * len(t)) for t in texts}


def _face_band(boxes):
    """بازه‌ی عمودی صورت(ها) با حاشیه‌ی مو، چانه و زوم ملایم روی برش‌ها."""
    return [(y - 0.18 * h - 0.01, y + h + 0.18 * h + 0.01) for x, y, w, h in boxes]


def _overlap(a0, bh, band):
    return max((max(0.0, min(a0 + bh, b1) - max(a0, b0)) / bh for b0, b1 in band), default=0.0)


def auto_pos(boxes, kind, bh, prev):
    """(نام، y) برای یک تکه. اول جای قبلی اگر هنوز امن است (زیرنویس بی‌دلیل بالا-پایین نپرد)، بعد پایینِ همیشگی،
    بعد درست بالای صورت یا زیر آن (در صفحه‌ی دونیمه یعنی روی مرز دو نیمه)، و اگر هیچ‌کدام جا نداشت کم‌تداخل‌ترین جای ثابت."""
    zones, (lo, hi) = zones_for(kind, bh), SAFE[kind]
    if not boxes:
        return prev or ("bot", zones["bot"])
    band = _face_band(boxes)
    if prev and _overlap(prev[1], bh, band) == 0:
        return prev
    if _overlap(zones["bot"], bh, band) == 0:
        return ("bot", zones["bot"])
    top, bot = min(b0 for b0, _ in band), max(b1 for _, b1 in band)
    cands = []
    if top - 0.012 - bh >= lo:
        cands.append(("above", top - 0.012 - bh))
    if bot + 0.012 + bh <= hi:
        cands.append(("below", bot + 0.012))
    cands = [(n, math.floor(y * 100) / 100 if n == "above" else math.ceil(y * 100) / 100) for n, y in cands]
    cands = [c for c in cands if _overlap(c[1], bh, band) == 0]
    if cands:
        return min(cands, key=lambda c: abs(c[1] - zones["bot"]))
    return min((("bot", zones["bot"]), ("top", zones["top"]), ("mid", zones["mid"])), key=lambda z: round(_overlap(z[1], bh, band), 2))


def place_captions(caps, words, faces, kind, style, overrides, size="m"):
    """جای هر تکه: دستی (capPos روی یکی از کلمه‌هایش) یا خودکار از روی صورت در همان بازه."""
    H = CANVAS[kind][1]
    bh = cap_box_h(kind, style, size)
    zones = zones_for(kind, bh)
    samples = (faces or {}).get("s") or []
    ts = [s["t"] for s in samples]
    prev, prev_end = None, -9.0
    for c in caps:
        ids = [w["i"] for w in c["words"]]
        ov = next((overrides[str(i)] for i in ids if str(i) in overrides), None)
        if ov is not None:
            c["pos"], c["auto"] = ov, False
            y = ov if isinstance(ov, (int, float)) else zones.get(ov, zones["bot"])
            prev = None
        else:
            t0, t1 = words[ids[0]]["s"], words[ids[-1]]["e"]
            lo, hi = bisect.bisect_left(ts, t0 - 0.2), bisect.bisect_right(ts, t1 + 0.2)
            boxes = [f for s in samples[lo:hi] for f in s["f"]]
            name, y = auto_pos(boxes, kind, bh, prev if c["s"] - prev_end < 1.0 else None)
            c["pos"], c["auto"] = name, True
            prev = (name, y)
        prev_end = c["e"]
        c["y"] = int(round(min(0.9, max(0.02, float(y))) * H))
    return caps


def env_threshold(env):
    vals = sorted(x for x in env if x > -95)
    if len(vals) < 20:
        return -45.0
    floor, speech = vals[int(len(vals) * 0.10)], vals[int(len(vals) * 0.90)]
    return round(floor + max(6.0, 0.3 * (speech - floor)), 1)


# ---------------- متن فارسی ----------------
_DIAC = re.compile(r"[ً-ْٰ]")            # اعراب (فقط برای تطبیق؛ تنوین «تقریباً» در متن می‌ماند)
_FA2EN = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def norm_fa(s):
    s = (s or "").replace("ي", "ی").replace("ك", "ک").replace("ى", "ی").replace("ۀ", "هٔ").replace("ـ", "")
    return re.sub(r"[ \t]+", " ", s).strip()


def mkey(s):
    """کلید تطبیق دو متن: بدون اعراب، نیم‌فاصله، علامت و فاصله؛ رقم‌ها لاتین."""
    s = _DIAC.sub("", norm_fa(s)).replace("‌", "").translate(_FA2EN).lower()
    return "".join(ch for ch in s if ch.isalnum())


def has_latin(s):
    return re.search(r"[A-Za-z]", s or "") is not None


# ---------------- Gemini 3.5 Transcribe ----------------
GBASE = "https://generativelanguage.googleapis.com"


def gemini_key():
    return cfg.gemini_key()


def _greq(method, url, body=None, timeout=600):
    key = gemini_key()
    if not key:
        raise RuntimeError("کلید Gemini تنظیم نشده؛ از تب «تنظیمات» واردش کن (رایگان است).")
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, method=method,
                               headers={"x-goog-api-key": key, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            return json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Gemini HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:400]}")


def gemini_stt(audio_path, timestamps):
    """یک بار تبدیل؛ با زمان کلمه‌ها یا بدون آن. خروجی: (کلمه‌ها، متن)."""
    part = {"type": "audio", "data": base64.b64encode(Path(audio_path).read_bytes()).decode(), "mime_type": "audio/ogg"}
    cfg = {"language_codes": ["fa-IR"]}
    if timestamps:
        cfg["mode"] = {"type": "verbatim", "timestamp_granularities": ["word"]}
    out = _greq("POST", f"{GBASE}/v1beta/interactions",
                {"model": STT_MODEL, "input": [part], "generation_config": {"transcription_config": cfg}})
    for _ in range(400):
        if out.get("status") in (None, "completed", "failed", "cancelled"):
            break
        time.sleep(1.5)
        out = _greq("GET", f"{GBASE}/v1beta/{out['id']}")
    if out.get("status") not in (None, "completed"):
        raise RuntimeError(f"Gemini: وضعیت {out.get('status')}")
    words, texts = [], []
    for st in out.get("steps") or []:
        for c in st.get("content") or []:
            if c.get("type") == "text":
                texts.append(c.get("text") or "")
            for a in c.get("annotations") or []:
                if a.get("type") == "word_info":
                    words.append({"w": a.get("text", ""), "s": float(str(a.get("start_offset", "0")).rstrip("s") or 0),
                                  "e": float(str(a.get("end_offset", "0")).rstrip("s") or 0)})
    return words, (out.get("output_text") or " ".join(texts)).strip()


def stt_cut(d, a, n, out, vid=None):
    """تکه‌ی دقیق صدا برای Gemini، از a به طول n ثانیه: از voice.wav (PCM، دقیق تا نمونه) دوباره opus ساخته می‌شود.
    **تله:** برش stt.ogg با `-c copy` از اول صفحه‌ی Ogg شروع می‌شود، نه از a (۲۰۲۶-۱۰-۰۹: ۰٫۷ ثانیه زودتر، start_time=-0.7)،
    پس همه‌ی زمان‌های آن تکه ۰٫۷ ثانیه دیر می‌شد و «فقط باید»، درست بعد از یک برش، نصفه بریده شد."""
    run([FFMPEG, "-v", "error", "-y", "-ss", f"{a:.3f}", "-t", f"{n:.3f}", "-i", Path(d) / "voice.wav", "-ac", "1", "-ar", "16000",
         "-c:a", "libopus", "-b:a", "32k", "-application", "voip", out], vid)


def ts_tail(ws, d, a, b, env, td, vid=None):
    """اجرای زمان‌دار Gemini گاهی پیش از پایان صدا تمام می‌شود (۲۰۲۶-۱۰-۰۹: ویدیوی ۱۵ دقیقه‌ای فقط تا ۷۰۹ ثانیه زمان داشت،
    وسط یک کلمه بریده بود؛ align_text ۲۷۶ کلمه‌ی آخر را در یک لحظه فشرد و «سکوت آخر» compute_keeps کل ۳ دقیقه‌ی آخر، یعنی
    برداشت‌های کامل آخر، را برید). اگر بعد از آخرین کلمه‌ی زمان‌دار هنوز دست‌کم ۳ ثانیه حرف هست، بقیه‌ی همین تکه از کمی قبل
    از آن کلمه جدا رونویسی و به آخر اضافه می‌شود (حداکثر ۴ بار). ws زمان نسبی به شروع تکه (a) دارد؛ d پوشه‌ی پروژه است."""
    thr = env_threshold(env)
    for n in range(4):
        covered = max((w["e"] for w in ws), default=0.0)
        k0, k1 = int((a + covered + 1.0) / FR), min(len(env), int(b / FR))
        if sum(1 for x in env[k0:k1] if x >= thr) * FR < 3.0:
            break
        start = max(0.0, covered - 1.5)
        sub = Path(td) / f"tail{int(a)}-{n}.ogg"
        stt_cut(d, a + start, b - a - start, sub, vid)
        more = [dict(w, s=round(w["s"] + start, 3), e=round(w["e"] + start, 3)) for w in _retry(gemini_stt, sub, True)[0]]
        more = [w for w in more if w["s"] >= covered - 0.05]
        if not more or max(w["e"] for w in more) <= covered + 0.5:
            break
        ws = ws + more
    return ws


def _retry(fn, *a, waits=(5, 20, 45)):
    """شلوغی Gemini (۵۰۳/۴۲۹) معمولاً بیش از چند ثانیه طول می‌کشد؛ ۲۰۲۶-۱۰-۰۷ با سه تلاش در ۱۵ ثانیه
    کار به whisper افتاد و رونویسی یک ویدیوی ۱۹ دقیقه‌ای خراب شد. حالا ۴ تلاش در حدود ۷۰ ثانیه."""
    err = None
    for k in range(len(waits) + 1):
        try:
            return fn(*a)
        except Exception as e:
            err = e
            if k < len(waits):
                time.sleep(waits[k])
    raise err or RuntimeError("retry")


def whisper_stt(audio_path, vid=None):
    """پشتیبان آفلاین (دقتش روی فارسی خیلی کمتر است)."""
    if not WHISPER_MODEL.exists():
        raise RuntimeError("مدل whisper پیدا نشد.")
    with tempfile.TemporaryDirectory() as td:
        wav = Path(td) / "a.wav"
        run([FFMPEG, "-v", "error", "-y", "-i", audio_path, "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", wav], vid)
        # -mc 0: هر پنجره‌ی ۳۰ ثانیه‌ای بدون متن پنجره‌ی قبل. وگرنه یک توهم در سکوت اول ویدیو («PYM JBZ»)
        # تا آخر فایل تکرار می‌شود (۲۰۲۶-۱۰-۰۷: کل ۱۹ دقیقه شد ۷۸ کلمه‌ی بی‌معنی؛ با -mc 0 همان فایل ۱۰۸۳ کلمه‌ی درست داد).
        run(["whisper-cli", "-m", WHISPER_MODEL, "-l", "fa", "-f", wav, "-ojf", "-ml", "1", "-sow", "-np", "-mc", "0",
             "-of", Path(td) / "o"], vid)
        segs = jload(Path(td) / "o.json", {}).get("transcription", [])
    words = [{"w": s["text"].strip(), "s": s["offsets"]["from"] / 1000, "e": s["offsets"]["to"] / 1000}
             for s in segs if s.get("text", "").strip()]
    return words, " ".join(w["w"] for w in words)


def plan_chunks(env, dur, max_len=STT_CHUNK):
    """تکه‌های ≤ ۲۰ دقیقه، بریده‌شده در ساکت‌ترین لحظه‌ی نزدیک مرز."""
    if dur <= max_len + 30:
        return [(0.0, dur)]
    cuts, t = [0.0], 0.0
    while dur - t > max_len + 30:
        lo, hi = int((t + max_len - 30) / FR), int((t + max_len) / FR)
        win = env[lo:hi] or [0]
        best = lo + min(range(len(win)), key=lambda i: win[i])
        t = best * FR
        cuts.append(t)
    cuts.append(dur)
    return list(zip(cuts, cuts[1:]))


def align_text(ts_words, text):
    """متن بهتر (اجرای بدون زمان) روی زمان‌های اجرای زمان‌دار. هر کلمه: w, s, e و اگر دو اجرا فرق داشتند alt."""
    words = [w for w in norm_fa(text).split() if w]
    if not words:
        return [dict(w, alt=None) for w in ts_words]
    if not ts_words:
        return []
    A, B = [mkey(w) for w in words], [mkey(t["w"]) for t in ts_words]
    out = []

    def at(j_chars, j1, j2):   # زمان یک موقعیت حرفی در تکه‌ی B[j1:j2]
        acc = 0
        for j in range(j1, j2):
            L = max(1, len(B[j]))
            if j_chars <= acc + L or j == j2 - 1:
                f = min(1.0, max(0.0, (j_chars - acc) / L))
                return ts_words[j]["s"] + f * (ts_words[j]["e"] - ts_words[j]["s"])
            acc += L
        return ts_words[j2 - 1]["e"]

    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, A, B, autojunk=False).get_opcodes():
        if op == "equal":
            for k in range(i2 - i1):
                t = ts_words[j1 + k]
                out.append({"w": words[i1 + k], "s": t["s"], "e": t["e"], "alt": None})
        elif op == "replace":
            ca = [max(1, len(a)) for a in A[i1:i2]]
            CA, CB = sum(ca), sum(max(1, len(b)) for b in B[j1:j2])
            alt = " ".join(t["w"] for t in ts_words[j1:j2])
            acc = 0
            for k, L in enumerate(ca):
                s, e = at(acc * CB / CA, j1, j2), at((acc + L) * CB / CA, j1, j2)
                acc += L
                same = mkey(words[i1 + k]) in mkey(alt) and len(ca) != (j2 - j1)
                out.append({"w": words[i1 + k], "s": round(s, 3), "e": round(max(e, s + 0.05), 3),
                            "alt": None if same else alt})
        elif op == "insert":       # فقط اجرای زمان‌دار شنیده؛ نگه می‌داریم تا حرفی گم نشود
            for t in ts_words[j1:j2]:
                out.append({"w": norm_fa(t["w"]), "s": t["s"], "e": t["e"], "alt": "only-ts"})
        else:                      # delete: فقط متن بدون زمان دارد؛ زمانش را از همسایه می‌گیرد
            t0 = out[-1]["e"] if out else (ts_words[j1]["s"] if j1 < len(ts_words) else 0.0)
            for k in range(i2 - i1):
                out.append({"w": words[i1 + k], "s": t0, "e": t0, "alt": "no-time"})
    for i, w in enumerate(out):
        w["i"] = i
    return out


def retime_squeezed(words, env):
    """کلمه‌هایی که align_text در یک لحظه‌ی خیلی کوتاه فشرده کرده، روی صدای واقعی‌شان پخش می‌شوند.

    اجرای زمان‌دار Gemini گاهی واژه‌های انگلیسی را جا می‌اندازد («AI Agent»، «ChatGPT»، «LinkedIn»)؛
    align_text کلمه‌های اجرای بی‌زمان را روی همان یکی دو کلمه‌ی باقی‌مانده فشرده می‌کند و کنارشان
    یک «فاصله‌ی بی‌کلمه» می‌ماند که در واقع خودِ حرف است. compute_keeps آن را مکث می‌بیند و می‌بُرد
    (۲۰۲۶-۱۰-۰۷: «ای‌آی ایجنت و ایجنتیک ای‌آی»، ۹ کلمه در ۰٫۷ ثانیه، صدای واقعی‌شان ۳ ثانیه؛
    کاربر دو بار با «بازتولید» خواست برگردد و نشد، چون برش Claude رویش نبود).
    فقط دنباله‌ای که خیلی تندتر از سرعت عادی همین گوینده است و صدای پیوسته‌ی حرف کنارش ادامه دارد
    کشیده می‌شود؛ صدای بلندِ بی‌حرف (موسیقی) کنار کلمه‌های عادی دست نمی‌خورد. تعداد کلمه‌های جابه‌جاشده را برمی‌گرداند."""
    if not env or len(words) < 20:
        return 0
    thr, L = env_threshold(env), len(env)
    ln = lambda w: max(1, len(mkey(w["w"])))
    rates = sorted((w["e"] - w["s"]) / ln(w) for w in words if w["e"] > w["s"])
    if len(rates) < 20:
        return 0
    norm = rates[len(rates) // 2]                  # ثانیه برای هر حرف، سرعت عادی همین گوینده
    fast, slow = norm * 0.5, norm * 1.5
    pre = [0]                                      # «حرف»: دست‌کم نیمی از ۰٫۲ ثانیه‌ی دورش بلند باشد (نه چند تق تک)
    for x in env:
        pre.append(pre[-1] + (x >= thr))
    dense = lambda k: pre[min(L, k + 10)] - pre[max(0, k - 10)] >= 10

    def edge(t, limit, step):                      # از t در جهت step تا سکوت ≥ ۰٫۱۵ ثانیه یا limit
        k, end = int(round(t / FR)), int(round(limit / FR))
        last, q = k, 0
        while 0 <= k < L and (k < end if step > 0 else k > end):
            if dense(k):
                last, q = k + (step > 0), 0
            else:
                q += 1
                if q >= 15:
                    break
            k += step
        return last * FR

    moved, i, n = 0, 0, len(words)
    while i < n:
        # بلندترین دنباله‌ی پیوسته از i که کل آن خیلی تند است
        j, k, ch = i, i, ln(words[i])
        while k + 1 < n and -0.05 <= words[k + 1]["s"] - words[k]["e"] < 0.15 and words[k + 1]["e"] >= words[k + 1]["s"] and \
                (words[k + 1]["e"] - words[j]["s"]) / (ch + ln(words[k + 1])) <= fast:
            k += 1
            ch += ln(words[k])
        t0, t1 = words[j]["s"], words[k]["e"]
        if ch < 6 or not 0 <= t1 - t0 <= ch * fast:
            i += 1
            continue
        lo = words[j - 1]["e"] + 0.05 if j else 0.0
        hi = words[k + 1]["s"] - 0.05 if k + 1 < n else L * FR
        s, e = edge(t0, lo, -1), edge(t1, hi, 1)
        room = ch * slow - (t1 - t0)               # بیشتر از سرعت آرامِ گوینده کش نمی‌آید
        left, right = t0 - s, e - t1
        if room > 0 and left + right >= 0.3:
            f = min(1.0, room / (left + right))       # اگر جا بیشتر از لازم است، به نسبت از دو طرف
            s, e = t0 - left * f, t1 + right * f
            tot, acc = ch, 0
            for w in words[j:k + 1]:
                w["s"] = round(s + (e - s) * acc / tot, 3)
                acc += ln(w)
                w["e"] = round(s + (e - s) * acc / tot, 3)
            moved += k + 1 - j
        i = k + 1

    # ۲) واژه‌ی جاافتاده‌ی کوتاه‌تر (۲۰۲۶-۱۰-۰۸: «چت‌بات دولوپر» روی «چت بات» اجرای زمان‌دار فشرده ماند و «developer» واقعی،
    # ۰٫۷ ثانیه حرفِ درست بعدش، بی‌کلمه ماند و مثل مکث بریده شد؛ قدم ۱ نمی‌دیدش چون دو کلمه آن‌قدر تند نبودند).
    # نشانه‌اش دقیق است: چند کلمه‌ی پشت‌سرهم با یک alt مشترک که حرف‌هایشان خیلی بیشتر از alt است (اجرای زمان‌دار تکه‌ای را
    # نشنیده). فقط آن دسته تا لبه‌ی حرفِ پیوسته‌ی بی‌کلمه‌ی کنارش (بی‌سکوتِ ≥ ۰٫۱۵ ثانیه، حداکثر ۱٫۲ ثانیه) کش می‌آید.
    # «تند بودن» تنها نشانه نیست: «یه»، «که»، «تا» ذاتاً کوتاه‌اند و کنارشان معمولاً «اِممم» است، نه واژه‌ی جاافتاده.
    def spread(a, b, s, e):
        tot, acc = sum(ln(w) for w in words[a:b + 1]), 0
        for w in words[a:b + 1]:
            w["s"] = round(s + (e - s) * acc / tot, 3)
            acc += ln(w)
            w["e"] = round(s + (e - s) * acc / tot, 3)

    i = 0
    while i < n:
        a = words[i].get("alt")
        j = i
        while j + 1 < n and words[j + 1].get("alt") == a:
            j += 1
        i, k = j + 1, i
        if not isinstance(a, str) or a in ("only-ts", "no-time"):
            continue
        have, said = sum(ln(w) for w in words[k:j + 1]), max(1, len(mkey(a)))
        if have - said < 4 or have < 1.4 * said:
            continue
        if j + 1 < n and words[j + 1]["s"] - words[j]["e"] >= 0.3:      # حرفِ بی‌کلمه بعد از دسته
            nx = words[j + 1]["s"] - 0.05
            cap = min(nx, words[j]["e"] + 1.2)
            e = edge(words[j]["e"], cap, 1)
            if e - words[j]["e"] >= 0.2 and not (cap < nx and e >= cap - 0.02):
                spread(k, j, words[k]["s"], e)
                moved += j + 1 - k
                continue
        if k > 0 and words[k]["s"] - words[k - 1]["e"] >= 0.3:          # حرفِ بی‌کلمه پیش از دسته
            pv = words[k - 1]["e"] + 0.05
            cap = max(pv, words[k]["s"] - 1.2)
            s = edge(words[k]["s"], cap, -1)
            if words[k]["s"] - s >= 0.2 and not (cap > pv and s <= cap + 0.02):
                spread(k, j, s, words[j]["e"])
                moved += j + 1 - k
    return moved


def transcribe(vid, step=lambda s: None):
    d = pdir(vid)
    proj = jload(d / "project.json", {})
    dur = (proj.get("info") or {}).get("masterDur") or (proj.get("info") or {}).get("dur") or 0
    env = jload(d / "env.json", [])
    if not (proj.get("info") or {}).get("audio") or not env or max(env) < -50:
        res = {"engine": "none", "lang": "fa", "words": [], "text": "", "note": "صدای حرف زدن پیدا نشد."}
        jsave(d / "transcript.json", res)
        return res
    chunks = plan_chunks(env, dur)
    all_ts, texts, engine, gemini_errs = [], [], STT_MODEL, []
    with tempfile.TemporaryDirectory() as td:
        for n, (a, b) in enumerate(chunks):
            step(f"تبدیل صدا به متن{'' if len(chunks) == 1 else f' (تکه‌ی {n + 1} از {len(chunks)})'}…")
            src = d / "stt.ogg"
            if len(chunks) > 1:
                src = Path(td) / f"c{n}.ogg"
                stt_cut(d, a, b - a, src, vid)          # نه `-c copy`: زمان‌های تکه دیر می‌شد (stt_cut)
            res = {}

            def go(kind, path=src):
                try:
                    res[kind] = _retry(gemini_stt, path, kind == "ts")
                except Exception as e:
                    res[kind + "_err"] = str(e)

            th = [threading.Thread(target=go, args=(k,)) for k in ("ts", "plain")]
            for t in th:
                t.start()
            for t in th:
                t.join()
            if "ts" in res:                       # اجرای زمان‌دار نیمه‌کاره ماند؟ بقیه‌اش جدا
                try:
                    res["ts"] = (ts_tail(res["ts"][0], d, a, b, env, td, vid), res["ts"][1])
                except Exception as e:
                    gemini_errs.append(f"tail: {e}"[:400])
            if "ts" not in res:
                gerr = res.get("ts_err", "")
                print(f"[video {vid}] Gemini STT failed, falling back to whisper: {gerr[:400]}", file=sys.stderr, flush=True)
                step(f"Gemini جواب نداد ({gerr[:120]})؛ تبدیل آفلاین با whisper…")
                engine = "whisper.cpp"
                gemini_errs.append(gerr[:400])
                ws, txt = whisper_stt(src, vid)
                res["ts"], res["plain"] = (ws, txt), (ws, txt)
            ws = res["ts"][0]
            for w in ws:
                w["s"], w["e"] = round(w["s"] + a, 3), round(w["e"] + a, 3)
            all_ts += ws
            texts.append((res.get("plain") or res["ts"])[1])
    text = " ".join(t for t in texts if t)
    words = align_text(all_ts, text)
    for w in words:
        w["s"], w["e"] = max(0.0, min(w["s"], dur)), max(0.0, min(w["e"], dur))
    retime_squeezed(words, env)
    # گفتار واقعی حدود ۳۰٪ کلمه‌ی یکتا دارد؛ زیر ۱۰٪ یعنی موتور در یک حلقه گیر کرده. خطا = مرحله «انجام‌نشده»
    # می‌ماند و «ساخت کامل» دوباره رونویسی می‌کند، به جای اینکه Claude روی متن بی‌معنی تصمیم بگیرد.
    if len(words) >= 40 and len({mkey(w["w"]) for w in words}) / len(words) < 0.1:
        why = f" Gemini: {gemini_errs[0][:200]}" if gemini_errs else ""
        raise RuntimeError(f"رونویسی ({engine}) بی‌معنی درآمد؛ چند دقیقه بعد «ساخت کامل» را دوباره بزن.{why}")
    res = {"engine": engine, "lang": "fa", "words": words, "text": text,
           "tsText": " ".join(w["w"] for w in all_ts), "at": now()}
    if gemini_errs:
        res["geminiError"] = gemini_errs[0]
    jsave(d / "transcript.json", res)
    return res


# ---------------- برش‌ها → بخش‌های نگه‌داشته ----------------
def cut_set(edit, n, auto=True):
    """اندیس کلمه‌هایی که حذف می‌شوند: برش‌های Claude (روشن) + تغییرهای دستی (دستی برنده است).
    auto=False («برش خودکار» خاموش، opts.autoCut): فقط حذف‌های دستی کاربر."""
    s = set()
    for c in edit.get("cuts") or []:
        if auto and c.get("on", True):
            s.update(range(max(0, int(c["w0"])), min(n, int(c["w1"]) + 1)))
    for k, v in (edit.get("manual") or {}).items():
        i = int(k)
        if 0 <= i < n:
            (s.add if v else s.discard)(i)
    return s


def compute_keeps(words, cut, env, dur, rhythm="normal", keep_pauses=(), trim=True, breaths=None):
    """بخش‌های نگه‌داشته‌ی منبع، هم‌تراز با فریم‌ها، تا صدا و تصویر بعد از برش از هم جدا نشوند.
    trim=False («برش خودکار» خاموش): مکث و سکوت کوتاه نمی‌شود (قدم‌های ۲ تا ۴)؛ فقط کلمه‌های حذف‌شده می‌روند."""
    gap_max, pad = RHYTHM.get(rhythm, RHYTHM["normal"])
    n = max(1, int(math.ceil(dur / FR)))
    keep = bytearray(b"\x01") * n
    fi = lambda t: max(0, min(n, int(round(t / FR))))

    def kill(a, b):
        i, j = fi(a), fi(b)
        if j > i:
            keep[i:j] = b"\x00" * (j - i)

    kept = [w for w in words if w["i"] not in cut and w["e"] > w["s"]]
    if not words:
        return [(0.0, round(math.floor(dur * FPS) / FPS, 4))]
    # ۱) کلمه‌های بریده‌شده (پشت‌سرهم یک‌جا)
    i = 0
    while i < len(words):
        if words[i]["i"] in cut:
            j = i
            while j + 1 < len(words) and words[j + 1]["i"] in cut:
                j += 1
            kill(words[i]["s"], words[j]["e"])
            i = j + 1
        else:
            i += 1
    pauses = {int(x) for x in keep_pauses}
    # ۲) فاصله‌ی بلند بین دو کلمه‌ی نگه‌داشته. شروع کلمه‌ی بعدی تا شروع واقعی صدایش عقب می‌رود (حداکثر ۰٫۴ ثانیه، فقط
    # اگر صدا تا خود کلمه پیوسته است): زمان شروع کلمه‌های Gemini معمولاً ۰٫۲ ثانیه دیرتر از صداست و بعد از یک برش،
    # هجای اول بریده می‌شد (۲۰۲۶-۱۰-۰۹: «فقط باید» بعد از برش «...قط باید» شنیده می‌شد).
    thr = env_threshold(env) if env else 0.0

    def onset(t):
        k0 = last = int(round(t / FR))
        q = 0
        for k in range(k0 - 1, max(-1, k0 - 1 - int(0.4 / FR)), -1):
            if k >= len(env):
                continue
            if env[k] >= thr:
                last, q = k, 0
            else:
                q += 1
                if q >= 5:                          # ۵۰ میلی‌ثانیه سکوت = لبه‌ی حرف
                    return last * FR
        # تا ۰٫۴ ثانیه عقب‌تر هم بی‌وقفه صداست: شروع حرف نیست (موسیقی، یا دنباله‌ی کلمه‌ی بریده‌شده)، پس شروع قبلی
        # می‌ماند (۲۰۲۶-۱۰-۰۹: روی v1791401523881، ۰٫۴ ثانیه از ۳۳ ثانیه موسیقیِ پیش از «دیر» وارد ریلز می‌شد).
        return t

    for a, b in zip(kept, kept[1:]) if trim else ():
        if b["s"] - a["e"] > gap_max + 2 * pad and a["i"] not in pauses:
            kill(a["e"] + pad, max(a["e"] + pad, (onset(b["s"]) if env else b["s"]) - pad))
    # ۳) سکوت واقعی (حتی وسط بازه‌ی یک کلمه؛ زمان‌های Gemini گام ۰٫۱ ثانیه‌ای دارند و مکث را می‌بلعند)
    if env and trim:
        thr = env_threshold(env)
        protect = bytearray(n)
        for w in kept:
            if w["i"] in pauses:
                protect[fi(w["e"]):fi(w["e"] + 3)] = b"\x01" * max(0, fi(w["e"] + 3) - fi(w["e"]))
        k = 0
        L = min(n, len(env))
        quiet = bytearray(1 if x < thr else 0 for x in env[:L])
        gm, pd = gap_max, pad
        if breaths is not None:                     # «خیلی تند»: نفس هم سکوت است و مکث‌های خیلی کوتاه هم می‌روند
            gm, pd = TIGHT
            for a, b in breaths:
                i0, i1 = max(0, fi(a)), min(L, fi(b))
                if i1 > i0:
                    quiet[i0:i1] = b"\x01" * (i1 - i0)
        while k < L:
            if quiet[k]:
                j = k
                while j < L and quiet[j]:
                    j += 1
                if (j - k) * FR > gm + 2 * pd and not any(protect[k:j]):
                    kill(k * FR + pd, j * FR - pd)
                k = j
            else:
                k += 1
    # ۴) سکوت اول و آخر
    if kept and trim:
        kill(0, kept[0]["s"] - pad)
        kill(kept[-1]["e"] + pad, dur + 1)
    # ۵) تکه‌های خیلی کوتاه: نگه‌داشته‌ی بی‌کلمه زیر ۰٫۱۲ ثانیه حذف، حذف‌شده‌ی زیر ۰٫۰۶ ثانیه برمی‌گردد
    cores = bytearray(n)
    for w in kept:
        a, b = fi(w["s"] + 0.03), fi(w["e"] - 0.03)
        if b > a:
            cores[a:b] = b"\x01" * (b - a)
    runs, k = [], 0
    while k < n:
        j = k
        while j < n and keep[j] == keep[k]:
            j += 1
        runs.append([keep[k], k, j])
        k = j
    for r in runs:
        v, a, b = r
        if v and (b - a) * FR < 0.12 and not any(cores[a:b]):
            keep[a:b] = b"\x00" * (b - a)
        elif not v and (b - a) * FR < 0.06 and 0 < a and b < n:
            keep[a:b] = b"\x01" * (b - a)
    # ۶) بازه‌ها، هم‌تراز با فریم
    out, k = [], 0
    while k < n:
        if keep[k]:
            j = k
            while j < n and keep[j]:
                j += 1
            a, b = round(k * FR * FPS) / FPS, round(min(j * FR, dur) * FPS) / FPS
            if b - a >= 1 / FPS:
                if out and a <= out[-1][1]:
                    out[-1][1] = max(out[-1][1], b)
                else:
                    out.append([a, b])
            k = j
        else:
            k += 1
    return [(round(a, 4), round(b, 4)) for a, b in out] or [(0.0, round(math.floor(dur * FPS) / FPS, 4))]


class TimeMap:
    """زمان منبع ↔ زمان خروجی، بر اساس بخش‌های نگه‌داشته."""

    def __init__(self, keeps):
        self.k = list(keeps)
        self.starts = [a for a, _ in self.k]
        self.cum = [0.0]
        for a, b in self.k:
            self.cum.append(self.cum[-1] + (b - a))

    @property
    def dur(self):
        return self.cum[-1]

    def out(self, t):
        i = bisect.bisect_right(self.starts, t) - 1
        if i < 0:
            return 0.0
        a, b = self.k[i]
        return self.cum[i] + (t - a) if t <= b else self.cum[i + 1]

    def seg_starts(self):
        return self.cum[:-1]


# ---------------- زیرنویس ----------------
END_SENT = re.compile(r"[.!؟?…:]$")


def disp(words, fix, i):
    v = (fix or {}).get(str(i))
    return words[i]["w"] if v is None else v


def cap_fix(words, fix, ids, text):
    """ویرایش یک تکه‌ی زیرنویس به‌صورت یک خط (کاربر روی متن تکه کلیک می‌کند). متن تازه روی همان کلمه‌ها پخش می‌شود
    تا زمان هر کلمه (رنگ کلمه‌به‌کلمه) بماند: بخش‌های دست‌نخورده با difflib سر کلمه‌ی خودشان می‌مانند، بخش عوض‌شده
    به‌ترتیب و یکنواخت بین کلمه‌های همان جا پخش می‌شود، و کلمه‌ای که چیزی برایش نماند خالی می‌شود (در زیرنویس نمی‌آید).
    فهرست زیرنویس آخر تکه را بی‌نقطه نشان می‌دهد (clean_caption_text)، پس نقطه‌ی آخر اگر کاربر ننوشت برمی‌گردد.
    خروجی: {اندیس: متن تازه} فقط برای کلمه‌هایی که عوض شده‌اند."""
    new = norm_fa(text).split()
    old, own = [], []
    for i in ids:
        for t in disp(words, fix, i).split():
            old.append(t)
            own.append(i)
    if not old or not new:
        return {}
    tail = old[-1][len(clean_caption_text(old[-1])):]
    got, last = {i: [] for i in ids}, own[0]
    sm = difflib.SequenceMatcher(None, old[:-1] + [clean_caption_text(old[-1])], new, autojunk=False)
    for tag, a, b, c, d in sm.get_opcodes():
        if tag == "equal":
            for k in range(a, b):
                got[own[k]].append(old[k])
            last = own[b - 1]
        elif tag == "insert":                 # کلمه‌ی اضافه به کلمه‌ی قبلی‌اش می‌چسبد
            got[last].extend(new[c:d])
        else:                                 # replace / delete
            ws, toks = list(dict.fromkeys(own[a:b])), new[c:d]
            q, r = divmod(len(toks), len(ws))
            pos = 0
            for k, i in enumerate(ws):
                take = q + (1 if k < r else 0)
                got[i].extend(toks[pos:pos + take])
                pos += take
            last = own[b - 1]
    if tail:
        lw = next((i for i in reversed(ids) if got[i]), None)
        if lw is not None and not re.search(r"[.،,؛;!?؟…]$", got[lw][-1]):
            got[lw][-1] += tail
    out = {}
    for i in ids:
        t = " ".join(got[i])[:80]
        if t != disp(words, fix, i):
            out[str(i)] = t
    return out


def captions(words, cut, fix, tmap, kind, style="clean", breaks=(), size="m", emph=()):
    """تکه‌های زیرنویس روی زمان خروجی؛ هر تکه همیشه یک خط است. هر تکه: ids کلمه‌ها، s/e، متن، fs.
    پهنای هر تکه با اندازه‌گیری واقعی فونت حساب می‌شود (نه شمردن حرف)، تا از CAP_W بیرون نزند.
    breaks: اندیس کلمه‌هایی که Claude گفته بعدشان خط بشکند (مرز عبارت)؛ اولویت با آن‌هاست."""
    fs, wt = cap_font(kind, style, size)
    maxpx = CAP_W[kind] - (2 * PILL_PAD[kind][1] if style == "pill" else 0)
    maxw = ({"reel": 6, "screen": 10} if style != "punch" else {"reel": 3, "screen": 5})[kind]
    brk = {int(b) for b in breaks or ()}
    emph = set(emph or ())
    items = []
    for w in words:
        if w["i"] in cut:
            continue
        t = disp(words, fix, w["i"]).strip()
        if not t:
            continue
        items.append({"i": w["i"], "t": t, "s": tmap.out(w["s"]), "e": tmap.out(w["e"])})
    em = text_em([x["t"] for x in items] + [clean_caption_text(x["t"]) for x in items] + [" "], wt)
    gap_px = em.get(" ", 0.25) * fs + 2                       # فاصله + word-spacing:2px

    def width(ch):
        ws = [em.get(clean_caption_text(x["t"]) if k == len(ch) - 1 else x["t"], 0.62 * len(x["t"])) * fs
              * (1.12 if style == "punch" and x["i"] in emph else 1.0) for k, x in enumerate(ch)]
        return (sum(ws) + gap_px * (len(ch) - 1)) * WIDTH_SAFETY

    # ۱) عبارت‌ها: مکث، آخر جمله، مرزهایی که Claude داده، ویرگول
    phrases, cur = [], []
    for it in items:
        if cur:
            prev = cur[-1]
            if (it["s"] - prev["e"] > 0.3 or END_SENT.search(prev["t"]) or prev["i"] in brk or len(cur) >= maxw
                    or (prev["t"].endswith(("،", ",")) and len(cur) >= 2 and not brk)):
                phrases.append(cur)
                cur = []
        cur.append(it)
    if cur:
        phrases.append(cur)

    # ۲) عبارتی که در یک خط جا نمی‌شود، متعادل نصف می‌شود (نه حریصانه)، تا کلمه‌ی آخر تنها نماند («…هوش / مصنوعی»)
    def fit(ph):
        if len(ph) < 2 or width(ph) <= maxpx:
            return [ph]
        best = min(range(1, len(ph)), key=lambda k: max(width(ph[:k]), width(ph[k:]))
                   + (0.35 * maxpx if (k == 1 or k == len(ph) - 1) and len(ph) > 2 else 0))
        return fit(ph[:best]) + fit(ph[best:])

    chunks = [part for ph in phrases for part in fit(ph)]
    # تکه‌ی تک‌کلمه‌ای که بی‌مکث دنبال تکه‌ی قبلی آمده و در همان یک خط جا می‌شود، به آن می‌چسبد («شرکت / بکنیم.»)
    merged = []
    for ch in chunks:
        if (merged and len(ch) == 1 and ch[0]["s"] - merged[-1][-1]["e"] < 0.15 and len(merged[-1]) < maxw
                and width(merged[-1] + ch) <= maxpx and not END_SENT.search(merged[-1][-1]["t"])):
            merged[-1] = merged[-1] + ch
        else:
            merged.append(ch)
    chunks = merged
    out, half = [], 0.5 / FPS
    for k, ch in enumerate(chunks):
        s = max(0.0, ch[0]["s"] - 0.04)
        e = ch[-1]["e"] + 0.25
        if k + 1 < len(chunks):
            e = min(e, chunks[k + 1][0]["s"] - 0.04 - half)
        e = max(e, s + 0.4)
        if out and s <= out[-1]["e"]:
            s = out[-1]["e"] + half
        words_out = [{"i": x["i"], "t": x["t"], "s": round(x["s"], 3), "e": round(x["e"], 3)} for x in ch]
        w = width(ch)       # کلمه‌ای که تنهایی هم در یک خط جا نمی‌شود: فقط همان تکه کوچک‌تر می‌شود
        out.append({"id": f"c{k}", "s": round(s, 3), "e": round(e, 3), "words": words_out,
                    "text": " ".join(x["t"] for x in ch), "fs": fs if w <= maxpx else max(int(fs * maxpx / w), int(fs * 0.6)),
                    "wpx": int(w)})
    return out


def clean_caption_text(t):
    """نقطه و ویرگولِ آخر تکه در زیرنویس ریلز نمی‌آید؛ علامت سؤال و تعجب می‌ماند."""
    return re.sub(r"[.،,؛;]+$", "", t)


def srt(chunks):
    def ts(x):
        ms = int(round(x * 1000))
        return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"
    lines = []
    for k, c in enumerate(chunks, 1):
        lines += [str(k), f"{ts(c['s'])} --> {ts(c['e'])}", "‏" + clean_caption_text(c["text"]) + "‏", ""]
    return "\n".join(lines)


# ---------------- افکت صوتی ----------------
_SFXLIB = {"m": None, "v": {"cats": {}, "sounds": {}}}


def sfx_lib():
    """modules/video/sfx/manifest.json: دسته‌ها (اسم فارسی، صدای پیش‌فرض) و صداها (فایل، اسم، hit، gain، مجوز)."""
    f = SFX_DIR / "manifest.json"
    try:
        m = f.stat().st_mtime
    except OSError:
        return {"cats": {}, "sounds": {}}
    if _SFXLIB["m"] != m:
        _SFXLIB.update(m=m, v=jload(f, {"cats": {}, "sounds": {}}))
    return _SFXLIB["v"]


def sfx_cues(edit, words, cut, tmap, opts):
    """افکت‌های edit.json روی زمان خروجی. هر افکت به شروع یک کلمه گره خورده و ضربه‌ی صدا (hit) دقیقاً روی آن می‌افتد.
    کلمه‌ی بریده‌شده: افکتش پخش نمی‌شود (skip="cut") ولی می‌ماند تا اگر کلمه برگشت، خودش برگردد.
    هر افکت: at (لحظه‌ی کلمه)، t (شروع فایل)، db (هم‌بلندی کتابخانه + بلندی کل + تنظیم همان افکت)."""
    lib = sfx_lib()["sounds"]
    lvl = SFX_LEVEL.get(opts.get("sfxLevel", "mid"), 0.0)
    vis_on = {v.get("id") for v in edit.get("vis") or [] if v.get("on") is not False}
    out = []
    for x in edit.get("sfx") or []:
        c, w, snd = dict(x, skip=None), x.get("w"), lib.get(x.get("snd"))
        if not isinstance(w, int) or not 0 <= w < len(words) or not snd:
            c["skip"] = "bad"
        elif w in cut:
            c["skip"] = "cut"
        elif x.get("link") and x["link"] not in vis_on:      # افکت ورود تصویری که خاموش یا پاک شده
            c["skip"] = "vis"
        else:
            at = max(0.0, tmap.out(words[w]["s"]) + float(x.get("dt") or 0))
            c.update(at=round(at, 3), t=round(max(0.0, at - snd["hit"]), 3),
                     db=round(snd["gain"] + lvl + float(x.get("g") or 0), 1))
        out.append(c)
    return sorted(out, key=lambda c: (c.get("at", 1e9), c.get("w", 0)))


def sfx_active(dv):
    """افکت‌هایی که واقعاً در خروجی می‌آیند: افکت‌ها روشن، خود افکت روشن، کلمه‌اش نبریده، فایلش هست."""
    if not dv["opts"].get("sfx", True):
        return []
    lib = sfx_lib()["sounds"]
    return [c for c in dv["sfx"] if not c["skip"] and c.get("on") is not False and (SFX_DIR / lib[c["snd"]]["file"]).exists()]


def sfx_preview(dv, assets):
    """برای preview.html: فایل‌ها کنار ترکیب کپی می‌شوند (comp/assets/sfx-<کلید>.mp3)؛ g بهره‌ی خطی است."""
    lib, out = sfx_lib()["sounds"], []
    for c in sfx_active(dv):
        src, dst = SFX_DIR / lib[c["snd"]]["file"], assets / f"sfx-{c['snd']}.mp3"
        if not dst.exists() or dst.stat().st_mtime < src.stat().st_mtime:
            shutil.copy2(src, dst)
        out.append({"t": c["t"], "src": f"assets/{dst.name}", "g": round(10 ** (c["db"] / 20), 4)})
    return out


# ---------------- وضعیت مشتق‌شده ----------------
def load(vid):
    d = pdir(vid)
    return jload(d / "project.json", {}), jload(d / "edit.json", {}), jload(d / "transcript.json", {})


def default_opts(kind):
    st = jload(SETTINGS, {})
    return {"style": st.get("style", "clean"), "size": st.get("size", "m"), "rhythm": "normal", "punch": kind == "reel",
            "captions": True, "voiceClean": True, "sfx": True, "sfxLevel": st.get("sfxLevel", "mid"),
            "vertical": False, "vlayout": "frame", "vbg": "brand", "autoCut": True}


def derive(vid):
    """همه‌ی چیزهای محاسبه‌شده از روی edit + transcript: برش‌ها، نقشه‌ی زمان، زیرنویس."""
    proj, edit, tr = load(vid)
    words = tr.get("words") or []
    kind = proj.get("kind", "reel")
    opts = {**default_opts(kind), **(edit.get("opts") or {})}
    src_kind = kind                                  # نوع منبع؛ kind از این‌جا یعنی کادر ترکیب
    if kind == "screen" and opts.get("vertical"):    # فاز ۵: ضبط صفحه با خروجی عمودی ۹:۱۶ → کادر و زیرنویس ریلز
        kind = "reel"
    info = proj.get("info") or {}
    dur = info.get("masterDur") or info.get("dur") or 0
    cut = cut_set(edit, len(words), opts["autoCut"])
    env = jload(pdir(vid) / "env.json", [])
    keeps = compute_keeps(words, cut, env, dur, opts["rhythm"], edit.get("pauses") or [], opts["autoCut"],
                          breath_runs(vid, env) if opts["rhythm"] == "tight" else None)
    tmap = TimeMap(keeps)
    emph = {int(x) for x in edit.get("emph") or []}
    caps = (captions(words, cut, edit.get("fix") or {}, tmap, kind, opts["style"], edit.get("breaks") or (), opts["size"], emph)
            if opts["captions"] else [])
    place_captions(caps, words, jload(pdir(vid) / "faces.json", {}), kind, opts["style"], edit.get("capPos") or {}, opts["size"])
    dv = {"proj": proj, "edit": edit, "words": words, "kind": kind, "src_kind": src_kind, "opts": opts, "cut": cut, "keeps": keeps,
          "tmap": tmap, "caps": caps, "emph": emph, "dur": dur, "sfx": sfx_cues(edit, words, cut, tmap, opts), "vis": [], "zooms": []}
    if src_kind == "screen" and edit.get("zooms"):
        import video_screen as vsc               # فاز ۵؛ دیر import
        dv["zooms"] = vsc.resolve_zooms(dv)
    if edit.get("vis"):
        import video_visuals as vv        # فاز ۳؛ دیر import تا دور نشود
        dv["vis"] = vv.resolve(vid, dv)
        scenes = [(x["s"], x["e"]) for x in dv["vis"] if x.get("scene") and not x.get("skip") and x.get("on") is not False]
        if scenes and kind == "reel":         # صحنه‌ی تمام‌صفحه‌ی سایت گوینده را می‌پوشاند: زیرنویس خودکارِ آن بازه پایین، زیر قاب
            by = int(CANVAS[kind][1] * zones_for(kind, cap_box_h(kind, opts["style"], opts.get("size", "m")))["bot"])
            for c in caps:
                if c.get("auto", True) and any(c["s"] < e and c["e"] > s for s, e in scenes):
                    c["pos"], c["y"] = "bot", by
        if opts.get("capsOver"):
            # زیرنویس خود ویدیو از قبل سوخته است (۲۰۲۶-۱۰-۱۷، ads2): زیرنویس فقط وقتی که تصویر تمام‌صفحه (صحنه یا «تمام‌صفحه»)
            # آن را می‌پوشاند، و فقط در همان بازه؛ پایانش کمی زودتر، چون زمینه‌ی صحنه از پایین جمع می‌شود و زیرنویس سوخته پیدا می‌شود.
            # شروع: وقتی زمینه از پایین بالا آمده و زیرنویس سوخته را پوشانده (~۰٫۲۲ ثانیه؛ وگرنه دو متن روی هم می‌افتند).
            # صحنه‌های پیوسته (joinPrev) یک بازه‌اند تا زیرنویس سر مرزشان قطع نشود.
            wins = []
            for x in sorted(dv["vis"], key=lambda x: x.get("s") or 0):
                if x.get("skip") or x.get("on") is False or not (x.get("scene") or x.get("tpl") == "full"):
                    continue
                if wins and (x.get("joinPrev") or x["s"] - wins[-1][1] < 0.05):
                    wins[-1][1] = max(wins[-1][1], x["e"])
                else:
                    wins.append([x["s"] + (0.22 if x.get("scene") else 0.12), x["e"]])
            keep = []
            for c in caps:
                for s, e in wins:
                    if c["s"] < e - 0.3 and c["e"] > s:
                        c["s"], c["e"] = round(max(c["s"], s), 3), round(min(c["e"], e - 0.24), 3)
                        keep.append(c)
                        break
            caps[:] = keep
    elif opts.get("capsOver"):
        caps[:] = []
    return dv


# ---------------- Claude ----------------
def claude_bin():
    return cfg.claude_bin()


def ask(prompt, vid=None, timeout=1800, web=False, effort="high"):
    """claude -p بیرون از پوشه‌ی استودیو؛ پرامپت از stdin؛ هرگز Read در allowlist نیست."""
    cmd = [claude_bin(), "-p", "--output-format", "json", "--model", am.get("video"), "--no-session-persistence", "--safe-mode"]
    cmd += ["--tools", "WebSearch,WebFetch", "--allowedTools", "WebSearch", "WebFetch"] if web else ["--tools", ""]
    if effort:
        cmd += ["--effort", effort]
    out, _ = run(cmd, vid, timeout=timeout, input=prompt.encode("utf-8"), cwd=tempfile.gettempdir())
    try:
        return (json.loads(out).get("result") or "").strip()
    except Exception:
        return out.decode("utf-8", "replace")


def json_block(text, a, b):
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
    # Claude گاهی شیء را بعد از فهرست زودتر می‌بندد و ادامه می‌دهد: {"cuts": [...]}, "summary": "..."}
    # (۲۰۲۶-۱۰-۰۹، سه «بازتولید برش» پشت‌سرهم با همین خطا دور ریخته شد و کاربر فقط «Claude در حال تولید» دید).
    s = t[t.find("{"):] if "{" in t else ""
    try:
        v, k = json.JSONDecoder().raw_decode(s)
        rest = s[k:].strip()
        if isinstance(v, dict) and rest.startswith(","):
            more = json.loads("{" + rest[1:])
            if isinstance(more, dict):
                return {**v, **more}
    except Exception:
        pass
    return None


def brand_text(limit=14000):
    return read_text(BRAND_MD, limit)


CUT_RULES = """۱. برش‌ها (cuts): این‌ها را پیدا کن و حذف کن:
- برداشت دوباره (retake): گوینده جمله‌ای را شروع کرده، خراب کرده و دوباره گفته. همه‌ی نسخه‌های ناقص قبلی حذف می‌شوند و فقط آخرین نسخه‌ی کامل می‌ماند.
- شروع ناقص (false_start) و تپق (stutter)، یعنی تکرار پشت‌سرهم یک کلمه مثل «که که».
- پرکننده (filler): «اِم»، «اِ»، «اوم»، «آ» همیشه. «خب»، «یعنی»، «مثلاً»، «در واقع»، «به اصطلاح» فقط وقتی واقعاً پرکننده‌اند و حذفشان معنا را عوض نمی‌کند.
- حرف بیرون از ویدیو (offtopic)، مثل «صبر کن دوباره بگیرم» یا «اوکی شروع کنیم».
- هرگز محتوای معنادار را حذف نکن. اگر شک داشتی، نگه دار. سکوت را برش نزن؛ کد خودش مکث‌ها را کوتاه می‌کند.
- هر برش یک بازه‌ی پیوسته از اندیس‌هاست: w0 تا w1، هر دو شامل."""

FIX_RULES = """۲. اصلاح متن (fix): زیرنویس از روی همین کلمه‌ها ساخته می‌شود.
- کلمه‌ای را که اشتباه شنیده شده درست کن. متن دوم پایین (اجرای دوم همین صدا) معمولاً املای بهتری دارد؛ ولی هر جا دو اجرا فرق دارند، با منطق جمله و موضوع تصمیم بگیر.
- لحن محاوره‌ای گوینده را عوض نکن («میخوام» نباید «می‌خواهم» شود)؛ فقط املایش را درست کن: «می‌خوام» با نیم‌فاصله، «شرکت‌ها».
- اسم برند و محصول و اصطلاح انگلیسی که انگلیسی گفته شده به خط لاتین: LinkedIn، ChatGPT، AI Engineer.
- عددها با رقم فارسی (۲۰۲۶).
- علامت‌گذاری: «،» و «.» و «؟» را به آخر کلمه‌ی مناسب بچسبان. کمک می‌کند زیرنویس درست تکه شود.
- اگر دو اندیس باید یک کلمه شوند (مثل «شرکت» + «ها»)، کل متن را روی اندیس اول بگذار و برای دومی رشته‌ی خالی "".
- فقط کلمه‌هایی را بنویس که عوض می‌شوند.
- شکستن خط (breaks): زیرنویس همیشه یک خط است، پس هر تکه کوتاه است: ۲ تا ۴ کلمه و حداکثر حدود ۲۲ حرف (با فاصله‌ها). اندیس کلمه‌هایی را بده که بعدشان خط باید بشکند؛ روی مرز طبیعی عبارت، طوری که هر تکه خودش معنا بدهد. «دو» و «تا»، اسم و صفتش («هوش مصنوعی»)، مضاف و مضاف‌الیه، یا فعل مرکب («شرکت بکنیم») هرگز از هم جدا نشوند؛ اگر عبارتی بلندتر از ۲۲ حرف است، جای شکستنش را خودت انتخاب کن."""

EMPH_RULES = """۳. تأکید (emph): ۳ تا ۸ کلمه‌ی کلیدی کل ویدیو که باید در زیرنویس زرد شوند (عدد، اسم، نتیجه، کلمه‌ی قلاب). کم ولی دقیق."""


def words_listing(words, env=None):
    rows = []
    for a, b in zip(words, words[1:] + [None]):
        alt = f"  ‹اجرای دیگر: {a['alt']}›" if a.get("alt") and a["alt"] not in ("only-ts", "no-time") else ""
        gap = f"  ⟨مکث {b['s'] - a['e']:.1f}s⟩" if b and b["s"] - a["e"] >= 0.6 else ""
        rows.append(f"{a['i']}|{a['w']}|{a['s']:.2f}{alt}{gap}")
    return "\n".join(rows)


def decide_prompt(vid, sections=("cuts", "fix", "emph"), comment="", current=None):
    proj, edit, tr = load(vid)
    words = tr.get("words") or []
    kind = "ریلز عمودی (حرف زدن جلوی دوربین)" if proj.get("kind") == "reel" else "ضبط صفحه‌ی کامپیوتر (آموزش یا دمو)"
    parts = [f"تو تدوینگر ویدیوهای کوتاه فارسی این برند هستی. ویدیو: {kind}، {len(words)} کلمه.",
             "هسته‌ی برند (برای اسم‌ها، اصطلاح‌ها و لحن):\n<<<BRAND\n" + brand_text() + "\nBRAND>>>",
             "کلمه‌ها با اندیس و زمان شروع (ثانیه). قالب هر خط: اندیس|کلمه|شروع:\n<<<WORDS\n" + words_listing(words) + "\nWORDS>>>",
             "متن دوم همین صدا (املای بهتر، بدون زمان):\n<<<TEXT2\n" + (tr.get("text") or "") + "\nTEXT2>>>"]
    rules = {"cuts": CUT_RULES, "fix": FIX_RULES, "emph": EMPH_RULES}
    parts.append("کار تو:\n" + "\n\n".join(rules[s] for s in sections))
    if current is not None:
        parts.append("وضعیت فعلی این بخش‌ها (برای بازنویسی):\n" + json.dumps(current, ensure_ascii=False))
    past = [n for s in sections for n in (edit.get("notes") or {}).get(s, [])][-6:]
    if past:
        parts.append("نظرهای قبلی کاربر درباره‌ی همین بخش‌ها (رعایت کن):\n" + "\n".join("- " + p for p in past))
    if comment:
        parts.append("نظر تازه‌ی کاربر (مهم‌ترین دستور): " + comment)
    shape = {"cuts": '"cuts": [{"w0": 12, "w1": 15, "reason": "retake|false_start|stutter|filler|offtopic", "note": "یک جمله‌ی کوتاه فارسی"}]',
             "fix": '"fix": {"17": "هوش", "18": "مصنوعی،"}, "breaks": [3, 7, 11]',
             "emph": '"emph": [5, 22]'}
    body = ", ".join(shape[s] for s in sections)
    parts.append("خروجی فقط یک JSON بین این دو نشانه، بدون هیچ توضیح دیگر:\n<<<EDIT\n{" +
                 ('"title": "اسم کوتاه ویدیو (حداکثر ۶ کلمه)", ' if "cuts" in sections else "") + body +
                 ', "summary": "یک جمله: چه کردی"}\nEDIT>>>')
    return "\n\n".join(parts)


def clean_decision(data, n):
    """خروجی Claude را امن می‌کند: اندیس‌های معتبر، برش‌های بی‌تداخل."""
    cuts = []
    for c in data.get("cuts") or []:
        try:
            a, b = int(c.get("w0")), int(c.get("w1"))
        except Exception:
            continue
        a, b = max(0, min(a, b)), min(n - 1, max(a, b))
        if a <= b:
            cuts.append({"id": f"k{len(cuts)}", "w0": a, "w1": b, "on": True,
                         "reason": str(c.get("reason") or "filler")[:20], "note": str(c.get("note") or "")[:200]})
    fix = {}
    for k, v in (data.get("fix") or {}).items():
        try:
            i = int(k)
        except Exception:
            continue
        if 0 <= i < n and isinstance(v, str):
            fix[str(i)] = norm_fa(v) if v.strip() else ""
    ints = lambda key: sorted({int(x) for x in data.get(key) or [] if str(x).lstrip("-").isdigit() and 0 <= int(x) < n})
    return cuts, fix, ints("emph"), ints("breaks")


def decide(vid, sections=("cuts", "fix", "emph"), comment="", step=lambda s: None):
    proj, edit, tr = load(vid)
    n = len(tr.get("words") or [])
    if not n:
        with plock(vid):
            e = jload(pdir(vid) / "edit.json", {})
            e.setdefault("opts", default_opts(proj.get("kind", "reel")))
            e.update({"cuts": e.get("cuts", []), "fix": e.get("fix", {}), "emph": e.get("emph", []),
                      "summary": "حرفی در این ویدیو نیست؛ زیرنویس و برش متنی ندارد."})
            jsave(pdir(vid) / "edit.json", e)
        return
    current = {s: edit.get(s) for s in sections} if comment else None
    step("Claude دارد ویدیو را می‌خواند و برش‌ها را پیدا می‌کند…")
    res = ask(decide_prompt(vid, sections, comment, current), vid, timeout=1800, effort="high")
    data = json_block(res, "<<<EDIT", "EDIT>>>")
    if not data:
        (pdir(vid) / "decide.last-output.txt").write_text(res or "", encoding="utf-8")
        raise RuntimeError("جواب Claude قابل خواندن نبود.")
    cuts, fix, emph, breaks = clean_decision(data, n)
    with plock(vid):
        e = jload(pdir(vid) / "edit.json", {})
        e.setdefault("opts", default_opts(proj.get("kind", "reel")))
        prev = e.setdefault("prev", {})
        for s in sections:
            if s in e:
                prev[s] = e[s]
        if "cuts" in sections:      # برش‌های دستی (manual) دست نمی‌خورند و همچنان برنده‌اند
            e["cuts"] = cuts
        if "fix" in sections:       # اصلاح‌های دستی کاربر (fixUser) دست نمی‌خورند و همچنان برنده‌اند
            mine = e.get("fix") or {}
            e["fix"] = {**fix, **{k: mine[k] for k in e.get("fixUser") or [] if k in mine}}
            if "breaks" in data:
                e["breaks"] = breaks
        if "emph" in sections:
            e["emph"] = emph
        if comment:
            for s in sections:
                e.setdefault("notes", {}).setdefault(s, []).append(comment[:500])
        e["summary"] = str(data.get("summary") or "")[:900]   # ۴۰۰ وسط توضیح Claude می‌بُرید («برای برگشتن این …»)
        if data.get("title") and not proj.get("titleSet"):
            with plock(vid):
                p = jload(pdir(vid) / "project.json", {})
                p["title"] = str(data["title"])[:80]
                jsave(pdir(vid) / "project.json", p)
        e["decidedAt"] = now()
        jsave(pdir(vid) / "edit.json", e)


SFX_RULES = """دسته‌ها (cat) و جای هر کدام:
- whoosh: شروع مورد بعدیِ یک فهرست یا یک بخش تازه («اولیش»، «دومیش»، «حالا بریم سراغ…»)؛ روی اولین کلمه‌ی همان مورد.
- money: قیمت، هزینه، پرداخت، درآمد یا صرفه‌جویی؛ روی خود عدد یا کلمه‌ی پول.
- notify: پیام، دایرکت، ایمیل، نوتیفیکیشن.
- negative: کنسل کردن، حذف کردن، اشتباه، شکست، «نه».
- ding: نکته‌ی اصلی، نتیجه‌گیری، جواب درست، یک نقل‌قول مهم.
- impact: یک عدد یا نتیجه‌ی خیلی بزرگ و غافلگیرکننده (حداکثر ۲ بار در کل ویدیو).
- click: کلیک، انتخاب، فشار دادن دکمه یا میانبر کیبورد.
- typing: تایپ کردن یا نوشتن متن.
- sparkle: کاری که هوش مصنوعی مثل جادو انجام می‌دهد، یا یک نتیجه‌ی عالی.
- pop: تأکید روی یک کلمه‌ی کلیدی که هیچ دسته‌ی دیگری نمی‌گیرد.
قاعده‌ها:
- کم و دقیق: افکت باید معنای همان لحظه را تقویت کند، نه جای خالی را پر. به‌طور میانگین حداکثر یکی در هر ۵ ثانیه و هرگز دو تا با فاصله‌ی کمتر از ۱٫۵ ثانیه؛ ویدیوی ۶۰ ثانیه‌ای حدود ۶ تا ۱۲ افکت.
- افکت روی شروع همان کلمه‌ای می‌نشیند که اندیسش را می‌دهی.
- هر مورد یک دلیل کوتاه فارسی (why) دارد، مثل «مورد دوم فهرست» یا «قیمت ManyChat».
- summary یک جمله به فارسی ساده است و اسم انگلیسی دسته‌ها را نمی‌آورد؛ مثلاً «صدای سکه روی هر قیمت، ووش سر هر مورد فهرست».
- اگر مطمئن نیستی، نگذار."""


def sfx_prompt(dv, comment="", current=None, notes=()):
    words, fix, tm = dv["words"], dv["edit"].get("fix") or {}, dv["tmap"]
    rows = []
    for w in words:
        t = disp(words, fix, w["i"]).strip()
        if w["i"] not in dv["cut"] and t:
            rows.append(f"{w['i']}|{t}|{tm.out(w['s']):.1f}")
    kind = "ریلز عمودی (حرف زدن جلوی دوربین)" if dv.get("src_kind", dv["kind"]) == "reel" else "ضبط صفحه‌ی کامپیوتر (آموزش یا دمو)"
    parts = [f"تو صداگذار ویدیوهای کوتاه فارسی این برند هستی. ویدیو: {kind}، {tm.dur:.0f} ثانیه بعد از برش. "
             "موزیک پس‌زمینه نداریم؛ فقط چند افکت کوتاه که ساختار حرف و لحظه‌های مهمش را حس‌پذیر کند.",
             "کلمه‌های ویدیو بعد از برش. قالب هر خط: اندیس|کلمه|زمان در خروجی (ثانیه):\n<<<WORDS\n" + "\n".join(rows) + "\nWORDS>>>"]
    if dv["emph"]:
        parts.append("اندیس کلمه‌های تأکیدی زیرنویس (زرد): " + "، ".join(str(i) for i in sorted(dv["emph"])))
    parts.append("کار تو: جای افکت‌ها را پیدا کن.\n" + SFX_RULES)
    if current is not None:
        parts.append("افکت‌های فعلی (برای بازنویسی):\n" + json.dumps(current, ensure_ascii=False))
    if notes:
        parts.append("نظرهای قبلی کاربر درباره‌ی افکت‌ها (رعایت کن):\n" + "\n".join("- " + n for n in notes))
    if comment:
        parts.append("نظر تازه‌ی کاربر (مهم‌ترین دستور): " + comment)
    parts.append('خروجی فقط یک JSON بین این دو نشانه، بدون هیچ توضیح دیگر:\n<<<SFX\n'
                 '{"sfx": [{"w": 12, "cat": "whoosh", "why": "دلیل کوتاه فارسی"}], "summary": "یک جمله: کجاها و چرا"}\nSFX>>>')
    return "\n\n".join(parts)


def clean_sfx(data, dv):
    """پیشنهاد Claude را امن می‌کند: کلمه‌ی معتبر و نبریده، دسته‌ی مجاز، فاصله‌ها و سقف‌ها. هر دسته صدای پیش‌فرض خودش را می‌گیرد."""
    lib = sfx_lib()
    words, tm = dv["words"], dv["tmap"]
    cand = []
    for x in data.get("sfx") or []:
        try:
            w = int(x.get("w"))
        except Exception:
            continue
        cat = str(x.get("cat") or "")
        snd = (lib["cats"].get(cat) or {}).get("default")
        if cat in SFX_PRI and 0 <= w < len(words) and w not in dv["cut"] and snd in lib["sounds"]:
            cand.append({"w": w, "cat": cat, "snd": snd, "why": str(x.get("why") or "")[:120], "at": tm.out(words[w]["s"])})
    cand.sort(key=lambda c: c["at"])
    keep = []
    for c in cand:
        if keep and c["at"] - keep[-1]["at"] < SFX_GAP:
            if SFX_PRI[c["cat"]] > SFX_PRI[keep[-1]["cat"]]:
                keep[-1] = c
            continue
        keep.append(c)
    out, last_pop, impacts = [], -99.0, 0
    for c in keep:
        if c["cat"] == "pop":
            if c["at"] - last_pop < SFX_POP_GAP:
                continue
            last_pop = c["at"]
        if c["cat"] == "impact":
            if impacts >= SFX_MAX_IMPACT:
                continue
            impacts += 1
        out.append(c)
    return [{"id": f"x{k}", "w": c["w"], "snd": c["snd"], "cat": c["cat"], "why": c["why"], "on": True, "src": "claude"}
            for k, c in enumerate(out)]


def suggest_sfx(vid, comment="", step=lambda s: None):
    """Claude جای افکت‌ها را پیشنهاد می‌دهد و کد فاصله‌ها و سقف‌ها را اعمال می‌کند. افکتی که کاربر خودش گذاشته دست نمی‌خورد."""
    dv = derive(vid)
    e0 = dv["edit"]
    cues, summary = [], "حرفی در این ویدیو نیست؛ افکتی پیشنهاد نشد."
    if any(w["i"] not in dv["cut"] for w in dv["words"]):
        step("Claude دارد جای افکت‌های صوتی را پیدا می‌کند…")
        current = [{"w": x.get("w"), "cat": x.get("cat"), "why": x.get("why", "")} for x in e0.get("sfx") or []
                   if x.get("src") not in ("user", "vis")]
        notes = ((e0.get("notes") or {}).get("sfx") or [])[-6:]
        res = ask(sfx_prompt(dv, comment, current if comment else None, notes), vid, timeout=900, effort="medium")
        data = json_block(res, "<<<SFX", "SFX>>>")
        if not data:
            (pdir(vid) / "sfx.last-output.txt").write_text(res or "", encoding="utf-8")
            raise RuntimeError("جواب Claude برای افکت‌ها قابل خواندن نبود.")
        cues, summary = clean_sfx(data, dv), str(data.get("summary") or "")[:400]
    with plock(vid):
        e = jload(pdir(vid) / "edit.json", {})
        if "sfx" in e:
            e.setdefault("prev", {})["sfx"] = e["sfx"]
        e["sfx"] = sorted([x for x in e.get("sfx") or [] if x.get("src") in ("user", "vis")] + cues, key=lambda x: x["w"])
        e["sfxSummary"] = summary
        if comment:
            e.setdefault("notes", {}).setdefault("sfx", []).append(comment[:500])
        e["sfxAt"] = now()
        jsave(pdir(vid) / "edit.json", e)


# ---------------- ترکیب HTML (HyperFrames) ----------------
def style_css(style, kind, W, H, size="m"):
    fs, wt = cap_font(kind, style, size)
    y = int(H * zones_for(kind, cap_box_h(kind, style, size))["bot"])
    pv, ph = PILL_PAD[kind]
    # همیشه یک خط (nowrap)؛ تکه‌ها از قبل با اندازه‌گیری فونت طوری بریده شده‌اند که در CAP_W جا شوند
    base = f"""
.cap{{position:absolute;left:0;top:{y}px;width:{W}px;display:flex;justify-content:center;align-items:flex-start;z-index:10}}
.cap .line{{display:block;direction:rtl;white-space:nowrap;text-align:center;font-weight:{wt};font-size:{fs}px;line-height:1.5;color:#fff;word-spacing:2px}}
.cap .w{{display:inline}}
.cap .w.em{{color:{YELLOW}}}"""
    big = kind == "reel"
    # هاله‌ی تیره‌ی چندلایه تا روی زمینه‌ی سفید (مثل صفحه‌ی سایت) هم خوانا بماند؛ stroke روی حروف چسبیده درز می‌اندازد
    shadow = ("text-shadow:0 0 2px rgba(0,0,0,.95),0 0 6px rgba(0,0,0,.85),0 0 14px rgba(0,0,0,.65),"
              "0 4px 22px rgba(0,0,0,.55),0 2px 0 rgba(0,0,0,.45)")
    extra = {
        "clean": f".cap .line{{{shadow}}}",
        "pill": f".cap .line{{background:rgba(26,60,100,.94);padding:{pv}px {ph}px;border-radius:{24 if big else 16}px;box-shadow:0 10px 30px rgba(0,0,0,.35)}}",
        "punch": f".cap .line{{{shadow}}}\n.cap .w.em{{font-size:1.12em}}",
        "karaoke": f".cap .line{{{shadow}}}\n.cap .w{{color:rgba(255,255,255,.42)}}\n.cap .w.em{{color:rgba(255,219,88,.5)}}",
    }[style]
    return base + "\n" + extra


def build_comp(vid, mode="render", dv=None):
    """comp/index.html (رندر) یا comp/preview.html. dv = derive(vid) اگر از قبل حساب شده."""
    global NAVY, YELLOW
    NAVY, YELLOW = brand_colors()          # زیرنویس تأکیدی به رنگ تأکید برند خود کاربر
    dv = dv or derive(vid)
    d = pdir(vid)
    comp, assets = d / "comp", d / "comp" / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    for src in (MOD / "fonts" / "Vazirmatn-Variable.woff2", MOD / "vendor" / "gsap.min.js", MOD / "preview-shim.js"):
        dst = assets / src.name
        if src.exists() and (not dst.exists() or dst.stat().st_mtime < src.stat().st_mtime):
            shutil.copy2(src, dst)
    kind, opts, tmap = dv["kind"], dv["opts"], dv["tmap"]
    W, H = CANVAS[kind]
    D = round(max(tmap.dur, 1 / FPS), 3)
    style = opts["style"] if opts["style"] in STYLES else "clean"
    video_src = "assets/cut.mp4" if mode == "render" else "assets/proxy_cut.mp4"
    info = dv["proj"].get("info") or {}

    pre_tl = []
    if dv.get("src_kind", kind) == "reel":
        stage = (f'<div id="vwrap"><video id="v" src="{video_src}" data-start="0" data-duration="{D}" data-track-index="0" '
                 f'{"muted " if mode == "render" else ""}playsinline></video></div>')
        stage_css = "#vwrap{position:absolute;inset:0;transform-origin:50% 38%}\n#v{width:100%;height:100%;object-fit:cover;display:block}"
    else:   # ضبط صفحه (فاز ۵، video_screen.py): قاب روی زمینه‌ی برند، یا عمودی ۹:۱۶؛ با ظرف زوم #vz
        import video_screen as vsc
        stage, stage_css, pre_tl = vsc.screen_stage(vid, dv, mode, video_src, D, W, H, assets)

    caps_html, tl = [], list(pre_tl)
    emph = dv["emph"]
    base_fs = cap_font(kind, style, opts.get("size", "m"))[0]
    bot_y = int(H * zones_for(kind, cap_box_h(kind, style, opts.get("size", "m")))["bot"])
    for c in dv["caps"]:
        spans = []
        for k, w in enumerate(c["words"]):
            txt = clean_caption_text(w["t"]) if k == len(c["words"]) - 1 else w["t"]
            cls = "w em" if w["i"] in emph else "w"
            spans.append(f'<span id="{c["id"]}w{k}" class="{cls}">{escape(txt)}</span>')
        dur = round(c["e"] - c["s"], 3)
        fs_style = f' style="font-size:{c["fs"]}px"' if c.get("fs") and c["fs"] != base_fs else ""
        caps_html.append(f'<div id="{c["id"]}" class="clip cap" data-start="{c["s"]}" data-duration="{dur}" data-track-index="2" '
                         f'style="top:{c.get("y", 0) or bot_y}px">'
                         f'<div class="line" id="{c["id"]}l"{fs_style}>{" ".join(spans)}</div></div>')
        if style == "punch":
            tl.append(f'tl.fromTo("#{c["id"]}l",{{opacity:0,scale:.82}},{{opacity:1,scale:1,duration:.16,ease:"back.out(2.2)"}},{c["s"]});')
        else:
            tl.append(f'tl.fromTo("#{c["id"]}l",{{opacity:0,y:16}},{{opacity:1,y:0,duration:.14,ease:"power2.out"}},{c["s"]});')
        for k, w in enumerate(c["words"]):   # GSAP 3 کلاس را tween نمی‌کند؛ رنگ مستقیم عوض می‌شود
            sel = f'#{c["id"]}w{k}'
            after = YELLOW if w["i"] in emph else "#ffffff"
            tl.append(f'tl.set("{sel}",{{color:"{YELLOW}"}},{max(c["s"], w["s"])});')
            tl.append(f'tl.set("{sel}",{{color:"{after}"}},{min(c["s"] + dur, max(w["e"], w["s"] + 0.08))});')

    ov_html, ov_css = [], ""
    if dv.get("vis"):                          # عکس، ویدیو و گرافیک (video_visuals.py)؛ زیر زیرنویس
        import video_visuals as vv
        ov_html, ov_css, ov_tl = vv.comp_parts(vid, dv, mode, assets)
        tl += ov_tl

    if opts.get("punch") and dv.get("src_kind", kind) == "reel":   # زوم ملایم یکی‌درمیان روی برش‌ها تا پرش تصویر به چشم نیاید
        for k, t in enumerate(tmap.seg_starts()):
            if k:
                tl.append(f'tl.set("#vwrap",{{scale:{1.08 if k % 2 else 1.0}}},{round(t, 3)});')

    shim = '<script src="assets/preview-shim.js"></script>' if mode == "preview" else ""
    if mode == "preview":       # افکت‌ها در پیش‌نمایش با WebAudio پخش می‌شوند (preview-shim.js)؛ در رندر ffmpeg میکسشان می‌کند
        shim = f"<script>window.__sfx={json.dumps(sfx_preview(dv, assets))};</script>\n" + shim
    page = f"""<!doctype html>
<html lang="fa">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width={W}, height={H}"/>
<title>{escape((dv["proj"].get("title") or "video")[:60])}</title>
<script src="assets/gsap.min.js"></script>
<style>
@font-face{{font-family:"Vazirmatn";src:url("assets/Vazirmatn-Variable.woff2") format("woff2");font-weight:100 900;font-display:block}}
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{width:{W}px;height:{H}px;overflow:hidden;background:{BG}}}
body{{font-family:"Vazirmatn",sans-serif}}
#root{{position:relative;width:{W}px;height:{H}px;overflow:hidden}}
{stage_css}
{style_css(style, kind, W, H, opts.get("size", "m"))}
{ov_css}
</style>
</head>
<body>
<div id="root" data-composition-id="main" data-start="0" data-duration="{D}" data-width="{W}" data-height="{H}" data-fps="{FPS}">
{stage}
{chr(10).join(ov_html)}
{chr(10).join(caps_html)}
</div>
<script>
window.__timelines = window.__timelines || {{}};
const tl = gsap.timeline({{ paused: true }});
{chr(10).join(tl)}
window.__timelines["main"] = tl;
</script>
{shim}
</body>
</html>
"""
    name = "index.html" if mode == "render" else "preview.html"
    (comp / name).write_text(page, encoding="utf-8")
    return comp / name


# ---------------- برش رسانه، میکس، رندر ----------------
def _select_expr(keeps):
    """ffmpeg بیش از ۹۹ جمله‌ی پشت‌سرهم در یک عبارت را نمی‌پذیرد («Error while parsing expression»، کد 244)
    و ویدیوی بلند صدها بخش دارد (۲۰۲۶-۱۰-۰۷: ۱۹ دقیقه = ۱۷۸ بخش). پس جمع دوتایی و پرانتزدار ساخته می‌شود؛ با ۳۰۰۰ بخش هم آزموده شد."""
    terms = [f"gte(t\\,{a - 0.001:.4f})*lt(t\\,{b - 0.001:.4f})" for a, b in keeps]

    def tree(ts):
        if len(ts) <= 32:
            return "+".join(ts)
        m = len(ts) // 2
        return f"({tree(ts[:m])})+({tree(ts[m:])})"
    return tree(terms) if terms else "0"


def cut_video(src, keeps, out, vid=None, preview=False, blurs=()):
    """blurs: [(s, e, box)] محو اطلاعات حساس ضبط صفحه (فاز ۵) — پیش از برش و با زمان منبع، پس با برش‌ها جابه‌جا نمی‌شود."""
    sel = _select_expr(keeps)
    enc = (["-c:v", "libx264", "-preset", "veryfast", "-crf", "30", "-g", "10"] if preview else
           ["-c:v", "libx264", "-preset", "veryfast", "-crf", "15", "-g", str(FPS), "-keyint_min", str(FPS), "-sc_threshold", "0"])
    if blurs:
        import video_screen as vsc
        p = probe(src)
        graph, last = vsc.blur_graph(list(blurs), p["w"], p["h"])
        body, flag = graph + f"{last}select='{sel}',setpts=N/({FPS}*TB)[vout]", ["-/filter_complex"]
    else:
        body, flag = f"select='{sel}',setpts=N/({FPS}*TB)", ["-/filter:v"]
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        f.write(body)
        script = f.name
    try:
        run([FFMPEG, "-v", "error", "-y", "-i", src, *flag, script, *(["-map", "[vout]"] if blurs else []), "-an", *enc,
             "-pix_fmt", "yuv420p", "-movflags", "+faststart", out], vid)
    finally:
        os.unlink(script)


def screen_blurs(dv):
    if dv.get("src_kind") != "screen":
        return []
    import video_screen as vsc
    return vsc.active_blurs(dv)


def cut_audio(src, keeps, out, vid=None):
    """هر تکه ۸ میلی‌ثانیه محو می‌شود تا محل برش «تق» نکند."""
    lines = []
    for k, (a, b) in enumerate(keeps):
        L = b - a
        fade = min(0.008, L / 4)
        lines.append(f"[0:a]atrim=start={a:.4f}:end={b:.4f},asetpts=PTS-STARTPTS,"
                     f"afade=t=in:d={fade:.4f},afade=t=out:st={max(0, L - fade):.4f}:d={fade:.4f}[a{k}];")
    lines.append("".join(f"[a{k}]" for k in range(len(keeps))) + f"concat=n={len(keeps)}:v=0:a=1[ao]")
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        f.write("\n".join(lines))
        script = f.name
    try:
        run([FFMPEG, "-v", "error", "-y", "-i", src, "-/filter_complex", script, "-map", "[ao]",
             "-ar", "48000", "-ac", "1", "-c:a", "pcm_s16le", out], vid)
    finally:
        os.unlink(script)


VOICE_CHAIN = "highpass=f=75,afftdn=nf=-28:tn=1,acompressor=threshold=-20dB:ratio=2.5:attack=8:release=90:makeup=1.5"


def loudnorm(src, out, vid=None, clean=True, target=-14.0):
    """بلندی نهایی −14 LUFS (استاندارد شبکه‌های اجتماعی)، اوج −1 dBTP؛ دو مرحله‌ای."""
    pre = (VOICE_CHAIN + ",") if clean else ""
    _, err = run([FFMPEG, "-hide_banner", "-nostats", "-i", src, "-af", f"{pre}loudnorm=I={target}:TP=-1.0:LRA=11:print_format=json",
                  "-f", "null", "-"], vid)
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", err.decode("utf-8", "replace"))
    if m:
        j = json.loads(m.group(0))
        ln = (f"loudnorm=I={target}:TP=-1.0:LRA=11:measured_I={j['input_i']}:measured_TP={j['input_tp']}:"
              f"measured_LRA={j['input_lra']}:measured_thresh={j['input_thresh']}:offset={j['target_offset']}:linear=true")
    else:
        ln = f"loudnorm=I={target}:TP=-1.0:LRA=11"
    run([FFMPEG, "-v", "error", "-y", "-i", src, "-af", pre + ln, "-ar", "48000", "-c:a", "pcm_s16le", out], vid)


def mix_sfx(voice, cues, out, vid=None):
    """صدای گوینده (از قبل −14 LUFS) + افکت‌ها، هر کدام سر جای خودش و با بهره‌ی خودش (amix بدون نرمال‌سازی)؛
    آخرش محدودکننده روی ۱۹۲ کیلوهرتز تا اوج واقعی (بین نمونه‌ها هم) زیر −2 dBTP بماند؛ روی ۴۸ کیلوهرتز اوج واقعی −0.7 می‌شد.
    AAC خروجی روی گذرای فلزی (صدای سکه) تا حدود ۱٫۵ dB به اوج اضافه می‌کند: final.mp4 حدود −0.5 dBTP، زیر صفر.
    بلندی کل تقریباً همان می‌ماند (−14.9 → −14.7 LUFS روی ریلز ۱۴۳ ثانیه‌ای با ۲۳ افکت)، چون افکت‌ها کوتاه و حدود ۱۰ dB زیر صدای گوینده‌اند."""
    lib = sfx_lib()["sounds"]
    args, lines = [FFMPEG, "-v", "error", "-y", "-i", voice], ["[0:a]aformat=sample_rates=48000:channel_layouts=stereo[v];"]
    for k, c in enumerate(cues, 1):
        ms = int(round(c["t"] * 1000))
        args += ["-i", SFX_DIR / lib[c["snd"]]["file"]]
        lines.append(f"[{k}:a]aformat=sample_rates=48000:channel_layouts=stereo,volume={c['db']}dB,adelay=delays={ms}:all=1[s{k}];")
    lines.append("[v]" + "".join(f"[s{k}]" for k in range(1, len(cues) + 1)) +
                 f"amix=inputs={len(cues) + 1}:duration=first:dropout_transition=0:normalize=0,"
                 "aresample=192000,alimiter=limit=0.79:attack=5:release=60:level=false:latency=true,aresample=48000[ao]")
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        f.write("\n".join(lines))
        script = f.name
    try:
        run(args + ["-/filter_complex", script, "-map", "[ao]", "-ar", "48000", "-c:a", "pcm_s16le", out], vid)
    finally:
        os.unlink(script)


def build_preview(vid, step=lambda s: None):
    """نسخه‌ی سبکِ برش‌خورده با صدا + preview.html. چند ثانیه."""
    dv = derive(vid)
    d = pdir(vid)
    assets = d / "comp" / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    step("ساخت پیش‌نمایش…")
    with tempfile.TemporaryDirectory() as td:
        v, a = Path(td) / "v.mp4", Path(td) / "a.wav"
        cut_video(d / "proxy.mp4", dv["keeps"], v, vid, preview=True, blurs=screen_blurs(dv))
        cut_audio(d / "voice.wav", dv["keeps"], a, vid)
        tmp = assets / "proxy_cut.tmp.mp4"
        run([FFMPEG, "-v", "error", "-y", "-i", v, "-i", a, "-map", "0:v", "-map", "1:a",
             "-af", (VOICE_CHAIN + "," if dv["opts"].get("voiceClean") else "") + "loudnorm=I=-14:TP=-1.0",
             "-c:v", "copy", "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", tmp], vid)
        tmp.replace(assets / "proxy_cut.mp4")
    build_comp(vid, "preview", dv)
    return dv


def render(vid, step=lambda s: None):
    dv = derive(vid)
    d = pdir(vid)
    out = d / "out"
    out.mkdir(parents=True, exist_ok=True)
    assets = d / "comp" / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    step("برش نسخه‌ی اصلی…")
    cut_video(d / "master.mp4", dv["keeps"], assets / "cut.mp4", vid, blurs=screen_blurs(dv))
    step("صدا: برش، تمیزکاری و تنظیم بلندی…")
    cues = sfx_active(dv)
    with tempfile.TemporaryDirectory() as td:
        a = Path(td) / "voice_cut.wav"
        cut_audio(d / "voice.wav", dv["keeps"], a, vid)
        voice = Path(td) / "voice_norm.wav" if cues else d / "out" / "mix.wav"
        loudnorm(a, voice, vid, clean=dv["opts"].get("voiceClean", True))
        if cues:
            step(f"میکس {len(cues)} افکت صوتی…")
            mix_sfx(voice, cues, d / "out" / "mix.wav", vid)
    build_comp(vid, "render", dv)
    step("رندر طراحی با Chrome (HyperFrames)…")
    env = {**os.environ, "HYPERFRAMES_NO_TELEMETRY": "1", "DO_NOT_TRACK": "1", "PRODUCER_BROWSER_GPU_MODE": "hardware"}
    silent = out / "video.mp4"
    args = [HF_BIN, "render", d / "comp", "-o", silent, "--fps", str(FPS), "--quality", "high"]
    if dv.get("src_kind", dv["kind"]) == "screen":
        args += ["--video-frame-format", "png"]
    log = out / "render.log"
    try:
        o, e = run(args, vid, timeout=4 * 3600, cwd=MOD, env=env)
        log.write_bytes((o or b"") + b"\n---- stderr ----\n" + (e or b""))
    except RuntimeError as ex:
        log.write_text(str(ex), encoding="utf-8")
        raise
    step("چسباندن صدا…")
    final = out / "final.mp4"
    run([FFMPEG, "-v", "error", "-y", "-i", silent, "-i", out / "mix.wav", "-map", "0:v", "-map", "1:a", "-c:v", "copy",
         "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-shortest", "-movflags", "+faststart", out / "final.tmp.mp4"], vid)
    (out / "final.tmp.mp4").replace(final)
    (out / "final.srt").write_text(srt(dv["caps"]), encoding="utf-8")
    silent.unlink(missing_ok=True)
    return {"secs": round(time.time() - t0, 1), "dur": round(dv["tmap"].dur, 2), "size": final.stat().st_size, "sfx": len(cues)}
