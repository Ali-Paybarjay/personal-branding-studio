/* ================= تحلیل اینستاگرام =================
   استودیو با توکن خود کاربر مستقیم از Instagram API می‌خواند (فقط خواندنی).
   همه‌ی درخواست‌ها از سرور لوکال می‌گذرند (/api/insta/*) و توکن هرگز به مرورگر نمی‌رسد. */

const IGS = {
  igTab: 'overview', dataset: null, syncedAt: null,
  postType: 'all', postSort: 'date', report: null, reports: [],
};
const IG_PILLARS = typeof PILLARS !== 'undefined' ? PILLARS : ['آموزشی', 'تجربه و داستان', 'دیدگاه و تحلیل', 'پشت‌صحنه'];
const TYPE_FA = { REELS: 'ریل', POST: 'پست', CAROUSEL: 'کاروسل' };

/* ---------- ابزار ---------- */
async function igGet(p) {
  try {
    const r = await fetch(p);
    const data = await r.json().catch(() => ({}));
    return { ok: r.ok, status: r.status, data };
  } catch { return { ok: false, status: 0, data: { error: 'سرور استودیو جواب نداد.' } }; }
}
async function igPost(p, body) {
  try {
    const r = await fetch(p, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}) });
    return { ok: r.ok, status: r.status, data: await r.json().catch(() => ({})) };
  } catch { return { ok: false, status: 0, data: { error: 'سرور استودیو جواب نداد.' } }; }
}
const fnum = n => (n == null || Number.isNaN(n)) ? '—' : Number(n).toLocaleString('fa-IR');
const fpct = n => n == null ? '—' : `${Number(n).toLocaleString('fa-IR', { maximumFractionDigits: 1 })}٪`;
const fx = n => n == null ? '—' : `×${Number(n).toLocaleString('fa-IR', { maximumFractionDigits: 1 })}`;
function igAgo(iso) {
  if (!iso) return '—';
  const s = (Date.now() - Date.parse(iso)) / 1000;
  if (s < 60) return 'همین الان';
  if (s < 3600) return `${faNum(Math.floor(s / 60))} دقیقه پیش`;
  if (s < 86400) return `${faNum(Math.floor(s / 3600))} ساعت پیش`;
  return `${faNum(Math.floor(s / 86400))} روز پیش`;
}
const uname = u => `<bdi dir="ltr">@${esc(u)}</bdi>`;

function tabsHTML(id, tabs, on) {
  return `<div class="tabs-wrap"><nav class="tabs" id="${id}" style="padding:0">
    ${tabs.map(([k, l]) => `<button data-igtab="${k}" class="${on === k ? 'on' : ''}">${l}</button>`).join('')}
  </nav></div>`;
}
function wireTabs(id, onPick) {
  $$(`#${id} button`).forEach(b => b.onclick = () => {
    $$(`#${id} button`).forEach(x => x.classList.toggle('on', x === b));
    onPick(b.dataset.igtab);
  });
}

/* job polling, shared by every background task */
const IGPOLL = {};
function igPoll(kind, box, onDone) {
  clearInterval(IGPOLL[kind]);
  const tick = async () => {
    const r = await igGet('/api/jobs'); if (!r.ok) return;
    const j = r.data[kind]; if (!j) return;
    if (box && document.body.contains(box)) {
      box.hidden = j.state === 'idle';
      box.className = 'build-status' + (j.state === 'error' ? ' err' : '');
      const head = j.state === 'running' ? `<span class="spin"></span> ${esc(j.step || 'در حال اجرا')}…`
        : j.state === 'done' ? '✓ تمام شد' : '✕ ' + esc(j.error || 'خطا');
      const lg = (j.log || []).length ? `<div class="build-log">${j.log.map(l => `<div>${esc(l)}</div>`).join('')}</div>` : '';
      box.innerHTML = `<div class="build-step">${head}</div>${lg}`;
    }
    if (j.state !== 'running') { clearInterval(IGPOLL[kind]); if (j.state === 'done' && onDone) onDone(j); }
  };
  IGPOLL[kind] = setInterval(tick, 2500); tick();
}

/* hover tooltip for every [data-tip] mark */
(function igTooltip() {
  const tip = document.createElement('div'); tip.className = 'ig-tip'; tip.hidden = true;
  document.body.appendChild(tip);
  document.addEventListener('mouseover', e => {
    const t = e.target.closest('[data-tip]'); if (!t) return;
    tip.innerHTML = t.dataset.tip.split('|').map(esc).join('<br>'); tip.hidden = false;
  });
  document.addEventListener('mousemove', e => {
    if (tip.hidden) return;
    tip.style.left = Math.min(window.innerWidth - tip.offsetWidth - 8, e.clientX + 14) + 'px';
    tip.style.top = (e.clientY + 16) + 'px';
  });
  document.addEventListener('mouseout', e => { if (e.target.closest('[data-tip]')) tip.hidden = true; });
})();

/* ================= تحلیل اینستاگرام ================= */
const IG_TABS = [['overview', 'نمای کلی'], ['posts', 'پست‌ها و ریل‌ها'], ['stories', 'استوری‌ها'],
  ['audience', 'مخاطب'], ['timing', 'زمان انتشار'], ['analyst', 'تحلیلگر']];

async function viewInsta() {
  const st = await igGet('/api/insta/status');
  const conn = st.ok ? st.data : { connected: false };
  if (!conn.connected) return igConnectView();
  $('#page').innerHTML = `
    <div class="page-head"><h2>تحلیل اینستاگرام</h2>
      <p>آمار پیج ${conn.username ? uname(conn.username) : ''} مستقیم از اینستاگرام خوانده و روی همین کامپیوتر ذخیره می‌شود. اینستاگرام آمار استوری را فقط ۲۴ ساعت نگه می‌دارد، پس هر روز یک بار «همگام‌سازی» بزن تا تاریخچه‌ات کامل شود.</p></div>
    <div class="rowbar">
      <button class="btn primary" id="igSync">همگام‌سازی</button>
      <span class="ig-dim" id="igSyncedAt"></span>
      <span class="grow"></span>
      <button class="btn" id="igReplace" title="مثلاً وقتی توکن منقضی شده">تعویض توکن</button>
      <button class="btn" id="igDisconnect" title="توکن از این کامپیوتر پاک می‌شود؛ داده‌های ذخیره‌شده می‌مانند">قطع اتصال</button>
    </div>
    <div id="igJob" class="build-status" hidden></div>
    ${tabsHTML('igTabs', IG_TABS, IGS.igTab)}
    <div id="igView" style="padding-top:20px"></div>`;
  wireTabs('igTabs', k => { IGS.igTab = k; renderInstaTab(); });
  $('#igSync').onclick = startSync;
  $('#igReplace').onclick = () => igConnectView({ replace: true });
  $('#igDisconnect').onclick = async () => {
    if (!confirm('اتصال اینستاگرام قطع شود؟ آمارهای ذخیره‌شده پاک نمی‌شوند.')) return;
    await igPost('/api/insta/disconnect'); viewInsta();
  };
  await loadDataset();
  const stale = !IGS.syncedAt || Date.now() / 1000 - IGS.syncedAt > 6 * 3600;
  const j = await igGet('/api/jobs');
  if (j.ok && j.data.sync && j.data.sync.state === 'running') igPoll('sync', $('#igJob'), afterSync);
  else if (stale) startSync();
  renderInstaTab();
}

