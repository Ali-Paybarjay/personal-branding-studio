/* ================= ترجمه‌ی کامل ویدیو → انتخاب تکه‌ها → بانک ایده =================
   پنل «ساخت سریع از لینک یوتیوب» در داشبورد، تب «ترجمه‌های یوتیوب» (?s=translations)
   و صفحه‌ی خواندن (?s=translations&read=<slug>).
   سرور: app/translate.py. انتخاب‌ها در picks.json پوشه‌ی همان ویدیو ذخیره می‌شوند. */

const TR = { slug:null, data:null, pending:[], sent:[], active:0, poll:null, ipoll:null, saveT:null, saving:null, dockObs:null };

const trTime = t => faNum(t || '');
const trYt = (url, t) => {
  const m = String(url || '').match(/(?:v=|youtu\.be\/|\/shorts\/|\/live\/|\/embed\/)([\w-]{11})/);
  const s = String(t || '0').split(':').reduce((a, x) => a * 60 + (+x || 0), 0);
  return m ? `https://www.youtube.com/watch?v=${m[1]}&t=${s}s` : url;
};
// تامبنیل از سرور (thumb.jpg پوشه‌ی ویدیو)؛ اگر نبود، جایش یک قاب خالی با نشان پخش می‌ماند
const trThumb = (slug, cls = '') => `<div class="tr-thumb ${cls}"><img src="/api/tr/thumb?slug=${encodeURIComponent(slug)}"
  alt="" loading="lazy" onerror="this.parentElement.classList.add('none')"></div>`;
const trPidKey = id => id.split('.').map(Number);
const trByPid = (a, b) => { const x = trPidKey(a), y = trPidKey(b); return x[0] - y[0] || x[1] - y[1]; };

/* ---------------- پنل لینک (داشبورد و تب «ترجمه‌های یوتیوب») ---------------- */
let TPOLL = null;
// full: در تب ترجمه‌ها همه‌ی ترجمه‌ها کارت‌کارت زیر پنل می‌آیند؛ در داشبورد فقط سه‌تای آخر
async function mountTrPanel(el, full = false) {
  el.innerHTML = `
    <h3>${full ? 'ترجمه‌ی ویدیوی تازه' : 'ساخت سریع از لینک یوتیوب'}</h3>
    <p class="tr-lead">لینک را بده تا کل متن ویدیو به فارسی ترجمه شود — کامل، بدون خلاصه و بدون تحلیل.
      بعد متن را می‌خوانی، تکه‌هایی را که دوست داری انتخاب می‌کنی و همه را با هم به بانک ایده می‌فرستی.</p>
    <section class="build" style="padding:0 0 4px">
      <div class="build-row">
        <input id="trUrl" type="url" dir="ltr" placeholder="لینک یوتیوب را اینجا بگذار…" autocomplete="off">
        <button id="trGo">ترجمه کن</button>
      </div>
      <div id="trStatus" class="build-status" hidden></div>
    </section>
    ${full ? '' : '<div id="trList" class="tr-list"></div>'}`;
  $('#trGo').onclick = trStart;
  $('#trUrl').onkeydown = e => { if (e.key === 'Enter') trStart(); };
  trRenderList();
  const j = await api('/api/tr/status');
  if (j && j.state === 'running') { trShowStatus(j); trPollStatus(); }
}

