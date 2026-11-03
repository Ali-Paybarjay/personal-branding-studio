"""اجرای GPT-6 Astra با Codex CLI (اشتراک ChatGPT خود کاربر) برای کارهایی که فقط متن برمی‌گردانند.

Codex در یک پوشه‌ی موقت خالی، فقط‌خواندنی و بدون هیچ ابزار فایل یا فرمان اجرا می‌شود؛ پس به پوشه‌ی
استودیو (و .env) دسترسی ندارد و هر متنی که لازم دارد باید داخل خود پرامپت باشد. پرامپت از stdin می‌رود.
تنظیم‌ها همان‌هایی است که اسکیل crossidea روی همین Codex آزموده است.
"""
import os, re, shutil, subprocess, sys, tempfile, threading, time
from pathlib import Path

EFFORT = "high"
# ابزارهایی که فرمان اجرا می‌کنند، فایل محلی می‌خوانند یا پردازه راه می‌اندازند؛ Astra فقط پرامپت و (گاهی) جستجوی وب لازم دارد
DISABLED = """shell_tool unified_exec apps computer_use browser_use browser_use_external browser_use_full_cdp_access
in_app_browser plugins remote_plugin plugin_sharing skill_search skill_mcp_dependency_install workspace_dependencies
tool_suggest multi_agent image_generation view_image mentions_v2 hooks goals daemon_auto_start
in_app_local_automation""".split()

_STATUS = {"t": 0, "v": None}
_SLOCK = threading.Lock()


def codex_bin():
    found = shutil.which("codex")
    if found:
        return found
    for p in (Path.home() / ".npm-global" / "bin" / "codex", Path("/opt/homebrew/bin/codex"), Path("/usr/local/bin/codex")):
        if p.exists():
            return str(p)
    return None


def status(fresh=False):
    """{"installed", "logged_in", "note"}؛ یک دقیقه کش می‌شود چون هر بار باز شدن تنظیمات صدایش می‌زند."""
    with _SLOCK:
        if not fresh and _STATUS["v"] and time.time() - _STATUS["t"] < 60:
            return _STATUS["v"]
        b = codex_bin()
        if not b:
            v = {"installed": False, "logged_in": False, "note": "Codex نصب نیست."}
        else:
            try:
                r = subprocess.run([b, "login", "status"], capture_output=True, text=True, encoding="utf-8",
                                   errors="replace", timeout=20, stdin=subprocess.DEVNULL)
                out = ((r.stdout or "") + (r.stderr or "")).strip()
                ok = out.lower().startswith("logged in")
                v = {"installed": True, "logged_in": ok,
                     "note": out.splitlines()[0] if ok and out else "Codex نصب است ولی وارد حساب نشده‌ای (در ترمینال بزن: codex login)."}
            except Exception as e:
                v = {"installed": True, "logged_in": False, "note": f"Codex جواب نداد: {e}"}
        _STATUS.update(t=time.time(), v=v)
        return v


def ask(prompt, timeout, model, web=False):
    """(کد خروج، متن جواب، دنباله‌ی خطا) — همان قالب _ask در reel_editor."""
    b = codex_bin()
    if not b:
        return 1, "", "Codex پیدا نشد. در «تنظیمات» مدل این کار را به Claude برگردان یا Codex را نصب کن."
    work = tempfile.mkdtemp(prefix="studio-codex-")
    out = os.path.join(work, "reply.txt")
    # مقدارهای -c بی‌گیومه‌اند: Codex اگر مقدار TOML معتبر نباشد همان رشته را برمی‌دارد، و گیومه از codex.cmd
    # روی ویندوز سالم رد نمی‌شود
    cmd = [b, "exec", "-m", model, "-c", f"model_reasoning_effort={EFFORT}",
           "-s", "read-only", "--ephemeral", "--skip-git-repo-check", "--ignore-user-config", "--ignore-rules",
           "-c", f"web_search={'live' if web else 'disabled'}"]
    if sys.platform == "win32":
        cmd += ["-c", "windows.sandbox=elevated"]
    for f in DISABLED:
        cmd += ["--disable", f]
    cmd += ["-C", work, "-o", out, "-"]
    try:
        r = subprocess.run(cmd, input=prompt, cwd=work, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout)
        try:
            # Astra کلمه‌های لاتین را لای نشانه‌های نامرئی جهت (U+2066..U+2069) می‌گذارد؛ در کپشن و متن ضبط دردسرند
            text = re.sub(r"[\u2066-\u2069]", "", Path(out).read_text(encoding="utf-8")).strip()
        except Exception:
            text = ""
        err = (r.stderr or r.stdout or "")[-400:] if (r.returncode or not text) else ""
        return r.returncode, text, err
    except subprocess.TimeoutExpired:
        return 1, "", "زمان اجرای Codex تمام شد."
    finally:
        shutil.rmtree(work, ignore_errors=True)
