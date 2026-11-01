// عکس صفحه‌ی یک سایت و جای دقیق جمله‌ای که باید هایلایت شود (فاز ۴ تدوین ویدیو). playwright-core + Chrome خود مک.
// ورودی (stdin، JSON): {url, quote, mode: "desktop"|"mobile", out: "<پوشه>", profile: "<پوشه‌ی پروفایل ماندگار>", chrome?}
// خروجی: <out>/shot.jpg — حدود سه برابر ارتفاع پنجره دور جمله (برای انیمیشن اسکرول) — و یک JSON روی stdout:
//   {ok, how: exact|nospace|fuzzy, score, lines: [[x,y,w,h]…] (px CSS نسبت به بالای shot)، target (y خط اول)، y0،
//    view: {w,h,dpr}, shot: {w,h}, dir, title, finalUrl, text, viewportOnly}
//   یا {ok:false, blocked|notFound|error, reason} (در notFound هم shot.jpg از بالای صفحه ساخته می‌شود تا کاربر خودش کادر بکشد).
// امنیت: فقط http(s)؛ هر درخواست به localhost، شبکه‌ی داخلی، Tailscale (100.64/10، *.ts.net) و *.local رد می‌شود
// (صفحه‌ی ناشناس نباید بتواند به API همین استودیو روی 127.0.0.1 درخواست بزند). دانلود و service worker خاموش.
import fs from "fs";
import path from "path";
import { createRequire } from "module";
const require = createRequire(import.meta.url);
const { chromium } = require("playwright-core");

const inp = JSON.parse(fs.readFileSync(0, "utf8"));
const CHROME = inp.chrome || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const DESKTOP_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36";
const MOBILE_UA = "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Mobile Safari/537.36";
const MODES = {
  desktop: { viewport: { width: 1024, height: 768 }, deviceScaleFactor: 2, isMobile: false, hasTouch: false, userAgent: DESKTOP_UA },
  mobile: { viewport: { width: 390, height: 844 }, deviceScaleFactor: 3, isMobile: true, hasTouch: true, userAgent: MOBILE_UA },
};
const PRIVATE = /^(localhost|127\.|10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.|169\.254\.|0\.|::1$|\[::1\]|100\.(6[4-9]|[7-9]\d|1[01]\d|12[0-7])\.)|\.(local|localhost|internal|ts\.net)$/i;
const CONSENT = "^(accept|accept all|accept all cookies|accept cookies|allow all|allow all cookies|allow cookies|i agree|agree|agree and continue|got it|ok|okay|i accept|yes, i agree|i understand|continue|close|dismiss|no thanks|not now|قبول|قبول دارم|پذیرفتن|موافقم|متوجه شدم|بستن)$";
const out = o => { process.stdout.write(JSON.stringify(o)); };
const sleep = ms => new Promise(r => setTimeout(r, ms));

function tweetEmbed(u) {
  const m = u.match(/^https?:\/\/(?:www\.|mobile\.)?(?:twitter|x)\.com\/[^/]+\/status(?:es)?\/(\d+)/i);
  return m ? `https://platform.twitter.com/embed/Tweet.html?id=${m[1]}&theme=light&dnt=true&lang=en` : null;
}