/* اتصال: کاربر یک توکن بلندمدت از داشبورد Meta می‌سازد و اینجا می‌گذارد. همین راهنما در docs/instagram-connect.md هم هست؛
   هر تغییری این‌جا، آن‌جا هم. هر قدم یک کارت با تیک «انجام دادم» است (localStorage)؛ قدم انجام‌شده جمع می‌شود. */
const IGC_KEY = 'ig-connect-done';
const igcDone = () => { try { return new Set(JSON.parse(localStorage.getItem(IGC_KEY) || '[]')); } catch { return new Set(); } };
const igUi = s => `<span class="ui" dir="ltr">${s}</span>`;
const igPath = (...xs) => xs.map(igUi).join('<span class="ui-sep">←</span>');
const igExt = (href, label) => `<a class="ext" dir="ltr" href="${href}" target="_blank" rel="noopener">${label}</a>`;
const IGC_STEPS = [
  ['dev', 'ساختن حساب توسعه‌دهنده‌ی Meta', `
    <p>به ${igExt('https://developers.facebook.com/', 'developers.facebook.com')} برو و بالای صفحه ${igUi('Log in')} را بزن و با اکانت فیسبوکت وارد شو.</p>
    <p>اگر بار اول است، ${igUi('Get Started')} را بزن و ثبت‌نام را تا آخر برو: شرایط را قبول کن، شماره‌ی تلفن و ایمیلت را تأیید کن، و اگر نقشت را پرسید، ${igUi('Developer')} را انتخاب کن.</p>
    <p class="igc-note">اگر قبلاً حساب توسعه‌دهنده ساخته‌ای، این قدم را رد کن.</p>`],
  ['app', 'ساختن اپ', `
    <p>به ${igExt('https://developers.facebook.com/apps/creation/', 'developers.facebook.com/apps/creation')} برو. چند صفحه پشت سر هم باز می‌شود؛ بعد از هر صفحه ${igUi('Next')} را بزن:</p>
    <ol class="igc-sub">
      <li>${igUi('App details')}: یک اسم برای اپ بنویس، مثلاً «Maryam Studio»، و ایمیلت را وارد کن. کلمه‌های Instagram، IG، Facebook و Meta نباید در اسم باشند، وگرنه Meta قبولش نمی‌کند. این اسم را کسی جز خودت نمی‌بیند.</li>
      <li>${igUi('Use cases')}: گزینه‌ی ${igUi('Manage messaging &amp; content on Instagram')} را انتخاب کن. اگر در فهرست ندیدی، صفحه را پایین بکش.</li>
      <li>${igUi('Business')}: اگر business portfolio داری، انتخابش کن. اگر نداری، همین‌جا یکی با اسم خودت یا برندت بساز. لازم نیست تأیید شده باشد.</li>
      <li>در صفحه‌های ${igUi('Requirements')} و ${igUi('Overview')} هم جلو برو و آخر ${igUi('Go to dashboard')} را بزن.</li>
    </ol>
    <p class="igc-note">ممکن است Meta وسط کار دوباره رمز فیسبوکت را بخواهد؛ عادی است.</p>`],
  ['setup', 'باز کردن تنظیمات اینستاگرامِ اپ', `
    <p>در داشبورد اپ این مسیر را برو:</p>
    <p>${igPath('Use cases', 'Customize')} (دکمه‌ی کنار ${igUi('Manage messaging &amp; content on Instagram')})${'<span class="ui-sep">←</span>'}${igUi('API setup with Instagram login')}</p>
    <p class="igc-note">قدم‌های ۴ تا ۷ همه در همین صفحه‌اند. این تب مرورگر را باز نگه دار.</p>`],
  ['perms', 'اضافه کردن دسترسی‌ها', `
    <p>اول ${igUi('Add all required permissions')} را بزن. بعد چک کن این دو دسترسی در فهرست باشند؛ برای استودیو همین دو تا کافی است:</p>
    <table class="igc-perms"><tbody>
      <tr><td><code dir="ltr">instagram_business_basic</code></td><td>اسم پیج، تعداد فالوور و فهرست پست‌ها</td></tr>
      <tr><td><code dir="ltr">instagram_business_manage_insights</code></td><td>آمار پست‌ها، ریل‌ها، استوری‌ها و مخاطب</td></tr>
    </tbody></table>
    <p>اگر یکی نبود، ${igUi('Go to permissions and features')} را بزن، آن دسترسی را پیدا کن و جلویش ${igUi('Add')} را بزن.</p>
    <p class="igc-warn"><b>این قدم را پیش از ساختن توکن تمام کن.</b> توکن فقط دسترسی‌هایی را می‌گیرد که لحظه‌ی ساختنش فعال بوده‌اند. اگر بعداً دسترسی‌ای اضافه کنی، باید توکن را دوباره بسازی.</p>
    <p class="igc-note">اگر Meta دسترسی‌های دیگری مثل پیام و کامنت را هم خودش اضافه کرد، اشکالی ندارد؛ استودیو از آن‌ها استفاده نمی‌کند. دسترسی‌هایی که business در اسمشان نیست (مثل <code dir="ltr">instagram_basic</code>) یا با <code dir="ltr">pages_</code> و <code dir="ltr">ads_</code> شروع می‌شوند مال روش دیگری از اتصال‌اند؛ اضافه‌شان نکن.</p>`],
  ['tester', 'اضافه کردن پیجت به‌عنوان «تستر»', `
    <p>در همان صفحه، در بخش ${igUi('Generate access tokens')} روی ${igUi('Add account')} بزن.</p>
    <p>Meta اول می‌خواهد پیجت «تستر» این اپ شود. در صفحه‌ای که باز می‌شود ${igUi('Instagram Tester')} را انتخاب کن، یوزرنیم اینستاگرامت را <b>بدون @</b> بنویس و ${igUi('Add')} را بزن.</p>
    <p class="igc-note">با این کار یک دعوت برای پیجت فرستاده می‌شود. تا دعوت را قبول نکنی (قدم بعد)، نمی‌شود توکن ساخت.</p>`],
  ['accept', 'قبول کردن دعوت در اینستاگرام', `
    <p>در یک تب تازه‌ی مرورگر کامپیوتر ${igExt('https://www.instagram.com/accounts/manage_access/', 'instagram.com/accounts/manage_access')} را باز کن و با <b>همان پیجی</b> وارد شو که در قدم قبل نوشتی.</p>
    <p>تب ${igUi('Tester Invites')} را باز کن و کنار اسم اپت ${igUi('Accept')} را بزن.</p>
    <p class="igc-note">اگر دعوت هنوز نیامده، یکی دو دقیقه صبر کن و صفحه را refresh کن. این بخش در اپ گوشی معمولاً نیست؛ از مرورگر کامپیوتر برو. اگر چند پیج داری، مطمئن شو با پیج درست وارد شده‌ای.</p>`],
  ['token', 'ساختن توکن', `
    <p>به تب ${igUi('API setup with Instagram login')} برگرد و صفحه را refresh کن. حالا یوزرنیمت زیر ${igUi('Generate access tokens')} دیده می‌شود.</p>
    <ol class="igc-sub">
      <li>کنار یوزرنیمت ${igUi('Generate token')} را بزن.</li>
      <li>پنجره‌ی ورود اینستاگرام باز می‌شود. وارد شو و دسترسی‌ها را قبول کن. اگر پنجره باز نشد، مرورگر جلوی پنجره‌ی بازشو (pop-up) را گرفته؛ برای همین سایت اجازه بده و دوباره بزن.</li>
      <li>توکن نشان داده می‌شود: یک رشته‌ی خیلی طولانی از حرف و عدد که معمولاً با <code dir="ltr">IG</code> شروع می‌شود. اگر تیک ${igUi('I understand')} خواست، بزنش. توکن را <b>کامل</b> کپی کن.</li>
    </ol>
    <p class="igc-note">اگر پنجره را بستی و توکن را کپی نکرده بودی، دوباره ${igUi('Generate token')} را بزن؛ توکن تازه ساخته می‌شود.</p>`],
  ['paste', 'وارد کردن توکن در استودیو', `
    <p>توکن را این‌جا بچسبان و «اتصال» را بزن. اگر یوزرنیمت نشان داده شد، اتصال درست است.</p>
    <div class="rowbar" style="margin:10px 0 0">
      <input id="igToken" class="cap-input" dir="ltr" placeholder="IGAA…" autocomplete="off" style="flex:1">
      <button class="btn primary" id="igConnect">اتصال</button>
    </div>
    <div id="igConnectMsg" class="cap-hint"></div>
    <p class="igc-note">بعد از اتصال، اولین همگام‌سازی خودش شروع می‌شود و بسته به تعداد پست‌ها چند دقیقه طول می‌کشد. اینستاگرام در هر ساعت تعداد محدودی درخواست قبول می‌کند؛ اگر پیام «سقف درخواست» آمد، یک ساعت بعد دوباره «همگام‌سازی» بزن تا کامل شود.</p>`],
];

