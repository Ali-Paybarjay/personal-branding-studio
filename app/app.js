/* ================= ابزارها ================= */
const $  = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;' }[c]));
const faNum = n => String(n).replace(/\d/g, d => '۰۱۲۳۴۵۶۷۸۹'[d]);
const enNum = s => String(s).replace(/[۰-۹]/g, d => '۰۱۲۳۴۵۶۷۸۹'.indexOf(d));

function toast(msg) {
  const t = $('#toast'); t.textContent = msg; t.hidden = false;
  clearTimeout(t._t); t._t = setTimeout(() => (t.hidden = true), 1800);
}
const api  = async p => { const r = await fetch(p); return r.ok ? r.json() : null; };
const post = async (p, body) => {
  const r = await fetch(p, { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body) });
  return { ok: r.ok, data: await r.json().catch(() => ({})) };
};

/* ================= مارک‌داون ================= */
function inline(s) {
  return esc(s)
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/(^|[\s(])\*([^*\n]+)\*/g, '$1<em>$2</em>')
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
}
function md(src) {
  const lines = String(src).split('\n'); let out = '', i = 0;
  const table = () => {
    const rows = [];
    while (i < lines.length && /^\s*\|/.test(lines[i])) {
      rows.push(lines[i].trim().replace(/^\||\|$/g,'').split('|').map(c=>c.trim())); i++;
    }
    if (rows.length < 2) return rows.map(r => `<p>${inline(r.join(' | '))}</p>`).join('');
    const body = rows.filter((_, n) => n !== 1); const head = body.shift();
    return `<table><thead><tr>${head.map(c=>`<th>${inline(c)}</th>`).join('')}</tr></thead>`
         + `<tbody>${body.map(r=>`<tr>${r.map(c=>`<td>${inline(c)}</td>`).join('')}</tr>`).join('')}</tbody></table>`;
  };
  while (i < lines.length) {
    const l = lines[i];
    if (!l.trim()) { i++; continue; }
    if (/^\s*\|/.test(l)) { out += table(); continue; }
    if (/^(---+|\*\*\*+)\s*$/.test(l)) { out += '<hr>'; i++; continue; }
    let m;
    if ((m = l.match(/^@(en|fa)\s+(.*)$/))) { out += `<p class="${m[1]}">${inline(m[2])}</p>`; i++; continue; }
    if ((m = l.match(/^(#{1,6})\s+(.*)$/))) { const n = Math.min(m[1].length,3); out += `<h${n}>${inline(m[2])}</h${n}>`; i++; continue; }
    if (/^\s*>/.test(l)) {
      const buf = [];
      while (i < lines.length && /^\s*>/.test(lines[i])) { buf.push(lines[i].replace(/^\s*>\s?/,'')); i++; }
      out += `<blockquote>${md(buf.join('\n'))}</blockquote>`; continue;
    }
    if (/^\s*[-*+]\s+/.test(l) || /^\s*\d+[.)]\s+/.test(l)) {
      const ord = /^\s*\d+[.)]\s+/.test(l); const items = [];
      while (i < lines.length && (/^\s*[-*+]\s+/.test(lines[i]) || /^\s*\d+[.)]\s+/.test(lines[i]))) {
        items.push(lines[i].replace(/^\s*(?:[-*+]|\d+[.)])\s+/,'')); i++;
      }
      const t = ord ? 'ol' : 'ul';
      out += `<${t}>${items.map(x=>`<li>${inline(x)}</li>`).join('')}</${t}>`; continue;
    }
    const buf = [];
    while (i < lines.length && lines[i].trim() &&
      !/^(#{1,6}\s|\s*>|\s*[-*+]\s|\s*\d+[.)]\s|\s*\||@(en|fa)\s|---+\s*$)/.test(lines[i])) { buf.push(lines[i]); i++; }
    if (buf.length) out += `<p>${inline(buf.join(' '))}</p>`; else i++;
  }
  return out;
}

/* ================= وضعیت ================= */
const S = {
  section: 'dashboard', modules: [], videos: [], ideas: [], sources: [], job: {}, profile: {}, platform: 'mac',
  slug: null, tab: 'reels', cache: {}, reels: [], scripts: [], filter: 'all', openReel: null, openIdea: null, capture: 'text',
  read: null,   // slug ویدیویی که صفحه‌ی خواندنِ ترجمه‌اش باز است (translate.js)
};
// پیش‌فرض؛ loadState آن را با پیلرهای هسته‌ی برند جایگزین می‌کند
const PILLARS = ['آموزشی','تجربه و داستان','دیدگاه و تحلیل','پشت‌صحنه'];
const STATUS = { idea:'خام', approved:'تأییدشده', producing:'در تولید', done:'منتشرشده' };

async function loadState() {
  const d = await api('/api/state'); if (!d) return;
  Object.assign(S, { modules:d.modules, videos:d.videos, ideas:d.ideas, sources:d.sources, job:d.job,
                     profile:d.profile || {}, platform:d.platform || 'mac' });
  if (Array.isArray(d.pillars) && d.pillars.length) PILLARS.splice(0, PILLARS.length, ...d.pillars);
}
async function getFile(name) {
  const k = S.slug + '|' + name;
  if (k in S.cache) return S.cache[k];
  const r = await api(`/api/file?video=${encodeURIComponent(S.slug)}&name=${name}`);
  return (S.cache[k] = r && r.text ? r.text : null);
}

/* ================= ناوبری ================= */
function renderNav() {
  $('#nav').innerHTML = S.modules.map(m =>
    `<button data-sec="${m.key}" class="${m.key === S.section ? 'on' : ''}" ${m.ready ? '' : 'disabled'}>${esc(m.label)}</button>`
  ).join('');
}
function go(sec) {
  S.section = sec; S.read = null; renderNav();
  $('#videoSelect').hidden = sec !== 'reels';
  history.replaceState(null, '', `?s=${sec}`);
  window.scrollTo(0, 0);
  ({ start:window.viewStart, settings:window.viewSettings,
     dashboard:viewDashboard, brand:window.viewBrand, translations:window.viewTranslations, ideas:viewIdeas, reels:viewReels,
     story:window.viewStory, advisor:window.viewAdvisor, analytics:window.viewInsta, carousel:window.viewCarousel,
     video: S.platform === 'mac' ? window.viewVideo : window.viewVideoMacOnly }[sec] || viewDashboard)();
}

/* ================= داشبورد ================= */
function buildBarHTML() {
  return `<section class="build" style="padding:0 0 4px">
    <div class="build-row">
      <input id="urlInput" type="url" dir="ltr" placeholder="لینک یوتیوب را اینجا بگذار…" autocomplete="off">
      <button id="buildBtn" class="btn primary">بساز</button>
    </div>
    <div id="buildStatus" class="build-status" hidden></div>
  </section>`;
}
function viewDashboard() {
  const ready = S.videos.filter(v => v.has && v.has.reels).length;
  const byStatus = k => S.ideas.filter(i => i.status === k).length;
  $('#page').innerHTML = `
    <div class="page-head"><h2>${S.profile.name ? `سلام ${esc(S.profile.name)}` : 'داشبورد'}</h2><p>وضعیت استودیو در یک نگاه</p></div>
    <div id="nextStep"></div>
    <div class="stats">
      <div class="stat"><b>${faNum(S.ideas.length)}</b><span>ایده در بانک</span></div>
      <div class="stat"><b>${faNum(byStatus('approved'))}</b><span>تأییدشده</span></div>
      <div class="stat"><b>${faNum(S.videos.length)}</b><span>منبع پردازش‌شده</span></div>
      <div class="stat"><b>${faNum(ready)}</b><span>منبع با ریلز آماده</span></div>
    </div>
    <div class="panel" style="margin-bottom:16px" id="trPanel"></div>
    <div class="cards2">
      <div class="panel"><h3>بخش‌های استودیو</h3><ul class="roadmap">
        ${S.modules.filter(m => !['start', 'dashboard', 'settings'].includes(m.key)).map(m => `<li class="done"><a href="?s=${m.key}" data-go="${m.key}">${esc(m.label)}</a></li>`).join('')}
      </ul></div>
      <div class="panel"><h3>ایده‌های اخیر</h3><ul>
        ${S.ideas.slice(0,5).map(i => `<li>${esc(i.title)}</li>`).join('') || '<li>هنوز ایده‌ای نیست</li>'}
      </ul></div>
    </div>`;
  if (window.mountTrPanel) mountTrPanel($('#trPanel'));
  if (window.mountNextStep) mountNextStep($('#nextStep'));
}

/* هسته‌ی برند در brand.js است */

/* ================= بانک ایده ================= */
// Only the changed fields go up — never this page's whole list — so a tab left
// open on the Mac can't undo what was just edited on the phone, or vice versa.
async function patchIdea(id, fields) {
  const r = await post('/api/idea/edit', { id, ...fields });
  if (!r.ok) { toast(r.data.error || 'ذخیره نشد'); return null; }
  const k = S.ideas.findIndex(i => i.id === id);
  if (k >= 0) S.ideas[k] = r.data.idea;
  return r.data.idea;
}
async function deleteIdea(id) {
  // an empty list + the id: the server keeps every other idea exactly as it is on disk
  const r = await post('/api/ideas', { ideas: [], deleted: [id] });
  if (!r.ok) { toast('حذف نشد'); return false; }
  await loadState(); return true;
}
const STEPS = [['analyze','تحلیل'],['enrich','جستجوی وب'],['produce','ساخت ریلز']];
const VOICE_STEP = ['transcribe','رونویسی صدا'];
const stepsFor = it => (it.audio ? [VOICE_STEP, ...STEPS] : STEPS);

function captureHTML() {
  const tab = k => S.capture === k ? 'on' : '';
  return `<div class="panel capture">
    <div class="cap-tabs">
      <button data-cap="text" class="${tab('text')}">متن</button>
      <button data-cap="url"  class="${tab('url')}">لینک مقاله</button>
      <button data-cap="voice" class="${tab('voice')}">🎙 ضبط ویس</button>
      <button data-cap="file" class="${tab('file')}">فایل</button>
    </div>
    ${S.capture === 'text' ? `
      <textarea id="capText" class="cap-text" placeholder="ایده‌ات را بنویس، یا تکه‌ای از یک مقاله را اینجا بچسبان…&#10;&#10;مثال: می‌خوام یه ریلز بسازم درباره‌ی اینکه چرا مهارت prompt نوشتن داره از کدنویسی مهم‌تر می‌شه"></textarea>
      <p id="capDraftHint" class="cap-hint" hidden>${draftPending() ? 'در حال ذخیره…' : DRAFT_SAVED}</p>`
    : S.capture === 'url' ? `
      <input id="capUrl" class="cap-input" dir="ltr" placeholder="https://…">
      <p class="cap-hint">محتوای این آدرس در مرحله‌ی تحلیل خوانده می‌شود.</p>`
    : S.capture === 'voice' ? `
      <div class="rec">
        <button id="recBtn" class="rec-btn" title="شروع ضبط"><span class="rec-dot"></span></button>
        <div class="rec-info">
          <b id="recState">آماده‌ی ضبط</b>
          <span id="recTime">۰:۰۰</span>
          <span id="recHint" class="cap-hint">دکمه را بزن و حرف بزن. تا حدود ۸ دقیقه.</span>
        </div>
        <audio id="recPlay" controls hidden></audio>
      </div>`
    : `
      <div id="drop" class="drop">
        <b>فایل را اینجا رها کن</b>
        <span>PDF · Word · متن · صوت</span>
        <input type="file" id="capFile" hidden>
      </div>`}
    <div class="rowbar" style="margin:14px 0 0">
      <select id="capPillar">
        <option value="">— پیلر (اختیاری) —</option>
        ${PILLARS.map(p=>`<option>${p}</option>`).join('')}
      </select>
      <span class="grow"></span>
      <button id="capSave" class="btn primary">ثبت ایده</button>
    </div>
  </div>`;
}

function viewIdeas() {
  if (S.openIdea) return viewIdeaDetail();
  const counts = { all: S.ideas.length };
  Object.keys(STATUS).forEach(k => counts[k] = S.ideas.filter(i => i.status === k).length);
  const list = S.filter === 'all' ? S.ideas : S.ideas.filter(i => i.status === S.filter);

  $('#page').innerHTML = `
    <div class="page-head"><h2>بانک ایده</h2>
      <p>ایده را می‌گیرد، تحلیل می‌کند، وب را می‌گردد، و به ریلز تبدیلش می‌کند</p></div>
    ${captureHTML()}
    <div class="filters" style="margin-top:24px">
      <button data-f="all" class="${S.filter==='all'?'on':''}">همه (${faNum(counts.all)})</button>
      ${Object.entries(STATUS).map(([k,l])=>`<button data-f="${k}" class="${S.filter===k?'on':''}">${l} (${faNum(counts[k])})</button>`).join('')}
    </div>
    ${list.length ? list.map(ideaHTML).join('') : '<div class="empty">ایده‌ای در این وضعیت نیست.</div>'}
    <p class="cap-hint" style="margin-top:24px">مدل هوش مصنوعی هر مرحله (Sonnet یا Opus) از تب <a href="?s=settings" data-go="settings">تنظیمات</a> عوض می‌شود.</p>`;
  wireCapture();
  $$('.filters button').forEach(b => b.onclick = () => { S.filter = b.dataset.f; viewIdeas(); });
  $$('.idea select').forEach(sel => sel.onchange = async e => {
    e.stopPropagation();
    await patchIdea(sel.dataset.id, { status: sel.value }); viewIdeas();  // a failed save snaps the select back
  });
  $$('.idea .del').forEach(b => b.onclick = async e => {
    e.stopPropagation();
    if (!confirm('این ایده حذف شود؟')) return;
    if (await deleteIdea(b.dataset.id)) { toast('حذف شد'); viewIdeas(); }
  });
  $$('.idea-main').forEach(m => m.onclick = () => { S.openIdea = m.dataset.id; viewIdeas(); });
}

function wireCapture() {
  $$('.cap-tabs button').forEach(b => b.onclick = () => { S.capture = b.dataset.cap; viewIdeas(); });
  const drop = $('#drop'), fin = $('#capFile');
  if (drop) {
    drop.onclick = () => fin.click();
    fin.onchange = () => fin.files[0] && pickFile(fin.files[0]);
    ['dragenter','dragover'].forEach(ev => drop.addEventListener(ev, e => {
      e.preventDefault(); drop.classList.add('over'); }));
    ['dragleave','drop'].forEach(ev => drop.addEventListener(ev, e => {
      e.preventDefault(); drop.classList.remove('over'); }));
    drop.addEventListener('drop', e => { const f = e.dataTransfer.files[0]; if (f) pickFile(f); });
  }
  wireRecorder();
  const ta = $('#capText'), url = $('#capUrl'), pil = $('#capPillar');
  if (ta) ta.addEventListener('input', () => { growCapText(); setDraft({ text: ta.value }); });
  if (url) url.addEventListener('input', () => setDraft({ url: url.value }));
  if (pil) pil.onchange = () => setDraft({ pillar: pil.value });
  // every re-render (refresh, filter click, tab switch) rebuilds these fields — refill them from the draft
  fillCapture();
  const save = $('#capSave'); if (save) save.onclick = submitCapture;
}

/* ---- پیش‌نویس کادر ایده: روی سرور، تا هر مرورگری همان را ببیند ---- */
// d: the draft as this page knows it; patch: fields typed here that haven't reached the server yet
const DRAFT = { d: {}, patch: {}, timer: null };
const DRAFT_SAVED = '✓ پیش‌نویس ذخیره شد — در هر مرورگری که استودیو را باز کنی همین را می‌بینی';
const draftPending = () => Object.keys(DRAFT.patch).length > 0;

function fillCapture() {
  const d = DRAFT.d, ta = $('#capText'), url = $('#capUrl'), pil = $('#capPillar');
  if (ta) { ta.value = d.text || ''; growCapText(); }
  if (url) url.value = d.url || '';
  if (pil) pil.value = d.pillar || '';
}
// a textarea as tall as its text, so it's read without scrolling inside it
function fitHeight(ta) {
  // height:auto shrinks the page for a moment; keep the window where it was
  const y = window.scrollY;
  ta.style.height = 'auto'; ta.style.height = (ta.scrollHeight + 2) + 'px';
  window.scrollTo(0, y);
}
function growCapText() {
  const ta = $('#capText'), hint = $('#capDraftHint'); if (!ta) return;
  fitHeight(ta);
  if (hint) hint.hidden = !ta.value.trim();
}
const draftHint = msg => { const h = $('#capDraftHint'); if (h) h.textContent = msg; };

async function pullDraft() {
  if (draftPending()) return;                 // never overwrite typing that hasn't been saved yet
  const d = await api('/api/idea/draft').catch(() => null);
  if (!d || draftPending()) return;
  const changed = JSON.stringify(d) !== JSON.stringify(DRAFT.d);
  DRAFT.d = d; if (changed) fillCapture();
}
function setDraft(patch) {
  Object.assign(DRAFT.d, patch); Object.assign(DRAFT.patch, patch);
  draftHint('در حال ذخیره…');
  clearTimeout(DRAFT.timer); DRAFT.timer = setTimeout(pushDraft, 400);
}
async function pushDraft() {
  clearTimeout(DRAFT.timer);
  if (!draftPending()) return;
  const patch = DRAFT.patch; DRAFT.patch = {};
  const r = await post('/api/idea/draft', patch).catch(() => ({ ok: false }));
  if (r.ok) { if (!draftPending()) draftHint(DRAFT_SAVED); return; }
  DRAFT.patch = { ...patch, ...DRAFT.patch };  // keep it and try again
  draftHint('ذخیره نشد — دوباره تلاش می‌کنم…');
  DRAFT.timer = setTimeout(pushDraft, 3000);
}
// a refresh or a closed tab inside the 400ms wait still gets its last keystrokes out
addEventListener('pagehide', () => {
  if (draftPending()) navigator.sendBeacon('/api/idea/draft', JSON.stringify(DRAFT.patch));
});
// coming back to this window picks up whatever was typed in another browser meanwhile
addEventListener('focus', pullDraft);
document.addEventListener('visibilitychange', () => { if (!document.hidden) pullDraft(); });
const REC = { mr:null, chunks:[], blob:null, t0:0, timer:null, stream:null };

function recFmt(sec){ return `${faNum(Math.floor(sec/60))}:${faNum(String(Math.floor(sec%60)).padStart(2,'0'))}`; }

function wireRecorder() {
  const btn = $('#recBtn'); if (!btn) return;
  btn.onclick = () => REC.mr && REC.mr.state === 'recording' ? stopRec() : startRec();
}

async function startRec() {
  try {
    REC.stream = await navigator.mediaDevices.getUserMedia({ audio:{
      echoCancellation:true, noiseSuppression:true, channelCount:1 } });
  } catch (e) {
    $('#recState').textContent = 'دسترسی به میکروفون داده نشد';
    $('#recHint').textContent = 'در تنظیمات مرورگر اجازه‌ی میکروفون را برای این صفحه روشن کن.';
    return;
  }
  const types = ['audio/webm;codecs=opus','audio/webm','audio/mp4','audio/ogg;codecs=opus'];
  const mime = types.find(t => window.MediaRecorder && MediaRecorder.isTypeSupported(t)) || '';
  REC.chunks = []; REC.blob = null;
  REC.mr = new MediaRecorder(REC.stream, mime ? { mimeType:mime, audioBitsPerSecond:32000 } : {});
  REC.mr.ondataavailable = e => e.data.size && REC.chunks.push(e.data);
  REC.mr.onstop = () => {
    REC.blob = new Blob(REC.chunks, { type: REC.mr.mimeType || 'audio/webm' });
    REC.stream.getTracks().forEach(t => t.stop());
    const el = $('#recPlay'); if (el) { el.src = URL.createObjectURL(REC.blob); el.hidden = false; }
    const secs = (Date.now() - REC.t0)/1000;
    $('#recState').textContent = 'ضبط شد';
    $('#recHint').textContent = `${recFmt(secs)} · ${faNum((REC.blob.size/1e6).toFixed(1))} مگابایت — «ثبت ایده» را بزن یا دوباره ضبط کن.`;
    $('#recBtn').classList.remove('on');
  };
  REC.mr.start(250); REC.t0 = Date.now();
  $('#recBtn').classList.add('on');
  $('#recState').textContent = 'در حال ضبط…';
  $('#recHint').textContent = 'برای پایان دوباره دکمه را بزن.';
  $('#recPlay').hidden = true;
  clearInterval(REC.timer);
  REC.timer = setInterval(() => {
    const s = (Date.now() - REC.t0)/1000;
    $('#recTime').textContent = recFmt(s);
    if (s > 480) { $('#recHint').textContent = '⚠ از ۸ دقیقه گذشت — بهتر است تمامش کنی.'; }
  }, 250);
}
function stopRec() {
  clearInterval(REC.timer);
  if (REC.mr && REC.mr.state === 'recording') REC.mr.stop();
}

let PENDING_FILE = null;
function pickFile(f) {
  PENDING_FILE = f;
  const d = $('#drop');
  d.innerHTML = `<b>${esc(f.name)}</b><span>${faNum((f.size/1024/1024).toFixed(1))} مگابایت — «ثبت ایده» را بزن</span>`;
}
async function submitCapture() {
  const btn = $('#capSave'); btn.disabled = true;
  const pillar = $('#capPillar').value;
  let payload = null;
  if (S.capture === 'text') {
    const t = $('#capText').value.trim();
    if (!t) { btn.disabled = false; return toast('متن خالی است'); }
    payload = { kind:'text', text:t, pillar };
  } else if (S.capture === 'url') {
    const u = $('#capUrl').value.trim();
    if (!u) { btn.disabled = false; return toast('آدرس را بگذار'); }
    payload = { kind:'url', url:u, pillar };
  } else if (S.capture === 'voice') {
    if (REC.mr && REC.mr.state === 'recording') { stopRec(); await new Promise(r => setTimeout(r, 400)); }
    if (!REC.blob) { btn.disabled = false; return toast('هنوز چیزی ضبط نشده'); }
    const ext = (REC.blob.type.includes('mp4') ? 'm4a' : REC.blob.type.includes('ogg') ? 'ogg' : 'webm');
    const data = await new Promise(res => {
      const r = new FileReader(); r.onload = () => res(r.result); r.readAsDataURL(REC.blob); });
    payload = { kind:'file', filename:`voice-${Date.now()}.${ext}`, data, pillar };
  } else {
    if (!PENDING_FILE) { btn.disabled = false; return toast('فایلی انتخاب نشده'); }
    const data = await new Promise(res => {
      const r = new FileReader(); r.onload = () => res(r.result); r.readAsDataURL(PENDING_FILE); });
    payload = { kind:'file', filename:PENDING_FILE.name, data, pillar };
  }
  const r = await post('/api/idea/capture', payload);
  btn.disabled = false;
  if (!r.ok) return toast(r.data.error || 'ثبت نشد');
  const wasVoice = S.capture === 'voice';
  // only the field that was just sent is cleared; a half-written text survives a voice capture
  setDraft({ pillar: '', ...(S.capture === 'text' ? { text: '' } : S.capture === 'url' ? { url: '' } : {}) });
  pushDraft();
  PENDING_FILE = null; REC.blob = null;
  toast('✓ ایده ثبت شد');
  await loadState(); S.openIdea = r.data.id;
  await viewIdeas();
  if (wasVoice) runIdeaStep(r.data.id, 'transcribe');
}

function ideaHTML(i) {
  const src = i.source || {}, st = i.steps || {};
  const srcLabel = i.audio ? 'ویس' : ({ youtube:'یوتیوب', website:'سایت', url:'لینک', file:'فایل', text:'متن', manual:'دستی', analyst:'تحلیلگر', advisor:'مشاور' }[src.kind] || 'دستی');
  const done = stepsFor(i).filter(([k]) => st[k]).map(([,l]) => l);
  return `<article class="idea ${i.status==='done'?'done':''}">
    <div class="idea-main" data-id="${i.id}">
      <h4>${esc(i.title)}</h4>
      <div class="idea-meta">
        ${i.pillar?`<span class="pill">${esc(i.pillar)}</span>`:''}
        <span>${esc(srcLabel)}${src.at?' · '+esc(src.at):''}</span>
        ${i.created?`<span>${esc(i.created)}</span>`:''}
        ${done.length?`<span style="color:var(--up)">✓ ${done.join(' · ')}</span>`:''}
      </div>
      ${i.note?`<p class="idea-note">${esc(i.note)}</p>`:''}
    </div>
    <div class="idea-side">
      ${i.score?`<span class="idea-score">${faNum(i.score)}</span>`:''}
      <select data-id="${i.id}">${Object.entries(STATUS).map(([k,l]) =>
        `<option value="${k}" ${i.status===k?'selected':''}>${l}</option>`).join('')}</select>
      <button class="del" data-id="${i.id}" title="حذف">✕</button>
    </div>
  </article>`;
}

/* ---- جزئیات ایده ---- */
let IPOLL = null;
async function viewIdeaDetail() {
  const it = S.ideas.find(i => i.id === S.openIdea);
  if (!it) { S.openIdea = null; return viewIdeas(); }
  const f = await api(`/api/idea/files?id=${encodeURIComponent(it.id)}`) || {};
  const has = k => f[k] != null;
  const box = (k, label) => has(k)
    ? `<section class="panel" data-box="${k}" style="margin-bottom:16px"><h3>${label}</h3>
         <div class="md" style="max-width:none">${md(f[k])}</div></section>` : '';

  $('#page').innerHTML = `
    <div class="detail-bar">
      <button class="btn" id="ideaBack">→ برگشت به بانک</button>
      <span class="grow"></span>
      ${stepsFor(it).map(([k,l]) => `<button class="btn ${
        k==='transcribe'?'danger':''}" data-step="${k}">${
        (it.steps||{})[k] ? 'دوباره: ' : ''}${l}</button>`).join('')}
      <button class="btn primary" data-step="full"
        title="مرحله‌هایی که هنوز انجام نشده (تحلیل، جستجوی وب) و بعد ساخت ریلز، پشت سر هم">⚡ ساخت کامل</button>
    </div>
    <div id="ideaHead"></div>
    <details class="brief" ${f.brief ? 'open' : ''}>
      <summary>دستورالعمل پژوهش <span>— اختیاری، ولی خیلی فرق می‌کند</span></summary>
      <textarea id="briefText" class="cap-text" style="min-height:110px"
        placeholder="مثال: فقط دنبال اتفاقات سه ماه اخیر بگرد. حتماً ببین کاربرهای Reddit چه تجربه‌ای داشته‌اند. آمار بازار ایران هم اگر هست بیاور.">${esc(f.brief || '')}</textarea>
      <p class="cap-hint">این متن مستقیم به پژوهشگر داده می‌شود و بر قواعد پیش‌فرض اولویت دارد.</p>
    </details>
    <div id="ideaJob" class="build-status" hidden></div>
    <div id="reelEd"></div>
    ${box('research','یافته‌های وب')}
    ${box('analysis','تحلیل')}
    ${box('raw','ورودی خام')}
    ${!has('analysis') && !has('reel') ? '<div class="empty">هنوز پردازش نشده. با «تحلیل» شروع کن.</div>' : ''}`;
  showIdeaHead(it, f);
  if (window.mountCarouselIdea) mountCarouselIdea($('.detail-bar'), it);
  if (window.mountReelEditor) mountReelEditor($('#reelEd'), it, f);

  $('#ideaBack').onclick = () => { S.openIdea = null; clearInterval(IPOLL); viewIdeas(); };
  $$('[data-step]').forEach(b => b.onclick = () => {
    if ((b.dataset.step === 'produce' || b.dataset.step === 'full') && has('reel') &&
        !confirm('ریلز فعلی (با همه‌ی ویرایش‌هایت) جایش را به یک ریلز تازه می‌دهد.\nنسخه‌ی فعلی کنار گذاشته می‌شود (reel.prev.json / reel.prev.md). ادامه؟')) return;
    runIdeaStep(it.id, b.dataset.step);
  });
  const j = await api('/api/idea/status');
  if (j && j.state === 'running' && j.id === it.id) { showIdeaJob(j); pollIdea(); }
}

