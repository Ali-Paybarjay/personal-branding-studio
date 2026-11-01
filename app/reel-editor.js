/* ================= ویرایشگر ریلز (بانک ایده) =================
   ریلز بخش‌بخش است: هر بخش همان‌جا ویرایش می‌شود (ذخیره‌ی خودکار)، نظر می‌گیرد و جدا بازتولید می‌شود.
   پایین صفحه: متن آماده‌ی ضبط = هوک انتخاب‌شده + بدنه + کال تو اکشن. سرور: app/reel_editor.py */
const RE = { id:null, el:null, reel:null, jobs:{}, timers:{}, saving:{}, poll:null,
             files:null, raw:'', rawSaved:'', rawTimer:null };
const RE_SECS = [
  ['title',    'تایتل',        'روی کاور و صفحه'],
  ['hooks',    'هوک‌ها',       '۳ ثانیه‌ی اول — یکی را برای متن نهایی انتخاب کن'],
  ['body',     'بدنه',         'بعد از هوک گفته می‌شود · سمت راست متن خام خودت برای مقایسه · Cmd+B = پررنگ (تأکید)'],
  ['cta',      'کال تو اکشن', 'جمله‌های پایانی ریلز'],
  ['caption',  'کپشن',         'متن زیر پست — گفته نمی‌شود'],
  ['hashtags', 'هشتگ‌ها',      ''],
];
const RE_NOTE_HINT = {
  title: 'مثلاً: کوتاه‌ترش کن و عدد بیاور',
  hooks: 'مثلاً: هوک ۳ را دوست دارم، بقیه را هم همین‌قدر مستقیم کن',
  body: 'مثلاً: بخش دوم را بیشتر توضیح بده و یک مثال واقعی بیاور',
  cta: 'مثلاً: به‌جای سؤال، بگو ذخیره‌اش کنند',
  caption: 'مثلاً: خط اول را سؤالی کن',
  hashtags: 'مثلاً: هشتگ‌های مهاجرتی هم اضافه کن',
};
const RE_RICH = new Set(['body', 'cta', 'caption']);   // ویرایش با پررنگ واقعی، نه علامت **
const reWords = t => String(t || '').replace(/\*\*/g, '').split(/\s+/).filter(Boolean).length;
const rePlain = t => String(t || '').replace(/\*\*/g, '');

async function mountReelEditor(el, idea, files) {
  if (RE.rawTimer) await reRawSave();   // متن خامِ ذخیره‌نشده‌ی ایده‌ی قبلی، پیش از عوض شدن RE.id
  RE.id = idea.id; RE.el = el; clearInterval(RE.poll);
  RE.files = files; RE.raw = files.raw || ''; RE.rawSaved = RE.raw.trim();
  const d = await api(`/api/idea/reel?id=${encodeURIComponent(idea.id)}`);
  RE.reel = d && d.reel; RE.jobs = (d && d.jobs) || {};
  if (!RE.reel) {
    if (files.reel) el.innerHTML = `<section class="panel" style="margin-bottom:16px"><h3>ریلز ساخته‌شده</h3>
      <p class="re-legacy">این ریلز با قالب قدیمی (یک‌تکه) ساخته شده. «دوباره: ساخت ریلز» را بزن تا بخش‌بخش و قابل ویرایش شود.</p>
      <div class="md" style="max-width:none">${md(files.reel)}</div></section>`;
    return;
  }
  const r = RE.reel;
  el.innerHTML = `<section class="reel-ed">
      <div class="re-top"><h3>ریلز</h3>${r.note ? `<span class="re-score">${esc(r.note)}</span>` : ''}</div>
      ${RE_SECS.map(([k, l, h]) => `
        <div class="re-sec" data-sec="${k}">
          <div class="re-head">
            <h4>${l}</h4>${h ? `<span class="re-hint">${inline(h)}</span>` : ''}
            <span class="grow"></span>
            <span class="re-save" data-save="${k}"></span>
            ${k === 'caption' || k === 'hashtags' ? `<button class="re-mini" data-recopy="${k}">کپی</button>` : ''}
          </div>
          ${k === 'body' ? reCmpHTML() : `<div class="re-content" data-content="${k}"></div>`}
          <div class="re-busy" data-busy="${k}" hidden><span class="spin"></span> در حال بازتولید «${l}»… چند دقیقه طول می‌کشد</div>
          <div class="re-err" data-err="${k}" hidden></div>
          <div class="re-fb">
            <textarea class="re-note" data-note="${k}" rows="1" placeholder="نظرت درباره‌ی ${l}… ${RE_NOTE_HINT[k]}"></textarea>
            <button class="btn re-undo" data-undo="${k}" title="برگشت به نسخه‌ی قبل از آخرین بازتولید">↶ نسخه‌ی قبل</button>
            <button class="btn primary" data-regen="${k}">↻ بازتولید</button>
          </div>
          <p class="re-last" data-last="${k}"></p>
        </div>`).join('')}
    </section>
    <section class="re-final" id="reFinal"></section>`;
  RE_SECS.forEach(([k]) => reRenderSec(k));
  reRenderFinal();
  const rawTa = $('[data-raw]', el); fitHeight(rawTa); reWc('raw', RE.raw);
  const rawBox = $('[data-box="raw"]'); if (rawBox) rawBox.style.display = 'none';   // همان متن، حالا کنار بدنه
  el.addEventListener('input', reOnInput);
  el.addEventListener('click', reOnClick);
  el.addEventListener('paste', e => {
    if (!e.target.closest('.re-rich')) return;
    e.preventDefault();
    document.execCommand('insertText', false, (e.clipboardData || window.clipboardData).getData('text/plain'));
  });
  $$('.re-note', el).forEach(reGrow);
  if (Object.values(RE.jobs).some(j => j.state === 'running')) rePoll();
}

