/* ================= تدوین ویدیو =================
   ویدیوی خام → برش سکوت و تکرار، زیرنویس فارسی، عکس و گرافیک، سایت و هایلایت، افکت صوتی، رندر. سرور: app/video.py؛ موتور: app/video_engine.py.
   پیش‌نمایش همان ترکیب رندر است که در iframe اجرا می‌شود (comp/preview.html + preview-shim.js)؛
   این صفحه با postMessage فرمان پخش و جست‌وجو می‌دهد و زمان را پس می‌گیرد.
   همه‌چیز به اندیس کلمه گره خورده: حذف یا برگرداندن یک کلمه، زمان خروجی همه‌چیز را از نو می‌سازد.
   ذخیره‌ها تک‌فیلدی‌اند (/api/video/edit)، تا گوشی و مک کار هم را پاک نکنند. */

const VD = {
  id: null, data: null, poll: null, listPoll: null, sel: new Set(), anchor: null, drag: false,
  t: 0, dur: 0, paused: true, pv: 0, kind: 'reel', upKind: 'reel', fixing: null, delArm: null,
  openId: new URLSearchParams(location.search).get('v'),   // go() نشانی را به ?s=video برمی‌گرداند؛ پیش از آن گرفته می‌شود
};
const VD_REASON = { retake: 'برداشت دوباره', false_start: 'شروع ناقص', stutter: 'تپق', filler: 'پرکننده',
  offtopic: 'بیرون از موضوع', manual: 'دستی' };
const VD_RHYTHM = { slow: 'آرام', normal: 'معمولی', fast: 'تند', tight: 'خیلی تند (بدون نفس)' };
const VD_POS = { auto: 'خودکار', top: 'بالا', mid: 'وسط', bot: 'پایین' };
const vdPosName = p => typeof p === 'number' ? 'دستی' : ({ ...VD_POS, above: 'بالای صورت', below: 'زیر صورت' }[p] || VD_POS.bot);
const VD_W = { reel: [1080, 1920], screen: [1920, 1080] };

const vdT = s => { s = Math.max(0, Math.round(+s || 0)); return faNum(`${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`); };
const vdSec = s => faNum((Math.round((+s || 0) * 10) / 10).toString().replace('.', '٫'));
const vdMedia = (id, path, v) => `/video-media/${encodeURIComponent(id)}/${path}${v ? `?v=${v}` : ''}`;

function vdJobLine(j) {
  if (!j || !j.state) return '';
  if (j.state === 'running') {
    const step = { ingest: 'آماده‌سازی', transcribe: 'تبدیل صدا به متن', decide: 'تصمیم‌های Claude', preview: 'ساخت پیش‌نمایش',
      sfx: 'پیشنهاد افکت‌های صوتی', vis: 'چیدن عکس و گرافیک', sites: 'پیدا کردن منبع‌ها در وب', screen: 'زوم هوشمند و محو اطلاعات حساس', post: 'کاور و کپشن', render: 'رندر نهایی', regen: 'بازتولید با نظر تو', all: 'ساخت کامل' }[j.step] || j.step;
    return `<span class="spin"></span><span>${esc(j.msg || step + '…')}</span>`;
  }
  if (j.state === 'error') return `<span>خطا در «${esc(j.step || '')}»: ${esc(j.error || '')}</span>`;
  return '';
}

/* ---------------- صفحه‌ی اصلی ---------------- */
async function viewVideo() {
  clearTimeout(VD.poll); clearTimeout(VD.listPoll);
  window.removeEventListener('message', vdOnMsg);
  if (VD.openId) { const id = VD.openId; VD.openId = null; return vdOpen(id); }
  vdHome();
}

function vdHome() {
  VD.id = null; VD.data = null;
  history.replaceState(null, '', '?s=video');
  $('#page').innerHTML = `
    <div class="vd-wrap">
      <div class="page-head"><h2>تدوین ویدیو</h2>
        <p>ویدیوی خام را بده: سکوت‌ها، تپق‌ها و برداشت‌های تکراری بریده می‌شوند، زیرنویس فارسی می‌خورد و خروجی آماده‌ی انتشار می‌گیری. بعد هر بخش را خودت ویرایش می‌کنی یا با یک نظر از نو می‌سازی.</p></div>
      <section class="panel vd-up">
        <h3>ویدیوی تازه</h3>
        <div class="vd-kinds">
          <button class="btn ${VD.upKind === 'reel' ? 'on' : ''}" data-kind="reel">ریلز عمودی <small>حرف زدن جلوی دوربین</small></button>
          <button class="btn ${VD.upKind === 'screen' ? 'on' : ''}" data-kind="screen">ضبط صفحه <small>آموزش یا دمو</small></button>
        </div>
        <input id="vdTitle" class="vd-input" placeholder="اسم ویدیو (اختیاری؛ وگرنه Claude می‌گذارد)" autocomplete="off">
        <div class="vd-partsw"><b>چه کارهایی خودکار انجام شود؟</b>
          <div class="vd-parts" id="vdParts"><span class="cr-dim">…</span></div>
          <small class="cr-dim">آماده‌سازی، تبدیل صدا به متن و پیش‌نمایش همیشه انجام می‌شوند. هر کاری را که الان نخواهی، بعداً از بخش خودش در صفحه‌ی ویدیو می‌سازی.</small></div>
        <label class="vd-drop" id="vdDrop">
          <input type="file" id="vdFile" accept="video/*,.mov,.mp4,.m4v,.webm" hidden>
          <b>فایل ویدیو را این‌جا بکش یا بزن تا انتخاب کنی</b>
          <span>MP4 یا MOV، از مک یا گوشی. بعد از آپلود، کارهای تیک‌خورده خودکار شروع می‌شوند.</span>
        </label>
        <div id="vdUpState" class="build-status" hidden></div>
      </section>
      <section class="vd-listwrap"><h3>ویدیوها</h3><div id="vdList" class="vd-list"><div class="cr-dim">در حال بارگذاری…</div></div></section>
    </div>`;
  $$('.vd-kinds .btn').forEach(b => b.onclick = () => {
    VD.upKind = b.dataset.kind; $$('.vd-kinds .btn').forEach(x => x.classList.toggle('on', x === b));
    vdPartsPaint();
  });
  const drop = $('#vdDrop'), file = $('#vdFile');
  file.onchange = () => file.files[0] && vdUpload(file.files[0]);
  drop.ondragover = e => { e.preventDefault(); drop.classList.add('over'); };
  drop.ondragleave = () => drop.classList.remove('over');
  drop.ondrop = e => { e.preventDefault(); drop.classList.remove('over'); const f = e.dataTransfer.files[0]; if (f) vdUpload(f); };
  vdPartsPaint();
  vdLoadList();
}

async function vdLoadList() {
  clearTimeout(VD.listPoll);
  if (S.section !== 'video' || VD.id) return;
  const d = await api('/api/video/list');
  const box = $('#vdList'); if (!box || !d) return;
  if (!VD.parts && d.parts) {                // انتخاب آپلود قبلی؛ بعد از آن تیک‌های همین صفحه
    VD.partList = d.parts; VD.parts = Object.fromEntries(d.parts.map(p => [p.k, p.on]));
    vdPartsPaint();
  }
  const vids = d.videos || [];
  box.innerHTML = vids.length ? vids.map(v => {
    const j = v.job || {};
    const tag = j.state === 'running' ? `<span class="cr-tag run">${esc(j.msg || 'در حال کار…')}</span>`
      : j.state === 'error' ? '<span class="cr-tag err">خطا</span>'
      : v.final ? '<span class="cr-tag ok">رندر شده</span>' : '';
    const dur = v.dur ? vdT(v.dur) + (v.outDur ? ' ← ' + vdT(v.outDur) : '') : '';
    return `<div class="vd-card" data-id="${esc(v.id)}">
      <div class="vd-thumb ${v.kind}">${v.thumb ? `<img src="${vdMedia(v.id, 'thumb.jpg')}" alt="">` : '<span class="spin"></span>'}</div>
      <div class="vd-cmeta"><b>${esc(v.title)}</b>
        <span>${v.kind === 'screen' ? 'ضبط صفحه' : 'ریلز'}${dur ? ' · ' + dur : ''}</span>${tag}</div>
      <button class="btn vd-del" data-del="${esc(v.id)}" title="به سطل">${VD.delArm === v.id ? 'مطمئنی؟' : '🗑'}</button>
    </div>`;
  }).join('') : '<div class="cr-dim">هنوز ویدیویی نیست.</div>';
  $$('.vd-card', box).forEach(c => c.onclick = e => { if (!e.target.closest('.vd-del')) vdOpen(c.dataset.id); });
  $$('.vd-del', box).forEach(b => b.onclick = async e => {
    e.stopPropagation();
    if (VD.delArm !== b.dataset.del) { VD.delArm = b.dataset.del; return vdLoadList(); }
    VD.delArm = null;
    const r = await post('/api/video/delete', { id: b.dataset.del });
    toast(r.ok ? 'به سطل رفت' : (r.data.error || 'نشد')); vdLoadList();
  });
  if (vids.some(v => (v.job || {}).state === 'running')) VD.listPoll = setTimeout(vdLoadList, 2500);
}

/* تیک کارهای خودکار پیش از آپلود (۲۰۲۶-۱۰-۰۸)؛ زوم و محو فقط برای ضبط صفحه */
const VD_PART_HINT = { cuts: 'سکوت، تپق، تکرار', captions: 'فارسی، کلمه‌به‌کلمه', voice: 'حذف نویز', sfx: 'پیشنهاد Claude',
  vis: 'گرافیک خودکار', sites: 'پیدا کردن در وب', zooms: 'جایی که اشاره می‌کنی', blurs: 'ایمیل، کلید، کارت', post: 'پیشنهاد Claude' };
const vdPartsShown = () => (VD.partList || []).filter(p => !p.screen || VD.upKind === 'screen');
function vdPartsPaint() {
  const box = $('#vdParts'); if (!box || !VD.parts) return;
  box.innerHTML = vdPartsShown().map(p => `<label class="vd-part ${VD.parts[p.k] ? 'on' : ''}">
    <input type="checkbox" data-part="${p.k}" ${VD.parts[p.k] ? 'checked' : ''}><span>${esc(p.fa)}</span>
    <small>${esc(VD_PART_HINT[p.k] || '')}</small></label>`).join('');
  $$('[data-part]', box).forEach(c => c.onchange = () => {
    VD.parts[c.dataset.part] = c.checked; c.closest('.vd-part').classList.toggle('on', c.checked);
  });
}

async function vdUpload(f) {
  const st = $('#vdUpState'); st.hidden = false; st.classList.remove('err');
  if (!/\.(mp4|mov|m4v|webm|mkv)$/i.test(f.name)) { st.classList.add('err'); st.textContent = 'فقط فایل ویدیو (MP4، MOV، M4V، WEBM).'; return; }
  const parts = VD.parts ? Object.fromEntries(vdPartsShown().map(p => [p.k, !!VD.parts[p.k]])) : undefined;
  const r = await post('/api/video/new', { kind: VD.upKind, title: $('#vdTitle').value.trim(), parts });
  if (!r.ok) { st.classList.add('err'); st.textContent = r.data.error || 'نشد'; return; }
  const id = r.data.id;
  st.innerHTML = '<span class="spin"></span><span id="vdUpPct">آپلود… ۰٪</span><i class="vd-bar"><i id="vdUpBar"></i></i>';
  const xhr = new XMLHttpRequest();
  xhr.open('POST', `/api/video/upload?id=${encodeURIComponent(id)}&name=${encodeURIComponent(f.name)}`);
  xhr.upload.onprogress = e => {
    if (!e.lengthComputable) return;
    const p = Math.round(e.loaded / e.total * 100);
    $('#vdUpPct') && ($('#vdUpPct').textContent = `آپلود… ${faNum(p)}٪ (${faNum((e.total / 1048576).toFixed(0))} مگ)`);
    $('#vdUpBar') && ($('#vdUpBar').style.width = p + '%');
  };
  xhr.onload = () => {
    if (xhr.status === 200) { toast('آپلود شد؛ پردازش شروع شد'); vdOpen(id); }
    else { st.classList.add('err'); let m = 'آپلود نشد'; try { m = JSON.parse(xhr.responseText).error || m; } catch {} st.textContent = m; }
  };
  xhr.onerror = () => { st.classList.add('err'); st.textContent = 'اتصال قطع شد؛ دوباره امتحان کن.'; };
  xhr.send(f);
}

/* ---------------- صفحه‌ی پروژه ---------------- */
async function vdOpen(id) {
  clearTimeout(VD.listPoll); clearTimeout(VD.poll);
  Object.assign(VD, { id, data: null, sel: new Set(), anchor: null, pv: 0, fixing: null, t: 0, paused: true });
  history.replaceState(null, '', `?s=video&v=${encodeURIComponent(id)}`);
  $('#page').innerHTML = '<div class="empty">در حال بارگذاری…</div>';
  window.removeEventListener('message', vdOnMsg); window.addEventListener('message', vdOnMsg);
  await vdRefresh(true);
}

async function vdRefresh(first) {
  clearTimeout(VD.poll);
  if (S.section !== 'video' || !VD.id) return;
  const d = await api(`/api/video/project?id=${encodeURIComponent(VD.id)}`);
  if (!d) { $('#page').innerHTML = '<div class="empty">این ویدیو پیدا نشد. <a href="?s=video">برگرد</a></div>'; return; }
  const was = VD.data;
  VD.data = d; VD.kind = d.canvas || d.kind;
  // ضبط صفحه با خروجی عمودی: کادر پیش‌نمایش عوض می‌شود، پس پوسته از نو
  if (first || !$('.vd-proj') || (was && (was.canvas || was.kind) !== VD.kind)) { VD.pv = 0; vdShell(d); }
  vdPaint(d, was);
  const busy = (d.job || {}).state === 'running' || d.mediaBusy || (d.media || []).some(m => ['upload', 'queued', 'analyze', 'process'].includes(m.status))
    || d.sitesBusy || (d.sites || []).some(s => ['queued', 'capturing', 'upload'].includes(s.status)) || vdPostBusy(d);
  VD.poll = setTimeout(() => vdRefresh(false), busy ? 1500 : 6000);
}

function vdShell(d) {
  $('#page').innerHTML = `
    <div class="vd-wrap vd-proj">
      <div class="vd-top">
        <button class="btn" id="vdBack">→ همه‌ی ویدیوها</button>
        <input id="vdName" class="vd-name" value="${esc(d.title)}" title="اسم ویدیو">
        <span class="cr-tag">${d.kind === 'screen' ? 'ضبط صفحه' : 'ریلز ۹:۱۶'}</span>
        <span class="grow"></span>
        <button class="btn" id="vdAll" title="هر مرحله‌ای که انجام نشده، به ترتیب">⚡ ساخت کامل</button>
        <button class="btn primary" id="vdRender">رندر نهایی</button>
      </div>
      <div id="vdJob" class="build-status" hidden></div>
      <div class="vd-grid">
        <div class="vd-player">
          <div class="vd-stage ${d.canvas || d.kind}" id="vdStage"><div class="vd-ph"><span class="spin"></span><span>پیش‌نمایش بعد از آماده‌سازی…</span></div></div>
          <div class="vd-ctrl">
            <button class="btn" id="vdPlay" title="پخش/توقف (Space)">▶</button>
            <input type="range" id="vdSeek" min="0" max="1000" value="0" dir="ltr">
            <span id="vdTime" class="vd-time">۰:۰۰</span>
          </div>
          ${(d.canvas || d.kind) === 'reel' ? `<label class="vd-guide-t"><input type="checkbox" id="vdGuide" ${VD.guide ? 'checked' : ''}> راهنمای اینستاگرام
            <small>(جای دکمه‌ها، کپشن و نوار بالا؛ در خروجی نیست)</small></label>` : ''}
          <div id="vdStats" class="vd-stats"></div>
        </div>
        <div class="vd-secs">
          <section class="panel vd-sec" id="vdCuts"></section>
          <section class="panel vd-sec" id="vdCaps"></section>
          ${d.kind === 'screen' ? '<section class="panel vd-sec" id="vdScreen"></section>' : ''}
          <section class="panel vd-sec" id="vdVis"></section>
          <section class="panel vd-sec" id="vdSites"></section>
          <section class="panel vd-sec" id="vdSfx"></section>
          <section class="panel vd-sec" id="vdOut"></section>
          <section class="panel vd-sec" id="vdPost"></section>
        </div>
      </div>
    </div>`;
  $('#vdBack').onclick = () => { window.removeEventListener('message', vdOnMsg); clearTimeout(VD.poll); vdHome(); };
  $('#vdName').onchange = async e => {
    const r = await post('/api/video/edit', { id: VD.id, op: 'title', title: e.target.value });
    toast(r.ok ? 'اسم ذخیره شد' : 'نشد');
  };
  $('#vdAll').onclick = () => vdRun('all');
  $('#vdRender').onclick = () => vdRun('render');
  $('#vdPlay').onclick = () => vdCmd({ cmd: 'toggle' });
  $('#vdGuide') && ($('#vdGuide').onchange = e => { VD.guide = e.target.checked; vdGuideLayer(); });
  $('#vdSeek').oninput = e => vdCmd({ cmd: 'seek', t: (+e.target.value / 1000) * (VD.dur || 0) });
  document.removeEventListener('keydown', vdKey); document.addEventListener('keydown', vdKey);
  if (!VD.bound) {     // یک بار؛ هندلرهای سراسری بقیه‌ی تب‌ها دست نمی‌خورند
    VD.bound = true;
    window.addEventListener('resize', vdFit);
    document.addEventListener('mouseup', () => { VD.drag = false; });
  }
}