// در صفحه اجرا می‌شود: متن دیدنی صفحه با نقشه به گره‌ها، پیدا کردن جمله (دقیق، بدون فاصله، یا تقریبی بر اساس کلمه‌ها)
function locate(quote) {
  const normCh = c => {
    if (/\s/.test(c) || c === " ") return " ";
    if ("‘’‚‛′`´".includes(c)) return "'";
    if ("“”„‟″«»".includes(c)) return '"';
    if ("‐‑‒–—―−".includes(c)) return "-";
    if ("​‌‍﻿ـ".includes(c)) return "";
    if (c === "ي" || c === "ى") return "ی";
    if (c === "ك") return "ک";
    return c.toLowerCase();
  };
  const norm = s => [...s].map(normCh).join("").replace(/ +/g, " ").trim();
  const BLOCK = "p,li,h1,h2,h3,h4,h5,h6,td,th,div,section,article,blockquote,figcaption,dd,dt,header,footer,main,aside,nav,pre,tr,table,ul,ol";
  let text = "", map = [], lastBlock = null;
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, {
    acceptNode(n) {
      const p = n.parentElement;
      if (!p || p.closest("script,style,noscript,template,svg,textarea,select,option")) return NodeFilter.FILTER_REJECT;
      return NodeFilter.FILTER_ACCEPT;
    },
  });
  const visCache = new Map();
  const visible = el => {
    if (visCache.has(el)) return visCache.get(el);
    const cs = getComputedStyle(el);
    const v = cs.display !== "none" && cs.visibility !== "hidden" && cs.opacity !== "0" && el.getClientRects().length > 0;
    visCache.set(el, v);
    return v;
  };
  for (let n = walker.nextNode(); n; n = walker.nextNode()) {
    const v = n.nodeValue;
    if (!v || !v.trim() && !text) continue;
    const p = n.parentElement;
    if (!visible(p)) continue;
    const block = p.closest(BLOCK);
    if (block !== lastBlock && text && text[text.length - 1] !== " ") { text += " "; map.push([n, 0]); }
    lastBlock = block;
    for (let i = 0; i < v.length; i++) {
      const c = normCh(v[i]);
      if (!c) continue;
      if (c === " " && (!text || text[text.length - 1] === " ")) continue;
      text += c;
      map.push([n, i]);
    }
  }
  const q = norm(quote || "");
  if (!q) return { found: false, textLen: text.length };
  const rangeFrom = (a, b) => {           // اندیس‌های text (شامل a، بدون b)
    const r = document.createRange();
    const [n0, o0] = map[a], [n1, o1] = map[b - 1];
    r.setStart(n0, o0);
    r.setEnd(n1, Math.min(o1 + 1, n1.nodeValue.length));
    return r;
  };
  const hasRects = r => [...r.getClientRects()].some(x => x.width > 1 && x.height > 1);
  let best = null;
  for (let i = text.indexOf(q); i >= 0 && !best; i = text.indexOf(q, i + 1)) {
    const r = rangeFrom(i, i + q.length);
    if (hasRects(r)) best = { r, how: "exact", score: 1, a: i, b: i + q.length };
  }
  if (!best) {                            // نیم‌فاصله و فاصله‌ی فارسی: مقایسه بدون فاصله
    let ns = "", nmap = [];
    for (let i = 0; i < text.length; i++) if (text[i] !== " ") { ns += text[i]; nmap.push(i); }
    const qn = q.replace(/ /g, "");
    for (let i = ns.indexOf(qn); i >= 0 && !best && qn.length > 6; i = ns.indexOf(qn, i + 1)) {
      const r = rangeFrom(nmap[i], nmap[i + qn.length - 1] + 1);
      if (hasRects(r)) best = { r, how: "nospace", score: 1, a: nmap[i], b: nmap[i + qn.length - 1] + 1 };
    }
  }
  if (!best) {                            // تقریبی: پنجره‌ای از کلمه‌های صفحه با بیشترین کلمه‌ی مشترک به همان ترتیب
    const qt = q.split(" ").filter(Boolean);
    const toks = [];
    for (let i = 0, s = -1; i <= text.length; i++) {
      if (i === text.length || text[i] === " ") { if (s >= 0) { toks.push([text.slice(s, i), s, i]); s = -1; } }
      else if (s < 0) s = i;
    }
    const strip = t => t.replace(/[^\p{L}\p{N}]+/gu, "");
    const qs = qt.map(strip), ps = toks.map(t => strip(t[0]));
    const anchors = qs.map((t, j) => [t, j]).filter(([t]) => t.length >= 4).sort((a, b) => b[0].length - a[0].length).slice(0, 4);
    const seen = new Set();
    for (const [t, j] of anchors) {
      for (let p = 0; p < ps.length; p++) {
        if (ps[p] !== t) continue;
        const st = Math.max(0, p - j - 3), en = Math.min(ps.length, p - j + qs.length + 3);
        if (seen.has(st)) continue;
        seen.add(st);
        const W = ps.slice(st, en), dp = Array.from({ length: qs.length + 1 }, () => new Array(W.length + 1).fill(0));
        for (let a = 1; a <= qs.length; a++)
          for (let b = 1; b <= W.length; b++)
            dp[a][b] = qs[a - 1] && qs[a - 1] === W[b - 1] ? dp[a - 1][b - 1] + 1 : Math.max(dp[a - 1][b], dp[a][b - 1]);
        const score = dp[qs.length][W.length] / Math.max(1, qs.filter(Boolean).length);
        let a = qs.length, b = W.length, first = -1, last = -1;     // اولین و آخرین کلمه‌ی جور
        while (a > 0 && b > 0) {
          if (qs[a - 1] && qs[a - 1] === W[b - 1]) { if (last < 0) last = b - 1; first = b - 1; a--; b--; }
          else if (dp[a - 1][b] >= dp[a][b - 1]) a--; else b--;
        }
        // بازه نباید خیلی پهن‌تر از خود جمله باشد (وگرنه چند کلمه‌ی پراکنده‌ی صفحه «جور» می‌شوند)
        if (first < 0 || last - first + 1 > Math.ceil(qs.length * 1.35) + 1) continue;
        const span = last - first + 1;
        if (!best || score > best.score || (score === best.score && span < best.span))
          best = { first: st + first, last: st + last, score, span, how: "fuzzy" };
      }
    }
    if (best && best.score >= (qs.length < 8 ? 0.8 : 0.65)) {
      const r = rangeFrom(toks[best.first][1], toks[best.last][2]);
      best = hasRects(r) ? { r, how: "fuzzy", score: best.score, a: toks[best.first][1], b: toks[best.last][2] } : null;
    } else best = null;
  }
  if (!best) return { found: false, textLen: text.length };
  window.__hl = best.r;
  const el = best.r.startContainer.parentElement;
  return { found: true, how: best.how, score: Math.round(best.score * 100) / 100, dir: getComputedStyle(el).direction,
           text: text.slice(best.a, best.b).trim().slice(0, 600) };      // فقط متن دیدنی (toString متن style پنهان را هم می‌آورد)
}

