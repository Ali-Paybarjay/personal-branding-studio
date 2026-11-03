/* ================= شروع، تنظیمات و راهنمای هر تب =================
   - viewStart: صفحه‌ی «شروع» با قدم‌های راه‌اندازی و پیشرفت (/api/setup).
   - viewSettings: پروفایل، Claude و مدل‌ها، کلید Gemini، اینستاگرام، داده‌ها.
   - GUIDES: راهنمای کوتاه بالای هر تب. خودکار زیر .page-head هر صفحه می‌نشیند (MutationObserver)،
     پس هیچ ماژولی لازم نیست خودش صدایش بزند. با «×» جمع می‌شود و با «؟» دوباره باز می‌شود. */

/* ---------- راهنمای هر تب ---------- */
const GUIDES = {
  dashboard: {
    title: 'داشبورد',
    what: 'نمای کلی استودیو، و ساخت سریع از لینک یوتیوب.',
    steps: [
      'کارت «قدم بعدی» (اگر هست) می‌گوید الان چه کاری از همه مهم‌تر است.',
      'لینک یک ویدیوی انگلیسی یوتیوب در حوزه‌ی کارت را در کادر ترجمه بگذار تا کامل به فارسی ترجمه شود.',
      'تکه‌هایی را که به کارت می‌آید با ماوس انتخاب کن و به بانک ایده بفرست.',
    ],
    tip: 'ترتیب پیشنهادی کار: هسته‌ی برند ← بانک ایده ← ریلز، استوری و کاروسل ← تحلیل.',
  },
  brand: {
    title: 'هسته‌ی برند: پایه‌ی همه‌چیز',
    what: 'پرسش‌نامه‌ای درباره‌ی خودت، مخاطبت، لحنت و خط قرمزهایت. همه‌ی بخش‌های هوشمند استودیو (مشاور، ریلز، کاروسل، تحلیلگر) قبل از هر کاری همین را می‌خوانند. هرچه دقیق‌تر پرش کنی، خروجی‌ها بیشتر شبیه خودت می‌شوند.',
    steps: [
      'دکمه‌ی «سؤال ضروریِ بعدی» را بزن؛ سؤال‌های ضروری مهم‌ترین‌ها هستند.',
      'جواب‌ها خودکار ذخیره می‌شوند؛ لازم نیست همه را یک‌جا پر کنی.',
      'در «صدا و لحن» چند نمونه از متن یا حرف واقعی خودت بگذار. این بیشترین اثر را روی لحن متن‌ها دارد.',
      'در «هویت بصری» لوگو و رنگ‌هایت را بگذار تا استوری و کاروسل با برند خودت ساخته شوند.',
    ],
    tip: 'جواب کوتاه ولی واقعی بهتر از جواب بلند و کلی است. اگر گیر کردی، به «مشاور» بگو کمکت کند.',
  },
  advisor: {
    title: 'مشاور: هم‌فکر برند شخصی‌ات',
    what: 'یک مشاور هوش مصنوعی که هسته‌ی برند، بانک ایده و آمار پیجت را می‌داند. ایده‌ات را بگو تا بسنجد، نقدش کند و پخته‌اش کند.',
    steps: [
      '«گفت‌وگوی تازه» را بزن و ایده یا سؤالت را بنویس، یا با میکروفون بگو.',
      'وقتی به ایده‌ی خوبی رسیدید، کارتی با دکمه‌ی «بفرست به بانک ایده» می‌آید.',
      'تصمیم‌های مهم را با «یادت بمونه» به حافظه‌ی مشاور اضافه کن تا در گفت‌وگوهای بعدی یادش باشد.',
    ],
    tip: 'هسته‌ی برندت هنوز ناقص است؟ بنویس «کمکم کن هسته‌ی برندم رو پر کنم». خواندن جواب‌ها با صدا کلید Gemini می‌خواهد.',
  },
  ideas: {
    title: 'بانک ایده: از ایده‌ی خام تا متن ریلز',
    what: 'هر ایده‌ای که داری اینجا ثبت می‌شود و قدم‌به‌قدم به یک ریلز آماده‌ی ضبط تبدیل می‌شود.',
    steps: [
      'ایده را ثبت کن: متن بنویس، لینک مقاله بگذار، ویس ضبط کن یا فایل (PDF، Word، صوت) بده.',
      'روی ایده بزن و «⚡ ساخت کامل» را بزن: تحلیل، جستجوی وب و ساخت ریلز پشت سر هم انجام می‌شود (چند دقیقه).',
      'در ویرایشگر ریلز بهترین هوک را انتخاب کن؛ هر بخش را دستی ویرایش کن یا با نظرت «بازتولید» بزن.',
      'متن آماده را کپی کن یا با «تله‌پرامپتر» جلوی دوربین بخوان.',
    ],
    tip: 'هر مرحله را جدا هم می‌شود اجرا کرد. در کادر «دستورالعمل» بگو دقیقاً چه می‌خواهی؛ بر بقیه‌ی قواعد اولویت دارد.',
  },
  translations: {
    title: 'ترجمه‌های یوتیوب',
    what: 'ویدیوهای انگلیسی حوزه‌ی کارت را کامل به فارسی بخوان و تکه‌های مفیدش را به ایده تبدیل کن. ترجمه فقط برای خواندن خودت است، نه برای انتشار.',
    steps: [
      'لینک ویدیو را بگذار. ویدیو باید زیرنویس داشته باشد (بیشتر ویدیوها زیرنویس خودکار دارند).',
      'ترجمه بخش‌به‌بخش ساخته می‌شود و از همان بخش اول می‌توانی شروع به خواندن کنی.',
      'تکه‌هایی را که دوست داری با ماوس انتخاب کن و «ثبت همه در بانک ایده» را بزن.',
      'یا پایین صفحه «ساخت ایده از روی این متن» را بزن تا Claude ایده‌ی ریلز پیشنهاد بدهد.',
    ],
    tip: 'ریلز را با حرف و تجربه‌ی خودت بساز؛ اگر از حرف گوینده استفاده می‌کنی، اسمش را بیاور.',
  },
  reels: {
    title: 'استودیو ریلز: از ویدیوی یوتیوب تا متن ضبط',
    what: 'یک لینک یوتیوب بده؛ استودیو چند ایده‌ی ریلز، متن آماده‌ی ضبط و نسخه‌ی خواندنی می‌سازد.',
    steps: [
      'لینک یوتیوب را بگذار و «بساز» را بزن (چند دقیقه طول می‌کشد).',
      'در تب «ریلزها» ایده‌ها را ببین و آن‌هایی را که نمی‌خواهی حذف کن.',
      'در «متن ضبط» متن هر ریلز را کپی کن یا با تله‌پرامپتر بخوان.',
    ],
    tip: 'تله‌پرامپتر: Space پخش و توقف، فلش بالا و پایین سرعت، + و − اندازه، M آینه.',
  },
  video: {
    title: 'تدوین ویدیو',
    what: 'ویدیوی خامی را که ضبط کرده‌ای بده؛ سکوت‌ها و تپق‌ها بریده می‌شوند و زیرنویس فارسی کلمه‌به‌کلمه، کاور و کپشن ساخته می‌شود.',
    steps: [
      '«ویدیوی تازه» را بزن، تیک کارهایی را که می‌خواهی خودکار انجام شود بزن و فایل را انتخاب کن.',
      'در «متن و برش» ببین چه چیزی بریده شده؛ با کلیک روی هر کلمه برش را عوض کن.',
      'زیرنویس، عکس‌ها و افکت‌ها را مرور کن و «رندر» را بزن.',
      'فایل نهایی و کاور را دانلود کن و خودت در اینستاگرام منتشر کن.',
    ],
    tip: 'این بخش کلید Gemini را لازم دارد (برای متن ویدیو). ویدیوی بلند چند دقیقه طول می‌کشد؛ صفحه را ببندی هم کار ادامه پیدا می‌کند.',
  },
  story: {
    title: 'استوری متنی',
    what: 'متنت را بنویس؛ یک تصویر ۱۰۸۰×۱۹۲۰ آماده‌ی استوری با رنگ و لوگوی برندت تحویل بگیر.',
    steps: [
      'متن را در کادر بنویس. خط خالی یعنی پاراگراف تازه؛ پررنگ کردن (⌘B در مک، Ctrl+B در ویندوز) یعنی رنگ تأکیدی.',
      'از ستون کنار یک استایل انتخاب کن، یا رنگ، اندازه و جای لوگو را عوض کن.',
      '«+ استوری بعدی» برای چند استوری پشت‌سرهم.',
      'PNG را دانلود کن و از گوشی منتشر کن.',
    ],
    tip: 'اول لوگو و رنگ‌هایت را در «هسته‌ی برند ← هویت بصری» بگذار تا استایل «برند من» از روی آن‌ها ساخته شود.',
  },
  carousel: {
    title: 'کاروسل و پست',
    what: 'پست چنداسلایدی ۱۰۸۰×۱۳۵۰: اسلاید به اسلاید خودت بساز، یا Claude از روی متن خودت یا یکی از ایده‌های بانک بسازد.',
    steps: [
      '«کاروسل تازه» را بزن: متن یا ایده بده تا Claude اسلایدها را بسازد، یا خالی شروع کن.',
      'هر اسلاید را ویرایش کن، عکس خودت را اضافه کن، یا از Claude بخواه بازنویسی‌اش کند.',
      'رنگ و لوگو را تنظیم کن و «ذخیره به‌عنوان استایل من» را بزن تا کاروسل‌های بعدی هم همین شکل باشند.',
      'اسلایدها را دانلود کن و با کپشن در اینستاگرام منتشر کن.',
    ],
    tip: 'ساختن تصویر با هوش مصنوعی کلید Gemini می‌خواهد. عکس‌های خودت را با توضیح در کتابخانه بگذار تا Claude جای مناسبشان را پیدا کند.',
  },
  analytics: {
    title: 'تحلیل اینستاگرام (اختیاری)',
    what: 'آمار پست‌ها، ریل‌ها، استوری‌ها و مخاطبت، به‌علاوه‌ی تحلیلگری که گزارش و پیشنهاد می‌نویسد.',
    steps: [
      'یک بار پیجت را با توکن Meta وصل کن (راهنما همین پایین است).',
      'هر روز یک بار «همگام‌سازی» بزن؛ اینستاگرام آمار استوری را فقط ۲۴ ساعت نگه می‌دارد.',
      'در تب «تحلیلگر» گزارش بساز و درباره‌اش سؤال بپرس.',
      'ایده‌های پیشنهادی گزارش را با یک کلیک به بانک ایده بفرست.',
    ],
    tip: 'این بخش اختیاری است؛ بقیه‌ی استودیو بدون آن هم کامل کار می‌کند.',
  },
};

