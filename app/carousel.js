/* ================= کاروسل و پست =================
   هر کاروسل چند اسلاید ۱۰۸۰×۱۳۵۰ است (۴:۵، بلندترین قاب عمودی فید). هر اسلاید یک کارت با ویرایشگر و پیش‌نمایش
   خودش، مثل استوری؛ پیش‌نمایش همان canvas خروجی است. متن با موتور story.js کشیده می‌شود (stLayout/stLines با box،
   الگوریتم دوجهتی، تأکید، اندازه‌ی بخش‌ها)، پس story.js باید قبل از این فایل بارگذاری شود.
   داده‌ها روی سرور است (app/carousel.py) و هر ذخیره فقط اسلایدهای عوض‌شده را می‌فرستد، تا گوشی و مک کار هم را پاک نکنند.
   ظاهر پیش‌فرض از کاروسل‌های خود پیج اندازه‌گیری شده (۲۰۲۶-۱۰-۰۶): سرمه‌ای تخت، متن سفید ضخیم راست‌چین،
   تأکید زرد، لوگوی سفید گوشه‌ی پایین-چپ؛ و کاور روشن با کمان سرمه‌ای و فلش برای فهرست‌ها. */

const CRW = 1080, CRH = 1350;
const CR_EDGE = 54;    // فاصله‌ی لوگو، شماره و آیدی از لبه
const CR_PAD = 90;     // حاشیه‌ی چپ و راست متن
const CR_GAP_IMG = 46;
const crHandle = () => (typeof S !== 'undefined' && S.profile && S.profile.handle) ? '@' + S.profile.handle : '@your.page';

const CR_BASE = {
  bgMode: 'solid', bg: '#1f2b3a', bg2: '#0f151d',
  fg: '#ffffff', hl: '#ffcc4d', hlMode: 'color',
  alt: 'none', altBg: '#ffffff', altFg: '#1f2b3a', altHl: '#1f2b3a',
  tSize: 68, tWeight: 800, tLh: 1.6, bSize: 48, bWeight: 600, bLh: 1.85, pgap: 0.8, coverScale: 1.2,
  align: 'right', valign: 'center',
  logo: 'corner', logoW: 0.2, logoOn: 'all', logoInk: 'auto',
  num: 'none', handle: '', swipe: 'none', ac: '#ffcc4d',
  deco: 'none', decoColor: '#8ecae6',
};
const CR_PRESETS = [
  { key: 'archive', name: 'برند من', s: {},
    note: 'رنگ اصلی برندت، متن سفید، رنگ تأکیدی، لوگو گوشه‌ی پایین' },
  { key: 'archive-tab', name: 'لوگو روی زبانه', s: { logo: 'tab', logoW: 0.19 },
    note: 'همان، با لوگو روی زبانه‌ی سفید گوشه‌ی پایین' },
  { key: 'archive-mid', name: 'لوگو وسط', s: { logo: 'bottom', logoW: 0.22 },
    note: 'همان، با لوگوی وسط پایین' },
  { key: 'light-arc', name: 'روشن با کمان', s: { bg: '$light', fg: '#22262e', hlMode: 'marker',
      tWeight: 900, coverScale: 1.55, swipe: 'arc', ac: '$bg' },
    note: 'روشن، متن تیره‌ی درشت، کمان رنگ برند با فلش روی کاور' },
  { key: 'alt', name: 'یک‌درمیان سفید', s: { align: 'center', alt: 'light', altFg: '$bg', altHl: '$bg' },
    note: 'اسلایدها یکی رنگ برند، یکی سفید؛ وسط‌چین' },
  { key: 'marker', name: 'ماژیکی', s: { hlMode: 'marker', tWeight: 900 },
    note: 'تأکید با نوار رنگی پشت کلمه‌ها' },
  { key: 'night', name: 'گرادیان', s: { bgMode: 'gradient', bg: '$bg', bg2: '$bg2', hl: '$alt',
      align: 'center', deco: 'frame', ac: '$alt' },
    note: 'از رنگ برند تا تیره، کادر نازک' },
  { key: 'cream', name: 'روشن', s: { bg: '$light', fg: '$bg', hlMode: 'marker', ac: '$bg' },
    note: 'زمینه‌ی روشن، متن به رنگ برند، ماژیک' },
];
// ** = تأکید
const CR_DEMO = {
  title: '۵ اشتباهی که باعث می‌شه **برند شخصی‌ات** دیده نشه',
  body: 'اشتباه اول: برای **همه** محتوا می‌سازی، پس برای هیچ‌کس نمی‌سازی.',
};
// دایره‌های رنگ: خنثی‌ها؛ crApplyBrand رنگ‌های پالت هسته‌ی برند را جلویشان می‌گذارد
const CR_SW = {
  bg: ['#1f2b3a', '#0f151d', '#020202', '#ebebeb', '#f3efe6', '#ffffff'],
  bg2: ['#0f151d', '#1f2b3a', '#020202'],
  fg: ['#ffffff', '#f3efe6', '#22262e', '#020202'],
  hl: ['#ffcc4d', '#8ecae6', '#ffffff'],
  altBg: ['#ffffff', '#ebebeb', '#f3efe6'],
  altFg: ['#22262e', '#020202'],
  altHl: ['#ffcc4d', '#22262e'],
  ac: ['#ffcc4d', '#8ecae6', '#ffffff'],
  decoColor: ['#8ecae6', '#ffcc4d', '#ffffff'],
};
// بعد از stLogos (که پالت برند را در ST_BASE و ST_PAL و ST_SW ریخته) صدا زده می‌شود
function crApplyBrand() {
  Object.assign(CR_BASE, { bg: ST_BASE.bg, bg2: ST_BASE.bg2, hl: ST_BASE.hl, ac: ST_BASE.hl, decoColor: ST_BASE.decoColor,
    altFg: ST_PAL.bg, altHl: ST_PAL.bg });
  for (const k of ['bg', 'bg2', 'fg', 'hl', 'decoColor'])
    CR_SW[k] = [...new Set([...ST_SW[k], ...CR_SW[k]])].slice(0, 10);
  CR_SW.ac = [...new Set([...ST_SW.hl, ...CR_SW.ac])].slice(0, 10);
  CR_SW.altFg = [...new Set([ST_PAL.bg, ...CR_SW.altFg])];
  CR_SW.altHl = [...new Set([ST_BASE.hl, ST_PAL.bg, ...CR_SW.altHl])];
}
const CR_NUM = new Set(['tSize', 'tWeight', 'tLh', 'bSize', 'bWeight', 'bLh', 'pgap', 'coverScale', 'logoW']);
const CR_LOGOW = { corner: 0.2, tab: 0.19, bottom: 0.22, top: 0.18 };
const CR_INLINE = new Set(['above', 'between', 'below', 'circle']);
const CR_PUBLISH_MAX = 10;

const CR = {
  deck: null, jobs: {}, known: new Set(), dirty: new Set(), meta: new Set(), structure: false,
  tSave: 0, saving: null, poll: 0, listPoll: 0, tGal: 0, saved: null, savedPreset: '',
  pending: null, openId: null, res: new Map(), names: {},
};
// go() آدرس را به ?s=carousel برمی‌گرداند؛ ?deck= همین اول گرفته می‌شود تا رفرش همان کاروسل را باز کند
(() => { const q = new URLSearchParams(location.search); if (q.get('s') === 'carousel' && q.get('deck')) CR.openId = q.get('deck'); })();
const CR_IMG = new Map();   // فایل کتابخانه ← Image
const crLS = (k, v) => { try { if (v === undefined) return localStorage.getItem(k); localStorage.setItem(k, v); } catch {} return null; };

/* ---------- کشیدن ---------- */
const crStyle = () => ({ ...CR_BASE, ...((CR.deck && CR.deck.style) || {}) });
// «$bg» و مانند آن = نقش رنگ برند (ST_PAL در story.js)
const crPreset = key => {
  const s = (CR_PRESETS.find(p => p.key === key) || CR_PRESETS[0]).s, out = { ...CR_BASE, preset: key };
  for (const [k, v] of Object.entries(s)) out[k] = typeof v === 'string' && v[0] === '$' ? (ST_PAL[v.slice(1)] || CR_BASE[k]) : v;
  return out;
};
const crSlideStyle = (s, i) => s.alt === 'light' && i % 2 === 1 ? { ...s, bgMode: 'solid', bg: s.altBg, fg: s.altFg, hl: s.altHl } : s;
const crFrame = html => stTrimLines(stParse(html || ''));
const crData = sl => ({ tF: crFrame(sl.title), bF: crFrame(sl.body), img: sl.img });
const crHas = f => f.some(l => stTxt(l).trim());