/* ---- سرِ صفحه‌ی ایده: عنوان و برچسب‌ها، یا فرم ویرایش ---- */
function showIdeaHead(it, f) {
  const stale = f.stale || [];
  $('#ideaHead').innerHTML = `
    <div class="detail-head">
      <h2 class="detail-title">${esc(it.title)}</h2>
      <button class="btn" id="ideaEdit">✎ ویرایش</button>
    </div>
    <div class="idea-meta" style="margin-bottom:20px">
      ${it.pillar?`<span class="pill">${esc(it.pillar)}</span>`:''}
      <span>${esc(STATUS[it.status]||it.status)}</span>
      ${it.created?`<span>${esc(it.created)}</span>`:''}
    </div>
    ${stale.length ? `<p class="idea-stale">متن ایده بعد از ساختِ ${esc(stale.join('، '))} عوض شده، پس این‌ها هنوز از روی متن قبلی‌اند.
      برای به‌روز شدن، دکمه‌های «دوباره: …» بالای صفحه را به ترتیب بزن.</p>` : ''}`;
  $('#ideaEdit').onclick = () => editIdeaHead(it, f);
}
function editIdeaHead(it, f) {
  const pillars = PILLARS.includes(it.pillar) || !it.pillar ? PILLARS : [it.pillar, ...PILLARS];
  const built = ['analysis', 'research', 'reel'].some(k => f[k] != null);
  $('#ideaHead').innerHTML = `
    <section class="panel idea-edit">
      <label>عنوان<input id="edTitle" class="cap-input" value="${esc(it.title)}"></label>
      <div class="idea-edit-row">
        <label>پیلر<select id="edPillar"><option value="">— بدون پیلر —</option>
          ${pillars.map(p => `<option ${p === it.pillar ? 'selected' : ''}>${esc(p)}</option>`).join('')}</select></label>
        <label>وضعیت<select id="edStatus">
          ${Object.entries(STATUS).map(([k, l]) => `<option value="${k}" ${k === it.status ? 'selected' : ''}>${l}</option>`).join('')}</select></label>
      </div>
      <label>متن ایده<textarea id="edRaw" class="cap-text">${esc(f.raw || '')}</textarea></label>
      ${built ? '<p class="cap-hint">تحلیل و ریلزِ فعلی از روی متن فعلی ساخته شده‌اند. اگر متن را عوض کنی، بعد از ذخیره می‌توانی دوباره بسازی‌شان.</p>' : ''}
      <div class="rowbar">
        <button class="btn" id="edCancel">انصراف</button>
        <span class="grow"></span>
        <button class="btn primary" id="edSave">ذخیره</button>
      </div>
    </section>`;
  const ta = $('#edRaw');
  fitHeight(ta); ta.addEventListener('input', () => fitHeight(ta));
  $('#edCancel').onclick = () => showIdeaHead(it, f);
  $('#edSave').onclick = async () => {
    const btn = $('#edSave'), raw = ta.value.trim();
    if (!raw) return toast('متن ایده خالی است');
    const fields = { title: $('#edTitle').value, pillar: $('#edPillar').value, status: $('#edStatus').value };
    if (raw !== (f.raw || '').trim()) fields.raw = raw;   // untouched text keeps raw.md's date, so nothing turns "stale"
    btn.disabled = true;
    if (!await patchIdea(it.id, fields)) { btn.disabled = false; return; }
    toast('✓ ذخیره شد'); viewIdeaDetail();
  };
}

