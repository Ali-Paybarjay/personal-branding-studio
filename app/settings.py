"""تنظیمات استودیو: پروفایل صاحب استودیو، کلیدها، بررسی ابزارها و وضعیت «شروع».

هر دانشجو استودیوی خودش را دارد. هرچه شخصی است از اینجا خوانده می‌شود، نه از کد:
- data/settings.json: پروفایل (اسم، آیدی اینستاگرام، کار) و قدم‌های شروع.
- .env در ریشه‌ی استودیو: کلید Gemini و توکن اینستاگرام. هرگز به مرورگر فرستاده نمی‌شود.
"""
import json, os, re, shutil, subprocess, sys, threading, time, urllib.error, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
BRAND = ROOT / "brand"
ENV_FILE = ROOT / ".env"
FILE = DATA / "settings.json"
IS_MAC = sys.platform == "darwin"
IS_WIN = os.name == "nt"
LOCK = threading.Lock()
IDEAS_LOCK = threading.Lock()   # همه‌ی نوشتن‌های data/ideas.json از این قفل رد می‌شوند

PROFILE_KEYS = ("name", "handle", "work")


# ---------- فایل .env ----------
def read_env():
    vals = {}
    if ENV_FILE.exists():
        for ln in ENV_FILE.read_text(encoding="utf-8").splitlines():
            ln = ln.strip()
            if ln and not ln.startswith("#") and "=" in ln:
                k, v = ln.split("=", 1)
                vals[k.strip()] = v.strip().strip('"').strip("'")
    return vals


def write_env(key, value):
    """یک کلید را در .env می‌نویسد یا پاک می‌کند (value خالی) و بقیه‌ی خط‌ها را نگه می‌دارد."""
    with LOCK:
        lines = ENV_FILE.read_text(encoding="utf-8").splitlines() if ENV_FILE.exists() else []
        lines = [l for l in lines if not re.match(rf"\s*{re.escape(key)}\s*=", l)]
        if value:
            lines.append(f"{key}={value}")
        ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
        if not IS_WIN:
            os.chmod(ENV_FILE, 0o600)


def env(key):
    return os.environ.get(key) or read_env().get(key, "")


def gemini_key():
    return env("GEMINI_API_KEY") or env("GOOGLE_API_KEY")


# ---------- Claude Code ----------
def claude_bin():
    found = shutil.which("claude")
    if found:
        return found
    for name in ("claude.exe", "claude"):
        p = Path.home() / ".local" / "bin" / name
        if p.exists():
            return str(p)
    return "claude"


def prepare_env():
    """یک بار موقع شروع سرور. همه‌ی claude هایی که استودیو اجرا می‌کند این‌ها را به ارث می‌برند.
    بدون این دو، کانکتورهای MCP حساب کاربر (Canva، Notion و …) کامل در پرامپت می‌ریزند
    و هر فراخوانی با «Prompt is too long» شکست می‌خورد."""
    os.environ.setdefault("ENABLE_CLAUDEAI_MCP_SERVERS", "false")
    os.environ.setdefault("ENABLE_TOOL_SEARCH", "true")
    os.environ.setdefault("HYPERFRAMES_NO_TELEMETRY", "1")


# ---------- پروفایل ----------
def load():
    try:
        d = json.loads(FILE.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def save(patch):
    with LOCK:
        d = load()
        for k, v in patch.items():
            if isinstance(v, dict) and isinstance(d.get(k), dict):
                d[k] = {**d[k], **v}
            else:
                d[k] = v
        DATA.mkdir(exist_ok=True)
        tmp = FILE.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, FILE)
        return d


def profile():
    p = load().get("profile") or {}
    out = {k: str(p.get(k) or "").strip() for k in PROFILE_KEYS}
    out["handle"] = out["handle"].lstrip("@")
    return out


def owner():
    """اسم صاحب استودیو برای پرامپت‌ها؛ اگر هنوز پر نشده «صاحب این استودیو»."""
    return profile()["name"] or "صاحب این استودیو"