function crImg(file) {
  if (!file) return null;
  let im = CR_IMG.get(file);
  if (!im) {
    im = new Image(); CR_IMG.set(file, im);
    im.onload = () => crRenderUsing(file);
    im.src = '/carousel-media/' + encodeURIComponent(file);
  }
  return im.complete && im.naturalWidth ? im : null;
}
function crImgLoad(file) {
  const ready = crImg(file); if (ready || !file) return Promise.resolve(ready);
  const im = CR_IMG.get(file);
  return new Promise(r => { im.addEventListener('load', () => r(im), { once: true }); im.addEventListener('error', () => r(null), { once: true }); });
}
function crCover(ctx, im, x, y, w, h) {
  const r = Math.max(w / im.naturalWidth, h / im.naturalHeight), sw = w / r, sh = h / r;
  ctx.drawImage(im, (im.naturalWidth - sw) / 2, (im.naturalHeight - sh) / 2, sw, sh, x, y, w, h);
}
function crBg(ctx, s, d) {
  if (s.bgMode === 'gradient') {
    const g = ctx.createLinearGradient(0, 0, CRW * 0.35, CRH);
    g.addColorStop(0, s.bg); g.addColorStop(1, s.bg2); ctx.fillStyle = g;
  } else ctx.fillStyle = s.bg;
  ctx.fillRect(0, 0, CRW, CRH);
  const m = d.img && d.img.mode, im = m === 'bg' || m === 'full' ? crImg(d.img.file) : null;
  if (im) {
    crCover(ctx, im, 0, 0, CRW, CRH);
    if (m === 'bg') { ctx.fillStyle = stAlpha(s.bg, d.img.dim ?? 0.65); ctx.fillRect(0, 0, CRW, CRH); }
  }
  if (s.deco === 'frame') {
    ctx.strokeStyle = stAlpha(s.fg, 0.3); ctx.lineWidth = 3;
    stRR(ctx, 40, 40, CRW - 80, CRH - 80, 30); ctx.stroke();
  }
}
const crLogoOn = (s, i, n) => s.logo !== 'none' && (s.logoOn === 'all' || i === 0 || (s.logoOn === 'ends' && i === n - 1));
function crLogoBox(s, i, n) {
  if (!crLogoOn(s, i, n) || !ST.logos) return null;
  const tone = s.bgMode === 'gradient' ? (stLum(s.bg) + stLum(s.bg2)) / 2 : stLum(s.bg);
  const tab = s.logo === 'tab';
  const set = tab ? ST.logos.dark : (s.logoInk === 'auto' ? tone < 0.5 : s.logoInk === 'light') ? ST.logos.light : ST.logos.dark;
  if (!set) return null;
  const part = set.full, w = CRW * s.logoW, h = w * part.sh / part.sw;
  if (s.logo === 'bottom') return { part, w, h, x: (CRW - w) / 2, y: CRH - CR_EDGE - h, at: 'bottom', top: CRH - CR_EDGE - h };
  if (s.logo === 'top') return { part, w, h, x: CR_EDGE, y: CR_EDGE, at: 'top', bottom: CR_EDGE + h };
  if (tab) {   // زبانه‌ی سفید با گوشه‌ی گرد، چسبیده به گوشه‌ی پایین-چپ؛ لوگوی سرمه‌ای رویش
    const p = Math.round(w * 0.17), tw = w + 2 * p, th = h + 2 * p;
    return { part, w, h, x: p, y: CRH - p - h, at: 'bottom', top: CRH - th, tab: { w: tw, h: th } };
  }
  return { part, w, h, x: CR_EDGE, y: CRH - CR_EDGE - h, at: 'bottom', top: CRH - CR_EDGE - h };
}
// کادر متن، و جای شماره (بالا-چپ؛ اگر لوگو آن‌جاست پایین-چپ)، آیدی (بالا-راست) و فلش (پایین-راست)
function crBox(s, i, n, lg) {
  const numOn = s.num === 'num' && n > 1, handleOn = !!String(s.handle || '').trim();
  const numAt = lg && lg.at === 'top' ? 'bottom' : 'top', arrowOn = s.swipe === 'arrow' && i < n - 1;
  let top = 100, bottom = CRH - 100;
  if (lg && lg.at === 'top') top = Math.max(top, lg.bottom + 44);
  if ((numOn && numAt === 'top') || handleOn) top = Math.max(top, CR_EDGE + 84);
  if (lg && lg.at === 'bottom') bottom = Math.min(bottom, lg.top - 44);
  if ((numOn && numAt === 'bottom') || arrowOn) bottom = Math.min(bottom, CRH - CR_EDGE - 100);
  const x1 = i === 0 && s.swipe === 'arc' ? Math.round(CRW * 0.8) : CRW - CR_PAD;
  return { x: CR_PAD, w: x1 - CR_PAD, top, bottom, numOn, numAt, handleOn, arrowOn };
}
function crArrow(ctx, x, y, len, lw, color) {   // → (کاروسل به راست ورق می‌خورد)
  const t = len * 0.32;
  ctx.strokeStyle = color; ctx.lineWidth = lw; ctx.lineCap = 'round'; ctx.lineJoin = 'round';
  ctx.beginPath(); ctx.moveTo(x - len / 2, y); ctx.lineTo(x + len / 2, y);
  ctx.moveTo(x + len / 2 - t, y - t); ctx.lineTo(x + len / 2, y); ctx.lineTo(x + len / 2 - t, y + t); ctx.stroke();
}
function crChrome(ctx, s, i, n, lg, box) {
  if (lg) {
    if (lg.tab) {
      const { w, h } = lg.tab, y0 = CRH - h, r = Math.min(h * 0.55, 70);
      ctx.beginPath(); ctx.moveTo(0, y0); ctx.lineTo(w - r, y0); ctx.arcTo(w, y0, w, y0 + r, r);
      ctx.lineTo(w, CRH); ctx.lineTo(0, CRH); ctx.closePath(); ctx.fillStyle = '#ffffff'; ctx.fill();
    }
    ctx.drawImage(lg.part.img, lg.part.sx, lg.part.sy, lg.part.sw, lg.part.sh, lg.x, lg.y, lg.w, lg.h);
  }
  ctx.textBaseline = 'alphabetic';
  if (box.numOn) {
    ctx.font = `700 30px ${ST_FONT}`; ctx.fillStyle = stAlpha(s.fg, 0.72); ctx.direction = 'rtl'; ctx.textAlign = 'left';
    ctx.fillText(`${faNum(i + 1)} از ${faNum(n)}`, CR_EDGE, box.numAt === 'top' ? CR_EDGE + 30 : CRH - CR_EDGE);   // «۱ / ۴» در راست‌به‌چپ «۴ / ۱» دیده می‌شد
  }
  if (box.handleOn) {
    ctx.font = `600 28px ${ST_FONT}`; ctx.fillStyle = stAlpha(s.fg, 0.72); ctx.direction = 'ltr'; ctx.textAlign = 'right';
    ctx.fillText(String(s.handle).trim(), CRW - CR_EDGE, CR_EDGE + 30);
  }
  const ink = stLum(s.ac) > 0.6 ? ST_PAL.bg : '#ffffff';
  if (i === 0 && s.swipe === 'arc') {   // کمان بزرگ از لبه‌ی راست کاور با فلش
    const cy = CRH * 0.55;
    ctx.fillStyle = s.ac; ctx.beginPath(); ctx.ellipse(CRW * 1.3, cy, CRW * 0.46, CRH * 0.73, 0, 0, Math.PI * 2); ctx.fill();
    crArrow(ctx, CRW * 0.915, cy, 74, 9, ink);
  }
  if (box.arrowOn) {
    const r = 32, cx = CRW - CR_EDGE - r, cy = CRH - CR_EDGE - r;
    ctx.fillStyle = s.ac; ctx.beginPath(); ctx.arc(cx, cy, r, 0, Math.PI * 2); ctx.fill();
    crArrow(ctx, cx, cy, 30, 5, ink);
  }
}
function crInlineImg(ctx, im, x, y, w, h, mode, fit, s) {
  ctx.save();
  if (mode === 'circle') {
    ctx.beginPath(); ctx.arc(x + w / 2, y + h / 2, w / 2, 0, Math.PI * 2); ctx.closePath();
    ctx.save(); ctx.clip(); crCover(ctx, im, x, y, w, h); ctx.restore();
    ctx.lineWidth = 8; ctx.strokeStyle = s.hl;
    ctx.beginPath(); ctx.arc(x + w / 2, y + h / 2, w / 2 - 4, 0, Math.PI * 2); ctx.stroke();
  } else {
    stRR(ctx, x, y, w, h, 26); ctx.clip();
    if (fit === 'cover') crCover(ctx, im, x, y, w, h); else ctx.drawImage(im, x, y, w, h);
  }
  ctx.restore();
}
// تیتر، متن و تصویرِ داخل متن، پشت هم. اگر جا نشوند همه با هم کوچک می‌شوند (تا نصف)؛ تصویر هم تا ۲۶٪ کادر.
function crBlocks(ctx, d, i, s, box) {
  const hasT = crHas(d.tF), hasB = crHas(d.bF);
  const mode = d.img && CR_INLINE.has(d.img.mode) ? d.img.mode : '';
  const im = mode ? crImg(d.img.file) : null, ar = im ? im.naturalWidth / im.naturalHeight : 1;
  const avail = box.bottom - box.top;
  const tBase = s.tSize * (i === 0 ? s.coverScale : 1), bBase = s.bSize;
  const tS = { ...s, weight: s.tWeight, lh: s.tLh, pgap: 0.55 }, bS = { ...s, weight: s.bWeight, lh: s.bLh };
  const barH = s.deco === 'bar' && (hasT || hasB) ? 46 : 0;
  let k = 1, LT, LB, items, ih = 0, textH = 0, fits = true, gapTB = 0;
  for (;;) {
    const ts = Math.max(28, Math.round(tBase * k)), bs = Math.max(24, Math.round(bBase * k));
    LT = hasT ? stLayout(ctx, d.tF, tS, ts, box) : null;
    LB = hasB ? stLayout(ctx, d.bF, bS, bs, box) : null;
    gapTB = Math.max(24, bs * 0.7);
    items = [];
    if (LT) items.push({ k: 't', h: LT.h });
    if (LB) items.push({ k: 'b', h: LB.h });
    if (im) {
      const it = { k: 'i', h: 0 };
      if (mode === 'above' || mode === 'circle') items.unshift(it);
      else if (mode === 'between') items.splice(LT ? 1 : 0, 0, it); else items.push(it);
    }
    textH = barH + items.reduce((a, it, j) => a + it.h + (j ? (it.k === 'i' || items[j - 1].k === 'i' ? CR_GAP_IMG : gapTB) : 0), 0);
    fits = (!LT || LT.fits) && (!LB || LB.fits);
    if (im) {
      const want = mode === 'circle' ? Math.min(box.w * 0.44, avail * 0.38) : Math.min(box.w / ar, avail * 0.52);
      ih = Math.max(0, Math.min(want, avail - textH));
      if ((ih >= Math.min(want, avail * 0.26) && fits) || k <= 0.5) break;
    } else if ((textH <= avail && fits) || k <= 0.5) break;
    k = Math.round((k - 0.05) * 100) / 100;
  }
  let iw = 0;
  if (im) {
    if (mode === 'circle') iw = ih;
    else if (d.img.fit === 'cover') iw = box.w;
    else { iw = Math.min(box.w, ih * ar); ih = iw / ar; }
    items.find(it => it.k === 'i').h = ih;
  }
  const total = textH + ih;
  let y = s.valign === 'top' ? box.top : box.top + Math.max(0, (avail - total) / 2);
  if (barH) {
    ctx.fillStyle = s.decoColor; const w = 120;
    stRR(ctx, s.align === 'center' ? box.x + (box.w - w) / 2 : box.x + box.w - w, y, w, 14, 7); ctx.fill();
    y += barH;
  }
  items.forEach((it, j) => {
    if (j) y += it.k === 'i' || items[j - 1].k === 'i' ? CR_GAP_IMG : gapTB;
    if (it.k === 't') stLines(ctx, LT, tS, y, box);
    else if (it.k === 'b') stLines(ctx, LB, bS, y, box);
    else if (ih > 0) crInlineImg(ctx, im, box.x + (box.w - iw) / 2, y, iw, ih, mode, d.img.fit, s);
    y += it.h;
  });
  return { overflow: total > avail + 1 || !fits || (im && ih < 40), shrunk: k < 1 };
}
function crDraw(ctx, d, i, n, s0) {
  const s = crSlideStyle(s0, i);
  crBg(ctx, s, d);
  const lg = crLogoBox(s, i, n), box = crBox(s, i, n, lg);
  const r = d.img && d.img.mode === 'full' ? { overflow: false, shrunk: false } : crBlocks(ctx, d, i, s, box);
  crChrome(ctx, s, i, n, lg, box);
  return r;
}
function crPaint(cv, d, i, n, s, scale = 1) {
  const w = Math.round(CRW * scale), h = Math.round(CRH * scale);
  if (cv.width !== w) cv.width = w;
  if (cv.height !== h) cv.height = h;
  const ctx = cv.getContext('2d');
  ctx.setTransform(scale, 0, 0, scale, 0, 0);
  ctx.clearRect(0, 0, CRW, CRH);
  return crDraw(ctx, d, i, n, s);
}
const crDemoData = () => ({ tF: stDemo(CR_DEMO.title), bF: [], img: null });