async function runIdeaStep(id, step) {
  $$('[data-step]').forEach(b => b.disabled = true);
  const bt = $('#briefText');
  const r = await post('/api/idea/run', { id, step, brief: bt ? bt.value.trim() : '' });
  if (!r.ok) { $$('[data-step]').forEach(b => b.disabled = false);
    return showIdeaJob({ state:'error', error:r.data.error || 'شروع نشد' }); }
  pollIdea();
}
function pollIdea() {
  clearInterval(IPOLL);
  IPOLL = setInterval(async () => {
    const j = await api('/api/idea/status'); if (!j) return;
    showIdeaJob(j);
    if (j.state === 'done' || j.state === 'error') {
      clearInterval(IPOLL);
      if (j.state === 'done') { toast('✓ تمام شد'); await loadState(); viewIdeaDetail(); }
      else $$('[data-step]').forEach(b => b.disabled = false);
    }
  }, 2500);
}
function showIdeaJob(j) {
  const box = $('#ideaJob'); if (!box) return;
  if (!j || j.state === 'idle') { box.hidden = true; return; }
  box.hidden = false;
  box.className = 'build-status' + (j.state === 'error' ? ' err' : '');
  const head = j.state === 'running' ? `<span class="spin"></span> ${esc(j.step)} — چند دقیقه طول می‌کشد…`
             : j.state === 'done' ? '✓ تمام شد' : '✕ ' + esc(j.error || 'خطا');
  const lg = (j.log||[]).length ? `<div class="build-log">${j.log.map(l=>`<div>${esc(l)}</div>`).join('')}</div>` : '';
  box.innerHTML = `<div class="build-step">${head}</div>${lg}`;
}