async function trRenderList() {
  const d = await api('/api/tr/list'); const items = (d && d.items) || [];
  const box = $('#trList'), all = $('#trAll');
  if (box) {
    box.innerHTML = !items.length ? '' : `<h4>ترجمه‌های اخیر</h4>` + items.slice(0, 3).map(v => {
      const bits = [v.channel, v.done === v.total ? '✓ کامل' : `${faNum(v.done)} از ${faNum(v.total)} بخش`,
        v.pending ? `${faNum(v.pending)} انتخاب منتظر ثبت` : ''].filter(Boolean);
      return `<button class="tr-item" data-read="${esc(v.slug)}">${trThumb(v.slug, 'sm')}
        <div class="tr-item-text"><b>${esc(v.title)}</b><span>${bits.map(esc).join(' — ')}</span></div></button>`;
    }).join('') + `<button class="tr-link tr-all-link" data-go="translations">همه‌ی ترجمه‌ها (${faNum(items.length)}) ←</button>`;
  }
  if (all) {
    all.innerHTML = !items.length
      ? `<div class="tr-none">هنوز ویدیویی ترجمه نشده. لینک یوتیوب را در کادر بالا بگذار.</div>`
      : items.map(v => {
        const full = v.done === v.total;
        const state = v.live ? `<span class="spin"></span> در حال ترجمه — ${faNum(v.done)} از ${faNum(v.total)} بخش`
          : full ? '✓ ترجمه‌ی کامل' : `${faNum(v.done)} از ${faNum(v.total)} بخش ترجمه شده — بقیه را از صفحه‌ی خواندن ادامه بده`;
        const mins = Math.max(1, Math.round(v.words / 200));
        return `<article class="tr-vcard" data-read="${esc(v.slug)}">
          <div class="tr-media">${trThumb(v.slug)}
            ${v.duration ? `<span class="tr-dur" dir="ltr">${trTime(v.duration)}</span>` : ''}
            ${v.live ? '<span class="tr-live"><span class="spin"></span> در حال ترجمه</span>' : ''}</div>
          <h3>${esc(v.title)}</h3>
          <div class="idea-meta">
            ${v.channel ? `<span>${esc(v.channel)}</span>` : ''}
            ${v.words ? `<span>حدود ${faNum(mins)} دقیقه خواندن</span>` : ''}
            ${v.created ? `<span>${esc(v.created)}</span>` : ''}
          </div>
          <div class="tr-vstate ${full ? 'ok' : ''}">${state}</div>
          ${v.pending || v.sent || v.ideas ? `<div class="tr-vstats">
            ${v.ideas ? `<span>${faNum(v.ideas)} ایده‌ی ریلز پیشنهادی</span>` : ''}
            ${v.pending ? `<span class="warn">${faNum(v.pending)} انتخاب منتظر ثبت</span>` : ''}
            ${v.sent ? `<span>${faNum(v.sent)} ایده به بانک ایده رفته</span>` : ''}</div>` : ''}
          <div class="tr-vactions">
            <button class="btn primary" data-read="${esc(v.slug)}">خواندن</button>
            ${v.url ? `<a class="btn" href="${esc(v.url)}" target="_blank" rel="noopener">یوتیوب ↗</a>` : ''}
          </div>
        </article>`;
      }).join('');
  }
  [box, all].filter(Boolean).forEach(el => $$('[data-read]', el).forEach(b => b.onclick = e => {
    if (e.target.closest('a')) return;       // لینک یوتیوب خودش باز می‌شود
    e.stopPropagation(); openReader(b.dataset.read);
  }));
  if (box) $$('[data-go]', box).forEach(b => b.onclick = () => { go(b.dataset.go); window.scrollTo(0, 0); });
}

/* ---------------- تب «ترجمه‌های یوتیوب» ---------------- */
function viewTranslations() {
  if (S.read) return viewReader(S.read);
  $('#page').innerHTML = `
    <div class="page-head"><h2>ترجمه‌های یوتیوب</h2>
      <p>متن کامل فارسی ویدیوهایی که ترجمه کرده‌ای. هر کدام را باز کن، بخوان و تکه‌های خوبش را به بانک ایده بفرست.</p></div>
    <div class="panel" style="margin-bottom:22px" id="trPanel"></div>
    <div id="trAll" class="tr-cards"></div>`;
  mountTrPanel($('#trPanel'), true);
}

async function trStart() {
  const inp = $('#trUrl'), btn = $('#trGo'); const url = inp.value.trim();
  if (!url) return toast('لینک را بگذار');
  btn.disabled = true;
  const r = await post('/api/tr/start', { url });
  if (!r.ok) { btn.disabled = false; return trShowStatus({ state:'error', error:r.data.error || 'شروع نشد' }); }
  inp.value = '';
  if (r.data.existing) { btn.disabled = false; toast('این ویدیو قبلاً کامل ترجمه شده'); return openReader(r.data.slug); }
  trPollStatus();
}

function trPollStatus() {
  clearInterval(TPOLL);
  TPOLL = setInterval(async () => {
    const j = await api('/api/tr/status'); if (!j) return;
    if (!$('#trStatus')) return clearInterval(TPOLL);       // کاربر از این صفحه رفته
    trShowStatus(j);
    // همین که ترجمه‌ی بخش‌ها شروع شد صفحه‌ی خواندن باز می‌شود؛ بخش‌ها همان‌جا یکی‌یکی می‌رسند
    if (j.state === 'running' && j.step === 'ترجمه' && j.slug) { clearInterval(TPOLL); return openReader(j.slug); }
    if (j.state !== 'running') {
      clearInterval(TPOLL); const b = $('#trGo'); if (b) b.disabled = false;
    }
    trRenderList();
  }, 2000);
}