/* ---------- صفحه‌ی اصلی: ساخت با هوش مصنوعی + فهرست کاروسل‌ها ---------- */
async function viewCarousel() {
  clearTimeout(CR.poll); clearTimeout(CR.listPoll);
  $('#page').innerHTML = '<div class="empty">در حال بارگذاری…</div>';
  const [st, b] = await Promise.all([api('/api/carousel/style'), api('/api/brand'), stFonts(), stLogos()]);
  crApplyBrand();
  for (const c of (b && b.fields && b.fields.colors && b.fields.colors.v) || []) if (c.hex) CR.names[c.hex.toLowerCase()] = c.name;
  CR.saved = st && st.style ? { ...CR_BASE, ...st.style } : null;
  CR.savedPreset = (st && st.preset) || '';
  const want = CR.openId; CR.openId = null;
  if (want) return crOpen(want);
  crHome();
}

function crForm() {
  let f = {};
  try { f = JSON.parse(crLS('cr-form') || '{}') || {}; } catch {}
  f = { src: 'text', text: '', idea: '', count: '0', keep: false, web: false, images: true, notes: '', ...f };
  if (CR.pending && CR.pending.idea) { f.src = 'idea'; f.idea = CR.pending.idea; CR.pending = null; }
  return f;
}
function crReadForm() {
  return { src: $('.cr-src .on')?.dataset.crsrc || 'text', text: $('#crText').value, idea: $('#crIdea').value,
    count: $('#crCount').value, keep: $('#crKeep').checked, web: $('#crWeb').checked, images: $('#crImgs').checked,
    notes: $('#crNotes').value };
}
const crSaveForm = () => crLS('cr-form', JSON.stringify(crReadForm()));
const crIdeaLabel = it => {
  const st = it.steps || {}, got = [st.analyze && 'تحلیل', st.enrich && 'پژوهش', st.produce && 'ریلز'].filter(Boolean);
  return it.title + (got.length ? ` (${got.join('، ')})` : '');
};

async function crHome() {
  CR.deck = null;
  history.replaceState(null, '', '?s=carousel');
  const f = crForm();
  const ideas = (typeof S !== 'undefined' && S.ideas) || [];
  const counts = [['0', 'خودکار (۵ تا ۸)'], ...[3, 4, 5, 6, 7, 8, 9, 10].map(n => [String(n), faNum(n) + ' اسلاید'])];
  $('#page').innerHTML = `
    <div class="cr-wrap cr-home">
      <div class="page-head"><h2>کاروسل و پست</h2>
        <p>هر اسلاید یک تصویر ۱۰۸۰×۱۳۵۰ است. خودت اسلاید به اسلاید بساز، یا متن و ایده‌ات را بده تا Claude با هسته‌ی برندت بسازد؛ بعد ویرایش می‌کنی، اسلایدها را دانلود می‌کنی و خودت در اینستاگرام منتشر می‌کنی.</p></div>
      <section class="panel cr-ai">
        <h3>ساخت با هوش مصنوعی</h3>
        <div class="cr-src">
          <button class="st-chip${f.src === 'text' ? ' on' : ''}" data-crsrc="text">متن یا ایده‌ی خودم</button>
          <button class="st-chip${f.src === 'idea' ? ' on' : ''}" data-crsrc="idea">از بانک ایده</button>
        </div>
        <textarea id="crText" class="cap-text" dir="rtl" ${f.src === 'idea' ? 'hidden' : ''}
          placeholder="یک ایده‌ی کوتاه بنویس («۵ اشتباه رایج در رزومه‌ی مهاجرها») یا یک متن کامل بچسبان تا به اسلاید تبدیل شود…">${esc(f.text)}</textarea>
        <select id="crIdea" class="cr-select" ${f.src === 'idea' ? '' : 'hidden'}>
          <option value="">— یک ایده انتخاب کن —</option>
          ${ideas.map(it => `<option value="${esc(it.id)}"${it.id === f.idea ? ' selected' : ''}>${esc(crIdeaLabel(it))}</option>`).join('')}
        </select>
        <div class="cr-opts">
          <label class="cr-opt">تعداد اسلاید <select id="crCount" class="cr-select sm">${counts.map(([v, l]) => `<option value="${v}"${v === String(f.count) ? ' selected' : ''}>${l}</option>`).join('')}</select></label>
          <label class="st-check cr-keep" ${f.src === 'idea' ? 'hidden' : ''}><input type="checkbox" id="crKeep"${f.keep ? ' checked' : ''}> متنم عیناً بماند؛ فقط بین اسلایدها تقسیمش کن</label>
          <label class="st-check"><input type="checkbox" id="crWeb"${f.web ? ' checked' : ''}> برای عدد و منبع در وب بگرد (کندتر)</label>
          <label class="st-check"><input type="checkbox" id="crImgs"${f.images ? ' checked' : ''}> برای اسلایدهایی که لازم دارند تصویر بساز</label>
        </div>
        <textarea id="crNotes" class="cap-text cr-notes" dir="rtl" placeholder="توضیح اضافه برای Claude (اختیاری): مثلاً «اسلاید آخر دعوت به وبینار جمعه باشه»، «عکس من رو روی کاور بذار»…">${esc(f.notes)}</textarea>
        <div class="rowbar cr-gorow">
          <button class="btn primary" data-cra="gen">ساخت کاروسل</button>
          <span class="grow"></span>
          <button class="btn" data-cra="blank">+ کاروسل خالی؛ خودم اسلاید به اسلاید می‌سازم</button>
        </div>
        <p class="cap-hint">Claude با هسته‌ی برندت می‌نویسد، معمولاً ۱ تا ۳ دقیقه. تصویرها با Gemini ساخته می‌شوند، هر کدام حدود ۱۰ ثانیه و چند سنت. لوگو طبق استایل روی اسلایدها می‌آید؛ عکس‌های خودت را در «کتابخانه‌ی تصویر» هر اسلاید آپلود کن تا Claude هم بتواند از آن‌ها استفاده کند.</p>
      </section>
      <section class="cr-listwrap"><h3>کاروسل‌هایت</h3><div id="crDecks" class="cr-decks"><div class="cr-dim">در حال بارگذاری…</div></div></section>
    </div>`;
  crBind($('.cr-wrap'));
  crLoadList();
}
async function crLoadList() {
  clearTimeout(CR.listPoll);
  const r = await api('/api/carousel/list'), box = $('#crDecks');
  if (!box || !$('.cr-home')) return;
  const decks = (r && r.decks) || [];
  box.innerHTML = decks.length ? decks.map(d => {
    const pub = d.published && d.published[0];
    return `<article class="cr-deck" data-crdeck="${esc(d.id)}">
      <canvas data-crc="${esc(d.id)}"></canvas>
      <div class="cr-dmeta"><b>${esc(d.title)}</b>
        <span>${faNum(d.n)} اسلاید، ${esc(faNum((d.updated || '').slice(0, 16)))}</span>
        ${d.generating ? '<span class="cr-tag run">در حال ساخت…</span>' : d.error ? '<span class="cr-tag err">ساخت ناتمام ماند</span>' : ''}
        ${pub ? `<a class="cr-tag ok" href="${esc(pub.permalink || '#')}" target="_blank" rel="noopener" data-stop>منتشر شد ↗</a>` : ''}</div>
      <div class="cr-dact"><button class="st-tool" data-cra="copy" data-id="${esc(d.id)}">کپی</button>
        <button class="st-tool st-del" data-cra="del" data-id="${esc(d.id)}">حذف</button></div>
    </article>`;
  }).join('') : '<div class="cr-dim">هنوز کاروسلی نساخته‌ای.</div>';
  for (const cv of $$('canvas[data-crc]', box)) {
    const d = decks.find(x => x.id === cv.dataset.crc);
    const data = d.cover && (d.cover.title || d.cover.body || d.cover.img) ? crData(d.cover) : crDemoData();
    crPaint(cv, data, 0, Math.max(d.n, 1), { ...CR_BASE, ...(d.style || CR.saved || {}) }, 0.25);
  }
  if (decks.some(d => d.generating)) CR.listPoll = setTimeout(crLoadList, 3000);
}

async function crGenerate() {
  const f = crReadForm();
  if (f.src === 'text' && f.text.trim().length < 3) return toast('متن یا ایده را بنویس');
  if (f.src === 'idea' && !f.idea) return toast('یک ایده انتخاب کن');
  const btn = $('[data-cra="gen"]'); btn.disabled = true;
  const r = await post('/api/carousel/generate', { mode: f.src, text: f.text, idea: f.idea, count: Number(f.count),
    keep: f.keep, web: f.web, images: f.images, notes: f.notes });
  if (!r.ok) { btn.disabled = false; return toast(r.data.error || 'شروع نشد'); }
  crLS('cr-form', JSON.stringify({ ...f, text: '', notes: '' }));   // متن کامل در خود کاروسل (source) می‌ماند
  crOpen(r.data.id);
}