/* ================= استودیو ریلز ================= */
const REEL_TABS = [['reels','ریلزها'],['scripts','متن ضبط'],['full','متن کامل'],['reading','نسخه‌ی خواندنی'],['study','تمرین انگلیسی']];

function viewReels() {
  const sel = $('#videoSelect');
  if (!S.videos.length) {
    $('#page').innerHTML = `<div class="page-head"><h2>استودیو ریلز</h2></div>
      ${buildBarHTML()}<div class="empty">هنوز منبعی پردازش نشده. یک لینک یوتیوب بگذار.</div>`;
    return wireBuild();
  }
  if (!S.slug || !S.videos.some(v => v.slug === S.slug)) {
    const ready = S.videos.find(v => v.has && v.has.reels);
    S.slug = (ready || S.videos[0]).slug;
  }
  sel.innerHTML = S.videos.map(v => `<option value="${esc(v.slug)}">${esc(v.title)}</option>`).join('');
  sel.value = S.slug;
  const v = S.videos.find(x => x.slug === S.slug) || {};
  $('#page').innerHTML = `
    <div class="page-head"><h2>استودیو ریلز</h2>
      <p><b style="color:var(--fg)">${esc(v.title||'')}</b>${v.channel?' · '+esc(v.channel):''}${v.duration?' · '+esc(v.duration):''}
      ${v.url?` · <a href="${esc(v.url)}" target="_blank" rel="noopener" style="color:var(--accent2)">یوتیوب ↗</a>`:''}</p></div>
    ${buildBarHTML()}
    <div class="tabs-wrap" style="margin:18px 0 0"><nav class="tabs" id="rtabs" style="padding:0">
      ${REEL_TABS.map(([k,l]) => `<button data-tab="${k}" class="${S.tab===k?'on':''}">${l}</button>`).join('')}
    </nav></div>
    <div id="rview" style="padding-top:20px"></div>`;
  wireBuild();
  $$('#rtabs button').forEach(b => b.onclick = () => {
    $$('#rtabs button').forEach(x => x.classList.toggle('on', x === b));
    S.tab = b.dataset.tab; renderReelTab();
  });
  renderReelTab();
}

