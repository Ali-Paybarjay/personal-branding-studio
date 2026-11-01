/* ================= استوری متنی =================
   متنِ خودِ کاربر + یک استایل ثابت ← فایل PNG ۱۰۸۰×۱۹۲۰ برای استوری اینستاگرام.
   همه‌چیز روی canvas کشیده می‌شود و پیش‌نمایش همان canvas خروجی است: آنچه می‌بینی همان فایل است.
   متن عیناً همانی است که نوشته شده؛ کلمه، نیم‌فاصله و عدد دست نمی‌خورد. فقط شکستن خط و (اگر جا نشود) کوچک کردن فونت.
   استایل ذخیره‌شده: data/stories/settings.json (app/story.py). */

const STW = 1080, STH = 1920;
const ST_PAD = 86;                           // حاشیه‌ی چپ و راست متن
const ST_SAFE = { top: 250, bottom: 250 };   // زیر نوار پروفایل (بالا) و نوار پیام (پایین) اینستاگرام
const ST_FONT = 'Vazirmatn, "Apple Color Emoji", sans-serif';

// پیش‌فرض: زمینه‌ی تخت به رنگ اصلی برند، متن سفید ضخیم راست‌چین از حدود ۲۵٪ ارتفاع،
// خط خالی بین پاراگراف‌ها، تأکید به رنگ تأکیدی برند، لوگوی سفید وسطِ پایین با پهنای ۳۲٪.
// رنگ‌ها اول خنثی‌اند و stApplyBrand آن‌ها را از پالت «هسته‌ی برند ← هویت بصری» پر می‌کند.
const ST_BASE = {
  bgMode: 'solid', bg: '#1f2b3a', bg2: '#0f151d', bgImage: '', bgDim: 0.45,
  fg: '#ffffff', hl: '#ffcc4d', hlMode: 'color',
  size: 54, weight: 700, lh: 1.8, pgap: 1, align: 'right', valign: 'top', top: 0.24,
  logo: 'bottom', logoW: 0.32, logoInk: 'auto', deco: 'none', decoColor: '#8ecae6',
};
const ST_PRESETS = [
  { key: 'archive', name: 'برند من', demo: 'mid', s: {},
    note: 'رنگ اصلی برندت، متن سفید، رنگ تأکیدی، لوگو پایین' },
  { key: 'archive-clean', name: 'برند من، بی‌لوگو', demo: 'mid', s: { logo: 'none' },
    note: 'همان، بدون لوگو' },
  { key: 'big', name: 'تیتر درشت', demo: 'short',
    s: { size: 86, weight: 800, lh: 1.6, align: 'center', valign: 'center', logo: 'none' },
    note: 'یک جمله‌ی کوتاه، وسط صفحه، بدون لوگو' },
  { key: 'big-logo', name: 'درشت با لوگوی بالا', demo: 'short',
    s: { size: 80, weight: 800, lh: 1.6, align: 'center', valign: 'center', logo: 'top', logoW: 0.24 },
    note: 'جمله‌ی کوتاه با لوگوی کوچک بالای صفحه' },
  { key: 'long', name: 'متن بلند، ریز', demo: 'long',
    s: { size: 40, weight: 600, lh: 1.85, pgap: 0.7, top: 0.15, logo: 'mark', logoW: 0.1 },
    note: 'برای متن طولانی؛ فقط نشان لوگو پایین' },
  { key: 'marker', name: 'ماژیکی', demo: 'mid',
    s: { size: 62, weight: 800, lh: 1.85, pgap: 0.8, valign: 'center', hlMode: 'marker', logoW: 0.26 },
    note: 'تأکید با نوار رنگی پشت کلمه‌ها' },
  { key: 'deep', name: 'تیره', demo: 'mid',
    s: { bg: '$bg2', size: 58, pgap: 0.8, valign: 'center', deco: 'bar', logo: 'mark', logoW: 0.12 },
    note: 'نسخه‌ی تیره‌ی رنگ برندت، خط کوتاه بالای متن، نشان کوچک' },
  { key: 'night', name: 'گرادیان', demo: 'mid',
    s: { bgMode: 'gradient', bg: '$bg', bg2: '$bg2', hl: '$alt', size: 56, pgap: 0.8,
         align: 'center', valign: 'center', deco: 'frame', logoW: 0.26 },
    note: 'از رنگ برند تا تیره، کادر نازک' },
  { key: 'cream', name: 'روشن', demo: 'mid',
    s: { bg: '$light', fg: '$bg', hlMode: 'marker', size: 58, weight: 800, pgap: 0.8, valign: 'center', logoW: 0.28 },
    note: 'زمینه‌ی روشن، متن به رنگ برند، ماژیک' },
];
// ** = تأکید
const ST_DEMO = {
  mid: 'اگه تو هم می‌خوای برند شخصی‌ات رو بسازی ولی نمی‌دونی از کجا شروع کنی،\n\n'
     + '**این هفته سه تا اشتباه رایج رو با هم مرور می‌کنیم.**',
  short: 'بیشتر آدم‌ها به‌جای شروع کردن، **منتظر لحظه‌ی بی‌نقص** می‌مونن.',
  long: '**سه درسی که از یک سال تولید محتوا گرفتم**\n\n'
      + 'اول: ثبات از کیفیت مهم‌تره. پستی که منتشر می‌شه از پست بی‌نقصی که هیچ‌وقت منتشر نمی‌شه بهتره.\n\n'
      + '**دوم: با زبان مخاطبت حرف بزن، نه با زبان خودت.**\n\n'
      + 'سوم: هر ریلز فقط یک حرف اصلی داشته باشه.\n\n'
      + '**و از همه مهم‌تر: ایده رو از سؤال‌هایی بگیر که مخاطب‌هات ازت می‌پرسن.**',
};
// دایره‌های رنگ: اول رنگ‌های خنثی؛ stApplyBrand رنگ‌های پالت هسته‌ی برند را جلویشان می‌گذارد. اسم‌ها از /api/brand می‌آیند.
const ST_SW = {
  bg: ['#1f2b3a', '#0f151d', '#020202', '#f3efe6', '#ffffff'],
  bg2: ['#0f151d', '#1f2b3a', '#020202'],
  fg: ['#ffffff', '#f3efe6', '#020202'],
  hl: ['#ffcc4d', '#8ecae6', '#ffffff'],
  decoColor: ['#8ecae6', '#ffcc4d', '#ffffff'],
};
// نقش‌های رنگ برند که نمونه‌ها با «$نام» به آن‌ها اشاره می‌کنند
const ST_PAL = { bg: '#1f2b3a', bg2: '#0f151d', light: '#f3efe6', alt: '#8ecae6' };
const ST_NUM = new Set(['size', 'weight', 'lh', 'pgap', 'top', 'logoW', 'bgDim']);
const ST_LOGOW = { bottom: 0.32, top: 0.24, mark: 0.12 };   // اندازه‌ی پیش‌فرض هر جای لوگو، وقتی جایش عوض می‌شود
// بزرگ/کوچک کردن یک بخش از متن: در ویرایشگر <font size="1..7"> است (۳ = عادی) و در خروجی ضریبِ اندازه‌ی پایه
const ST_SIZES = { 1: 0.7, 2: 0.85, 3: 1, 4: 1.25, 5: 1.5, 6: 1.8, 7: 2.2 };
const ST_CSSZ = { 'x-small': 1, small: 2, medium: 3, large: 4, 'x-large': 5, 'xx-large': 6, 'xxx-large': 7, '-webkit-xxx-large': 7 };
const stZ = v => { const n = parseInt(v, 10) || 0; return Math.max(1, Math.min(7, /^[+-]/.test(v) ? 3 + n : n || 3)); };

const ST = {
  style: null, preset: 'archive', mod: false, saved: null, savedPreset: '',
  names: { '#0b1c24': 'سرمه‌ای شب (زمینه‌ی استودیو)' }, logos: null, fontOK: true,
  tPrev: 0, tGal: 0, tDraft: 0,
};
const ST_BG = new Map();   // فایل زمینه ← Image