/* ---------- ویرایشگر یک کاروسل ---------- */
async function crOpen(id) {
  const r = await api(`/api/carousel/deck?id=${encodeURIComponent(id)}`);
  if (!r || !r.deck) { toast('این کاروسل پیدا نشد'); return crHome(); }
  CR.deck = r.deck; CR.jobs = r.jobs || {}; CR.res.clear();
  CR.known = new Set(r.deck.slides.map(s => s.id)); CR.dirty.clear(); CR.meta.clear(); CR.structure = false;
  if (!CR.deck.style) { CR.deck.style = CR.saved ? { ...CR.saved } : crPreset('archive'); CR.meta.add('style'); crQueue(); }
  history.replaceState(null, '', `?s=carousel&deck=${encodeURIComponent(id)}`);
  crEditor();
  crWatch();
}
function crEditor() {
  const d = CR.deck;
  $('#page').innerHTML = `
    <div class="cr-wrap cr-edit">
      <div class="cr-top">
        <button class="btn" data-cra="home">→ همه‌ی کاروسل‌ها</button>
        <input id="crTitle" class="cr-title" value="${esc(d.title || '')}" placeholder="اسم این کاروسل (فقط برای خودت)">
        <span id="crSaved" class="cr-saved"></span>
        <span class="grow"></span>
        <button class="btn" data-cra="dlall">دانلود همه</button>
        <button class="btn primary" data-cra="copycap" title="کپشن و هشتگ‌ها را کپی می‌کند تا در اینستاگرام بچسبانی">کپی کپشن</button>
      </div>
      ${ST.fontOK ? '' : '<div class="st-warn">فونت وزیرمتن بارگذاری نشد و خروجی با فونت دیگری کشیده می‌شود. صفحه را یک بار تازه کن.</div>'}
      <div id="crGenBox"></div>
      <div id="crPubBox"></div>
      <div class="cr-layout"${CR.jobs.gen && CR.jobs.gen.state === 'running' && !d.slides.length ? ' hidden' : ''}>
        <section class="cr-main">
          <div id="crSlides" class="cr-slides"></div>
          <div class="st-listbar">
            <button class="btn" data-cra="add">+ اسلاید بعدی</button>
            <span class="st-grow"></span>
            <span id="crCountNote" class="cr-dim"></span>
          </div>
          <p class="st-hint">بخشی از متن را انتخاب کن: «تأکید» یا <kbd>⌘B</kbd> رنگی‌اش می‌کند؛ «بزرگ‌تر» و «کوچک‌تر» (<kbd>⌘⇧.</kbd> و <kbd>⌘⇧,</kbd>) اندازه‌اش را پله‌پله عوض می‌کنند · اسلاید اول کاور است و تیترش درشت‌تر کشیده می‌شود · اگر متن جا نشود همه‌چیز با هم کوچک می‌شود · متنی که بچسبانی و خطی با فقط «---» داشته باشد، خودش به چند اسلاید تقسیم می‌شود</p>
          <section class="panel cr-cap">
            <div class="cr-caphead"><h3>کپشن و هشتگ‌ها</h3><span class="st-grow"></span><span id="crCapCount" class="cr-dim"></span></div>
            <textarea id="crCaption" class="cap-text" dir="rtl" placeholder="کپشن پست؛ خط اولش همان چیزی است که قبل از «بیشتر» دیده می‌شود…">${esc(d.caption || '')}</textarea>
            <input id="crTags" class="cap-input" dir="auto" value="${esc(d.hashtags || '')}" placeholder="#هشتگ‌ها با فاصله از هم">
            <div class="cr-regen">
              <input id="crCapNote" class="cap-input" placeholder="نظرت برای بازنویسی کپشن و هشتگ‌ها (اختیاری)…">
              <button class="btn" data-cra="capregen">بازنویسی با Claude</button>
              <button class="btn" data-cra="capundo"${d.prevCaption ? '' : ' hidden'}>↶ نسخه‌ی قبل</button>
            </div>
            <p class="cr-last" id="crCapLast" hidden></p>
          </section>
          ${d.note ? `<p class="cr-note">یادداشت Claude: ${esc(d.note)}</p>` : ''}
        </section>
        <aside class="cr-side"><div id="crCtl" class="st-ctl"></div></aside>
      </div>
    </div>`;
  crBind($('.cr-wrap'));
  const box = $('#crSlides');
  for (const sl of d.slides) box.appendChild(crCard(sl));
  crNumber(); crCtl(); crCapCount(); crShowJobs(); crShowPub(); crRenderAll();
  const ta = $('#crCaption'); if (window.fitHeight) { fitHeight(ta); }
}
const crSlide = sid => CR.deck && CR.deck.slides.find(s => s.id === sid);
const crCardOf = sid => $(`.cr-slide[data-sid="${CSS.escape(sid)}"]`);
function crCard(sl) {
  const el = document.createElement('article');
  el.className = 'cr-slide'; el.dataset.sid = sl.id;
  el.innerHTML = `
    <div class="cr-sedit">
      <div class="cr-shead">
        <b class="cr-snum"></b><span class="cr-role" hidden></span><span class="st-grow"></span>
        <button class="st-tool" data-crs="hl" title="Cmd+B">تأکید</button>
        <button class="st-tool" data-crs="big" title="Cmd+Shift+.">بزرگ‌تر</button>
        <button class="st-tool" data-crs="small" title="Cmd+Shift+,">کوچک‌تر</button>
        <span class="cr-tsep"></span>
        <button class="st-tool" data-crs="up" title="یکی جلوتر">↑</button>
        <button class="st-tool" data-crs="down" title="یکی عقب‌تر">↓</button>
        <button class="st-tool" data-crs="dup" title="یک کپی بعد از همین اسلاید">کپی</button>
        <button class="st-tool st-del" data-crs="del" title="حذف این اسلاید">✕</button>
      </div>
      <span class="cr-lab">تیتر</span>
      <div class="st-ed cr-t" contenteditable="true" dir="rtl" spellcheck="false" data-ph="تیتر این اسلاید…"></div>
      <span class="cr-lab">متن</span>
      <div class="st-ed cr-b" contenteditable="true" dir="rtl" spellcheck="false" data-ph="متن این اسلاید (اختیاری)…"></div>
      <div class="cr-imgrow"></div>
      <div class="cr-regen">
        <input class="cap-input cr-note" placeholder="نظرت برای بازنویسی همین اسلاید (اختیاری)…">
        <button class="btn" data-crs="regen">بازنویسی با Claude</button>
        <button class="btn" data-crs="undo" hidden>↶ نسخه‌ی قبل</button>
      </div>
      <p class="cr-last" hidden></p>
      <p class="st-fnote"></p>
    </div>
    <div class="cr-frame">
      <div class="cr-cvwrap"><canvas></canvas><span class="st-badge" hidden>نمونه</span>
        <div class="cr-busy" hidden><i class="spin"></i><span></span></div></div>
      <div class="st-fbar"><button class="btn" data-crs="dl">دانلود</button></div>
    </div>`;
  crFill(el, sl);
  return el;
}
function crFill(el, sl) {   // متن و تصویر اسلاید از روی داده (بعد از ساخت، بازنویسی یا برگشت)
  for (const [cls, k] of [['.cr-t', 'title'], ['.cr-b', 'body']]) {
    const ed = $(cls, el);
    ed.innerHTML = stHTML(stTrimLines(stParse(sl[k] || '')));
    ed.classList.toggle('is-empty', !ed.textContent.trim());
  }
  $('[data-crs="undo"]', el).hidden = !sl.prev;
  const last = (sl.notes || []).slice(-1)[0], p = $('.cr-last', el);
  p.hidden = !last; p.textContent = last ? `آخرین نظرت: ${last.t}` : '';
  crImgRow(el, sl);
}
function crImgRow(el, sl) {
  const box = $('.cr-imgrow', el), im = sl.img;
  if (!im) {
    box.innerHTML = `<button class="st-tool" data-crs="pick">+ تصویر یا عکس</button>`
      + (sl.imgPrompt ? `<div class="cr-sugg"><span>پیشنهاد Claude برای تصویر این اسلاید:</span>
          <textarea class="cr-iprompt" dir="ltr" rows="2">${esc(sl.imgPrompt)}</textarea>
          <button class="st-tool" data-crs="mkimg">ساخت این تصویر با Gemini</button></div>` : '');
    return;
  }
  const chips = (k, opts) => opts.map(([v, l]) =>
    `<button class="st-chip${String(im[k]) === v ? ' on' : ''}" data-crimg="${k}" data-v="${v}">${l}</button>`).join('');
  box.innerHTML = `
    <img class="cr-thumb" src="/carousel-media/${encodeURIComponent(im.file)}" alt="">
    <div class="cr-imgctl">
      <div class="st-in">${chips('mode', [['below', 'زیر متن'], ['above', 'بالای متن'], ['between', 'بین تیتر و متن'],
        ['circle', 'دایره'], ['bg', 'زمینه'], ['full', 'تمام‌صفحه']])}</div>
      <div class="st-in">${im.mode === 'bg'
        ? `<span class="cr-dim">پررنگیِ لایه‌ی رنگ</span><input type="range" data-crimg="dim" min="0" max="0.9" step="0.05" value="${im.dim ?? 0.65}">`
        : im.mode === 'full' || im.mode === 'circle' ? '' : chips('fit', [['contain', 'کل تصویر'], ['cover', 'پر کردن عرض']])}
        <span class="st-grow"></span>
        <button class="st-tool" data-crs="pick">عوض کردن</button>
        <button class="st-tool st-del" data-crs="noimg">برداشتن تصویر</button></div>
    </div>`;
}
function crNumber() {
  const all = $$('.cr-slide'), n = all.length;
  all.forEach((el, i) => {
    $('.cr-snum', el).textContent = `اسلاید ${faNum(i + 1)}`;
    const r = $('.cr-role', el), role = i === 0 ? 'کاور' : i === n - 1 && n > 1 ? 'آخر' : '';
    r.hidden = !role; r.textContent = role;
    $('[data-crs="up"]', el).disabled = i === 0;
    $('[data-crs="down"]', el).disabled = i === n - 1;
  });
  const note = $('#crCountNote');
  if (note) note.textContent = n > CR_PUBLISH_MAX ? `${faNum(n)} اسلاید؛ اینستاگرام از راه API حداکثر ${faNum(CR_PUBLISH_MAX)} اسلاید را منتشر می‌کند.` : `${faNum(n)} اسلاید`;
}
// پیش‌نمایش یک اسلاید از روی ویرایشگرهای خودش (نه داده‌ی ذخیره‌شده) تا تایپ همان لحظه دیده شود
function crRenderCard(el) {
  if (!el || !el.isConnected) return;
  const all = $$('.cr-slide'), i = all.indexOf(el), n = all.length, sl = crSlide(el.dataset.sid);
  if (!sl) return;
  const tF = stTrimLines(stRead($('.cr-t', el))), bF = stTrimLines(stRead($('.cr-b', el)));
  const empty = !crHas(tF) && !crHas(bF) && !sl.img;
  const demo = empty && n === 1;
  const r = crPaint($('canvas', el), demo ? crDemoData() : { tF, bF, img: sl.img }, i, n, crStyle());
  CR.res.set(sl.id, { ...r, empty });
  $('.st-badge', el).hidden = !demo;
  $('[data-crs="dl"]', el).disabled = empty || !ST.fontOK;
  const full = sl.img && sl.img.mode === 'full';
  $('.st-fnote', el).textContent = demo ? 'پیش‌نمایش با متن کاور یکی از کاروسل‌های خودت است، فقط برای دیدن استایل.'
    : full && (crHas(tF) || crHas(bF)) ? 'در حالت «تمام‌صفحه» متن روی تصویر نمی‌آید.'
    : r.overflow ? 'متن برای این اسلاید زیاد است و جا نمی‌شود؛ کوتاهش کن یا بخشی را به اسلاید تازه ببر.'
    : r.shrunk ? 'برای جا شدن، اندازه‌ی متن این اسلاید کوچک‌تر کشیده شد.' : '';
}
function crRenderAll() {
  $$('.cr-slide').forEach(crRenderCard);
  clearTimeout(CR.tGal); CR.tGal = setTimeout(crRenderGal, 60);
}
function crRenderUsing(file) {
  for (const el of $$('.cr-slide')) { const sl = crSlide(el.dataset.sid); if (sl && sl.img && sl.img.file === file) crRenderCard(el); }
  if ($('.cr-home')) crLoadList();
  clearTimeout(CR.tGal); CR.tGal = setTimeout(crRenderGal, 60);
}