function vdKey(e) {
  if (S.section !== 'video' || !VD.id || /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName)) return;
  if (e.code === 'Space') { e.preventDefault(); vdCmd({ cmd: 'toggle' }); }
  else if ((e.key === 'Delete' || e.key === 'Backspace') && VD.sel.size) { e.preventDefault(); vdWords(true); }
}

async function vdRun(step) {
  const r = await post('/api/video/run', { id: VD.id, step });
  if (!r.ok) return toast(r.data.error || 'نشد');
  toast(step === 'render' ? 'رندر شروع شد' : 'شروع شد'); vdRefresh(false);
}

function vdPaint(d, was) {
  const j = d.job || {};
  const box = $('#vdJob'); const line = vdJobLine(j);
  box.hidden = !line; box.innerHTML = line; box.classList.toggle('err', j.state === 'error');
  const busy = j.state === 'running';
  $('#vdAll').disabled = busy; $('#vdRender').disabled = busy || !d.words;
  if (document.activeElement !== $('#vdName') && $('#vdName').value !== d.title) $('#vdName').value = d.title;
  // پیش‌نمایش فقط وقتی نسخه‌اش عوض شده دوباره بار می‌شود
  if (d.preview && d.preview !== VD.pv) {
    VD.pv = d.preview;
    const [W, H] = VD_W[VD.kind];
    $('#vdStage').innerHTML = `<iframe id="vdFrame" src="${vdMedia(d.id, 'comp/preview.html', d.preview)}" width="${W}" height="${H}" scrolling="no" title="پیش‌نمایش"></iframe>`;
    $('#vdFrame').onload = () => { if (VD.t > 0.05) vdCmd({ cmd: 'seek', t: VD.t }); };
    vdFit();
  }
  const st = [];
  if (d.srcDur) st.push(`${vdT(d.srcDur)} ← <b>${vdT(d.outDur)}</b>`);
  if (d.words) st.push(`${faNum(d.words.length)} کلمه`);
  if (d.cut && d.cut.length) st.push(`${faNum(d.cut.length)} کلمه حذف`);
  if (d.keeps) st.push(`${faNum(d.keeps.length)} تکه`);
  $('#vdStats').innerHTML = st.join(' · ');
  const sig = JSON.stringify([d.words && d.words.length, d.cut, d.edit, d.opts, d.faces, (d.caps || []).map(c => [c.id, c.pos]), d.prevSections, d.sfx]);
  if (!was || sig !== VD.sig) { VD.sig = sig; vdCutsPanel(d); vdCapsPanel(d); vdSfxPanel(d); }
  const vsig = JSON.stringify([!!d.words, d.media, d.vis, d.sites, (d.edit || {}).visSummary, (d.edit || {}).notes, d.prevSections, (d.job || {}).state]);
  if (!was || vsig !== VD.vsig) { VD.vsig = vsig; vdVisPanel(d); }
  const ssig = JSON.stringify([!!d.words, d.sites, (d.edit || {}).sitesSummary, ((d.edit || {}).notes || {}).sites, (d.job || {}).state]);
  if (!was || ssig !== VD.ssig) { VD.ssig = ssig; vdSitesPanel(d); }
  const zsig = JSON.stringify([!!d.words, d.zooms, d.blurs, d.opts, (d.edit || {}).zoomSummary, d.prevSections, (d.job || {}).state]);
  if (d.kind === 'screen' && (!was || zsig !== VD.zsig)) { VD.zsig = zsig; vdScreenPanel(d); }
  const osig = JSON.stringify([d.finalAt, busy, d.render]);
  if (osig !== VD.osig) { VD.osig = osig; vdOutPanel(d); }
  vdPostPaint(d);
  // نتیجه‌ی «بازتولید» زیر دکمه‌ی همان بخش (۲۰۲۶-۱۰-۰۹): خطا فقط در نوار بالای صفحه بود و کاربر پایین صفحه چیزی نمی‌دید
  const now = Date.now() / 1000;
  $$('.vd-regenmsg').forEach(el => {
    const mine = j.step === 'regen' && j.section === el.dataset.sec;
    el.classList.toggle('err', mine && j.state === 'error');
    el.innerHTML = !mine ? ''
      : j.state === 'running' ? `<span class="spin"></span><span>${esc(j.msg || 'Claude دارد کار می‌کند…')} (چند دقیقه)</span>`
      : j.state === 'error' && now - (j.started || 0) < 1800 ? `<span>نشد: ${esc(j.error || 'خطای ناشناخته')} دوباره بزن.</span>`
      : j.state === 'done' && now - (j.finished || 0) < 300 ? '<span>✓ انجام شد. توضیح Claude بالای همین بخش است.</span>' : '';
  });
  const pj = (was && was.job) || {};
  if (pj.state === 'running' && pj.step === 'regen' && j.state !== 'running') toast(j.state === 'error' ? 'بازتولید نشد' : 'بازتولید انجام شد');
}

function vdFit() {
  vdCovFit();
  const st = $('#vdStage'), fr = $('#vdFrame'); if (!st || !fr) return;
  const [W, H] = VD_W[VD.kind];
  const w = st.clientWidth, s = w / W;
  fr.style.transform = `scale(${s})`; st.style.height = Math.round(H * s) + 'px';
  vdGuideLayer();
}

/* ناحیه‌هایی که رابط ریلز اینستاگرام رویشان می‌افتد (۱۰۸۰×۱۹۲۰، ۲۰۲۶)؛ فقط روی پیش‌نمایش، با درصد تا با اندازه‌ی قاب بزرگ و کوچک شود.
   pointer-events ندارد تا کشیدن زیرنویس زیرش کار کند. */
function vdGuideLayer() {
  const st = $('#vdStage'); if (!st) return;
  let g = $('#vdGuideL', st);
  if (!VD.guide || VD.kind !== 'reel') { g && g.remove(); return; }
  if (g) return;
  st.insertAdjacentHTML('beforeend', `<div id="vdGuideL" class="vd-guide">
    <i style="top:0;height:13%;left:0;right:0"><span>نوار بالای اینستاگرام</span></i>
    <i style="top:76.5%;bottom:0;left:0;right:0"><span>اسم، کپشن، ردیف صدا</span></i>
    <i class="v" style="top:52%;height:40.6%;left:88.9%;right:0"><span>لایک و کامنت</span></i>
    <b style="top:69.2%;height:5.3%;left:13.9%;right:13.9%"></b></div>`);
}

/* ---------------- پخش (postMessage با iframe) ---------------- */
function vdCmd(m) { const f = $('#vdFrame'); if (f && f.contentWindow) f.contentWindow.postMessage(m, '*'); }
function vdOnMsg(e) {
  const m = e.data || {}; if (!VD.data) return;
  if (m.hf === 'capmove') {          // زیرنویس در پیش‌نمایش کشیده شد
    const c = (VD.data.caps || []).find(x => x.id === m.id);
    if (c) vdCapPos(c.w, Math.round(m.y * 1000) / 1000);
    return;
  }
  if (m.hf !== 'time') return;
  VD.t = m.t; VD.dur = m.d || VD.data.outDur || 0; VD.paused = m.paused;
  $('#vdPlay') && ($('#vdPlay').textContent = m.paused ? '▶' : '❚❚');
  $('#vdTime') && ($('#vdTime').textContent = `${vdT(m.t)} از ${vdT(VD.dur)}`);   // «/» در راست‌به‌چپ وارونه خوانده می‌شود
  const sk = $('#vdSeek'); if (sk && document.activeElement !== sk && VD.dur) sk.value = Math.round(m.t / VD.dur * 1000);
  // کلمه و تکه‌ی زیرنویسِ در حال پخش
  const ws = VD.data.words || [];
  let cur = -1;
  for (const w of ws) { if (w.o == null) continue; if (w.o <= m.t + 0.02) cur = w.i; else break; }
  if (cur !== VD.curWord) {
    $('.vw.now') && $('.vw.now').classList.remove('now');
    const el = $(`.vw[data-i="${cur}"]`); if (el) { el.classList.add('now'); if (!m.paused) vdKeepVisible(el, $('#vdTr')); }
    VD.curWord = cur;
  }
  const cap = (VD.data.caps || []).find(c => m.t >= c.s && m.t <= c.e);
  const cid = cap ? cap.id : null;
  if (cid !== VD.curCap) {
    $('.vd-cap.now') && $('.vd-cap.now').classList.remove('now');
    const el = cid && $(`.vd-cap[data-id="${cid}"]`); if (el) { el.classList.add('now'); if (!m.paused) vdKeepVisible(el, $('#vdCapList')); }
    VD.curCap = cid;
  }
  // افکتی که همین الان پخش شد (تا حدود یک ثانیه بعدش)
  const fx = (VD.data.sfx || []).filter(c => c.at != null && c.on !== false && c.at <= m.t + 0.05 && m.t - c.at < 0.9).pop();
  const fid = fx ? fx.id : null;
  if (fid !== VD.curFx) {
    $('.vd-fx.now') && $('.vd-fx.now').classList.remove('now');
    const el = fid && $(`.vd-fx[data-sid="${fid}"]`); if (el) { el.classList.add('now'); if (!m.paused) vdKeepVisible(el, $('#vdFxList')); }
    VD.curFx = fid;
  }
}
function vdKeepVisible(el, box) {
  if (!box) return;
  const r = el.getBoundingClientRect(), b = box.getBoundingClientRect();
  if (r.top < b.top || r.bottom > b.bottom) box.scrollTop += r.top - b.top - b.height / 3;
}

/* ---------------- متن و برش ---------------- */
function vdCutsPanel(d) {
  const sec = $('#vdCuts');
  if (!d.words) {
    sec.innerHTML = `<h3>متن و برش</h3><div class="cr-dim">${(d.job || {}).state === 'running' ? 'بعد از تبدیل صدا به متن این‌جا می‌آید…' : 'هنوز متنی نیست. «⚡ ساخت کامل» را بزن.'}</div>`;
    return;
  }
  const cut = new Set(d.cut), reason = {};
  for (const c of (d.edit.cuts || [])) if (c.on !== false) for (let i = c.w0; i <= c.w1; i++) reason[i] = c.reason;
  const man = d.edit.manual || {}, emph = new Set(d.edit.emph || []), pauses = new Set(d.edit.pauses || []);
  const ws = d.words;
  // کلمه‌هایی که Claude به قبلی چسبانده (متن خالی، مثل «کسب‌وکارها» از سه تکه) جدا نشان داده نمی‌شوند
  VD.tails = {};
  let head = null;
  for (const w of ws) { if (w.w === '' && head != null) VD.tails[head].push(w.i); else { head = w.i; VD.tails[head] = []; } }
  const tr = ws.map((w, k) => {
    if (w.w === '' && k > 0) return '';
    const tl = VD.tails[w.i] || [];
    const nx = ws[k + 1 + tl.length];
    w = { ...w, e: tl.length ? ws[tl[tl.length - 1]].e : w.e };
    const cls = ['vw'];
    if (cut.has(w.i)) cls.push('cut', 'r-' + (man[w.i] === 1 ? 'manual' : (reason[w.i] || 'manual')));
    else if (man[w.i] === 0 && reason[w.i]) cls.push('kept');
    if (emph.has(w.i)) cls.push('em');
    if (VD.sel.has(w.i)) cls.push('sel');
    if (w.alt && w.alt !== 'only-ts' && w.alt !== 'no-time') cls.push('alt');
    const gap = nx ? nx.s - w.e : 0;
    const p = gap >= 0.6 ? `<i class="vp ${pauses.has(w.i) ? 'keep' : ''}" title="مکث ${vdSec(gap)} ثانیه${pauses.has(w.i) ? ' (می‌ماند)' : ' (کوتاه می‌شود)'}">·</i>` : '';
    const title = w.alt && w.alt !== 'only-ts' && w.alt !== 'no-time' ? ` title="اجرای دیگر: ${esc(w.alt)}"` : '';
    return `<span class="${cls.join(' ')}" data-i="${w.i}"${title}>${esc(w.w || w.raw)}</span>${p}`;
  }).filter(Boolean).join(' ');
  const cuts = (d.edit.cuts || []).map(c => {
    const txt = ws.slice(c.w0, c.w1 + 1).map(w => w.raw).join(' ');
    return `<label class="vd-cutrow ${c.on === false ? 'off' : ''}">
      <input type="checkbox" data-cut="${esc(c.id)}" ${c.on === false ? '' : 'checked'}>
      <span class="vd-why r-${esc(c.reason)}">${esc(VD_REASON[c.reason] || c.reason)}</span>
      <span class="vd-cuttxt" data-go="${c.w0}">«${esc(txt.length > 70 ? txt.slice(0, 70) + '…' : txt)}»</span>
      ${c.note ? `<small>${esc(c.note)}</small>` : ''}</label>`;
  }).join('');
  const notes = ((d.edit.notes || {}).cuts || []).slice(-1)[0];
  const auto = d.opts.autoCut !== false;
  sec.innerHTML = `
    <h3>متن و برش</h3>
    ${d.edit.summary ? `<p class="vd-sum">${esc(d.edit.summary)}</p>` : ''}
    ${auto ? `<div class="vd-row"><span class="cr-dim">ریتم (کوتاه کردن مکث‌ها):</span>
      ${Object.entries(VD_RHYTHM).map(([k, v]) => `<button class="btn sm ${d.opts.rhythm === k ? 'on' : ''}" data-rhythm="${k}"${k === 'tight'
        ? ' title="نفس‌ها و مکث‌های خیلی کوتاه هم بریده می‌شوند؛ ویدیو تندتر می‌شود. حرف‌ها دست نمی‌خورند."' : ''}>${v}</button>`).join('')}
      <button class="btn sm" data-autocut="0" title="هیچ چیز خودکار بریده نشود؛ فقط کلمه‌هایی که خودت حذف کنی">بدون برش خودکار</button></div>`
    : `<div class="vd-row vd-nocut"><span>برش خودکار خاموش است: سکوت و تپق بریده نمی‌شود و فقط کلمه‌هایی که خودت حذف کنی می‌روند.</span>
      <button class="btn sm primary" data-autocut="1">روشن کردن برش خودکار</button></div>`}
    <div class="vd-tools" id="vdTools"></div>
    <div class="vd-tr" id="vdTr" dir="rtl">${tr}</div>
    <p class="cr-dim vd-help">روی کلمه بزن تا پخش از همان‌جا باشد. برای حذف یک تکه‌ی کامل: <b>دوبار کلیک</b> روی یک کلمه کل جمله‌اش را انتخاب می‌کند؛ یا روی اولین کلمه بزن و با <b>Shift</b> روی آخرین کلمه بزن (یا ماوس را رویشان بکش)؛ بعد «✂ حذف» یا ⌫. خط‌خورده‌ها حذف می‌شوند؛ رنگشان دلیل را می‌گوید.</p>
    ${cuts && auto ? `<div class="vd-cutlist"><b>برش‌های Claude</b>${cuts}</div>` : ''}
    <div class="vd-regen" ${auto ? '' : 'hidden'}>
      ${notes ? `<div class="cr-dim">آخرین نظرت: «${esc(notes)}»</div>` : ''}
      <textarea id="vdCutNote" class="vd-note" placeholder="نظرت درباره‌ی برش‌ها، مثلاً «مقدمه‌ی اول را کامل حذف کن» یا «تپق‌ها را نگه دار»"></textarea>
      <div class="vd-regenmsg" data-sec="cuts"></div>
      <div class="vd-row"><button class="btn" data-regen="cuts">بازتولید برش‌ها با این نظر</button>
        ${(d.prevSections || []).includes('cuts') ? '<button class="btn" data-undo="cuts">↶ نسخه‌ی قبل</button>' : ''}</div>
    </div>`;
  vdTools();
  $$('[data-rhythm]', sec).forEach(b => b.onclick = () => vdOpt('rhythm', b.dataset.rhythm));
  $$('[data-autocut]', sec).forEach(b => b.onclick = async () => {
    const on = b.dataset.autocut === '1';
    await vdOpt('autoCut', on);
    if (on && d.edit.cuts == null) vdRegen('cuts', '');     // موقع آپلود برش خواسته نشده بود: Claude حالا پیدا می‌کند
  });
  $$('[data-cut]', sec).forEach(c => c.onchange = async () => {
    await post('/api/video/edit', { id: VD.id, op: 'cut', cutId: c.dataset.cut, on: c.checked }); vdSoon();
  });
  $$('[data-go]', sec).forEach(s => s.onclick = e => { e.preventDefault(); vdSelect([+s.dataset.go], true); });
  $$('[data-regen]', sec).forEach(b => b.onclick = () => vdRegen(b.dataset.regen, $('#vdCutNote').value));
  $$('[data-undo]', sec).forEach(b => b.onclick = () => vdUndo(b.dataset.undo));
  const box = $('#vdTr');
  box.onmousedown = e => {
    const w = e.target.closest('.vw'); if (!w) return;
    e.preventDefault();
    // دوبار کلیک: کل جمله‌ی همان کلمه، تا یک‌جا حذفش کنی (۲۰۲۶-۱۰-۰۹). کلمه‌ی کلیک اول ملاک است، نه زیر ماوس:
    // نوار ابزار با کلیک اول باز می‌شود و متن را پایین می‌برد، پس کلیک دوم روی کلمه‌ی دیگری می‌افتد.
    if (e.detail >= 2 && VD.anchor != null) {
      VD.drag = false;
      const [a, b] = vdSentence(VD.downAt);
      VD.anchor = a; return vdRange(a, b);
    }
    const i = +w.dataset.i;
    if (e.shiftKey && VD.anchor != null) return vdRange(VD.anchor, i);
    VD.anchor = VD.downAt = i; VD.drag = true; vdSelect([i], true);
  };
  box.onmouseover = e => { if (!VD.drag) return; const w = e.target.closest('.vw'); if (w) vdRange(VD.anchor, +w.dataset.i, false); };
}