/* ---------- متن ---------- */
// ویرایشگر ← خط‌ها؛ هر خط آرایه‌ای از {ch, hl, z}. پررنگ (⌘B) در ویرایشگر = تأکید؛ z = پله‌ی اندازه (۳ = عادی).
function stRead(root) {
  const lines = [[]], cur = () => lines[lines.length - 1];
  const walk = (node, hl, z) => {
    for (const n of node.childNodes) {
      if (n.nodeType === 3) {
        for (const ch of n.nodeValue.replace(/\r/g, ''))
          ch === '\n' ? lines.push([]) : cur().push({ ch: ch === '\u00A0' ? ' ' : ch, hl, z });
      } else if (n.nodeType === 1) {
        if (n.tagName === 'BR') { lines.push([]); continue; }
        const block = /^(DIV|P|LI|H\d)$/.test(n.tagName);
        if (block && cur().length) lines.push([]);
        const fw = n.style ? n.style.fontWeight : '', fs = n.style ? n.style.fontSize : '';
        const sz = n.tagName === 'FONT' && n.getAttribute('size');
        walk(n, hl || /^(B|STRONG|MARK)$/.test(n.tagName) || fw === 'bold' || +fw >= 600, sz ? stZ(sz) : ST_CSSZ[fs] || z);
        if (block && cur().length) lines.push([]);
      }
    }
  };
  walk(root, false, 3);
  return lines;
}
const stTxt = ln => ln.map(c => c.ch).join('');
function stFrames(lines) {
  const out = [[]];
  for (const ln of lines) /^\s*[-–—_]{3,}\s*$/.test(stTxt(ln)) ? out.push([]) : out[out.length - 1].push(ln);
  const blank = l => !stTxt(l).trim();
  return out.map(f => {
    let a = 0, b = f.length;
    while (a < b && blank(f[a])) a++;
    while (b > a && blank(f[b - 1])) b--;
    return f.slice(a, b);
  }).filter(f => f.length);
}
const stDemo = src => src.split('\n').map(line => {
  const out = []; let hl = false;
  for (const part of line.split('**')) { for (const ch of part) out.push({ ch, hl, z: 3 }); hl = !hl; }
  return out;
});
function stHTML(lines) {
  return lines.map(ln => {
    if (!ln.length) return '<div><br></div>';
    let h = '';
    for (let i = 0; i < ln.length;) {   // تکه‌های پشت‌سرهم با تأکید و اندازه‌ی یکسان
      const hl = ln[i].hl, z = ln[i].z || 3; let t = '';
      while (i < ln.length && ln[i].hl === hl && (ln[i].z || 3) === z) t += esc(ln[i++].ch);
      if (hl) t = `<b>${t}</b>`;
      h += z === 3 ? t : `<font size="${z}">${t}</font>`;
    }
    return `<div>${h}</div>`;
  }).join('');
}
// کلمه‌ها؛ کلمه‌ای که دست‌کم نصفش انتخاب شده کامل رنگی می‌شود (رنگ نیمه‌کاره اتصال حروف را می‌شکند).
// اندازه هم کلمه‌به‌کلمه است: اندازه‌ای که بیشترِ حرف‌های کلمه دارند.
// pre = تعداد فاصله‌های قبل از کلمه، همان‌طور که تایپ شده (چند فاصله = جای بیشتر؛ فاصله‌ی اول خط = تورفتگی).
function stTokens(ln) {
  const out = []; let t = null, pre = 0, preHl = true;
  ln.forEach((c, i) => {
    if (c.ch === ' ' || c.ch === '\t') { t = null; pre += c.ch === '\t' ? 4 : 1; if (!c.hl) preHl = false; return; }
    if (!t) { out.push(t = { t: '', a: i, b: i, n: 0, h: 0, zs: {}, pre, preHl: pre > 0 && preHl }); pre = 0; preHl = true; }
    t.t += c.ch; t.b = i + 1; t.n++; if (c.hl) t.h++;
    t.zs[c.z || 3] = (t.zs[c.z || 3] || 0) + 1;
  });
  return out.map((k, i) => ({ t: k.t, a: k.a, b: k.b, i, pre: k.pre, preHl: k.preHl, hl: k.h * 2 >= k.n,
    z: +Object.keys(k.zs).sort((a, b) => k.zs[b] - k.zs[a] || b - a)[0] }));
}

/* ---------- ترتیب راست‌به‌چپ (الگوریتم دوجهتی یونیکد، UAX #9) ----------
   حرف‌به‌حرف، مثل خود مرورگر در ویرایشگر (dir=rtl): قاعده‌های W1–W7، جفت پرانتزها (N0)، N1/N2، سطح‌ها (I2)
   و برعکس کردن تکه‌ها در هر خط (L2). قرینه‌شدن پرانتز را خود canvas در تکه‌های راست‌به‌چپ انجام می‌دهد.
   قبلاً جهت کلمه‌به‌کلمه تعیین می‌شد و «(Baidu» یک کلمه‌ی انگلیسی حساب می‌شد؛ پرانتز سمت اشتباه می‌افتاد (۲۰۲۶-۱۰-۰۵). */