/* ---- بدنه کنار متن خام: راست = raw.md خود کاربر، چپ = بدنه. هر دو ویرایش‌پذیرند.
   ستون متن خام فقط یک بار ساخته می‌شود؛ reRenderSec('body') فقط ستون بدنه را عوض می‌کند،
   تا پایان یک بازتولید وسط تایپ، متن خام را از زیر دست کاربر نکشد. ---- */
function reCmpHTML() {
  return `<div class="re-cmp">
      <div class="re-cmp-col">
        <div class="re-cmp-head"><b class="mine">متن خام تو</b><span class="re-meta" data-wc="raw"></span>
          <span class="grow"></span><span class="re-save" data-save="raw"></span></div>
        <textarea class="re-raw" data-raw="1" rows="1" spellcheck="false" placeholder="متن ایده‌ات…">${esc(RE.raw)}</textarea>
        <p class="re-hint re-cmp-note">ویرایش این متن بدنه را عوض نمی‌کند. برای بازنویسی بدنه از روی متن تازه، پایین بنویس «از روی متن خامم بازنویسی کن» و «↻ بازتولید» را بزن.</p>
      </div>
      <div class="re-cmp-col">
        <div class="re-cmp-head"><b>بدنه‌ی نوشته‌ی AI</b><span class="re-meta" data-wc="body"></span></div>
        <div class="re-content" data-content="body"></div>
      </div>
    </div>`;
}
function reWc(k, text) {
  const s = $(`[data-wc="${k}"]`, RE.el); if (s) s.textContent = `${faNum(reWords(text))} کلمه`;
}

