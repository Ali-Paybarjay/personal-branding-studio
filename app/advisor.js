/* ================= مشاور =================
   چت با مشاور برند شخصی (Claude روی اشتراک خود کاربر) + خواندن جواب‌ها با صدا (Gemini TTS).
   سرور: app/advisor.py — مسیرهای /api/advisor/*. ابزارهای $، esc، md، api، post، toast، faNum از app.js می‌آیند. */

const ADV = {
  chats: [], chat: null, settings: { voice: 'Sadaltager', rate: 1, autoplay: false }, voices: [], usage: {},
  effort: { normal: 'high', deep: 'xhigh' }, pollT: null, pollId: null, liveMsg: null, sending: false,
  rec: { mr: null, stream: null, chunks: [], t0: 0, timer: null, busy: false },
  audio: { el: null, mid: null, token: 0, state: '' },
  // باید پیش از go() خوانده شود؛ go() آدرس را به ?s=advisor برمی‌گرداند
  initChat: new URLSearchParams(location.search).get('chat'),
};

const ADV_STARTERS = [
  ['ایده‌ی امروزم اینه که ', 'ایده‌ی امروزم اینه…'],
  ['این هفته چی منتشر کنم؟ یه برنامه‌ی کوتاه و مشخص بهم بده.', 'این هفته چی منتشر کنم؟'],
  ['کمکم کن هسته‌ی برندم رو پر کنم. سؤال‌های ضروری رو یکی‌یکی ازم بپرس.', 'کمکم کن هسته‌ی برندم رو پر کنم'],
  ['پیلرهای محتوایی من چی باشه؟ با توجه به کار و مخاطبم سه تا چهار پیشنهاد بده.', 'پیلرهای محتوایی‌ام چی باشه؟'],
  ['دو ماهه پست نذاشتم. چطور برگردم که فالوورها دوباره ببیننم؟', 'چطور بعد از سکوت برگردم؟'],
  ['آمار پیجم رو ساده برام توضیح بده: الان کجای کارم و مهم‌ترین مشکلم چیه؟', 'الان کجای کارم؟'],
];
const ADV_RATES = [1, 1.15, 1.3, 1.5];

const advFmtSecs = s => { s = Math.max(0, Math.round(s)); return faNum(`${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`); };
const advEffortLabel = e => e === ADV.effort.deep ? 'عمیق' : 'عادی';
const advStrip = t => String(t || '').replace(/<<<(IDEA|MEMO)[\s\S]*?(\1>>>|$)/g, '').trim();
const ADV_GM = ['ژانویه','فوریه','مارس','آوریل','مه','ژوئن','ژوئیه','اوت','سپتامبر','اکتبر','نوامبر','دسامبر'];
// «2026-10-05» → «۵ اکتبر» (سال فقط اگر امسال نباشد)
const advDay = iso => { const [y, m, d] = String(iso || '').slice(0, 10).split('-').map(Number); if (!y || !m || !d) return '';
  return faNum(`${d} ${ADV_GM[m - 1]}${y !== new Date().getFullYear() ? ' ' + y : ''}`); };
// «2026-10-05 15:45» → «امروز، ۱۵:۴۵» / «دیروز، …» / «۳ اکتبر، …»
const advWhen = st => { st = String(st || ''); const day = st.slice(0, 10), hm = faNum(st.slice(11, 16));
  const iso = dt => `${dt.getFullYear()}-${String(dt.getMonth() + 1).padStart(2, '0')}-${String(dt.getDate()).padStart(2, '0')}`;
  const now = new Date(), y = new Date(now - 864e5);
  const d = day === iso(now) ? 'امروز' : day === iso(y) ? 'دیروز' : advDay(day);
  return hm ? `${d}، ${hm}` : d; };
const advDur = ms => ms >= 60000 ? `${faNum(Math.floor(ms / 60000))} دقیقه و ${faNum(Math.round(ms % 60000 / 1000))} ثانیه` : `${faNum(Math.round(ms / 1000))} ثانیه`;

/* ---------- صفحه ---------- */
async function viewAdvisor() {
  advStopPoll();
  $('#page').innerHTML = `
    <div class="adv" id="adv">
      <aside class="adv-side">
        <button class="btn primary adv-new" data-adv="new">+ گفت‌وگوی تازه</button>
        <div class="adv-list" id="advList"></div>
        <div class="adv-foot">
          <button class="adv-link" data-adv="open-memory">حافظه‌ی مشاور</button>
          <button class="adv-link" data-adv="open-settings">صدا و تنظیمات</button>
          <div class="adv-usage" id="advUsage"></div>
        </div>
      </aside>
      <section class="adv-main" id="advMain"></section>
      <div class="adv-drawer" id="advDrawer" hidden></div>
    </div>`;
  await advLoadList();
  const want = ADV.initChat || ADV.chat?.id || null;
  ADV.initChat = null;
  if (want && ADV.chats.some(c => c.id === want)) await advOpen(want);
  else advRenderNew();
}