/* جمله‌ی دور کلمه‌ی i: تا نقطه، علامت سؤال یا مکث (·، ≥ ۰٫۶ ثانیه) قبلی و بعدی */
function vdSentence(i) {
  const ws = VD.data.words;
  const brk = k => /[.!?؟…]$/.test((ws[k].w || ws[k].raw || '').trim()) || (ws[k + 1] && ws[k + 1].s - ws[k].e >= 0.6);
  let a = i, b = i;
  while (a > 0 && !brk(a - 1)) a--;
  while (b < ws.length - 1 && !brk(b)) b++;
  return [a, b];
}

function vdRange(a, b, seek = false) {
  const [x, y] = a < b ? [a, b] : [b, a];
  const ids = []; for (let i = x; i <= y; i++) ids.push(i);
  vdSelect(ids, seek);
}
function vdSelect(ids, seek) {
  VD.sel = new Set(ids); VD.fixing = null;
  $$('.vw.sel').forEach(x => x.classList.remove('sel'));
  ids.forEach(i => { const el = $(`.vw[data-i="${i}"]`); el && el.classList.add('sel'); });
  vdTools();
  if (seek && ids.length) {
    const ws = VD.data.words; const w = ws[ids[0]];
    const o = w && w.o != null ? w.o : (ws.slice(ids[0]).find(x => x.o != null) || {}).o;
    if (o != null) vdCmd({ cmd: 'seek', t: Math.max(0, o - 0.05) });
  }
}

function vdTools() {
  const t = $('#vdTools'); if (!t) return;
  const ids = [...VD.sel].sort((a, b) => a - b);
  if (!ids.length) { t.innerHTML = ''; t.hidden = true; return; }
  t.hidden = false;
  const d = VD.data, cut = new Set(d.cut), emph = new Set(d.edit.emph || []);
  const allCut = ids.every(i => cut.has(i)), anyCut = ids.some(i => cut.has(i));
  const w = d.words[ids[0]];
  if (VD.fixing != null) {
    t.innerHTML = `<span class="cr-dim">متن زیرنویس این کلمه:</span>
      <input id="vdFixIn" class="vd-input sm" value="${esc(w.w)}" dir="rtl">
      <button class="btn sm primary" id="vdFixOk">ذخیره</button><button class="btn sm" id="vdFixNo">انصراف</button>
      ${w.alt && w.alt !== 'only-ts' && w.alt !== 'no-time' ? `<span class="cr-dim">اجرای دیگر شنیده: «${esc(w.alt)}»</span>` : ''}`;
    const inp = $('#vdFixIn'); inp.focus(); inp.select();
    const save = async () => { await post('/api/video/edit', { id: VD.id, op: 'fix', i: w.i, text: inp.value }); VD.fixing = null; vdSoon(); };
    $('#vdFixOk').onclick = save; inp.onkeydown = e => { if (e.key === 'Enter') save(); if (e.key === 'Escape') { VD.fixing = null; vdTools(); } };
    $('#vdFixNo').onclick = () => { VD.fixing = null; vdTools(); };
    return;
  }
  const gap = ids.length === 1 && d.words[w.i + 1] ? d.words[w.i + 1].s - w.e : 0;
  const pz = new Set(d.edit.pauses || []);
  t.innerHTML = `<span class="cr-dim">${faNum(ids.length)} کلمه:</span>
    <button class="btn sm" data-act="sent" title="کل جمله (تا نقطه یا مکث قبلی و بعدی) انتخاب شود؛ دوبار کلیک روی یک کلمه هم همین کار را می‌کند">انتخاب کل جمله</button>
    ${allCut ? '' : '<button class="btn sm danger" data-act="cut">✂ حذف</button>'}
    ${anyCut ? '<button class="btn sm" data-act="keep">↩ برگرداندن</button>' : ''}
    <button class="btn sm" data-act="${ids.every(i => emph.has(i)) ? 'unem' : 'em'}">${ids.every(i => emph.has(i)) ? '☆ بدون تأکید' : '★ تأکید زرد'}</button>
    ${ids.length === 1 ? '<button class="btn sm" data-act="fix">✎ اصلاح متن</button>' : ''}
    ${gap >= 0.6 ? `<button class="btn sm" data-act="pause">${pz.has(w.i) ? 'مکث بعدش کوتاه شود' : '⏸ مکث بعدش بماند'}</button>` : ''}
    <button class="btn sm" data-act="clear">لغو انتخاب</button>
    ${d.sfxLib ? `<select class="vd-fxs" id="vdFxAdd" title="افکت صوتی روی شروع اولین کلمه‌ی انتخاب‌شده"><option value="">♪ افکت…</option>${vdFxOptions(d, '')}</select>` : ''}
    ${d.kind === 'screen' ? '<button class="btn sm" id="vdZoomAdd" title="زوم روی جایی از صفحه در همین کلمه‌ها">🔍 زوم</button><button class="btn sm" id="vdBlurAdd" title="محو یک بخش از صفحه در همین کلمه‌ها">▒ محو</button>' : ''}
    <button class="btn sm" id="vdSiteAddBtn" title="سایتی که در این کلمه‌ها درباره‌اش حرف می‌زنی؛ جمله‌اش هایلایت می‌شود">🌐 سایت…</button>
    ${(d.media || []).some(m => m.status === 'ready') ? `<select class="vd-fxs" id="vdVisAdd" title="عکس یا ویدیوی خودت روی همین کلمه‌ها"><option value="">🖼 تصویر…</option>${d.media.filter(m => m.status === 'ready').map(m => `<option value="${esc(m.id)}">${esc(m.label || m.name)}</option>`).join('')}</select>` : ''}
    <span class="vd-tpos"><span class="cr-dim">جای زیرنویس این بخش:</span>
      ${['auto', 'top', 'mid', 'bot'].map(p => `<button class="btn sm" data-pos="${p}">${VD_POS[p]}</button>`).join('')}</span>`;
  $$('[data-pos]', t).forEach(b => b.onclick = () => vdCapPos(vdExpand(ids), b.dataset.pos));
  $('#vdSiteAddBtn') && ($('#vdSiteAddBtn').onclick = () => vdSiteForm(t, vdExpand(ids)));
  $('#vdZoomAdd') && ($('#vdZoomAdd').onclick = () => vdScreenAdd('zoom', vdExpand(ids)));
  $('#vdBlurAdd') && ($('#vdBlurAdd').onclick = () => vdScreenAdd('blur', vdExpand(ids)));
  $('#vdVisAdd') && ($('#vdVisAdd').onchange = async e => {
    const mid = e.target.value; if (!mid) return;
    const ex = vdExpand(ids);
    const r = await post('/api/video/edit', { id: VD.id, op: 'vis', act: 'add', mid, w0: Math.min(...ex), w1: Math.max(...ex) });
    toast(r.ok ? 'تصویر روی این کلمه‌ها گذاشته شد' : (r.data.error || 'نشد')); vdSoon();
  });
  $('#vdFxAdd') && ($('#vdFxAdd').onchange = async e => {
    const snd = e.target.value; if (!snd) return;
    vdHear(snd);
    const r = await post('/api/video/edit', { id: VD.id, op: 'sfx', act: 'add', w: ids[0], snd });
    toast(r.ok ? `افکت «${d.sfxLib[snd].fa}» اضافه شد` : (r.data.error || 'نشد')); vdSoon();
  });
  $$('[data-act]', t).forEach(b => b.onclick = async () => {
    const a = b.dataset.act;
    if (a === 'cut') return vdWords(true);
    if (a === 'keep') return vdWords(false);
    if (a === 'clear') { VD.sel = new Set(); $$('.vw.sel').forEach(x => x.classList.remove('sel')); return vdTools(); }
    if (a === 'sent') { VD.anchor = vdSentence(ids[0])[0]; return vdRange(VD.anchor, vdSentence(ids[ids.length - 1])[1]); }
    if (a === 'fix') { VD.fixing = w.i; return vdTools(); }
    if (a === 'em' || a === 'unem') { await post('/api/video/edit', { id: VD.id, op: 'emph', ids: vdExpand(ids), on: a === 'em' }); return vdSoon(); }
    if (a === 'pause') { await post('/api/video/edit', { id: VD.id, op: 'pause', i: w.i, on: !pz.has(w.i) }); return vdSoon(); }
  });
}

const vdExpand = ids => [...new Set(ids.flatMap(i => [i, ...((VD.tails || {})[i] || [])]))];

async function vdWords(cut) {
  const ids = vdExpand([...VD.sel]); if (!ids.length) return;
  const r = await post('/api/video/edit', { id: VD.id, op: 'words', ids, cut });
  if (!r.ok) return toast(r.data.error || 'نشد');
  toast(cut ? 'حذف شد؛ پیش‌نمایش به‌روز می‌شود' : 'برگشت'); vdSoon();
}
async function vdCapPos(ids, pos) {
  if (!ids.length) return;
  const r = await post('/api/video/edit', { id: VD.id, op: 'cappos', ids, pos });
  if (!r.ok) return toast(r.data.error || 'نشد');
  toast(pos === 'auto' ? 'جای زیرنویس دوباره خودکار شد' : typeof pos === 'number' ? 'جای این تکه ذخیره شد' : `زیرنویس این بخش: ${VD_POS[pos]}`);
  vdSoon();
}
async function vdOpt(key, value) {
  const r = await post('/api/video/edit', { id: VD.id, op: 'opts', key, value });
  if (!r.ok) return toast(r.data.error || 'نشد');
  vdSoon();
}
async function vdRegen(section, comment) {
  const r = await post('/api/video/regen', { id: VD.id, section, comment: (comment || '').trim() });
  if (!r.ok) return toast(r.data.error || 'نشد');
  toast('Claude دارد از نو می‌سازد…'); vdRefresh(false);
}
async function vdUndo(section) {
  const r = await post('/api/video/undo', { id: VD.id, section });
  toast(r.ok ? 'نسخه‌ی قبل برگشت' : (r.data.error || 'نشد')); vdSoon();
}
function vdSoon() { clearTimeout(VD.poll); VD.poll = setTimeout(() => vdRefresh(false), 250); }

/* ---------------- زیرنویس ---------------- */
function vdCapsPanel(d) {
  const sec = $('#vdCaps');
  if (!d.words) { sec.innerHTML = '<h3>زیرنویس</h3><div class="cr-dim">بعد از متن.</div>'; return; }
  const o = d.opts, styles = d.styles || {};
  const notes = ((d.edit.notes || {}).fix || []).slice(-1)[0];
  const fu = new Set(d.edit.fixUser || []);
  // ساخت دوباره‌ی پنل جای اسکرول فهرست و نظر نیمه‌نوشته را نگه می‌دارد
  const keep = { top: ($('#vdCapList') || {}).scrollTop || 0, note: ($('#vdCapNote') || {}).value || '' };
  sec.innerHTML = `
    <h3>زیرنویس</h3>
    <div class="vd-row vd-styles">${Object.entries(styles).map(([k, v]) =>
      `<button class="btn sm vd-style s-${k} ${o.style === k ? 'on' : ''}" data-style="${k}">${esc(v)}</button>`).join('')}</div>
    <div class="vd-row"><span class="cr-dim">اندازه:</span>
      ${Object.entries(d.sizes || { s: 'کوچک', m: 'معمولی', l: 'بزرگ' }).map(([k, v]) =>
        `<button class="btn sm ${(o.size || 'm') === k ? 'on' : ''}" data-size="${k}">${esc(v)}${k === 'm' ? ' (پیشنهادی)' : ''}</button>`).join('')}
      <button class="btn sm" id="vdStyleDef" title="ویدیوهای بعدی با همین سبک و اندازه شروع شوند">پیش‌فرض من</button></div>
    <div class="vd-row vd-toggles">
      <label><input type="checkbox" data-opt="captions" ${o.captions ? 'checked' : ''}> زیرنویس</label>
      <label title="وقتی زیرنویس از قبل روی خود ویدیو سوخته است"><input type="checkbox" data-opt="capsOver" ${o.capsOver ? 'checked' : ''}> فقط روی تصویرهای تمام‌صفحه</label>
      ${d.kind === 'reel' ? `<label><input type="checkbox" data-opt="punch" ${o.punch ? 'checked' : ''}> زوم ملایم روی برش‌ها</label>` : ''}
      <label><input type="checkbox" data-opt="voiceClean" ${o.voiceClean ? 'checked' : ''}> صدای تمیز (حذف نویز و یکدست کردن)</label>
    </div>
    <div class="vd-caplist" id="vdCapList">${(d.caps || []).map(c => {
      const moved = c.auto && c.pos !== 'bot';
      return `<div class="vd-cap ${c.auto ? '' : 'man'}" data-id="${c.id}" data-s="${c.s}"><span class="vd-ct">${vdT(c.s)}</span>
        <span class="vd-ctx" dir="rtl" data-capedit="${c.id}" title="برای اصلاح متن کلیک کن">${esc(c.text)}${c.w.some(i => fu.has(String(i)))
          ? '<span class="vd-mine" title="متن این تکه را خودت اصلاح کرده‌ای؛ «بازتولید» عوضش نمی‌کند"> ✎</span>' : ''}</span>
        <select class="vd-pos ${moved ? 'moved' : ''}" data-cap="${c.id}" title="جای این تکه">
          <option value="auto" ${c.auto ? 'selected' : ''}>${c.auto ? `خودکار: ${vdPosName(c.pos)}` : 'خودکار'}</option>
          ${['top', 'mid', 'bot'].map(p => `<option value="${p}" ${!c.auto && c.pos === p ? 'selected' : ''}>${VD_POS[p]}</option>`).join('')}
          ${!c.auto && typeof c.pos === 'number' ? '<option value="custom" selected>دستی (کشیده)</option>' : ''}
        </select></div>`;
    }).join('') || '<div class="cr-dim">زیرنویس خاموش است.</div>'}</div>
    ${d.kind === 'reel' ? `<p class="cr-dim vd-help">زیرنویس همیشه یک خط است و طبق محدوده‌ی امن ریلز چیده می‌شود: پایینش حدود ۴۹۰ پیکسل بالاتر از لبه‌ی پایین (جای اسم، کپشن و ردیف صدا)،
      پهنایش حداکثر ۷۸۰ پیکسل وسط‌چین تا به ستون لایک و کامنت سمت راست نرسد، و زیر ۲۷۰ پیکسل بالا. اندازه‌ی «معمولی» ۶۸ پیکسل است (بهترین بازه‌ی ریلز ۶۰ تا ۷۵).
      «راهنمای اینستاگرام» زیر پیش‌نمایش این ناحیه‌ها را نشان می‌دهد.</p>` : ''}
    <p class="cr-dim vd-help">${d.kind === 'reel' ? (d.faces
      ? 'زیرنویس خودکار از روی صورتت کنار می‌رود (جای صورت ۴ بار در ثانیه دیده می‌شود). برای عوض کردن جای یک تکه، از فهرست انتخاب کن یا در پیش‌نمایش بگیرش و بکش؛ برای یک بخش کامل (مثلاً از جایی که زاویه عوض شده)، کلمه‌هایش را در «متن و برش» انتخاب کن.'
      : 'جای صورت هنوز پیدا نشده؛ «⚡ ساخت کامل» را بزن تا زیرنویس خودکار از روی صورت کنار برود.') : 'جای هر تکه را از فهرست عوض کن یا در پیش‌نمایش بکش.'}
      برای اصلاح متن، روی متن هر تکه کلیک کن، درستش کن و Enter بزن (Esc یعنی انصراف). اصلاح‌های تو با ✎ نشان داده می‌شوند و «بازتولید» عوضشان نمی‌کند. کلمه‌های ★ زرد می‌شوند.
      ${Object.keys(d.edit.capPos || {}).length ? '<button class="btn sm" id="vdPosReset">همه‌ی جاها خودکار شوند</button>' : ''}</p>
    <div class="vd-regen">
      ${notes ? `<div class="cr-dim">آخرین نظرت: «${esc(notes)}»</div>` : ''}
      <textarea id="vdCapNote" class="vd-note" placeholder="نظرت درباره‌ی متن زیرنویس، مثلاً «اسم‌های انگلیسی را فارسی بنویس» یا «تکه‌ها کوتاه‌تر»"></textarea>
      <div class="vd-regenmsg" data-sec="captions"></div>
      <div class="vd-row"><button class="btn" data-regen="captions">بازتولید متن زیرنویس</button>
        ${(d.prevSections || []).some(s => s === 'fix' || s === 'emph') ? '<button class="btn" data-undo="captions">↶ نسخه‌ی قبل</button>' : ''}</div>
    </div>`;
  $$('[data-style]', sec).forEach(b => b.onclick = () => vdOpt('style', b.dataset.style));
  $$('[data-size]', sec).forEach(b => b.onclick = () => vdOpt('size', b.dataset.size));
  $('#vdStyleDef').onclick = async () => {
    const r = await post('/api/video/style-default', { style: o.style, size: o.size || 'm' });
    toast(r.ok ? `«${styles[o.style]}»، اندازه‌ی ${(d.sizes || {})[o.size || 'm'] || ''} پیش‌فرض شد` : 'نشد');
  };
  $$('[data-opt]', sec).forEach(c => c.onchange = () => vdOpt(c.dataset.opt, c.checked));
  $$('.vd-cap', sec).forEach(c => c.onclick = e => {
    if (e.target.closest('select, .vd-capedit')) return;
    vdCmd({ cmd: 'seek', t: +c.dataset.s + 0.01 });
    if (e.target.closest('[data-capedit]')) { vdCmd({ cmd: 'pause' }); vdCapEdit(d.caps.find(x => x.id === c.dataset.id)); }
  });
  $('#vdCapList').scrollTop = keep.top;
  $('#vdCapNote').value = keep.note;
  if (VD.capEdit) {                  // پنل وسط نوشتن از نو ساخته شد: همان تکه با همان پیش‌نویس دوباره باز می‌شود
    const c = (d.caps || []).find(x => x.w.join(',') === VD.capEdit.w);
    c ? vdCapEdit(c, VD.capEdit.draft) : (VD.capEdit = null);
  }
  $$('.vd-pos', sec).forEach(s => s.onchange = () => {
    const c = d.caps.find(x => x.id === s.dataset.cap);
    if (c && s.value !== 'custom') vdCapPos(c.w, s.value);
  });
  $('#vdPosReset') && ($('#vdPosReset').onclick = () => vdCapPos(Object.keys(d.edit.capPos || {}).map(Number), 'auto'));
  $$('[data-regen]', sec).forEach(b => b.onclick = () => vdRegen(b.dataset.regen, $('#vdCapNote').value));
  $$('[data-undo]', sec).forEach(b => b.onclick = () => vdUndo(b.dataset.undo));
}