function igConnectView(opts = {}) {
  const done = igcDone();
  const n = IGC_STEPS.filter(([k]) => done.has(k)).length;
  $('#page').innerHTML = `
    <div class="page-head"><h2>تحلیل اینستاگرام</h2>
      <p>پیج اینستاگرامت را وصل کن تا آمار پست‌ها، ریل‌ها، استوری‌ها و مخاطب‌هایت این‌جا جمع شود و تحلیلگر برایت گزارش بنویسد.</p></div>
    ${opts.replace ? '<div class="rowbar"><button class="btn" id="igBack">→ برگشت به آمار</button></div>' : ''}
    <section class="panel igc-intro">
      <h3>${opts.replace ? 'تعویض توکن اینستاگرام' : 'اتصال اینستاگرام: راهنمای قدم‌به‌قدم'}</h3>
      <p>با این راهنما یک «توکن دسترسی» از Meta (شرکت مادر اینستاگرام) می‌گیری و این‌جا واردش می‌کنی. توکن کلیدی است که به استودیو اجازه می‌دهد آمار پیجت را بخواند، <b>بدون اینکه رمز اینستاگرامت را به آن بدهی</b>. این مسیر رسمی خود Meta است.</p>
      <dl class="igc-facts">
        <div><dt>زمان</dt><dd>حدود ۲۰ دقیقه</dd></div>
        <div><dt>کجا</dt><dd>مرورگر کامپیوتر</dd></div>
        <div><dt>هزینه</dt><dd>رایگان</dd></div>
        <div><dt>دسترسی استودیو</dt><dd>فقط خواندن آمار</dd></div>
      </dl>
      <p class="igc-note">استودیو هیچ‌وقت چیزی منتشر یا پاک نمی‌کند و به دایرکت‌هایت دست نمی‌زند. این بخش اختیاری است؛ بقیه‌ی استودیو بدون آن هم کامل کار می‌کند.</p>
      <div class="rowbar" style="margin:12px 0 0">
        <span class="cap-hint" style="margin:0">${faNum(n)} از ${faNum(IGC_STEPS.length)} قدم انجام شده</span>
        <span class="grow"></span>
        <button class="btn" id="igcJump">توکن را از قبل دارم</button>
      </div>
    </section>

    <section class="panel igc-before">
      <h3>پیش از شروع</h3>
      <ul class="igc-check">
        <li><b>پیجت باید «حرفه‌ای» باشد</b> (Creator یا Business؛ هر دو کار می‌کند). اگر هنوز شخصی است، در اپ اینستاگرام:<br>${igPath('Settings and activity', 'Account type and tools', 'Switch to professional account')}<br><span class="cap-hint">رایگان است و فالوورها و پست‌هایت دست نمی‌خورند.</span></li>
        <li><b>یک اکانت فیسبوک لازم داری.</b> ورود به پنل Meta با فیسبوک است. لازم نیست پیج اینستاگرامت به فیسبوک وصل باشد.</li>
        <li><b>کار را روی کامپیوتر انجام بده.</b> پنل Meta و صفحه‌ی قبول دعوت روی گوشی کامل کار نمی‌کنند.</li>
      </ul>
      <p class="igc-note">اسم دکمه‌ها همان‌طور که روی صفحه می‌بینی، انگلیسی آمده‌اند. Meta گاهی اسم یا جای دکمه‌ها را کمی عوض می‌کند؛ اگر صفحه‌ای با این راهنما فرق داشت، دنبال نزدیک‌ترین گزینه بگرد، یا از همان صفحه اسکرین‌شات بگیر و در گروه کلاس بپرس.</p>
    </section>

    <div class="start-steps igc-steps">
      ${IGC_STEPS.map(([k, title, body], i) => `
        <section class="start-step igc-step${done.has(k) ? ' done folded' : ''}" data-igc="${k}" id="igc-${k}">
          <div class="start-num">${done.has(k) ? '✓' : faNum(i + 1)}</div>
          <div class="start-main">
            <h3>${title}</h3>
            <div class="start-body igc-body">${body}
              <label class="igc-tick"><input type="checkbox" data-igtick="${k}" ${done.has(k) ? 'checked' : ''}> این قدم را انجام دادم</label>
            </div>
          </div>
        </section>`).join('')}
    </div>

    <section class="panel igc-safe">
      <h3>نگه‌داری از توکن</h3>
      <ul>
        <li><b>توکن مثل رمز عبور است.</b> هر کس داشته باشدش می‌تواند آمار پیجت را بخواند. فقط روی همین کامپیوتر در فایل <code>.env</code> پوشه‌ی استودیو ذخیره می‌شود؛ آن را در چت، ایمیل یا اسکرین‌شات برای کسی نفرست.</li>
        <li><b>۶۰ روز اعتبار دارد</b> و استودیو هر چند روز که باز باشد خودش تمدیدش می‌کند. اگر مدت زیادی استودیو را باز نکردی و منقضی شد، قدم ۷ را تکرار کن و با «تعویض توکن» توکن تازه را بگذار.</li>
        <li><b>اگر فکر می‌کنی لو رفته:</b> در ${igExt('https://www.instagram.com/accounts/manage_access/', 'instagram.com/accounts/manage_access')} تب ${igUi('Active')} اپ را ${igUi('Remove')} کن تا دسترسی‌اش قطع شود، بعد توکن تازه بساز.</li>
        <li><b>تأیید کسب‌وکار (Business Verification) لازم نیست.</b></li>
      </ul>
    </section>

    <section class="panel igc-faq">
      <h3>اگر جایی گیر کردی</h3>
      ${[
        ['Meta اسم اپ را قبول نمی‌کند.', 'کلمه‌های Instagram، IG، Facebook و Meta را از اسم بردار.'],
        ['گزینه‌ی Manage messaging &amp; content on Instagram را پیدا نمی‌کنم.', 'فهرست Use cases را تا پایین ببین. اگر اپ را قبلاً با گزینه‌ی دیگری ساخته‌ای، یک اپ تازه بساز؛ ساختن اپ رایگان است.'],
        ['بعد از Add account پیجم دیده نمی‌شود.', 'دعوت تستر هنوز قبول نشده. قدم ۶ را انجام بده و بعد صفحه‌ی API setup را refresh کن.'],
        ['تب Tester Invites خالی است.', 'یوزرنیمی را که در قدم ۵ نوشتی چک کن (بدون @)، و مطمئن شو با همان پیج وارد instagram.com شده‌ای. یکی دو دقیقه صبر کن و refresh کن.'],
        ['یکی از دسترسی‌ها در فهرست نیست.', `${igUi('Go to permissions and features')} را بزن و از آن‌جا اضافه‌اش کن.`],
        ['استودیو می‌گوید «این شبیه توکن اینستاگرام نیست».', 'توکن ناقص کپی شده. همه‌اش را از اول تا آخر، بدون فاصله‌ی اضافه، دوباره کپی کن.'],
        ['استودیو می‌گوید «اینستاگرام این توکن را قبول نکرد».', 'توکن منقضی شده یا بعد از ساختنش دسترسی اضافه کرده‌ای. در قدم ۷ توکن تازه بساز.'],
        ['اینستاگرام اجازه‌ی اتصال نمی‌دهد.', 'پیج باید حرفه‌ای باشد؛ بخش «پیش از شروع» را ببین.'],
        ['بعضی عددها در آمار خالی‌اند.', 'بعضی آمارها (مثل مخاطب) فقط برای پیج‌هایی با دست‌کم ۱۰۰ فالوور، یا برای پست‌هایی که چند روز از انتشارشان گذشته داده می‌شوند. چند روز بعد دوباره همگام‌سازی کن.'],
      ].map(([q, a]) => `<details><summary>${q}</summary><p>${a}</p></details>`).join('')}
    </section>`;

  if (opts.replace) $('#igBack').onclick = viewInsta;
  $('#igcJump').onclick = () => {
    const s = $('#igc-paste'); s.classList.remove('folded');
    s.scrollIntoView({ behavior: 'smooth', block: 'center' }); setTimeout(() => $('#igToken').focus(), 400);
  };
  $$('.igc-step h3').forEach(h => h.onclick = () => h.closest('.igc-step').classList.toggle('folded'));
  $$('[data-igtick]').forEach(cb => cb.onchange = () => {
    const d = igcDone(); cb.checked ? d.add(cb.dataset.igtick) : d.delete(cb.dataset.igtick);
    localStorage.setItem(IGC_KEY, JSON.stringify([...d]));
    const scroll = window.scrollY; igConnectView(opts); window.scrollTo(0, scroll);
  });
  $('#igConnect').onclick = async () => {
    const tok = $('#igToken').value.trim(); if (!tok) return toast('توکن را بچسبان');
    $('#igConnect').disabled = true; $('#igConnectMsg').textContent = 'در حال بررسی توکن…';
    const r = await igPost('/api/insta/connect', { token: tok });
    $('#igConnect').disabled = false;
    if (!r.ok) { $('#igConnectMsg').textContent = '✕ ' + (r.data.error || 'نشد'); return; }
    localStorage.removeItem(IGC_KEY);
    toast(`✓ وصل شد: @${r.data.username}`); viewInsta();
  };
}