/* ---- رندر یک بخش ---- */
function reRenderSec(k) {
  const r = RE.reel, box = $(`[data-content="${k}"]`, RE.el); if (!box) return;
  const busy = (RE.jobs[k] || {}).state === 'running';
  if (RE_RICH.has(k)) {
    box.innerHTML = `<div class="re-rich ${k === 'body' ? 'big' : ''}" data-field="${k}"
      contenteditable="${busy ? 'false' : 'true'}" spellcheck="false">${reRichHTML(r[k])}</div>`;
  } else if (k === 'hooks') {
    const hooks = r.hooks || [];
    box.innerHTML = `<ol class="re-hooks">${hooks.map((h, i) => `
        <li class="re-hook ${i === (r.pick || 0) ? 'on' : ''}">
          <button class="re-pick" data-pick="${i}" title="این هوک در متن نهایی بیاید">${i === (r.pick || 0) ? '✓ انتخاب' : 'انتخاب'}</button>
          <span class="re-n">${faNum(i + 1)}</span>
          <textarea class="re-in" data-hook="${i}" rows="1">${esc(h)}</textarea>
          <button class="re-x" data-hookdel="${i}" title="حذف این هوک">✕</button>
        </li>`).join('')}</ol>
      <button class="re-mini" data-hookadd="1">+ هوک تازه</button>`;
  } else {
    box.innerHTML = `<textarea class="re-in ${k === 'body' ? 'big' : ''}" data-field="${k}" rows="1">${esc(r[k] || '')}</textarea>`;
  }
  $$('.re-in', box).forEach(reGrow);
  if (k === 'body') reWc('body', r.body);
  $(`[data-busy="${k}"]`, RE.el).hidden = !busy;
  $(`[data-sec="${k}"]`, RE.el).classList.toggle('busy', busy);
  $$('.re-in, .re-note, [data-regen], [data-undo], .re-pick, .re-x, [data-hookadd]', $(`[data-sec="${k}"]`, RE.el))
    .forEach(x => (x.disabled = busy));
  const err = (RE.jobs[k] || {}).state === 'error' ? RE.jobs[k].error : '';
  const eb = $(`[data-err="${k}"]`, RE.el); eb.hidden = !err; eb.textContent = err ? '✕ ' + err : '';
  $(`[data-undo="${k}"]`, RE.el).hidden = !(r.prev && r.prev[k] != null);
  const last = ((r.notes || {})[k] || []).slice(-1)[0];
  const lp = $(`[data-last="${k}"]`, RE.el);
  lp.textContent = last ? `آخرین نظرت (${faNum(last.at)}): «${last.t}»` : ''; lp.hidden = !last;
}

/* ---- ویرایشگر متنی: مارک‌داون ساده ⇄ HTML (فقط پاراگراف، خط تازه و پررنگ) ---- */
function reRichHTML(src) {
  const paras = String(src || '').split(/\n\s*\n/).filter(x => x.trim());
  if (!paras.length) return '<p><br></p>';
  return paras.map(p => '<p>' + esc(p.trim()).replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/\n/g, '<br>') + '</p>').join('');
}
function reRichMD(el) {
  const inl = n => {
    if (n.nodeType === 3) return n.nodeValue.replace(/\u00a0/g, ' ');
    if (n.nodeType !== 1) return '';
    if (n.tagName === 'BR') return '\n';
    const inner = [...n.childNodes].map(inl).join('');
    if ((n.tagName === 'STRONG' || n.tagName === 'B') && inner.replace(/\*\*/g, '').trim()) {
      const m = inner.replace(/\*\*/g, '').match(/^(\s*)([\s\S]*?)(\s*)$/);   // فاصله‌ها بیرون از **
      return `${m[1]}**${m[2]}**${m[3]}`;
    }
    return inner;
  };
  const blocks = []; let run = '';
  for (const n of el.childNodes) {
    if (n.nodeType === 1 && /^(P|DIV)$/.test(n.tagName)) {
      if (run.trim()) blocks.push(run); run = '';
      blocks.push(inl(n));
    } else run += inl(n);
  }
  if (run.trim()) blocks.push(run);
  return blocks.map(b => b.replace(/[ \t]+\n/g, '\n').replace(/\n+$/, '').trim()).filter(Boolean).join('\n\n');
}

function reGrow(t) { t.style.height = 'auto'; t.style.height = (t.scrollHeight + 2) + 'px'; }

/* ---- متن آماده‌ی ضبط ---- */
function reFinal() {
  const r = RE.reel, hooks = r.hooks || [];
  const hook = hooks[r.pick || 0] ?? hooks[0] ?? '';
  return [hook, r.body, r.cta].map(x => String(x || '').trim()).filter(Boolean).join('\n\n');
}
function reRenderFinal() {
  const box = $('#reFinal'); if (!box) return;
  const t = reFinal(), w = reWords(t), secs = Math.round(w / 160 * 60);
  box.innerHTML = `<div class="re-final-head">
      <h3>متن آماده‌ی ضبط</h3>
      <span class="re-meta">${faNum(w)} کلمه · حدود ${faNum(Math.floor(secs / 60))}:${faNum(String(secs % 60).padStart(2, '0'))}</span>
      <span class="grow"></span>
      <button class="btn" data-recopy="final">کپی متن</button>
      <button class="btn primary" data-retp="1">▶ تله‌پرامپتر</button>
    </div>
    <p class="re-hint" style="margin:0 0 6px">هوک انتخاب‌شده + بدنه + کال تو اکشن. با هر ویرایش بالا، همین‌جا به‌روز می‌شود.</p>
    <div class="script-text re-final-text">${md(t)}</div>`;
}