async function advLoadList() {
  const d = await api('/api/advisor/chats'); if (!d) return;
  Object.assign(ADV, { chats: d.chats, settings: d.settings, voices: d.voices, usage: d.usage || {}, effort: d.effort || ADV.effort });
  advRenderList(); advRenderUsage();
}

function advRenderList() {
  const box = $('#advList'); if (!box) return;
  box.innerHTML = ADV.chats.length ? ADV.chats.map(c => `
    <button class="adv-item ${ADV.chat?.id === c.id ? 'on' : ''}" data-adv="open" data-id="${esc(c.id)}">
      <b>${esc(c.title)}</b>
      <span>${c.running ? '<i class="adv-dot"></i>در حال جواب…' : esc(advWhen(c.updated))}</span>
    </button>`).join('') : '<p class="adv-none">هنوز گفت‌وگویی نیست.</p>';
}

function advRenderUsage() {
  const w = ADV.usage?.windows || {}, el = $('#advUsage'); if (!el) return;
  const pc = x => x ? faNum(Math.round(x.used * 100)) + '٪' : '—';
  el.innerHTML = w.five_hour || w.seven_day
    ? `سهمیه‌ی Claude — ۵ ساعت اخیر: <b>${pc(w.five_hour)}</b>، این هفته: <b>${pc(w.seven_day)}</b>` : '';
}

function advUrl(id) { history.replaceState(null, '', id ? `?s=advisor&chat=${encodeURIComponent(id)}` : '?s=advisor'); }

function advRenderNew() {
  ADV.chat = null; advUrl(null); advRenderList();
  $('#advMain').innerHTML = `
    <div class="adv-msgs" id="advMsgs">
      <div class="adv-welcome">
        <h2>مشاور</h2>
        <p>ایده‌ات را بگو تا با هسته‌ی برندت بسنجیمش. هر گفت‌وگوی تازه با پرونده‌ی تازه شروع می‌شود: هسته‌ی برند، بانک ایده، ترجمه‌ها، استوری‌ها، آمار اینستاگرام (اگر وصل باشد) و حافظه‌ی گفت‌وگوهای قبلی.</p>
        ${window.guideHTML ? guideHTML('advisor') : ''}
        <div class="adv-starters">${ADV_STARTERS.map(([t, l], k) => `<button data-adv="starter" data-k="${k}">${esc(l)}</button>`).join('')}</div>
      </div>
    </div>
    ${advComposerHTML()}`;
  advWireComposer();
}

function advComposerHTML() {
  return `
    <div class="adv-composer">
      <textarea id="advInput" rows="2" placeholder="بنویس یا ضبط کن…  (Enter بفرست، Shift+Enter خط تازه)"></textarea>
      <div class="adv-bar">
        <button class="adv-mic" id="advMic" data-adv="mic" title="ضبط صدا — دوباره بزن تا تمام شود">${ADV_MIC}<span>ضبط</span></button>
        <span class="adv-recstate" id="advRecState"></span>
        <label class="adv-deep" title="همان پیام با effort بالاتر (xhigh): کندتر، عمیق‌تر — برای سؤال‌های بزرگ">
          <input type="checkbox" id="advDeep"> عمیق‌تر فکر کن</label>
        <span class="grow"></span>
        <button class="btn primary" id="advSend" data-adv="send">بفرست</button>
      </div>
    </div>`;
}
const ADV_MIC = `<svg viewBox="0 0 24 24" width="17" height="17" aria-hidden="true"><path fill="currentColor" d="M12 15a3.5 3.5 0 0 0 3.5-3.5v-6a3.5 3.5 0 1 0-7 0v6A3.5 3.5 0 0 0 12 15Zm6-3.5a.9.9 0 1 1 1.8 0A7.8 7.8 0 0 1 12.9 19.3V22h-1.8v-2.7A7.8 7.8 0 0 1 4.2 11.5a.9.9 0 1 1 1.8 0 6 6 0 0 0 12 0Z"/></svg>`;

function advWireComposer() {
  const ta = $('#advInput'); if (!ta) return;
  const grow = () => { ta.style.height = 'auto'; ta.style.height = Math.min(ta.scrollHeight, 220) + 'px'; };
  ta.addEventListener('input', grow);
  ta.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); advSend(); }
  });
  try { ta.value = localStorage.getItem('adv-draft-' + (ADV.chat?.id || 'new')) || ''; } catch {}
  ta.addEventListener('input', () => { try { localStorage.setItem('adv-draft-' + (ADV.chat?.id || 'new'), ta.value); } catch {} });
  grow();
  advSetBusy(ADV.chat && ADV.chat.job?.state === 'running');
}

