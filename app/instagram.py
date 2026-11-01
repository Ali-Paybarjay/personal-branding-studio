"""Content Studio — تحلیل اینستاگرام با توکن خود کاربر (فقط خواندنی).

استودیو مستقیم با Instagram API (graph.instagram.com) حرف می‌زند؛ هیچ سرور واسطی نیست و چیزی منتشر نمی‌شود.
توکن در ‎.env‎ استودیو (INSTAGRAM_TOKEN) است و هرگز به مرورگر فرستاده نمی‌شود. توکن بلندمدت ۶۰ روز اعتبار دارد و
token_keeper هر چند روز تمدیدش می‌کند، پس تا وقتی استودیو گاهی باز شود منقضی نمی‌شود.

اینستاگرام فقط آخرین عددها را می‌دهد، نه تاریخچه را، و آمار استوری را فقط ۲۴ ساعت نگه می‌دارد. پس هر همگام‌سازی
یک «عکس» از عددها را در data/instagram/raw.json روی همین کامپیوتر نگه می‌دارد و تاریخچه کم‌کم ساخته می‌شود.
شکل raw.json همان چیزی است که build_dataset می‌خواند:
  {username, media:[...], metrics:[{media_id, captured_at, metrics}], account:[{date, followers, metrics}],
   stories:[{id, posted_at, media_type, metrics, has_thumb}], audience:{data, captured_on}}

سقف درخواست: اینستاگرام برای هر حساب در ساعت حدود ۲۰۰ درخواست اجازه می‌دهد. هر همگام‌سازی سهمیه‌ای دارد
و اگر به سقف خورد، هرچه گرفته ذخیره می‌شود و دفعه‌ی بعد ادامه می‌دهد.
"""
import json, os, re, shutil, statistics, subprocess, threading, time, urllib.error, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import settings as cfg
import ai_models as am

ROOT    = Path(__file__).resolve().parent.parent
DATA    = ROOT / "data"
IG      = DATA / "instagram"
THUMBS  = IG / "thumbs"
REPORTS = IG / "reports"
RAW     = IG / "raw.json"
LOCAL   = datetime.now().astimezone().tzinfo        # منطقه‌ی زمانی همین کامپیوتر
GRAPH   = "https://graph.instagram.com/v26.0"
DAY     = 86400
BUDGET_DAYS = 30          # در هر همگام‌سازی حداکثر چند روزِ حساب گرفته شود (هر روز ۳ درخواست)
BUDGET_MEDIA = 70         # و آمار حداکثر چند پست
HISTORY_DAYS = 89         # اینستاگرام آمار روزانه‌ی حساب را ۹۰ روز نگه می‌دارد


# ---------- Graph API ----------
class GraphError(Exception):
    def __init__(self, msg, code=None, status=None):
        super().__init__(msg)
        self.code, self.status = code, status

    @property
    def token_invalid(self):
        return self.code == 190

    @property
    def rate_limited(self):
        return self.code in (4, 17, 32, 613)


def token():
    return cfg.env("INSTAGRAM_TOKEN")


def call(path, params=None, tok=None, base=GRAPH, timeout=20):
    tok = tok or token()
    if not tok:
        raise GraphError("اینستاگرام وصل نیست.", code=190)
    url = base + path + ("?" + urllib.parse.urlencode({k: v for k, v in (params or {}).items() if v is not None}) if params else "")
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {tok}", "User-Agent": "ContentStudio/1"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            err = json.loads(e.read() or b"{}").get("error") or {}
        except Exception:
            err = {}
        raise GraphError(err.get("message") or f"HTTP {e.code}", err.get("code"), e.code)
    except GraphError:
        raise
    except Exception as e:
        raise GraphError(f"اتصال به اینستاگرام برقرار نشد: {str(e)[:120]}")


def flatten(rows):
    out = {}
    for r in rows or []:
        tv = r.get("total_value")
        if tv:
            res = ((tv.get("breakdowns") or [{}])[0] or {}).get("results")
            out[r["name"]] = ({"|".join(x["dimension_values"]): x["value"] for x in res} if res else tv.get("value"))
        else:
            vals = r.get("values") or []
            out[r["name"]] = vals[-1].get("value") if vals else None
    return out