/* ---- ویرایش و ذخیره‌ی خودکار ---- */
function reOnInput(e) {
  const t = e.target;
  if (t.dataset.raw) {   // متن خام در متن ضبط نمی‌آید، پس reRenderFinal لازم نیست
    fitHeight(t); RE.raw = t.value; reWc('raw', t.value); return reRawQueue();
  }
  if (t.matches('.re-in, .re-note')) reGrow(t);
  if (t.dataset.field) {
    RE.reel[t.dataset.field] = t.isContentEditable ? reRichMD(t) : t.value;
    reQueueSave(t.dataset.field);
    if (t.dataset.field === 'body') reWc('body', RE.reel.body);
  }
  else if (t.dataset.hook != null) { RE.reel.hooks[+t.dataset.hook] = t.value; reQueueSave('hooks'); }
  else return;
  reRenderFinal();
}
function reQueueSave(k) {
  reSaveMark(k, 'در حال ذخیره…', '');
  clearTimeout(RE.timers[k]);
  RE.timers[k] = setTimeout(() => reSave(k), 700);
}
async function reSave(k) {
  clearTimeout(RE.timers[k]); delete RE.timers[k];
  const value = k === 'pick' ? (RE.reel.pick || 0) : RE.reel[k];
  const r = await post('/api/idea/reel/save', { id: RE.id, field: k, value });
  const shown = k === 'pick' ? 'hooks' : k;
  if (r.ok) reSaveMark(shown, '✓ ذخیره شد', 'ok');
  else reSaveMark(shown, '✕ ' + (r.data.error || 'ذخیره نشد'), 'bad');
  return r.ok;
}
/* متن خام ← raw.md از همان مسیر «✎ ویرایش» (/api/idea/edit، فقط فیلد raw). */
function reRawQueue() {
  reSaveMark('raw', 'در حال ذخیره…', '');
  clearTimeout(RE.rawTimer);
  RE.rawTimer = setTimeout(reRawSave, 900);
}
async function reRawSave() {
  clearTimeout(RE.rawTimer); RE.rawTimer = null;
  const id = RE.id, el = RE.el, raw = RE.raw.trim();
  if (!raw) { reSaveMark('raw', 'متن خالی ذخیره نمی‌شود', 'bad'); return false; }
  if (raw === RE.rawSaved) { reSaveMark('raw', '', ''); return true; }
  const r = await post('/api/idea/edit', { id, raw });
  if (!r.ok) { reSaveMark('raw', '✕ ' + (r.data.error || 'ذخیره نشد'), 'bad'); return false; }
  if (RE.id !== id) return true;   // کاربر در این فاصله ایده‌ی دیگری باز کرده
  RE.rawSaved = raw; RE.files.raw = raw;   // فرم «✎ ویرایش» بالای صفحه هم با همین متن باز شود
  const i = S.ideas.findIndex(x => x.id === id); if (i >= 0) S.ideas[i] = r.data.idea;
  reSaveMark('raw', '✓ ذخیره شد', 'ok');
  // یادداشت زرد «متن ایده بعد از ساختِ … عوض شده» را تازه کن، مگر فرم ویرایش بالا باز باشد
  const f = await api(`/api/idea/files?id=${encodeURIComponent(id)}`);
  if (f && RE.id === id && document.body.contains(el) && !$('#edRaw')) {
    RE.files.stale = f.stale || [];
    showIdeaHead(r.data.idea, RE.files);
  }
  return true;
}
function reSaveMark(k, text, cls) {
  const s = $(`[data-save="${k}"]`, RE.el); if (!s) return;
  s.textContent = text; s.className = 're-save ' + cls;
  if (cls === 'ok') { clearTimeout(s._t); s._t = setTimeout(() => { s.textContent = ''; }, 2500); }
}