const ST_LETTER = /\p{L}/u;
function stClass(ch) {
  const u = ch.codePointAt(0);
  if (u === 0x20 || u === 0x09 || (u >= 0x2000 && u <= 0x200A) || u === 0x3000) return 'WS';
  if ((u >= 0x30 && u <= 0x39) || (u >= 0x6F0 && u <= 0x6F9)) return 'EN';             // رقم لاتین و فارسی
  if ((u >= 0x660 && u <= 0x669) || u === 0x66B || u === 0x66C) return 'AN';            // رقم عربی
  if (u === 0x2B || u === 0x2D) return 'ES';
  if ((u >= 0x23 && u <= 0x25) || (u >= 0xA2 && u <= 0xA5) || u === 0xB0 || u === 0xB1 || u === 0x66A
      || u === 0x2030 || u === 0x2031 || (u >= 0x20A0 && u <= 0x20CF)) return 'ET';
  if (u === 0x2C || u === 0x2E || u === 0x2F || u === 0x3A || u === 0xA0 || u === 0x60C || u === 0x202F) return 'CS';
  if ((u >= 0x300 && u <= 0x36F) || (u >= 0x610 && u <= 0x61A) || (u >= 0x64B && u <= 0x65F) || u === 0x670
      || (u >= 0x6D6 && u <= 0x6DC) || (u >= 0x6DF && u <= 0x6E4) || u === 0x6E7 || u === 0x6E8
      || (u >= 0x6EA && u <= 0x6ED) || (u >= 0xFE00 && u <= 0xFE0F)) return 'NSM';         // اعراب و انتخاب‌گر شکل
  if ((u >= 0x200B && u <= 0x200D) || u === 0xFEFF || u === 0xAD || u === 0x2060) return 'BN';   // نیم‌فاصله و ZWJ
  if ((u >= 0x590 && u <= 0x5FF) || (u >= 0x7C0 && u <= 0x85F) || (u >= 0xFB1D && u <= 0xFB4F)) return 'R';
  if ((u >= 0x600 && u <= 0x6FF) || (u >= 0x750 && u <= 0x77F) || (u >= 0x8A0 && u <= 0x8FF)
      || (u >= 0xFB50 && u <= 0xFDFF) || (u >= 0xFE70 && u <= 0xFEFF)) return 'AL';         // حرف فارسی/عربی
  return ST_LETTER.test(ch) ? 'L' : 'ON';
}
const ST_PAIR = { '(': ')', '[': ']', '{': '}' }, ST_UNPAIR = { ')': '(', ']': '[', '}': '{' };
// سطح هر حرف در یک پاراگراف راست‌به‌چپ: ۱ = راست‌به‌چپ، ۲ = چپ‌به‌راست (انگلیسی و عدد)
function stLevels(ln) {
  const cls = ln.map(c => stClass(c.ch)), idx = [];
  cls.forEach((c, i) => { if (c !== 'BN') idx.push(i); });   // X9: نیم‌فاصله در محاسبه نیست، آخر سطح همسایه را می‌گیرد
  const t = idx.map(i => cls[i]), m = t.length;
  const strong = x => x === 'L' ? 'L' : x === 'R' || x === 'EN' || x === 'AN' ? 'R' : null;   // عدد در حکم R
  for (let k = 0; k < m; k++) if (t[k] === 'NSM') t[k] = k ? t[k - 1] : 'R';                    // W1
  let last = 'R';
  for (let k = 0; k < m; k++) {                                                                   // W2
    if (t[k] === 'L' || t[k] === 'R' || t[k] === 'AL') last = t[k];
    else if (t[k] === 'EN' && last === 'AL') t[k] = 'AN';
  }
  for (let k = 0; k < m; k++) if (t[k] === 'AL') t[k] = 'R';                                      // W3
  for (let k = 1; k < m - 1; k++) {                                                               // W4
    if (t[k] === 'ES' && t[k - 1] === 'EN' && t[k + 1] === 'EN') t[k] = 'EN';
    else if (t[k] === 'CS' && (t[k - 1] === 'EN' || t[k - 1] === 'AN') && t[k + 1] === t[k - 1]) t[k] = t[k - 1];
  }
  for (let k = 0; k < m; k++) if (t[k] === 'ET') {                                                // W5
    let e = k; while (e < m && t[e] === 'ET') e++;
    if ((k > 0 && t[k - 1] === 'EN') || (e < m && t[e] === 'EN')) for (let j = k; j < e; j++) t[j] = 'EN';
    k = e - 1;
  }
  for (let k = 0; k < m; k++) if (t[k] === 'ES' || t[k] === 'ET' || t[k] === 'CS') t[k] = 'ON';  // W6
  last = 'R';
  for (let k = 0; k < m; k++) {                                                                   // W7
    if (t[k] === 'L' || t[k] === 'R') last = t[k];
    else if (t[k] === 'EN' && last === 'L') t[k] = 'L';
  }
  const stack = [], pairs = [];                                                                   // N0: جفت پرانتزها
  for (let k = 0; k < m; k++) {
    const ch = ln[idx[k]].ch;
    if (t[k] !== 'ON') continue;
    if (ST_PAIR[ch]) { if (stack.length === 63) break; stack.push([ch, k]); }
    else if (ST_UNPAIR[ch]) {
      for (let j = stack.length - 1; j >= 0; j--) if (stack[j][0] === ST_UNPAIR[ch]) { pairs.push([stack[j][1], k]); stack.length = j; break; }
    }
  }
  pairs.sort((a, b) => a[0] - b[0]);
  for (const [o, c] of pairs) {
    let inside = null;
    for (let k = o + 1; k < c; k++) { const d = strong(t[k]); if (d === 'R') { inside = 'R'; break; } if (d) inside = d; }
    if (!inside) continue;
    let dir = 'R';
    if (inside === 'L') {   // داخلش فقط انگلیسی: اگر پیش از پرانتز هم انگلیسی بود چپ‌به‌راست، وگرنه راست‌به‌چپ
      let before = 'R';
      for (let k = o - 1; k >= 0; k--) { const d = strong(t[k]); if (d) { before = d; break; } }
      dir = before;
    }
    for (const b of [o, c]) { t[b] = dir; for (let k = b + 1; k < m && cls[idx[k]] === 'NSM'; k++) t[k] = dir; }
  }
  for (let k = 0; k < m; k++) {                                                                   // N1 + N2
    if (strong(t[k])) continue;
    let e = k; while (e < m && !strong(t[e])) e++;
    const before = k ? strong(t[k - 1]) : 'R', after = e < m ? strong(t[e]) : 'R';
    for (let j = k; j < e; j++) t[j] = before === after ? before : 'R';
    k = e - 1;
  }
  const lv = new Array(ln.length);
  idx.forEach((i, k) => { lv[i] = t[k] === 'R' ? 1 : 2; });                                     // I2
  for (let i = 0; i < lv.length; i++) if (lv[i] === undefined) lv[i] = i ? lv[i - 1] : 1;
  return lv;
}
const ST_LV = new WeakMap();   // سطح‌های هر پاراگراف، یک بار برای همه‌ی دورهای کوچک کردن فونت
const stLvOf = ln => { let v = ST_LV.get(ln); if (!v) ST_LV.set(ln, (v = stLevels(ln))); return v; };