/* ---------- ذخیره (فقط بخش‌های عوض‌شده) ---------- */
function crSavedNote(t) { const s = $('#crSaved'); if (s) s.textContent = t; }
function crQueue() { clearTimeout(CR.tSave); CR.tSave = setTimeout(crFlush, 700); crSavedNote('ذخیره…'); }
const crClean = html => stHTML(stTrimLines(stParse(html || '')));   // خط خالیِ دو سر ذخیره نمی‌شود (هر رفت‌وبرگشت یکی اضافه می‌کرد)
function crBody() {
  const d = CR.deck;
  if (!d || (!CR.dirty.size && !CR.meta.size && !CR.structure)) return null;
  const body = { id: d.id };
  if (CR.dirty.size) body.slides = d.slides.filter(s => CR.dirty.has(s.id)).map(s => ({ id: s.id, title: crClean(s.title),
    body: crClean(s.body), img: s.img || null, imgPrompt: s.imgPrompt || '' }));
  if (CR.structure) { body.order = d.slides.map(s => s.id); body.known = [...CR.known]; }
  for (const k of CR.meta) body[k] = d[k];
  CR.dirty.clear(); CR.meta.clear(); CR.structure = false;
  return body;
}
async function crFlush() {
  clearTimeout(CR.tSave);
  while (CR.saving) await CR.saving;
  const body = crBody(), d = CR.deck;
  if (!body) return true;
  CR.saving = post('/api/carousel/save', body).then(r => {
    if (!r.ok) {
      crSavedNote('ذخیره نشد'); toast(r.data.error || 'ذخیره نشد');
      (body.slides || []).forEach(s => CR.dirty.add(s.id));
      ['title', 'caption', 'hashtags', 'style'].forEach(k => { if (k in body) CR.meta.add(k); });
      if (body.order) CR.structure = true;
      return false;
    }
    d.updated = r.data.updated; d.slides.forEach(s => CR.known.add(s.id));
    if (CR.deck === d && !CR.dirty.size && !CR.meta.size) crSavedNote('✓ ذخیره شد');
    return true;
  }).finally(() => { CR.saving = null; });
  return CR.saving;
}
addEventListener('pagehide', () => {   // رفرش یا بستن صفحه وسط تایپ
  const body = crBody();
  if (body) navigator.sendBeacon('/api/carousel/save', new Blob([JSON.stringify(body)], { type: 'text/plain;charset=UTF-8' }));
});
addEventListener('visibilitychange', () => { if (document.visibilityState === 'hidden') crFlush(); });

/* ---------- کارهای پس‌زمینه (ساخت، بازنویسی، تصویر، انتشار) ---------- */
function crWatch() {
  clearTimeout(CR.poll);
  const did = CR.deck && CR.deck.id;
  const tick = async () => {
    if (!CR.deck || CR.deck.id !== did || !$('.cr-edit')) return;
    const r = await api(`/api/carousel/status?id=${encodeURIComponent(did)}`);
    if (!CR.deck || CR.deck.id !== did) return;
    const jobs = {};
    for (const [k, v] of Object.entries((r && r.jobs) || {})) jobs[k.slice(did.length + 1)] = v;
    const before = CR.jobs; CR.jobs = jobs;
    const ended = Object.keys(jobs).filter(k => before[k] && before[k].state === 'running' && jobs[k].state !== 'running');
    const progressed = jobs.gen && jobs.gen.state === 'running' && !CR.deck.slides.length;
    if (ended.length || progressed) await crRefresh(ended);
    crShowJobs();
    if (Object.values(jobs).some(j => j.state === 'running')) CR.poll = setTimeout(tick, 1500);
  };
  tick();
}
// بعد از تمام شدن یک کار، فقط همان بخش از روی سرور تازه می‌شود؛ تایپ اسلایدهای دیگر دست نمی‌خورد
async function crRefresh(ended) {
  const d = CR.deck, r = await api(`/api/carousel/deck?id=${encodeURIComponent(d.id)}`);
  if (!r || !r.deck || CR.deck !== d) return;
  const fresh = r.deck;
  if (!d.slides.length && fresh.slides.length) {   // متن اسلایدها رسید
    if (CR.dirty.size || CR.meta.size) await crFlush();
    CR.deck = fresh; CR.known = new Set(fresh.slides.map(s => s.id));
    if (!fresh.style) { fresh.style = d.style; CR.meta.add('style'); crQueue(); }
    return crEditor();
  }
  if (ended.includes('gen')) {   // تصویرهای ساخته‌شده؛ تایپ در جریان دست نمی‌خورد
    for (const f of fresh.slides) {
      const mine = d.slides.find(s => s.id === f.id), el = crCardOf(f.id);
      if (!mine || JSON.stringify(mine.img) === JSON.stringify(f.img)) continue;
      mine.img = f.img; mine.imgPrompt = f.imgPrompt;
      if (el) { crImgRow(el, mine); crRenderCard(el); }
    }
  }
  for (const k of ended) {
    if (k === 'caption') {
      d.caption = fresh.caption; d.hashtags = fresh.hashtags; d.prevCaption = fresh.prevCaption; d.captionNotes = fresh.captionNotes;
      $('#crCaption').value = d.caption || ''; $('#crTags').value = d.hashtags || ''; crCapCount();
      $('[data-cra="capundo"]').hidden = !d.prevCaption;
      const last = (d.captionNotes || []).slice(-1)[0], p = $('#crCapLast');
      p.hidden = !last; p.textContent = last ? `آخرین نظرت: ${last.t}` : '';
      continue;
    }
    if (k === 'publish') { d.published = fresh.published; d.pending = fresh.pending; crShowPub(); continue; }
    const sid = k.startsWith('img-') ? k.slice(4) : k, f = fresh.slides.find(s => s.id === sid), at = d.slides.findIndex(s => s.id === sid);
    if (!f || at < 0) continue;
    const mine = d.slides[at];
    if (k.startsWith('img-')) { mine.img = f.img; mine.imgPrompt = f.imgPrompt; }
    else Object.assign(mine, { title: f.title, body: f.body, prev: f.prev, notes: f.notes });
    const el = crCardOf(sid);
    if (el) { if (k.startsWith('img-')) crImgRow(el, mine); else crFill(el, mine); crRenderCard(el); }
  }
}
function crShowJobs() {
  const j = CR.jobs, gb = $('#crGenBox');
  if (gb) {
    const g = j.gen;
    gb.innerHTML = g && g.state === 'running'
      ? `<div class="build-status"><div class="build-step"><span class="spin"></span>${esc(g.step || 'در حال ساخت…')}
           <span class="st-grow"></span><span class="cr-dim">${faNum(Math.max(0, Math.round((Date.now() / 1000 - (g.started || Date.now() / 1000)))))} ثانیه</span></div></div>`
      : g && g.state === 'error'
        ? `<div class="build-status err">${esc(g.error || 'ساخت ناتمام ماند.')}
             <div class="rowbar" style="margin:10px 0 0"><button class="btn" data-cra="regenall">دوباره بساز</button></div></div>`
        : g && g.state === 'done' && g.warn ? `<div class="build-status">کاروسل ساخته شد، ولی بعضی تصویرها ساخته نشدند: ${esc(g.warn)}</div>`
        : !g && CR.deck && !CR.deck.slides.length && ['text', 'idea'].includes((CR.deck.source || {}).kind)
          ? `<div class="build-status err">ساخت این کاروسل نیمه‌کاره ماند (احتمالاً استودیو وسط کار ری‌استارت شد).
               <div class="rowbar" style="margin:10px 0 0"><button class="btn" data-cra="regenall">دوباره بساز</button></div></div>` : '';
  }
  for (const el of $$('.cr-slide')) {
    const sid = el.dataset.sid, rj = j[sid], ij = j['img-' + sid];
    const run = (rj && rj.state === 'running') ? rj : (ij && ij.state === 'running') ? ij : null;
    const busy = $('.cr-busy', el);
    busy.hidden = !run; $('span', busy).textContent = run ? (run.step || 'در حال کار…') : '';
    $$('.st-ed', el).forEach(e => e.contentEditable = run ? 'false' : 'true');
    $$('[data-crs="regen"],[data-crs="undo"],[data-crs="mkimg"],[data-crs="pick"]', el).forEach(b => (b.disabled = !!run));
    const err = rj && rj.state === 'error' ? rj.error : ij && ij.state === 'error' ? ij.error : '';
    const fn = $('.st-fnote', el);
    if (err && !run) fn.textContent = err;
  }
  const cj = j.caption, cb = $('[data-cra="capregen"]');
  if (cb) { cb.disabled = !!(cj && cj.state === 'running'); cb.textContent = cj && cj.state === 'running' ? 'در حال بازنویسی…' : 'بازنویسی با Claude'; }
  if (cj && cj.state === 'error') toast(cj.error);
  crShowPub();
}
function crShowPub() {
  const box = $('#crPubBox'); if (!box || !CR.deck) return;
  const d = CR.deck, pj = CR.jobs.publish, pub = (d.published || []).slice(-1)[0];
  let h = '';
  if (pj && pj.state === 'running') h = `<div class="build-status"><div class="build-step"><span class="spin"></span>${esc(pj.step || 'در حال انتشار…')}</div></div>`;
  else if (pj && pj.state === 'error') h = `<div class="build-status err">${esc(pj.error)}
      ${pj.retry || d.pending ? '<div class="rowbar" style="margin:10px 0 0"><button class="btn" data-cra="retry">دوباره امتحان کن (همان پست)</button><button class="btn" data-cra="forget">بی‌خیال</button></div>' : ''}</div>`;
  else if (pj && pj.state === 'done' && pj.dry) h = `<div class="build-status">✓ آزمایش موفق بود: اسلایدها آپلود شدند و اینستاگرام پست را ساخت، ولی منتشر نشد.</div>`;
  if (pub) h += `<div class="cr-pubok">✓ منتشر شد، ${esc(faNum((pub.at || '').slice(0, 16)))}${pub.permalink ? ` — <a href="${esc(pub.permalink)}" target="_blank" rel="noopener">دیدن در اینستاگرام ↗</a>` : ''}</div>`;
  box.innerHTML = h;
  const m = $('#crPubStatus');
  if (m) m.innerHTML = h || '';
}