def owner_line():
    """یک خط معرفی برای پرامپت‌ها: «مریم احمدی (پیج ‎@maryam.hr‎) — مشاور منابع انسانی»."""
    p = profile()
    s = p["name"] or "صاحب این استودیو"
    if p["handle"]:
        s += f" (پیج اینستاگرام @{p['handle']})"
    if p["work"]:
        s += f" — {p['work']}"
    return s


def handle_at():
    h = profile()["handle"]
    return f"@{h}" if h else ""


# ---------- بررسی ابزارها ----------
def _ver(cmd, timeout=15):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
        out = (r.stdout or r.stderr or "").strip().splitlines()
        return out[0][:80] if r.returncode == 0 and out else None
    except Exception:
        return None


def claude_auth():
    """{installed, version, loggedIn, plan} — بدون خرج کردن سهمیه."""
    c = claude_bin()
    v = _ver([c, "--version"])
    if not v:
        return {"installed": False}
    out = {"installed": True, "version": v, "loggedIn": False, "plan": ""}
    try:
        r = subprocess.run([c, "auth", "status", "--json"], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=20)
        d = json.loads(r.stdout or "{}")
        out["loggedIn"] = bool(d.get("loggedIn"))
        out["plan"] = d.get("subscriptionType") or d.get("authMethod") or ""
    except Exception:
        pass
    return out


def tools():
    """وضعیت هر ابزار. بررسی‌ها هم‌زمان اجرا می‌شوند (claude auth status خودش یکی دو ثانیه طول می‌کشد)."""
    from concurrent.futures import ThreadPoolExecutor
    ffmpeg = shutil.which("ffmpeg")
    node = shutil.which("node")
    with ThreadPoolExecutor(3) as ex:
        f_claude = ex.submit(claude_auth)
        f_yt = ex.submit(lambda: _ver(["yt-dlp", "--version"]) if shutil.which("yt-dlp") else None)
        f_node = ex.submit(lambda: _ver(["node", "--version"]) if node else None)
        claude, yt_ver, node_ver = f_claude.result(), f_yt.result(), f_node.result()
    chrome = IS_MAC and Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome").exists()
    video_ready = IS_MAC and bool(ffmpeg) and bool(node) and chrome and (ROOT / "modules" / "video" / "node_modules").is_dir()
    return {
        "python": {"ok": True, "version": sys.version.split()[0]},
        "claude": claude,
        "ytdlp": {"ok": bool(yt_ver), "version": yt_ver},
        "ffmpeg": {"ok": bool(ffmpeg)},
        "node": {"ok": bool(node), "version": node_ver},
        "gemini": {"ok": bool(gemini_key())},
        "video": {"ok": video_ready, "mac": IS_MAC, "chrome": chrome},
        "instagram": {"ok": bool(env("INSTAGRAM_TOKEN"))},
    }


def test_gemini(key):
    """کلید را با فهرست مدل‌ها امتحان می‌کند (رایگان)."""
    req = urllib.request.Request("https://generativelanguage.googleapis.com/v1beta/models?pageSize=1",
                                 headers={"x-goog-api-key": key})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status == 200, ""
    except urllib.error.HTTPError as e:
        return False, "کلید را Google قبول نکرد." if e.code in (400, 401, 403) else f"HTTP {e.code}"
    except Exception as e:
        return False, f"اتصال برقرار نشد: {str(e)[:120]}"