const GUIDE_KEY = 'guide-closed';
const guideClosed = () => { try { return JSON.parse(localStorage.getItem(GUIDE_KEY) || '{}'); } catch { return {}; } };
function setGuideClosed(key, closed) {
  const g = guideClosed(); if (closed) g[key] = 1; else delete g[key];
  localStorage.setItem(GUIDE_KEY, JSON.stringify(g));
}

window.guideHTML = guideHTML;
function guideHTML(key) {
  const g = GUIDES[key]; if (!g) return '';
  const closed = guideClosed()[key];
  return `<div class="guide${closed ? ' closed' : ''}" data-guide="${key}">
    <button class="guide-toggle" title="${closed ? 'راهنمای این بخش' : 'بستن راهنما'}">${closed ? '؟ راهنما' : '×'}</button>
    <div class="guide-body">
      <b class="guide-title">${esc(g.title)}</b>
      <p class="guide-what">${esc(g.what)}</p>
      <ol>${g.steps.map(s => `<li>${esc(s)}</li>`).join('')}</ol>
      ${g.tip ? `<p class="guide-tip">نکته: ${esc(g.tip)}</p>` : ''}
    </div>
  </div>`;
}

document.addEventListener('click', e => {
  const t = e.target.closest('.guide-toggle'); if (!t) return;
  const box = t.closest('.guide'); const key = box.dataset.guide;
  const closed = !box.classList.contains('closed');
  setGuideClosed(key, closed);
  box.outerHTML = guideHTML(key);
});

