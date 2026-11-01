"""تدوین ویدیو — فاز ۵: ضبط صفحه. موتور اصلی video_engine.py، مسیرها video.py.

- زوم هوشمند: هر جا گوینده به جایی از صفحه اشاره می‌کند («اینجا»، «این دکمه»، «سمت چپ»، «روی … بزنید») یا متنی را می‌خواند،
  تصویر روی همان‌جا زوم می‌شود و اگر لازم است زیر همان متن ماژیک می‌خورد. Claude اول از حرف‌ها لحظه‌ها را پیدا می‌کند،
  بعد فریم همان لحظه را با خط‌های متن Vision می‌بیند (stream-json، بدون ابزار) و جای دقیق را با شماره‌ی خط یا جعبه می‌دهد.
- محو اطلاعات حساس: هر ثانیه (ویدیوی بلندتر از ۳ دقیقه هر دو ثانیه) یک فریم OCR می‌شود؛ ایمیل، کلید API و توکن، شماره‌ی کارت
  و تلفن پیدا و در خود ویدیو محو می‌شوند: ffmpeg پیش از برش، با enable زمانی، هم در پیش‌نمایش و هم در رندر.
- خروجی عمودی ۹:۱۶ برای ریلز (opts.vertical): «قاب وسط» (frame؛ زمینه‌ی سرمه‌ای یا محو) یا «تمام‌قد» (follow: کادر عمودی
  روی ضبط که دنبال زوم‌ها می‌رود). در این حالت dv["kind"] (کادر ترکیب) reel است و dv["src_kind"] همچنان screen.

edit.json → zooms  [{id, w0, w1, t, box, z: s|m|l, hl: [[x,y,w,h]], target, why, on, src}]  (box و hl کسری از کادر منبع)
edit.json → blurs  [{id, s, e, box, type, label, on, src}]  (s و e ثانیه‌ی منبع، پیش از برش)
frames/f<ms>.jpg   فریم منبع برای رابط (۱۲۸۰px)
"""
import json, math, re, shutil, tempfile, time
from html import escape
from pathlib import Path
import video_engine as ve
import video_visuals as vv