/* ---- کلیک‌ها ---- */
async function reOnClick(e) {
  const b = e.target.closest('button'); if (!b || b.disabled) return;
  const r = RE.reel;
  if (b.dataset.pick != null) {
    r.pick = +b.dataset.pick; reRenderSec('hooks'); reRenderFinal(); return reSave('pick');
  }
  if (b.dataset.hookdel != null) {
    if ((r.hooks || []).length <= 1) return toast('حداقل یک هوک لازم است');
    const i = +b.dataset.hookdel; r.hooks.splice(i, 1);
    if ((r.pick || 0) > i || (r.pick || 0) >= r.hooks.length) r.pick = Math.max(0, (r.pick || 0) - 1);
    reRenderSec('hooks'); reRenderFinal(); return reSave('hooks');
  }
  if (b.dataset.hookadd) {
    r.hooks.push(''); reRenderSec('hooks');
    const ts = $$('[data-hook]', RE.el); ts[ts.length - 1].focus(); return;
  }
  if (b.dataset.recopy) {
    const k = b.dataset.recopy;
    const text = k === 'final' ? rePlain(reFinal()) : rePlain(r[k]);
    return navigator.clipboard.writeText(text).then(() => toast('✓ کپی شد'), () => toast('کپی نشد'));
  }
  if (b.dataset.retp) {
    const t = reFinal();
    return tpOpenScript({ title: r.title || 'ریلز', body: t, secs: Math.round(reWords(t) / 160 * 60) });
  }
  if (b.dataset.regen) return reRegen(b.dataset.regen);
  if (b.dataset.undo) {
    const k = b.dataset.undo;
    if (RE.timers[k]) await reSave(k);
    const res = await post('/api/idea/reel/undo', { id: RE.id, field: k });
    if (!res.ok) return toast(res.data.error || 'برنگشت');
    await reRefresh([k]); toast('↶ نسخه‌ی قبل برگشت — دوباره بزنی، برمی‌گردد');
  }
}

async function reRegen(k) {
  // اول ویرایش‌های ذخیره‌نشده را بفرست تا بازتولید روی آخرین نسخه‌ی تو انجام شود
  for (const f of Object.keys(RE.timers)) await reSave(f);
  if (RE.rawTimer) await reRawSave();   // بازتولید ممکن است raw.md را بخواند
  const noteEl = $(`[data-note="${k}"]`, RE.el);
  const res = await post('/api/idea/reel/regen', { id: RE.id, field: k, note: noteEl.value.trim() });
  if (!res.ok) return toast(res.data.error || 'شروع نشد');
  RE.jobs[k] = { state: 'running', error: '' };
  reRenderSec(k); rePoll();
}

async function reRefresh(fields) {
  const d = await api(`/api/idea/reel?id=${encodeURIComponent(RE.id)}`);
  if (!d || !d.reel) return null;
  for (const k of fields) {
    RE.reel[k] = d.reel[k];
    if (k === 'hooks') RE.reel.pick = d.reel.pick;
  }
  RE.reel.prev = d.reel.prev; RE.reel.notes = d.reel.notes;
  fields.forEach(reRenderSec); reRenderFinal();
  return d;
}

function rePoll() {
  clearInterval(RE.poll);
  RE.poll = setInterval(async () => {
    if (!RE.el || !document.body.contains(RE.el)) return clearInterval(RE.poll);
    const d = await api(`/api/idea/reel?id=${encodeURIComponent(RE.id)}`); if (!d) return;
    const finished = Object.keys(RE.jobs).filter(k =>
      RE.jobs[k].state === 'running' && d.jobs[k] && d.jobs[k].state !== 'running');
    for (const k of finished) {
      RE.jobs[k] = d.jobs[k];
      if (d.jobs[k].state === 'done') {
        RE.reel[k] = d.reel[k]; if (k === 'hooks') RE.reel.pick = d.reel.pick;
        RE.reel.prev = d.reel.prev; RE.reel.notes = d.reel.notes;
        const n = $(`[data-note="${k}"]`, RE.el); if (n) { n.value = ''; reGrow(n); }
        toast(`✓ «${RE_SECS.find(s => s[0] === k)[1]}» بازتولید شد`);
      }
      reRenderSec(k); reRenderFinal();
    }
    if (!Object.values(RE.jobs).some(j => j.state === 'running')) clearInterval(RE.poll);
  }, 2500);
}

window.mountReelEditor = mountReelEditor;