/* ویرایش متن یک تکه‌ی زیرنویس در خود فهرست؛ سرور متن تازه را روی همان کلمه‌ها پخش می‌کند (op: capfix) */
function vdCapEdit(c, draft) {
  if (!c) return;
  if ($('.vd-capedit')) { VD.capEdit = null; vdCapsPanel(VD.data); }      // فقط یک تکه در هر لحظه باز است
  const sp = $(`.vd-cap[data-id="${c.id}"] [data-capedit]`);
  if (!sp) return;
  VD.capEdit = { w: c.w.join(','), draft: draft != null ? draft : c.text };
  const ed = document.createElement('span');
  ed.className = 'vd-ctx vd-capedit';
  ed.innerHTML = `<input class="vd-input sm vd-capin" dir="rtl" value="${esc(VD.capEdit.draft)}">
    <button class="btn sm primary" data-capok>ذخیره</button><button class="btn sm" data-capno>انصراف</button>`;
  sp.replaceWith(ed);
  const inp = $('.vd-capin', ed);
  inp.focus(); inp.setSelectionRange(inp.value.length, inp.value.length);
  inp.oninput = () => { VD.capEdit.draft = inp.value; };
  const close = () => { VD.capEdit = null; ed.replaceWith(sp); };
  let busy = false;
  const save = async () => {
    const text = inp.value.trim();
    if (busy) return;
    if (!text) return toast('متن خالی است. برای حذف این حرف از «✂ حذف» در «متن و برش» استفاده کن.');
    if (text === c.text.trim()) return close();
    busy = true;
    const r = await post('/api/video/edit', { id: VD.id, op: 'capfix', ids: c.w, text });
    busy = false;
    if (!r.ok) return toast(r.data.error || 'نشد');
    VD.capEdit = null;
    toast('متن زیرنویس ذخیره شد'); vdSoon();
  };
  inp.onkeydown = e => {
    if (e.key === 'Enter' && !e.isComposing) { e.preventDefault(); save(); }
    else if (e.key === 'Escape') close();
  };
  $('[data-capok]', ed).onclick = save;
  $('[data-capno]', ed).onclick = close;
}

/* ---------------- عکس، ویدیو و گرافیک (فاز ۳) ----------------
   فایل‌های خود کاربر با توضیح زیرشان (POST /api/video/upload?asset=1 و /api/video/media) و چیدمان روی ویدیو (edit.json → vis). */
const VD_MST = { upload: 'در حال آپلود…', queued: 'در صف…', analyze: 'Claude دارد می‌خواند…', process: 'محو کردن…', error: 'خطا' };
const VD_GF = { name: 'اسم', domain: 'سایت (دامنه)', price: 'قیمت', cur: 'واحد', per: 'دوره', stamp: 'مُهر', strike: 'خط بخورد',
  value: 'عدد', label: 'عنوان', text: 'متن', by: 'گوینده', n: 'شماره', of: 'از چند' };
const VD_GFF = { logo: ['name', 'domain', 'price', 'cur', 'per', 'stamp', 'strike'], price: ['value', 'cur', 'per', 'strike'],
  counter: ['n', 'of'], total: ['value', 'cur', 'label'], quote: ['text', 'by'] };
const vdMBusy = m => ['upload', 'queued', 'analyze', 'process'].includes(m.status);

function vdVisPanel(d) {
  const sec = $('#vdVis'); if (!sec) return;
  if (!d.words) { sec.innerHTML = '<h3>عکس، ویدیو و گرافیک</h3><div class="cr-dim">بعد از متن.</div>'; return; }
  VD.mnote = VD.mnote || {}; VD.ups = VD.ups || [];
  const tp = d.visTpls || {}, media = d.media || [], vis = d.vis || [];
  const ae = document.activeElement, focusMid = ae && ae.matches && ae.matches('[data-mnote]') ? ae.closest('.vd-mc').dataset.mid : null;
  const card = m => {
    const busy = vdMBusy(m), bx = m.boxes || {};
    const tag = m.type === 'video' ? `ویدیو ${vdT(m.dur || 0)}` : m.src === 'pdf' ? (m.pages > 1 ? `PDF، صفحه‌ی اول از ${faNum(m.pages)}` : 'PDF') : 'عکس';
    const marks = [...(bx.blur || []).map(b => ['b', b]), ...(bx.hl || []).map(b => ['h', b]), ...(bx.focus ? [['f', bx.focus]] : [])]
      .map(([k, b]) => `<i class="vd-mk ${k}" style="left:${b[0] * 100}%;top:${b[1] * 100}%;width:${b[2] * 100}%;height:${b[3] * 100}%"></i>`).join('');
    const note = VD.mnote[m.id] != null ? VD.mnote[m.id] : (m.note || '');
    return `<div class="vd-mc ${m.status === 'error' ? 'err' : ''}" data-mid="${esc(m.id)}">
      <div class="vd-mth" data-mbox title="محو و هایلایت">${m.v ? `<div class="vd-mimg"><img src="${vdMedia(d.id, `media/${m.id}/thumb.jpg`, m.v)}" alt="">${marks}</div>` : '<span class="spin"></span>'}
        <span class="vd-mtag">${esc(tag)}</span>
        ${busy ? `<span class="vd-mst"><span class="spin"></span>${esc(m.step || VD_MST[m.status] || '')}</span>` : ''}</div>
      <div class="vd-mbody">
        <b dir="auto">${esc(m.label || m.name || '')}</b>
        ${m.desc ? `<small>${esc(m.desc)}</small>` : ''}
        ${m.status === 'ready' ? `<small class="vd-mbx">محو: ${faNum((bx.blur || []).length)} · هایلایت: ${faNum((bx.hl || []).length)}${m.boxesBy === 'user' ? ' (دستی)' : ''}${m.fallback ? ' · Claude جواب نداد؛ محو با الگوهای ساده، خودت هم نگاه کن' : ''}</small>` : ''}
        ${m.status === 'error' ? `<small class="vd-merr">${esc(m.err || 'خطا')}</small>` : ''}
        <textarea class="vd-mnote" data-mnote rows="3" placeholder="این چیست و چطور بیاید؟ مثلاً «فاکتور ManyChat؛ ایمیلم را محو کن؛ وقتی ۱۷۳ دلار را می‌گویم نشانش بده»">${esc(note)}</textarea>
        <div class="vd-row"><button class="btn sm" data-msave>ذخیره‌ی توضیح</button>
          <button class="btn sm" data-mbox ${m.v ? '' : 'disabled'}>محو و هایلایت</button>
          ${m.status === 'error' ? '<button class="btn sm" data-mretry>دوباره</button>' : ''}
          <button class="btn sm" data-mdel title="حذف">${VD.mdel === m.id ? 'مطمئنی؟' : '🗑'}</button></div>
      </div></div>`;
  };
  const sel = (map, cur, attr, title) => `<select class="vd-fxg" ${attr} title="${title}">${Object.entries(map || {}).map(([k, t]) =>
    `<option value="${k}" ${cur === k ? 'selected' : ''}>${esc(t)}</option>`).join('')}</select>`;
  const row = v => {
    const off = v.on === false, m = v.kind === 'media' ? media.find(x => x.id === v.mid) : null;
    const st = v.kind === 'site' ? (d.sites || []).find(x => x.id === v.sid) : null;
    const thumb = m && m.v ? `<img src="${vdMedia(d.id, `media/${m.id}/thumb.jpg`, m.v)}" alt="">`
      : st && st.v ? `<img src="${vdMedia(d.id, `sites/${st.id}/${st.mode}/thumb.jpg`, st.v)}" alt="">`
      : `<span class="vd-gico">${{ logo: '◎', counter: '#', quote: '❝', total: '∑' }[v.tpl] || (v.kind === 'site' ? '🌐' : '$')}</span>`;
    const skip = v.skip === 'cut' ? 'کلمه‌هایش حذف شده' : v.skip === 'media' ? 'فایلش آماده نیست' : v.skip === 'site' ? 'عکس سایت هنوز آماده نیست' : '';
    const keys = v.kind === 'site' ? Object.keys(tp.site || {}) : v.kind === 'media' ? (m && m.type === 'video' ? (tp.video || []) : Object.keys(tp.media || {})) : [];
    const tpls = keys.length ? `<select class="vd-fxs" data-vtpl title="قالب">${keys.map(k => `<option value="${k}" ${v.tpl === k ? 'selected' : ''}>${esc((tp.media || {})[k] || (tp.site || {})[k] || k)}</option>`).join('')}</select>` : '';
    const fields = VD.vedit === v.id && v.kind === 'gfx' ? `<div class="vd-gf">${(VD_GFF[v.tpl] || []).map(k => k === 'strike'
      ? `<label><input type="checkbox" data-gf="${k}" ${(v.data || {}).strike ? 'checked' : ''}> ${VD_GF[k]}</label>`
      : `<label>${VD_GF[k]}<input class="vd-input sm" data-gf="${k}" value="${esc(String((v.data || {})[k] ?? ''))}" dir="${k === 'domain' ? 'ltr' : 'auto'}"></label>`).join('')}
      <button class="btn sm primary" data-gfsave>ذخیره</button></div>` : '';
    const sub = [v.kind === 'gfx' ? (tp.gfx || {})[v.tpl] || v.tpl : '', skip || v.why || ''].filter(Boolean).join(' · ');
    return `<div class="vd-ov ${off || v.skip ? 'off' : ''}" data-oid="${esc(v.id)}">
      <input type="checkbox" data-von ${off ? '' : 'checked'} ${v.skip ? 'disabled' : ''} title="روشن/خاموش">
      <span class="vd-ct">${v.s != null ? vdT(v.s) : '—'}</span>
      <span class="vd-ovth">${thumb}</span>
      <span class="vd-ovt" data-vgo><b dir="auto">${esc(v.label || '')}</b>${sub ? `<small>${esc(sub)}</small>` : ''}</span>
      ${tpls}
      ${['counter', 'full', 'top', 'scene'].includes(v.tpl) ? '' : sel(v.kind === 'site' ? (tp.sitePos || tp.pos) : tp.pos, v.pos || 'auto', 'data-vpos', 'جا')
        + (v.pos === 'scene' ? '' : sel(tp.size, v.size || 'm', 'data-vsize', 'اندازه'))}
      ${v.kind === 'gfx' ? '<button class="btn sm" data-vedit title="ویرایش متن">✎</button>' : ''}
      <button class="btn sm" data-vdel title="حذف">✕</button>${fields}</div>`;
  };
  const notes = ((d.edit.notes || {}).vis || []).slice(-1)[0];
  const running = (d.job || {}).state === 'running', pending = media.some(vdMBusy);
  sec.innerHTML = `
    <h3>عکس، ویدیو و گرافیک</h3>
    ${d.edit.visSummary ? `<p class="vd-sum">${esc(d.edit.visSummary)}</p>` : ''}
    <label class="vd-drop vd-mdrop" id="vdMDrop"><input type="file" id="vdMFile" multiple accept="image/*,video/*,.pdf,.heic,.heif" hidden>
      <b>عکس، اسکرین‌شات، فاکتور (PDF) یا ویدیوی خودت را این‌جا بکش</b>
      <span>زیر هر کدام بنویس چیست و چطور بیاید. ایمیل، آدرس و شماره‌ی کارت خودکار محو می‌شوند؛ با «محو و هایلایت» خودت هم کادر بکش.</span></label>
    <div id="vdMUp" class="vd-mup"></div>
    ${media.length ? `<div class="vd-mgrid">${media.map(card).join('')}</div>` : ''}
    <div class="vd-regen">
      ${notes ? `<div class="cr-dim">آخرین نظرت: «${esc(notes)}»</div>` : ''}
      <textarea id="vdVisNote" class="vd-note" placeholder="نظرت درباره‌ی چیدمان، مثلاً «لوگوها بزرگ‌تر» یا «فاکتور Canva را وقتی می‌گویم ۱۹ دلار نشان بده»"></textarea>
      <div class="vd-row"><button class="btn primary" data-regen="vis" ${running ? 'disabled' : ''}>${vis.some(v => v.src !== 'user') ? 'چیدن دوباره با Claude' : 'چیدن عکس‌ها و گرافیک با Claude'}</button>
        ${(d.prevSections || []).includes('vis') ? '<button class="btn" data-undo="vis">↶ نسخه‌ی قبل</button>' : ''}
        ${pending ? '<span class="cr-dim">صبر کن تحلیل فایل‌ها تمام شود، بعد بچین.</span>' : ''}</div>
    </div>
    <div class="vd-vislist" id="vdVisList">${vis.map(row).join('') || '<div class="cr-dim">هنوز تصویری روی ویدیو نیست.</div>'}</div>
    <p class="cr-dim vd-help">Claude عکس‌های تو را با توضیحت سر لحظه‌ی خودش می‌گذارد و برای اسم سرویس‌ها، قیمت‌ها، فهرست‌ها و نقل‌قول‌ها گرافیک می‌سازد (لوگو از سایت خود سرویس). روی صورت و زیرنویس نمی‌افتند و افکت ورود دارند.
      برای گذاشتن دستی: در «متن و برش» کلمه‌ها را انتخاب کن و از «🖼 تصویر…» فایل را بردار. روی هر ردیف بزن تا پیش‌نمایش از همان‌جا پخش شود.</p>`;
  vdUpRows();
  const drop = $('#vdMDrop'), file = $('#vdMFile');
  file.onchange = () => { if (file.files.length) vdMUpload([...file.files]); file.value = ''; };
  drop.ondragover = e => { e.preventDefault(); drop.classList.add('over'); };
  drop.ondragleave = () => drop.classList.remove('over');
  drop.ondrop = e => { e.preventDefault(); drop.classList.remove('over'); if (e.dataTransfer.files.length) vdMUpload([...e.dataTransfer.files]); };
  $$('.vd-mc', sec).forEach(c => {
    const mid = c.dataset.mid, m = media.find(x => x.id === mid), ta = $('[data-mnote]', c);
    ta.oninput = () => { VD.mnote[mid] = ta.value; };
    const save = async () => {
      if (VD.mnote[mid] == null || VD.mnote[mid] === (m.note || '')) { delete VD.mnote[mid]; return; }
      const r = await post('/api/video/media', { id: VD.id, mid, act: 'note', note: VD.mnote[mid] });
      if (!r.ok) return toast(r.data.error || 'نشد');
      delete VD.mnote[mid]; toast('توضیح ذخیره شد؛ Claude دوباره می‌خواندش'); vdSoon();
    };
    $('[data-msave]', c).onclick = save;
    ta.onblur = () => setTimeout(save, 150);
    $$('[data-mbox]', c).forEach(b => b.onclick = () => m.v && vdBoxEditor(m));
    $('[data-mretry]', c) && ($('[data-mretry]', c).onclick = async () => { await post('/api/video/media', { id: VD.id, mid, act: 'retry' }); vdSoon(); });
    $('[data-mdel]', c).onclick = async e => {
      if (VD.mdel !== mid) { VD.mdel = mid; e.target.textContent = 'مطمئنی؟'; return; }
      VD.mdel = null;
      const r = await post('/api/video/media', { id: VD.id, mid, act: 'del' });
      toast(r.ok ? 'حذف شد' : (r.data.error || 'نشد')); vdSoon();
    };
  });
  if (focusMid) { const ta = $(`.vd-mc[data-mid="${focusMid}"] [data-mnote]`, sec); if (ta) { ta.focus(); ta.selectionStart = ta.selectionEnd = ta.value.length; } }
  $$('.vd-ov', sec).forEach(r => {
    const oid = r.dataset.oid, v = vis.find(x => x.id === oid);
    $('[data-von]', r).onchange = e => vdVis(oid, { act: 'on', on: e.target.checked });
    $('[data-vtpl]', r) && ($('[data-vtpl]', r).onchange = e => vdVis(oid, { act: 'tpl', tpl: e.target.value }));
    $('[data-vpos]', r) && ($('[data-vpos]', r).onchange = e => vdVis(oid, { act: 'pos', pos: e.target.value }));
    $('[data-vsize]', r) && ($('[data-vsize]', r).onchange = e => vdVis(oid, { act: 'size', size: e.target.value }));
    $('[data-vdel]', r).onclick = () => vdVis(oid, { act: 'del' }, 'حذف شد');
    $('[data-vgo]', r).onclick = () => { if (v && v.s != null) { vdCmd({ cmd: 'seek', t: Math.max(0, v.s - 0.6) }); vdCmd({ cmd: 'play' }); } };
    $('[data-vedit]', r) && ($('[data-vedit]', r).onclick = () => { VD.vedit = VD.vedit === oid ? null : oid; vdVisPanel(VD.data); });
    $('[data-gfsave]', r) && ($('[data-gfsave]', r).onclick = () => {
      const data = {}; $$('[data-gf]', r).forEach(i => { data[i.dataset.gf] = i.type === 'checkbox' ? i.checked : i.value; });
      VD.vedit = null; vdVis(oid, { act: 'data', data }, 'ذخیره شد');
    });
  });
  $$('[data-regen]', sec).forEach(b => b.onclick = () => vdRegen('vis', $('#vdVisNote').value));
  $$('[data-undo]', sec).forEach(b => b.onclick = () => vdUndo('vis'));
}

