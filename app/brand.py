"""هسته‌ی برند — پرسش‌نامه‌ای که brand/brand-core.md را برای ایجنت‌ها می‌سازد.

پاسخ‌ها در brand/brand-core.json هستند (منبع اصلی). هر ذخیره brand-core.md را از
نو می‌سازد و ایجنت‌ها فقط همان را می‌خوانند. سؤال‌ها در brand_schema.py هستند؛
سؤال تازه = یک دیکشنری تازه در آنجا، بدون تغییر در جای دیگر.

بعد از تغییر schema، md را بدون باز کردن استودیو از نو بساز:
    python3 app/brand.py
"""
import base64, json, os, re, threading, time
from pathlib import Path

from brand_schema import SCHEMA

ROOT = Path(__file__).resolve().parent.parent
BRAND = ROOT / "brand"
DATA_F = BRAND / "brand-core.json"
MD_F = BRAND / "brand-core.md"
ASSETS = BRAND / "assets"                 # تصویرهای لوگو و نمونه‌ها
IMG_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp",
             ".gif": "image/gif", ".svg": "image/svg+xml"}
ROLE_ORDER = {"اصلی": 0, "فرعی": 1, "تأکیدی": 2}
LOCK = threading.Lock()
DEFAULT_PILLARS = ["آموزشی", "تجربه و داستان", "دیدگاه و تحلیل", "پشت‌صحنه"]   # تا وقتی کاربر پیلرهای خودش را ننوشته
FA = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


MONTHS = ["ژانویه", "فوریه", "مارس", "آوریل", "مه", "ژوئن", "ژوئیه", "اوت", "سپتامبر", "اکتبر", "نوامبر", "دسامبر"]


def fa(n):
    return str(n).translate(FA)


def fa_date(s):
    """'2026-10-04' یا '2026-10-04 15:36' ← «۴ اکتبر ۲۰۲۶» (و ساعت، اگر بود)."""
    try:
        y, m, d = s[:10].split("-")
        out = f"{int(d)} {MONTHS[int(m) - 1]} {y}"
    except Exception:
        return fa(s or "—")
    return fa(out + (f"، ساعت {s[11:16]}" if len(s) >= 16 else ""))


def all_fields():
    return [f for s in SCHEMA for f in s["fields"]]


_ids = [f["id"] for f in all_fields()]
assert len(_ids) == len(set(_ids)), f"duplicate field ids: {sorted({i for i in _ids if _ids.count(i) > 1})}"


def load():
    try:
        d = json.loads(DATA_F.read_text(encoding="utf-8"))
        if isinstance(d, dict) and isinstance(d.get("fields"), dict):
            return d
    except Exception:
        pass
    return {"version": 1, "updated": None, "fields": {}}


def filled(f, v):
    t = f["type"]
    if v is None:
        return False
    if t == "list":
        return isinstance(v, list) and any(str(x).strip() for x in v)
    if t in ("group", "palette", "images"):
        return isinstance(v, list) and any(
            isinstance(it, dict) and any(str(x or "").strip() for k, x in it.items() if k != "bg") for it in v)
    if t == "scales":
        return isinstance(v, dict) and any(v.values())
    return isinstance(v, str) and v.strip() != ""