async function loadDataset() {
  const r = await igGet('/api/insta/dataset');
  IGS.dataset = r.ok ? r.data.dataset : null;
  IGS.syncedAt = r.ok ? r.data.synced_at : null;
  const s = $('#igSyncedAt');
  if (s) s.textContent = IGS.syncedAt ? `آخرین همگام‌سازی: ${igAgo(new Date(IGS.syncedAt * 1000).toISOString())}` : 'هنوز همگام‌سازی نشده';
}
async function startSync() {
  const r = await igPost('/api/insta/sync');
  if (!r.ok && r.status !== 409) return toast(r.data.error || 'شروع نشد');
  igPoll('sync', $('#igJob'), afterSync);
}
async function afterSync() { await loadDataset(); renderInstaTab(); }

function renderInstaTab() {
  const v = $('#igView'); if (!v) return;
  if (IGS.igTab === 'analyst') return igAnalyst(v);
  const d = IGS.dataset;
  if (!d) { v.innerHTML = '<div class="empty">هنوز داده‌ای نیست. «همگام‌سازی» را بزن. اولین بار ممکن است چند دقیقه طول بکشد.</div>'; return; }
  ({ overview: igOverview, posts: igPosts, stories: igStories, audience: igAudience, timing: igTiming }[IGS.igTab] || igOverview)(v, d);
}