function advSetBusy(on) {
  const b = $('#advSend'); if (!b) return;
  b.disabled = !!on; b.textContent = on ? 'در حال جواب…' : 'بفرست';
}

async function advOpen(id) {
  advStopPoll();
  const c = await api(`/api/advisor/chat?id=${encodeURIComponent(id)}`);
  if (!c) { toast('این گفت‌وگو پیدا نشد'); return advRenderNew(); }
  ADV.chat = c; advUrl(id); advRenderList();
  $('#advMain').innerHTML = `
    <header class="adv-head">
      <h2 class="adv-title" id="advTitle" title="برای تغییر اسم کلیک کن">${esc(c.title)}</h2>
      <span class="adv-headmeta" title="پرونده (هسته‌ی برند، آمار، بانک ایده، …) همان لحظه‌ی شروع گفت‌وگو ساخته شده">پرونده‌ی ${esc(advWhen(c.dossier?.built))}</span>
      <button class="adv-icon" data-adv="rename" title="تغییر اسم">اسم</button>
      <button class="adv-icon danger" data-adv="delete" title="حذف این گفت‌وگو">حذف</button>
    </header>
    <div class="adv-msgs" id="advMsgs"></div>
    ${advComposerHTML()}`;
  advRenderMsgs();
  advWireComposer();
  if (c.job?.state === 'running') advStartPoll(id);
}

function advRename() {
  const h = $('#advTitle'), c = ADV.chat; if (!h || !c || h.isContentEditable) return;
  h.contentEditable = 'true'; h.classList.add('editing'); h.focus();
  getSelection().selectAllChildren(h);
  const done = async save => {
    h.contentEditable = 'false'; h.classList.remove('editing');
    h.onkeydown = h.onblur = null;
    const t = h.innerText.trim();
    if (!save || !t || t === c.title) { h.textContent = c.title; return; }
    const r = await post('/api/advisor/rename', { id: c.id, title: t });
    if (r.ok) { c.title = t; advLoadList(); } else { h.textContent = c.title; toast(r.data.error || 'ذخیره نشد'); }
  };
  h.onkeydown = e => {
    if (e.key === 'Enter') { e.preventDefault(); done(true); }
    if (e.key === 'Escape') { e.preventDefault(); done(false); }
  };
  h.onblur = () => done(true);
}

/* ---------- پیام‌ها ---------- */
function advRenderMsgs() {
  const box = $('#advMsgs'), c = ADV.chat; if (!box || !c) return;
  let html = c.messages.map(advMsgHTML).join('');
  if (c.job?.state === 'running') html += advLiveHTML(c.job);
  else if (c.pending) html += `<div class="adv-msg bot"><div class="adv-err">جواب این پیام کامل نشد (استودیو وسط کار بسته شد).
      <button class="btn" data-adv="retry">دوباره بفرست</button></div></div>`;
  box.innerHTML = html || `<div class="adv-welcome"><p>اولین پیامت را بفرست.</p></div>`;
  advScroll(true);
}