/* ---------- رویدادها ---------- */
function crBind(wrap) {
  const edOf = t => t && t.closest ? t.closest('.cr-slide .st-ed') : null;
  wrap.addEventListener('paste', e => {   // فقط متن ساده؛ خطی که فقط «---» دارد اسلاید تازه می‌سازد
    const ed = edOf(e.target); if (!ed) return;
    e.preventDefault();
    const parts = [[]];
    for (const line of (e.clipboardData || window.clipboardData).getData('text/plain').replace(/\r/g, '').split('\n'))
      /^\s*[-–—_]{3,}\s*$/.test(line) ? parts.push([]) : parts[parts.length - 1].push(line);
    document.execCommand('insertText', false, parts[0].join('\n'));
    let after = ed.closest('.cr-slide'), made = 0;
    for (const p of parts.slice(1)) {
      const lines = stTrimLines(stPlain(p.join('\n')));
      if (lines.length) { after = crAddSlide({ body: stHTML(lines) }, after); made++; }
    }
    if (made) toast(`متن به ${faNum(made + 1)} اسلاید تقسیم شد`);
  });
  wrap.addEventListener('mousedown', e => {   // دکمه‌های ابزار انتخاب متن را از بین نبرند
    if (e.target.closest('[data-crs="hl"],[data-crs="big"],[data-crs="small"]')) e.preventDefault();
  });
  wrap.addEventListener('keydown', e => {
    if (!edOf(e.target) || !(e.metaKey || e.ctrlKey) || !e.shiftKey || (e.code !== 'Period' && e.code !== 'Comma')) return;
    e.preventDefault(); crResize(e.code === 'Period' ? 1 : -1);
  });
  wrap.addEventListener('click', e => {
    const t = e.target, q = s => t.closest(s);
    let b;
    if (q('[data-stop]')) return;
    if ((b = q('[data-crsrc]'))) return crSrc(b.dataset.crsrc);
    if ((b = q('[data-crp]'))) return crPick(b.dataset.crp);
    if ((b = q('button[data-crk]'))) return crSet(b.dataset.crk, b.dataset.v, true);
    if ((b = q('button[data-crimg]'))) return crImgOpt(b.closest('.cr-slide'), b.dataset.crimg, b.dataset.v);
    if ((b = q('[data-crs]'))) return crSlideAct(b.dataset.crs, b.closest('.cr-slide'), b);
    if ((b = q('[data-cra]'))) return crAct(b.dataset.cra, b);
    if ((b = q('[data-crdeck]'))) return crOpen(b.dataset.crdeck);
  });
  wrap.addEventListener('input', e => {
    const t = e.target, ed = edOf(t);
    if (ed === t) return crEdited(t);
    if (t.closest('.cr-ai')) return crSaveForm();
    if (t.id === 'crTitle') { CR.deck.title = t.value; CR.meta.add('title'); return crQueue(); }
    if (t.id === 'crCaption' || t.id === 'crTags') {
      CR.deck[t.id === 'crCaption' ? 'caption' : 'hashtags'] = t.value;
      CR.meta.add(t.id === 'crCaption' ? 'caption' : 'hashtags'); crCapCount();
      if (t.id === 'crCaption' && window.fitHeight) fitHeight(t);
      return crQueue();
    }
    if (t.matches('input[type=range][data-crimg]')) return crImgOpt(t.closest('.cr-slide'), 'dim', t.value);
    if (t.matches('.cr-iprompt')) { const sl = crSlide(t.closest('.cr-slide').dataset.sid); sl.imgPrompt = t.value; CR.dirty.add(sl.id); return crQueue(); }
    if (t.matches('input[type=range][data-crk]')) {
      crSet(t.dataset.crk, t.value, false);
      const o = $(`output[data-out="${t.dataset.crk}"]`, wrap); if (o) o.textContent = crFmt(t.dataset.crk, crStyle()[t.dataset.crk]);
    } else if (t.matches('input[type=color][data-crk]')) crSet(t.dataset.crk, t.value, false);
    else if (t.matches('input[type=text][data-crk]')) crSet(t.dataset.crk, t.value, false);
  });
  wrap.addEventListener('change', e => {
    const t = e.target;
    if (t.matches('input[type=color][data-crk]') || t.matches('input[type=range][data-crk]')) crCtl();
    if (t.closest('.cr-ai')) crSaveForm();
  });
}
function crSrc(src) {
  $$('[data-crsrc]').forEach(b => b.classList.toggle('on', b.dataset.crsrc === src));
  $('#crText').hidden = src !== 'text'; $('#crIdea').hidden = src !== 'idea'; $('.cr-keep').hidden = src !== 'text';
  crSaveForm();
}
function crEdited(ed) {
  const el = ed.closest('.cr-slide'), sl = crSlide(el.dataset.sid); if (!sl) return;
  ed.classList.toggle('is-empty', !ed.textContent.trim());
  sl[ed.classList.contains('cr-t') ? 'title' : 'body'] = ed.innerHTML;
  CR.dirty.add(sl.id); crQueue();
  clearTimeout(el._t); el._t = setTimeout(() => crRenderCard(el), 80);
  if ($$('.cr-slide').indexOf(el) === 0) { clearTimeout(CR.tGal); CR.tGal = setTimeout(crRenderGal, 400); }
}
function crResize(dz) {
  const ed = stSelEd(); if (!ed || !ed.closest('.cr-slide')) return toast('اول بخشی از متن را انتخاب کن');
  const r = getSelection().getRangeAt(0), root = r.commonAncestorContainer;
  const w = document.createTreeWalker(root.nodeType === 3 ? root.parentNode : root, NodeFilter.SHOW_TEXT);
  let n = w.nextNode(), z = 3;
  while (n && !(r.intersectsNode(n) && n.nodeValue.trim())) n = w.nextNode();
  for (let el = n && n.parentNode; el && el !== ed; el = el.parentNode)
    if (el.tagName === 'FONT' && el.getAttribute('size')) { z = stZ(el.getAttribute('size')); break; }
  const nz = Math.max(1, Math.min(7, z + dz));
  if (nz === z) return toast(dz > 0 ? 'بزرگ‌تر از این نمی‌شود' : 'کوچک‌تر از این نمی‌شود');
  document.execCommand('styleWithCSS', false, false);
  document.execCommand('fontSize', false, String(nz));
  crEdited(ed);
}
function crAddSlide(data, after, focus) {
  const d = CR.deck; if (!d) return null;
  if (d.slides.length >= 40) { toast('بیشتر از ۴۰ اسلاید نمی‌شود'); return null; }
  const sl = { id: 's' + Math.random().toString(16).slice(2, 10), title: '', body: '', img: null, imgPrompt: '', ...data };
  const at = after ? d.slides.findIndex(s => s.id === after.dataset.sid) + 1 : d.slides.length;
  d.slides.splice(at, 0, sl);
  const el = crCard(sl);
  if (after) after.after(el); else $('#crSlides').appendChild(el);
  CR.dirty.add(sl.id); CR.structure = true; crQueue();
  crNumber(); crRenderAll();
  if (focus) { $('.cr-t', el).focus(); el.scrollIntoView({ behavior: 'smooth', block: 'center' }); }
  return el;
}
async function crSlideAct(a, el, btn) {
  const d = CR.deck; if (!d || !el) return;
  const sl = crSlide(el.dataset.sid); if (!sl) return;
  const i = d.slides.indexOf(sl);
  if (a === 'big' || a === 'small') return crResize(a === 'big' ? 1 : -1);
  if (a === 'hl') {
    const ed = stSelEd(); if (!ed || !el.contains(ed)) return toast('اول بخشی از متن را انتخاب کن');
    document.execCommand('styleWithCSS', false, false); document.execCommand('bold');
    return crEdited(ed);
  }
  if (a === 'up' || a === 'down') {
    const j = a === 'up' ? i - 1 : i + 1; if (j < 0 || j >= d.slides.length) return;
    [d.slides[i], d.slides[j]] = [d.slides[j], d.slides[i]];
    const other = crCardOf(d.slides[i].id);
    if (a === 'up') el.after(other); else other.after(el);
    CR.structure = true; crQueue(); crNumber(); crRenderAll();
    return el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }
  if (a === 'dup') return crAddSlide({ title: crClean(sl.title), body: crClean(sl.body), img: sl.img ? { ...sl.img } : null, imgPrompt: sl.imgPrompt || '' }, el, false);
  if (a === 'del') {
    if (d.slides.length === 1) return toast('کاروسل دست‌کم یک اسلاید دارد');
    const res = CR.res.get(sl.id);
    if (res && !res.empty && !confirm('این اسلاید حذف شود؟')) return;
    d.slides.splice(i, 1); el.remove(); CR.dirty.delete(sl.id);
    CR.structure = true; crQueue(); crNumber(); return crRenderAll();
  }
  if (a === 'dl') return crDownload(el, i);
  if (a === 'pick') return crMedia(sl.id);
  if (a === 'noimg') { sl.img = null; CR.dirty.add(sl.id); crQueue(); crImgRow(el, sl); return crRenderCard(el); }
  if (a === 'mkimg') {
    const prompt = ($('.cr-iprompt', el) || {}).value || sl.imgPrompt;
    return crMakeImage(sl, prompt, sl.imgMode || 'below');
  }
  if (a === 'regen') {
    await crFlush();
    const note = $('.cr-note', el).value.trim();
    const r = await post('/api/carousel/regen', { id: d.id, target: 'slide', slide: sl.id, note });
    if (!r.ok) return toast(r.data.error || 'شروع نشد');
    $('.cr-note', el).value = '';
    CR.jobs[sl.id] = { state: 'running', step: 'Claude دارد بازنویسی می‌کند…' }; crShowJobs(); crWatch();
    return;
  }
  if (a === 'undo') {
    await crFlush();
    const r = await post('/api/carousel/undo', { id: d.id, target: 'slide', slide: sl.id });
    if (!r.ok) return toast(r.data.error || 'برنگشت');
    return crRefresh([sl.id]);
  }
}
async function crMakeImage(sl, prompt, mode) {
  prompt = String(prompt || '').trim(); if (!prompt) return toast('اول بنویس چه تصویری می‌خواهی');
  await crFlush();
  const r = await post('/api/carousel/image', { id: CR.deck.id, slide: sl.id, prompt, mode });
  if (!r.ok) return toast(r.data.error || 'شروع نشد');
  CR.jobs['img-' + sl.id] = { state: 'running', step: 'Gemini دارد تصویر را می‌سازد…' }; crShowJobs(); crWatch();
}
function crImgOpt(el, k, v) {
  const sl = el && crSlide(el.dataset.sid); if (!sl || !sl.img) return;
  sl.img = { ...sl.img, [k]: k === 'dim' ? Number(v) : v };
  if (k === 'mode') sl.img.fit = v === 'circle' || v === 'bg' || v === 'full' ? 'cover' : 'contain';
  CR.dirty.add(sl.id); crQueue();
  if (k !== 'dim') crImgRow(el, sl);
  crRenderCard(el);
}
async function crAct(a, btn) {
  const d = CR.deck;
  if (a === 'gen') return crGenerate();
  if (a === 'savestyle') return crSaveStyle();
  if (a === 'blank') {
    const r = await post('/api/carousel/new', {});
    return r.ok ? crOpen(r.data.deck.id) : toast(r.data.error || 'ساخته نشد');
  }
  if (a === 'copy') {
    const r = await post('/api/carousel/duplicate', { id: btn.dataset.id });
    return r.ok ? crOpen(r.data.deck.id) : toast(r.data.error || 'کپی نشد');
  }
  if (a === 'del') {
    if (!confirm('این کاروسل حذف شود؟ (به data/carousels/trash می‌رود)')) return;
    const r = await post('/api/carousel/delete', { id: btn.dataset.id });
    if (!r.ok) return toast(r.data.error || 'حذف نشد');
    return crLoadList();
  }
  if (a === 'home') { await crFlush(); clearTimeout(CR.poll); return crHome(); }
  if (a === 'add') return crAddSlide({}, null, true);
  if (a === 'dlall') return crDownloadAll();
  if (a === 'copycap') return navigator.clipboard.writeText(crFullCaption()).then(() => toast('✓ کپشن و هشتگ‌ها کپی شد؛ اسلایدها را با «دانلود همه» بگیر و در اینستاگرام منتشر کن'), () => toast('کپی نشد'));
  if (a === 'retry' || a === 'forget') {
    const r = await post(a === 'retry' ? '/api/carousel/publish/retry' : '/api/carousel/publish/forget', { id: d.id });
    if (!r.ok) return toast(r.data.error || 'نشد');
    if (a === 'forget') { d.pending = null; delete CR.jobs.publish; return crShowPub(); }
    CR.jobs.publish = { state: 'running', step: 'انتشار…' }; crShowPub(); return crWatch();
  }
  if (a === 'regenall') {
    if (d.slides.length && !confirm('همه‌ی اسلایدها از نو ساخته می‌شوند. ادامه؟')) return;
    const r = await post('/api/carousel/generate', { id: d.id });
    if (!r.ok) return toast(r.data.error || 'شروع نشد');
    CR.jobs.gen = { state: 'running', step: 'Claude دارد متن اسلایدها را می‌نویسد…', started: Date.now() / 1000 };
    crShowJobs(); return crWatch();
  }
  if (a === 'capregen') {
    await crFlush();
    const note = $('#crCapNote').value.trim();
    const r = await post('/api/carousel/regen', { id: d.id, target: 'caption', note });
    if (!r.ok) return toast(r.data.error || 'شروع نشد');
    $('#crCapNote').value = '';
    CR.jobs.caption = { state: 'running' }; crShowJobs(); return crWatch();
  }
  if (a === 'capundo') {
    await crFlush();
    const r = await post('/api/carousel/undo', { id: d.id, target: 'caption' });
    if (!r.ok) return toast(r.data.error || 'برنگشت');
    return crRefresh(['caption']);
  }
}