/* ---------- کشیدن ---------- */
const ST_MC = new Map();
function stW(ctx, t) {
  const key = ctx.font + '|' + t; let w = ST_MC.get(key);
  if (w === undefined) { if (ST_MC.size > 8000) ST_MC.clear(); w = ctx.measureText(t).width; ST_MC.set(key, w); }
  return w;
}
function stLum(hex) {
  const n = parseInt(String(hex).slice(1), 16);
  return isNaN(n) ? 0 : (0.2126 * (n >> 16 & 255) + 0.7152 * (n >> 8 & 255) + 0.0722 * (n & 255)) / 255;
}
function stAlpha(hex, a) {
  const n = parseInt(String(hex).slice(1), 16);
  return `rgba(${n >> 16 & 255},${n >> 8 & 255},${n & 255},${a})`;
}
function stRR(ctx, x, y, w, h, r) {
  ctx.beginPath();
  if (ctx.roundRect) ctx.roundRect(x, y, w, h, r); else ctx.rect(x, y, w, h);
}
function stBgImg(file) {
  if (!file) return null;
  let im = ST_BG.get(file);
  if (!im) {
    im = new Image(); ST_BG.set(file, im);
    im.onload = () => stSchedule(true);
    im.src = '/story-bg/' + encodeURIComponent(file);
  }
  return im.complete && im.naturalWidth ? im : null;
}
function stBg(ctx, s) {
  const im = s.bgMode === 'image' ? stBgImg(s.bgImage) : null;
  if (im) {
    const r = Math.max(STW / im.naturalWidth, STH / im.naturalHeight), w = im.naturalWidth * r, h = im.naturalHeight * r;
    ctx.drawImage(im, (STW - w) / 2, (STH - h) / 2, w, h);
    if (s.bgDim > 0) { ctx.fillStyle = stAlpha(s.bg, s.bgDim); ctx.fillRect(0, 0, STW, STH); }
  } else if (s.bgMode === 'gradient') {
    const g = ctx.createLinearGradient(0, 0, STW * 0.35, STH);
    g.addColorStop(0, s.bg); g.addColorStop(1, s.bg2);
    ctx.fillStyle = g; ctx.fillRect(0, 0, STW, STH);
  } else {
    ctx.fillStyle = s.bg; ctx.fillRect(0, 0, STW, STH);
  }
  if (s.deco === 'frame') {
    ctx.strokeStyle = stAlpha(s.fg, 0.3); ctx.lineWidth = 3;
    stRR(ctx, 56, 56, STW - 112, STH - 112, 34); ctx.stroke();
  }
}
function stLogoBox(s) {
  if (s.logo === 'none' || !ST.logos) return null;
  const tone = s.bgMode === 'gradient' ? (stLum(s.bg) + stLum(s.bg2)) / 2 : stLum(s.bg);
  const set = (s.logoInk === 'auto' ? tone < 0.5 : s.logoInk === 'light') ? ST.logos.light : ST.logos.dark;
  if (!set) return null;
  const part = s.logo === 'mark' ? set.mark : set.full;
  const w = STW * s.logoW, h = w * part.sh / part.sw;
  return { part, w, h, x: (STW - w) / 2, y: s.logo === 'top' ? ST_SAFE.top : STH - ST_SAFE.bottom - h };
}
// شکستن خط. هر کلمه اندازه‌ی خودش را دارد؛ فاصله‌ی بین دو کلمه = تعداد فاصله‌ها × پهنای فاصله‌ی کلمه‌ی بزرگ‌تر.
// فاصله‌های اول خط تورفتگی می‌شوند (مثل ویرایشگر، فقط سطر اول؛ خطی که خودش شکسته شده تورفتگی ندارد).
// box = {x, w}: کادر متن به‌جای پهنای کامل استوری (تب کاروسل از همین موتور استفاده می‌کند)
function stLayout(ctx, frame, s, size, box) {
  const maxW = box ? box.w : STW - 2 * ST_PAD, pitch0 = size * s.lh, lhBig = 1 + (s.lh - 1) * 0.55;
  const font = px => `${s.weight} ${px}px ${ST_FONT}`;
  const space = px => { ctx.font = font(px); return stW(ctx, ' '); };
  const lines = []; let h = 0, widest = 0, cur = [], cw = 0, ind = 0, para = null, lv = null;
  const close = () => {   // خطی که بخش بزرگ دارد بلندتر می‌شود، ولی با فاصله‌ی خطِ تنگ‌تر تا از هم نپاشد
    const mx = Math.max(...cur.map(t => t.px));
    const pitch = mx <= size ? mx * s.lh : Math.max(pitch0, mx * lhBig);
    cur[cur.length - 1].sp = 0;
    lines.push({ toks: cur, w: cw, ind, mx, pitch, para, lv }); h += pitch; cur = []; cw = 0; ind = 0;
  };
  for (const ln of frame) {
    const toks = stTokens(ln);
    if (!toks.length) { lines.push(null); h += pitch0 * s.pgap; continue; }
    para = ln; lv = stLvOf(ln);
    for (const t of toks) {
      t.px = size * (ST_SIZES[t.z] || 1);
      ctx.font = font(t.px); t.w = stW(ctx, t.t); widest = Math.max(widest, t.w);
      const prev = cur[cur.length - 1];
      if (!prev) {   // اولین کلمه‌ی خط: تورفتگی، ولی نه آن‌قدر که خود کلمه جا نشود
        ind = Math.min(space(t.px) * t.pre, Math.max(0, maxW - t.w));
        cur.push(t); cw = ind + t.w; continue;
      }
      const gap = space(Math.max(prev.px, t.px)) * t.pre;
      if (cw + gap + t.w > maxW) { close(); cur.push(t); cw = t.w; continue; }   // فاصله‌های سر شکستگی خط می‌افتند
      prev.sp = gap; cur.push(t); cw += gap + t.w;
    }
    close();
  }
  return { lines, h, pitch0, size, fits: widest <= maxW };
}
function stLines(ctx, L, s, y, box) {
  const font = px => `${s.weight} ${px}px ${ST_FONT}`;
  const markFg = stLum(s.hl) > 0.5 ? (stLum(s.bg) < 0.4 ? s.bg : ST_PAL.bg) : '#ffffff';
  ctx.textBaseline = 'alphabetic'; ctx.textAlign = 'left';
  for (const ln of L.lines) {
    if (!ln) { y += L.pitch0 * s.pgap; continue; }
    ctx.font = font(ln.mx);   // همه‌ی کلمه‌های خط روی یک خط کرسی، به اندازه‌ی بزرگ‌ترینشان
    const m = ctx.measureText('گل'), asc = m.fontBoundingBoxAscent, desc = m.fontBoundingBoxDescent;
    const base = y + (ln.pitch - asc - desc) / 2 + asc;
    // تکه‌ها به ترتیب منطقی: تورفتگی، تکه‌های هم‌سطحِ هر کلمه، فاصله‌ی بعد از هر کلمه (با سطح خود فاصله‌ها)
    const segs = [];
    if (ln.ind) segs.push({ w: ln.ind, lvl: 1 });
    ln.toks.forEach((t, k) => {
      ctx.font = font(t.px);
      for (let i = t.a; i < t.b;) {
        const l = ln.lv[i]; let j = i;
        while (j < t.b && ln.lv[j] === l) j++;
        const text = ln.para.slice(i, j).map(c => c.ch).join('');
        segs.push({ t, text, lvl: l, w: stW(ctx, text) });
        i = j;
      }
      const nx = ln.toks[k + 1];
      if (nx) segs.push({ w: t.sp, lvl: ln.lv[nx.a - 1], hl: nx.preHl });
    });
    for (let lev = Math.max(...segs.map(g => g.lvl)); lev >= 1; lev--)   // L2: از بالاترین سطح تا ۱ برعکس کن
      for (let i = 0; i < segs.length;) {
        if (segs[i].lvl < lev) { i++; continue; }
        let j = i; while (j < segs.length && segs[j].lvl >= lev) j++;
        segs.splice(i, j - i, ...segs.slice(i, j).reverse()); i = j;
      }
    const total = segs.reduce((a, g) => a + g.w, 0);
    let x = box ? (s.align === 'center' ? box.x + (box.w - total) / 2 : box.x + box.w - total)
      : s.align === 'center' ? (STW - total) / 2 : STW - ST_PAD - total;
    for (const g of segs) { g.x0 = x; x += g.w; }
    if (s.hlMode === 'marker') {   // تکه‌های تأکیدیِ کنار هم یک نوار: با یک فاصله، یا فاصله‌هایی که خودشان تأکید خورده‌اند
      const bands = []; let band = null, gap = [];
      for (const g of segs) {
        if (!g.t) { if (band) gap.push(g); continue; }
        if (!g.t.hl) { band = null; gap = []; continue; }
        const pad = g.t.px * 0.13, y0 = base - g.t.px * 0.86, y1 = base + g.t.px * 0.38;
        if (band && (gap.every(q => q.hl) || gap.reduce((a, q) => a + q.w, 0) <= ln.mx * 0.45)) {
          band.x1 = g.x0 + g.w + pad; band.y0 = Math.min(band.y0, y0); band.y1 = Math.max(band.y1, y1);
        } else bands.push(band = { x0: g.x0 - pad, x1: g.x0 + g.w + pad, y0, y1 });
        gap = [];
      }
      ctx.fillStyle = s.hl;
      for (const b of bands) { stRR(ctx, b.x0, b.y0, b.x1 - b.x0, b.y1 - b.y0, ln.mx * 0.16); ctx.fill(); }
    }
    for (const g of segs) {
      if (!g.t) continue;
      ctx.font = font(g.t.px);
      ctx.fillStyle = g.t.hl ? (s.hlMode === 'marker' ? markFg : s.hl) : s.fg;
      ctx.direction = g.lvl % 2 ? 'rtl' : 'ltr';   // در تکه‌ی راست‌به‌چپ canvas پرانتز را قرینه می‌کند
      ctx.fillText(g.text, g.x0, base);
    }
    y += ln.pitch;
  }
}
const stDecoH = (s, size) => s.deco === 'bar' ? size * 0.75 : s.deco === 'quote' ? size * 1.45 : 0;
function stDeco(ctx, s, size, y) {
  ctx.fillStyle = s.decoColor;
  if (s.deco === 'bar') {
    const w = Math.max(90, size * 2.1), h = Math.max(8, size * 0.16);
    stRR(ctx, s.align === 'center' ? (STW - w) / 2 : STW - ST_PAD - w, y, w, h, h / 2); ctx.fill();
  } else if (s.deco === 'quote') {
    ctx.font = `900 ${size * 2.6}px ${ST_FONT}`; ctx.direction = 'rtl'; ctx.textBaseline = 'alphabetic';
    ctx.textAlign = s.align === 'center' ? 'center' : 'right';
    ctx.fillText('«', s.align === 'center' ? STW / 2 : STW - ST_PAD, y + size * 1.5);
  }
}
// یک استوری کامل. اگر متن جا نشود فونت دو پیکسل دو پیکسل کوچک می‌شود (تا ۲۶).
function stDraw(ctx, frame, s) {
  stBg(ctx, s);
  const lg = stLogoBox(s), gap = Math.max(56, s.size * 0.9);
  let top = ST_SAFE.top + 10, bottom = STH - ST_SAFE.bottom - 10;
  if (lg) { if (s.logo === 'top') top = lg.y + lg.h + gap; else bottom = lg.y - gap; }
  let size = s.size, L;
  for (;;) {
    L = stLayout(ctx, frame, s, size);
    if ((L.h + stDecoH(s, size) <= bottom - top && L.fits) || size <= 26) break;
    size -= 2;
  }
  const blockH = L.h + stDecoH(s, size);
  let y = s.valign === 'center' ? top + (bottom - top - blockH) / 2 : Math.min(s.top * STH, bottom - blockH);
  y = Math.max(top, y);
  stDeco(ctx, s, size, y);
  stLines(ctx, L, s, y + stDecoH(s, size));
  if (lg) ctx.drawImage(lg.part.img, lg.part.sx, lg.part.sy, lg.part.sw, lg.part.sh, lg.x, lg.y, lg.w, lg.h);
  return { size, shrunk: size < s.size, overflow: blockH > bottom - top + 1 || !L.fits };
}
function stPaint(cv, frame, s, scale = 1) {
  const w = Math.round(STW * scale), h = Math.round(STH * scale);
  if (cv.width !== w) cv.width = w;
  if (cv.height !== h) cv.height = h;
  const ctx = cv.getContext('2d');
  ctx.setTransform(scale, 0, 0, scale, 0, 0);
  ctx.clearRect(0, 0, STW, STH);
  return stDraw(ctx, frame, s);
}