// هر بار که یک تب صفحه را می‌کشد، راهنمای همان تب زیر عنوانش می‌نشیند.
(function guideObserver() {
  const page = document.getElementById('page');
  const place = () => {
    const key = S.section; if (!GUIDES[key]) return;
    const head = page.querySelector(':scope > .page-head, :scope > * > .page-head');
    if (!head || page.querySelector('.guide')) return;
    head.insertAdjacentHTML('afterend', guideHTML(key));
  };
  new MutationObserver(place).observe(page, { childList: true });
})();

/* ---------- نام صاحب استودیو در هدر ---------- */
window.paintBrandName = function () {
  const h = document.querySelector('.top .brand');
  if (!h) return;
  let tag = h.querySelector('.owner');
  if (!tag) { tag = document.createElement('span'); tag.className = 'owner'; h.appendChild(tag); }
  const p = S.profile || {};
  tag.innerHTML = p.handle ? `<bdi dir="ltr">@${esc(p.handle)}</bdi>` : esc(p.name || '');
};

/* ---------- قدم‌ها ---------- */
const STEPS_META = [
  ['tools', 'ابزارها', 'Claude Code نصب است و وارد حسابت شده‌ای.'],
  ['profile', 'خودت را معرفی کن', 'اسم، آیدی اینستاگرام و کارت؛ همه‌ی بخش‌ها با همین تو را می‌شناسند.'],
  ['gemini', 'کلید Gemini (رایگان)', 'برای ویس، صدای مشاور، ساختن تصویر و متن ویدیو.'],
  ['brand', 'هسته‌ی برند', 'دست‌کم ۱۲ سؤال ضروری را جواب بده؛ بقیه را کم‌کم.'],
  ['idea', 'اولین ایده', 'یک ایده در بانک ایده ثبت کن: متن، لینک، ویس یا فایل.'],
  ['reel', 'اولین ریلز', 'روی ایده بزن و «⚡ ساخت کامل» را بزن.'],
  ['story', 'اولین استوری', 'یک استوری متنی بساز و دانلودش کن.'],
];
const SETUP = { d: null };
async function loadSetup() { SETUP.d = await api('/api/setup'); return SETUP.d; }
window.markStep = step => post('/api/setup/step', { step });