/* ---------- کپشن ---------- */
const crHashtags = t => (String(t || '').match(/(?:^|\s)#[^\s#]+/g) || []).length;
function crFullCaption() {
  const d = CR.deck, cap = (d.caption || '').trim(), tags = String(d.hashtags || '').split(/\s+/).filter(Boolean).join(' ');
  return cap + (cap && tags ? '\n\n' + tags : tags);
}
function crCapCount() {
  const el = $('#crCapCount'); if (!el || !CR.deck) return;
  const full = crFullCaption(), n = [...full].length, h = crHashtags(full);
  el.textContent = `${faNum(n)} از ۲۲۰۰ کاراکتر، ${faNum(h)} از ۵ هشتگ`;     // سقف اینستاگرام از دسامبر ۲۰۲۵
  el.classList.toggle('bad', n > 2200 || h > 5);
}

/* ---------- استایل ---------- */
const crFmt = (k, v) => k === 'tLh' || k === 'bLh' || k === 'coverScale' ? faNum(Number(v).toFixed(2)) : k === 'logoW' ? faNum(Math.round(v * 100)) + '٪' : faNum(v);
function crCtl() {
  const el = $('#crCtl'); if (!el || !CR.deck) return;
  const s = crStyle();
  const row = (label, body) => `<div class="st-row"><span class="st-lbl">${label}</span><div class="st-in">${body}</div></div>`;
  const chips = (k, opts) => opts.map(([v, l]) =>
    `<button class="st-chip${String(s[k]) === String(v) ? ' on' : ''}" data-crk="${k}" data-v="${v}">${l}</button>`).join('');
  const sw = k => CR_SW[k].map(c =>
    `<button class="st-sw${String(s[k]).toLowerCase() === c ? ' on' : ''}" style="--c:${c}" data-crk="${k}" data-v="${c}" title="${esc(CR.names[c] || c)}"></button>`).join('')
    + `<input type="color" class="st-pick" data-crk="${k}" value="${esc(s[k])}" title="رنگ دلخواه">`;
  const range = (k, min, max, step) =>
    `<input type="range" data-crk="${k}" min="${min}" max="${max}" step="${step}" value="${s[k]}"><output data-out="${k}">${crFmt(k, s[k])}</output>`;
  const sep = '<span class="st-sep"></span>';
  el.innerHTML = `
    <div class="st-ctlhead"><b>نمونه‌ها</b><span>روی همه‌ی اسلایدهای همین کاروسل</span></div>
    <div id="crGal" class="cr-gal">${CR_PRESETS.map(p => `
      <button class="st-card cr-card" data-crp="${p.key}" title="${esc(p.note)}"><canvas data-crg="${p.key}"></canvas><b>${esc(p.name)}</b></button>`).join('')}
      ${CR.saved ? `<button class="st-card cr-card" data-crp="mine" title="ذخیره‌شده"><canvas data-crg="mine"></canvas><b>استایل من</b></button>` : ''}</div>
    <div class="st-ctlhead"><b>تنظیم استایل</b><span id="crBase"></span></div>
    ${row('زمینه', chips('bgMode', [['solid', 'رنگ ساده'], ['gradient', 'گرادیان']]))}
    ${row(s.bgMode === 'gradient' ? 'رنگ بالا' : 'رنگ زمینه', sw('bg'))}
    ${s.bgMode === 'gradient' ? row('رنگ پایین', sw('bg2')) : ''}
    ${row('رنگ متن', sw('fg'))}
    ${row('تأکید', sw('hl') + sep + chips('hlMode', [['color', 'رنگ متن'], ['marker', 'ماژیک']]))}
    ${row('یک‌درمیان', chips('alt', [['none', 'نه'], ['light', 'اسلایدهای زوج روشن']]))}
    ${s.alt === 'light' ? row('زمینه‌ی روشن', sw('altBg')) + row('متن روشن', sw('altFg')) + row('تأکید روشن', sw('altHl')) : ''}
    ${row('تیتر', range('tSize', 40, 110, 1) + chips('tWeight', [[700, 'ضخیم'], [800, 'خیلی'], [900, 'سیاه']]))}
    ${row('تیتر کاور', range('coverScale', 1, 1.8, 0.05))}
    ${row('متن', range('bSize', 30, 64, 1) + chips('bWeight', [[500, 'معمولی'], [600, 'نیمه'], [700, 'ضخیم']]))}
    ${row('فاصله‌ی خط‌ها', range('bLh', 1.4, 2.3, 0.05))}
    ${row('چینش', chips('align', [['right', 'راست‌چین'], ['center', 'وسط‌چین']]) + sep + chips('valign', [['center', 'وسط'], ['top', 'از بالا']]))}
    ${row('لوگو', chips('logo', [['none', 'بدون'], ['corner', 'گوشه'], ['tab', 'زبانه'], ['bottom', 'وسط پایین'], ['top', 'بالا']]))}
    ${s.logo !== 'none' ? row('لوگو روی', chips('logoOn', [['all', 'همه'], ['first', 'فقط کاور'], ['ends', 'کاور و آخر']]))
        + row('اندازه‌ی لوگو', range('logoW', 0.1, 0.4, 0.01) + (ST.logos && ST.logos.light ? '' : '<span class="st-dim">لوگویی نیست؛ در «هسته‌ی برند ← هویت بصری» آپلودش کن</span>')) : ''}
    ${row('شماره', chips('num', [['none', 'بدون'], ['num', '۲ از ۷']]))}
    ${row('آیدی پیج', `<input type="text" class="cr-handle" data-crk="handle" dir="ltr" value="${esc(s.handle || '')}" placeholder="${crHandle()}">`
        + (s.handle ? '' : `<button class="st-chip" data-crk="handle" data-v="${crHandle()}">نشان بده</button>`))}
    ${row('ورق بزن', chips('swipe', [['none', 'بدون'], ['arrow', 'فلش گوشه'], ['arc', 'کمان روی کاور']]))}
    ${s.swipe !== 'none' ? row('رنگ فلش', sw('ac')) : ''}
    ${row('تزئین', chips('deco', [['none', 'هیچ'], ['bar', 'خط کوتاه'], ['frame', 'کادر']]))}
    ${s.deco === 'bar' ? row('رنگ تزئین', sw('decoColor')) : ''}
    <div class="st-save">
      <button class="btn primary" data-cra="savestyle">ذخیره به‌عنوان استایل من</button>
      <span id="crSaveNote" class="st-dim"></span>
    </div>`;
  crCtlNote(); crRenderGal();
}
const crSame = (a, b) => !!a && !!b && Object.keys(CR_BASE).every(k => String(a[k] ?? '') === String(b[k] ?? ''));
function crCtlNote() {
  const s = crStyle(), p = CR_PRESETS.find(x => crSame(s, crPreset(x.key)));
  const mine = CR.saved && crSame(s, CR.saved);
  const base = $('#crBase'); if (base) base.textContent = mine ? 'همان استایل من' : p ? `همان «${p.name}»` : 'با تغییر';
  $$('#crGal [data-crp]').forEach(b => b.classList.toggle('on', b.dataset.crp === 'mine' ? !!mine : !!p && p.key === b.dataset.crp && !mine));
  const n = $('#crSaveNote'); if (n) n.textContent = !CR.saved ? 'هنوز ذخیره نشده؛ کاروسل‌های تازه با «برند من» شروع می‌شوند.' : mine ? '✓ همین ذخیره شده.' : '';
}
function crSet(k, raw, rebuild) {
  const s = CR.deck.style = crStyle();
  s[k] = CR_NUM.has(k) ? Number(raw) : raw;
  if (k === 'logo' && CR_LOGOW[raw]) s.logoW = CR_LOGOW[raw];
  CR.meta.add('style'); crQueue();
  if (rebuild) crCtl(); else crCtlNote();
  crRenderAll();
}
function crPick(key) {
  const keep = { handle: crStyle().handle };   // آیدی پیج انتخاب خود اوست، با عوض شدن نمونه نمی‌رود
  CR.deck.style = { ...(key === 'mine' && CR.saved ? { ...CR.saved } : crPreset(key)), ...keep };
  CR.meta.add('style'); crQueue(); crCtl(); crRenderAll();
}
async function crSaveStyle() {
  const s = crStyle(), r = await post('/api/carousel/style', { style: s, preset: s.preset || '' });
  if (!r.ok) return toast(r.data.error || 'ذخیره نشد');
  CR.saved = { ...s }; CR.savedPreset = r.data.preset || '';
  toast('✓ استایل ذخیره شد؛ کاروسل‌های تازه با همین شروع می‌شوند'); crCtl();
}
function crRenderGal() {
  const d = CR.deck; if (!d) return;
  const first = $('.cr-slide'), sl = first && crSlide(first.dataset.sid);
  let data = crDemoData();
  if (first && sl) {
    const tF = stTrimLines(stRead($('.cr-t', first))), bF = stTrimLines(stRead($('.cr-b', first)));
    if (crHas(tF) || crHas(bF) || sl.img) data = { tF, bF, img: sl.img };
  }
  const n = Math.max(d.slides.length, 2), keep = { handle: crStyle().handle };
  for (const cv of $$('#crGal canvas[data-crg]')) {
    const key = cv.dataset.crg, st = key === 'mine' ? CR.saved : { ...crPreset(key), ...keep };
    if (!st) continue;
    const scale = Math.min(0.4, Math.max(0.16, (cv.clientWidth || 96) * (devicePixelRatio || 1) / CRW));
    crPaint(cv, data, 0, n, st, scale);
  }
}

/* ---------- کتابخانه‌ی تصویر ---------- */
async function crMedia(sid) {
  const sl = crSlide(sid); if (!sl) return;
  const r = await api('/api/carousel/media'), list = (r && r.media) || [];
  const m = document.createElement('div');
  m.className = 'cr-modal';
  m.innerHTML = `
    <div class="cr-mbox" role="dialog" aria-label="کتابخانه‌ی تصویر">
      <div class="cr-mhead"><b>تصویر برای اسلاید ${faNum(CR.deck.slides.indexOf(sl) + 1)}</b><span class="st-grow"></span>
        <label class="btn">آپلود عکس…<input type="file" accept="image/png,image/jpeg,image/webp" multiple hidden></label>
        <button class="btn" data-crm="close">بستن</button></div>
      <div class="cr-mgen">
        <input class="cap-input" id="crMPrompt" dir="auto" placeholder="یا بنویس چه تصویری بسازم (فارسی یا انگلیسی)؛ مثلاً «یک نفر پشت لپ‌تاپ که رزومه‌اش را با هوش مصنوعی مرتب می‌کند»">
        <button class="btn primary" data-crm="ai">ساخت با Gemini</button></div>
      <p class="cap-hint">عکس‌هایی که آپلود می‌کنی در کتابخانه می‌مانند و برای کاروسل‌های بعدی هم هستند. زیر هر عکس بنویس چیست («عکس من با کت سرمه‌ای»)؛ Claude موقع ساخت کاروسل از روی همین توضیح عکس مناسب را انتخاب می‌کند.</p>
      <div class="cr-mgrid">${list.length ? '' : '<div class="cr-dim">کتابخانه هنوز خالی است.</div>'}</div>
    </div>`;
  document.body.appendChild(m);
  const grid = $('.cr-mgrid', m);
  const draw = items => {
    if (!items.length) return;
    grid.innerHTML = items.map(x => `
      <div class="cr-mitem${sl.img && sl.img.file === x.file ? ' on' : ''}">
        <button class="cr-mpick" data-file="${esc(x.file)}" title="انتخاب برای این اسلاید"><img src="/carousel-media/${encodeURIComponent(x.file)}" alt="" loading="lazy"></button>
        <input class="cr-mlabel" data-file="${esc(x.file)}" dir="auto" value="${esc(x.label || '')}" placeholder="این عکس چیست؟">
        <div class="cr-mfoot"><span>${x.src === 'ai' ? 'ساخته‌ی Gemini' : 'آپلودی'}</span>
          <button class="st-tool st-del" data-crm="delimg" data-file="${esc(x.file)}">حذف</button></div>
      </div>`).join('');
  };
  draw(list);
  const close = () => { m.remove(); removeEventListener('keydown', onKey); };
  const onKey = e => { if (e.key === 'Escape') close(); };
  addEventListener('keydown', onKey);
  m.addEventListener('click', async e => {
    if (e.target === m) return close();
    const b = e.target.closest('[data-crm],.cr-mpick'); if (!b) return;
    if (b.matches('.cr-mpick')) {
      const file = b.dataset.file;
      sl.img = { file, mode: sl.img ? sl.img.mode : 'below', fit: sl.img ? sl.img.fit : 'contain', dim: 0.65 };
      if (sl.img.mode === 'circle' || sl.img.mode === 'bg' || sl.img.mode === 'full') sl.img.fit = 'cover';
      CR.dirty.add(sl.id); crQueue();
      const el = crCardOf(sl.id); if (el) { crImgRow(el, sl); crRenderCard(el); }
      return close();
    }
    const a = b.dataset.crm;
    if (a === 'close') return close();
    if (a === 'ai') {
      const prompt = $('#crMPrompt', m).value.trim(); if (!prompt) return toast('اول بنویس چه تصویری می‌خواهی');
      close(); return crMakeImage(sl, prompt, sl.img ? sl.img.mode : 'below');
    }
    if (a === 'delimg') {
      if (!confirm('این عکس از کتابخانه حذف شود؟')) return;
      const r2 = await post('/api/carousel/media/delete', { file: b.dataset.file });
      if (!r2.ok) return toast(r2.data.error || 'حذف نشد');
      draw(r2.data.media || []); if (!(r2.data.media || []).length) grid.innerHTML = '<div class="cr-dim">کتابخانه هنوز خالی است.</div>';
    }
  });
  m.addEventListener('change', async e => {
    const t = e.target;
    if (t.matches('.cr-mlabel')) {
      const r2 = await post('/api/carousel/media/label', { file: t.dataset.file, label: t.value });
      return r2.ok ? toast('✓ ذخیره شد') : toast(r2.data.error || 'ذخیره نشد');
    }
    if (t.type === 'file' && t.files.length) {
      let last = null;
      for (const f of t.files) {
        if (f.size > 15 * 1024 * 1024) { toast(`${f.name} از ۱۵ مگابایت بزرگ‌تر است`); continue; }
        const data = await new Promise(res => { const fr = new FileReader(); fr.onload = () => res(fr.result); fr.readAsDataURL(f); });
        const r2 = await post('/api/carousel/media', { filename: f.name, data, label: f.name.replace(/\.[^.]+$/, '') });
        if (!r2.ok) { toast(r2.data.error || 'آپلود نشد'); continue; }
        last = r2.data.media;
      }
      if (last) { draw(last); toast('✓ آپلود شد؛ زیر عکس بنویس چیست'); }
      t.value = '';
    }
  });
}

/* ---------- دانلود و انتشار ---------- */
async function crReadyForExport() {
  await crFlush();
  const d = CR.deck;
  await Promise.all(d.slides.filter(s => s.img).map(s => crImgLoad(s.img.file)));
  crRenderAll();
  return $$('.cr-slide');
}
const crJpegBlob = (cv, q = 0.92) => new Promise(r => cv.toBlob(r, 'image/jpeg', q));
const crDataURL = blob => new Promise(r => { const fr = new FileReader(); fr.onload = () => r(fr.result); fr.readAsDataURL(blob); });
function crFileName(i) {
  const d = new Date(), p = n => String(n).padStart(2, '0');
  return `carousel-${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}-${p(i + 1)}.jpg`;
}
async function crSaveBlob(blob, name) {
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob); a.download = name;
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 5000);
}
async function crDownload(el, i) {
  if (!ST.fontOK) return toast('فونت بارگذاری نشده؛ صفحه را تازه کن');
  await crReadyForExport();
  crSaveBlob(await crJpegBlob($('canvas', el)), crFileName(i));
}
async function crDownloadAll() {
  if (!ST.fontOK) return toast('فونت بارگذاری نشده؛ صفحه را تازه کن');
  const cards = await crReadyForExport();
  for (const [i, el] of cards.entries()) {
    if (CR.res.get(el.dataset.sid)?.empty) continue;
    crSaveBlob(await crJpegBlob($('canvas', el)), crFileName(i));
    await new Promise(r => setTimeout(r, 350));
  }
}
function crProblems() {
  const d = CR.deck, out = [], n = d.slides.length;
  if (n > CR_PUBLISH_MAX) out.push(`${faNum(n)} اسلاید داری؛ اینستاگرام از راه API حداکثر ${faNum(CR_PUBLISH_MAX)} را منتشر می‌کند.`);
  d.slides.forEach((s, i) => {
    const r = CR.res.get(s.id) || {};
    if (r.empty) out.push(`اسلاید ${faNum(i + 1)} خالی است.`);
    else if (r.overflow) out.push(`متن اسلاید ${faNum(i + 1)} جا نمی‌شود.`);
  });
  const cap = crFullCaption();
  if ([...cap].length > 2200) out.push('کپشن با هشتگ‌ها از ۲۲۰۰ کاراکتر بیشتر است.');
  if (crHashtags(cap) > 5) out.push('بیشتر از ۵ هشتگ داری؛ اینستاگرام از دسامبر ۲۰۲۵ بیشتر از ۵ تا نمی‌گذارد.');
  if (!ST.fontOK) out.push('فونت بارگذاری نشده؛ صفحه را تازه کن.');
  const running = Object.entries(CR.jobs).filter(([, j]) => j.state === 'running').map(([k]) => k);
  if (running.length) out.push('یک کار (ساخت، بازنویسی یا تصویر) هنوز در جریان است؛ بگذار تمام شود.');
  return out;
}
/* ---------- از بانک ایده ---------- */
window.mountCarouselIdea = (bar, it) => {
  if (!bar || !it || $('[data-cr-idea]', bar)) return;
  const b = document.createElement('button');
  b.className = 'btn'; b.dataset.crIdea = it.id; b.textContent = 'ساخت کاروسل';
  b.title = 'یک کاروسل اینستاگرام از همین ایده؛ تحلیل، پژوهش و ریلزش هم خوانده می‌شود';
  b.onclick = () => { CR.pending = { idea: it.id }; go('carousel'); };
  bar.appendChild(b);
};

window.viewCarousel = viewCarousel;