function advMsgHTML(m) {
  if (m.role === 'user') return `
    <div class="adv-msg user" data-mid="${esc(m.id)}"><div class="adv-bubble">${esc(m.text).replace(/\n/g, '<br>')}</div></div>`;
  const tools = (m.tools || []).length ? `<div class="adv-steps">${m.tools.map(t => `<span>${esc(t)}</span>`).join('')}</div>` : '';
  const ideas = (m.ideas || []).map((it, k) => `
    <div class="adv-idea">
      <div class="adv-idea-top"><b>${esc(it.title)}</b>${it.pillar ? `<span class="adv-chip">${esc(it.pillar)}</span>` : ''}${it.format ? `<span class="adv-chip dim">${esc(it.format)}</span>` : ''}</div>
      ${it.hook ? `<p><span class="adv-k">هوک:</span> ${esc(it.hook)}</p>` : ''}
      ${it.angle ? `<p><span class="adv-k">زاویه:</span> ${esc(it.angle)}</p>` : ''}
      ${it.why ? `<p class="adv-why"><span class="adv-k">چرا الان:</span> ${esc(it.why)}</p>` : ''}
      ${it.sent ? `<button class="adv-link" data-adv="goto-idea" data-idea="${esc(it.sent)}">✓ در بانک ایده — باز کن</button>`
                : `<button class="btn primary" data-adv="idea" data-mid="${esc(m.id)}" data-k="${k}">+ بفرست به بانک ایده</button>`}
    </div>`).join('');
  const memos = (m.memos || []).map((x, k) => `
    <div class="adv-memo"><span>${esc(x.text)}</span>
      ${x.saved ? '<em>✓ در حافظه</em>' : `<button class="btn" data-adv="memo" data-mid="${esc(m.id)}" data-k="${k}">یادت بمونه</button>`}</div>`).join('');
  const body = m.text ? `<div class="adv-text md">${md(m.text)}</div>` : '';
  const err = m.error ? `<div class="adv-err">جواب کامل نشد: ${esc(m.error)} <button class="btn" data-adv="retry">دوباره بفرست</button></div>`
            : m.stopped ? `<div class="adv-err soft">متوقف شد. <button class="btn" data-adv="retry">دوباره بفرست</button></div>` : '';
  const acts = m.text ? `
    <div class="adv-actions">
      <button data-adv="play" data-mid="${esc(m.id)}" class="${ADV.audio.mid === m.id && ADV.audio.state ? 'on' : ''}">${advPlayLabel(m.id)}</button>
      <button data-adv="copy" data-mid="${esc(m.id)}">کپی</button>
      ${m.sentAll ? `<button data-adv="goto-idea" data-idea="${esc(m.sentAll)}">✓ در بانک ایده</button>`
                  : `<button data-adv="idea" data-mid="${esc(m.id)}" title="این جواب و پیامت را یک ایده‌ی تازه در بانک ایده کن">+ بانک ایده</button>`}
      <button data-adv="note" data-mid="${esc(m.id)}" title="یک یادداشت برای حافظه‌ی مشاور بنویس">یادت بمونه</button>
    </div>` : '';
  return `
    <div class="adv-msg bot" data-mid="${esc(m.id)}">
      <div class="adv-meta">مشاور، ${advEffortLabel(m.effort)}${m.ms ? '، ' + advDur(m.ms) : ''}</div>
      ${tools}${body}${err}
      ${ideas ? `<div class="adv-ideas">${ideas}</div>` : ''}
      ${memos ? `<div class="adv-memos">${memos}</div>` : ''}
      ${acts}
      <div class="adv-noteform" hidden></div>
    </div>`;
}

function advLiveHTML(j) {
  return `<div class="adv-msg bot live" id="advLive">${advLiveInner(j)}</div>`;
}
function advLiveInner(j) {
  const segs = j.segs || [];
  const tools = segs.filter(s => s.t === 'tool');
  const text = advStrip(segs.filter(s => s.t === 'text').map(s => s.text).join('\n\n'));
  // offline/retry: اینترنت یا سرور Claude — نه «فکر کردن»؛ متنش از سرور می‌آید (note)
  const warn = j.activity === 'offline' || j.activity === 'retry';
  const act = warn ? (j.note || 'منتظر اینترنت…') : j.activity === 'writing' ? 'در حال نوشتن…'
            : j.activity === 'tool' ? (tools.at(-1)?.label || 'در حال خواندن') + '…' : 'در حال فکر کردن…';
  return `
    <div class="adv-think${warn ? ' warn' : ''}"><i class="spin"></i><span>${esc(act)}</span>
      <b id="advElapsed">${advFmtSecs(j.elapsed || 0)}</b>
      <span class="adv-chip dim">${advEffortLabel(j.effort)}</span>
      <button class="adv-icon" data-adv="stop">توقف</button></div>
    ${tools.length ? `<div class="adv-steps">${tools.map(t => `<span class="${t.done ? '' : 'now'}">${esc(t.label)}</span>`).join('')}</div>` : ''}
    ${text ? `<div class="adv-text md">${md(text)}</div>` : ''}`;
}

function advScroll(force) {
  const box = $('#advMsgs'); if (!box) return;
  const near = box.scrollHeight - box.scrollTop - box.clientHeight < 160;
  if (force || near) box.scrollTop = box.scrollHeight;
}

/* ---------- فرستادن و دنبال کردن جواب ---------- */
async function advSend(textArg) {
  const ta = $('#advInput');
  const text = (textArg ?? ta?.value ?? '').trim();
  if (!text || ADV.sending) return;
  if (ADV.chat?.job?.state === 'running') return toast('مشاور هنوز دارد جواب قبلی را می‌نویسد');
  ADV.sending = true; advSetBusy(true);
  try {
    if (!ADV.chat) {
      let drafts = [];
      try { drafts = (JSON.parse(localStorage.getItem('st-drafts') || '[]') || []).map(h => {
        const d = document.createElement('div'); d.innerHTML = h; return d.innerText.trim(); }).filter(Boolean); } catch {}
      $('#advMsgs').innerHTML = `<div class="adv-welcome"><p><i class="spin"></i> پرونده‌ی تازه ساخته می‌شود…</p></div>`;
      const r = await post('/api/advisor/new', { drafts });
      if (!r.ok) { toast(r.data.error || 'گفت‌وگو ساخته نشد'); return advRenderNew(); }
      try { localStorage.removeItem('adv-draft-new'); } catch {}
      await advLoadList(); await advOpen(r.data.id);
    }
    const id = ADV.chat.id, deep = !!$('#advDeep')?.checked;
    const r = await post('/api/advisor/send', { id, text, deep });
    if (!r.ok) { toast(r.data.error || 'فرستاده نشد'); return; }
    try { localStorage.removeItem('adv-draft-' + id); } catch {}
    if ($('#advInput')) $('#advInput').value = '';
    if ($('#advDeep')) $('#advDeep').checked = false;
    await advOpen(id);
    advLoadList();
    $('#advInput')?.focus();
  } finally { ADV.sending = false; advSetBusy(ADV.chat?.job?.state === 'running'); }
}