function renderReelDetail(view) {
  const r = S.reels.find(x => x.num === S.openReel);
  if (!r) { S.openReel = null; return renderReelTab(); }
  const sc = scriptFor(r.num);
  view.innerHTML = `
    <div class="detail">
      <div class="detail-bar">
        <button class="btn" id="backBtn">→ برگشت به لیست</button>
        <span class="grow"></span>
        ${sc ? `<button class="btn" data-copy="${r.num}">کپی متن</button>
                <button class="btn primary" data-tp="${r.num}">▶ تله‌پرامپتر</button>` : ''}
        <button class="btn danger" data-del="${r.num}">حذف</button>
      </div>
      <h2 class="detail-title">${esc(r.title || r.name)}</h2>
      <div class="tcode" style="margin-bottom:20px">
        <span class="score">${esc(r.score)}</span>
        ${r.tcode?`<span>⏱ ${esc(r.tcode)}</span>`:''}${r.len?`<span>${esc(r.len)}</span>`:''}
        ${sc?`<span>${faNum(sc.words)} کلمه · ~${faNum(Math.round(sc.secs/60*10)/10)} دقیقه</span>`:''}
      </div>
      <div class="detail-cols">
        <section class="panel">
          <h3>متن آماده‌ی ضبط</h3>
          ${sc ? `<div class="script-text">${md(sc.body)}</div>`
               : '<p style="color:var(--dim)">متن ضبط برای این ریلز ساخته نشده.</p>'}
        </section>
        <section class="panel">
          <h3>مشخصات و ساختار</h3>
          <div class="md" style="max-width:none">${md(r.raw || '')}</div>
        </section>
      </div>
    </div>`;
  $('#backBtn').onclick = () => { S.openReel = null; renderReelTab(); };
}