function trShowStatus(j) {
  const box = $('#trStatus'); if (!box) return;
  if (!j || j.state === 'idle') { box.hidden = true; return; }
  box.hidden = false;
  box.className = 'build-status' + (j.state === 'error' ? ' err' : '');
  const head = j.state === 'running' ? `<span class="spin"></span> ${esc(j.step || 'در حال کار…')}`
             : j.state === 'done' ? '✓ ترجمه تمام شد' : '✕ ' + esc(j.error || 'خطا');
  const lg = (j.log || []).length ? `<div class="build-log">${j.log.map(l => `<div>${esc(l)}</div>`).join('')}</div>` : '';
  box.innerHTML = `<div class="build-step">${head}</div>${lg}`;
  const el = box.querySelector('.build-log'); if (el) el.scrollTop = el.scrollHeight;
}

/* ---------------- صفحه‌ی خواندن ---------------- */
function openReader(slug) {
  // صفحه‌ی خواندن زیر تب «ترجمه‌های یوتیوب» است، از هر جا که باز شود
  S.section = 'translations'; renderNav(); $('#videoSelect').hidden = true;
  S.read = slug;
  history.replaceState(null, '', `?s=translations&read=${encodeURIComponent(slug)}`);
  window.scrollTo(0, 0);
  viewReader(slug);
}

async function viewReader(slug) {
  clearInterval(TR.poll); clearInterval(TPOLL);
  if (TR.saveT) await trSave();           // انتخاب‌های ذخیره‌نشده‌ی ویدیوی قبلی گم نشوند
  const d = await api(`/api/tr/get?slug=${encodeURIComponent(slug)}`);
  if (!d) { S.read = null; toast('ترجمه پیدا نشد'); return go('translations'); }
  Object.assign(TR, { slug, data:d, pending:d.picks.pending, sent:d.picks.sent });
  TR.active = Math.max(0, TR.pending.length - 1);
  $('#page').innerHTML = `
    <div class="detail-bar">
      <button class="btn" id="trBack">→ همه‌ی ترجمه‌ها</button>
      <span class="grow"></span>
      ${d.url ? `<a class="btn" href="${esc(d.url)}" target="_blank" rel="noopener">یوتیوب ↗</a>` : ''}
    </div>
    <h2 class="detail-title">${esc(d.title)}</h2>
    <div class="idea-meta" style="margin-bottom:14px">
      ${d.channel ? `<span>${esc(d.channel)}</span>` : ''}${d.duration ? `<span>${trTime(d.duration)}</span>` : ''}
      <span>ترجمه‌ی کامل فارسی</span>
    </div>
    <div id="trProg"></div>
    <p class="tr-help">هر جا تکه‌ای به دلت نشست، با ماوس انتخابش کن؛ دکمه‌ی <b>«+ ایده‌ی تازه»</b> کنارش ظاهر می‌شود.
      می‌توانی چند تکه از جاهای مختلف ویدیو را به یک ایده اضافه کنی. انتخاب‌ها پایین متن جمع می‌شوند.</p>
    <article id="trText" class="tr-text">
      ${d.chunks.map(c => `<section class="tr-chunk" data-i="${c.i}" data-st="${c.state}">${trChunkHTML(c)}</section>`).join('')}
    </article>
    <section id="trIdeas" class="panel tr-ideas"></section>
    <section id="trPicks" class="panel tr-picks"></section>
    <div id="trFloat" class="tr-float" hidden></div>
    <button id="trDock" class="tr-dock" hidden></button>`;
  $('#trBack').onclick = () => { go('translations'); window.scrollTo(0, 0); };
  trWireReader();
  trRenderProg(); trRenderIdeas(); trRenderPicks(); trMark();
  if (d.live) trPollReader();
  if ((d.ideas_job || {}).state === 'running') trPollIdeas();
}