function advStartPoll(id) {
  advStopPoll(); ADV.pollId = id;
  const tick = async () => {
    if (ADV.pollId !== id || S.section !== 'advisor' || ADV.chat?.id !== id) return;
    const j = await api(`/api/advisor/poll?id=${encodeURIComponent(id)}`);
    if (ADV.pollId !== id) return;
    if (!j) { ADV.pollT = setTimeout(tick, 1500); return; }
    if (j.usage) { ADV.usage = j.usage; advRenderUsage(); }
    if (j.state === 'running') {
      const live = $('#advLive');
      if (live) { live.innerHTML = advLiveInner(j); advScroll(); }
      ADV.pollT = setTimeout(tick, 450);
      return;
    }
    ADV.pollId = null;
    const fresh = await api(`/api/advisor/chat?id=${encodeURIComponent(id)}`);
    if (!fresh || ADV.chat?.id !== id) return;
    ADV.chat = fresh; advRenderMsgs(); advSetBusy(false); advLoadList();
    const last = fresh.messages.at(-1);
    if (ADV.settings.autoplay && last?.role === 'assistant' && last.text) advPlay(last.id);
  };
  tick();
}
function advStopPoll() { clearTimeout(ADV.pollT); ADV.pollT = null; ADV.pollId = null; }

/* ---------- صدا ---------- */
function advPlayLabel(mid) {
  if (ADV.audio.mid !== mid || !ADV.audio.state) return '▶ بخوان';
  return ADV.audio.state === 'loading' ? '… در حال ساخت صدا' : '■ توقف';
}
function advMarkAudio(state) {
  ADV.audio.state = state;
  $$('.adv-actions [data-adv="play"]').forEach(b => {
    b.textContent = advPlayLabel(b.dataset.mid);
    b.classList.toggle('on', ADV.audio.mid === b.dataset.mid && !!state);
  });
}
function advStopAudio() {
  ADV.audio.token++;
  const a = ADV.audio.el; if (a) { a.pause(); a.removeAttribute('src'); a.load(); }
  ADV.audio.mid = null; advMarkAudio('');
}
async function advPlay(mid) {
  if (ADV.audio.mid === mid && ADV.audio.state) return advStopAudio();
  advStopAudio();
  const id = ADV.chat?.id; if (!id) return;
  const token = ++ADV.audio.token;
  ADV.audio.mid = mid; advMarkAudio('loading');
  const plan = await api(`/api/advisor/tts-plan?chat=${encodeURIComponent(id)}&msg=${encodeURIComponent(mid)}`);
  if (token !== ADV.audio.token) return;
  if (!plan || !plan.parts) { advStopAudio(); return toast('متنی برای خواندن نیست'); }
  const url = k => `/api/advisor/audio?chat=${encodeURIComponent(id)}&msg=${encodeURIComponent(mid)}&part=${k}&voice=${encodeURIComponent(plan.voice)}`;
  const fetchPart = async k => {
    try {
      const r = await fetch(url(k));
      if (!r.ok) { const e = await r.json().catch(() => ({})); return { ok: false, error: e.error }; }
      return { ok: true, src: URL.createObjectURL(await r.blob()) };
    } catch { return { ok: false }; }
  };
  const a = ADV.audio.el || (ADV.audio.el = new Audio());
  let next = fetchPart(0);
  for (let k = 0; k < plan.parts; k++) {
    const cur = await next;
    if (token !== ADV.audio.token) return;
    if (k + 1 < plan.parts) next = fetchPart(k + 1);
    if (!cur.ok) { toast(cur.error || 'صدا ساخته نشد'); break; }
    const ended = await new Promise(res => {
      a.onended = () => res(true); a.onerror = () => res(false);
      a.src = cur.src; a.playbackRate = ADV.settings.rate || 1;
      a.play().then(() => token === ADV.audio.token && advMarkAudio('playing')).catch(() => res(false));
    });
    URL.revokeObjectURL(cur.src);
    if (!ended || token !== ADV.audio.token) break;
  }
  if (token === ADV.audio.token) advStopAudio();
}

