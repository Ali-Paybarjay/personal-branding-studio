#!/usr/bin/env python3
"""استخراج ترنسکریپت یوتیوب با تایم‌کد (مک و ویندوز).

استفاده:  python3 get_transcript.py <YOUTUBE_URL> [OUTPUT_DIR]
خروجی:   پیشرفت روی stderr؛ آخرین خط stdout مسیر پوشه‌ی خروجی است.
در پوشه: 00-transcript-raw.txt (بلوک‌های ۳۰ ثانیه‌ای) و video-info.md.
"""
import glob, os, re, shutil, subprocess, sys, unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent


def say(msg):
    print(msg, file=sys.stderr, flush=True)


def die(msg):
    say("خطا: " + msg)
    sys.exit(1)


def ytdlp(*args, timeout=180):
    exe = shutil.which("yt-dlp")
    if not exe:
        die("yt-dlp نصب نیست. اسکریپت نصب استودیو را دوباره اجرا کن.")
    r = subprocess.run([exe, "--socket-timeout", "30", "--no-warnings", *args],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    return r


def slugify(title, vid):
    t = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    s = re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", t.lower())).strip("-")[:50]
    return s or vid


def list_langs(text):
    """(دستی، خودکار) از خروجی --list-subs؛ ترتیب این دو بخش در خروجی yt-dlp ثابت نیست."""
    manual, auto, sec = [], [], None
    for line in text.splitlines():
        if "Available subtitles" in line:
            sec = manual; continue
        if "Available automatic captions" in line:
            sec = auto; continue
        if line.startswith("[") or not line.strip():
            continue
        first = line.split()[0]
        if sec is not None and first != "Language":
            sec.append(first)
    return manual, auto


def pick(manual, auto):
    # انگلیسی بر هر زبان دیگری مقدم است: زیرنویس دستی عربیِ یک تدتاک خودش ترجمه است، نه حرف گوینده
    for l in manual:
        if re.fullmatch(r"en|en-(US|GB|CA|AU)", l):
            return l, "دستی (انسانی)", "--write-subs"
    for l in manual:
        if re.match(r"^en(-|$)", l):
            return l, "دستی (انسانی)", "--write-subs"
    if "en-orig" in auto:
        return "en-orig", "خودکار (ماشینی)", "--write-auto-subs"
    if "en" in auto:
        return "en", "خودکار (ماشینی)", "--write-auto-subs"
    if manual:
        return manual[0], "دستی (انسانی) — انگلیسی نبود", "--write-subs"
    if auto:
        return auto[0], "خودکار (ماشینی)", "--write-auto-subs"
    return None, None, None


def srt_to_blocks(src, dst):
    cues = []
    for b in Path(src).read_text(encoding="utf-8", errors="replace").strip().split("\n\n"):
        lines = b.strip().split("\n")
        if len(lines) < 3 or "-->" not in lines[1]:
            continue
        h, m, s = lines[1].split(" --> ")[0].split(":")
        sec = int(h) * 3600 + int(m) * 60 + float(s.replace(",", "."))
        txt = re.sub(r"<[^>]+>", "", " ".join(lines[2:]).strip())
        if txt:
            cues.append((sec, txt))
    if not cues:
        die("زیرنویس خالی بود.")

    # زیرنویس «غلتان» هر جمله را ۲-۳ بار تکرار می‌کند؛ هر کیو فقط به اندازه‌ی بخش تازه‌اش اضافه می‌شود.
    def append_new(acc, txt):
        w = txt.split()
        for n in range(min(len(acc), len(w)), 0, -1):
            if acc[-n:] == w[:n]:
                acc.extend(w[n:]); return
        acc.extend(w)

    fmt = lambda s: f"{int(s) // 60:02d}:{int(s) % 60:02d}"
    out, cur, start = [], [], cues[0][0]
    for sec, txt in cues:
        if sec - start >= 30 and cur:
            out.append(f"[{fmt(start)}] " + " ".join(cur))
            cur, start = [], sec
        append_new(cur, txt)
    if cur:
        out.append(f"[{fmt(start)}] " + " ".join(cur))
    res = "\n\n".join(out)
    Path(dst).write_text(res, encoding="utf-8")
    say(f"▸ {len(cues)} کیو → {len(out)} بلوک → {len(res.split())} کلمه")


def main():
    if len(sys.argv) < 2 or not sys.argv[1].strip():
        die("لینک یوتیوب را بده.")
    url = sys.argv[1].strip()

    say("▸ در حال گرفتن اطلاعات ویدیو…")
    r = ytdlp("--skip-download", "--print", "%(title)s", "--print", "%(channel)s",
              "--print", "%(duration_string)s", "--print", "%(upload_date)s", "--print", "%(id)s", url)
    meta = (r.stdout or "").strip().splitlines()[-5:]
    if len(meta) < 5 or not meta[4].strip():
        die("نتوانستم اطلاعات ویدیو را بگیرم. لینک یا اینترنت را چک کن.")
    title, channel, duration, upload, vid = (x.strip() for x in meta)

    out_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else HERE.parent / "output" / slugify(title, vid)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_dir = out_dir.resolve()

    say("▸ در حال بررسی زیرنویس‌ها…")
    subs = ytdlp("--list-subs", url).stdout or ""
    lang, kind, flag = pick(*list_langs(subs))
    if not lang:
        die("این ویدیو هیچ زیرنویسی ندارد.")
    say(f"▸ زیرنویس انتخاب‌شده: {lang} — {kind}")

    ytdlp("--skip-download", flag, "--sub-langs", lang, "--sub-format", "srt/best", "--convert-subs", "srt",
          "-o", str(out_dir / "raw"), url, timeout=300)
    srts = sorted(glob.glob(str(out_dir / "raw*.srt")))
    if not srts:
        die("دانلود زیرنویس شکست خورد. (برای تبدیل زیرنویس، ffmpeg هم باید نصب باشد.)")
    srt_to_blocks(srts[0], out_dir / "00-transcript-raw.txt")
    for f in glob.glob(str(out_dir / "raw*.srt")) + glob.glob(str(out_dir / "raw*.vtt")):
        os.remove(f)

    (out_dir / "video-info.md").write_text(
        f"# {title}\n\n- **کانال:** {channel}\n- **مدت:** {duration}\n- **تاریخ انتشار:** {upload}\n"
        f"- **لینک:** {url}\n- **زیرنویس:** {lang} ({kind})\n", encoding="utf-8")
    say(f"\n✅ آماده شد → {out_dir}\n   عنوان: {title}\n   مدت:   {duration}\n")
    print(out_dir)


if __name__ == "__main__":
    if os.name == "nt":
        sys.stdout.reconfigure(encoding="utf-8"); sys.stderr.reconfigure(encoding="utf-8")
    main()