function lineRects() {                    // جعبه‌ی هر خط جمله (px نسبت به بالا-چپ صفحه)
  const r = window.__hl;
  const rs = [...r.getClientRects()].filter(x => x.width > 1 && x.height > 1).sort((a, b) => a.top - b.top || a.left - b.left);
  const lines = [];
  for (const x of rs) {
    const L = lines[lines.length - 1];
    if (L && Math.abs((x.top + x.bottom) / 2 - (L.t + L.b) / 2) < Math.min(x.height, L.b - L.t) * 0.5) {
      L.l = Math.min(L.l, x.left); L.r = Math.max(L.r, x.right); L.t = Math.min(L.t, x.top); L.b = Math.max(L.b, x.bottom);
    } else lines.push({ l: x.left, r: x.right, t: x.top, b: x.bottom });
  }
  const sx = window.scrollX, sy = window.scrollY;
  return lines.map(L => [L.l + sx, L.t + sy, L.r - L.l, L.b - L.t]);
}

function hideChrome() {                   // سربرگ چسبان، بنر کوکی، پنجره‌ی ثبت‌نام و دکمه‌ی چت: همه‌ی fixed و sticky جز ظرف خود جمله
  const keep = window.__hl ? window.__hl.commonAncestorContainer : null;
  for (const el of document.querySelectorAll("body *")) {
    const cs = getComputedStyle(el);
    if ((cs.position === "fixed" || cs.position === "sticky") && !(keep && el.contains(keep))) el.style.setProperty("visibility", "hidden", "important");
  }
  for (const el of [document.documentElement, document.body]) {
    el.style.setProperty("overflow", "auto", "important");
    el.style.setProperty("position", "static", "important");
  }
}

async function dismiss(page) {
  for (const f of page.frames()) {
    // یک iframe تبلیغاتی که هرگز جواب نمی‌دهد، عکس را تا تایم‌اوت ۱۸۰ ثانیه‌ای پایتون نگه می‌داشت (bernardmarr.com، ۲۰۲۶-۱۰-۰۷)
    await Promise.race([sleep(2500), f.evaluate((re) => {
      const R = new RegExp(re, "i");
      const sels = ["#onetrust-accept-btn-handler", "#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll", "#didomi-notice-agree-button",
                    ".fc-cta-consent", "button[mode=primary][data-testid*=accept]", "[aria-label*='Accept' i]"];
      for (const s of sels) { const el = document.querySelector(s); if (el && el.getClientRects().length) { el.click(); return true; } }
      for (const el of document.querySelectorAll("button,[role=button],a,input[type=button],input[type=submit]")) {
        const t = (el.innerText || el.value || el.getAttribute("aria-label") || "").trim();
        if (t && t.length < 40 && R.test(t) && el.getClientRects().length) { el.click(); return true; }
      }
      return false;
    }, CONSENT).catch(() => false)]);
  }
}