def test_claude():
    """یک پیام خیلی کوتاه با ارزان‌ترین مدل؛ نشان می‌دهد Claude Code از داخل استودیو جواب می‌دهد."""
    try:
        r = subprocess.run([claude_bin(), "-p", "فقط بنویس: آماده‌ام", "--model", "claude-haiku-5-5",
                            "--no-session-persistence", "--safe-mode", "--tools", ""],
                           capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=120, cwd=str(DATA if DATA.is_dir() else ROOT))
        out = (r.stdout or "").strip()
        if r.returncode == 0 and out:
            return True, out[:200]
        return False, ((r.stderr or r.stdout or "").strip()[-300:] or "جوابی نیامد.")
    except subprocess.TimeoutExpired:
        return False, "Claude در ۲ دقیقه جواب نداد."
    except Exception as e:
        return False, str(e)[:200]


# ---------- قدم‌های شروع ----------
def _brand_progress():
    import brand as bc
    fields = bc.load()["fields"]
    must = [f for f in bc.all_fields() if f.get("level") == 1]
    done = sum(1 for f in must if bc.filled(f, (fields.get(f["id"]) or {}).get("v")))
    return done, len(must)


def _ideas():
    try:
        return json.loads((DATA / "ideas.json").read_text(encoding="utf-8"))
    except Exception:
        return []


def onboarding():
    """قدم‌های «شروع»، هرکدام با done. ترتیب همان ترتیبی است که صفحه نشان می‌دهد."""
    p = profile()
    t = tools()
    bdone, btotal = _brand_progress()
    ideas = _ideas()
    reels = [i for i in ideas if (DATA / "ideas" / str(i.get("id")) / "reel.json").exists()]
    s = load().get("steps") or {}
    return {
        "profile": p,
        "tools": t,
        "brand": {"done": bdone, "total": btotal},
        "counts": {"ideas": len(ideas), "reels": len(reels)},
        "steps": {
            "tools": t["claude"].get("loggedIn", False),
            "profile": bool(p["name"]),
            "gemini": t["gemini"]["ok"],
            "brand": btotal > 0 and bdone >= min(btotal, 12),
            "idea": len(ideas) > 0,
            "reel": len(reels) > 0,
            "story": bool(s.get("story")),
        },
        "dismissed": bool(load().get("onboarding_dismissed")),
        "platform": "mac" if IS_MAC else "windows" if IS_WIN else "linux",
    }


# ---------- مسیرها ----------
def handle_get(p, q):
    if p == "/api/setup":
        return 200, onboarding()
    if p == "/api/settings":
        key = gemini_key()
        return 200, {"profile": profile(),
                     "gemini": {"set": bool(key), "hint": f"…{key[-4:]}" if key else ""},
                     "platform": "mac" if IS_MAC else "windows" if IS_WIN else "linux"}
    return None


def handle_post(p, body):
    if p == "/api/settings/profile":
        prof = {k: str(body.get(k) or "").strip()[:200] for k in PROFILE_KEYS if k in body}
        if "handle" in prof:
            prof["handle"] = re.sub(r"^(https?://)?(www\.)?instagram\.com/", "", prof["handle"]).strip("/@ ")
        d = save({"profile": prof})
        return 200, {"ok": True, "profile": d.get("profile")}
    if p == "/api/settings/gemini":
        key = str(body.get("key") or "").strip()
        if not key:
            write_env("GEMINI_API_KEY", "")
            return 200, {"ok": True, "set": False}
        if not re.fullmatch(r"[\w\-]{20,200}", key):
            return 400, {"error": "این شبیه کلید Gemini نیست. کلید را کامل از Google AI Studio کپی کن."}
        ok, err = test_gemini(key)
        if not ok:
            return 400, {"error": err}
        write_env("GEMINI_API_KEY", key)
        return 200, {"ok": True, "set": True, "hint": f"…{key[-4:]}"}
    if p == "/api/settings/test-claude":
        ok, msg = test_claude()
        return (200, {"ok": True, "reply": msg}) if ok else (400, {"error": msg})
    if p == "/api/setup/step":
        step = str(body.get("step") or "")
        if step in ("story",):
            save({"steps": {step: True}})
        if "dismissed" in body:
            save({"onboarding_dismissed": bool(body["dismissed"])})
        return 200, {"ok": True}
    return None