BAD_METRICS = {}          # نوع → متریک‌هایی که اینستاگرام برای این حساب رد کرده (یک بار یاد گرفته می‌شود)


def insights(path, metrics, extra=None, kind=""):
    """همه‌ی متریک‌ها یک‌جا؛ اگر یکی رد شد، یکی‌یکی امتحان می‌شوند و رد‌شده‌ها برای بار بعد کنار می‌روند."""
    ms = [m for m in metrics if m not in BAD_METRICS.get(kind, set())]
    try:
        return flatten(call(path, {"metric": ",".join(ms), **(extra or {})}).get("data"))
    except GraphError as e:
        if e.token_invalid or e.rate_limited:
            raise
    out = {}
    for m in ms:
        try:
            out.update(flatten(call(path, {"metric": m, **(extra or {})}).get("data")))
        except GraphError as e:
            if e.token_invalid or e.rate_limited:
                raise
            BAD_METRICS.setdefault(kind, set()).add(m)
    return out


MEDIA_FIELDS = "id,caption,media_type,media_product_type,permalink,thumbnail_url,media_url,timestamp"
REEL_METRICS = ["views", "reach", "likes", "comments", "shares", "saved", "total_interactions",
                "ig_reels_avg_watch_time", "ig_reels_video_view_total_time", "reels_skip_rate", "profile_visits", "follows"]
FEED_METRICS = ["views", "reach", "likes", "comments", "shares", "saved", "total_interactions", "profile_visits", "follows"]
STORY_METRICS = ["views", "reach", "replies", "shares", "total_interactions", "follows", "profile_visits", "link_clicks"]
DAILY_METRICS = ["reach", "views", "accounts_engaged", "total_interactions", "likes", "comments",
                 "shares", "saves", "replies", "profile_links_taps"]


def get_me(tok=None):
    return call("/me", {"fields": "user_id,username,followers_count,media_count"}, tok=tok)


def account_day(since, until):
    p = {"period": "day", "metric_type": "total_value", "since": since, "until": until}
    m = insights("/me/insights", DAILY_METRICS, p, kind="day")
    for name, metric, breakdown in (("reach_by_follow", "reach", "follow_type"),
                                    ("follows_and_unfollows", "follows_and_unfollows", "follow_type")):
        try:
            m[name] = flatten(call("/me/insights", {"metric": metric, "breakdown": breakdown, **p}).get("data")).get(metric)
        except GraphError as e:
            if e.token_invalid or e.rate_limited:
                raise
            m[name] = None
    return m


def demographics():
    out = {}
    for b in ("age", "gender", "country", "city"):
        try:
            out[b] = flatten(call("/me/insights", {"metric": "follower_demographics", "period": "lifetime",
                                                   "metric_type": "total_value", "breakdown": b}).get("data")).get("follower_demographics")
        except GraphError as e:
            if e.token_invalid or e.rate_limited:
                raise
    return out


# ---------- اتصال و تمدید توکن ----------
def connect(tok):
    tok = (tok or "").strip()
    if not re.fullmatch(r"[\w\-|.]{40,400}", tok):
        return 400, {"error": "این شبیه توکن اینستاگرام نیست. توکن را کامل کپی کن (معمولاً با IG شروع می‌شود)."}
    try:
        me = get_me(tok)
    except GraphError as e:
        if e.token_invalid:
            return 400, {"error": "اینستاگرام این توکن را قبول نکرد. شاید منقضی شده یا ناقص کپی شده."}
        return 400, {"error": str(e)}
    cfg.write_env("INSTAGRAM_TOKEN", tok)
    cfg.save({"instagram": {"username": me.get("username"), "token_at": time.time()}})
    refresh_token(force=True)
    return 200, {"ok": True, "username": me.get("username"), "followers": me.get("followers_count")}


def disconnect():
    cfg.write_env("INSTAGRAM_TOKEN", "")
    cfg.save({"instagram": {"username": None, "token_at": None}})
    return 200, {"ok": True}