async function renderReelTab() {
  const view = $('#rview'); if (!view) return;
  if (S.tab === 'reels' && S.openReel) {
    if (!S.reels.length) { S.reels = parseReels(await getFile('reels')); S.scripts = parseScripts(await getFile('scripts')); }
    return renderReelDetail(view);
  }
  view.innerHTML = `<div class="empty">در حال بارگذاری…</div>`;
  const NAMES = { reels:'03-پیشنهاد-ریلز.md', scripts:'04-متن-آماده-ضبط.md',
                  full:'01-متن-کامل-فارسی.md', reading:'05-نسخه-خواندنی.md', study:'06-تمرین-انگلیسی.md' };

  if (S.tab === 'reels') {
    S.reels = parseReels(await getFile('reels'));
    S.scripts = parseScripts(await getFile('scripts'));
    if (!S.reels.length) return emptyFile(view, NAMES.reels);
    view.innerHTML = `<div class="grid">${S.reels.map(r => {
      const sc = S.scripts.find(s => s.num === r.num);
      return `<article class="card open-card" data-open="${r.num}">
        <div class="card-top"><span class="rank">${r.rank||'🎬'}</span><span class="score">${esc(r.score)}</span>
          <button class="card-del" data-del="${r.num}" title="حذف این ریلز">✕</button></div>
        <h3>${esc(r.title || r.name)}</h3>
        <div class="tcode">${r.tcode?`<span>⏱ ${esc(r.tcode)}</span>`:''}${r.len?`<span>${esc(r.len)}</span>`:''}${sc?`<span>${faNum(sc.words)} کلمه</span>`:''}</div>
        ${r.hook?`<div class="hook"><em>هوک سه‌ثانیه‌ای</em>${inline(r.hook)}</div>`:''}
        ${r.why?`<div class="why"><b>چرا کار می‌کند:</b> ${inline(r.why)}</div>`:''}
        <div class="card-actions">
          <button data-copy="${r.num}" ${sc?'':'disabled'}>کپی متن</button>
          <button class="primary" data-tp="${r.num}" ${sc?'':'disabled'}>▶ تله‌پرامپتر</button>
        </div></article>`;
    }).join('')}</div>`;
  } else if (S.tab === 'scripts') {
    S.scripts = parseScripts(await getFile('scripts'));
    if (!S.scripts.length) return emptyFile(view, NAMES.scripts);
    view.innerHTML = S.scripts.map(s => `
      <section class="script" data-n="${s.num}">
        <div class="script-head"><span class="chev">▼</span>
          <h3>${faNum(s.num)}. ${esc(s.title||s.name)}</h3>
          <span class="words">${faNum(s.words)} کلمه · ~${faNum(Math.round(s.secs/60*10)/10)} دقیقه</span></div>
        <div class="script-body"><div class="script-text">${md(s.body)}</div>
          <div class="script-actions">
            <button data-copy="${s.num}">کپی متن</button>
            <button class="primary" data-tp="${s.num}">▶ تله‌پرامپتر</button>
          </div></div></section>`).join('');
  } else {
    const text = await getFile(S.tab);
    if (!text) return emptyFile(view, NAMES[S.tab]);
    view.innerHTML = `<div class="md${S.tab==='study'?' study':''}">${md(text)}</div>`;
  }
}
function emptyFile(view, file) {
  view.innerHTML = `<div class="empty">فایل <code>${esc(file)}</code> هنوز ساخته نشده.<br>لینک را در نوار بالا بگذار تا ساخته شود.</div>`;
}