function trChunkHTML(c) {
  if (c.state === 'done') return c.paras.map((p, k) => `
    <div class="tr-row" data-id="${c.i}.${k}">
      <div class="tr-side"><a class="tr-t" dir="ltr" href="${esc(trYt(TR.data.url, p.t))}" target="_blank" rel="noopener"
        title="همین لحظه در یوتیوب">${trTime(p.t)}</a><span class="tr-badge"></span></div>
      <p class="tr-p" data-id="${c.i}.${k}" data-t="${esc(p.t)}">${inline(p.fa)}</p>
    </div>`).join('');
  const span = `${trTime(c.start)} تا ${trTime(c.end)}`;
  if (c.state === 'error') return `<div class="tr-wait err">ترجمه‌ی بخش ${span} نشد. «ادامه‌ی ترجمه» را بالای صفحه بزن.</div>`;
  if (c.state === 'running') return `<div class="tr-wait"><span class="spin"></span> بخش ${span} در حال ترجمه است…</div>`;
  return `<div class="tr-wait">بخش ${span} در نوبت ترجمه است.</div>`;
}

function trRenderProg() {
  const box = $('#trProg'); if (!box) return;
  const cs = TR.data.chunks, done = cs.filter(c => c.state === 'done').length;
  if (done === cs.length) { box.innerHTML = ''; return; }
  box.innerHTML = TR.data.live
    ? `<div class="build-status"><div class="build-step"><span class="spin"></span>
         در حال ترجمه — ${faNum(done)} از ${faNum(cs.length)} بخش آماده است. از همین حالا می‌توانی بخوانی و انتخاب کنی.</div></div>`
    : `<div class="build-status err"><div class="build-step">${faNum(cs.length - done)} بخش هنوز ترجمه نشده.
         <span class="grow"></span><button class="btn primary" id="trResume">ادامه‌ی ترجمه</button></div></div>`;
  const b = $('#trResume');
  if (b) b.onclick = async () => {
    b.disabled = true;
    const r = await post('/api/tr/resume', { slug:TR.slug });
    if (!r.ok) { b.disabled = false; return toast(r.data.error || 'شروع نشد'); }
    TR.data.live = true; trRenderProg(); trPollReader();
  };
}

function trPollReader() {
  clearInterval(TR.poll);
  TR.poll = setInterval(async () => {
    if (!$('#trText') || S.read !== TR.slug) return clearInterval(TR.poll);
    const d = await api(`/api/tr/get?slug=${encodeURIComponent(TR.slug)}`); if (!d) return;
    // فقط بخش‌هایی که عوض شده‌اند از نو ساخته می‌شوند تا انتخاب کاربر در بقیه‌ی متن به هم نخورد
    d.chunks.forEach(c => {
      const el = $(`.tr-chunk[data-i="${c.i}"]`);
      if (el && el.dataset.st !== c.state) { TR.data.chunks[c.i] = c; el.dataset.st = c.state; el.innerHTML = trChunkHTML(c); }
    });
    TR.data.live = d.live; trRenderProg(); trMark();
    if (!d.live) trRenderIdeas();            // ترجمه کامل شد: دکمه‌ی ساخت ایده فعال می‌شود
    if (!d.live) { clearInterval(TR.poll); if (d.chunks.every(c => c.state === 'done')) toast('✓ ترجمه کامل شد'); }
  }, 4000);
}