def clean(fields):
    """ورودی مرورگر را با schema تطبیق می‌دهد. شناسه‌های ناشناخته دست‌نخورده می‌مانند
    تا اگر سؤالی بعداً تغییر نام داد، جوابش گم نشود."""
    known = {f["id"]: f for f in all_fields()}
    out = {}
    for fid, e in fields.items():
        if not isinstance(e, dict):
            continue
        f = known.get(fid)
        if f is None:
            out[fid] = e
            continue
        v, t = e.get("v"), f["type"]
        if t in ("text", "para"):
            v = v[:20000] if isinstance(v, str) else ""
        elif t == "list":
            v = [str(x)[:4000] for x in v if isinstance(x, (str, int, float))] if isinstance(v, list) else []
        elif t == "group":
            keys = [s["id"] for s in f["item"]]
            v = [{k: str(it.get(k) or "")[:8000] for k in keys}
                 for it in v if isinstance(it, dict)] if isinstance(v, list) else []
        elif t == "palette":
            v = [{"hex": str(it.get("hex") or "").strip()[:20], "name": str(it.get("name") or "")[:200],
                  "role": str(it.get("role") or "")[:40], "use": str(it.get("use") or "")[:500]}
                 for it in v if isinstance(it, dict)] if isinstance(v, list) else []
        elif t == "images":
            v = [{"file": n, "caption": str(it.get("caption") or "")[:300],
                  "bg": "dark" if it.get("bg") == "dark" else "light"}
                 for it in v if isinstance(it, dict) and (n := asset_name(it.get("file")))] if isinstance(v, list) else []
        elif t == "scales":
            ids = {s["id"] for s in f["scales"]}
            v = {k: x for k, x in v.items()
                 if k in ids and type(x) is int and 1 <= x <= 5} if isinstance(v, dict) else {}
        entry = {"v": v}
        for k in ("src", "note"):            # برچسب پیش‌نویس؛ با اولین ویرایش کاربر حذف می‌شود
            if isinstance(e.get(k), str) and e[k].strip():
                entry[k] = e[k][:1000]
        if isinstance(e.get("at"), str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", e["at"]):
            entry["at"] = e["at"]            # روز آخرین تغییر این جواب
        out[fid] = entry
    return out


# ---------------- ساخت متن ایجنت‌ها ----------------
def _one(s):
    return " ".join(str(s).split())


def scale_word(s, n):
    return {1: f"کاملاً {s['a']}", 2: f"بیشتر {s['a']}", 3: "میانه",
            4: f"بیشتر {s['b']}", 5: f"کاملاً {s['b']}"}[n]


def _render_field(f, v):
    head, t = f"**{f['label']}:**", f["type"]
    if f.get("md_note"):
        head = f"**{f['label']}** ({f['md_note']}):"
    if t == "text":
        return f"{head} {_one(v)}"
    if t == "para":
        v = v.strip()
        return f"{head}\n{v}" if "\n" in v else f"{head} {v}"
    if t == "list":
        return head + "\n" + "\n".join(f"- {_one(x)}" for x in v if str(x).strip())
    if t == "scales":
        return head + "\n" + "\n".join(
            f"- {s['a']} ↔ {s['b']}: {scale_word(s, v[s['id']])}" for s in f["scales"] if v.get(s["id"]))
    if t == "palette":
        rows = []
        for c in sorted(v, key=lambda c: ROLE_ORDER.get(c.get("role"), 3)):
            hexv, name = _one(c.get("hex") or ""), _one(c.get("name") or "")
            if not (hexv or name):
                continue
            parts = [p for p in (hexv, f"نقش: {c['role']}" if c.get("role") else "",
                                 f"کجا: {_one(c['use'])}" if str(c.get("use") or "").strip() else "") if p]
            rows.append(f"- **{name or hexv}** — " + " · ".join(parts))
        return head + "\n" + "\n".join(rows)
    if t == "images":
        return head + "\n" + "\n".join(
            f"- {_one(it.get('caption') or '') or 'بدون توضیح'}: `brand/assets/{it['file']}`" for it in v)
    rows = []                                   # group
    first, rest = f["item"][0], f["item"][1:]
    for it in v:
        if not any(str(x or "").strip() for x in it.values()):
            continue
        title = _one(it.get(first["id"]) or "")
        parts = [f"{s['label']}: {_one(it[s['id']])}" for s in rest if str(it.get(s["id"]) or "").strip()]
        line = f"**{title}**" if title else ""
        if parts:
            line += (" — " if line else "") + " · ".join(parts)
        rows.append(f"- {line}")
    return head + "\n" + "\n".join(rows)


def render(d):
    fields = d.get("fields", {})
    val = lambda f: (fields.get(f["id"]) or {}).get("v")
    every = all_fields()
    done = sum(1 for f in every if filled(f, val(f)))
    out = [
        "# هسته‌ی برند",
        "",
        "> این فایل خودکار از پرسش‌نامه‌ی «هسته‌ی برند» در Content Studio ساخته می‌شود. دستی ویرایشش نکن:"
        " منبع اصلی `brand/brand-core.json` است و ذخیره‌ی بعدی این فایل را از نو می‌سازد.",
        f"> آخرین به‌روزرسانی: {fa_date(d.get('updated') or '')} · {fa(done)} از {fa(len(every))} سؤال جواب دارد.",
        "",
        "**قانون ایجنت‌ها:** پیش از هر نوشتنی این فایل را کامل بخوان. «خط قرمزها» قانون‌اند، نه سلیقه."
        " هرچه اینجا نیامده — مخصوصاً قیمت، تاریخ، عدد، ادعا و نقل‌قول — را از خودت نساز؛"
        " اگر لازمش داشتی بنویس «در هسته‌ی برند تعریف نشده».",
        "",
    ]
    missing = []
    # بخش‌های md_first (ده قانون طلایی) اول می‌آیند: مدل‌ها ابتدای متن بلند را بهتر به کار می‌برند
    order = [s for s in SCHEMA if s.get("md_first")] + [s for s in SCHEMA if not s.get("md_first")]
    n = 0
    for s in order:
        body = []
        for f in s["fields"]:
            v = val(f)
            if filled(f, v):
                body.append(_render_field(f, v))
            else:
                missing.append((s, f))
        if not s.get("md_first"):
            n += 1
        if body:
            title = s["title"] if s.get("md_first") else f"{fa(n)}. {s['title']}"
            out += ["---", "", f"## {title}", ""]
            dates = [(fields.get(f["id"]) or {}).get("at") for f in s["fields"] if filled(f, val(f))]
            dates = [x for x in dates if x]
            if dates:
                out += [f"*آخرین تغییر این بخش: {fa_date(max(dates))}*", ""]
            for b in body:
                out += [b, ""]
    if missing:
        out += ["---", "", "## سؤال‌های بی‌جواب", "",
                "این‌ها هنوز تعریف نشده‌اند. درباره‌شان حدس نزن و از خودت پرشان نکن.", ""]
        for s in SCHEMA:
            labels = [f["label"] for (ms, f) in missing if ms is s]
            if labels == [s["title"]]:
                out.append(f"- **{s['title']}**")
            elif labels:
                out.append(f"- **{s['title']}:** {'، '.join(labels)}")
        out.append("")
    return "\n".join(out).rstrip() + "\n"


# ---------------- تصویرها ----------------
def asset_name(name):
    """فقط اسم ساده‌ی فایلی که واقعاً در brand/assets هست؛ هر چیز دیگر None."""
    if not isinstance(name, str) or not re.fullmatch(r"[\w.\-]{1,120}", name) or name.startswith("."):
        return None
    return name if (ASSETS / name).is_file() and Path(name).suffix.lower() in IMG_TYPES else None


def save_asset(filename, data_url):
    ext = Path(str(filename or "")).suffix.lower()
    if ext not in IMG_TYPES:
        return False, {"error": "فقط تصویر قبول می‌شود (png، jpg، webp، gif یا svg)."}
    try:
        blob = base64.b64decode(str(data_url or "").split(",")[-1])
    except Exception:
        return False, {"error": "فایل خوانده نشد."}
    if not blob or len(blob) > 15 * 1024 * 1024:
        return False, {"error": "فایل خالی است یا از ۱۵ مگابایت بزرگ‌تر است."}
    stem = re.sub(r"[^\w\-]", "_", Path(str(filename)).stem)[:40].strip("_") or "image"
    name = f"{int(time.time() * 1000)}-{stem}{ext}"
    ASSETS.mkdir(parents=True, exist_ok=True)
    (ASSETS / name).write_bytes(blob)
    return True, {"ok": True, "file": name}


def delete_asset(name):
    n = asset_name(name)
    if not n:
        return False, {"error": "پیدا نشد"}
    (ASSETS / n).unlink()
    return True, {"ok": True}


def read_asset(name):
    n = asset_name(name)
    return ((ASSETS / n).read_bytes(), IMG_TYPES[Path(n).suffix.lower()]) if n else None


# ---------------- API ----------------
def _write(path, text):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def payload():
    d = load()
    md = MD_F.read_text(encoding="utf-8") if MD_F.exists() else render(d)
    return {"schema": SCHEMA, "fields": d["fields"], "updated": d.get("updated"), "md": md}


def save(fields, changed=None):
    """changed = شناسه‌ی سؤال‌هایی که همین صفحه عوض کرده. بقیه از نسخه‌ی روی دیسک می‌آیند،
    تا یک تب کهنه یا اسکریپتی که هم‌زمان نوشته، جواب‌های تازه‌تر را پاک نکند."""
    if not isinstance(fields, dict):
        return False, {"error": "bad payload"}
    with LOCK:
        if isinstance(changed, list):
            merged = dict(load()["fields"])
            for fid in changed:
                if isinstance(fid, str):
                    if fid in fields:
                        merged[fid] = fields[fid]
                    else:
                        merged.pop(fid, None)
            fields = merged
        d = {"version": 1, "updated": time.strftime("%Y-%m-%d %H:%M"), "fields": clean(fields)}
        BRAND.mkdir(exist_ok=True)
        _write(DATA_F, json.dumps(d, ensure_ascii=False, indent=2))
        md = render(d)
        _write(MD_F, md)
    return True, {"ok": True, "updated": d["updated"], "md": md, "fields": d["fields"]}


def pillar_names():
    """نام پیلرها برای منوی بانک ایده؛ اگر هسته‌ی برند پیلری نداشت، پیش‌فرض."""
    v = (load()["fields"].get("pillars") or {}).get("v") or []
    names = [str(it.get("name") or "").strip() for it in v if isinstance(it, dict)]
    return [n for n in names if n] or DEFAULT_PILLARS


if __name__ == "__main__":
    with LOCK:
        _write(MD_F, render(load()))
    print(f"✓ {MD_F.relative_to(ROOT)} از نو ساخته شد")