/* ---------- ضبط صدا ---------- */
async function advMic() {
  const R = ADV.rec;
  if (R.busy) return;
  if (R.mr && R.mr.state === 'recording') { clearInterval(R.timer); R.mr.stop(); return; }
  try {
    R.stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, channelCount: 1 } });
  } catch { return toast('دسترسی به میکروفون داده نشد'); }
  const types = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/ogg;codecs=opus'];
  const mime = types.find(t => window.MediaRecorder && MediaRecorder.isTypeSupported(t)) || '';
  R.chunks = [];
  R.mr = new MediaRecorder(R.stream, mime ? { mimeType: mime, audioBitsPerSecond: 32000 } : {});
  R.mr.ondataavailable = e => e.data.size && R.chunks.push(e.data);
  R.mr.onstop = async () => {
    R.stream.getTracks().forEach(t => t.stop());
    $('#advMic')?.classList.remove('on');
    const blob = new Blob(R.chunks, { type: R.mr.mimeType || 'audio/webm' });
    if ((Date.now() - R.t0) < 700) { $('#advRecState').textContent = ''; return; }
    R.busy = true; $('#advRecState').innerHTML = '<i class="spin"></i> تبدیل به متن…';
    const ext = blob.type.includes('mp4') ? 'm4a' : blob.type.includes('ogg') ? 'ogg' : 'webm';
    const data = await new Promise(res => { const f = new FileReader(); f.onload = () => res(f.result); f.readAsDataURL(blob); });
    const r = await post('/api/advisor/transcribe', { filename: `rec.${ext}`, data });
    R.busy = false; if ($('#advRecState')) $('#advRecState').textContent = '';
    if (!r.ok) return toast(r.data.error || 'رونویسی نشد');
    const ta = $('#advInput'); if (!ta) return;
    ta.value = (ta.value.trim() ? ta.value.trim() + ' ' : '') + r.data.text;
    ta.dispatchEvent(new Event('input')); ta.focus();
  };
  R.mr.start(250); R.t0 = Date.now();
  $('#advMic').classList.add('on');
  clearInterval(R.timer);
  R.timer = setInterval(() => {
    const s = (Date.now() - R.t0) / 1000, el = $('#advRecState');
    if (el) el.textContent = `در حال ضبط ${advFmtSecs(s)}`;
    if (s > 300) { clearInterval(R.timer); R.mr.stop(); }
  }, 250);
}

/* ---------- کشوها: حافظه و تنظیمات ---------- */
async function advOpenMemory() {
  const d = await api('/api/advisor/memory'); if (!d) return;
  const dr = $('#advDrawer'); dr.hidden = false;
  dr.innerHTML = `
    <div class="adv-dr-head"><h3>حافظه‌ی مشاور</h3><button class="adv-icon" data-adv="close">✕</button></div>
    <p class="adv-dr-note">مشاور این‌ها را در هر گفت‌وگوی تازه می‌خواند. «پیش‌نویس»ها را Claude از کارهای قبلی‌تان برداشته؛ تا تأییدشان نکنی، مشاور می‌داند که تأییدنشده‌اند. برای ویرایش، روی متن کلیک کن.</p>
    <ul class="adv-mem">${d.items.map(x => `
      <li data-id="${esc(x.id)}">
        <div class="adv-mem-text" contenteditable="true" spellcheck="false">${esc(x.text)}</div>
        <div class="adv-mem-meta">
          ${x.draft ? '<span class="adv-chip warn">پیش‌نویس</span>' : ''}
          <span>${esc(x.src || '')}، ${esc(advDay(x.at))}</span>
          <span class="grow"></span>
          ${x.draft ? `<button class="adv-link" data-adv="mem-ok">✓ درست است</button>` : ''}
          <button class="adv-link danger" data-adv="mem-del">حذف</button>
        </div>
      </li>`).join('') || '<li class="adv-none">هنوز چیزی در حافظه نیست.</li>'}</ul>
    <div class="adv-mem-add">
      <textarea id="advMemNew" rows="2" placeholder="یک چیز تازه که مشاور باید بداند…"></textarea>
      <button class="btn" data-adv="mem-add">+ اضافه کن</button>
    </div>`;
  $$('.adv-mem-text', dr).forEach(el => {
    el.dataset.orig = el.innerText;
    el.addEventListener('blur', async () => {
      const t = el.innerText.trim(); if (t === el.dataset.orig.trim()) return;
      const r = await post('/api/advisor/memory', { action: 'update', id: el.closest('li').dataset.id, text: t });
      if (r.ok) { el.dataset.orig = t; toast('✓ ذخیره شد'); advOpenMemory(); } else toast(r.data.error || 'ذخیره نشد');
    });
  });
}