/* ---------------- ایده‌های ریلز پیشنهادی (فقط با دکمه) ---------------- */
function trRenderIdeas() {
  const box = $('#trIdeas'); if (!box) return;
  const d = TR.data, job = d.ideas_job || { state:'idle' }, ideas = d.ideas;
  const full = d.chunks.every(c => c.state === 'done');
  const running = job.state === 'running';
  const head = `<div class="tr-ideas-head">
      <h3>ایده‌های ریلز از دل این ویدیو</h3><span class="grow"></span>
      ${ideas && !running ? `<span class="tr-ideas-meta">ساخته‌شده ${esc(ideas.created || '')}</span>
        <button class="btn" id="trIdeasGo" data-again="1">ساخت دوباره</button>` : ''}
    </div>`;
  let body;
  if (running) body = `<div class="build-status"><div class="build-step"><span class="spin"></span>
      دارم کل متن را با هسته‌ی برندت می‌خوانم و ایده‌ها را بیرون می‌کشم — چند دقیقه طول می‌کشد. می‌توانی به خواندن ادامه بدهی.</div></div>`;
  else if (ideas && ideas.items && ideas.items.length) body = ideas.items.map((it, k) => `
      <article class="tr-icard">
        <div class="tr-icard-top">
          <span class="tr-num">${faNum(k + 1)}</span>
          <h4>${esc(it.title)}</h4>
          ${it.score ? `<span class="score">${faNum(it.score)}/۱۰</span>` : ''}
        </div>
        ${it.pillar ? `<div class="idea-meta"><span class="pill">${esc(it.pillar)}</span></div>` : ''}
        ${it.hook ? `<div class="hook"><em>هوک سه‌ثانیه‌ای</em>${esc(it.hook)}</div>` : ''}
        ${it.points && it.points.length ? `<div class="tr-ipoints"><b>گوینده چه گفته</b><ul>
          ${it.points.map(p => `<li>${p.t ? `<button class="tr-t" dir="ltr" data-seek="${esc(p.t)}" title="برو به همین‌جای متن">${trTime(p.t)}</button>` : ''}
            <span>${esc(p.text)}</span></li>`).join('')}</ul></div>` : ''}
        ${it.angle ? `<p class="tr-iangle"><b>زاویه‌ی تو:</b> ${esc(it.angle)}</p>` : ''}
        ${it.caution ? `<p class="tr-icaution"><b>احتیاط:</b> ${esc(it.caution)}</p>` : ''}
        <div class="tr-icard-foot">${it.sent
          ? `<button class="tr-link tr-isent" data-idea="${esc(it.sent)}">✓ در بانک ایده — باز کن</button>`
          : `<button class="btn primary" data-isend="${k}">+ بفرست به بانک ایده</button>`}</div>
      </article>`).join('');
  else body = `<p class="tr-ideas-intro">${full
      ? 'هر وقت خواستی، از روی همین متن ایده‌های ریلز را پیشنهاد می‌دهم: تایتل، هوک سه‌ثانیه‌ای و نکته‌هایی که گوینده درباره‌ی هر موضوع گفته، با زمانش.'
      : 'وقتی ترجمه کامل شد، می‌توانی از روی کل متن ایده‌ی ریلز بسازی.'}</p>
      ${job.state === 'error' ? `<p class="tr-icaution">✕ ${esc(job.error || 'ساخته نشد')}</p>` : ''}
      <button class="btn primary" id="trIdeasGo" ${full ? '' : 'disabled'}>ساخت ایده از روی این متن</button>`;
  box.innerHTML = head + body;
  const go_ = $('#trIdeasGo');
  if (go_) go_.onclick = trMakeIdeas;
}

async function trMakeIdeas(e) {
  if (e.currentTarget.dataset.again &&
      !confirm('ایده‌های فعلی جایشان را به ایده‌های تازه می‌دهند (نسخه‌ی فعلی در reel-ideas.prev.json می‌ماند). ادامه؟')) return;
  const r = await post('/api/tr/ideas', { slug:TR.slug });
  if (!r.ok) return toast(r.data.error || 'شروع نشد');
  TR.data.ideas_job = { state:'running' }; trRenderIdeas(); trPollIdeas();
}

function trPollIdeas() {
  clearInterval(TR.ipoll);
  const slug = TR.slug;
  TR.ipoll = setInterval(async () => {
    if (!$('#trIdeas') || TR.slug !== slug) return clearInterval(TR.ipoll);
    const d = await api(`/api/tr/ideas?slug=${encodeURIComponent(slug)}`); if (!d) return;
    if (d.job.state === 'running') return;
    clearInterval(TR.ipoll);
    TR.data.ideas_job = d.job; TR.data.ideas = d.ideas; trRenderIdeas();
    if (d.job.state === 'done') toast(`✓ ${faNum((d.ideas.items || []).length)} ایده آماده شد`);
  }, 4000);
}

async function trSendSuggested(b) {
  const k = +b.dataset.isend, it = TR.data.ideas.items[k];
  b.disabled = true;
  const r = await post('/api/tr/ideas/send', { slug:TR.slug, index:k });
  if (!r.ok && !r.data.id) { b.disabled = false; return toast(r.data.error || 'فرستاده نشد'); }
  it.sent = r.data.id;
  if (r.data.picks) TR.sent = r.data.picks.sent;
  await loadState();
  trRenderIdeas(); trRenderPicks(); trMark();
  toast(r.ok ? '✓ به بانک ایده رفت' : 'این ایده قبلاً در بانک ایده هست');
}

// زمانِ یک نکته ← پاراگرافی از متن که آن لحظه در آن است
function trSeek(t) {
  const sec = x => String(x).split(':').reduce((a, n) => a * 60 + (+n || 0), 0), want = sec(t);
  const rows = $$('#trText .tr-row');
  const row = rows.filter(r => sec(r.querySelector('.tr-p').dataset.t) <= want).pop() || rows[0];
  if (!row) return;
  row.scrollIntoView({ behavior:'smooth', block:'center' });
  row.classList.add('flash'); setTimeout(() => row.classList.remove('flash'), 1600);
}