const tick = ok => ok ? '<span class="st-ok">✓</span>' : '<span class="st-no">○</span>';

function toolsHTML(t) {
  const c = t.claude || {};
  const row = (ok, name, note) => `<tr><td>${tick(ok)}</td><td>${name}</td><td class="cap-hint" style="margin:0">${note}</td></tr>`;
  return `<table class="tools-table"><tbody>
    ${row(c.installed, 'Claude Code', c.installed ? esc(c.version || '') : 'نصب نیست. اسکریپت نصب را اجرا کن (README).')}
    ${row(c.loggedIn, 'ورود به حساب Claude', c.loggedIn ? `اشتراک: ${esc(c.plan || '—')}` : 'در ترمینال بنویس <code>claude</code> و وارد حسابت شو (اشتراک Pro یا Max).')}
    ${row(t.ytdlp && t.ytdlp.ok, 'yt-dlp (زیرنویس یوتیوب)', t.ytdlp && t.ytdlp.ok ? esc(t.ytdlp.version || '') : 'برای ترجمه و استودیو ریلز لازم است.')}
    ${row(t.ffmpeg && t.ffmpeg.ok, 'ffmpeg (صدا و ویدیو)', t.ffmpeg && t.ffmpeg.ok ? 'نصب است' : 'برای ویس و تدوین ویدیو لازم است.')}
    ${row(t.node && t.node.ok, 'Node.js', t.node && t.node.ok ? esc(t.node.version || '') : 'برای تدوین ویدیو لازم است.')}
    ${row(t.video && t.video.ok, 'تدوین ویدیو (اختیاری)', t.video && t.video.mac ? (t.video.ok ? 'آماده' : (t.video.chrome ? '' : 'Google Chrome لازم است. ') + 'اسکریپت «نصب تدوین ویدیو» را اجرا کن (README).') : 'فعلاً فقط روی مک.')}
  </tbody></table>`;
}