function advOpenSettings() {
  const s = ADV.settings, dr = $('#advDrawer'); dr.hidden = false;
  dr.innerHTML = `
    <div class="adv-dr-head"><h3>صدا و تنظیمات</h3><button class="adv-icon" data-adv="close">✕</button></div>
    <h4>صدای مشاور</h4>
    <p class="adv-dr-note">هر دوازده صدا روی متن فارسی تست شده‌اند. «نمونه» را بزن و هرکدام را دوست داشتی انتخاب کن.</p>
    <ul class="adv-voices">${ADV.voices.map(v => `
      <li class="${v.id === s.voice ? 'on' : ''}">
        <button class="adv-vpick" data-adv="voice" data-v="${esc(v.id)}"><b dir="ltr">${esc(v.id)}</b><span>${esc(v.label)}</span></button>
        <button class="adv-link" data-adv="sample" data-v="${esc(v.id)}">▶ نمونه</button>
      </li>`).join('')}</ul>
    <h4>سرعت خواندن</h4>
    <div class="adv-seg">${ADV_RATES.map(r => `<button data-adv="rate" data-r="${r}" class="${Math.abs((s.rate || 1) - r) < .01 ? 'on' : ''}">${faNum(String(r).replace('.', '٫'))}×</button>`).join('')}</div>
    <label class="adv-check"><input type="checkbox" id="advAuto" ${s.autoplay ? 'checked' : ''}> هر جواب تازه را خودکار با صدا بخوان</label>
    <p class="adv-dr-note">صدا با Gemini 3.8 Flash TTS و کلید Gemini خودت ساخته می‌شود؛ هر جواب یک بار ساخته و ذخیره می‌شود.<br>
      مدل مشاور از «تنظیمات» عوض می‌شود. پیام عادی با effort «${esc(ADV.effort.normal)}»، و «عمیق‌تر فکر کن» با «${esc(ADV.effort.deep)}».</p>`;
  $('#advAuto').onchange = e => advSaveSettings({ autoplay: e.target.checked });
}
async function advSaveSettings(patch) {
  const r = await post('/api/advisor/settings', patch);
  if (r.ok) { ADV.settings = r.data.settings; return true; }
  toast('ذخیره نشد'); return false;
}
let ADV_SAMPLE = null;
async function advSample(v, btn) {
  if (ADV_SAMPLE && !ADV_SAMPLE.paused) { ADV_SAMPLE.pause(); if (ADV_SAMPLE._v === v) { btn.textContent = '▶ نمونه'; return; } }
  $$('[data-adv="sample"]').forEach(b => (b.textContent = '▶ نمونه'));
  btn.textContent = '… در حال ساخت';
  const r = await fetch(`/api/advisor/voice-sample?voice=${encodeURIComponent(v)}`);
  if (!r.ok) { btn.textContent = '▶ نمونه'; return toast('نمونه ساخته نشد'); }
  ADV_SAMPLE = new Audio(URL.createObjectURL(await r.blob())); ADV_SAMPLE._v = v;
  ADV_SAMPLE.playbackRate = ADV.settings.rate || 1;
  ADV_SAMPLE.onended = () => (btn.textContent = '▶ نمونه');
  btn.textContent = '■ توقف'; ADV_SAMPLE.play();
}