function parseReels(text) {
  if (!text) return [];
  return text.split(/\n(?=##\s)/).map(sec => {
    if (!/^##\s/.test(sec) || !/\*\*امتیاز:/.test(sec)) return null;
    const head = (sec.match(/^##\s+(.+)$/m)||[,''])[1].trim();
    const num = enNum((head.match(/[۰-۹\d]+/)||['?'])[0]);
    const rank = (head.match(/^(\p{Emoji_Presentation}|🥇|🥈|🥉)/u)||[''])[0];
    const name = head.replace(/^\S*\s*/,'').replace(/^ریلز\s*[۰-۹\d]+\s*—\s*/,'')
      .replace(/^[۰-۹\d]+\s*—\s*/,'').replace(/^[«»]|[«»]$/g,'').trim();
    const g = re => (sec.match(re)||[,''])[1].trim();
    const hb = sec.match(/\*\*هوک[^*]*\*\*\s*\n((?:\s*>.*\n?)+)/);
    const raw = sec.replace(/^##\s+.*$/m, '').replace(/^\s*---\s*$/gm, '').trim();
    return { num, rank, name, raw,
      score:g(/امتیاز:\s*([^·\n*]+)/), tcode:g(/تایم‌کد:\s*([^·\n*]+)/), len:g(/طول هدف:\s*([^·\n*]+)/),
      title:g(/\*\*تایتل:\*\*\s*(.+)$/m), why:g(/\*\*چرا کار می‌کند:\*\*\s*(.+)$/m),
      hook: hb ? hb[1].replace(/^\s*>\s?/gm,'').trim() : '' };
  }).filter(Boolean);
}
function parseScripts(text) {
  if (!text) return [];
  return text.split(/\n(?=#\s*🎬)/).map(sec => {
    const head = (sec.match(/^#\s*🎬\s*(.+)$/m)||[,''])[1];
    if (!head) return null;
    const num = enNum((head.match(/[۰-۹\d]+/)||['?'])[0]);
    const name = head.replace(/^ریلز\s*[۰-۹\d]+\s*—\s*/,'').trim();
    const title = (sec.match(/\*\*تایتل:\*\*\s*(.+)$/m)||[,''])[1].trim();
    let body = sec.replace(/^#\s*🎬.*$/m,'').replace(/^\*\*تایتل:\*\*.*$/m,'')
                  .replace(/^\s*---\s*$/gm,'').trim();
    const plain = body.replace(/\*\*/g,'').replace(/\n{3,}/g,'\n\n').trim();
    const words = plain.split(/\s+/).filter(Boolean).length;
    return { num, name, title, body, plain, words, secs: Math.round(words/160*60) };
  }).filter(Boolean);
}
const scriptFor = n => S.scripts.find(s => s.num === n);

/* ================= تله‌پرامپتر ================= */
const TP = { on:false, playing:false, speed:1, size:46, mirror:false, base:40, raf:null, last:0, script:null };
function tpOpen(num) {
  const s = scriptFor(num); if (!s) return toast('متن این ریلز پیدا نشد');
  tpOpenScript(s);
}
function tpOpenScript(s) {                 // s: { title, body (مارک‌داون), secs }
  TP.script = s; $('#tpTitle').textContent = s.title || s.name;
  $('#tpInner').innerHTML = md(s.body); $('#tp').hidden = false; TP.on = true;
  document.body.style.overflow = 'hidden'; applySize();
  requestAnimationFrame(() => {
    const el = $('#tpScroll'); el.scrollTop = 0;
    const dist = el.scrollHeight - el.clientHeight;
    TP.base = dist > 0 ? dist / Math.max(s.secs, 20) : 40; updateHud();
  });
  tpPause();
}
function tpClose() { tpPause(); TP.on = false; $('#tp').hidden = true; document.body.style.overflow = ''; }
function tpPlay() {
  if (!TP.on) return;
  TP.playing = true; TP.last = performance.now(); $('#tpPlay').textContent = '❚❚ توقف';
  const step = now => {
    if (!TP.playing) return;
    const dt = (now - TP.last)/1000; TP.last = now;
    const el = $('#tpScroll'); el.scrollTop += TP.base * TP.speed * dt; updateHud();
    if (el.scrollTop >= el.scrollHeight - el.clientHeight - 1) return tpPause();
    TP.raf = requestAnimationFrame(step);
  };
  TP.raf = requestAnimationFrame(step);
}
function tpPause() { TP.playing = false; cancelAnimationFrame(TP.raf); $('#tpPlay').textContent = '▶ شروع'; }
function updateHud() {
  const el = $('#tpScroll'); const dist = el.scrollHeight - el.clientHeight;
  const p = dist > 0 ? el.scrollTop/dist : 0;
  $('#tpProgress').firstElementChild.style.width = (p*100)+'%';
  const left = Math.max(0, Math.round(TP.script.secs*(1-p)/TP.speed));
  $('#tpTime').textContent = `${faNum(Math.floor(left/60))}:${faNum(String(left%60).padStart(2,'0'))}`;
  $('#tpSpeed').textContent = `سرعت ${faNum((Math.round(TP.speed*10)/10).toFixed(1))}× · متن ${faNum(TP.size)}`;
}
function applySize() {
  $('#tpInner').style.fontSize = TP.size + 'px';
  try { localStorage.setItem('tp', JSON.stringify({ size:TP.size, speed:TP.speed })); } catch {}
}

/* ================= ساخت ================= */
let POLL = null;
function wireBuild() {
  const b = $('#buildBtn'), inp = $('#urlInput'); if (!b) return;
  b.onclick = startBuild;
  inp.onkeydown = e => { if (e.key === 'Enter') startBuild(); };
}
async function startBuild() {
  const inp = $('#urlInput'), btn = $('#buildBtn'); const url = inp.value.trim();
  if (!url) return toast('لینک را بگذار');
  btn.disabled = true;
  const r = await post('/api/build', { url });
  if (!r.ok) { btn.disabled = false; return showBuild({ state:'error', error:r.data.error || 'شروع نشد' }); }
  inp.value = ''; pollBuild();
}
function pollBuild() {
  clearInterval(POLL);
  POLL = setInterval(async () => {
    const d = await api('/api/state'); if (!d) return;
    S.job = d.job; showBuild(d.job);
    if (d.job.state === 'done' || d.job.state === 'error') {
      clearInterval(POLL);
      const b = $('#buildBtn'); if (b) b.disabled = false;
      if (d.job.state === 'done') {
        S.videos = d.videos; S.cache = {}; S.slug = d.job.slug;
        toast('✓ ساخته شد'); go('reels');
      }
    }
  }, 2000);
}
function showBuild(j) {
  const box = $('#buildStatus'); if (!box) return;
  if (!j || j.state === 'idle') { box.hidden = true; return; }
  box.hidden = false;
  box.className = 'build-status' + (j.state === 'error' ? ' err' : '');
  const head = j.state === 'running' ? `<span class="spin"></span> ${esc(j.step||'در حال کار…')}`
             : j.state === 'done' ? '✓ تمام شد'
             : '✕ ' + esc(j.error || 'خطا');
  const lg = (j.log||[]).length ? `<div class="build-log">${j.log.map(l=>`<div>${esc(l)}</div>`).join('')}</div>` : '';
  box.innerHTML = `<div class="build-step">${head}</div>${lg}`;
  const el = box.querySelector('.build-log'); if (el) el.scrollTop = el.scrollHeight;
}

async function delReel(num) {
  const r = S.reels.find(x => x.num === num);
  const label = r ? (r.title || r.name) : 'این ریلز';
  if (!confirm(`«${label}»\n\nاین ریلز از هر دو فایل (پیشنهادها و متن ضبط) پاک می‌شود. مطمئنی؟`)) return;
  const res = await post('/api/reel/delete', { slug: S.slug, num });
  if (!res.ok) return toast(res.data.error || 'حذف نشد');
  S.cache = {}; S.openReel = null;
  S.reels = parseReels(await getFile('reels'));
  S.scripts = parseScripts(await getFile('scripts'));
  toast('✓ حذف شد'); renderReelTab();
}

/* ================= رویدادها ================= */
document.addEventListener('click', e => {
  const nav = e.target.closest('#nav button');
  if (nav && !nav.disabled) return go(nav.dataset.sec);
  const link = e.target.closest('[data-go]');
  if (link) { e.preventDefault(); return go(link.dataset.go); }
  const del = e.target.closest('[data-del]');
  if (del) { e.stopPropagation(); return delReel(del.dataset.del); }
  const open = e.target.closest('[data-open]');
  if (open) { S.openReel = open.dataset.open; return renderReelTab(); }
  const tp = e.target.closest('[data-tp]');
  if (tp && !tp.disabled) return tpOpen(tp.dataset.tp);
  const cp = e.target.closest('[data-copy]');
  if (cp && !cp.disabled) {
    const s = scriptFor(cp.dataset.copy); if (!s) return toast('متن پیدا نشد');
    return navigator.clipboard.writeText(s.plain).then(() => toast('✓ متن کپی شد'), () => toast('کپی نشد'));
  }
  const head = e.target.closest('.script-head');
  if (head) return head.parentElement.classList.toggle('open');
  if (e.target.id === 'tpClose') return tpClose();
  if (e.target.id === 'tpPlay') return TP.playing ? tpPause() : tpPlay();
  if (e.target.id === 'tpMirror') {
    TP.mirror = !TP.mirror; $('#tp').classList.toggle('mirror', TP.mirror);
    e.target.classList.toggle('on', TP.mirror);
  }
});
document.addEventListener('keydown', e => {
  if (!TP.on) return; const k = e.key;
  if (k === 'Escape') { e.preventDefault(); return tpClose(); }
  if (k === ' ') { e.preventDefault(); return TP.playing ? tpPause() : tpPlay(); }
  if (k === 'ArrowUp') { e.preventDefault(); TP.speed = Math.min(4, TP.speed+.1); return updateHud(); }
  if (k === 'ArrowDown') { e.preventDefault(); TP.speed = Math.max(.2, TP.speed-.1); return updateHud(); }
  if (k === '+' || k === '=') { e.preventDefault(); TP.size = Math.min(110, TP.size+3); applySize(); return updateHud(); }
  if (k === '-' || k === '_') { e.preventDefault(); TP.size = Math.max(18, TP.size-3); applySize(); return updateHud(); }
  if (k.toLowerCase() === 'r') { e.preventDefault(); $('#tpScroll').scrollTop = 0; return updateHud(); }
  if (k.toLowerCase() === 'm') { e.preventDefault(); return $('#tpMirror').click(); }
});
$('#tpScroll').addEventListener('scroll', () => { if (TP.on && !TP.playing) updateHud(); });
$('#videoSelect').addEventListener('change', e => { S.slug = e.target.value; S.cache = {}; viewReels(); });

/* ================= شروع ================= */
(async function init() {
  try { const t = JSON.parse(localStorage.getItem('tp')||'{}');
    if (t.size) TP.size = t.size; if (t.speed) TP.speed = t.speed; } catch {}
  // همه‌ی اسکریپت‌های بعدی (view هر تب) باید بار شده باشند؛ وگرنه go() تب را پیدا نمی‌کند و داشبورد باز می‌شود
  const scriptsReady = document.readyState === 'loading'
    ? new Promise(r => document.addEventListener('DOMContentLoaded', r, { once: true })) : null;
  await Promise.all([loadState(), pullDraft(), scriptsReady]);
  if (window.paintBrandName) paintBrandName();
  const qs = new URLSearchParams(location.search);
  const want = qs.get('s');
  if (qs.get('reel')) { S.openReel = enNum(qs.get('reel')); S.tab = 'reels'; }
  if (qs.get('cap')) S.capture = qs.get('cap');
  // تا وقتی پروفایل پر نشده، استودیو با صفحه‌ی «شروع» باز می‌شود
  go(S.modules.some(m => m.key === want && m.ready) ? want : (S.profile.name ? 'dashboard' : 'start'));
  if (qs.get('read') && window.openReader) openReader(qs.get('read'));
})();
