"""کتابخانه‌ی افکت صوتی استودیو: بریدن سکوت اول و آخر، ۴۸ کیلوهرتز استریو، محاسبه‌ی لحظه‌ی ضربه (hit) و بهره‌ی هم‌بلندی (gain).
اجرا: اسکریپت «نصب تدوین ویدیو» خودش یک بار اجرایش می‌کند (python3 modules/video/sfx/build_lib.py).
صداها همراه ریپو نیستند (مجوزشان پخش جداگانه‌ی خود فایل را اجازه نمی‌دهد)؛ اصل صداهای Mixkit (mk/<شناسه>.mp3) از
assets.mixkit.co دانلود می‌شوند. صداهای Pixabay فقط اگر در مسیر MU باشند استفاده می‌شوند و در غیر این صورت رد می‌شوند.
بعد از اجرا، manifest.json و CREDITS.md و MP3ها همین‌جا بازنویسی می‌شوند؛ سرور با تغییر manifest خودش دوباره می‌خواند."""
import json, subprocess, sys, os, urllib.request
HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
from analyze import analyze
MU = os.path.expanduser("~/.claude/skills/media-use/audio/assets/sfx")
OUT = sys.argv[1] if len(sys.argv) > 1 else HERE
TARGET = -19.0          # بلندی اوج (RMS پنجره‌ی ۵۰ میلی‌ثانیه) در سطح «معمولی»، زیر صدای گوینده (−14 LUFS)
PX = ("Pixabay (media-use skill)", "Pixabay Content License")
MX = ("Mixkit", "Mixkit Sound Effects Free License")
#   کلید, منبع, اسم فارسی, دسته, حداکثر طول, تنظیم دسته (dB), (سازنده, مجوز), عنوان اصلی
LIB = [
  ("whoosh",      f"{MU}/whoosh.mp3",        "ووش کوتاه",      "whoosh",   0.6, 0,  PX, "whoosh"),
  ("sweep",       "mk/166.mp3",              "جاروی سریع",     "whoosh",   0.8, 0,  MX, "Fast small sweep transition"),
  ("swipe",       "mk/2627.mp3",             "سوایپ",          "whoosh",   0.8, 0,  MX, "Fast swipe zoom"),
  ("whoosh-air",  "mk/1489.mp3",             "ووش نرم",        "whoosh",   1.6, -1, MX, "Air woosh"),
  ("page",        "mk/1104.mp3",             "ورق زدن",        "whoosh",   0.5, 2,  MX, "Page turn single"),
  ("pop",         f"{MU}/pop.mp3",           "پاپ",            "pop",      0.5, -1, PX, "pop"),
  ("pop-soft",    "mk/2356.mp3",             "پاپ نرم",        "pop",      0.35, -1, MX, "Dry pop up notification alert"),
  ("bubble",      "mk/2357.mp3",             "حباب",           "pop",      0.4, -1, MX, "Bubble pop up alert notification"),
  ("pop-light",   "mk/3005.mp3",             "پاپ سبک",        "pop",      0.25, -1, MX, "Explainer video pops whoosh light pop"),
  ("ding",        "mk/2870.mp3",             "دینگ",           "ding",     1.0, -1, MX, "Correct answer tone"),
  ("chime",       f"{MU}/chime.mp3",         "زنگ ملایم",      "ding",     2.2, 0, PX, "chime"),
  ("ping",        f"{MU}/ping.mp3",          "پینگ",           "ding",     1.0, 0, PX, "ping"),
  ("success",     "mk/2865.mp3",             "موفقیت",         "ding",     1.4, -1, MX, "Success software tone"),
  ("coins",       "mk/1993.mp3",             "جرینگ سکه",      "money",    0.9, -2,  MX, "Clinking coins"),
  ("coins-hand",  "mk/1939.mp3",             "سکه در دست",     "money",    0.6, -1,  MX, "Coins handling"),
  ("coin-win",    "mk/1992.mp3",             "سکه‌ی برنده",     "money",    1.5, -3, MX, "Coin win notification"),
  ("coin",        "mk/2003.mp3",             "یک سکه",         "money",    0.5, 0,  MX, "Coins sound"),
  ("notification", f"{MU}/notification.mp3", "اعلان",          "notify",   1.6, -2, PX, "notification"),
  ("message",     "mk/2354.mp3",             "پیام",           "notify",   0.3, -1, MX, "Message pop alert"),
  ("click",       f"{MU}/click.mp3",         "کلیک",           "click",    0.25, 1, PX, "click"),
  ("select",      "mk/1109.mp3",             "انتخاب",         "click",    0.35, -2, MX, "Select click"),
  ("key",         f"{MU}/key-press.mp3",     "کلید",           "click",    0.25, 0,  PX, "key-press"),
  ("typing",      f"{MU}/typing.mp3",        "تایپ",           "typing",   1.5, -2, PX, "typing"),
  ("remove",      "mk/2576.mp3",             "حذف",            "negative", 1.6, -1, MX, "Software interface remove"),
  ("crumple",     "mk/2996.mp3",             "مچاله کردن کاغذ", "negative", 0.85, -1, MX, "Quick paper crumple sound"),
  ("wrong",       "mk/946.mp3",              "جواب غلط",       "negative", 1.6, -2, MX, "Wrong answer fail notification"),
  ("impact",      f"{MU}/impact-bass-1.mp3", "ضربه‌ی بم",       "impact",   2.1, -3, PX, "impact-bass-1"),
  ("sparkle",     f"{MU}/sparkle.mp3",       "درخشش",          "sparkle",  1.4, -2, PX, "sparkle"),
  ("shutter",     "mk/1133.mp3",             "شاتر دوربین",    "shutter",  0.35, 0,  MX, "Camera shutter click"),
  ("shutter-digital", "mk/1432.mp3",         "شاتر دیجیتال",   "shutter",  0.45, -1, MX, "Camera digital shutter"),
  ("marker",      "mk/2998.mp3",             "ماژیک",          "marker",   0.5, 1,  MX, "Pen marker line"),
  ("scribble",    "mk/2369.mp3",             "خط‌خطی روی کاغذ",  "marker",   0.7, 0,  MX, "Writing scribble on paper"),
]
CATS = {
  "whoosh":   ["ووش (مورد یا بخش بعدی)", "whoosh"],
  "money":    ["پول (قیمت، هزینه، صرفه‌جویی)", "coins"],
  "pop":      ["پاپ (تأکید، ظاهر شدن)", "pop"],
  "ding":     ["دینگ (نکته‌ی اصلی، نتیجه)", "ding"],
  "notify":   ["اعلان (پیام، دایرکت)", "notification"],
  "click":    ["کلیک (دکمه، انتخاب، میانبر)", "click"],
  "typing":   ["تایپ", "typing"],
  "negative": ["منفی (کنسل، حذف، اشتباه)", "remove"],
  "impact":   ["ضربه (عدد یا نتیجه‌ی بزرگ)", "impact"],
  "sparkle":  ["درخشش (جادوی AI، نتیجه‌ی عالی)", "sparkle"],
  "shutter":  ["عکس (برای عکس‌ها، فاز ۳)", "shutter"],
  "marker":   ["ماژیک (برای هایلایت، فاز ۴)", "marker"],
}
os.makedirs(OUT, exist_ok=True)
sounds, credits = {}, []
for key, src, fa, cat, maxlen, adj, (who, lic), title in LIB:
    if src.startswith("mk/") and not os.path.exists(src):
        os.makedirs("mk", exist_ok=True)
        sid = src[3:-4]
        req = urllib.request.Request(f"https://assets.mixkit.co/active_storage/sfx/{sid}/{sid}-preview.mp3",
                                     headers={"User-Agent": "Mozilla/5.0 (Macintosh)"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r, open(src, "wb") as f:
                f.write(r.read())
        except Exception as e:
            print(f"{key:16s} دانلود نشد ({e}); رد شد")
            continue
    if not os.path.exists(src):
        print(f"{key:16s} فایلش نیست؛ رد شد")
        continue
    a = analyze(src)
    lead = max(0.0, min(a["onset"], a["hit"]) - 0.02)
    length = min(maxlen, max(a["end"] + 0.12, a["hit"] + 0.1) - lead)
    fade = min(0.12, length / 4)
    dst = os.path.join(OUT, key + ".mp3")
    # بدون -ss پیش از ورودی: جست‌وجو در MP3 قاب اول را (بدون مخزن بیت) خراب می‌کند و ضربه‌ی کوتاه گم می‌شود
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", src,
                    "-af", f"asetpts=PTS-STARTPTS,atrim=start={lead:.3f}:duration={length:.3f},asetpts=PTS-STARTPTS,"
                           f"aresample=48000,aformat=channel_layouts=stereo,afade=t=out:st={max(0, length - fade):.3f}:d={fade:.3f}",
                    "-c:a", "libmp3lame", "-b:a", "192k", dst], check=True)
    b = analyze(dst)
    gain = round(min(TARGET + adj - b["peakRms"], -3.0 - b["samplePk"]), 1)     # سقف: اوج نمونه زیر −3 dBFS
    sounds[key] = {"file": key + ".mp3", "fa": fa, "cat": cat, "dur": b["dur"], "hit": round(max(0.0, a["hit"] - lead), 3),
                   "gain": gain, "by": who, "license": lic, "title": title}
    credits.append(f"| `{key}.mp3` | {fa} | {title} | {who} | {lic} |")
    print(f"{key:16s} lead {lead:4.2f} len {length:4.2f} hit {sounds[key]['hit']:4.2f} peakRms {b['peakRms']:6.1f} spk {b['samplePk']:5.1f} gain {gain:5.1f}")