async function vdVis(oid, body, msg) {
  const r = await post('/api/video/edit', { id: VD.id, op: 'vis', oid, ...body });
  if (!r.ok) return toast(r.data.error || 'نشد');
  msg && toast(msg); vdSoon();
}

/* آپلود چند فایل، یکی‌یکی؛ وضعیت در VD.ups تا با ساخته‌شدن دوباره‌ی بخش گم نشود */
function vdUpRows() {
  const box = $('#vdMUp'); if (!box) return;
  box.innerHTML = (VD.ups || []).map(u => `<div class="vd-mupr"><span class="spin"></span><span>${esc(u.name)} — ${faNum(u.pct)}٪</span>
    <i class="vd-bar"><i style="width:${u.pct}%"></i></i></div>`).join('');
}
async function vdMUpload(files) {
  const ok = /\.(jpe?g|png|webp|heic|heif|gif|tiff?|bmp|pdf|mp4|mov|m4v|webm)$/i;
  for (const f of files) {
    if (!ok.test(f.name)) { toast(`«${f.name}» پشتیبانی نمی‌شود`); continue; }
    const u = { name: f.name, pct: 0 }; VD.ups.push(u); vdUpRows();
    await new Promise(res => {
      const xhr = new XMLHttpRequest();
      xhr.open('POST', `/api/video/upload?id=${encodeURIComponent(VD.id)}&name=${encodeURIComponent(f.name)}&asset=1`);
      xhr.upload.onprogress = e => { if (e.lengthComputable) { u.pct = Math.round(e.loaded / e.total * 100); vdUpRows(); } };
      const done = msg => { VD.ups = VD.ups.filter(x => x !== u); vdUpRows(); if (msg) toast(msg); vdSoon(); res(); };
      xhr.onload = () => { let m = ''; if (xhr.status !== 200) { m = 'آپلود نشد'; try { m = JSON.parse(xhr.responseText).error || m; } catch {} } done(m); };
      xhr.onerror = () => done('اتصال قطع شد؛ دوباره امتحان کن.');
      xhr.send(f);
    });
  }
}

/* پنجره‌ی محو و هایلایت: کادر کشیدن روی تصویر (کسری از عرض و ارتفاع)، زدن روی کادر = پاک کردن */
function vdBoxEditor(m) {
  const d = VD.data, bx = JSON.parse(JSON.stringify(m.boxes || { blur: [], hl: [], focus: null }));
  bx.blur = bx.blur || []; bx.hl = bx.hl || [];
  let mode = 'blur', drag = null;
  const ov = document.createElement('div'); ov.className = 'vd-modal';
  ov.innerHTML = `<div class="vd-mdl" role="dialog" aria-label="محو و هایلایت">
    <div class="vd-row"><b dir="auto">${esc(m.label || m.name || '')}</b><span class="grow"></span>
      <button class="btn sm on" data-bm="blur">محو</button><button class="btn sm" data-bm="hl">هایلایت</button><button class="btn sm" data-bm="focus">زوم</button></div>
    <p class="cr-dim vd-help">روی تصویر بکش تا کادر تازه بسازی؛ روی هر کادر بزن تا پاک شود. قرمز: محو. زرد: هایلایت. آبی: جایی که ویدیو رویش زوم می‌کند.${m.type === 'video' ? ' برای ویدیو، محو روی کل آن ثابت است.' : ''}</p>
    <div class="vd-bxw"><img src="${vdMedia(d.id, `media/${m.id}/view.jpg`, m.v)}" draggable="false" alt=""><div class="vd-bxl"></div></div>
    <div class="vd-row"><button class="btn primary" data-bsave>ذخیره</button><button class="btn" data-breset>برگشت به پیشنهاد Claude</button>
      <span class="grow"></span><button class="btn" data-bno>انصراف</button></div></div>`;
  document.body.appendChild(ov);
  const L = $('.vd-bxl', ov);
  const pos = b => `left:${b[0] * 100}%;top:${b[1] * 100}%;width:${b[2] * 100}%;height:${b[3] * 100}%`;
  const draw = () => {
    const all = [...bx.blur.map((b, k) => ['blur', k, b]), ...bx.hl.map((b, k) => ['hl', k, b]), ...(bx.focus ? [['focus', 0, bx.focus]] : [])];
    L.innerHTML = all.map(([t, k, b]) => `<i class="vd-bx ${t}" data-t="${t}" data-k="${k}" style="${pos(b)}"></i>`).join('')
      + (drag ? `<i class="vd-bx ${mode} draft" style="${pos(drag.b)}"></i>` : '');
  };
  const pt = e => { const r = L.getBoundingClientRect(); return [Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)), Math.min(1, Math.max(0, (e.clientY - r.top) / r.height))]; };
  L.onpointerdown = e => {
    const hit = e.target.closest('.vd-bx:not(.draft)');
    if (hit) { const t = hit.dataset.t; if (t === 'focus') bx.focus = null; else bx[t].splice(+hit.dataset.k, 1); draw(); return; }
    e.preventDefault(); const p = pt(e); drag = { p, b: [p[0], p[1], 0, 0] };
    try { L.setPointerCapture(e.pointerId); } catch (_) {}
    draw();
  };
  L.onpointermove = e => {
    if (!drag) return; const p = pt(e);
    drag.b = [Math.min(p[0], drag.p[0]), Math.min(p[1], drag.p[1]), Math.abs(p[0] - drag.p[0]), Math.abs(p[1] - drag.p[1])]; draw();
  };
  L.onpointerup = () => {
    if (!drag) return; const b = drag.b.map(x => Math.round(x * 10000) / 10000); drag = null;
    if (b[2] > 0.008 && b[3] > 0.006) { if (mode === 'focus') bx.focus = b; else bx[mode].push(b); }
    draw();
  };
  $$('[data-bm]', ov).forEach(b => b.onclick = () => { mode = b.dataset.bm; $$('[data-bm]', ov).forEach(x => x.classList.toggle('on', x === b)); });
  const esc_ = e => { if (e.key === 'Escape') close(); };
  const close = () => { ov.remove(); document.removeEventListener('keydown', esc_); };
  document.addEventListener('keydown', esc_);
  $('[data-bno]', ov).onclick = close;
  ov.onclick = e => { if (e.target === ov) close(); };
  $('[data-bsave]', ov).onclick = async () => {
    const r = await post('/api/video/media', { id: VD.id, mid: m.id, act: 'boxes', boxes: bx });
    toast(r.ok ? 'ذخیره شد؛ محوها دوباره ساخته می‌شوند' : (r.data.error || 'نشد')); if (r.ok) { close(); vdSoon(); }
  };
  $('[data-breset]', ov).onclick = async () => {
    const r = await post('/api/video/media', { id: VD.id, mid: m.id, act: 'reset' });
    toast(r.ok ? 'Claude دوباره پیشنهاد می‌دهد' : (r.data.error || 'نشد')); if (r.ok) { close(); vdSoon(); }
  };
  draw();
}
/* ---------------- سایت و هایلایت (فاز ۴) ----------------
   منبع‌هایی که گوینده درباره‌شان حرف می‌زند (edit.json → sites): Claude با وب پیدا می‌کند یا کاربر نشانی می‌دهد؛ Chrome عکس می‌گیرد
   و جمله را در صفحه پیدا می‌کند (POST /api/video/site، اسکرین‌شات خود کاربر با /api/video/upload?site=). قاب‌ها در فهرست تصویرها. */
const VD_SST = { queued: 'در صف…', capturing: 'در حال باز کردن سایت و عکس گرفتن…', upload: 'در حال خواندن اسکرین‌شات…',
  nomatch: 'جمله در صفحه پیدا نشد', blocked: 'سایت اجازه‌ی عکس گرفتن نداد', error: 'خطا' };
const VD_SVIA = { firecrawl: 'عکس با Firecrawl (۱ اعتبار)', upload: 'اسکرین‌شات خودت' };
const vdSBusy = s => ['queued', 'capturing', 'upload'].includes(s.status);

function vdSitesPanel(d) {
  const sec = $('#vdSites'); if (!sec) return;
  if (!d.words) { sec.innerHTML = '<h3>سایت و هایلایت</h3><div class="cr-dim">بعد از متن.</div>'; return; }
  VD.sdraft = VD.sdraft || {};
  const sites = d.sites || [], running = (d.job || {}).state === 'running';
  const ae = document.activeElement, focusSid = ae && ae.matches && ae.matches('[data-surl],[data-sq]') ? [ae.closest('.vd-sc').dataset.sid, ae.matches('[data-surl]') ? 'u' : 'q'] : null;
  const card = s => {
    const busy = vdSBusy(s), dr = VD.sdraft[s.id] || {};
    const marks = (s.boxes || []).map(b => `<i class="vd-mk h" style="left:${b[0] * 100}%;top:${b[1] * 100}%;width:${b[2] * 100}%;height:${b[3] * 100}%"></i>`).join('');
    const state = busy ? `<span class="spin"></span>${esc(VD_SST[s.status] || '')}` : s.status === 'ready'
      ? `${s.how === 'manual' ? 'کادر دستی' : s.how === 'fuzzy' || s.how === 'ocr' ? 'جمله پیدا شد (تقریبی)' : 'جمله پیدا شد'}${VD_SVIA[s.via] ? ' · ' + VD_SVIA[s.via] : ''}`
      : esc(s.err || VD_SST[s.status] || '');
    return `<div class="vd-sc ${['blocked', 'error', 'nomatch'].includes(s.status) ? 'warn' : ''}" data-sid="${esc(s.id)}">
      <div class="vd-sth" ${s.v ? 'data-sbox title="کادر هایلایت را خودت بکش"' : ''}>${s.v ? `<div class="vd-mimg"><img src="${vdMedia(d.id, `sites/${s.id}/${s.mode}/thumb.jpg`, s.v)}" alt=""></div>` : `<span class="vd-gico">🌐</span>`}
        <span class="vd-mtag">${s.mode === 'mobile' ? 'گوشی' : 'دسکتاپ'}</span></div>
      <div class="vd-mbody">
        <b dir="auto">${esc(s.domain || '')}${s.title ? ' — ' + esc(s.title) : ''}</b>
        ${s.claim ? `<small>${esc(s.claim)}</small>` : ''}
        <small class="vd-sst ${s.status}">${state}</small>
        <label class="vd-sl">نشانی<input class="vd-input sm" data-surl dir="ltr" value="${esc(dr.url ?? s.url ?? '')}"></label>
        <label class="vd-sl">جمله‌ای که هایلایت می‌شود (عین متن صفحه)<textarea class="vd-mnote" data-sq rows="2" dir="auto">${esc(dr.quote ?? s.quote ?? '')}</textarea></label>
        <div class="vd-row">
          <button class="btn sm primary" data-ssave style="${dr.url != null || dr.quote != null ? '' : 'display:none'}">ذخیره و عکس دوباره</button>
          <button class="btn sm" data-sre ${busy ? 'disabled' : ''}>عکس دوباره</button>
          <label class="btn sm vd-sup">اسکرین‌شات خودم<input type="file" accept="image/*,.heic,.heif" data-sfile hidden></label>
          ${s.v ? '<button class="btn sm" data-sbox>کادر هایلایت</button>' : ''}
          <a class="btn sm" href="${esc(s.url || '#')}" target="_blank" rel="noopener noreferrer" title="باز کردن سایت">↗</a>
          <button class="btn sm" data-sdel title="حذف">${VD.sdel === s.id ? 'مطمئنی؟' : '🗑'}</button></div>
      </div></div>`;
  };
  const notes = ((d.edit.notes || {}).sites || []).slice(-1)[0];
  sec.innerHTML = `
    <h3>سایت و هایلایت</h3>
    ${d.edit.sitesSummary ? `<p class="vd-sum">${esc(d.edit.sitesSummary)}</p>` : ''}
    ${sites.length ? `<div class="vd-sgrid">${sites.map(card).join('')}</div>` : `<div class="cr-dim">${running ? 'بعد از کار فعلی…' : 'هنوز منبعی نیست.'}</div>`}
    <div class="vd-regen">
      ${notes ? `<div class="cr-dim">آخرین نظرت: «${esc(notes)}»</div>` : ''}
      <textarea id="vdSiteNote" class="vd-note" placeholder="نظرت، مثلاً «گزارش لینکدین را از خود سایت لینکدین بیاور» یا «قیمت ManyChat را از صفحه‌ی pricing هایلایت کن»"></textarea>
      <div class="vd-row"><button class="btn primary" data-regen="sites" ${running ? 'disabled' : ''}>${sites.some(s => s.src !== 'user') ? 'دوباره پیدا کن' : 'پیدا کردن منبع‌ها با Claude'}</button>
        <span class="cr-dim">چند دقیقه طول می‌کشد؛ Claude در وب می‌گردد و عین جمله را از خود صفحه برمی‌دارد.</span></div>
    </div>
    <p class="cr-dim vd-help">وقتی از یک گزارش، صفحه‌ی قیمت، مقاله یا پست حرف می‌زنی، خود همان صفحه در قاب مرورگر یا گوشی می‌آید، تا جمله اسکرول می‌کند، بقیه‌ی صفحه تیره می‌شود و ماژیک زرد هم‌زمان با حرفت روی همان جمله کشیده می‌شود.
      منبع خودت: در «متن و برش» کلمه‌ها را انتخاب کن و «🌐 سایت…» را بزن. اگر سایتی اجازه‌ی عکس نداد، اسکرین‌شات خودت را بده؛ اگر جمله پیدا نشد، «کادر هایلایت» را بکش.
      قاب و جای هر کدام را در فهرست «عکس، ویدیو و گرافیک» عوض کن.</p>`;
  $$('.vd-sc', sec).forEach(c => {
    const sid = c.dataset.sid, s = sites.find(x => x.id === sid);
    const draft = (k, v) => { VD.sdraft[sid] = { ...(VD.sdraft[sid] || {}), [k]: v }; };
    const dirty = () => { $('[data-ssave]', c).style.display = ''; };
    $('[data-surl]', c).oninput = e => { draft('url', e.target.value); dirty(); };
    $('[data-sq]', c).oninput = e => { draft('quote', e.target.value); dirty(); };
    $('[data-ssave]', c) && ($('[data-ssave]', c).onclick = async () => {
      const dr = VD.sdraft[sid] || {}, body = { id: VD.id, act: 'edit', sid };
      if (dr.url != null) body.url = dr.url;
      if (dr.quote != null) body.quote = dr.quote;
      const r = await post('/api/video/site', body);
      if (!r.ok) return toast(r.data.error || 'نشد');
      delete VD.sdraft[sid]; toast('ذخیره شد؛ دوباره عکس گرفته می‌شود'); vdSoon();
    });
    $('[data-sre]', c) && ($('[data-sre]', c).onclick = async () => { await post('/api/video/site', { id: VD.id, act: 'recapture', sid }); vdSoon(); });
    $('[data-sfile]', c).onchange = e => { const f = e.target.files[0]; if (f) vdSiteUpload(sid, f); };
    $$('[data-sbox]', c).forEach(b => b.onclick = () => s.v && vdSiteBoxes(s));
    $('[data-sdel]', c).onclick = async e => {
      if (VD.sdel !== sid) { VD.sdel = sid; e.target.textContent = 'مطمئنی؟'; return; }
      VD.sdel = null; const r = await post('/api/video/site', { id: VD.id, act: 'del', sid });
      toast(r.ok ? 'حذف شد' : (r.data.error || 'نشد')); vdSoon();
    };
  });
  if (focusSid) { const el = $(`.vd-sc[data-sid="${focusSid[0]}"] ${focusSid[1] === 'u' ? '[data-surl]' : '[data-sq]'}`, sec); if (el) { el.focus(); const n = el.value.length; el.setSelectionRange(n, n); } }
  $$('[data-regen]', sec).forEach(b => b.onclick = () => vdRegen('sites', $('#vdSiteNote').value));
}
function vdSiteUpload(sid, f) {
  const xhr = new XMLHttpRequest();
  xhr.open('POST', `/api/video/upload?id=${encodeURIComponent(VD.id)}&name=${encodeURIComponent(f.name)}&site=${encodeURIComponent(sid)}`);
  xhr.onload = () => { let m = 'اسکرین‌شات رسید؛ جمله رویش پیدا می‌شود'; if (xhr.status !== 200) { m = 'آپلود نشد'; try { m = JSON.parse(xhr.responseText).error || m; } catch {} } toast(m); vdSoon(); };
  xhr.onerror = () => toast('اتصال قطع شد');
  xhr.send(f);
}