function profileFormHTML(p) {
  return `<div class="form-grid">
    <label>اسمت <input class="cap-input" id="pfName" value="${esc(p.name || '')}" placeholder="مثال: مریم احمدی"></label>
    <label>آیدی اینستاگرام <input class="cap-input" id="pfHandle" dir="ltr" value="${esc(p.handle || '')}" placeholder="maryam.ahmadi"></label>
    <label class="wide">کارت در یک خط <input class="cap-input" id="pfWork" value="${esc(p.work || '')}" placeholder="مثال: مشاور منابع انسانی که به کارجوها کمک می‌کند رزومه‌ی بهتری بنویسند"></label>
  </div>
  <div class="rowbar" style="margin:12px 0 0"><button class="btn primary" id="pfSave">ذخیره</button></div>`;
}
function wireProfileForm(after) {
  $('#pfSave').onclick = async () => {
    const body = { name: $('#pfName').value, handle: $('#pfHandle').value, work: $('#pfWork').value };
    if (!body.name.trim()) return toast('اسمت را بنویس');
    const r = await post('/api/settings/profile', body);
    if (!r.ok) return toast(r.data.error || 'ذخیره نشد');
    S.profile = r.data.profile || body; paintBrandName(); toast('✓ ذخیره شد'); after && after();
  };
}

function geminiFormHTML(set, hint) {
  return `<p class="cap-hint" style="margin-top:0">کلید رایگان را از <a href="https://aistudio.google.com/apikey" target="_blank" rel="noopener">aistudio.google.com/apikey</a> بگیر: با حساب گوگل وارد شو، «Create API key» را بزن و کلید را کپی کن.
    ${set ? `کلید فعلی: <bdi dir="ltr">${esc(hint)}</bdi>` : ''}</p>
  <div class="rowbar" style="margin:10px 0 0">
    <input class="cap-input" id="gmKey" dir="ltr" placeholder="${set ? 'کلید تازه (برای جایگزینی)' : 'AQ.… یا AIza…'}" autocomplete="off" style="flex:1">
    <button class="btn primary" id="gmSave">${set ? 'جایگزینی' : 'ذخیره و آزمایش'}</button>
    ${set ? '<button class="btn danger" id="gmDel">پاک کردن</button>' : ''}
  </div>`;
}
function wireGeminiForm(after) {
  $('#gmSave').onclick = async () => {
    const key = $('#gmKey').value.trim(); if (!key) return toast('کلید را بچسبان');
    $('#gmSave').disabled = true;
    const r = await post('/api/settings/gemini', { key });
    $('#gmSave').disabled = false;
    if (!r.ok) return toast(r.data.error || 'ذخیره نشد');
    toast('✓ کلید کار می‌کند و ذخیره شد'); after && after();
  };
  const del = $('#gmDel');
  if (del) del.onclick = async () => {
    if (!confirm('کلید Gemini از این کامپیوتر پاک شود؟')) return;
    await post('/api/settings/gemini', { key: '' }); after && after();
  };
}

async function testClaude(btn, out) {
  btn.disabled = true; out.textContent = 'در حال فرستادن یک پیام کوتاه به Claude…';
  const r = await post('/api/settings/test-claude', {});
  btn.disabled = false;
  out.innerHTML = r.ok ? `✓ Claude جواب داد: «${esc(r.data.reply)}»` : `✕ ${esc(r.data.error || 'جواب نداد')}`;
}