# دسته‌ای که هیچ صدایی ندارد کنار می‌رود؛ اگر صدای پیش‌فرض دسته نبود، اولین صدای موجود همان دسته
cats = {}
for k, v in CATS.items():
    have = [s for s, x in sounds.items() if x["cat"] == k]
    if have:
        cats[k] = {"fa": v[0], "default": v[1] if v[1] in sounds else have[0]}
man = {"version": 1, "target": TARGET, "cats": cats, "sounds": sounds}
json.dump(man, open(os.path.join(OUT, "manifest.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
open(os.path.join(OUT, "CREDITS.md"), "w", encoding="utf-8").write(
"""# افکت‌های صوتی تدوین ویدیو

همه‌ی فایل‌ها رایگان و برای استفاده‌ی تجاری در ویدیو آزادند؛ ذکر منبع لازم نیست:
- **Pixabay Content License** (https://pixabay.com/service/license-summary/): همان ۱۹ صدای اسکیل media-use.
- **Mixkit Sound Effects Free License** (https://mixkit.co/license/#sfxFree): استفاده در ریلز، یوتیوب، تبلیغ و پروژه‌ی تجاری آزاد است؛ فقط خود فایل را نمی‌شود جدا فروخت یا پخش کرد.

فایل‌ها با `build_lib.py` بریده (سکوت اول و آخر)، ۴۸ کیلوهرتز استریو و MP3 شده‌اند. `manifest.json` برای هر صدا این‌ها را دارد:
- `hit`: لحظه‌ی ضربه از شروع فایل؛ این لحظه روی شروع کلمه می‌نشیند.
- `gain`: بهره (dB) تا همه‌ی صداها در سطح «معمولی» هم‌بلند باشند (اوج حدود −19 dBFS، زیر صدای گوینده).

| فایل | اسم | عنوان اصلی | منبع | مجوز |
|---|---|---|---|---|
""" + "\n".join(credits) + "\n")
print(len(sounds), "sounds")