/* ---------- لوگو و فونت ---------- */
// حاشیه‌ی شفاف لوگو بریده می‌شود؛ «نشان» = نوار اول (مغز) تا اولین فاصله‌ی خالی قبل از نوشته.
function stTrim(img) {
  const c = document.createElement('canvas'); c.width = img.naturalWidth || img.width; c.height = img.naturalHeight || img.height;
  const x = c.getContext('2d'); x.drawImage(img, 0, 0);
  const d = x.getImageData(0, 0, c.width, c.height).data, W = c.width;
  const ink = (xx, y) => d[(y * W + xx) * 4 + 3] > 24;
  const rows = []; let x0 = W, x1 = -1, y0 = -1, y1 = -1;
  for (let y = 0; y < c.height; y++) {
    let any = false;
    for (let xx = 0; xx < W; xx++) if (ink(xx, y)) { any = true; if (xx < x0) x0 = xx; if (xx > x1) x1 = xx; }
    rows.push(any); if (any) { if (y0 < 0) y0 = y; y1 = y; }
  }
  if (y0 < 0) return null;
  const full = { img, sx: x0, sy: y0, sw: x1 - x0 + 1, sh: y1 - y0 + 1 };
  let gapAt = -1, run = 0;
  for (let y = y0; y <= y1; y++) {
    if (rows[y]) { run = 0; continue; }
    if (++run > (y1 - y0) * 0.03) { gapAt = y - run + 1; break; }
  }
  if (gapAt < 0) return { full, mark: full };
  let mx0 = W, mx1 = -1;
  for (let y = y0; y < gapAt; y++) for (let xx = 0; xx < W; xx++) if (ink(xx, y)) { if (xx < mx0) mx0 = xx; if (xx > mx1) mx1 = xx; }
  return { full, mark: { img, sx: mx0, sy: y0, sw: mx1 - mx0 + 1, sh: gapAt - y0 } };
}
// لوگو = اولین تصویر سؤال «لوگو» در هسته‌ی برند: روی زمینه‌ی روشن با رنگ خودش، روی زمینه‌ی تیره سفیدشده.
function stWhite(img) {
  const c = document.createElement('canvas'); c.width = img.naturalWidth; c.height = img.naturalHeight;
  const x = c.getContext('2d'); x.drawImage(img, 0, 0);
  x.globalCompositeOperation = 'source-in'; x.fillStyle = '#ffffff'; x.fillRect(0, 0, c.width, c.height);
  return c;
}
async function stLogos() {
  // هر بار از نو: شاید لوگو یا رنگ‌ها همین الان در هسته‌ی برند عوض شده باشند
  const b = await api('/api/brand');
  stApplyBrand(b);
  const f = (((b && b.fields && b.fields.logo && b.fields.logo.v) || []).find(x => x && x.file) || {}).file;
  const k = f ? await new Promise(r => { const i = new Image(); i.onload = () => r(i); i.onerror = () => r(null); i.src = '/brand-assets/' + encodeURIComponent(f); }) : null;
  ST.logos = { light: k && stTrim(stWhite(k)), dark: k && stTrim(k) };   // light = لوگوی سفید برای زمینه‌ی تیره
}