def refresh_token(force=False):
    """توکن بلندمدت را تمدید می‌کند (فقط وقتی دست‌کم یک روز از ساختش گذشته باشد؛ قاعده‌ی خود اینستاگرام)."""
    tok = token()
    if not tok:
        return False
    st = cfg.load().get("instagram") or {}
    if not force and time.time() - (st.get("refreshed_at") or st.get("token_at") or 0) < 5 * DAY:
        return False
    try:
        d = call("/refresh_access_token", {"grant_type": "ig_refresh_token", "access_token": tok},
                 tok=tok, base="https://graph.instagram.com")
    except GraphError:
        return False
    if d.get("access_token"):
        cfg.write_env("INSTAGRAM_TOKEN", d["access_token"])
        cfg.save({"instagram": {"refreshed_at": time.time(), "expires_at": time.time() + (d.get("expires_in") or 0)}})
        return True
    return False


def token_keeper():
    while True:
        try:
            refresh_token()
        except Exception:
            pass
        time.sleep(12 * 3600)


def status():
    st = cfg.load().get("instagram") or {}
    return {"connected": bool(token()), "username": st.get("username"), "expires_at": st.get("expires_at")}


# ---------- تاریخچه‌ی لوکال ----------
def ymd(ts):
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d")


def age_hours(iso):
    try:
        return (time.time() - datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()) / 3600
    except Exception:
        return None


def media_due(m, last):
    """این پست الان عکس تازه می‌خواهد؟ (مثل سایت: پست‌های تازه زیاد، کهنه‌ها ماهی یک بار)"""
    age = age_hours(m.get("posted_at") or "")
    if age is None:
        return False
    if not last:
        return True
    ago = (time.time() - datetime.fromisoformat(last["captured_at"]).timestamp()) / 3600
    if age < 48:
        return ago > 6
    if age < 35 * 24:
        return ago > 24
    return ago > 30 * 24


# ---------- کارهای پس‌زمینه ----------
JOBS = {k: {"state": "idle", "step": "", "log": [], "error": "", "result": None}
        for k in ("sync", "report", "ask")}
JLOCK = threading.Lock()


def jset(kind, **kw):
    with JLOCK:
        JOBS[kind].update(kw)


def jlog(kind, line):
    with JLOCK:
        JOBS[kind]["log"].append(line)
        del JOBS[kind]["log"][:-30]


def jstart(kind, target, *args):
    with JLOCK:
        if JOBS[kind]["state"] == "running":
            return False
        JOBS[kind].update(state="running", step="", log=[], error="", result=None)

    def wrapped():
        try:
            target(*args)
        except subprocess.TimeoutExpired:
            jset(kind, state="error", error="زمان اجرا تمام شد.")
        except Exception as e:
            jset(kind, state="error", error=f"خطا: {e}")
    threading.Thread(target=wrapped, daemon=True).start()
    return True


def claude_bin():
    return cfg.claude_bin()


def safe_id(s):
    return re.sub(r"[^\w-]", "", str(s))[:80]