ZOOM_CAP = {"s": 1.6, "m": 2.2, "l": 3.0}                # بیشترین بزرگ‌نمایی در قاب
ZOOM_FA = {"s": "کم", "m": "معمولی", "l": "زیاد"}
FOLLOW_Z = {"s": 1.0, "m": 1.25, "l": 1.55}              # بزرگ‌نمایی اضافه در چیدمان تمام‌قد
VLAYOUT = {"frame": "قاب وسط", "follow": "تمام‌قد، دنبال زوم"}
VBG = {"brand": "زمینه‌ی سرمه‌ای", "blur": "زمینه‌ی محو"}
BLUR_FA = {"email": "ایمیل", "key": "کلید یا توکن", "card": "شماره‌ی کارت", "phone": "تلفن", "manual": "دستی"}
SENS = [("email", re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")),
        ("key", re.compile(r"\b(?:sk|pk|rk|fc|ghp|gho|ghu|ghs|ghr|github_pat|xox[abprs]|AIza|AKIA|ASIA|hf|glpat|whsec|rk_live|sk_live)"
                           r"[-_]?[A-Za-z0-9_\-]{6,}")),
        ("key", re.compile(r"(?<![\w/.])(?=[A-Za-z0-9_\-]{24,}(?![\w/.]))(?=[A-Za-z_\-]*\d)(?=[\d_\-]*[A-Za-z])[A-Za-z0-9_\-]{24,}")),
        ("key", re.compile(r"\b[A-Za-z0-9]{2,}[-_][A-Za-z0-9]{1,}\s?[•*·.]{4,}\s?[A-Za-z0-9]{0,16}")),   # کلید نیمه‌پنهان «fc-4••••05200c2d» با ته پیدایش
        ("key", re.compile(r"[•*·]{3,}\s?[A-Za-z0-9]{4,16}\b")),                       # فقط ته کلید پیدا: «••••05200c2d»
        ("card", re.compile(r"\b(?:\d[ -]?){13,19}\b")),
        ("phone", re.compile(r"\+\d[\d\s().-]{8,}\d"))]


def is_screen(dv):
    return dv.get("src_kind", dv["kind"]) == "screen"


# ---------------- فریم‌ها ----------------
def frame_rel(t):
    return f"frames/f{int(round(max(0.0, t) * 1000))}.jpg"


def ensure_frame(vid, t):
    f = ve.pdir(vid) / frame_rel(t)
    if not f.exists():
        f.parent.mkdir(parents=True, exist_ok=True)
        ve.run([ve.FFMPEG, "-v", "error", "-y", "-ss", f"{max(0.0, t):.3f}", "-i", ve.pdir(vid) / "master.mp4", "-frames:v", "1",
                "-vf", "scale='min(1280,iw)':-2", "-q:v", "3", f], vid)
    return f


def _ocr_frame(vid, t, td):
    p = Path(td) / f"o{int(t * 1000)}.png"
    ve.run([ve.FFMPEG, "-v", "error", "-y", "-ss", f"{max(0.0, t):.3f}", "-i", ve.pdir(vid) / "master.mp4", "-frames:v", "1", p], vid)
    return vv.mtool("ocr", p, vid=vid, timeout=300)


def _dur(dv):
    info = dv["proj"].get("info") or {}
    return info.get("masterDur") or info.get("dur") or 0


# ---------------- اطلاعات حساس ----------------
def _match_box(ln, a, b):
    """جعبه‌ی بخش [a,b) از متن یک خط OCR: کلمه‌هایی که درون همان بخش‌اند؛ اگر نشد، به نسبت حرف‌ها."""
    t, words = ln["t"], ln.get("w") or []
    seg = re.sub(r"\W+", "", t[a:b].lower())
    hits = [w["b"] for w in words if re.sub(r"\W+", "", w["t"].lower()) and re.sub(r"\W+", "", w["t"].lower()) in seg]
    if hits:
        return vv._union(hits)
    x, y, w, h = ln["b"]
    n = max(1, len(t))
    return [x + w * a / n, y, w * (b - a) / n, h]


def _mask(kind, s):
    s = s.strip()
    if kind == "email" and "@" in s:
        u, d = s.split("@", 1)
        return (u[:2] + "…@" + d)[:40]
    return (s[:4] + "…" + (s[-2:] if len(s) > 10 else ""))[:24]


def scan_sensitive(vid, step=lambda s: None):
    """OCR فریم‌های ضبط → محوهای خودکار (src=auto) در edit.json؛ محوهای دستی کاربر می‌مانند."""
    dv = ve.derive(vid)
    dur = _dur(dv)
    every = 1.0 if dur <= 180 else 2.0
    dets = []
    with tempfile.TemporaryDirectory() as td:
        step("پیدا کردن اطلاعات حساس روی صفحه (ایمیل، کلید API، شماره‌ی کارت)…")
        ve.run([ve.FFMPEG, "-v", "error", "-y", "-i", ve.pdir(vid) / "master.mp4", "-vf", f"fps=1/{every},scale='min(2560,iw)':-2",
                "-q:v", "2", Path(td) / "s%05d.jpg"], vid, timeout=3600)
        files = sorted(Path(td).glob("s*.jpg"))
        for k, f in enumerate(files):
            t = k * every
            if k % 10 == 0:
                step(f"پیدا کردن اطلاعات حساس روی صفحه… ({vv.fa_num(k)} از {vv.fa_num(len(files))} فریم)")
            o = vv.mtool("ocr", f, vid=vid, timeout=300)
            for ln in o.get("lines") or []:
                for kind, rx in SENS:
                    for m in rx.finditer(ln["t"]):
                        txt = m.group(0)
                        if kind == "card" and len(re.sub(r"\D", "", txt)) < 13:
                            continue
                        box = _match_box(ln, m.start(), m.end())
                        if kind == "key":           # نقطه‌های پوشاننده و ته کلید را OCR نمی‌خواند: تا ته همان ردیف (یا متن بعدی) محو
                            cy = box[1] + box[3] / 2
                            right = [q["b"][0] for q in o.get("lines") or []
                                     if abs(q["b"][1] + q["b"][3] / 2 - cy) < box[3] and q["b"][0] > box[0] + box[2] + 0.002
                                     and not re.fullmatch(r"[\s•*·.]*[A-Za-z0-9]{0,16}", q["t"].strip())]    # ته خود کلید نه
                            end = min(right) - 0.006 if right else box[0] + max(0.26, 4 * box[2])
                            box = [box[0], box[1], max(box[2], min(1.0, end) - box[0]), box[3]]
                        dets.append((t, kind, re.sub(r"\W+", "", txt.lower()), box, txt))
    groups = []
    for t, kind, key, box, txt in sorted(dets, key=lambda d: d[0]):
        c = (box[0] + box[2] / 2, box[1] + box[3] / 2)
        g = next((g for g in groups if g["key"] == key and t - g["t1"] <= 2.2 * every
                  and abs(g["c"][0] - c[0]) < 0.06 and abs(g["c"][1] - c[1]) < 0.06), None)
        if g:
            g["t1"], g["c"] = t, c
            g["boxes"].append(box)
        else:
            groups.append({"key": key, "kind": kind, "t0": t, "t1": t, "c": c, "boxes": [box], "txt": txt})
    pad = 0.6 * every + 0.25
    blurs = []
    for k, g in enumerate(groups):
        b = vv._union(g["boxes"])
        x, y, w, h = b
        b = vv._clip([x - 0.004, y - h * 0.35, w + 0.008, h * 1.7])
        blurs.append({"id": f"b{int(time.time())}{k}", "s": round(max(0.0, g["t0"] - pad), 2), "e": round(min(dur, g["t1"] + pad), 2),
                      "box": b, "type": g["kind"], "label": _mask(g["kind"], g["txt"]), "on": True, "src": "auto"})
    for b in blurs:
        ensure_frame(vid, (b["s"] + b["e"]) / 2)
    with ve.plock(vid):
        e = ve.jload(ve.pdir(vid) / "edit.json", {})
        if "blurs" in e:
            e.setdefault("prev", {})["blurs"] = e["blurs"]
        e["blurs"] = [b for b in e.get("blurs") or [] if b.get("src") == "user"] + blurs
        e["blursAt"] = ve.now()
        ve.jsave(ve.pdir(vid) / "edit.json", e)
    return len(blurs)


def active_blurs(dv):
    """(s, e, box) محوهای روشن، برای ffmpeg (زمان منبع)."""
    if not is_screen(dv):
        return []
    return [(b["s"], b["e"], b["box"]) for b in dv["edit"].get("blurs") or []
            if b.get("on") is not False and isinstance(b.get("box"), list) and b.get("e", 0) > b.get("s", 0)]


def blur_graph(blurs, W, H):
    """زنجیره‌ی filter_complex: هر محو یک برش، pixelize و boxblur، با enable زمانی روی همان بخش. خروجی (گراف، برچسب آخر)."""
    n = len(blurs)
    g = f"[0:v]split={n + 1}[b0]" + "".join(f"[c{i}]" for i in range(n)) + ";"
    for i, (s, e, (x, y, w, h)) in enumerate(blurs):
        X, Y = max(0, int(x * W)), max(0, int(y * H))
        BW, BH = max(8, min(W - X, int(math.ceil(w * W)))), max(8, min(H - Y, int(math.ceil(h * H))))
        X, Y, BW, BH = X - X % 2, Y - Y % 2, BW - BW % 2, BH - BH % 2
        blk = max(6, min(48, BH // 2))
        r = max(2, min(BH // 2 - 1, BW // 2 - 1, 20))
        cr = max(0, min(r, BH // 4 - 1, BW // 4 - 1))       # در yuv420p کانال رنگ نصف است؛ شعاعش جدا و کوچک‌تر
        g += (f"[c{i}]crop={BW}:{BH}:{X}:{Y},pixelize=width={blk}:height={blk},boxblur={r}:2:{cr}:1[p{i}];"
              f"[b{i}][p{i}]overlay={X}:{Y}:enable='between(t,{s:.3f},{e:.3f})'[b{i + 1}];")
    return g, f"[b{n}]"


# ---------------- زوم هوشمند ----------------
ZOOM_RULES = """بیننده روی گوشی نگاه می‌کند و جزئیات ریز صفحه را نمی‌بیند. هر جا گوینده به یک جای مشخص صفحه اشاره می‌کند («اینجا»، «این دکمه»، «سمت چپ»، «این فیلد»، «این عدد»، «روی … بزنید») یا کاری روی صفحه می‌کند (کلیک، تایپ، انتخاب، کپی)، تصویر روی همان‌جا زوم می‌شود.
برای هر لحظه:
- w0..w1: کلمه‌هایی که زوم در طولشان می‌ماند (حدود ۱٫۵ تا ۶ ثانیه).
- target: چیزی که باید دیده شود، دقیق و پیداشدنی روی تصویر، مثل «منوی سمت چپ، گزینه‌ی API Keys» یا «دکمه‌ی نارنجی Create Key پایین پنجره» یا «فیلد Key Name». اگر اسم انگلیسی چیزی روی صفحه را می‌دانی یا حدس می‌زنی، بنویس.
- text: اگر گوینده متنی روی صفحه را می‌خواند یا عددی را می‌گوید که روی صفحه است (مثل قیمت)، همان متن کوتاه برای ماژیک؛ وگرنه "".
- z: s برای یک بخش بزرگ (منو، کارت، پنجره)، m برای یک گروه کوچک، l برای یک دکمه یا فیلد یا عدد.
قاعده‌ها: فقط جاهایی که زوم واقعاً کمک می‌کند؛ بین دو زوم دست‌کم ۱ ثانیه؛ به‌طور میانگین حداکثر یکی در هر ۴ ثانیه. هر مورد یک دلیل کوتاه فارسی (why). summary یک جمله‌ی فارسی ساده."""


def zoom_prompt(dv, comment="", current=None):
    words, fix, tm = dv["words"], dv["edit"].get("fix") or {}, dv["tmap"]
    rows = [f"{w['i']}|{ve.disp(words, fix, w['i']).strip()}|{tm.out(w['s']):.1f}" for w in words
            if w["i"] not in dv["cut"] and ve.disp(words, fix, w["i"]).strip()]
    parts = [f"تو تدوینگر آموزش‌های ضبط صفحه‌ی فارسی هستی. ویدیو {tm.dur:.0f} ثانیه است بعد از برش.",
             "کلمه‌های ویدیو بعد از برش. قالب هر خط: اندیس|کلمه|زمان در خروجی (ثانیه):\n<<<WORDS\n" + "\n".join(rows) + "\nWORDS>>>",
             ZOOM_RULES]
    if current:
        parts.append("زوم‌های فعلی (برای بازنویسی):\n" + json.dumps(current, ensure_ascii=False))
    if comment:
        parts.append("نظر کاربر (مهم‌ترین دستور): " + comment)
    parts.append('خروجی فقط یک JSON بین این دو نشانه:\n<<<ZOOM\n{"zooms": [{"w0": 30, "w1": 41, "target": "", "text": "", "z": "m", '
                 '"why": ""}], "summary": ""}\nZOOM>>>')
    return "\n\n".join(parts)


LOC_RULES = """برای هر تصویر بگو هدفی که گوینده به آن اشاره می‌کند دقیقاً کجای تصویر است تا تصویر روی آن زوم شود:
- lines: شماره‌ی خط‌هایی (از فهرست همان تصویر) که خود هدف‌اند، اگر هدف متن دارد (دکمه، منو، فیلد با برچسب).
- box: [x,y,w,h] کسری از عرض و ارتفاع (مبدأ بالا-چپ) اگر هدف متن ندارد یا خط‌ها کافی نیست (آیکن، تصویر، یک ناحیه).
- hl: شماره‌ی خط‌هایی که باید زیرشان ماژیک بخورد (فقط اگر «متن برای ماژیک» داده شده)؛ وگرنه [].
- found: false اگر هدف در این فریم دیده نمی‌شود.
نشانگر موس هم در تصویر هست و معمولاً نزدیک همان چیزی است که گوینده می‌گوید «اینجا»."""


def _locate(vid, cands, step):
    """فریم و OCR هر لحظه → Claude با خود تصویرها (حداکثر ۵ تا در هر بار) جای هدف را می‌دهد."""
    out = {}
    with tempfile.TemporaryDirectory() as td:
        for k, c in enumerate(cands):
            c["ocr"] = _ocr_frame(vid, c["t"], td)
            c["img"] = ensure_frame(vid, c["t"])
        for b0 in range(0, len(cands), 5):
            batch = cands[b0:b0 + 5]
            step(f"Claude دارد جای هر زوم را روی تصویر پیدا می‌کند… ({b0 + len(batch)} از {len(cands)})")
            parts = ["تو دستیار تدوین آموزش‌های ضبط صفحه هستی. تصویرها به همین ترتیب IMG0، IMG1، … هستند.", LOC_RULES]
            for k, c in enumerate(batch):
                lines = [ln for ln in (c["ocr"].get("lines") or []) if len(ln["t"].strip()) >= 1][:160]
                c["lines"] = lines
                rows = "\n".join(f"L{i}|{ln['t'][:80]}|{','.join(f'{v:.3f}' for v in ln['b'])}" for i, ln in enumerate(lines))
                parts.append(f"IMG{k}: گوینده می‌گوید: «{c['say']}»\nهدف: «{c['target']}»\nمتن برای ماژیک: «{c.get('text') or '—'}»\n"
                             f"خط‌های متن Vision در این فریم:\n{rows or '(متنی نیست)'}")
            parts.append('خروجی فقط یک JSON بین این دو نشانه:\n<<<BOX\n{"items": [{"k": 0, "found": true, "lines": [3], "box": null, "hl": []}]}\nBOX>>>')
            res = vv.ask_vision("\n\n".join(parts), [c["img"] for c in batch], vid, timeout=900, effort="medium")
            data = ve.json_block(res, "<<<BOX", "BOX>>>") or {}
            for it in data.get("items") or []:
                try:
                    k = int(it.get("k"))
                except Exception:
                    continue
                if 0 <= k < len(batch) and it.get("found") is not False:
                    out[b0 + k] = it
    return out


def _zoom_box(c, it):
    lines = c.get("lines") or []
    pick = [lines[i]["b"] for i in it.get("lines") or [] if isinstance(i, int) and 0 <= i < len(lines)]
    box = vv._union(pick) if pick else (vv._clip(it["box"]) if isinstance(it.get("box"), list) and len(it["box"]) == 4 else None)
    if not box or box[2] <= 0 or box[3] <= 0:
        return None, []
    x, y, w, h = box                                  # کمی زمینه دور هدف؛ حداقل اندازه تا زوم بیش از حد نشود
    w2, h2 = max(w * 1.5, 0.2), max(h * 1.8, 0.14)
    box = vv._clip([x + w / 2 - w2 / 2, y + h / 2 - h2 / 2, w2, h2])
    hl = [vv._clip([b[0] - 0.003, b[1] - b[3] * 0.25, b[2] + 0.006, b[3] * 1.5])
          for b in (lines[i]["b"] for i in it.get("hl") or [] if isinstance(i, int) and 0 <= i < len(lines))][:6]
    return box, hl


def find_zooms(vid, comment="", step=lambda s: None):
    dv = ve.derive(vid)
    if not is_screen(dv):
        return 0
    words, tm = dv["words"], dv["tmap"]
    zooms, summary = [], "حرفی در این ویدیو نیست."
    if any(w["i"] not in dv["cut"] for w in words):
        step("Claude دارد جاهایی را که به صفحه اشاره می‌کنی پیدا می‌کند…")
        cur = [{k: z.get(k) for k in ("w0", "w1", "target", "z")} for z in dv["edit"].get("zooms") or [] if z.get("src") != "user"]
        res = ve.ask(zoom_prompt(dv, comment, cur if comment else None), vid, timeout=900, effort="medium")
        data = ve.json_block(res, "<<<ZOOM", "ZOOM>>>")
        if not data:
            (ve.pdir(vid) / "zoom.last-output.txt").write_text(res or "", encoding="utf-8")
            raise RuntimeError("جواب Claude برای زوم‌ها قابل خواندن نبود.")
        summary = str(data.get("summary") or "")[:400]
        cands = []
        for x in (data.get("zooms") or [])[:40]:
            try:
                w0, w1 = int(x.get("w0")), int(x.get("w1"))
            except Exception:
                continue
            span = vv._kept_span(max(0, min(w0, w1)), min(len(words) - 1, max(w0, w1)), dv)
            if not span:
                continue
            a, b = words[span[0]]["s"], words[span[1]]["e"]
            say = " ".join(ve.disp(words, dv["edit"].get("fix") or {}, i) for i in range(span[0], span[1] + 1)
                           if i not in dv["cut"])[:200]
            cands.append({"w0": span[0], "w1": span[1], "t": round(min(b, a + 0.7), 3), "target": str(x.get("target") or "")[:200],
                          "text": str(x.get("text") or "")[:120], "z": x.get("z") if x.get("z") in ZOOM_CAP else "m",
                          "why": str(x.get("why") or "")[:200], "say": say, "_o": tm.out(a)})
        cands.sort(key=lambda c: c["_o"])
        keep = []
        for c in cands:                                # بین دو زوم دست‌کم ۱ ثانیه
            if keep and c["_o"] < tm.out(words[keep[-1]["w1"]]["e"]) + 1.0:
                continue
            keep.append(c)
        locs = _locate(vid, keep, step) if keep else {}
        for k, c in enumerate(keep):
            if k not in locs:
                continue
            box, hl = _zoom_box(c, locs[k])
            if box:
                zooms.append({"id": f"z{int(time.time())}{k}", "w0": c["w0"], "w1": c["w1"], "t": c["t"], "box": box, "z": c["z"], "hl": hl,
                              "target": c["target"], "why": c["why"], "on": True, "src": "claude"})
    with ve.plock(vid):
        e = ve.jload(ve.pdir(vid) / "edit.json", {})
        if "zooms" in e:
            e.setdefault("prev", {})["zooms"] = e["zooms"]
        e["zooms"] = sorted([z for z in e.get("zooms") or [] if z.get("src") == "user"] + zooms, key=lambda z: z["w0"])
        e["zoomSummary"], e["zoomsAt"] = summary, ve.now()
        if comment:
            e.setdefault("notes", {}).setdefault("zooms", []).append(comment[:500])
        ve.jsave(ve.pdir(vid) / "edit.json", e)
    return len(zooms)


def analyze(vid, step=lambda s: None):
    """مرحله‌ی screen در «ساخت کامل»: اطلاعات حساس، بعد زوم‌ها. برای ریلز کاری نمی‌کند."""
    p = ve.jload(ve.pdir(vid) / "project.json", {})
    if p.get("kind") != "screen":
        return
    scan_sensitive(vid, step)
    find_zooms(vid, step=step)


def resolve_zooms(dv):
    """زوم‌ها روی زمان خروجی: s، e. کلمه‌ی بریده‌شده → اولین و آخرین کلمه‌ی نبریده‌ی بازه؛ همه بریده → skip."""
    out, tm, ws = [], dv["tmap"], dv["words"]
    for z in dv["edit"].get("zooms") or []:
        c = dict(z, skip=None)
        span = vv._kept_span(int(z.get("w0", 0)), int(z.get("w1", 0)), dv) if isinstance(z.get("w0"), int) else None
        if not span or not isinstance(z.get("box"), list):
            c["skip"] = "cut"
        else:
            s, e = tm.out(ws[span[0]]["s"]), tm.out(ws[span[1]]["e"])
            c["s"], c["e"] = round(max(0.0, s - 0.1), 3), round(min(tm.dur, max(e + 0.3, s + 1.2)), 3)
        out.append(c)
    return sorted(out, key=lambda c: c.get("s", 1e9))


# ---------------- ترکیب: صحنه‌ی ضبط صفحه ----------------
def _bg_blur(vid, dv, assets, W, H):
    """زمینه‌ی محو چیدمان عمودی: یک فریم ثابت از یک‌سوم ویدیو، بزرگ و محو (ارزان‌تر از ویدیوی دوم)."""
    dst = assets / "bgblur.jpg"
    if not dst.exists():
        t = _dur(dv) / 3
        ve.run([ve.FFMPEG, "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", ve.pdir(vid) / "master.mp4", "-frames:v", "1", "-vf",
                f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=40:3,eq=brightness=-0.12:saturation=0.8",
                "-q:v", "4", dst], vid)
    return "assets/bgblur.jpg"


def screen_stage(vid, dv, mode, video_src, D, W, H, assets):
    """(html، css، خط‌های تایم‌لاین) صحنه‌ی ضبط صفحه. #vz ظرف زوم است (ویدیو + ماژیک‌ها)؛ زوم‌ها روی آن tween می‌شوند."""
    info = dv["proj"].get("info") or {}
    sw, sh = max(1, info.get("w") or 1920), max(1, info.get("h") or 1080)
    opts = dv["opts"]
    vert = dv["kind"] == "reel"
    layout = opts.get("vlayout", "frame") if vert else "frame"
    vtag = (f'<video id="v" src="{video_src}" data-start="0" data-duration="{D}" data-track-index="0" '
            f'{"muted " if mode == "render" else ""}playsinline></video>')
    zooms = [z for z in dv.get("zooms") or [] if not z.get("skip") and z.get("on") is not False]
    if layout == "follow":
        FW, FH = sw * H / sh, float(H)
        x0 = (W - FW) / 2
    else:
        if vert:                                     # قاب وسط بین نوار بالای اینستاگرام و جای زیرنویس
            fw = W - 48
            fh = fw * sh / sw
            if fh > 1100:
                fh, fw = 1100, 1100 * sw / sh
            fx, fy = (W - fw) / 2, 290 + (1110 - fh) / 2
        else:
            mx, top, bottom = 64, 48, 150
            bw, bh = W - 2 * mx, H - top - bottom
            sc = min(bw / sw, bh / sh)
            fw, fh = sw * sc, sh * sc
            fx, fy = (W - fw) / 2, top + (bh - fh) / 2
        FW, FH, x0 = fw, fh, 0.0
    marks, tl = [], [f'tl.set("#vz",{{x:{x0:.1f},y:0,scale:1,transformOrigin:"0 0"}},0);']
    for k, z in enumerate(zooms):
        x, y, w, h = z["box"]
        if layout == "follow":
            Z = max(FOLLOW_Z.get(z.get("z"), 1.25), min(1.8, 0.45 * W / max(1.0, w * FW)))
            cx, cy = (x + w / 2) * FW * Z, (y + h / 2) * FH * Z
            tx, ty = min(0.0, max(W - FW * Z, W / 2 - cx)), min(0.0, max(H - FH * Z, H / 2 - cy))
        else:
            Z = max(1.15, min(ZOOM_CAP.get(z.get("z"), 2.2), 0.85 / max(w, 0.01), 0.85 / max(h, 0.01)))
            cx, cy = (x + w / 2) * FW * Z, (y + h / 2) * FH * Z
            tx, ty = min(0.0, max(FW - FW * Z, FW / 2 - cx)), min(0.0, max(FH - FH * Z, FH / 2 - cy))
        s, e = z["s"], z["e"]
        tl.append(f'tl.to("#vz",{{x:{tx:.1f},y:{ty:.1f},scale:{Z:.4f},duration:.6,ease:"power2.inOut"}},{max(0.0, s - .3):.3f});')
        nxt = zooms[k + 1] if k + 1 < len(zooms) else None
        if not nxt or nxt["s"] - e > 1.2:            # برگشت؛ در تمام‌قد همان‌جا می‌ماند ولی کوچک می‌شود
            if layout == "follow":
                bx = min(0.0, max(W - FW, W / 2 - (x + w / 2) * FW))
                tl.append(f'tl.to("#vz",{{x:{bx:.1f},y:0,scale:1,duration:.6,ease:"power2.inOut"}},{e:.3f});')
            else:
                tl.append(f'tl.to("#vz",{{x:0,y:0,scale:1,duration:.6,ease:"power2.inOut"}},{e:.3f});')
        hls = z.get("hl") or []
        for j, hb in enumerate(hls):
            mid = f"zm{k}_{j}"
            marks.append(f'<i class="zm" id="{mid}" style="left:{hb[0] * FW:.1f}px;top:{hb[1] * FH:.1f}px;width:{hb[2] * FW:.1f}px;'
                         f'height:{hb[3] * FH:.1f}px"></i>')
            t0 = round(s + .45 + .3 * j, 3)
            tl.append(f'tl.fromTo("#{mid}",{{opacity:1,scaleX:0}},{{opacity:1,scaleX:1,duration:.4,ease:"power2.out"}},{t0});')
            tl.append(f'tl.to("#{mid}",{{opacity:0,duration:.25}},{max(t0 + .5, e):.3f});')
    zm_css = ".zm{position:absolute;background:rgba(255,219,88,.6);mix-blend-mode:multiply;border-radius:6px;opacity:0;transform-origin:0 50%}"
    if layout == "follow":
        stage = f'<div id="vwrap"><div id="vz" style="width:{FW:.0f}px;height:{FH:.0f}px">{vtag}{"".join(marks)}</div></div>'
        css = ("#vwrap{position:absolute;inset:0;overflow:hidden;background:#000}\n#vz{position:absolute;left:0;top:0;transform-origin:0 0}\n"
               "#v{width:100%;height:100%;display:block}\n" + zm_css)
        return stage, css, tl
    bg = (f'#bg{{position:absolute;inset:0;background:url({_bg_blur(vid, dv, assets, W, H)}) center/cover}}' if vert and opts.get("vbg") == "blur"
          else f"#bg{{position:absolute;inset:0;background:radial-gradient(120% 90% at 50% 0%,#1d4355 0%,{ve.BG} 70%)}}")
    stage = f'<div id="bg"></div><div id="vwrap"><div id="frame"><div id="vz">{vtag}{"".join(marks)}</div></div></div>'
    css = (bg + "\n"
           f"#vwrap{{position:absolute;left:{fx:.0f}px;top:{fy:.0f}px;width:{FW:.0f}px;height:{FH:.0f}px}}\n"
           f"#frame{{position:relative;width:100%;height:100%;border-radius:{26 if vert else 22}px;overflow:hidden;"
           "box-shadow:0 24px 60px rgba(0,0,0,.45),0 0 0 2px rgba(135,206,250,.18);background:#000}\n"
           "#vz{position:absolute;left:0;top:0;width:100%;height:100%;transform-origin:0 0}\n"
           "#v{width:100%;height:100%;object-fit:contain;display:block}\n" + zm_css)
    return stage, css, tl


# ---------------- برای صفحه ----------------
def views(vid, dv):
    if not is_screen(dv):
        return {}
    zooms = []
    for z in dv.get("zooms") or []:
        f = ve.pdir(vid) / frame_rel(z.get("t", 0))
        zooms.append({k: z.get(k) for k in ("id", "w0", "w1", "t", "s", "e", "box", "hl", "z", "target", "why", "on", "src", "skip")}
                     | {"frame": frame_rel(z.get("t", 0)) if f.exists() else ""})
    blurs = []
    for b in dv["edit"].get("blurs") or []:
        t = (b.get("s", 0) + b.get("e", 0)) / 2
        f = ve.pdir(vid) / frame_rel(t)
        blurs.append({k: b.get(k) for k in ("id", "s", "e", "box", "type", "label", "on", "src")}
                     | {"frame": frame_rel(t) if f.exists() else "", "o": round(dv["tmap"].out(b.get("s", 0)), 2)})
    return {"zooms": zooms, "blurs": blurs, "screen": {"vlayout": VLAYOUT, "vbg": VBG, "zoom": ZOOM_FA, "blurType": BLUR_FA}}