// رنگ‌های «هسته‌ی برند ← هویت بصری» ← زمینه، تأکید و دایره‌های رنگ استوری و کاروسل.
// اصلیِ تیره = زمینه؛ تأکیدی = رنگ تأکید؛ روشن‌ترین = زمینه‌ی نمونه‌ی «روشن».
function stApplyBrand(b) {
  const pal = ((b && b.fields && b.fields.colors && b.fields.colors.v) || [])
    .filter(c => c && /^#[0-9a-f]{6}$/i.test(c.hex || '')).map(c => ({ hex: c.hex.toLowerCase(), role: c.role || '' }));
  if (!pal.length) return;
  const dark = pal.filter(c => stLum(c.hex) < 0.35), light = pal.filter(c => stLum(c.hex) > 0.7);
  const main = dark.find(c => c.role === 'اصلی') || dark[0];
  const accent = pal.find(c => c.role === 'تأکیدی' && c !== main && stLum(c.hex) > 0.3) || pal.find(c => c !== main && stLum(c.hex) > 0.35 && stLum(c.hex) < 0.85);
  const second = dark.find(c => c !== main);
  if (main) {
    ST_PAL.bg = main.hex; ST_BASE.bg = main.hex;
    ST_PAL.bg2 = second ? second.hex : stShade(main.hex, 0.55); ST_BASE.bg2 = ST_PAL.bg2;
  }
  if (accent) { ST_BASE.hl = accent.hex; ST_PAL.alt = accent.hex; ST_BASE.decoColor = accent.hex; }
  if (light[0]) ST_PAL.light = light[0].hex;
  const hexes = pal.map(c => c.hex);
  const front = (k, list) => { ST_SW[k] = [...new Set([...list, ...ST_SW[k]])].slice(0, 10); };
  front('bg', [...dark.map(c => c.hex), ...light.map(c => c.hex)]);
  front('bg2', dark.map(c => c.hex));
  front('fg', light.map(c => c.hex).concat(dark.map(c => c.hex)));
  front('hl', hexes);
  front('decoColor', hexes);
}
// یک رنگ تیره‌تر (ضریب ۰ تا ۱)
function stShade(hex, k) {
  const n = parseInt(hex.slice(1), 16), f = v => Math.round(v * k).toString(16).padStart(2, '0');
  return '#' + f(n >> 16 & 255) + f(n >> 8 & 255) + f(n & 255);
}
async function stFonts() {
  try {
    const faces = await Promise.all([500, 600, 700, 800, 900].map(w => document.fonts.load(`${w} 40px Vazirmatn`, 'سلام')));
    ST.fontOK = faces.every(f => f.length);
  } catch { ST.fontOK = false; }
}

/* ---------- صفحه ---------- */
// «$bg» و مانند آن در نمونه‌ها = نقش رنگ برند (ST_PAL)
const stPreset = key => {
  const s = (ST_PRESETS.find(p => p.key === key) || ST_PRESETS[0]).s, out = { ...ST_BASE };
  for (const [k, v] of Object.entries(s)) out[k] = typeof v === 'string' && v[0] === '$' ? (ST_PAL[v.slice(1)] || ST_BASE[k]) : v;
  return out;
};
const stSame = (a, b) => !!a && !!b && Object.keys(ST_BASE).every(k => String(a[k]) === String(b[k]));
const stLS = (k, v) => { try { if (v === undefined) return localStorage.getItem(k); localStorage.setItem(k, v); } catch {} return null; };
const stTrimLines = f => {
  const blank = l => !stTxt(l).trim(); let a = 0, b = f.length;
  while (a < b && blank(f[a])) a++;
  while (b > a && blank(f[b - 1])) b--;
  return f.slice(a, b);
};
const stParse = html => stRead(new DOMParser().parseFromString(html || '', 'text/html').body);   // DOMParser: هیچ اسکریپتی اجرا نمی‌شود
const stPlain = text => text.split('\n').map(l => [...l].map(ch => ({ ch, hl: false, z: 3 })));
// خط‌های خالیِ اول متن می‌مانند (Enter متن را پایین می‌برد)؛ فقط خالی‌های آخر حذف می‌شوند
const stFrameOf = el => { const f = stRead($('.st-ed', el)); let b = f.length; while (b && !stTxt(f[b - 1]).trim()) b--; return f.slice(0, b); };

// هر استوری یک کارت جدا با ویرایشگر و پیش‌نمایش خودش است و کارت تازه زیر قبلی می‌آید، تا همه‌ی استوری‌ها در صفحه دیده شوند.
// (قبلاً یک ویرایشگر بود با «---» و پیش‌نمایش‌ها کنار هم در یک ردیف افقی بودند که از سومی به بعد از کادر بیرون می‌زد.)
async function viewStory() {
  const keep = $$('.st-story .st-ed').map(e => e.innerHTML);   // بعد از اولین ذخیره صفحه از نو ساخته می‌شود؛ متن‌ها بمانند
  $('#page').innerHTML = '<div class="empty">در حال بارگذاری…</div>';
  const [d, b] = await Promise.all([api('/api/story'), api('/api/brand'), stFonts(), stLogos()]);
  for (const c of (b && b.fields && b.fields.colors && b.fields.colors.v) || []) if (c.hex) ST.names[c.hex.toLowerCase()] = c.name;
  ST.saved = d && d.style ? { ...ST_BASE, ...d.style } : null;
  ST.savedPreset = (d && d.preset) || '';
  if (!ST.style) {
    ST.style = ST.saved ? { ...ST.saved } : stPreset('archive');
    ST.preset = ST.saved ? 'mine' : 'archive'; ST.mod = false;
  }
  const gal = `
    <section class="st-galwrap">
      <div class="st-galhead"><h3>${ST.saved ? 'نمونه‌های دیگر' : 'نمونه‌ها — یکی را انتخاب کن'}</h3>
        <p>روی هرکدام بزنی، روی همه‌ی استوری‌هایت اعمال می‌شود. بعد اندازه، رنگ و لوگو را تنظیم کن و «ذخیره به‌عنوان استایل من» را بزن تا از این به بعد همیشه همان بیاید.</p></div>
      <div id="stGal" class="st-gal"></div>
    </section>`;
  $('#page').innerHTML = `
    <div class="st-wrap">
      <div class="page-head"><h2>استوری متنی</h2>
        <p>متن هر استوری را در کارت خودش بنویس؛ با استایل ثابتت روی فایل ۱۰۸۰×۱۹۲۰ کشیده می‌شود و آماده‌ی انتشار دانلود می‌شود. پیش‌نمایش همان فایل است.</p></div>
      ${ST.fontOK ? '' : '<div class="st-warn">فونت وزیرمتن بارگذاری نشد و خروجی با فونت دیگری کشیده می‌شود. صفحه را یک بار تازه کن.</div>'}
      ${ST.saved ? '' : gal}
      <div class="st-layout">
        <section class="st-list">
          <div id="stStories" class="st-stories"></div>
          <div class="st-listbar">
            <button class="btn" data-sta="add">+ استوری بعدی</button>
            <button class="btn primary" data-sta="all" hidden>دانلود همه</button>
            <span class="st-grow"></span>
            <label class="st-check"><input type="checkbox" id="stGuides"> نشان دادن محدوده‌ی امن اینستاگرام</label>
          </div>
          <p class="st-hint">بخشی از متن را انتخاب کن: «تأکید» یا <kbd>⌘B</kbd> رنگی‌اش می‌کند؛ «بزرگ‌تر» و «کوچک‌تر» (<kbd>⌘⇧.</kbd> و <kbd>⌘⇧,</kbd>) اندازه‌اش را پله‌پله عوض می‌کنند · خط خالی = فاصله‌ی پاراگراف · متنی که بچسبانی و خطی با فقط «---» داشته باشد، خودش به چند استوری تقسیم می‌شود</p>
        </section>
        <aside class="st-side"><div id="stCtl" class="st-ctl"></div></aside>
      </div>
      ${ST.saved ? gal : ''}
    </div>`;
  stBind($('.st-wrap'));
  for (const h of keep.length ? keep : stDrafts()) stAddStory(h);
  stCtl();
  $('#stGal').innerHTML = stGalHTML();
  stSchedule(true);
}

// پیش‌نویس‌ها، یکی برای هر استوری. پیش‌نویس قدیمیِ تک‌ویرایشگر (st-draft با «---») به چند استوری تبدیل می‌شود.
function stDrafts() {
  try { const a = JSON.parse(stLS('st-drafts') || 'null'); if (Array.isArray(a) && a.length) return a.map(String); } catch {}
  const old = stLS('st-draft');
  const fr = old ? stFrames(stParse(old)) : [];
  return fr.length ? fr.map(stHTML) : [''];
}
function stSaveDrafts() {
  clearTimeout(ST.tDraft);
  ST.tDraft = setTimeout(() => stLS('st-drafts', JSON.stringify($$('.st-story .st-ed').map(e => e.innerHTML))), 400);
}
function stAddStory(html, after, focus) {
  const box = $('#stStories'); if (!box) return null;
  const el = document.createElement('article'); el.className = 'st-story';
  el.innerHTML = `
    <div class="st-sedit">
      <div class="st-shead">
        <b class="st-snum"></b><span class="st-grow"></span>
        <button class="st-tool" data-sta="hl" title="Cmd+B">تأکید</button>
        <button class="st-tool" data-sta="big" title="Cmd+Shift+.">بزرگ‌تر</button>
        <button class="st-tool" data-sta="small" title="Cmd+Shift+,">کوچک‌تر</button>
        <button class="st-tool st-del" data-sta="del"></button>
      </div>
      <div class="st-ed" contenteditable="true" dir="rtl" spellcheck="false" data-ph="متن این استوری را این‌جا بنویس یا بچسبان…"></div>
      <p class="st-fnote"></p>
    </div>
    <div class="st-frame">
      <div class="st-cvwrap"><canvas></canvas><span class="st-badge" hidden>نمونه</span>
        <i class="st-g t">نوار پروفایل</i><i class="st-g b">نوار پیام</i></div>
      <div class="st-fbar"><button class="btn primary" data-std>دانلود PNG</button><button class="btn" data-stcp title="کپی تصویر در کلیپ‌بورد">کپی</button></div>
    </div>`;
  const ed = $('.st-ed', el);
  if (html) ed.innerHTML = stHTML(stParse(html));
  if (after) after.after(el); else box.appendChild(el);
  ed.classList.toggle('is-empty', !ed.textContent.trim());
  stNumber(); stSaveDrafts(); stRenderAll();   // تک‌استوریِ خالی «نمونه» نشان می‌دهد؛ با استوری دوم دیگر نه
  if (focus) { ed.focus(); el.scrollIntoView({ behavior: 'smooth', block: 'center' }); }
  return el;
}
function stNumber() {
  const all = $$('.st-story'), many = all.length > 1;
  all.forEach((el, i) => {
    $('.st-snum', el).textContent = `استوری ${faNum(i + 1)}`;
    const d = $('[data-sta="del"]', el);
    d.textContent = many ? '✕ حذف' : 'پاک کردن'; d.title = many ? 'حذف این استوری' : 'پاک کردن متن';
  });
}
function stDel(el) {
  const ed = $('.st-ed', el), many = $$('.st-story').length > 1;
  if (ed.textContent.trim() && !confirm(many ? 'این استوری حذف شود؟' : 'متن این استوری پاک شود؟')) return;
  if (!many) { ed.innerHTML = ''; return stEdited(ed); }
  el.remove(); stNumber(); stSaveDrafts(); stRenderAll(); stSchedule(false, true);
}

function stBind(wrap) {
  const edOf = t => t && t.closest ? t.closest('.st-ed') : null;
  wrap.addEventListener('paste', e => {   // فقط متن ساده؛ خطی که فقط «---» دارد استوری تازه می‌سازد
    const ed = edOf(e.target); if (!ed) return;
    e.preventDefault();
    const parts = [[]];
    for (const line of (e.clipboardData || window.clipboardData).getData('text/plain').replace(/\r/g, '').split('\n'))
      /^\s*[-–—_]{3,}\s*$/.test(line) ? parts.push([]) : parts[parts.length - 1].push(line);
    document.execCommand('insertText', false, parts[0].join('\n'));
    let after = ed.closest('.st-story'), made = 0;
    for (const p of parts.slice(1)) {
      const lines = stTrimLines(stPlain(p.join('\n')));
      if (lines.length) { after = stAddStory(stHTML(lines), after); made++; }
    }
    if (made) toast(`متن به ${faNum(made + 1)} استوری تقسیم شد`);
  });
  wrap.addEventListener('mousedown', e => {   // دکمه‌های ابزار انتخاب متن را از بین نبرند
    if (e.target.closest('[data-sta="hl"],[data-sta="big"],[data-sta="small"]')) e.preventDefault();
  });
  wrap.addEventListener('keydown', e => {   // ⌘⇧. بزرگ‌تر، ⌘⇧, کوچک‌تر (مثل Google Docs)؛ با e.code تا با کیبورد فارسی هم کار کند
    if (!edOf(e.target) || !(e.metaKey || e.ctrlKey) || !e.shiftKey || (e.code !== 'Period' && e.code !== 'Comma')) return;
    e.preventDefault(); stResize(e.code === 'Period' ? 1 : -1);
  });
  wrap.addEventListener('click', e => {
    const t = e.target, q = s => t.closest(s);
    let b;
    if ((b = q('[data-stp]'))) return stPick(b.dataset.stp);
    if ((b = q('button[data-stk]'))) return stSet(b.dataset.stk, b.dataset.v, true);
    if ((b = q('[data-std]'))) return stDownload(b.closest('.st-story'));
    if ((b = q('[data-stcp]'))) return stCopy(b.closest('.st-story'));
    if ((b = q('[data-sta]'))) return stAct(b.dataset.sta, b.closest('.st-story'));
  });
  wrap.addEventListener('input', e => {
    const t = e.target;
    if (edOf(t) === t) return stEdited(t);
    if (t.matches('input[type=range][data-stk]')) {
      stSet(t.dataset.stk, t.value, false);
      const o = $(`output[data-out="${t.dataset.stk}"]`, wrap); if (o) o.textContent = stFmt(t.dataset.stk, ST.style[t.dataset.stk]);
    } else if (t.matches('input[type=color][data-stk]')) stSet(t.dataset.stk, t.value, false);
  });
  wrap.addEventListener('change', e => {
    const t = e.target;
    if (t.matches('input[type=color][data-stk]') || t.matches('input[type=range][data-stk]')) stCtl();
    else if (t.matches('[data-stfile]') && t.files[0]) stUpload(t.files[0]);
    else if (t.id === 'stGuides') wrap.classList.toggle('guides', t.checked);
  });
}

function stEdited(ed) {
  const el = ed.closest('.st-story');
  ed.classList.toggle('is-empty', !ed.textContent.trim());
  stSaveDrafts();
  clearTimeout(el._t); el._t = setTimeout(() => stRenderStory(el), 80);   // فقط همین استوری
  clearTimeout(ST.tGal); ST.tGal = setTimeout(stRenderGal, 350);
}
function stSchedule(now, gal) {   // تغییر استایل: همه‌ی استوری‌ها
  clearTimeout(ST.tPrev); ST.tPrev = setTimeout(stRenderAll, now ? 0 : 80);
  if (now || gal) { clearTimeout(ST.tGal); ST.tGal = setTimeout(stRenderGal, now ? 20 : 350); }
}
function stSet(key, raw, rebuild) {
  ST.style[key] = ST_NUM.has(key) ? Number(raw) : raw;
  if (key === 'logo' && ST_LOGOW[raw]) ST.style.logoW = ST_LOGOW[raw];
  ST.mod = true;
  if (rebuild) stCtl(); else stCtlNote();
  stMarkGal();
  stSchedule();
}
function stPick(key) {
  ST.style = key === 'mine' && ST.saved ? { ...ST.saved } : stPreset(key);
  ST.preset = key; ST.mod = false;
  stCtl(); stMarkGal(); stSchedule();
}
// ویرایشگری که انتخاب متن در آن است (دکمه‌های هر کارت روی همان انتخاب کار می‌کنند)
function stSelEd() {
  const sel = getSelection(); if (!sel.rangeCount || sel.isCollapsed) return null;
  const n = sel.anchorNode, el = n && (n.nodeType === 3 ? n.parentNode : n);
  const ed = el && el.closest ? el.closest('.st-ed') : null;
  return ed && ed.contains(sel.focusNode) ? ed : null;
}
// اندازه‌ی بخش انتخاب‌شده یک پله بالا/پایین؛ پله‌ی فعلی = پله‌ی اولین حرف انتخاب‌شده
function stResize(d) {
  const ed = stSelEd(); if (!ed) return toast('اول بخشی از متن را انتخاب کن');
  const r = getSelection().getRangeAt(0), root = r.commonAncestorContainer;
  const w = document.createTreeWalker(root.nodeType === 3 ? root.parentNode : root, NodeFilter.SHOW_TEXT);
  let n = w.nextNode(), z = 3;
  while (n && !(r.intersectsNode(n) && n.nodeValue.trim())) n = w.nextNode();
  for (let el = n && n.parentNode; el && el !== ed; el = el.parentNode)
    if (el.tagName === 'FONT' && el.getAttribute('size')) { z = stZ(el.getAttribute('size')); break; }
  const nz = Math.max(1, Math.min(7, z + d));
  if (nz === z) return toast(d > 0 ? 'بزرگ‌تر از این نمی‌شود' : 'کوچک‌تر از این نمی‌شود');
  document.execCommand('styleWithCSS', false, false);
  document.execCommand('fontSize', false, String(nz));
  stEdited(ed);
}
function stAct(a, el) {
  if (a === 'big' || a === 'small') return stResize(a === 'big' ? 1 : -1);
  if (a === 'hl') {
    const ed = stSelEd(); if (!ed) return toast('اول بخشی از متن را انتخاب کن');
    document.execCommand('styleWithCSS', false, false);
    document.execCommand('bold');
    return stEdited(ed);
  }
  if (a === 'add') return stAddStory('', null, true);
  if (a === 'del' && el) return stDel(el);
  if (a === 'save') return stSave();
  if (a === 'all') return $$('.st-story').filter(x => x._full).forEach((x, k) => setTimeout(() => stDownload(x), k * 350));
}

/* ---------- تنظیم استایل ---------- */
const stFmt = (k, v) => k === 'lh' ? faNum(Number(v).toFixed(2)) : k === 'logoW' || k === 'bgDim' ? faNum(Math.round(v * 100)) + '٪' : faNum(v);
function stCtl() {
  const s = ST.style, el = $('#stCtl'); if (!el) return;
  const row = (label, body) => `<div class="st-row"><span class="st-lbl">${label}</span><div class="st-in">${body}</div></div>`;
  const chips = (k, opts) => opts.map(([v, l]) =>
    `<button class="st-chip${String(s[k]) === String(v) ? ' on' : ''}" data-stk="${k}" data-v="${v}">${l}</button>`).join('');
  const sw = k => ST_SW[k].map(c =>
    `<button class="st-sw${String(s[k]).toLowerCase() === c ? ' on' : ''}" style="--c:${c}" data-stk="${k}" data-v="${c}" title="${esc(ST.names[c] || c)}"></button>`).join('')
    + `<input type="color" class="st-pick" data-stk="${k}" value="${esc(s[k])}" title="رنگ دلخواه">`;
  const range = (k, min, max, step) =>
    `<input type="range" data-stk="${k}" min="${min}" max="${max}" step="${step}" value="${s[k]}"><output data-out="${k}">${stFmt(k, s[k])}</output>`;
  const sep = '<span class="st-sep"></span>';
  el.innerHTML = `
    <div class="st-ctlhead"><b>تنظیم استایل</b><span id="stBase"></span></div>
    ${row('زمینه', chips('bgMode', [['solid', 'رنگ ساده'], ['gradient', 'گرادیان'], ['image', 'تصویر']]))}
    ${row(s.bgMode === 'gradient' ? 'رنگ بالا' : s.bgMode === 'image' ? 'رنگ روی تصویر' : 'رنگ زمینه', sw('bg'))}
    ${s.bgMode === 'gradient' ? row('رنگ پایین', sw('bg2')) : ''}
    ${s.bgMode === 'image' ? row('تصویر', `<label class="btn st-up">انتخاب تصویر…<input type="file" accept="image/png,image/jpeg,image/webp" data-stfile hidden></label>`
        + (s.bgImage ? `<span class="st-dim">${esc(s.bgImage.replace(/^\d+-/, ''))}</span>` : '<span class="st-dim">هنوز تصویری نیست؛ تا آن موقع رنگ زمینه کشیده می‌شود.</span>'))
      + row('پررنگیِ رنگ', range('bgDim', 0, 0.9, 0.05)) : ''}
    ${row('رنگ متن', sw('fg'))}
    ${row('تأکید', sw('hl') + sep + chips('hlMode', [['color', 'رنگ متن'], ['marker', 'ماژیک']]))}
    ${row('اندازه‌ی متن', range('size', 30, 110, 1) + chips('size', [[42, 'ریز'], [54, 'متوسط'], [70, 'درشت'], [88, 'خیلی درشت']]))}
    ${row('ضخامت', chips('weight', [[500, 'معمولی'], [600, 'نیمه‌ضخیم'], [700, 'ضخیم'], [800, 'خیلی ضخیم']]))}
    ${row('فاصله‌ی خط‌ها', range('lh', 1.3, 2.3, 0.05))}
    ${row('چینش', chips('align', [['right', 'راست‌چین'], ['center', 'وسط‌چین']]) + sep + chips('valign', [['top', 'از بالا'], ['center', 'وسط صفحه']]))}
    ${row('لوگو', chips('logo', [['none', 'بدون'], ['bottom', 'پایین'], ['top', 'بالا'], ['mark', 'فقط نشان لوگو']]))}
    ${s.logo !== 'none' ? row('اندازه‌ی لوگو', range('logoW', 0.08, 0.5, 0.01)
        + (ST.logos && ST.logos.light ? '' : '<span class="st-dim">لوگویی نیست؛ در «هسته‌ی برند ← هویت بصری» آپلودش کن</span>')) : ''}
    ${row('تزئین', chips('deco', [['none', 'هیچ'], ['bar', 'خط کوتاه'], ['quote', 'گیومه'], ['frame', 'کادر']]))}
    ${s.deco === 'bar' || s.deco === 'quote' ? row('رنگ تزئین', sw('decoColor')) : ''}
    <div class="st-save">
      <button class="btn primary" data-sta="save">ذخیره به‌عنوان استایل من</button>
      <span id="stSaveNote" class="st-dim"></span>
    </div>`;
  stCtlNote();
}
function stCtlNote() {
  const p = ST.preset === 'mine' ? 'استایل من' : (ST_PRESETS.find(x => x.key === ST.preset) || {}).name;
  const base = $('#stBase'); if (base) base.textContent = p ? `بر پایه‌ی «${p}»${ST.mod ? ' · با تغییر' : ''}` : '';
  const n = $('#stSaveNote'); if (!n) return;
  n.textContent = !ST.saved ? 'هنوز استایلی ذخیره نشده؛ تا آن موقع «برند من» باز می‌شود.'
    : stSame(ST.style, ST.saved) ? '✓ همین استایل ذخیره‌شده‌ی توست.' : 'این تغییرها هنوز ذخیره نشده‌اند.';
}
async function stSave() {
  const res = await post('/api/story', { style: ST.style, preset: ST.preset === 'mine' ? ST.savedPreset : ST.preset });
  if (!res.ok) return toast(res.data.error || 'ذخیره نشد');
  const first = !ST.saved;
  ST.saved = { ...ST.style }; ST.savedPreset = res.data.preset || '';
  ST.preset = 'mine'; ST.mod = false;
  toast('✓ استایل ذخیره شد');
  if (first) return viewStory();   // گالری می‌رود پایین و کارت «استایل من» اضافه می‌شود
  stCtlNote(); $('#stGal').innerHTML = stGalHTML(); stSchedule(true);
}
async function stUpload(file) {
  if (file.size > 15 * 1024 * 1024) return toast('تصویر از ۱۵ مگابایت بزرگ‌تر است');
  const data = await new Promise(r => { const fr = new FileReader(); fr.onload = () => r(fr.result); fr.readAsDataURL(file); });
  const res = await post('/api/story/bg', { filename: file.name, data });
  if (!res.ok) return toast(res.data.error || 'آپلود نشد');
  stSet('bgImage', res.data.file, true);
}

/* ---------- پیش‌نمایش، گالری، دانلود ---------- */
const stDemoKey = () => (ST_PRESETS.find(p => p.key === (ST.preset === 'mine' ? ST.savedPreset : ST.preset)) || ST_PRESETS[0]).demo;
function stRenderStory(el) {
  if (!el || !el.isConnected) return;
  const frame = stFrameOf(el), full = frame.some(l => stTxt(l).trim());
  const demo = !full && $$('.st-story').length === 1;   // فقط تک‌استوریِ خالی، متن نمونه نشان می‌دهد
  const r = stPaint($('canvas', el), demo ? stDemo(ST_DEMO[stDemoKey()]) : full ? frame : [], ST.style);
  el._full = full;
  $('.st-badge', el).hidden = !demo;
  $$('.st-fbar button', el).forEach(b => (b.disabled = !full || !ST.fontOK));
  $('.st-fnote', el).textContent = demo ? 'پیش‌نمایش با یک متن نمونه است، فقط برای دیدن استایل. متن خودت را این‌جا بنویس.'
    : !full ? '' : r.overflow ? 'متن برای یک استوری زیاد است و بیرون می‌زند؛ بخشی از آن را به یک استوری تازه ببر.'
    : r.shrunk ? `برای جا شدن، اندازه‌ی متن از ${faNum(ST.style.size)} به ${faNum(r.size)} رسید.` : '';
  const all = $('[data-sta="all"]'); if (all) all.hidden = $$('.st-story').filter(x => x._full).length < 2;
}
const stRenderAll = () => $$('.st-story').forEach(stRenderStory);
function stGalCards() {
  const cards = ST_PRESETS.map(p => ({ ...p, st: stPreset(p.key) }));
  if (ST.saved) cards.unshift({ key: 'mine', name: 'استایل من', note: 'ذخیره‌شده؛ هر بار همین باز می‌شود',
    demo: (ST_PRESETS.find(p => p.key === ST.savedPreset) || ST_PRESETS[0]).demo, st: ST.saved });
  return cards;
}
function stGalHTML() {
  return stGalCards().map(c => `
    <button class="st-card${ST.preset === c.key && !ST.mod ? ' on' : ''}" data-stp="${c.key}">
      <canvas data-stc="${c.key}"></canvas><b>${esc(c.name)}</b><span>${esc(c.note)}</span>
    </button>`).join('');
}
function stRenderGal() {   // گالری با متن اولین استوریِ پر کشیده می‌شود
  const cards = stGalCards(), first = $$('.st-story').map(stFrameOf).find(f => f.some(l => stTxt(l).trim()));
  for (const cv of $$('#stGal canvas[data-stc]')) {
    const c = cards.find(x => x.key === cv.dataset.stc); if (!c) continue;
    const scale = Math.min(0.5, Math.max(0.2, (cv.clientWidth || 160) * (devicePixelRatio || 1) / STW));
    stPaint(cv, first || stDemo(ST_DEMO[c.demo]), c.st, scale);
  }
}
function stMarkGal() {
  $$('#stGal [data-stp]').forEach(b => b.classList.toggle('on', b.dataset.stp === ST.preset && !ST.mod));
}
function stName(el) {
  const all = $$('.st-story'), d = new Date(), p = n => String(n).padStart(2, '0');
  return `story-${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}-${p(d.getHours())}${p(d.getMinutes())}`
    + (all.length > 1 ? `-${all.indexOf(el) + 1}` : '') + '.png';
}
function stDownload(el) {
  const cv = el && $('canvas', el); if (!cv || !el._full) return;
  window.advisorLogStory?.($('.st-ed', el)?.innerText);   // مشاور متن استوری‌های ساخته‌شده را می‌بیند
  window.markStep?.('story');                             // قدم «اولین استوری» در صفحه‌ی شروع
  cv.toBlob(b => {
    const a = document.createElement('a');
    a.href = URL.createObjectURL(b); a.download = stName(el);
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 5000);
  }, 'image/png');
}
function stCopy(el) {
  const cv = el && $('canvas', el); if (!cv || !el._full) return;
  window.advisorLogStory?.($('.st-ed', el)?.innerText);
  try {
    navigator.clipboard.write([new ClipboardItem({ 'image/png': new Promise(r => cv.toBlob(r, 'image/png')) })])
      .then(() => toast('✓ تصویر کپی شد'), () => toast('کپی نشد'));
  } catch { toast('کپی نشد'); }
}

window.viewStory = viewStory;