/* فرم «🌐 سایت…» در نوار ابزار «متن و برش»: نشانی + جمله، روی کلمه‌های انتخاب‌شده */
function vdSiteForm(bar, ids) {
  if ($('#vdSiteForm')) { $('#vdSiteForm').remove(); return; }
  bar.insertAdjacentHTML('beforeend', `<div class="vd-tsite" id="vdSiteForm">
    <input class="vd-input sm" id="vdSfUrl" dir="ltr" placeholder="https://… نشانی صفحه">
    <textarea class="vd-note" id="vdSfQ" rows="2" dir="auto" placeholder="جمله‌ای از همان صفحه که باید هایلایت شود (عین متن صفحه؛ خالی = فقط صفحه)"></textarea>
    <div class="vd-row"><select class="vd-fxs" id="vdSfTpl"><option value="browser">قاب مرورگر</option><option value="phone">قاب گوشی</option></select>
      <button class="btn sm primary" id="vdSfOk">بگذار</button><button class="btn sm" id="vdSfNo">انصراف</button></div></div>`);
  $('#vdSfUrl').focus();
  $('#vdSfNo').onclick = () => $('#vdSiteForm').remove();
  $('#vdSfOk').onclick = async () => {
    const r = await post('/api/video/site', { id: VD.id, act: 'add', url: $('#vdSfUrl').value, quote: $('#vdSfQ').value,
      tpl: $('#vdSfTpl').value, w0: Math.min(...ids), w1: Math.max(...ids) });
    if (!r.ok) return toast(r.data.error || 'نشد');
    toast('سایت گذاشته شد؛ دارد عکس گرفته می‌شود'); $('#vdSiteForm') && $('#vdSiteForm').remove(); vdSoon();
  };
}

/* کادر هایلایت دستی روی عکس سایت (وقتی جمله پیدا نشد یا جای دیگری را می‌خواهی) */
function vdSiteBoxes(s) {
  const d = VD.data, boxes = JSON.parse(JSON.stringify(s.boxes || []));
  let drag = null;
  const ov = document.createElement('div'); ov.className = 'vd-modal';
  ov.innerHTML = `<div class="vd-mdl" role="dialog" aria-label="کادر هایلایت">
    <div class="vd-row"><b dir="auto">${esc(s.domain || '')}</b><span class="grow"></span><span class="cr-dim">${faNum(boxes.length)} کادر</span></div>
    <p class="cr-dim vd-help">روی هر خطی که باید ماژیک بخورد یک کادر بکش (خط‌به‌خط، به ترتیب خواندن)؛ روی کادر بزن تا پاک شود.</p>
    <div class="vd-bxw"><img src="${vdMedia(d.id, `sites/${s.id}/${s.mode}/view.jpg`, s.v)}" draggable="false" alt=""><div class="vd-bxl"></div></div>
    <div class="vd-row"><button class="btn primary" data-bsave>ذخیره</button><span class="grow"></span><button class="btn" data-bno>انصراف</button></div></div>`;
  document.body.appendChild(ov);
  const L = $('.vd-bxl', ov);
  const pos = b => `left:${b[0] * 100}%;top:${b[1] * 100}%;width:${b[2] * 100}%;height:${b[3] * 100}%`;
  const draw = () => {
    L.innerHTML = boxes.map((b, k) => `<i class="vd-bx hl" data-k="${k}" style="${pos(b)}"></i>`).join('') + (drag ? `<i class="vd-bx hl draft" style="${pos(drag.b)}"></i>` : '');
    $('.vd-mdl .cr-dim', ov).textContent = `${faNum(boxes.length)} کادر`;
  };
  const pt = e => { const r = L.getBoundingClientRect(); return [Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)), Math.min(1, Math.max(0, (e.clientY - r.top) / r.height))]; };
  L.onpointerdown = e => {
    const hit = e.target.closest('.vd-bx:not(.draft)');
    if (hit) { boxes.splice(+hit.dataset.k, 1); draw(); return; }
    e.preventDefault(); const p = pt(e); drag = { p, b: [p[0], p[1], 0, 0] };
    try { L.setPointerCapture(e.pointerId); } catch (_) {}
    draw();
  };
  L.onpointermove = e => { if (!drag) return; const p = pt(e); drag.b = [Math.min(p[0], drag.p[0]), Math.min(p[1], drag.p[1]), Math.abs(p[0] - drag.p[0]), Math.abs(p[1] - drag.p[1])]; draw(); };
  L.onpointerup = () => { if (!drag) return; const b = drag.b.map(x => Math.round(x * 10000) / 10000); drag = null; if (b[2] > 0.008 && b[3] > 0.004) boxes.push(b); draw(); };
  const escK = e => { if (e.key === 'Escape') close(); };
  const close = () => { ov.remove(); document.removeEventListener('keydown', escK); };
  document.addEventListener('keydown', escK);
  $('[data-bno]', ov).onclick = close;
  ov.onclick = e => { if (e.target === ov) close(); };
  $('[data-bsave]', ov).onclick = async () => {
    const r = await post('/api/video/site', { id: VD.id, act: 'boxes', sid: s.id, boxes });
    toast(r.ok ? 'ذخیره شد' : (r.data.error || 'نشد')); if (r.ok) { close(); vdSoon(); }
  };
  draw();
}
/* ---------------- ضبط صفحه (فاز ۵) ----------------
   زوم هوشمند (edit.json → zooms)، محو اطلاعات حساس (blurs) و خروجی عمودی ۹:۱۶ (opts.vertical / vlayout / vbg).
   ویرایش‌ها: POST /api/video/screen. فریم هر مورد: /video-media/<id>/frames/f<ms>.jpg */
function vdScreenPanel(d) {
  const sec = $('#vdScreen'); if (!sec) return;
  if (!d.words) { sec.innerHTML = '<h3>ضبط صفحه</h3><div class="cr-dim">بعد از متن.</div>'; return; }
  const o = d.opts, sc = d.screen || {}, zooms = d.zooms || [], blurs = d.blurs || [];
  const running = (d.job || {}).state === 'running';
  const thumb = (frame, box, cls) => frame ? `<div class="vd-mimg"><img src="${vdMedia(d.id, frame)}" alt="">${box ? `<i class="vd-mk ${cls}" style="left:${box[0] * 100}%;top:${box[1] * 100}%;width:${box[2] * 100}%;height:${box[3] * 100}%"></i>` : ''}</div>` : '<span class="vd-gico">🔍</span>';
  const zrow = z => `<div class="vd-ov ${z.on === false || z.skip ? 'off' : ''}" data-zid="${esc(z.id)}">
      <input type="checkbox" data-zon ${z.on === false ? '' : 'checked'} ${z.skip ? 'disabled' : ''} title="روشن/خاموش">
      <span class="vd-ct">${z.s != null ? vdT(z.s) : '—'}</span>
      <span class="vd-ovth vd-zth" data-zbox title="جای زوم را خودت بکش">${thumb(z.frame, z.box, 'f')}</span>
      <span class="vd-ovt" data-zgo><b dir="auto">${esc(z.target || 'زوم دستی')}</b><small>${esc(z.skip ? 'کلمه‌هایش حذف شده' : (z.hl || []).length ? `با ماژیک روی ${faNum(z.hl.length)} خط` + (z.why ? ' · ' + z.why : '') : (z.why || ''))}</small></span>
      <select class="vd-fxg" data-zz title="شدت زوم">${Object.entries(sc.zoom || {}).map(([k, t]) => `<option value="${k}" ${(z.z || 'm') === k ? 'selected' : ''}>زوم ${esc(t)}</option>`).join('')}</select>
      <button class="btn sm" data-zbox>جای زوم</button>
      <button class="btn sm" data-zdel title="حذف">✕</button></div>`;
  const brow = b => `<div class="vd-ov ${b.on === false ? 'off' : ''}" data-bid="${esc(b.id)}">
      <input type="checkbox" data-bon ${b.on === false ? '' : 'checked'} title="روشن/خاموش">
      <span class="vd-ct">${vdT(b.o != null ? b.o : b.s)}</span>
      <span class="vd-ovth vd-zth" data-bbox title="جای محو">${thumb(b.frame, b.box, 'b')}</span>
      <span class="vd-ovt"><b dir="ltr">${esc(b.label || '')}</b><small>${esc((sc.blurType || {})[b.type] || b.type || '')} · ${faNum((Math.round((b.e - b.s) * 10) / 10).toString().replace('.', '٫'))} ثانیه از ضبط</small></span>
      <button class="btn sm" data-bbox>جای محو</button>
      <button class="btn sm" data-bdel title="حذف">✕</button></div>`;
  const notes = ((d.edit.notes || {}).zooms || []).slice(-1)[0];
  const vert = !!o.vertical;
  sec.innerHTML = `
    <h3>ضبط صفحه</h3>
    <div class="vd-row vd-toggles"><label><input type="checkbox" id="vdVert" ${vert ? 'checked' : ''}> خروجی عمودی ۹:۱۶ برای ریلز</label></div>
    ${vert ? `<div class="vd-row"><span class="cr-dim">چیدمان:</span>${Object.entries(sc.vlayout || {}).map(([k, t]) => `<button class="btn sm ${(o.vlayout || 'frame') === k ? 'on' : ''}" data-vl="${k}">${esc(t)}</button>`).join('')}
      ${(o.vlayout || 'frame') === 'frame' ? Object.entries(sc.vbg || {}).map(([k, t]) => `<button class="btn sm ${(o.vbg || 'brand') === k ? 'on' : ''}" data-vb="${k}">${esc(t)}</button>`).join('') : ''}</div>
      <p class="cr-dim vd-help">پیش‌نمایش بالا همین حالا عوض می‌شود؛ هر کدام را دوست داری نگه دار. «قاب وسط» کل صفحه را نشان می‌دهد و زوم‌ها جزئیات را بزرگ می‌کنند؛ «تمام‌قد» یک کادر عمودی از صفحه است که خودش دنبال جای زوم‌ها می‌رود (متن درشت‌تر، ولی همه‌ی صفحه دیده نمی‌شود).</p>` : ''}
    <h4 class="vd-h4">زوم هوشمند</h4>
    ${d.edit.zoomSummary ? `<p class="vd-sum">${esc(d.edit.zoomSummary)}</p>` : ''}
    <div class="vd-vislist">${zooms.map(zrow).join('') || `<div class="cr-dim">${running ? 'بعد از کار فعلی…' : 'هنوز زومی نیست.'}</div>`}</div>
    <div class="vd-regen">
      ${notes ? `<div class="cr-dim">آخرین نظرت: «${esc(notes)}»</div>` : ''}
      <textarea id="vdZoomNote" class="vd-note" placeholder="نظرت، مثلاً «کمتر زوم کن» یا «وقتی کلید را کپی می‌کنم روی دکمه‌ی Copy زوم کن»"></textarea>
      <div class="vd-row"><button class="btn primary" data-zregen ${running ? 'disabled' : ''}>${zooms.some(z => z.src !== 'user') ? 'دوباره پیدا کن' : 'پیدا کردن جای زوم با Claude'}</button>
        ${(d.prevSections || []).includes('zooms') ? '<button class="btn" data-undo="zooms">↶ نسخه‌ی قبل</button>' : ''}</div>
    </div>
    <h4 class="vd-h4">محو اطلاعات حساس</h4>
    <div class="vd-vislist">${blurs.map(brow).join('') || `<div class="cr-dim">${running ? 'بعد از کار فعلی…' : 'چیزی پیدا نشد یا هنوز اسکن نشده.'}</div>`}</div>
    <div class="vd-row"><button class="btn" data-bregen ${running ? 'disabled' : ''}>اسکن دوباره‌ی صفحه</button>
      ${(d.prevSections || []).includes('blurs') ? '<button class="btn" data-undo="blurs">↶ نسخه‌ی قبل</button>' : ''}</div>
    <p class="cr-dim vd-help">هر جا به جایی از صفحه اشاره می‌کنی («اینجا»، «این دکمه»، «سمت چپ») یا عددی را می‌خوانی، تصویر روی همان‌جا زوم می‌شود و اگر لازم است زیر متن ماژیک می‌خورد.
      ایمیل، کلید API و توکن، شماره‌ی کارت و تلفن که روی صفحه دیده می‌شوند، در کل ویدیو خودکار محو می‌شوند (هم پیش‌نمایش، هم خروجی).
      دستی: در «متن و برش» کلمه‌ها را انتخاب کن و «🔍 زوم» یا «▒ محو» بزن، بعد روی فریم کادر بکش.</p>`;
  $('#vdVert').onchange = e => vdOpt('vertical', e.target.checked);
  $$('[data-vl]', sec).forEach(b => b.onclick = () => vdOpt('vlayout', b.dataset.vl));
  $$('[data-vb]', sec).forEach(b => b.onclick = () => vdOpt('vbg', b.dataset.vb));
  $$('[data-zid]', sec).forEach(r => {
    const zid = r.dataset.zid, z = zooms.find(x => x.id === zid);
    const send = (body, msg) => vdScreen({ act: 'zoom', zid, ...body }, msg);
    $('[data-zon]', r).onchange = e => send({ on: e.target.checked });
    $('[data-zz]', r).onchange = e => send({ z: e.target.value });
    $$('[data-zbox]', r).forEach(b => b.onclick = () => z.frame && vdFrameBox(z.frame, z.box, z.hl || [], true, (box, hl) => send({ box, hl }, 'جای زوم ذخیره شد')));
    $('[data-zgo]', r).onclick = () => { if (z.s != null) { vdCmd({ cmd: 'seek', t: Math.max(0, z.s - 0.8) }); vdCmd({ cmd: 'play' }); } };
    $('[data-zdel]', r).onclick = () => vdScreen({ act: 'zoom_del', zid }, 'زوم حذف شد');
  });
  $$('[data-bid]', sec).forEach(r => {
    const bid = r.dataset.bid, b = blurs.find(x => x.id === bid);
    $('[data-bon]', r).onchange = e => vdScreen({ act: 'blur', bid, on: e.target.checked }, e.target.checked ? '' : 'این بخش دیگر محو نمی‌شود');
    $$('[data-bbox]', r).forEach(x => x.onclick = () => b.frame && vdFrameBox(b.frame, b.box, null, false, box => vdScreen({ act: 'blur', bid, box }, 'جای محو ذخیره شد')));
    $('[data-bdel]', r).onclick = () => vdScreen({ act: 'blur_del', bid }, 'محو حذف شد');
  });
  $('[data-zregen]', sec).onclick = () => vdRegen('zooms', $('#vdZoomNote').value);
  $('[data-bregen]', sec).onclick = () => vdRegen('blurs', '');
  $$('[data-undo]', sec).forEach(b => b.onclick = () => vdUndo(b.dataset.undo));
}