/* ---------- صفحه‌ی شروع ---------- */
window.viewStart = async function viewStart() {
  $('#page').innerHTML = `<div class="page-head"><h2>شروع</h2><p>در حال بررسی…</p></div>`;
  const d = await loadSetup(); if (!d) return;
  const st = d.steps, doneN = Object.values(st).filter(Boolean).length, total = STEPS_META.length;
  const current = (STEPS_META.find(([k]) => !st[k]) || [null])[0];
  const name = d.profile.name;
  $('#page').innerHTML = `
    <div class="page-head"><h2>${name ? `${esc(name)}، خوش آمدی` : 'به استودیوی تولید محتوای خودت خوش آمدی'}</h2>
      <p>این استودیو روی کامپیوتر خودت اجرا می‌شود و همه‌ی داده‌هایت همین‌جا می‌ماند. مسیر کار: <b>هسته‌ی برند</b> ← <b>ایده</b> ← <b>ریلز، استوری و کاروسل</b> ← انتشار دستی ← <b>تحلیل</b>.</p></div>
    <div class="start-progress"><div class="bar"><i style="width:${Math.round(doneN / total * 100)}%"></i></div>
      <span>${faNum(doneN)} از ${faNum(total)} قدم</span></div>
    <div class="start-steps">
      ${STEPS_META.map(([k, title, desc], i) => `
        <section class="start-step${st[k] ? ' done' : ''}${k === current ? ' current' : ''}" data-step="${k}">
          <div class="start-num">${st[k] ? '✓' : faNum(i + 1)}</div>
          <div class="start-main">
            <h3>${title}${k === 'gemini' ? ' <span class="opt">پیشنهادی</span>' : ''}</h3>
            <p class="cap-hint" style="margin:2px 0 0">${desc}</p>
            <div class="start-body" id="sb-${k}"></div>
          </div>
        </section>`).join('')}
    </div>
    <div class="panel" style="margin-top:22px">
      <h3>روال پیشنهادی هر هفته</h3>
      <ol class="start-routine">
        <li><b>هر روز:</b> هر ایده‌ای که به ذهنت رسید، همان لحظه در «بانک ایده» ثبت کن (متن یا ویس).</li>
        <li><b>اول هفته:</b> با «مشاور» ایده‌ها را مرور کن و ۳ تا را برای این هفته انتخاب کن.</li>
        <li><b>روز تولید:</b> برای هر ایده «⚡ ساخت کامل»، هوک را انتخاب کن، با تله‌پرامپتر ضبط کن و در «تدوین ویدیو» زیرنویس بگذار.</li>
        <li><b>بین ریلزها:</b> یک کاروسل و چند استوری متنی از همان ایده‌ها بساز.</li>
        <li><b>آخر هفته:</b> اگر اینستاگرامت را وصل کرده‌ای، گزارش تحلیلگر را بخوان و درس‌هایش را به «هسته‌ی برند ← درس‌های داده» اضافه کن.</li>
      </ol>
    </div>
    <div class="rowbar" style="margin-top:16px">
      <button class="btn" id="guidesReset">نمایش دوباره‌ی راهنمای همه‌ی تب‌ها</button>
      <span class="grow"></span>
      <button class="btn" data-go="dashboard">رفتن به داشبورد</button>
    </div>`;
  fillStartBodies(d);
  $('#guidesReset').onclick = () => { localStorage.removeItem(GUIDE_KEY); toast('✓ راهنماها دوباره نشان داده می‌شوند'); };
};

function fillStartBodies(d) {
  const st = d.steps, b = k => $('#sb-' + k);
  b('tools').innerHTML = toolsHTML(d.tools) + `<div class="rowbar" style="margin:10px 0 0">
      <button class="btn" id="tcBtn">آزمایش Claude</button><button class="btn" id="tcRe">بررسی دوباره</button></div>
      <p class="cap-hint" id="tcOut"></p>`;
  $('#tcBtn').onclick = () => testClaude($('#tcBtn'), $('#tcOut'));
  $('#tcRe').onclick = () => viewStart();

  b('profile').innerHTML = profileFormHTML(d.profile);
  wireProfileForm(() => viewStart());

  b('gemini').innerHTML = geminiFormHTML(st.gemini, '');
  wireGeminiForm(() => viewStart());

  const pct = d.brand.total ? Math.round(d.brand.done / d.brand.total * 100) : 0;
  b('brand').innerHTML = `<div class="start-progress small"><div class="bar"><i style="width:${pct}%"></i></div>
      <span>${faNum(d.brand.done)} از ${faNum(d.brand.total)} سؤال ضروری</span></div>
    <div class="rowbar" style="margin:8px 0 0"><button class="btn primary" data-go="brand">برو به هسته‌ی برند</button>
      <button class="btn" data-go="advisor">از مشاور کمک بگیر</button></div>`;
  b('idea').innerHTML = `<div class="rowbar" style="margin:8px 0 0"><button class="btn${st.idea ? '' : ' primary'}" data-go="ideas">برو به بانک ایده</button>
    <span class="cap-hint" style="margin:0">${d.counts.ideas ? `${faNum(d.counts.ideas)} ایده ثبت شده` : ''}</span></div>`;
  b('reel').innerHTML = `<div class="rowbar" style="margin:8px 0 0"><button class="btn${st.reel ? '' : ' primary'}" data-go="ideas">برو به بانک ایده</button>
    <span class="cap-hint" style="margin:0">${d.counts.reels ? `${faNum(d.counts.reels)} ریلز ساخته شده` : ''}</span></div>`;
  b('story').innerHTML = `<div class="rowbar" style="margin:8px 0 0"><button class="btn${st.story ? '' : ' primary'}" data-go="story">برو به استوری</button></div>`;
  // قدم‌های تمام‌شده جمع می‌شوند تا صفحه شلوغ نشود؛ کلیک روی عنوان بازشان می‌کند
  $$('.start-step.done').forEach(s => {
    s.classList.add('folded');
    s.querySelector('h3').onclick = () => s.classList.toggle('folded');
  });
}