/* ---------------- انتخاب ---------------- */
function trSelection() {
  const sel = getSelection();
  if (!sel || !sel.rangeCount || sel.isCollapsed) return null;
  const r = sel.getRangeAt(0), root = $('#trText');
  if (!root || !root.contains(r.commonAncestorContainer)) return null;
  // انتخاب با ماوس اغلب وسط کلمه شروع یا تمام می‌شود؛ تا مرز کلمه باز می‌شود تا تکه‌ها کلمه‌ی بریده نداشته باشند
  const isW = c => !!c && /[\p{L}\p{N}\p{M}\u200c'’-]/u.test(c);
  const offset = (p, node, off) => { const y = document.createRange(); y.selectNodeContents(p); y.setEnd(node, off); return y.toString().length; };
  const parts = $$('.tr-p', root).filter(p => r.intersectsNode(p)).map(p => {
    const pt = p.textContent;
    let a = p.contains(r.startContainer) ? offset(p, r.startContainer, r.startOffset) : 0;
    let b = p.contains(r.endContainer) ? offset(p, r.endContainer, r.endOffset) : pt.length;
    if (isW(pt[a])) while (a > 0 && isW(pt[a - 1])) a--;
    if (b > 0 && isW(pt[b - 1])) while (b < pt.length && isW(pt[b])) b++;
    return { id:p.dataset.id, t:p.dataset.t, text:pt.slice(a, b).replace(/\s+/g, ' ').trim() };
  }).filter(x => x.text);
  if (!parts.length) return null;
  return { pids:parts.map(x => x.id), t:parts[0].t, text:parts.map(x => x.text).join('\n\n') };
}

function trShowFloat() {
  const f = $('#trFloat'); if (!f) return;
  const pick = trSelection();
  if (!pick) { f.hidden = true; return; }
  const rects = getSelection().getRangeAt(0).getClientRects();
  const last = rects[rects.length - 1]; if (!last) { f.hidden = true; return; }
  const card = TR.pending[TR.active];
  f.innerHTML = `<button data-tr="new">+ ایده‌ی تازه</button>
    ${card ? `<button data-tr="add">+ به ایده‌ی ${faNum(TR.active + 1)}</button>` : ''}`;
  f.hidden = false;
  const w = f.offsetWidth;
  const x = Math.min(Math.max(8, last.left + window.scrollX - w / 2), document.documentElement.clientWidth - w - 8);
  f.style.left = x + 'px';
  f.style.top = (last.bottom + window.scrollY + 8) + 'px';
}

function trAdd(mode) {
  const pick = trSelection();
  if (!pick) return toast('اول تکه‌ای از متن را انتخاب کن');
  if (mode === 'add' && TR.pending[TR.active]) {
    const card = TR.pending[TR.active];
    if (card.passages.some(p => p.text === pick.text)) return toast('این تکه قبلاً در همین ایده هست');
    card.passages.push(pick);
    card.passages.sort((a, b) => trByPid(a.pids[0], b.pids[0]));
    toast(`✓ به ایده‌ی ${faNum(TR.active + 1)} اضافه شد`);
  } else {
    TR.pending.push({ title:'', note:'', passages:[pick] });
    TR.active = TR.pending.length - 1;
    toast(`✓ ایده‌ی ${faNum(TR.active + 1)} ساخته شد`);
  }
  getSelection().removeAllRanges(); $('#trFloat').hidden = true;
  trRenderPicks(); trMark(); trQueueSave();
}

function trMark() {
  const by = {};
  TR.pending.forEach((c, k) => c.passages.forEach(p => p.pids.forEach(id => (by[id] = by[id] || new Set()).add(k + 1))));
  const sent = new Set(TR.sent.flatMap(s => s.pids || []));
  $$('#trText .tr-row').forEach(row => {
    const id = row.dataset.id, nums = by[id] ? [...by[id]] : [];
    row.classList.toggle('picked', nums.length > 0);
    row.classList.toggle('sent', !nums.length && sent.has(id));
    const b = row.querySelector('.tr-badge');
    b.textContent = nums.length ? nums.map(faNum).join('،') : sent.has(id) ? '✓' : '';
    b.title = nums.length ? 'در ایده‌ی انتخاب‌شده' : sent.has(id) ? 'قبلاً به بانک ایده رفته' : '';
  });
  trDock();
}

/* ---------------- فهرست انتخاب‌ها (پایین متن) ---------------- */
function trRenderPicks() {
  const box = $('#trPicks'); if (!box) return;
  const n = TR.pending.reduce((a, c) => a + c.passages.length, 0);
  box.innerHTML = `
    <h3>بخش‌های انتخاب‌شده</h3>
    ${TR.pending.length ? TR.pending.map((c, k) => `
      <article class="tr-card ${k === TR.active ? 'on' : ''}" data-k="${k}">
        <div class="tr-card-head">
          <span class="tr-num">${faNum(k + 1)}</span>
          <input class="tr-in" data-k="${k}" data-f="title" value="${esc(c.title)}"
            placeholder="عنوان ایده (اختیاری — خالی بماند، از اول متن ساخته می‌شود)">
          <button class="tr-x" data-delcard="${k}" title="حذف این ایده">✕</button>
        </div>
        ${c.passages.map((p, j) => `
          <div class="tr-pass">
            <button class="tr-t" dir="ltr" data-goto="${esc(p.pids[0])}" title="برو به همین‌جای متن">${trTime(p.t)}</button>
            <div class="tr-pass-text">${p.text.split('\n\n').map(x => `<p>${inline(x)}</p>`).join('')}</div>
            <button class="tr-x" data-delpass="${k}.${j}" title="حذف این تکه">✕</button>
          </div>`).join('')}
        <input class="tr-in tr-note" data-k="${k}" data-f="note" value="${esc(c.note)}"
          placeholder="زاویه‌ی خودت (اختیاری): چرا این برایت جالب است؟ می‌خواهی درباره‌اش چه بگویی؟">
        <div class="tr-card-foot">${k === TR.active
          ? '<span class="tr-active">تکه‌های بعدی با «+ به ایده‌ی ' + faNum(k + 1) + '» به همین ایده اضافه می‌شوند</span>'
          : `<button class="tr-link" data-use="${k}">تکه‌های بعدی به این ایده اضافه شوند</button>`}</div>
      </article>`).join('')
    : `<p class="tr-empty">هنوز چیزی انتخاب نکرده‌ای. متن بالا را بخوان و هر تکه‌ای که موضوع خوبی است انتخاب کن.</p>`}
    ${TR.pending.length ? `<div class="tr-send">
        <span>${faNum(TR.pending.length)} ایده، ${faNum(n)} تکه</span><span class="grow"></span>
        <button class="btn primary" id="trSend">ثبت همه در بانک ایده</button>
      </div>` : ''}
    ${TR.sent.length ? `<div class="tr-sent"><h4>قبلاً از این ویدیو به بانک ایده رفته</h4>
        ${TR.sent.map(s => `<button class="tr-link" data-idea="${esc(s.idea)}">${esc(s.title)}</button>`).join('')}
      </div>` : ''}`;
  const send = $('#trSend'); if (send) send.onclick = trSend;
}

function trQueueSave() {
  clearTimeout(TR.saveT);
  TR.saveT = setTimeout(trSave, 600);
}
async function trSave() {
  clearTimeout(TR.saveT); TR.saveT = null;
  TR.saving = post('/api/tr/picks', { slug:TR.slug, pending:TR.pending });
  const r = await TR.saving; TR.saving = null;
  if (!r.ok) toast('انتخاب‌ها ذخیره نشد');
  return r.ok;
}

async function trSend() {
  const b = $('#trSend'); b.disabled = true;
  // ذخیره‌ای که دیرتر از ثبت برسد، انتخاب‌های فرستاده‌شده را دوباره «منتظر» می‌کرد
  clearTimeout(TR.saveT); TR.saveT = null;
  if (TR.saving) await TR.saving;
  const count = TR.pending.length;
  const r = await post('/api/tr/send', { slug:TR.slug, pending:TR.pending });
  if (!r.ok) { b.disabled = false; return toast(r.data.error || 'ثبت نشد'); }
  TR.pending = []; TR.sent = r.data.picks.sent; TR.active = 0;
  await loadState();
  trRenderPicks(); trMark();
  const box = $('#trPicks');
  box.insertAdjacentHTML('afterbegin', `<div class="tr-done">✓ ${faNum(count)} ایده به بانک ایده رفت.
    <button class="btn primary" id="trToIdeas">برو به بانک ایده</button></div>`);
  $('#trToIdeas').onclick = () => { S.filter = 'all'; go('ideas'); window.scrollTo(0, 0); };
  toast(`✓ ${faNum(count)} ایده ثبت شد`);
}

function trDock() {
  const dock = $('#trDock'); if (!dock) return;
  const n = TR.pending.reduce((a, c) => a + c.passages.length, 0);
  dock.textContent = `${faNum(TR.pending.length)} ایده، ${faNum(n)} تکه انتخاب شده — ↓ دیدن و ثبت`;
  dock.dataset.has = TR.pending.length ? '1' : '';
  dock.hidden = !TR.pending.length || dock.dataset.near === '1';
}

/* ---------------- رویدادها ---------------- */
function trWireReader() {
  const f = $('#trFloat');
  f.addEventListener('mousedown', e => e.preventDefault());      // انتخاب متن با کلیک روی دکمه از بین نرود
  f.addEventListener('click', e => { const b = e.target.closest('[data-tr]'); if (b) trAdd(b.dataset.tr); });

  const text = $('#trText');
  text.addEventListener('mouseup', () => setTimeout(trShowFloat, 0));
  text.addEventListener('keyup', e => { if (e.shiftKey) trShowFloat(); });

  // نوار پایین صفحه فقط وقتی فهرست انتخاب‌ها دیده نمی‌شود
  if (TR.dockObs) TR.dockObs.disconnect();
  TR.dockObs = new IntersectionObserver(([en]) => {
    const d = $('#trDock'); if (!d) return;
    d.dataset.near = en.isIntersecting ? '1' : ''; trDock();
  });
  TR.dockObs.observe($('#trPicks'));
}

// #page بین صفحه‌ها می‌ماند، پس این‌ها یک بار روی document وصل می‌شوند و فقط در صفحه‌ی خواندن کار می‌کنند
document.addEventListener('input', e => {
  const t = e.target; if (!$('#trText') || !t.matches('.tr-in')) return;
  const c = TR.pending[+t.dataset.k]; if (!c) return;
  c[t.dataset.f] = t.value; trQueueSave();
});
document.addEventListener('click', e => {
  if (!$('#trText')) return;
  const t = e.target;
  let b;
  if ((b = t.closest('[data-delcard]'))) {
    const k = +b.dataset.delcard;
    if (!confirm(`ایده‌ی ${faNum(k + 1)} و همه‌ی تکه‌هایش از انتخاب‌ها حذف شود؟`)) return;
    TR.pending.splice(k, 1);
    TR.active = Math.min(TR.active > k ? TR.active - 1 : TR.active, Math.max(0, TR.pending.length - 1));
  } else if ((b = t.closest('[data-delpass]'))) {
    const [k, j] = b.dataset.delpass.split('.').map(Number);
    TR.pending[k].passages.splice(j, 1);
    if (!TR.pending[k].passages.length) {
      TR.pending.splice(k, 1);
      TR.active = Math.min(TR.active > k ? TR.active - 1 : TR.active, Math.max(0, TR.pending.length - 1));
    }
  } else if ((b = t.closest('[data-use]'))) {
    TR.active = +b.dataset.use;
  } else if ((b = t.closest('[data-seek]'))) {
    return trSeek(b.dataset.seek);
  } else if ((b = t.closest('[data-isend]'))) {
    return trSendSuggested(b);
  } else if ((b = t.closest('[data-goto]'))) {
    const row = $(`.tr-row[data-id="${b.dataset.goto}"]`);
    if (row) { row.scrollIntoView({ behavior:'smooth', block:'center' });
      row.classList.add('flash'); setTimeout(() => row.classList.remove('flash'), 1600); }
    return;
  } else if ((b = t.closest('[data-idea]'))) {
    S.openIdea = b.dataset.idea; go('ideas'); return window.scrollTo(0, 0);
  } else if (t.id === 'trDock') {
    return $('#trPicks').scrollIntoView({ behavior:'smooth', block:'start' });
  } else return;
  trRenderPicks(); trMark(); trQueueSave();
});

document.addEventListener('selectionchange', () => {
  const f = $('#trFloat');
  if (f && !f.hidden && (!getSelection().rangeCount || getSelection().isCollapsed)) f.hidden = true;
});

window.mountTrPanel = mountTrPanel;
window.viewTranslations = viewTranslations;
window.viewReader = viewReader;
window.openReader = openReader;