let ctx;
try {
  const mode = MODES[inp.mode] ? inp.mode : "desktop";
  const M = MODES[mode];
  fs.mkdirSync(inp.out, { recursive: true });
  ctx = await chromium.launchPersistentContext(inp.profile, {
    executablePath: CHROME, headless: true, ...M, locale: "en-US", colorScheme: "light", acceptDownloads: false,
    serviceWorkers: "block", ignoreHTTPSErrors: false, args: ["--disable-blink-features=AutomationControlled", "--mute-audio"],
  });
  await ctx.route("**/*", route => {
    let u;
    try { u = new URL(route.request().url()); } catch { return route.abort(); }
    if (u.protocol === "data:" || u.protocol === "blob:") return route.continue();
    if (!/^https?:$/.test(u.protocol) || PRIVATE.test(u.hostname)) return route.abort();
    return route.continue();
  });
  const page = ctx.pages()[0] || await ctx.newPage();
  page.setDefaultTimeout(15000);
  const target = tweetEmbed(inp.url) || inp.url;
  const u0 = new URL(target);
  if (!/^https?:$/.test(u0.protocol) || PRIVATE.test(u0.hostname)) throw new Error("نشانی مجاز نیست");
  const resp = await page.goto(target, { waitUntil: "domcontentloaded", timeout: 35000 });
  await page.waitForLoadState("networkidle", { timeout: 9000 }).catch(() => {});
  await sleep(800);
  await dismiss(page);
  await sleep(700);
  const status = resp ? resp.status() : 0;
  const title = await page.title().catch(() => "");
  const bodyLen = await page.evaluate(() => (document.body && document.body.innerText || "").length).catch(() => 0);
  const vw = M.viewport.width, vh = M.viewport.height;
  const base = { finalUrl: page.url(), title, status, view: { w: vw, h: vh, dpr: M.deviceScaleFactor }, mode };
  if (status >= 400 || /just a moment|attention required|access denied|verify you are human|captcha|are you a robot/i.test(title) || bodyLen < 120) {
    out({ ok: false, blocked: true, reason: `status ${status}, ${bodyLen} chars`, ...base });
  } else {
    let loc = await page.evaluate(locate, inp.quote || "");
    if (!loc.found) {                      // شاید بخشی از متن بعد از اسکرول بار شود
      await page.evaluate(() => window.scrollTo(0, document.scrollingElement.scrollHeight)).catch(() => {});
      await sleep(1500);
      loc = await page.evaluate(locate, inp.quote || "");
    }
    if (!loc.found) {
      await page.evaluate(() => window.scrollTo(0, 0));
      await sleep(400);
      await page.evaluate(hideChrome);
      await page.screenshot({ path: path.join(inp.out, "shot.jpg"), type: "jpeg", quality: 85, animations: "disabled", caret: "hide" });
      out({ ok: false, notFound: true, reason: `جمله در متن صفحه (${loc.textLen} حرف) پیدا نشد`, y0: 0, shot: { w: vw, h: vh }, ...base });
    } else {
      let lines = await page.evaluate(lineRects);
      const docH = await page.evaluate(() => Math.max(document.scrollingElement.scrollHeight, document.body.scrollHeight));
      const top = lines[0][1];
      let y0 = Math.max(0, Math.round(top - 1.6 * vh)), viewportOnly = false;
      await page.evaluate(y => window.scrollTo(0, y), y0);
      await sleep(400);
      await page.evaluate(y => window.scrollTo(0, y), Math.max(0, top - 0.38 * vh));
      await sleep(900);
      if (await page.evaluate(() => window.scrollY) === 0 && top > vh) {   // صفحه‌ای که خودش اسکرول ندارد (ظرف داخلی)
        await page.evaluate(() => window.__hl.startContainer.parentElement.scrollIntoView({ block: "center" }));
        await sleep(700);
        viewportOnly = true;
      }
      lines = await page.evaluate(lineRects);
      await page.evaluate(hideChrome);
      await sleep(250);
      lines = await page.evaluate(lineRects);
      const docH2 = await page.evaluate(() => Math.max(document.scrollingElement.scrollHeight, document.body.scrollHeight));
      let clip, shot;
      if (viewportOnly) {
        const sy = await page.evaluate(() => window.scrollY);
        y0 = sy;
        shot = { w: vw, h: vh };
        await page.screenshot({ path: path.join(inp.out, "shot.jpg"), type: "jpeg", quality: 85, animations: "disabled", caret: "hide" });
      } else {
        const t0 = lines[0][1];
        y0 = Math.max(0, Math.round(t0 - 1.6 * vh));
        const y1 = Math.min(Math.max(docH, docH2), Math.round(t0 + 1.4 * vh));
        clip = { x: 0, y: y0, width: vw, height: Math.max(vh, y1 - y0) };
        shot = { w: vw, h: clip.height };
        await page.screenshot({ path: path.join(inp.out, "shot.jpg"), type: "jpeg", quality: 85, fullPage: true, clip, animations: "disabled", caret: "hide" });
      }
      const rel = lines.map(([x, y, w, h]) => [Math.round(x * 10) / 10, Math.round((y - y0) * 10) / 10, Math.round(w * 10) / 10, Math.round(h * 10) / 10]);
      out({ ok: true, how: loc.how, score: loc.score, dir: loc.dir, text: loc.text, lines: rel, target: rel[0][1], y0, shot, viewportOnly, ...base });
    }
  }
} catch (e) {
  out({ ok: false, error: true, reason: String(e && e.message || e).slice(0, 400) });
} finally {
  if (ctx) await ctx.close().catch(() => {});
}