/* ---------- قدم بعدی در داشبورد ---------- */
window.mountNextStep = async function (el) {
  const d = SETUP.d || await loadSetup(); if (!d || !el) return;
  const i = STEPS_META.findIndex(([k]) => !d.steps[k]);
  if (i < 0) return;
  const [k, title, desc] = STEPS_META[i];
  const target = { tools: 'start', profile: 'start', gemini: 'start', brand: 'brand', idea: 'ideas', reel: 'ideas', story: 'story' }[k];
  el.innerHTML = `<div class="panel next-step"><div><b>قدم بعدی (${faNum(i + 1)} از ${faNum(STEPS_META.length)}): ${title}</b>
      <p class="cap-hint" style="margin:2px 0 0">${desc}</p></div>
    <button class="btn primary" data-go="${target}">بزن بریم</button></div>`;
  SETUP.d = null;     // دفعه‌ی بعد تازه خوانده شود
};

/* ---------- تنظیمات ---------- */
// Astra (Codex) فقط برای کارهایی که متن خالص برمی‌گردانند، و فقط وقتی Codex وارد حساب است (یا همین حالا انتخاب شده)
function modelChoices(m, step) {
  const st = m.codex_status || {};
  const withCodex = (m.codex_steps || []).includes(step) && (st.logged_in || (m.codex || {})[m.models[step]]);
  return withCodex ? { ...m.choices, ...m.codex } : m.choices;
}
function codexHTML(m) {
  const st = m.codex_status || {};
  const tasks = (m.codex_steps || []).map(k => `«${esc(m.steps[k])}»`).join(' و ');
  return `<h3 style="margin-top:18px">GPT-6 Astra (اختیاری)</h3>
    <p class="cap-hint" style="margin-top:0">اگر اشتراک ChatGPT و Codex را روی همین کامپیوتر داری، ${tasks} را می‌شود با Astra نوشت؛
    از سهمیه‌ی ChatGPT کم می‌کند، نه Claude. Astra به فایل‌های استودیو دسترسی ندارد و هسته‌ی برند و فایل‌های ایده داخل پرامپتش می‌رود.
    یوتیوب ← ریلز همیشه با Claude است.</p>
    <p class="cap-hint">${st.logged_in ? '✓ ' : ''}${esc(st.note || '')}</p>
    ${st.installed ? `<div class="rowbar" style="margin:6px 0 0"><button class="btn" id="cxBtn">آزمایش Astra</button></div>
    <p class="cap-hint" id="cxOut"></p>` : ''}`;
}