async function vdScreen(body, msg) {
  const r = await post('/api/video/screen', { id: VD.id, ...body });
  if (!r.ok) { toast(r.data.error || 'نشد'); return null; }
  msg && toast(msg); vdSoon(); return r.data;
}

/* افزودن دستی از نوار ابزار «متن و برش»: مورد ساخته می‌شود و بلافاصله کادرش روی فریم همان لحظه */
async function vdScreenAdd(kind, ids) {
  const data = await vdScreen({ act: kind === 'zoom' ? 'zoom_add' : 'blur_add', w0: Math.min(...ids), w1: Math.max(...ids) });
  if (!data) return;
  const d = await api(`/api/video/project?id=${encodeURIComponent(VD.id)}`);
  if (!d) return;
  VD.data = d;
  if (kind === 'zoom') {
    const z = (d.zooms || []).find(x => x.id === data.zid);
    if (z && z.frame) vdFrameBox(z.frame, z.box, [], true, (box, hl) => vdScreen({ act: 'zoom', zid: z.id, box, hl }, 'زوم ذخیره شد'));
  } else {
    const b = (d.blurs || []).find(x => x.id === data.bid);
    if (b && b.frame) vdFrameBox(b.frame, b.box, null, false, box => vdScreen({ act: 'blur', bid: b.id, box }, 'محو ذخیره شد'));
  }
}

/* کشیدن کادر روی فریم: یک کادر اصلی (زوم آبی / محو قرمز) و برای زوم چند کادر ماژیک (زرد). onSave(box, hl) */
function vdFrameBox(frame, box, hl, zoom, onSave) {
  let main = box ? [...box] : null, marks = (hl || []).map(b => [...b]), mode = 'main', drag = null;
  const ov = document.createElement('div'); ov.className = 'vd-modal';
  ov.innerHTML = `<div class="vd-mdl" role="dialog" aria-label="${zoom ? 'جای زوم' : 'جای محو'}">
    <div class="vd-row"><b>${zoom ? 'جای زوم' : 'جای محو'}</b><span class="grow"></span>
      ${zoom ? '<button class="btn sm on" data-fm="main">کادر زوم</button><button class="btn sm" data-fm="hl">ماژیک زیر متن</button>' : ''}</div>
    <p class="cr-dim vd-help">${zoom ? 'دور چیزی که باید بزرگ دیده شود کادر بکش (آبی). اگر زیر متنی باید ماژیک بخورد، «ماژیک زیر متن» را بزن و روی هر خط یک کادر بکش (زرد). روی کادر زرد بزن تا پاک شود.' : 'دور بخشی که باید محو شود کادر بکش.'}</p>
    <div class="vd-bxw"><img src="${vdMedia(VD.id, frame)}" draggable="false" alt=""><div class="vd-bxl"></div></div>
    <div class="vd-row"><button class="btn primary" data-fsave>ذخیره</button><span class="grow"></span><button class="btn" data-fno>انصراف</button></div></div>`;
  document.body.appendChild(ov);
  const L = $('.vd-bxl', ov);
  const pos = b => `left:${b[0] * 100}%;top:${b[1] * 100}%;width:${b[2] * 100}%;height:${b[3] * 100}%`;
  const draw = () => {
    L.innerHTML = (main ? `<i class="vd-bx ${zoom ? 'focus' : 'blur'}" style="${pos(main)}"></i>` : '')
      + marks.map((b, k) => `<i class="vd-bx hl" data-k="${k}" style="${pos(b)}"></i>`).join('')
      + (drag ? `<i class="vd-bx ${mode === 'hl' ? 'hl' : zoom ? 'focus' : 'blur'} draft" style="${pos(drag.b)}"></i>` : '');
  };
  const pt = e => { const r = L.getBoundingClientRect(); return [Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)), Math.min(1, Math.max(0, (e.clientY - r.top) / r.height))]; };
  L.onpointerdown = e => {
    const hit = e.target.closest('.vd-bx.hl:not(.draft)');
    if (hit) { marks.splice(+hit.dataset.k, 1); draw(); return; }
    e.preventDefault(); const p = pt(e); drag = { p, b: [p[0], p[1], 0, 0] };
    try { L.setPointerCapture(e.pointerId); } catch (_) {}
    draw();
  };
  L.onpointermove = e => { if (!drag) return; const p = pt(e); drag.b = [Math.min(p[0], drag.p[0]), Math.min(p[1], drag.p[1]), Math.abs(p[0] - drag.p[0]), Math.abs(p[1] - drag.p[1])]; draw(); };
  L.onpointerup = () => {
    if (!drag) return; const b = drag.b.map(x => Math.round(x * 10000) / 10000); drag = null;
    if (b[2] > 0.01 && b[3] > 0.006) { if (mode === 'hl') marks.push(b); else main = b; }
    draw();
  };
  $$('[data-fm]', ov).forEach(b => b.onclick = () => { mode = b.dataset.fm; $$('[data-fm]', ov).forEach(x => x.classList.toggle('on', x === b)); });
  const escK = e => { if (e.key === 'Escape') close(); };
  const close = () => { ov.remove(); document.removeEventListener('keydown', escK); };
  document.addEventListener('keydown', escK);
  $('[data-fno]', ov).onclick = close;
  ov.onclick = e => { if (e.target === ov) close(); };
  $('[data-fsave]', ov).onclick = () => { if (!main) return toast('اول کادر را بکش'); close(); onSave(main, marks); };
  draw();
}
/* ---------------- افکت صوتی ---------------- */
function vdFxOptions(d, sel) {
  const lib = d.sfxLib || {};
  return Object.entries(d.sfxCats || {}).map(([cat, fa]) => {
    const ks = Object.keys(lib).filter(k => lib[k].cat === cat);
    return ks.length ? `<optgroup label="${esc(fa)}">${ks.map(k => `<option value="${k}" ${k === sel ? 'selected' : ''}>${esc(lib[k].fa)}</option>`).join('')}</optgroup>` : '';
  }).join('');
}
function vdHear(k) {           // فقط خود صدا، بیرون از پیش‌نمایش
  try { VD.hear && VD.hear.pause(); VD.hear = new Audio(`/api/video/sfx-file?k=${encodeURIComponent(k)}`); VD.hear.play(); } catch (_) {}
}
async function vdFx(sid, body, msg) {
  const r = await post('/api/video/edit', { id: VD.id, op: 'sfx', sid, ...body });
  if (!r.ok) return toast(r.data.error || 'نشد');
  msg && toast(msg); vdSoon();
}
function vdSfxPanel(d) {
  const sec = $('#vdSfx'); if (!sec) return;
  if (!d.words) { sec.innerHTML = '<h3>افکت صوتی</h3><div class="cr-dim">بعد از متن.</div>'; return; }
  const o = d.opts, list = d.sfx || [], ws = d.words;
  const notes = ((d.edit.notes || {}).sfx || []).slice(-1)[0];
  const ctx = w => { const out = []; for (let i = w; i < ws.length && out.length < 4; i++) if (ws[i].w && ws[i].o != null) out.push(ws[i].w); return out.join(' '); };
  const vols = [[-6, 'آرام‌تر'], [0, 'معمولی'], [4, 'بلندتر']];
  const rows = list.map(c => {
    const off = c.on === false, cutw = c.skip === 'cut';
    return `<div class="vd-fx ${off || c.skip ? 'off' : ''}" data-sid="${esc(c.id)}">
      <input type="checkbox" data-fxon ${off ? '' : 'checked'} ${c.skip ? 'disabled' : ''} title="روشن/خاموش">
      <span class="vd-ct">${c.at != null ? vdT(c.at) : '—'}</span>
      <span class="vd-fxw" data-fxgo dir="rtl"><b>«${esc(ctx(c.w) || (ws[c.w] || {}).raw || '')}»</b>${cutw ? '<small>کلمه‌اش حذف شده؛ پخش نمی‌شود</small>' : c.why ? `<small>${esc(c.why)}</small>` : ''}</span>
      <select class="vd-fxs" data-fxsnd title="صدای این افکت">${vdFxOptions(d, c.snd)}</select>
      <button class="btn sm" data-fxplay title="شنیدن خود صدا">▶</button>
      <select class="vd-fxg" data-fxg title="بلندی همین افکت">${vols.map(([g, t]) => `<option value="${g}" ${(+c.g || 0) === g ? 'selected' : ''}>${t}</option>`).join('')}</select>
      <button class="btn sm" data-fxdel title="حذف">✕</button></div>`;
  }).join('');
  const busy = (d.job || {}).state === 'running';
  sec.innerHTML = `
    <h3>افکت صوتی</h3>
    ${d.edit.sfxSummary ? `<p class="vd-sum">${esc(d.edit.sfxSummary)}</p>` : ''}
    <div class="vd-row vd-toggles"><label><input type="checkbox" id="vdFxOn" ${o.sfx !== false ? 'checked' : ''}> افکت‌ها در ویدیو</label>
      <span class="cr-dim">بلندی همه:</span>
      ${Object.entries(d.sfxLevels || {}).map(([k, v]) => `<button class="btn sm ${(o.sfxLevel || 'mid') === k ? 'on' : ''}" data-fxlvl="${k}">${esc(v)}</button>`).join('')}</div>
    <div class="vd-fxlist" id="vdFxList">${rows || `<div class="cr-dim">${busy ? 'بعد از کار فعلی…' : 'هنوز افکتی نیست. «پیشنهاد افکت‌ها» را بزن، یا در «متن و برش» کلمه‌ای را انتخاب کن و از «♪ افکت…» صدا بگذار.'}</div>`}</div>
    <p class="cr-dim vd-help">ضربه‌ی هر صدا دقیقاً روی شروع کلمه‌اش می‌نشیند و با تغییر برش‌ها جابه‌جا نمی‌شود. روی متن ردیف بزن تا پیش‌نمایش از کمی قبلش پخش شود؛ ▶ فقط خود صدا را پخش می‌کند.
      برای افکت تازه، در «متن و برش» کلمه را انتخاب کن و از «♪ افکت…» صدا را بردار.</p>
    <div class="vd-regen">
      ${notes ? `<div class="cr-dim">آخرین نظرت: «${esc(notes)}»</div>` : ''}
      <textarea id="vdFxNote" class="vd-note" placeholder="نظرت درباره‌ی افکت‌ها، مثلاً «کمترش کن» یا «روی اسم هر اپ هم یک افکت بگذار»"></textarea>
      <div class="vd-row"><button class="btn" data-regen="sfx">${list.some(c => c.src !== 'user') ? 'بازتولید افکت‌ها با این نظر' : 'پیشنهاد افکت‌ها'}</button>
        ${(d.prevSections || []).includes('sfx') ? '<button class="btn" data-undo="sfx">↶ نسخه‌ی قبل</button>' : ''}</div>
    </div>`;
  $('#vdFxOn').onchange = e => vdOpt('sfx', e.target.checked);
  $$('[data-fxlvl]', sec).forEach(b => b.onclick = () => vdOpt('sfxLevel', b.dataset.fxlvl));
  $$('.vd-fx', sec).forEach(row => {
    const sid = row.dataset.sid, c = list.find(x => x.id === sid);
    $('[data-fxon]', row).onchange = e => vdFx(sid, { act: 'on', on: e.target.checked });
    $('[data-fxsnd]', row).onchange = e => { vdHear(e.target.value); vdFx(sid, { act: 'snd', snd: e.target.value }); };
    $('[data-fxplay]', row).onclick = () => vdHear($('[data-fxsnd]', row).value);
    $('[data-fxg]', row).onchange = e => vdFx(sid, { act: 'gain', g: +e.target.value });
    $('[data-fxdel]', row).onclick = () => vdFx(sid, { act: 'del' }, 'افکت حذف شد');
    $('[data-fxgo]', row).onclick = () => { if (c && c.at != null) { vdCmd({ cmd: 'seek', t: Math.max(0, c.at - 1.2) }); vdCmd({ cmd: 'play' }); } };
  });
  $$('[data-regen]', sec).forEach(b => b.onclick = () => vdRegen(b.dataset.regen, $('#vdFxNote').value));
  $$('[data-undo]', sec).forEach(b => b.onclick = () => vdUndo(b.dataset.undo));
}

/* ---------------- رندر و دانلود ---------------- */
function vdOutPanel(d) {
  const sec = $('#vdOut'), j = d.job || {};
  const r = d.render || {};
  const rendering = j.state === 'running' && j.step === 'render';
  sec.innerHTML = `
    <h3>رندر و دانلود</h3>
    ${d.finalAt ? `
      <video class="vd-final ${d.kind}" controls playsinline preload="metadata" src="${vdMedia(d.id, 'out/final.mp4', d.finalAt)}"></video>
      <div class="vd-row">
        <a class="btn primary" href="${vdMedia(d.id, 'out/final.mp4', d.finalAt)}&dl=1" download>دانلود MP4</a>
        <a class="btn" href="${vdMedia(d.id, 'out/final.srt', d.finalAt)}" download="${esc(d.id)}.srt">فایل زیرنویس (SRT)</a>
      </div>
      <p class="cr-dim">${r.dur ? `${vdT(r.dur)} · ${faNum(((r.size || 0) / 1048576).toFixed(1)).replace('.', '٫')} مگ · رندر در ${faNum(Math.round(r.secs || 0))} ثانیه` : ''}
        ${d.editAt > d.finalAt ? '<br><b class="vd-stale">بعد از آخرین رندر تغییر داده‌ای؛ دوباره رندر بگیر.</b>' : ''}</p>`
      : `<p class="cr-dim">${rendering ? 'در حال رندر…' : 'هنوز رندر نشده. وقتی برش و زیرنویس خوب شد، «رندر نهایی» را بزن. خروجی ۱۰۸۰p با صدای یکدست (−۱۴ LUFS) است.'}</p>`}
    <div class="vd-row"><button class="btn ${d.finalAt ? '' : 'primary'}" id="vdRender2" ${j.state === 'running' || !d.words ? 'disabled' : ''}>${d.finalAt ? 'رندر دوباره' : 'رندر نهایی'}</button>
      ${j.state === 'running' ? '<button class="btn danger" id="vdCancel">توقف کار</button>' : ''}</div>`;
  $('#vdRender2') && ($('#vdRender2').onclick = () => vdRun('render'));
  $('#vdCancel') && ($('#vdCancel').onclick = async () => { await post('/api/video/cancel', { id: VD.id }); toast('متوقف شد'); vdSoon(); });
}

/* ---------------- کاور، کپشن و انتشار (فاز ۶؛ سرور: app/video_publish.py) ----------------
   کاور همان cover/cover.html است که در iframe کوچک دیده می‌شود و Chrome از آن JPEG می‌گیرد.
   کارهای این پنل (فریم‌ها، Claude، انتشار) جدا از کار اصلی پروژه‌اند (JOBS[vid:post])، پس ویرایش را قفل نمی‌کنند.
   انتشار واقعی فقط با تیک «مطمئنم» و دکمه‌ی «منتشر کن». */