/* ---------- کلیک‌ها ---------- */
document.addEventListener('click', async e => {
  const b = e.target.closest('[data-adv]'); if (!b || !$('#adv')) return;
  const act = b.dataset.adv, c = ADV.chat, mid = b.dataset.mid;
  const msg = c && mid ? c.messages.find(m => m.id === mid) : null;
  if (act === 'new') { advStopPoll(); return advRenderNew(); }
  if (act === 'open') return advOpen(b.dataset.id);
  if (act === 'starter') {
    const ta = $('#advInput'); ta.value = ADV_STARTERS[+b.dataset.k][0];
    ta.dispatchEvent(new Event('input')); ta.focus(); ta.setSelectionRange(ta.value.length, ta.value.length); return;
  }
  if (act === 'send') return advSend();
  if (act === 'mic') return advMic();
  if (act === 'stop' && c) { b.disabled = true; await post('/api/advisor/stop', { id: c.id }); return; }
  if (act === 'retry' && c) {
    const r = await post('/api/advisor/retry', { id: c.id });
    if (!r.ok) return toast(r.data.error || 'نشد');
    return advOpen(c.id);
  }
  if (act === 'rename' && c) return advRename();
  if (act === 'delete' && c) {
    if (!confirm(`گفت‌وگوی «${c.title}» پاک شود؟`)) return;
    advStopAudio(); await post('/api/advisor/delete', { id: c.id });
    ADV.chat = null; await advLoadList(); return advRenderNew();
  }
  if (act === 'play' && mid) return advPlay(mid);
  if (act === 'copy' && msg) {
    return navigator.clipboard.writeText(msg.text).then(() => toast('✓ کپی شد'), () => toast('کپی نشد'));
  }
  if (act === 'idea' && msg) {
    b.disabled = true;
    const k = b.dataset.k !== undefined ? +b.dataset.k : undefined;
    const r = await post('/api/advisor/idea', { chat: c.id, msg: mid, index: k });
    if (!r.ok && !r.data.id) { b.disabled = false; return toast(r.data.error || 'ثبت نشد'); }   // ۴۰۹ شناسه‌ی ایده‌ی قبلی را دارد
    if (k !== undefined) msg.ideas[k].sent = r.data.id; else msg.sentAll = r.data.id;
    toast(r.ok ? '✓ به بانک ایده رفت' : (r.data.error || 'قبلاً رفته'));
    return advRenderMsgs();
  }
  if (act === 'goto-idea') {
    await loadState(); S.openIdea = b.dataset.idea; go('ideas'); return window.scrollTo(0, 0);
  }
  if (act === 'memo' && msg) {
    b.disabled = true;
    const k = +b.dataset.k;
    const r = await post('/api/advisor/memo', { chat: c.id, msg: mid, index: k });
    if (!r.ok) { b.disabled = false; return toast(r.data.error || 'ذخیره نشد'); }
    msg.memos[k].saved = r.data.id; toast('✓ در حافظه‌ی مشاور ماند'); return advRenderMsgs();
  }
  if (act === 'note' && msg) {
    const box = $(`.adv-msg[data-mid="${mid}"] .adv-noteform`); if (!box) return;
    if (!box.hidden) { box.hidden = true; return; }
    const sel = String(getSelection() || '').trim();
    box.hidden = false;
    box.innerHTML = `<textarea rows="2" placeholder="چه چیزی از این گفت‌وگو باید یادش بماند؟">${esc(sel)}</textarea>
      <button class="btn primary" data-adv="note-save" data-mid="${esc(mid)}">ذخیره در حافظه</button>`;
    return $('textarea', box).focus();
  }
  if (act === 'note-save' && c) {
    const t = b.previousElementSibling.value.trim(); if (!t) return toast('متن خالی است');
    const r = await post('/api/advisor/memory', { action: 'add', text: t, chat: c.id });
    if (!r.ok) return toast(r.data.error || 'ذخیره نشد');
    b.parentElement.hidden = true; return toast('✓ در حافظه‌ی مشاور ماند');
  }
  if (act === 'open-memory') return advOpenMemory();
  if (act === 'open-settings') return advOpenSettings();
  if (act === 'close') { $('#advDrawer').hidden = true; if (ADV_SAMPLE) ADV_SAMPLE.pause(); return; }
  if (act === 'mem-ok' || act === 'mem-del') {
    const id = b.closest('li').dataset.id;
    if (act === 'mem-del' && !confirm('این یادداشت از حافظه‌ی مشاور پاک شود؟')) return;
    const r = await post('/api/advisor/memory', { action: act === 'mem-ok' ? 'confirm' : 'delete', id });
    if (!r.ok) return toast(r.data.error || 'نشد');
    return advOpenMemory();
  }
  if (act === 'mem-add') {
    const t = $('#advMemNew').value.trim(); if (!t) return toast('متن خالی است');
    const r = await post('/api/advisor/memory', { action: 'add', text: t });
    if (!r.ok) return toast(r.data.error || 'نشد');
    return advOpenMemory();
  }
  if (act === 'voice') {
    if (await advSaveSettings({ voice: b.dataset.v })) { advStopAudio(); advOpenSettings(); toast('✓ صدای مشاور عوض شد'); }
    return;
  }
  if (act === 'sample') return advSample(b.dataset.v, b);
  if (act === 'rate') {
    if (await advSaveSettings({ rate: +b.dataset.r })) {
      if (ADV.audio.el) ADV.audio.el.playbackRate = ADV.settings.rate;
      advOpenSettings();
    }
  }
});

// تب دیگری باز شد: صدا و دنبال کردن جواب قطع شود (جواب روی سرور ادامه پیدا می‌کند)
document.getElementById('nav')?.addEventListener('click', e => {
  const b = e.target.closest('[data-sec]');
  if (b && b.dataset.sec !== 'advisor') { advStopPoll(); advStopAudio(); }
});
document.addEventListener('keydown', e => {
  if (e.key === 'Escape' && $('#advDrawer') && !$('#advDrawer').hidden) $('#advDrawer').hidden = true;
});

/* تب استوری متن هر استوری دانلود یا کپی‌شده را اینجا ثبت می‌کند تا مشاور ببیند */
window.advisorLogStory = text => {
  text = String(text || '').trim(); if (!text) return;
  post('/api/advisor/story', { text }).catch(() => {});
};

window.viewAdvisor = viewAdvisor;