window.viewSettings = async function viewSettings() {
  $('#page').innerHTML = `<div class="page-head"><h2>تنظیمات</h2><p>در حال بررسی…</p></div>`;
  const [s, setup, models] = await Promise.all([api('/api/settings'), loadSetup(), api('/api/models')]);
  if (!s || !setup) return;
  const ig = await api('/api/insta/status') || {};
  $('#page').innerHTML = `
    <div class="page-head"><h2>تنظیمات</h2><p>همه‌ی تنظیم‌ها و کلیدها فقط روی همین کامپیوتر ذخیره می‌شوند.</p></div>
    <section class="panel set-sec"><h3>پروفایل</h3>${profileFormHTML(s.profile)}</section>
    <section class="panel set-sec"><h3>Claude</h3>
      ${toolsHTML(setup.tools)}
      <div class="rowbar" style="margin:10px 0 0"><button class="btn" id="tcBtn">آزمایش Claude</button></div>
      <p class="cap-hint" id="tcOut"></p>
      <h3 style="margin-top:18px">مدل هر کار</h3>
      <p class="cap-hint" style="margin-top:0">Sonnet سریع‌تر است و سهمیه‌ی اشتراکت را دیرتر تمام می‌کند. Opus دقیق‌تر است ولی سهمیه را زودتر تمام می‌کند؛ روی اشتراک Pro برای کارهای مهم نگهش دار.</p>
      <div class="rowbar"><button class="btn" data-all="claude-sonnet-5-5">همه Sonnet</button><button class="btn" data-all="claude-opus-5-5">همه Opus</button></div>
      <div class="models-grid">${Object.entries(models.steps).map(([k, l]) => `<label class="model-row"><span>${esc(l)}</span>
        <select data-model="${k}">${Object.entries(modelChoices(models, k)).map(([id, name]) =>
          `<option value="${id}" ${models.models[k] === id ? 'selected' : ''}>${esc(name)}</option>`).join('')}</select></label>`).join('')}</div>
      ${codexHTML(models)}
    </section>
    <section class="panel set-sec"><h3>کلید Gemini</h3>${geminiFormHTML(s.gemini.set, s.gemini.hint)}</section>
    <section class="panel set-sec"><h3>اینستاگرام</h3>
      <p>${ig.connected ? `وصل است${ig.username ? `: <bdi dir="ltr">@${esc(ig.username)}</bdi>` : ''}` : 'وصل نیست.'}
        <a href="?s=analytics" data-go="analytics">${ig.connected ? 'برو به تحلیل اینستاگرام' : 'اتصال در تب «تحلیل اینستاگرام»'}</a></p>
    </section>
    <section class="panel set-sec"><h3>داده‌های تو</h3>
      <p class="cap-hint" style="margin-top:0">همه‌چیز در پوشه‌ی استودیو است: <code>brand/</code> (هسته‌ی برند و لوگو)، <code>data/</code> (ایده‌ها، ریلزها، گفت‌وگوها، ویدیوها، آمار) و <code>modules/reels/output/</code> (ترجمه‌ها).
      برای پشتیبان‌گیری همین سه پوشه را جایی کپی کن. آپدیت استودیو (README، بخش «به‌روزرسانی») به این پوشه‌ها دست نمی‌زند.</p>
    </section>`;
  wireProfileForm();
  wireGeminiForm(() => viewSettings());
  $('#tcBtn').onclick = () => testClaude($('#tcBtn'), $('#tcOut'));
  $$('[data-model]').forEach(sel => sel.onchange = async () => {
    const r = await post('/api/models', { step: sel.dataset.model, model: sel.value });
    toast(r.ok ? '✓ مدل عوض شد' : (r.data.error || 'ذخیره نشد'));
  });
  const cx = $('#cxBtn');
  if (cx) cx.onclick = async () => {
    cx.disabled = true; $('#cxOut').textContent = 'در حال آزمایش… (چند ثانیه)';
    const r = await post('/api/models/codex-test', {});
    cx.disabled = false;
    $('#cxOut').textContent = r.data && r.data.ok ? `✓ Astra جواب داد: ${r.data.reply}` : `✗ ${(r.data && r.data.error) || 'جواب نداد'}`;
    if (r.data && r.data.ok && !(models.codex_status || {}).logged_in) viewSettings();
  };
  $$('[data-all]').forEach(b => b.onclick = async () => {
    const r = await post('/api/models', { step: '*', model: b.dataset.all });
    if (r.ok) { toast('✓ عوض شد'); viewSettings(); }
  });
};

/* ---------- تدوین ویدیو روی ویندوز ---------- */
window.viewVideoMacOnly = function () {
  $('#page').innerHTML = `
    <div class="page-head"><h2>تدوین ویدیو</h2><p>این بخش فعلاً فقط روی مک کار می‌کند.</p></div>
    <div class="empty">تدوین ویدیو (برش خودکار، زیرنویس فارسی و کاور) به ابزارهای مخصوص مک وابسته است و نسخه‌ی ویندوزش هنوز آماده نیست.
      تا آن موقع می‌توانی ویدیو را با CapCut یا هر ویرایشگر دیگری تدوین کنی و متن ضبطت را از «بانک ایده» برداری.</div>`;
};