def jread(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def jwrite(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")


# ---------- ساختن دیتاست از تاریخچه‌ی لوکال ----------
def num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def pct(a, b):
    return round(a / b * 100, 2) if a is not None and b else None


def med(xs):
    xs = [x for x in xs if x is not None]
    return round(statistics.median(xs), 2) if xs else None


def to_local(iso):
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(LOCAL)
    except Exception:
        return None


def post_type(p):
    if p.get("product_type") == "REELS":
        return "REELS"
    if p.get("media_type") == "CAROUSEL_ALBUM":
        return "CAROUSEL"
    return "POST"


def lower_keys(d):
    return {str(k).lower(): v for k, v in d.items()} if isinstance(d, dict) else {}


def build_dataset(raw):
    now = datetime.now(timezone.utc)
    snaps_by = {}
    for m in raw.get("metrics", []):
        snaps_by.setdefault(m["media_id"], []).append(m)

    posts = []
    for p in raw.get("media", []):
        snaps = sorted(snaps_by.get(p["id"], []), key=lambda s: s["captured_at"])
        last = snaps[-1]["metrics"] if snaps else {}
        dt = to_local(p.get("posted_at") or "")
        cap = (p.get("caption") or "").strip()
        reach = num(last.get("reach"))
        watch = num(last.get("ig_reels_avg_watch_time"))
        row = {
            "id": p["id"], "type": post_type(p), "permalink": p.get("permalink"),
            "posted_at": p.get("posted_at"),
            "date": dt.strftime("%Y-%m-%d") if dt else None,
            "weekday": dt.weekday() if dt else None,
            "hour": dt.hour if dt else None,
            "age_days": round((now - dt).total_seconds() / 86400, 1) if dt else None,
            "hook": cap.split("\n")[0][:160], "caption_len": len(cap),
            "views": num(last.get("views")), "reach": reach,
            "likes": num(last.get("likes")), "comments": num(last.get("comments")),
            "shares": num(last.get("shares")), "saved": num(last.get("saved")),
            "follows": num(last.get("follows")), "profile_visits": num(last.get("profile_visits")),
            "interactions": num(last.get("total_interactions")),
            "avg_watch_s": round(watch / 1000, 1) if watch else None,
            "skip_rate": num(last.get("reels_skip_rate")),
            "has_metrics": bool(snaps),
        }
        row["share_rate"] = pct(row["shares"], reach)
        row["save_rate"] = pct(row["saved"], reach)
        row["engagement_rate"] = pct(row["interactions"], reach)
        posts.append(row)

    recent = [p for p in posts if p["has_metrics"] and (p["age_days"] or 0) <= 90]
    baselines = {}
    for t in ("REELS", "POST", "CAROUSEL"):
        group = [p for p in recent if p["type"] == t]
        baselines[t] = {
            "n": len(group),
            **{k: med([p[k] for p in group]) for k in
               ("views", "reach", "share_rate", "save_rate", "engagement_rate", "avg_watch_s")},
        }
    for p in posts:
        base = baselines.get(p["type"], {}).get("views")
        p["views_vs_median"] = round(p["views"] / base, 2) if p["views"] is not None and base else None

    days = []
    for d in sorted(raw.get("account", []), key=lambda r: r["date"]):
        m = d.get("metrics") or {}
        rbf = lower_keys(m.get("reach_by_follow"))
        fu = lower_keys(m.get("follows_and_unfollows"))
        days.append({
            "date": d["date"], "followers": d.get("followers"),
            "views": num(m.get("views")), "reach": num(m.get("reach")),
            "reach_followers": num(rbf.get("follower")), "reach_non_followers": num(rbf.get("non_follower")),
            "interactions": num(m.get("total_interactions")), "accounts_engaged": num(m.get("accounts_engaged")),
            "follows": num(fu.get("follower")), "unfollows": num(fu.get("non_follower")),
            "profile_links_taps": num(m.get("profile_links_taps")),
        })

    def window(start, end):
        rows = [d for d in days if start <= d["date"] < end]
        tot = lambda k: sum(d[k] or 0 for d in rows) if rows else None
        n_posts = sum(1 for p in posts if p["date"] and start <= p["date"] < end)
        return {"days": len(rows), "views": tot("views"), "reach": tot("reach"),
                "interactions": tot("interactions"), "follows": tot("follows"),
                "unfollows": tot("unfollows"), "profile_links_taps": tot("profile_links_taps"), "posts": n_posts}
    today = now.astimezone(LOCAL).date()
    d30, d60 = str(today - timedelta(days=30)), str(today - timedelta(days=60))
    followers = next((d["followers"] for d in reversed(days) if d["followers"] is not None), None)

    stories = []
    for s in sorted(raw.get("stories", []), key=lambda r: r.get("posted_at") or ""):
        m = s.get("metrics") or {}
        nav = lower_keys(m.get("navigation"))
        dt = to_local(s.get("posted_at") or "")
        stories.append({
            "id": s["id"], "date": dt.strftime("%Y-%m-%d") if dt else None,
            "time": dt.strftime("%H:%M") if dt else None, "type": s.get("media_type"),
            "reach": num(m.get("reach")), "views": num(m.get("views")), "replies": num(m.get("replies")),
            "shares": num(m.get("shares")), "follows": num(m.get("follows")),
            "profile_visits": num(m.get("profile_visits")), "link_clicks": num(m.get("link_clicks")),
            "tap_forward": num(nav.get("tap_forward")), "tap_back": num(nav.get("tap_back")),
            "tap_exit": num(nav.get("tap_exit")), "swipe_forward": num(nav.get("swipe_forward")),
            "has_thumb": bool(s.get("thumb_path") or s.get("has_thumb")),
        })
    story_days = {}
    for s in stories:
        story_days.setdefault(s["date"], []).append(s["id"])

    def bucket(key, labels):
        out = []
        for k, label in labels:
            group = [p for p in recent if key(p) == k and p["views_vs_median"] is not None]
            out.append({"key": k, "label": label, "n": len(group),
                        "median_ratio": med([p["views_vs_median"] for p in group])})
        return out
    # Persian week order (Saturday first); Python's weekday() has Monday = 0.
    WEEKDAYS = [(5, "شنبه"), (6, "یکشنبه"), (0, "دوشنبه"), (1, "سه‌شنبه"), (2, "چهارشنبه"), (3, "پنجشنبه"), (4, "جمعه")]
    timing = {
        "by_weekday": bucket(lambda p: p["weekday"], WEEKDAYS),
        "by_hour": bucket(lambda p: None if p["hour"] is None else p["hour"] // 3 * 3,
                          [(h, f"{h:02d}–{h + 3:02d}") for h in range(0, 24, 3)]),
    }

    aud = (raw.get("audience") or {}).get("data") or {}
    return {
        "generated_at": now.isoformat(), "username": raw.get("username"),
        "summary": {"followers": followers, "last30": window(d30, str(today + timedelta(days=1))),
                    "prev30": window(d60, d30)},
        "baselines": baselines, "posts": posts, "account_days": days,
        "stories": stories, "story_days": story_days, "timing": timing,
        "audience": {k: aud.get(k) for k in ("age", "gender", "country", "city")},
        "audience_at": (raw.get("audience") or {}).get("captured_on"),
    }




# ---------- همگام‌سازی ----------
def download(url, dest):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 ContentStudio"})
        with urllib.request.urlopen(req, timeout=25) as r:
            data = r.read()
        if len(data) > 100:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            return True
    except Exception:
        pass
    return False


def thumb_file(kind, id_):
    return THUMBS / f"{kind}-{safe_id(id_)}.jpg"


def fetch_thumb(kind, id_):
    f = thumb_file(kind, id_)
    if f.exists():
        return True
    if kind != "media" or not token():
        return False
    raw = jread(RAW, {})
    m = next((x for x in raw.get("media") or [] if x.get("id") == id_), None)
    if m and m.get("thumb_url") and download(m["thumb_url"], f):
        return True
    try:                                   # لینک‌های CDN اینستاگرام چند روز بعد منقضی می‌شوند
        d = call(f"/{id_}", {"fields": "thumbnail_url,media_url,media_type"})
    except GraphError:
        return False
    url = d.get("thumbnail_url") or (d.get("media_url") if d.get("media_type") != "VIDEO" else None)
    return bool(url) and download(url, f)


def _media_row(m):
    thumb = m.get("thumbnail_url") or (m.get("media_url") if m.get("media_type") in ("IMAGE", "CAROUSEL_ALBUM") else None)
    return {"id": m["id"], "caption": m.get("caption") or "", "media_type": m.get("media_type"),
            "product_type": m.get("media_product_type"), "permalink": m.get("permalink"),
            "posted_at": m.get("timestamp"), "thumb_url": thumb}


def do_sync(kind):
    raw = jread(RAW, {}) or {}
    for k in ("media", "metrics", "account", "stories"):
        raw.setdefault(k, [])
    note = ""
    try:
        jset(kind, step="گرفتن فهرست پست‌ها")
        me = get_me()
        raw["username"] = me.get("username")
        media, after = [], None
        for _ in range(10):                                   # حداکثر ۵۰۰ پست
            d = call("/me/media", {"fields": MEDIA_FIELDS, "limit": 50, "after": after})
            media += d.get("data") or []
            after = ((d.get("paging") or {}).get("cursors") or {}).get("after")
            if not (d.get("paging") or {}).get("next") or not after:
                break
        raw["media"] = [_media_row(m) for m in media]
        jlog(kind, f"▸ {len(media)} پست در پیج @{me.get('username')}")

        last = {m["media_id"]: m for m in raw["metrics"]}
        due = [m for m in raw["media"] if media_due(m, last.get(m["id"]))][:BUDGET_MEDIA]
        for n, m in enumerate(due, 1):
            jset(kind, step=f"آمار پست‌ها ({n} از {len(due)})")
            reel = m.get("product_type") == "REELS"
            metrics = insights(f"/{m['id']}/insights", REEL_METRICS if reel else FEED_METRICS, kind="reel" if reel else "feed")
            last[m["id"]] = {"media_id": m["id"], "captured_at": datetime.now(timezone.utc).isoformat(), "metrics": metrics}
        raw["metrics"] = list(last.values())
        if due:
            jlog(kind, f"▸ آمار {len(due)} پست به‌روز شد")

        today = int(time.time()) // DAY * DAY
        rows = {a["date"]: a for a in raw["account"]}
        y = rows.get(ymd(today - DAY))
        if y is not None:
            y["followers"] = me.get("followers_count")
        n = 0
        for i in range(1, HISTORY_DAYS + 1):
            start = today - i * DAY
            if n >= BUDGET_DAYS:
                break
            if ymd(start) in rows and rows[ymd(start)].get("metrics"):
                continue
            jset(kind, step=f"آمار روزانه‌ی حساب ({ymd(start)})")
            rows[ymd(start)] = {"date": ymd(start), "metrics": account_day(start, start + DAY),
                                "followers": me.get("followers_count") if i == 1 else (rows.get(ymd(start)) or {}).get("followers")}
            n += 1
        raw["account"] = sorted(rows.values(), key=lambda r: r["date"])
        if n:
            jlog(kind, f"▸ آمار {n} روز حساب گرفته شد")

        jset(kind, step="استوری‌های ۲۴ ساعت اخیر")
        stories = {s["id"]: s for s in raw["stories"]}
        for s in call("/me/stories", {"fields": MEDIA_FIELDS}).get("data") or []:
            m = insights(f"/{s['id']}/insights", STORY_METRICS, kind="story")
            try:
                m.update(flatten(call(f"/{s['id']}/insights", {"metric": "navigation",
                                                               "breakdown": "story_navigation_action_type"}).get("data")))
            except GraphError as e:
                if e.token_invalid or e.rate_limited:
                    raise
            url = s.get("thumbnail_url") or (s.get("media_url") if s.get("media_type") == "IMAGE" else None)
            has = thumb_file("story", s["id"]).exists() or (bool(url) and download(url, thumb_file("story", s["id"])))
            stories[s["id"]] = {"id": s["id"], "posted_at": s.get("timestamp"), "media_type": s.get("media_type"),
                                "metrics": m, "has_thumb": has}
        raw["stories"] = list(stories.values())

        aud = raw.get("audience") or {}
        if not aud.get("captured_on") or time.time() - datetime.fromisoformat(aud["captured_on"]).timestamp() > 7 * DAY:
            jset(kind, step="مخاطب‌ها")
            raw["audience"] = {"data": demographics(), "captured_on": ymd(time.time())}
    except GraphError as e:
        if e.token_invalid:
            jwrite(RAW, raw)
            jset(kind, error="اینستاگرام توکن را قبول نکرد (منقضی یا لغو شده). از «اتصال دوباره» یک توکن تازه بگذار.")
            return False
        if e.rate_limited:
            note = "اینستاگرام سقف درخواست ساعتی را پر کرد. هرچه گرفته شد ذخیره شد؛ یک ساعت بعد دوباره «همگام‌سازی» بزن تا کامل شود."
        else:
            note = f"بخشی از داده گرفته نشد: {str(e)[:160]}"
        jlog(kind, "⚠️ " + note)

    jwrite(RAW, raw)
    if not raw.get("media"):
        jset(kind, error=note or "پستی پیدا نشد.")
        return False
    ds = build_dataset(raw)
    jwrite(IG / "dataset.json", ds)
    jlog(kind, f"▸ {len(ds['posts'])} پست، {len(ds['stories'])} استوری، {len(ds['account_days'])} روز آمار")

    jset(kind, step="ذخیره‌ی تصویرها")
    newest = sorted(raw["media"], key=lambda p: p.get("posted_at") or "", reverse=True)[:150]
    missing = [m for m in newest if m.get("thumb_url") and not thumb_file("media", m["id"]).exists()]
    with ThreadPoolExecutor(6) as ex:
        got = sum(ex.map(lambda m: download(m["thumb_url"], thumb_file("media", m["id"])), missing))
    if got:
        jlog(kind, f"▸ {got} تصویر تازه ذخیره شد")
    return True


def run_sync():
    if do_sync("sync"):
        jset("sync", state="done", step="تمام شد")
    else:
        jset("sync", state="error")


# ---------- تحلیلگر ----------
REPORT_PROMPT = (
    "اول modules/instagram/ANALYST.md را کامل بخوان و دقیقاً طبق آن عمل کن. صاحب پیج: {owner}.\n"
    "هسته‌ی برندش در brand/brand-core.md است. داده‌ها در data/instagram/dataset.json است. تاریخ امروز: {day}.\n"
    "گزارش را در {out} بنویس.\n"
    "هیچ سؤالی نپرس. وقتی فایل ساخته شد فقط بنویس: تمام."
)

ASK_PROMPT = (
    "سؤال تکمیلی دربارهٔ گزارش اینستاگرام (فایل گزارش: data/instagram/reports/{name}.md، "
    "داده‌ها: data/instagram/dataset.json):\n\n{q}\n\n"
    "فقط بر اساس داده‌ها جواب بده، کوتاه و به فارسی. هیچ عددی نساز؛ برای هر ادعا دربارهٔ یک پست لینکش را بیاور. "
    "اگر داده‌ای برای جواب نیست، صادقانه بگو. هیچ فایلی را تغییر نده."
)


def run_report():
    ds = IG / "dataset.json"
    if token() and (not ds.exists() or time.time() - ds.stat().st_mtime > 6 * 3600):
        do_sync("report")
    if not ds.exists():
        return jset("report", state="error",
                    error=JOBS["report"]["error"] or "داده‌ای برای تحلیل نیست؛ اول اینستاگرام را وصل کن و همگام‌سازی بزن.")
    day = time.strftime("%Y-%m-%d")
    out = REPORTS / f"{day}.md"
    REPORTS.mkdir(parents=True, exist_ok=True)
    jset("report", step="تحلیلگر در حال نوشتن گزارش")
    jlog("report", "▸ Claude دارد داده‌ها را می‌خواند؛ چند دقیقه طول می‌کشد…")
    prompt = REPORT_PROMPT.format(day=day, out=f"data/instagram/reports/{day}.md", owner=cfg.owner_line())
    r = subprocess.run([cfg.claude_bin(), "-p", prompt, "--model", am.get("analyst"),
                        "--permission-mode", "acceptEdits", "--output-format", "json"],
                       cwd=str(ROOT), capture_output=True, text=True, timeout=3600)
    if r.returncode != 0:
        jlog("report", (r.stderr or r.stdout or "")[-300:])
        return jset("report", state="error", error="تحلیلگر کارش را تمام نکرد.")
    try:
        meta = json.loads(r.stdout)
    except Exception:
        meta = {}
    if not out.exists():
        return jset("report", state="error", error="فایل گزارش ساخته نشد.")
    jwrite(REPORTS / f"{day}.json", {"session_id": meta.get("session_id"), "created": time.strftime("%Y-%m-%d %H:%M"), "chat": []})
    jset("report", state="done", step="تمام شد", result={"name": day})


def run_ask(name, question):
    meta_f = REPORTS / f"{name}.json"
    meta = jread(meta_f, {"chat": []})
    jset("ask", step="تحلیلگر در حال جواب دادن")
    cmd = [cfg.claude_bin(), "-p", ASK_PROMPT.format(name=name, q=question), "--model", am.get("analyst"),
           "--output-format", "json"]
    if meta.get("session_id"):
        cmd += ["--resume", meta["session_id"]]
    r = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=1800)
    try:
        out = json.loads(r.stdout)
    except Exception:
        out = {}
    answer = (out.get("result") or "").strip()
    if r.returncode != 0 or not answer:
        jlog("ask", (r.stderr or "")[-300:])
        return jset("ask", state="error", error="جوابی نیامد.")
    meta["session_id"] = out.get("session_id") or meta.get("session_id")
    meta.setdefault("chat", []).append({"q": question, "a": answer, "at": time.strftime("%Y-%m-%d %H:%M")})
    jwrite(meta_f, meta)
    jset("ask", state="done", step="تمام شد", result={"name": name})


def report_ideas(text):
    blocks = re.findall(r"```json\s*(\{.*?\})\s*```", text, flags=re.S)
    for b in reversed(blocks):
        try:
            ideas = json.loads(b).get("ideas")
            if isinstance(ideas, list):
                return [i for i in ideas if isinstance(i, dict) and i.get("title")]
        except Exception:
            continue
    return []


# ---------- مسیرها ----------
def handle_get(p, q):
    """(status, payload, content_type) یا None اگر مسیر مال این ماژول نیست."""
    if p == "/api/jobs":
        with JLOCK:
            return 200, {k: dict(v) for k, v in JOBS.items()}, None
    if p == "/api/insta/status":
        return 200, status(), None
    if p == "/api/insta/dataset":
        f = IG / "dataset.json"
        ds = jread(f, None)
        return 200, ({"dataset": ds, "synced_at": f.stat().st_mtime} if ds else {"dataset": None}), None
    if p == "/api/insta/thumb":
        kind = "story" if q.get("kind", [""])[0] == "story" else "media"
        id_ = q.get("id", [""])[0]
        if not id_:
            return 400, {"error": "bad"}, None
        f = thumb_file(kind, id_)
        if f.exists() or fetch_thumb(kind, id_):
            return 200, f.read_bytes(), "image/jpeg"
        return 404, {"error": "no thumb"}, None
    if p == "/api/insta/reports":
        REPORTS.mkdir(parents=True, exist_ok=True)
        return 200, sorted((f.stem for f in REPORTS.glob("*.md")), reverse=True), None
    if p == "/api/insta/report":
        name = safe_id(q.get("name", [""])[0])
        f = REPORTS / f"{name}.md"
        if not name or not f.exists():
            return 404, {"error": "not found"}, None
        text = f.read_text(encoding="utf-8")
        meta = jread(REPORTS / f"{name}.json", {})
        return 200, {"name": name, "text": text, "ideas": report_ideas(text), "chat": meta.get("chat", []),
                     "created": meta.get("created")}, None
    return None


def handle_post(p, body):
    if p == "/api/insta/connect":
        return connect(body.get("token"))
    if p == "/api/insta/disconnect":
        return disconnect()
    if p == "/api/insta/sync":
        if not token():
            return 400, {"error": "اول اینستاگرام را وصل کن."}
        return (200, {"ok": True}) if jstart("sync", run_sync) else (409, {"error": "در حال اجراست."})
    if p == "/api/insta/report":
        return (200, {"ok": True}) if jstart("report", run_report) else (409, {"error": "در حال اجراست."})
    if p == "/api/insta/ask":
        name = safe_id(body.get("name", ""))
        question = (body.get("q") or "").strip()[:1500]
        if not name or not question or not (REPORTS / f"{name}.md").exists():
            return 400, {"error": "سؤال یا گزارش نامعتبر است."}
        return (200, {"ok": True}) if jstart("ask", run_ask, name, question) else (409, {"error": "در حال اجراست."})
    return None