/* ---------- نمودارهای SVG (بدون کتابخانه) ---------- */
const W = 1000;
function axisY(max, h, top, fmt, min = 0) {
  const ticks = [min, (min + max) / 2, max];
  return ticks.map(t => { const y = top + h - ((t - min) / (max - min)) * h;
    return `<line x1="44" x2="${W - 8}" y1="${y}" y2="${y}" class="ig-grid"/><text x="38" y="${y + 4}" class="ig-axis" text-anchor="end">${esc(fmt(t))}</text>`; }).join('');
}
const compact = n => n >= 1e6 ? `${(n / 1e6).toLocaleString('fa-IR', { maximumFractionDigits: 1 })}M` : n >= 1e3 ? `${(n / 1e3).toLocaleString('fa-IR', { maximumFractionDigits: 1 })}K` : Number(Math.round(n)).toLocaleString('fa-IR');

/** One series over time: 2px line, hover columns with a tooltip. */
function lineChart(rows, key, { title, fmt = compact, h = 170, zero = true } = {}) {
  const pts = rows.filter(r => r[key] != null);
  if (pts.length < 2) return `<div class="panel ig-chart"><h3>${esc(title)}</h3><p class="ig-dim">هنوز داده‌ی کافی نیست.</p></div>`;
  const vals = pts.map(p => p[key]);
  // A level (followers) is read for its change, so its axis hugs the data;
  // a flow (daily views) starts at zero.
  const lo = Math.min(...vals), hi = Math.max(...vals), pad = (hi - lo) * 0.15 || hi * 0.01 || 1;
  const min = zero ? 0 : Math.max(0, lo - pad), max = zero ? (hi * 1.1 || 1) : hi + pad;
  const top = 10, left = 50, right = W - 12;
  const x = i => left + (i / (pts.length - 1)) * (right - left);
  const y = v => top + h - ((v - min) / (max - min)) * h;
  const path = pts.map((p, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(p[key]).toFixed(1)}`).join('');
  const colW = (right - left) / pts.length;
  const cols = pts.map((p, i) => `<rect x="${x(i) - colW / 2}" y="${top}" width="${colW}" height="${h}" class="ig-hit" data-tip="${esc(p.date)}|${esc(title)}: ${esc(fnum(p[key]))}"/>`).join('');
  const anchor = ['start', 'middle', 'end'];
  const lbl = [0, Math.floor(pts.length / 2), pts.length - 1].map((i, n) => `<text x="${x(i)}" y="${top + h + 16}" class="ig-axis" text-anchor="${anchor[n]}">${esc(pts[i].date.slice(5))}</text>`).join('');
  return `<div class="panel ig-chart"><h3>${esc(title)}</h3>
    <svg viewBox="0 0 ${W} ${h + 30}" class="ig-svg" role="img" aria-label="${esc(title)}">
      ${axisY(max, h, top, fmt, min)}<path d="${path}" class="ig-path"/>${cols}${lbl}</svg></div>`;
}

/** Two stacked series per day with a 2px gap; legend + direct labels on the last bar. */
function stackedBars(rows, a, b, { title, la, lb, h = 170 } = {}) {
  const pts = rows.filter(r => r[a] != null || r[b] != null);
  if (pts.length < 2) return `<div class="panel ig-chart"><h3>${esc(title)}</h3><p class="ig-dim">هنوز داده‌ی کافی نیست.</p></div>`;
  const top = 10, left = 50, right = W - 60, max = Math.max(...pts.map(p => (p[a] || 0) + (p[b] || 0))) * 1.1 || 1;
  const bw = (right - left) / pts.length;
  const y = v => (v / max) * h;
  const bars = pts.map((p, i) => {
    const x0 = left + i * bw + 1, w = Math.max(1, bw - 2);
    const ha = y(p[a] || 0), hb = y(p[b] || 0);
    const tip = `${p.date}|${la}: ${fnum(p[a])}|${lb}: ${fnum(p[b])}`;
    return `<g data-tip="${esc(tip)}"><rect x="${x0}" y="${top + h - ha}" width="${w}" height="${ha}" class="s1f"/>
      <rect x="${x0}" y="${top + h - ha - hb - (hb ? 2 : 0)}" width="${w}" height="${hb}" class="s2f"/></g>`;
  }).join('');
  const last = pts[pts.length - 1];
  const lx = left + pts.length * bw + 6;
  return `<div class="panel ig-chart"><h3>${esc(title)}</h3>
    <div class="ig-legend"><span><i class="s1f"></i>${esc(la)}</span><span><i class="s2f"></i>${esc(lb)}</span></div>
    <svg viewBox="0 0 ${W} ${h + 30}" class="ig-svg" role="img" aria-label="${esc(title)}">
      ${axisY(max, h, top, compact)}${bars}
      <text x="${lx}" y="${top + h - y(last[a] || 0) / 2 + 4}" class="ig-axis">${esc(la)}</text>
      <text x="${lx}" y="${top + h - y(last[a] || 0) - y(last[b] || 0) / 2 + 4}" class="ig-axis">${esc(lb)}</text>
      <text x="${left}" y="${top + h + 16}" class="ig-axis">${esc(pts[0].date.slice(5))}</text>
      <text x="${left + pts.length * bw}" y="${top + h + 16}" class="ig-axis" text-anchor="end">${esc(last.date.slice(5))}</text></svg></div>`;
}

/** Horizontal bars, one series, sorted; label + value always visible. */
function hBars(entries, { title, total, max = 10 } = {}) {
  const list = entries.filter(e => e[1] != null).sort((x, y) => y[1] - x[1]).slice(0, max);
  if (!list.length) return `<div class="panel ig-chart"><h3>${esc(title)}</h3><p class="ig-dim">داده‌ای نیست (زیر ۱۰۰ فالوور یا هنوز ثبت نشده).</p></div>`;
  const sum = total || list.reduce((s, e) => s + e[1], 0);
  const top = list[0][1] || 1;
  return `<div class="panel ig-chart"><h3>${esc(title)}</h3>${list.map(([k, n]) => `
    <div class="ig-hbar" data-tip="${esc(k)}|${esc(fnum(n))} (${esc(fpct(n / sum * 100))})">
      <span class="ig-hlabel" dir="auto">${esc(k)}</span>
      <span class="ig-htrack"><i class="s1f" style="width:${Math.max(1, n / top * 100)}%"></i></span>
      <span class="ig-hval">${esc(fpct(n / sum * 100))}</span></div>`).join('')}</div>`;
}

/** Ratio bars against the account's own median (1 = usual). */
function ratioBars(cells, { title, rtl = false }) {
  const vals = cells.filter(c => c.median_ratio != null);
  if (!vals.length) return `<div class="panel ig-chart"><h3>${esc(title)}</h3><p class="ig-dim">هنوز پست کافی با آمار نیست.</p></div>`;
  const max = Math.max(1.5, ...vals.map(c => c.median_ratio)) * 1.1;
  const h = 150, top = 10, left = 44, right = W - 10, bw = (right - left) / cells.length;
  const y1 = top + h - (1 / max) * h;
  const bars = cells.map((c, i) => {
    const x0 = left + (rtl ? cells.length - 1 - i : i) * bw + 1, w = bw - 2;
    const lab = `<text x="${x0 + w / 2}" y="${top + h + 16}" class="ig-axis" text-anchor="middle">${esc(c.label)}</text>`;
    if (c.median_ratio == null) return lab;
    const bh = (c.median_ratio / max) * h, few = c.n < 3;
    return `<g data-tip="${esc(c.label)}|${esc(fx(c.median_ratio))} معمول|${esc(fnum(c.n))} پست${few ? ' (نمونه کم)' : ''}">
      <rect x="${x0}" y="${top + h - bh}" width="${w}" height="${bh}" rx="3" class="s1f ${few ? 'few' : ''}"/>
      <text x="${x0 + w / 2}" y="${top + h - bh - 4}" class="ig-axis" text-anchor="middle">${esc(fx(c.median_ratio))}</text></g>${lab}`;
  }).join('');
  return `<div class="panel ig-chart"><h3>${esc(title)}</h3>
    <svg viewBox="0 0 ${W} ${h + 30}" class="ig-svg" role="img" aria-label="${esc(title)}">
      <line x1="${left}" x2="${right}" y1="${y1}" y2="${y1}" class="ig-base"/>
      <text x="${left - 4}" y="${y1 + 4}" class="ig-axis" text-anchor="end">معمول</text>${bars}</svg>
    <p class="cap-hint">ارتفاع = میانه‌ی بازدید پست‌ها نسبت به میانه‌ی همان نوع پست. ستون‌های کم‌رنگ کمتر از ۳ نمونه دارند و قابل‌اتکا نیستند.</p></div>`;
}

/* ---------- نمای کلی ---------- */
function delta(a, b) {
  if (a == null || !b) return '';
  const p = Math.round((a - b) / b * 100);
  return `<em class="${p >= 0 ? 'up' : 'down'}">${p >= 0 ? '▲' : '▼'} ${faNum(Math.abs(p))}٪</em>`;
}
function postLine(p) {
  return `<div class="ig-line"><img class="ig-thumbsm" src="/api/insta/thumb?kind=media&id=${encodeURIComponent(p.id)}" loading="lazy" alt="">
    <a class="grow" href="${esc(p.permalink || '#')}" target="_blank" rel="noopener">${esc(p.hook || '(بدون کپشن)')}</a>
    <span class="ig-dim">${esc(TYPE_FA[p.type] || p.type)} · ${esc(p.date || '')}</span><b>${esc(fx(p.views_vs_median))}</b></div>`;
}
function igOverview(v, d) {
  const s = d.summary, a = s.last30, b = s.prev30;
  const days = d.account_days.slice(-90);
  const recent = d.posts.filter(p => p.views_vs_median != null && (p.age_days ?? 99) <= 30);
  const best = [...recent].sort((x, y) => y.views_vs_median - x.views_vs_median).slice(0, 3);
  const worst = [...recent].filter(p => (p.age_days ?? 0) >= 3).sort((x, y) => x.views_vs_median - y.views_vs_median).slice(0, 3);
  const net = a.follows != null && a.unfollows != null ? a.follows - a.unfollows : null;
  v.innerHTML = `
    <div class="stats">
      <div class="stat"><b>${fnum(s.followers)}</b><span>فالوور</span></div>
      <div class="stat"><b>${compact(a.views || 0)} ${delta(a.views, b.views)}</b><span>بازدید ۳۰ روز</span></div>
      <div class="stat"><b>${compact(a.reach || 0)} ${delta(a.reach, b.reach)}</b><span>reach ۳۰ روز</span></div>
      <div class="stat"><b>${compact(a.interactions || 0)} ${delta(a.interactions, b.interactions)}</b><span>تعامل ۳۰ روز</span></div>
      <div class="stat"><b>${net == null ? '—' : `<bdi dir="ltr">${net >= 0 ? '+' : ''}${fnum(net)}</bdi>`}</b><span>فالو منهای آنفالو ۳۰ روز</span></div>
      <div class="stat"><b>${fnum(a.profile_links_taps)}</b><span>کلیک لینک‌های پروفایل</span></div>
      <div class="stat"><b>${fnum(a.posts)}</b><span>پست در ۳۰ روز</span></div>
    </div>
    ${a.days < 30 ? `<p class="ig-dim">آمار حساب برای ${fnum(a.days)} روز از ۳۰ روز ثبت شده؛ هر «همگام‌سازی» روزهای جاافتاده را تا ۹۰ روز عقب پر می‌کند.</p>` : ''}
    ${lineChart(days, 'views', { title: 'بازدید روزانه' })}
    ${stackedBars(days, 'reach_followers', 'reach_non_followers', { title: 'reach روزانه: فالوورها و غیرفالوورها', la: 'فالوور', lb: 'غیرفالوور' })}
    ${lineChart(days, 'followers', { title: 'تعداد فالوور', zero: false })}
    <div class="cards2">
      <section class="panel"><h3>بهترین‌های ۳۰ روز (نسبت به معمول)</h3>${best.map(postLine).join('') || '<p class="ig-dim">—</p>'}</section>
      <section class="panel"><h3>ضعیف‌ترین‌ها (دست‌کم ۳ روزه)</h3>${worst.map(postLine).join('') || '<p class="ig-dim">—</p>'}</section>
    </div>`;
}

/* ---------- پست‌ها ---------- */
const POST_SORTS = [['date', 'تازه‌ترین'], ['views_vs_median', 'بازدید نسبت به معمول'], ['share_rate', 'نرخ ارسال'],
  ['save_rate', 'نرخ ذخیره'], ['avg_watch_s', 'زمان تماشا'], ['follows', 'فالو']];
function igPosts(v, d) {
  let list = d.posts.filter(p => IGS.postType === 'all' || p.type === IGS.postType);
  const k = IGS.postSort;
  list = [...list].sort((x, y) => k === 'date' ? (y.posted_at || '').localeCompare(x.posted_at || '') : (y[k] ?? -1) - (x[k] ?? -1)).slice(0, 200);
  const base = d.baselines[IGS.postType] || null;
  v.innerHTML = `
    <div class="filters">${['all', 'REELS', 'POST', 'CAROUSEL'].map(t => `<button data-ptype="${t}" class="${IGS.postType === t ? 'on' : ''}">${t === 'all' ? 'همه' : TYPE_FA[t]}</button>`).join('')}
      <span style="width:12px"></span>
      <select id="pSort" class="ig-select">${POST_SORTS.map(([kk, l]) => `<option value="${kk}" ${kk === k ? 'selected' : ''}>${l}</option>`).join('')}</select></div>
    ${base ? `<p class="ig-dim">میانه‌ی ${esc(TYPE_FA[IGS.postType])}ها در ۹۰ روز (${fnum(base.n)} پست): بازدید ${fnum(base.views)} · reach ${fnum(base.reach)} · ارسال ${fpct(base.share_rate)} · ذخیره ${fpct(base.save_rate)}${base.avg_watch_s ? ` · تماشا ${fnum(base.avg_watch_s)} ثانیه` : ''}</p>` : ''}
    <div class="ig-tablewrap"><table class="ig-table"><thead><tr>
      <th></th><th>تاریخ</th><th>هوک</th><th>بازدید</th><th>نسبت به معمول</th><th>reach</th><th>ارسال</th><th>ذخیره</th><th>تماشا (ث)</th><th>رد شدن</th><th>فالو</th>
    </tr></thead><tbody>${list.map(p => `<tr>
      <td><img class="ig-thumbsm" src="/api/insta/thumb?kind=media&id=${encodeURIComponent(p.id)}" loading="lazy" alt=""></td>
      <td class="ig-nowrap">${esc(p.date || '')}<br><small class="ig-dim">${esc(TYPE_FA[p.type] || p.type)}${p.age_days != null && p.age_days < 3 ? ' · تازه' : ''}</small></td>
      <td class="ig-hook"><a href="${esc(p.permalink || '#')}" target="_blank" rel="noopener">${esc(p.hook || '(بدون کپشن)')}</a></td>
      <td>${fnum(p.views)}</td>
      <td>${p.views_vs_median == null ? '—' : `<span class="ig-ratio ${p.views_vs_median >= 1 ? 'up' : 'down'}">${p.views_vs_median >= 1 ? '▲' : '▼'} ${esc(fx(p.views_vs_median))}</span>`}</td>
      <td>${fnum(p.reach)}</td><td>${fpct(p.share_rate)}</td><td>${fpct(p.save_rate)}</td>
      <td>${fnum(p.avg_watch_s)}</td><td>${p.skip_rate == null ? '—' : fpct(p.skip_rate)}</td><td>${fnum(p.follows)}</td></tr>`).join('')}</tbody></table></div>
    ${!list.length ? '<div class="empty">پستی نیست.</div>' : ''}`;
  $$('[data-ptype]', v).forEach(b => b.onclick = () => { IGS.postType = b.dataset.ptype; igPosts(v, d); });
  $('#pSort').onchange = e => { IGS.postSort = e.target.value; igPosts(v, d); };
}

/* ---------- استوری‌ها ---------- */
function igStories(v, d) {
  const byId = Object.fromEntries(d.stories.map(s => [s.id, s]));
  const daysList = Object.keys(d.story_days || {}).sort().reverse().slice(0, 21);
  if (!daysList.length) { v.innerHTML = '<div class="empty">هنوز استوری‌ای ثبت نشده. اینستاگرام آمار استوری را فقط ۲۴ ساعت نگه می‌دارد؛ هر روز یک بار «همگام‌سازی» بزن تا استوری‌هایت ثبت شوند.</div>'; return; }
  v.innerHTML = daysList.map(day => {
    const ss = d.story_days[day].map(id => byId[id]).filter(Boolean);
    const first = ss.find(s => s.reach != null), last = [...ss].reverse().find(s => s.reach != null);
    const keep = first && last && first.reach ? Math.round(last.reach / first.reach * 100) : null;
    const sum = k => ss.reduce((t, s) => t + (s[k] || 0), 0);
    const top = Math.max(1, ...ss.map(s => s.reach || 0));
    return `<section class="panel" style="margin-bottom:14px">
      <h3>${esc(day)} · ${fnum(ss.length)} استوری</h3>
      <div class="idea-meta" style="margin-bottom:12px">
        ${keep != null ? `<span>ماندگاری تا آخرین استوری: ${fpct(keep)}</span>` : ''}
        <span>ریپلای: ${fnum(sum('replies'))}</span><span>کلیک لینک: ${fnum(sum('link_clicks'))}</span>
        <span>خروج: ${fnum(sum('tap_exit'))}</span><span>فالو: ${fnum(sum('follows'))}</span></div>
      <div class="ig-storyrow">${ss.map(s => `<div class="ig-story" data-tip="${esc(s.time || '')}|reach: ${esc(fnum(s.reach))}|ریپلای: ${esc(fnum(s.replies))} · خروج: ${esc(fnum(s.tap_exit))}">
        ${s.has_thumb ? `<img src="/api/insta/thumb?kind=story&id=${encodeURIComponent(s.id)}" loading="lazy" alt="">` : '<div class="ig-noimg"></div>'}
        <div class="ig-sbar"><i class="s1f" style="height:${Math.round((s.reach || 0) / top * 100)}%"></i></div>
        <small>${esc(fnum(s.reach))}</small></div>`).join('')}</div></section>`;
  }).join('');
}

/* ---------- مخاطب ---------- */
function igAudience(v, d) {
  const a = d.audience || {};
  const ent = o => Object.entries(o || {});
  const gender = ent(a.gender).map(([k, n]) => [{ F: 'زن', M: 'مرد', U: 'نامشخص' }[k] || k, n]);
  v.innerHTML = `${d.audience_at ? `<p class="ig-dim">ثبت‌شده در ${esc(d.audience_at)} (هفته‌ای یک بار به‌روز می‌شود)</p>` : ''}
    <div class="cards2">${hBars(ent(a.age), { title: 'سن', max: 8 })}${hBars(gender, { title: 'جنسیت' })}</div>
    <div class="cards2">${hBars(ent(a.country), { title: 'کشورها (۱۰ تای اول)' })}${hBars(ent(a.city), { title: 'شهرها (۱۰ تای اول)' })}</div>`;
}

/* ---------- زمان انتشار ---------- */
function igTiming(v, d) {
  v.innerHTML = `<div class="ig-note">ساعت‌ها به وقت تهران‌اند، چون بیشتر مخاطب در ایران است. فقط پست‌های ۹۰ روز اخیر حساب شده‌اند.</div>
    ${ratioBars(d.timing.by_weekday, { title: 'روز هفته', rtl: true })}
    ${ratioBars(d.timing.by_hour, { title: 'ساعت انتشار (بازه‌های ۳ساعته)' })}`;
}

/* ---------- تحلیلگر ---------- */
async function igAnalyst(v) {
  const lr = await igGet('/api/insta/reports');
  IGS.reports = lr.ok ? lr.data : [];
  const name = IGS.report && IGS.reports.includes(IGS.report) ? IGS.report : IGS.reports[0];
  v.innerHTML = `
    <div class="ig-note">تحلیلگر (Claude روی همین کامپیوتر) دیتاست، هسته‌ی برند و بانک ایده را می‌خواند و می‌گوید چه شد، چرا، و هفته‌ی بعد چه کنی. هیچ عددی را از خودش نمی‌سازد و برای هر ادعا لینک پست را می‌آورد.</div>
    <div class="rowbar">
      <button class="btn primary" id="rNew">ساخت گزارش تازه</button>
      ${IGS.reports.length ? `<select id="rPick" class="ig-select">${IGS.reports.map(r => `<option ${r === name ? 'selected' : ''}>${esc(r)}</option>`).join('')}</select>` : ''}
      ${name && (Date.now() - Date.parse(name)) > 7 * 86400000 ? '<span class="ig-err">آخرین گزارش بیش از یک هفته پیش است</span>' : ''}
    </div>
    <div id="rJob" class="build-status" hidden></div>
    <div id="rBody">${name ? '<span class="spin"></span>' : '<div class="empty">هنوز گزارشی ساخته نشده.</div>'}</div>`;
  $('#rNew').onclick = async () => {
    const r = await igPost('/api/insta/report'); if (!r.ok) return toast(r.data.error || 'شروع نشد');
    igPoll('report', $('#rJob'), j => { IGS.report = j.result && j.result.name; igAnalyst(v); });
  };
  const pick = $('#rPick'); if (pick) pick.onchange = () => { IGS.report = pick.value; igAnalyst(v); };
  const jobs = await igGet('/api/jobs');
  if (jobs.ok && jobs.data.report.state === 'running') igPoll('report', $('#rJob'), j => { IGS.report = j.result && j.result.name; igAnalyst(v); });
  if (name) renderReport($('#rBody'), name);
}

async function renderReport(box, name) {
  const r = await igGet(`/api/insta/report?name=${encodeURIComponent(name)}`);
  if (!r.ok) { box.innerHTML = `<div class="ig-note err">${esc(r.data.error || 'خطا')}</div>`; return; }
  const rep = r.data;
  const text = rep.text.replace(/```json[\s\S]*?```\s*$/, '');
  box.innerHTML = `
    <section class="panel" style="margin-bottom:16px"><div class="md" style="max-width:none">${md(text)}</div></section>
    ${rep.ideas.length ? `<section class="panel" style="margin-bottom:16px"><h3>ایده‌های پیشنهادی</h3>
      ${rep.ideas.map((i, n) => `<div class="ig-line"><span class="grow"><b>${esc(i.title)}</b><br><small class="ig-dim">${esc(i.pillar || '')} · ${esc(i.why || '')}</small></span>
        <button class="btn" data-ridea="${n}">به بانک ایده</button></div>`).join('')}</section>` : ''}
    <section class="panel"><h3>از تحلیلگر بپرس</h3>
      ${(rep.chat || []).map(c => `<div class="ig-qa"><p class="ig-q">${esc(c.q)}</p><div class="md" style="max-width:none">${md(c.a)}</div></div>`).join('')}
      <textarea id="askQ" class="cap-text" style="min-height:80px" placeholder="مثلاً: چرا ریل‌های مسیر شغلی این ماه کمتر ارسال شدند؟"></textarea>
      <div class="rowbar" style="margin-top:8px"><span class="grow"></span><button class="btn primary" id="askBtn">بپرس</button></div>
      <div id="askJob" class="build-status" hidden></div></section>`;
  $$('[data-ridea]', box).forEach(b => b.onclick = async () => {
    const i = rep.ideas[+b.dataset.ridea];
    const r2 = await post('/api/idea/capture', { kind: 'analyst', title: i.title,
      text: `# ${i.title}\n\nپیشنهاد تحلیلگر اینستاگرام (گزارش ${name}).\n\n${i.why || ''}`,
      pillar: IG_PILLARS.includes(i.pillar) ? i.pillar : '' });
    if (r2.ok) { b.disabled = true; b.textContent = '✓ اضافه شد'; await loadState(); } else toast(r2.data.error || 'اضافه نشد');
  });
  $('#askBtn', box).onclick = async () => {
    const q = $('#askQ', box).value.trim(); if (!q) return toast('سؤال را بنویس');
    const r2 = await igPost('/api/insta/ask', { name, q }); if (!r2.ok) return toast(r2.data.error || 'شروع نشد');
    $('#askBtn', box).disabled = true;
    igPoll('ask', $('#askJob', box), () => renderReport(box, name));
  };
}

window.viewInsta = viewInsta;