const VD_PJOB = { cands: 'پیدا کردن فریم‌های کاور', write: 'Claude دارد می‌نویسد', cover: 'ساخت عکس کاور', publish: 'انتشار', resume: 'ادامه‌ی انتشار' };
const vdTitleHtml = t => esc(t || '').replace(/\*\*(.+?)\*\*/g, '<em>$1</em>');
const vdTagCount = s => (String(s || '').match(/(?:^|\s)#[^\s#]+/g) || []).length;
const vdFullCap = (c, t) => { c = (c || '').trim(); t = (t || '').split(/\s+/).filter(Boolean).join(' '); return c + (c && t ? '\n\n' + t : t); };

function vdPostBusy(d) { return ((d.post || {}).job || {}).state === 'running'; }

function vdPostPanel(d) {
  const sec = $('#vdPost'); if (!sec) return;
  if (!d.words || !d.post) { sec.innerHTML = '<h3>کاور و کپشن</h3><div class="cr-dim">بعد از متن.</div>'; return; }
  const P = d.post, c = P.cover || {}, busy = vdPostBusy(d), j = P.job || {};
  const zl = z => faNum(String(z).replace('.', '٫')) + '×';
  const cands = (P.cands || []).map(x => `<button class="vd-cand ${c.src === 'frame' && Math.abs((c.t || 0) - x.t) < 0.01 ? 'on' : ''}" data-ct="${x.t}"
      title="ثانیه‌ی ${vdT(x.o)} ویدیوی نهایی${x.best ? ' — بهترین چهره' : ''}"><img src="${vdMedia(d.id, 'cover/' + x.img)}" alt="" loading="lazy"><span>${vdT(x.o)}</span></button>`).join('');
  const own = c.src === 'upload';
  sec.innerHTML = `
    <h3>کاور و کپشن</h3>
    <div class="vd-post">
      <div class="vd-pcov">
        <div class="vd-pstage" id="vdCovStage">${P.coverAt ? `<iframe id="vdCovFrame" src="${vdMedia(d.id, 'cover/cover.html', P.coverAt)}" width="1080" height="1920" scrolling="no" title="کاور"></iframe>`
          : `<div class="vd-ph">${busy && j.task === 'cands' ? '<span class="spin"></span><span>فریم‌ها…</span>' : '<span>هنوز کاوری نیست</span>'}</div>`}
          <div class="vd-pgrid" ${VD.noGrid ? 'hidden' : ''}></div></div>
        <label class="vd-gridt"><input type="checkbox" id="vdCovGrid" ${VD.noGrid ? '' : 'checked'}> برش شبکه‌ی پروفایل (۳:۴)</label>
        <div class="vd-row">
          <button class="btn sm" id="vdCovJpg" ${!P.coverAt || busy ? 'disabled' : ''}>${P.jpgAt && !P.jpgStale ? 'عکس کاور آماده است' : 'ساخت عکس کاور'}</button>
          ${P.jpgAt && !P.jpgStale ? `<a class="btn sm" href="${vdMedia(d.id, 'cover/cover.jpg', P.jpgAt)}" download="${esc(d.id)}-cover.jpg">دانلود</a>` : ''}</div>
      </div>
      <div class="vd-pside">
        <div class="vd-lbl">فریم کاور <small>بهترین چهره‌ها از بخش‌های نگه‌داشته</small></div>
        <div class="vd-cands">${cands || `<span class="cr-dim">${busy && j.task === 'cands' ? 'در حال پیدا کردن…' : 'هنوز فریمی نیست.'}</span>`}
          <label class="vd-cand vd-candup ${own ? 'on' : ''}" title="عکس خودت برای کاور">${own ? `<img src="${vdMedia(d.id, 'cover/upload.jpg', P.coverAt)}" alt="">` : ''}<span>${own ? 'عکس خودم' : '+ عکس خودم'}</span>
            <input type="file" id="vdCovUp" accept="image/*,.heic" hidden></label></div>
        ${P.cands && P.cands.length ? '' : `<button class="btn sm" id="vdCands" ${busy ? 'disabled' : ''}>پیدا کردن فریم‌ها</button>`}
        <div class="vd-lbl">تیتر <small>کلمه‌ی کلیدی را بین ** بگذار تا زرد شود؛ خالی = بی‌تیتر</small></div>
        <textarea id="vdCovTitle" class="vd-input vd-covt" rows="2" dir="rtl" placeholder="مثلاً: ابزارهای **AI** که هر روز باهاشون کار می‌کنم">${esc(c.title || '')}</textarea>
        ${(P.titles || []).length ? `<div class="vd-chips">${P.titles.map((t, i) => `<button class="vd-chip ${t === c.title ? 'on' : ''}" data-ti="${i}" title="همین تیتر">${vdTitleHtml(t)}</button>`).join('')}</div>` : ''}
        <div class="vd-row"><span class="cr-dim">قالب:</span>${Object.entries(P.tpls).map(([k, v]) => `<button class="btn sm ${(c.tpl || 'top') === k ? 'on' : ''}" data-ctpl="${k}">${esc(v)}</button>`).join('')}</div>
        <div class="vd-row"><span class="cr-dim">جای تیتر:</span>${Object.entries(P.poses).map(([k, v]) => `<button class="btn sm ${(c.pos || 'auto') === k ? 'on' : ''}" data-cpos="${k}">${esc(v)}</button>`).join('')}</div>
        <div class="vd-row"><span class="cr-dim">زوم روی صورت:</span>${P.zooms.map(z => `<button class="btn sm ${(+c.zoom || 1) === z ? 'on' : ''}" data-czoom="${z}">${zl(z)}</button>`).join('')}</div>
      </div>
    </div>
    <h4 class="vd-h4">کپشن</h4>
    <textarea id="vdCap" class="vd-input vd-cap" rows="9" dir="rtl" placeholder="${busy && j.task === 'write' ? 'Claude دارد می‌نویسد…' : 'کپشن پست'}">${esc(P.caption)}</textarea>
    <input id="vdTags" class="vd-input" dir="rtl" value="${esc(P.hashtags)}" placeholder="#هشتگ #hashtag — حداکثر ${faNum(P.tagMax)} تا">
    <div class="vd-row vd-capmeta"><span id="vdCapCount"></span><span class="grow"></span><button class="btn sm" id="vdCapCopy">کپی کپشن و هشتگ</button></div>
    <div class="vd-regen">
      ${['caption', 'titles'].map(k => ((P.notes || {})[k] || [])[0] ? `<div class="cr-dim">آخرین نظرت درباره‌ی ${k === 'caption' ? 'کپشن' : 'تیترها'}: «${esc(P.notes[k][0])}»</div>` : '').join('')}
      <textarea id="vdPostNote" class="vd-note" placeholder="نظرت، مثلاً «خط اول کپشن تندتر باشد» یا «تیترها درباره‌ی صرفه‌جویی پول باشند»"></textarea>
      <div class="vd-row">
        <button class="btn" data-pw="caption" ${busy ? 'disabled' : ''}>${P.caption ? 'بازنویسی کپشن' : 'نوشتن کپشن'}</button>
        <button class="btn" data-pw="titles" ${busy ? 'disabled' : ''}>تیترهای تازه</button>
        ${(P.prev || []).includes('caption') ? '<button class="btn" data-pundo="caption">↶ کپشن قبلی</button>' : ''}
        ${(P.prev || []).includes('titles') ? '<button class="btn" data-pundo="titles">↶ تیترهای قبلی</button>' : ''}</div>
    </div>
    <h4 class="vd-h4">انتشار در اینستاگرام (دستی)</h4>
    <ul class="vd-probs" id="vdProbs"></ul>
    <div id="vdPubStatus"></div>
    <div class="vd-row">
      ${d.finalAt ? `<a class="btn primary" href="${vdMedia(d.id, 'out/final.mp4', d.finalAt)}&dl=1" download>دانلود ویدیو</a>` : '<span class="cr-dim">اول «رندر نهایی» بگیر.</span>'}
      ${P.jpgAt && !P.jpgStale ? `<a class="btn" href="${vdMedia(d.id, 'cover/cover.jpg', P.jpgAt)}" download="${esc(d.id)}-cover.jpg">دانلود کاور</a>` : ''}
      <button class="btn" id="vdCapCopy2">کپی کپشن و هشتگ‌ها</button></div>
    <p class="cr-dim vd-help">ویدیو و کاور را به گوشی بفرست (AirDrop، تلگرام یا ایمیل). در اینستاگرام ریلز تازه بساز، کاور را از «Edit cover ← Add from camera roll» بگذار و کپشن را بچسبان.</p>`;
  const frame = $('#vdCovFrame');
  if (frame) { frame.onload = vdCovFit; vdCovFit(); }
  $('#vdCovGrid').onchange = e => { VD.noGrid = !e.target.checked; $('.vd-pgrid', sec).hidden = VD.noGrid; };
  $('#vdCovJpg').onclick = () => vdPostRun({ task: 'cover' }, 'عکس کاور در حال ساخت…');
  $('#vdCands') && ($('#vdCands').onclick = () => vdPostRun({ task: 'cands' }));
  $$('[data-ct]', sec).forEach(b => b.onclick = () => vdPostOp({ op: 'pick', t: +b.dataset.ct }));
  $('#vdCovUp').onchange = e => { const f = e.target.files[0]; if (f) vdCovUpload(f); };
  $('#vdCovTitle').oninput = e => { clearTimeout(VD.covT); VD.covT = setTimeout(() => vdPostOp({ op: 'title', value: e.target.value }), 700); };
  $$('[data-ti]', sec).forEach(b => b.onclick = () => { const t = P.titles[+b.dataset.ti]; $('#vdCovTitle').value = t; vdPostOp({ op: 'title', value: t }); });
  $$('[data-ctpl]', sec).forEach(b => b.onclick = () => vdPostOp({ op: 'tpl', value: b.dataset.ctpl }));
  $$('[data-cpos]', sec).forEach(b => b.onclick = () => vdPostOp({ op: 'pos', value: b.dataset.cpos }));
  $$('[data-czoom]', sec).forEach(b => b.onclick = () => vdPostOp({ op: 'zoom', value: +b.dataset.czoom }));
  const saveCap = () => { clearTimeout(VD.capT); VD.capT = setTimeout(() => vdPostOp({ op: 'caption', caption: $('#vdCap').value, hashtags: $('#vdTags').value }, null, true), 900); };
  $('#vdCap').oninput = () => { vdCapCount(); saveCap(); };
  $('#vdTags').oninput = () => { vdCapCount(); saveCap(); };
  $('#vdCapCopy').onclick = async () => {
    try { await navigator.clipboard.writeText(vdFullCap($('#vdCap').value, $('#vdTags').value)); toast('کپشن کپی شد'); } catch (_) { toast('کپی نشد'); }
  };
  $$('[data-pw]', sec).forEach(b => b.onclick = () => vdPostRun({ task: 'write', what: b.dataset.pw, comment: $('#vdPostNote').value }, 'Claude شروع کرد'));
  $$('[data-pundo]', sec).forEach(b => b.onclick = () => vdPostOp({ op: 'undo', section: b.dataset.pundo }, 'نسخه‌ی قبل برگشت'));
  $('#vdCapCopy2').onclick = () => $('#vdCapCopy').click();
  vdCapCount(); vdPostStatus(d);
}

function vdPostBlocked(d) { return ((d.post || {}).problems || []).some(p => p.block); }

function vdCovFit() {
  const st = $('#vdCovStage'), fr = $('#vdCovFrame'); if (!st || !fr) return;
  fr.style.transform = `scale(${st.clientWidth / 1080})`;
}

function vdCapCount() {
  const P = (VD.data || {}).post; if (!P || !$('#vdCapCount')) return;
  const full = vdFullCap($('#vdCap').value, $('#vdTags').value), n = vdTagCount(full), len = [...full].length;
  $('#vdCapCount').innerHTML = `<span class="${n > P.tagMax ? 'vd-stale' : ''}">${faNum(n)} از ${faNum(P.tagMax)} هشتگ</span>، `
    + `<span class="${len > P.capMax ? 'vd-stale' : ''}">${faNum(len)} از ${faNum(P.capMax)} حرف</span>`;
}

/* فقط بخش وضعیت؛ هر بار که صفحه تازه می‌شود، حتی وقتی کاربر دارد کپشن را تایپ می‌کند */
function vdPostStatus(d) {
  const P = d.post, box = $('#vdPubStatus'); if (!P || !box) return;
  const j = P.job || {}, busy = j.state === 'running', pend = P.pending, pub = (P.published || []).slice(-1)[0];
  $('#vdProbs').innerHTML = (P.problems || []).map(p => `<li class="${p.block ? 'block' : ''}">${esc(p.t)}</li>`).join('');
  let h = '';
  if (busy) {
    const pct = j.pct != null && j.task === 'publish' ? `<span class="vd-bar"><i style="width:${j.pct}%"></i></span>` : '';
    h = `<div class="build-status"><div class="build-step"><span class="spin"></span>${esc(j.msg || (VD_PJOB[j.task] || '') + '…')}</div>${pct}
      ${['publish', 'resume'].includes(j.task) ? '<button class="btn sm" id="vdPubStop">توقف</button>' : ''}</div>`;
  } else if (j.state === 'error') {
    h = `<div class="build-status err">${esc(j.error || 'خطا')}</div>`;
  } else if (j.state === 'done' && (j.task === 'publish' || j.task === 'resume')) {
    h = j.permalink ? `<div class="build-status ok">منتشر شد. <a href="${esc(j.permalink)}" target="_blank" rel="noopener">دیدن در اینستاگرام ↗</a></div>`
      : j.msg ? `<div class="build-status ok">${esc(j.msg)}</div>` : '';
  }
  if (!busy && pend && pend.fresh) {
    const ready = pend.state === 'ready';
    h += `<div class="vd-pend"><span>${ready ? (pend.dry ? 'یک ریلز آزمایشی ساخته و پردازش شده، ولی منتشر نشده.' : 'ریلز ساخته و پردازش شده، ولی منتشر نشده.')
        : 'ساخت ریلز نیمه‌کاره مانده (پردازش اینستاگرام هنوز تمام نشده بود).'} ${faNum((pend.at || '').slice(11, 16))}</span>
      ${!ready ? '<button class="btn sm" data-pres="check">ادامه</button>' : ''}
      ${j.retry ? '<button class="btn sm primary" data-pres="now">دوباره امتحان کن</button>' : ''}
      <button class="btn sm" data-pres="forget" title="این ریلز ساخته‌شده کنار گذاشته می‌شود؛ هیچ‌وقت منتشر نمی‌شود">فراموش کن</button></div>`;
  }
  if (pub) h += `<div class="vd-pubd">آخرین انتشار: ${faNum((pub.at || '').slice(0, 16))}${pub.permalink ? `، <a href="${esc(pub.permalink)}" target="_blank" rel="noopener">دیدن ↗</a>` : ''}
    ${(P.published || []).length > 1 ? `(تا حالا ${faNum(P.published.length)} بار)` : ''}<br><b class="vd-stale">انتشار دوباره یک ریلز تازه می‌سازد.</b></div>`;
  box.innerHTML = h;
  $('#vdPubStop') && ($('#vdPubStop').onclick = () => vdPostOp({ op: 'cancel' }, 'بعد از همین مرحله متوقف می‌شود'));
  $$('[data-pres]', box).forEach(b => b.onclick = () => {
    const a = b.dataset.pres;
    if (a === 'forget') return vdPostOp({ op: 'forget' }, 'کنار گذاشته شد');
    vdPostRun({ task: 'resume', now: a === 'now', sure: a === 'now' }, a === 'now' ? 'دوباره امتحان می‌شود' : 'ادامه');
  });
  const block = vdPostBlocked(d);

  $$('[data-pw]').forEach(b => (b.disabled = busy));
  $('#vdCovJpg') && ($('#vdCovJpg').disabled = busy || !P.coverAt);
}

async function vdPostOp(body, msg, quiet) {
  const r = await post('/api/video/post', { id: VD.id, ...body });
  if (!r.ok) return toast(r.data.error || 'نشد');
  msg && toast(msg);
  if (r.data.post && VD.data) {
    const was = VD.data.post || {};
    VD.data.post = { ...r.data.post, job: was.job };
    if (quiet) { vdCapCount(); vdPostStatus(VD.data); return; }
    if (r.data.post.coverAt !== was.coverAt && $('#vdCovFrame') && document.activeElement && ['vdCovTitle'].includes(document.activeElement.id)) {
      $('#vdCovFrame').src = vdMedia(VD.id, 'cover/cover.html', r.data.post.coverAt);      // در حال تایپ تیتر: فقط کاور تازه می‌شود
      VD.psig = vdPostSig(VD.data); return;
    }
    VD.psig = vdPostSig(VD.data); vdPostPanel(VD.data);
  }
}

async function vdPostRun(body, msg) {
  const r = await post('/api/video/post-run', { id: VD.id, ...body });
  if (!r.ok) return toast(r.data.error || 'نشد');
  msg && toast(msg); vdSoon();
}

function vdCovUpload(f) {
  toast('آپلود عکس کاور…');
  fetch(`/api/video/upload?id=${encodeURIComponent(VD.id)}&name=${encodeURIComponent(f.name)}&cover=1`, { method: 'POST', body: f })
    .then(r => r.json().then(j => ({ ok: r.ok, j })))
    .then(({ ok, j }) => { toast(ok ? 'عکس کاور گذاشته شد' : (j.error || 'نشد')); vdSoon(); })
    .catch(() => toast('آپلود نشد'));
}

/* امضای بخش‌های ثابت پنل (بدون وضعیت کار)؛ وقتی کاربر در فیلدی از همین پنل است، پنل دوباره ساخته نمی‌شود */
function vdPostSig(d) {
  const P = d.post || {};
  return JSON.stringify([!!d.words, P.cover, P.coverAt, P.jpgAt, P.jpgStale, P.cands, P.titles, P.prev, P.notes, P.feed,
    P.writtenAt, P.caption, P.hashtags, (P.job || {}).state === 'running' ? (P.job || {}).task : '', (P.job || {}).state]);
}
function vdPostPaint(d) {
  const sig = vdPostSig(d), sec = $('#vdPost');
  const typing = sec && document.activeElement && sec.contains(document.activeElement) && /^(INPUT|TEXTAREA)$/.test(document.activeElement.tagName)
    && document.activeElement.type !== 'checkbox';
  if (!sec) return;
  if ((sig !== VD.psig || !sec.innerHTML.trim()) && !typing) { VD.psig = sig; vdPostPanel(d); }   // پوسته‌ی تازه: بخش خالی
  else vdPostStatus(d);
}
