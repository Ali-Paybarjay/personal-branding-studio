/* ================= هسته‌ی برند =================
   فرمی خوانا به جای مارک‌داون خام. پاسخ‌ها در brand/brand-core.json ذخیره
   می‌شوند و سرور از روی آن‌ها brand/brand-core.md را می‌سازد — همان فایلی که
   ایجنت‌ها پیش از نوشتن می‌خوانند. سؤال‌ها (schema) در app/brand.py هستند. */

const BC = {
  schema: [], fields: {}, md: '', view: 'form', filter: 'all',
  timer: null, inflight: false, again: false, dirty: false, savedAt: null,
  changed: new Set(),          // فقط همین‌ها ذخیره می‌شوند؛ بقیه را سرور از نسخه‌ی روی دیسک برمی‌دارد
};
const BC_LEVEL = { 1: ['ضروری', 'must'], 2: ['مهم', 'should'], 3: ['اختیاری', 'opt'] };
const BC_FILTERS = [['all', 'همه'], ['empty', 'بی‌جواب'], ['draft', 'نیاز به بررسی'], ['must', 'فقط ضروری']];

const bcAll = () => BC.schema.flatMap(s => s.fields);
const bcField = id => bcAll().find(f => f.id === id);
const bcVal = id => (BC.fields[id] || {}).v;
const bcSrc = id => (BC.fields[id] || {}).src;

function bcFilled(f, v = bcVal(f.id)) {
  if (v == null) return false;
  if (f.type === 'list') return Array.isArray(v) && v.some(x => String(x).trim());
  if (f.type === 'group' || f.type === 'palette' || f.type === 'images')
    return Array.isArray(v) && v.some(it => it && Object.entries(it).some(([k, x]) => k !== 'bg' && String(x ?? '').trim()));
  if (f.type === 'scales') return typeof v === 'object' && Object.values(v).some(Boolean);
  return String(v).trim() !== '';
}
const bcScaleWord = (s, n) => ({ 1: `کاملاً ${s.a}`, 2: `بیشتر ${s.a}`, 3: 'میانه', 4: `بیشتر ${s.b}`, 5: `کاملاً ${s.b}` })[n];

/* ---------- صفحه ---------- */
async function viewBrand() {
  $('#page').innerHTML = '<div class="empty">در حال بارگذاری…</div>';
  const d = await api('/api/brand');
  if (!d || !Array.isArray(d.schema)) {
    $('#page').innerHTML = '<div class="empty">هسته‌ی برند بارگذاری نشد. سرور استودیو را یک بار ببند و دوباره باز کن.</div>';
    return;
  }
  Object.assign(BC, { schema: d.schema, fields: d.fields || {}, md: d.md || '', savedAt: d.updated || null, changed: new Set() });
  $('#page').innerHTML = `
    <div class="bc-wrap">
      <div class="page-head bc-head">
        <div><h2>هسته‌ی برند</h2>
          <p>هر ایجنتی که برایت محتوا می‌سازد، اول این‌ها را می‌خواند. هر سؤالی که جواب بدهی، از تولید بعدی در خروجی‌ها اثر می‌گذارد.</p></div>
        <div class="bc-seg">
          <button data-bcview="form">پرسش‌نامه</button>
          <button data-bcview="md">متنی که ایجنت می‌خواند</button>
        </div>
      </div>
      <div class="bc-layout">
        <aside class="bc-side">
          <div id="bcProg"></div>
          <div id="bcSave" class="bc-save"></div>
          <button class="btn primary bc-next" id="bcNext">سؤال ضروریِ بعدی</button>
          <div class="bc-flt">${BC_FILTERS.map(([k, l]) => `<button data-bcflt="${k}">${l}</button>`).join('')}</div>
          <nav class="bc-toc">${BC.schema.map((s, i) => `
            <a href="#bc-${s.id}" data-bcgo="${s.id}"><span><b>${faNum(i + 1)}</b>${esc(s.title)}</span><em data-tcount="${s.id}"></em></a>`).join('')}
          </nav>
        </aside>
        <div id="bcBody" class="bc-body"></div>
      </div>
    </div>`;
  bcBody();
  bcSaveState(BC.savedAt ? 'saved' : 'idle');
}

function bcBody() {
  $$('[data-bcview]').forEach(b => b.classList.toggle('on', b.dataset.bcview === BC.view));
  $$('[data-bcflt]').forEach(b => b.classList.toggle('on', b.dataset.bcflt === BC.filter));
  const body = $('#bcBody');
  if (BC.view === 'md') {
    body.innerHTML = `
      <div class="bc-mdnote">
        <p>این متن خودکار از جواب‌های پرسش‌نامه ساخته می‌شود و در <code>brand/brand-core.md</code> ذخیره است. سؤال‌های بی‌جواب در آن نمی‌آیند؛ فقط اسمشان در آخر فهرست می‌شود تا ایجنت درباره‌شان حدس نزند.</p>
        <button class="btn" id="bcCopy">کپی متن</button>
      </div>
      <div class="md bc-md">${md(BC.md)}</div>`;
  } else {
    body.innerHTML = BC.schema.map(bcSectionHTML).join('') + '<div class="empty bc-none" hidden>در این فیلتر سؤالی نمانده.</div>';
    $$('.bc-in', body).forEach(bcGrow);
    bcApplyFilter();
  }
  bcStats();
}

function bcSectionHTML(s, i) {
  return `<section class="bc-sec" id="bc-${s.id}">
    <header class="bc-sec-head"><span class="n">${faNum(i + 1)}</span><h3>${esc(s.title)}</h3><span class="c" data-count="${s.id}"></span></header>
    ${s.why ? `<p class="bc-why">${esc(s.why)}</p>` : ''}
    ${s.board ? `<div id="bcBoard">${bcBoardHTML()}</div>` : ''}
    ${s.fields.map(bcFieldHTML).join('')}
  </section>`;
}

function bcFieldHTML(f) {
  const src = bcSrc(f.id), [lv, lc] = BC_LEVEL[f.level] || BC_LEVEL[2];
  return `<div class="bc-f ${bcFilled(f) ? 'bc-filled' : 'bc-empty'} ${src ? 'bc-isdraft' : ''}" data-f="${f.id}">
    <div class="bc-k"><span>${esc(f.label)}</span><i class="bc-tag ${lc}">${lv}</i></div>
    <div class="bc-q">${esc(f.q)}</div>
    ${f.help ? `<p class="bc-help">${esc(f.help)}</p>` : ''}
    <div class="bc-ctl">${bcControl(f)}</div>
    ${f.chips ? `<div class="bc-chips"><span>${f.type === 'list' ? 'افزودن سریع:' : 'انتخاب سریع:'}</span>${f.chips.map(c =>
      `<button data-bcchip="${f.id}" data-c="${esc(c)}">${esc(c)}</button>`).join('')}</div>` : ''}
    ${src ? bcSrcHTML(f.id, src) : ''}
  </div>`;
}
function bcSrcHTML(id, src) {
  const note = (BC.fields[id] || {}).note;
  return `<div class="bc-src"><div><span><i class="bc-draft">پیش‌نویس</i> از ${esc(src)}. اگر درست است تأیید کن، وگرنه همین‌جا اصلاحش کن.</span>
    ${note ? `<p class="bc-note">⚠ ${esc(note)}</p>` : ''}</div>
    <button data-bcok="${id}">✓ درست است</button></div>`;
}

function bcControl(f) {
  const v = bcVal(f.id);
  const ta = (attrs, val, ph, one) =>
    `<textarea class="bc-in${one ? ' one' : ''}" rows="1" ${attrs} placeholder="${esc(ph || '')}">${esc(val ?? '')}</textarea>`;
  if (f.type === 'text') return ta(`data-in="${f.id}"`, v, f.ph, true);
  if (f.type === 'para') return ta(`data-in="${f.id}"`, v, f.ph);
  if (f.type === 'list') {
    const items = Array.isArray(v) && v.length ? v : [''];
    return `<div class="bc-list">${items.map((x, i) => `<div class="bc-li">
        ${ta(`data-in="${f.id}" data-i="${i}"`, x, i === 0 ? f.ph : '')}
        <button class="bc-x" data-bcdel="${f.id}" data-i="${i}" title="حذف این مورد">✕</button></div>`).join('')}</div>
      <button class="bc-add" data-bcadd="${f.id}">+ مورد تازه</button>`;
  }
  if (f.type === 'group') {
    const items = Array.isArray(v) && v.length ? v : [{}];
    return `${items.map((it, i) => `<div class="bc-card">
        <button class="bc-x" data-bcdel="${f.id}" data-i="${i}" title="حذف">✕</button>
        ${f.item.map(s => `<div class="bc-sub"><label>${esc(s.label)}</label>
          ${ta(`data-in="${f.id}" data-i="${i}" data-k="${s.id}"`, it[s.id], s.ph, s.type === 'text')}</div>`).join('')}
        ${f.preview === 'font' ? `<div class="bc-fontprev" style="font-family:${esc(bcFontFam(it.name))}">${esc(bcSample())}</div>` : ''}
      </div>`).join('')}
      <button class="bc-add" data-bcadd="${f.id}">+ ${esc(f.add || 'افزودن')}</button>`;
  }
  if (f.type === 'palette') {
    const items = Array.isArray(v) ? v : [];
    const inp = (i, k, val, ph, cls = '') => `<input class="bc-in bc-sm ${cls}" ${cls ? 'dir="ltr" spellcheck="false"' : ''}
      value="${esc(val || '')}" placeholder="${esc(ph)}" data-in="${f.id}" data-i="${i}" data-k="${k}">`;
    return `<div class="bc-pal-strip">${bcStripHTML(items)}</div>
      <div class="bc-pal-grid">${items.map((c, i) => {
        const hx = bcHex(c.hex);
        return `<div class="bc-color" data-i="${i}">
          <label class="bc-swatch" style="--c:${hx || 'transparent'}" title="انتخاب رنگ">
            <input type="color" value="${hx || '#000000'}" data-pal="${f.id}" data-i="${i}"></label>
          <div class="bc-color-f">
            <div class="bc-color-row">${inp(i, 'hex', c.hex, '#1d4355', 'hex')}${inp(i, 'name', c.name, 'اسم رنگ')}</div>
            <div class="bc-roles">${BC_ROLES.map(r => `<button class="${c.role === r ? 'on' : ''}"
              data-palrole="${f.id}" data-i="${i}" data-r="${r}">${r}</button>`).join('')}</div>
            ${inp(i, 'use', c.use, 'کجا استفاده شود؟')}
          </div>
          <button class="bc-x" data-bcdel="${f.id}" data-i="${i}" title="حذف رنگ">✕</button>
        </div>`; }).join('')}</div>
      <button class="bc-add" data-bcadd="${f.id}">+ ${esc(f.add || 'رنگ تازه')}</button>`;
  }
  if (f.type === 'images') {
    const items = Array.isArray(v) ? v : [];
    return `<div class="bc-imgs">${items.map((it, i) => {
        const url = '/brand-assets/' + encodeURIComponent(it.file);
        return `<figure class="bc-img">
          <a class="bc-img-box${it.bg === 'dark' ? ' dark' : ''}" href="${url}" target="_blank" rel="noopener" title="دیدن اندازه‌ی واقعی">
            <img src="${url}" alt="${esc(it.caption || '')}" loading="lazy"></a>
          <div class="bc-img-bar">
            <input class="bc-in bc-sm" value="${esc(it.caption || '')}" placeholder="توضیح، مثلاً لوگوی اصلی"
              data-in="${f.id}" data-i="${i}" data-k="caption">
            <button class="bc-imgbtn" data-imgbg="${f.id}" data-i="${i}" title="زمینه‌ی روشن یا تیره">◐</button>
            <button class="bc-imgbtn del" data-imgdel="${f.id}" data-i="${i}" title="حذف تصویر">✕</button>
          </div></figure>`; }).join('')}
      <label class="bc-drop" data-imgdrop="${f.id}">
        <input type="file" accept="image/*" multiple hidden data-imgfile="${f.id}">
        <b>+ افزودن تصویر</b><span>فایل را اینجا بکش و رها کن، یا کلیک کن</span>
      </label></div>`;
  }
  if (f.type === 'scales') {
    const o = v && typeof v === 'object' ? v : {};
    return f.scales.map(s => `<div class="bc-scale">
        <span class="a">${esc(s.a)}</span>
        <span class="bc-dots">${[1, 2, 3, 4, 5].map(n => `<button class="bc-dot${o[s.id] === n ? ' on' : ''}"
          data-bcscale="${f.id}" data-s="${s.id}" data-n="${n}" title="${esc(bcScaleWord(s, n))}"></button>`).join('')}</span>
        <span class="b">${esc(s.b)}</span>
        <em>${o[s.id] ? esc(bcScaleWord(s, o[s.id])) : 'انتخاب نشده'}</em>
      </div>`).join('');
  }
  return '';
}

function bcGrow(el) {
  if (el.tagName !== 'TEXTAREA') return;
  el.style.height = 'auto'; el.style.height = (el.scrollHeight + 2) + 'px';
}

/* ---------- رنگ، فونت و نمای کلی بصری ---------- */
const BC_ROLES = ['اصلی', 'فرعی', 'تأکیدی'];
const BC_ROLE_ORDER = { 'اصلی': 0, 'فرعی': 1, 'تأکیدی': 2 };
const BC_BOARD_FIELDS = ['logo', 'colors', 'fonts', 'tagline'];
function bcHex(h) {
  const m = String(h || '').trim().match(/^#?([0-9a-f]{6}|[0-9a-f]{3})$/i); if (!m) return null;
  const x = m[1].toLowerCase(); return '#' + (x.length === 3 ? x.split('').map(c => c + c).join('') : x);
}
function bcInk(hex) {                       // متن خوانا روی هر رنگ
  const n = parseInt(hex.slice(1), 16);
  return (0.299 * (n >> 16) + 0.587 * ((n >> 8) & 255) + 0.114 * (n & 255)) > 150 ? '#0b1c24' : '#ffffff';
}
function bcFontFam(name) {                  // «وزیرمتن (Vazirmatn)» ← "Vazirmatn"
  const m = String(name || '').match(/\(([^)]+)\)/);
  const n = (m ? m[1] : String(name || '')).replace(/["'\\;]/g, '').trim();
  return n ? `"${n}", "Brand ${n}", var(--font)` : 'var(--font)';
}
const bcSample = () => String(bcVal('tagline') || 'در عصر هوش مصنوعی، «غیرقابل جایگزین» شو!');
function bcColors() {
  const v = bcVal('colors');
  return (Array.isArray(v) ? v : []).map(c => ({ ...c, hx: bcHex(c.hex) })).filter(c => c.hx)
    .sort((a, b) => (BC_ROLE_ORDER[a.role] ?? 3) - (BC_ROLE_ORDER[b.role] ?? 3));
}
function bcStripHTML(items) {
  const cs = (items || []).map(c => ({ ...c, hx: bcHex(c.hex) })).filter(c => c.hx)
    .sort((a, b) => (BC_ROLE_ORDER[a.role] ?? 3) - (BC_ROLE_ORDER[b.role] ?? 3));
  if (!cs.length) return '<span class="bc-pal-none">هنوز رنگی نیست</span>';
  return cs.map(c => `<div class="bc-chip${c.role === 'اصلی' ? ' main' : ''}" style="--c:${c.hx};--ink:${bcInk(c.hx)}">
    <span>${esc(c.name || '')}</span><code>${c.hx}</code></div>`).join('');
}
function bcBoardHTML() {
  const logos = (Array.isArray(bcVal('logo')) ? bcVal('logo') : []).filter(x => x && x.file);
  const colors = bcColors(), main = colors.filter(c => c.role === 'اصلی');
  const big = main.length ? main : colors.slice(0, 3), rest = colors.filter(c => !big.includes(c));
  const fonts = (Array.isArray(bcVal('fonts')) ? bcVal('fonts') : []).filter(x => x && String(x.name || '').trim());
  const logo = logos[0];
  return `<div class="bc-board">
    <div class="bc-board-logo${logo && logo.bg === 'dark' ? ' dark' : ''}">${logo
      ? `<img src="/brand-assets/${encodeURIComponent(logo.file)}" alt="لوگو">` : '<span>لوگو هنوز اضافه نشده</span>'}</div>
    <div class="bc-board-main">
      <div class="bc-board-colors">${big.map(c => `<div class="bc-big-sw" style="--c:${c.hx};--ink:${bcInk(c.hx)}">
        <b>${esc(c.name || '')}</b><code>${c.hx}</code></div>`).join('') || '<span class="bc-pal-none">هنوز رنگی نیست</span>'}</div>
      ${rest.length ? `<div class="bc-board-rest">${rest.map(c => `<i style="--c:${c.hx}" title="${esc((c.name || '') + ' ' + c.hx)}"></i>`).join('')}</div>` : ''}
      ${fonts.map(x => `<div class="bc-board-font" style="font-family:${esc(bcFontFam(x.name))}"><span>${esc(x.name)}</span>${esc(bcSample())}</div>`).join('')}
    </div></div>`;
}
function bcBoardRefresh() { const b = $('#bcBoard'); if (b) b.innerHTML = bcBoardHTML(); }

/* ---------- آمار و فیلتر ---------- */
function bcStats() {
  const all = bcAll(), filled = all.filter(f => bcFilled(f));
  const must = all.filter(f => f.level === 1), mustDone = must.filter(f => bcFilled(f));
  const drafts = all.filter(f => bcSrc(f.id)).length;
  const pct = all.length ? Math.round(filled.length / all.length * 100) : 0;
  const prog = $('#bcProg');
  if (prog) prog.innerHTML = `
    <div class="bc-big"><b>${faNum(filled.length)}</b> از ${faNum(all.length)} سؤال جواب دارد</div>
    <div class="bc-bar"><i style="width:${pct}%"></i></div>
    <div class="bc-meta"><span>ضروری: ${faNum(mustDone.length)} از ${faNum(must.length)}</span>
      ${drafts ? `<span class="warn">نیاز به بررسی: ${faNum(drafts)}</span>` : ''}</div>`;
  BC.schema.forEach(s => {
    const n = s.fields.filter(f => bcFilled(f)).length, t = `${faNum(n)}/${faNum(s.fields.length)}`;
    const at = s.fields.filter(f => bcFilled(f)).map(f => (BC.fields[f.id] || {}).at).filter(Boolean).sort().pop();
    $$(`[data-tcount="${s.id}"]`).forEach(el => { el.textContent = t; el.classList.toggle('full', n === s.fields.length); });
    $$(`[data-count="${s.id}"]`).forEach(el => {
      el.textContent = `${faNum(n)} از ${faNum(s.fields.length)} جواب دارد${at ? ' · آخرین تغییر ' + bcAgo(at) : ''}`;
      el.classList.toggle('full', n === s.fields.length);
    });
  });
}
const bcToday = () => new Date().toLocaleDateString('en-CA');      // YYYY-MM-DD به وقت محلی
function bcAgo(day) {
  const d = Math.round((Date.parse(bcToday()) - Date.parse(day)) / 864e5);
  return d <= 0 ? 'امروز' : d === 1 ? 'دیروز' : `${faNum(d)} روز پیش`;
}

function bcApplyFilter() {
  $$('.bc-f').forEach(el => {
    const f = bcField(el.dataset.f);
    el.hidden = !(BC.filter === 'all'
      || (BC.filter === 'empty' && !bcFilled(f))
      || (BC.filter === 'draft' && bcSrc(f.id))
      || (BC.filter === 'must' && f.level === 1));
  });
  $$('.bc-sec').forEach(s => s.hidden = !s.querySelector('.bc-f:not([hidden])'));
  const none = $('.bc-none'); if (none) none.hidden = !!$('.bc-sec:not([hidden])');
}

/* ---------- ذخیره‌ی خودکار ---------- */
function bcSaveState(st) {
  const el = $('#bcSave'); if (!el) return;
  const at = BC.savedAt ? ` · ${faNum(String(BC.savedAt).slice(11, 16))}` : '';
  el.className = 'bc-save ' + st;
  el.textContent = { idle: 'هنوز چیزی ذخیره نشده', pending: 'تغییر داری — چند لحظه‌ی دیگر ذخیره می‌شود',
    saving: 'در حال ذخیره…', saved: `✓ ذخیره شد${at}`, error: 'ذخیره نشد — دوباره تلاش می‌کنم' }[st];
}
function bcQueue() {
  BC.dirty = true; bcSaveState('pending');
  clearTimeout(BC.timer); BC.timer = setTimeout(bcSaveNow, 700);
}
async function bcSaveNow() {
  clearTimeout(BC.timer);
  if (BC.inflight) { BC.again = true; return; }
  BC.inflight = true; BC.dirty = false; bcSaveState('saving');
  let r;
  try { r = await post('/api/brand', { fields: BC.fields, changed: [...BC.changed] }); } catch { r = { ok: false }; }
  BC.inflight = false;
  if (r.ok) {
    BC.md = r.data.md || BC.md; BC.savedAt = r.data.updated || BC.savedAt;
    bcAdopt(r.data.fields);
    bcSaveState('saved');
  } else {
    BC.dirty = true; bcSaveState('error');
    BC.timer = setTimeout(bcSaveNow, 4000);
  }
  if (BC.again) { BC.again = false; bcSaveNow(); }
}
window.addEventListener('pagehide', () => {
  if (BC.dirty) navigator.sendBeacon('/api/brand',
    new Blob([JSON.stringify({ fields: BC.fields, changed: [...BC.changed] })], { type: 'application/json' }));
});

/* ---------- ویرایش ---------- */
function bcSet(id, v) {
  BC.fields[id] = { v, at: bcToday() };   // هر ویرایشی برچسب «پیش‌نویس از …» را برمی‌دارد
  BC.changed.add(id);
  const box = $(`.bc-f[data-f="${id}"]`);
  if (box) {
    const ok = bcFilled(bcField(id), v);
    box.classList.toggle('bc-filled', ok); box.classList.toggle('bc-empty', !ok); box.classList.remove('bc-isdraft');
    const s = box.querySelector('.bc-src'); if (s) s.remove();
  }
  if (BC_BOARD_FIELDS.includes(id)) bcBoardRefresh();
  bcStats(); bcQueue();
}
function bcRefresh(id, focus) {
  const box = $(`.bc-f[data-f="${id}"]`); if (!box) return;
  box.querySelector('.bc-ctl').innerHTML = bcControl(bcField(id));
  $$('.bc-in', box).forEach(bcGrow);
  if (focus) {
    const el = box.querySelector(`.bc-in[data-i="${focus.i}"]${focus.k ? `[data-k="${focus.k}"]` : ''}`);
    if (el) { el.focus(); const n = focus.start ? 0 : el.value.length; el.setSelectionRange(n, n); }
  }
}
// جواب‌هایی که جای دیگری (تب دیگر، اسکریپت) عوض شده‌اند و این صفحه دستشان نزده، روی صفحه هم تازه می‌شوند
function bcAdopt(server) {
  if (!server || BC.view !== 'form') return;
  for (const [id, e] of Object.entries(server)) {
    if (BC.changed.has(id) || JSON.stringify(BC.fields[id]) === JSON.stringify(e)) continue;
    BC.fields[id] = e;
    const old = $(`.bc-f[data-f="${id}"]`), f = bcField(id);
    if (old && f) { old.outerHTML = bcFieldHTML(f); $$(`.bc-f[data-f="${id}"] .bc-in`).forEach(bcGrow); }
  }
  bcBoardRefresh(); bcStats();
}
const bcArr = id => { const v = bcVal(id); return Array.isArray(v) ? v.map(x => (x && typeof x === 'object') ? { ...x } : x) : []; };

document.addEventListener('input', e => {
  const t = e.target; if (!t.matches) return;
  if (t.matches('.bc-wrap [data-pal]')) {               // رنگ‌انتخاب‌کن: کارت را دوباره نساز تا باز بماند
    const id = t.dataset.pal, i = +t.dataset.i, arr = bcArr(id);
    while (arr.length <= i) arr.push({});
    arr[i] = { ...arr[i], hex: t.value }; bcSet(id, arr);
    const hexIn = $(`.bc-in[data-in="${id}"][data-i="${i}"][data-k="hex"]`); if (hexIn) hexIn.value = t.value;
    return bcPalLive(id, i, t.value);
  }
  if (!t.matches('.bc-wrap [data-in]')) return;
  bcGrow(t);
  const f = bcField(t.dataset.in); if (!f) return;
  if (f.type === 'text' || f.type === 'para') return bcSet(f.id, t.value);
  const i = +t.dataset.i, arr = bcArr(f.id);
  if (f.type === 'list') { while (arr.length <= i) arr.push(''); arr[i] = t.value; }
  else { while (arr.length <= i) arr.push({}); arr[i] = { ...arr[i], [t.dataset.k]: t.value }; }
  bcSet(f.id, arr);
  if (f.type === 'palette') bcPalLive(f.id, i, arr[i].hex);
  if (f.preview === 'font' && t.dataset.k === 'name') {
    const p = t.closest('.bc-card')?.querySelector('.bc-fontprev'); if (p) p.style.fontFamily = bcFontFam(t.value);
  }
});
function bcPalLive(id, i, hex) {                        // دایره، رنگ‌انتخاب‌کن و نوار رنگ‌ها هم‌زمان
  const box = $(`.bc-f[data-f="${id}"]`); if (!box) return;
  const hx = bcHex(hex), card = box.querySelector(`.bc-color[data-i="${i}"]`);
  if (card) {
    card.querySelector('.bc-swatch').style.setProperty('--c', hx || 'transparent');
    if (hx) card.querySelector('[data-pal]').value = hx;
  }
  const strip = box.querySelector('.bc-pal-strip'); if (strip) strip.innerHTML = bcStripHTML(bcVal(id));
}

/* ---------- بارگذاری تصویر ---------- */
async function bcUpload(id, files) {
  const imgs = [...(files || [])].filter(x => /^image\//.test(x.type));
  if (!imgs.length) return toast('فقط فایل تصویری قبول می‌شود');
  const drop = $(`[data-imgdrop="${id}"]`); if (drop) drop.classList.add('busy');
  for (const file of imgs) {
    const data = await new Promise(res => { const fr = new FileReader(); fr.onload = () => res(fr.result); fr.readAsDataURL(file); });
    let r; try { r = await post('/api/brand/asset', { filename: file.name, data }); } catch { r = { ok: false, data: {} }; }
    if (!r.ok) { toast(r.data.error || 'بارگذاری نشد'); continue; }
    const arr = bcArr(id); arr.push({ file: r.data.file, caption: file.name.replace(/\.[^.]+$/, ''), bg: 'light' });
    bcSet(id, arr);
  }
  bcRefresh(id);
}
document.addEventListener('change', e => {
  const t = e.target;
  if (t.matches && t.matches('.bc-wrap [data-imgfile]') && t.files.length) { bcUpload(t.dataset.imgfile, t.files); t.value = ''; }
});
['dragover', 'drop'].forEach(ev => document.addEventListener(ev, e => {
  if (!$('.bc-wrap')) return;
  e.preventDefault();                                   // فایلی که بیرون از کادر رها شود، صفحه را عوض نکند
  const d = e.target.closest && e.target.closest('[data-imgdrop]');
  $$('.bc-drop.over').forEach(x => x !== d && x.classList.remove('over'));
  if (!d) return;
  if (ev === 'dragover') d.classList.add('over');
  else { d.classList.remove('over'); bcUpload(d.dataset.imgdrop, e.dataTransfer.files); }
}));

document.addEventListener('keydown', e => {
  if (!$('.bc-wrap')) return;
  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 's') { e.preventDefault(); return bcSaveNow(); }
  const t = e.target; if (!t.matches || !t.matches('.bc-wrap .bc-in')) return;
  if (e.key === 'Enter' && t.classList.contains('one')) return e.preventDefault();
  if (!t.closest('.bc-li') || e.isComposing) return;
  const id = t.dataset.in, i = +t.dataset.i, arr = bcArr(id);
  if (e.key === 'Enter' && !e.shiftKey) {             // مثل نوت‌برداری: اینتر = مورد تازه
    e.preventDefault();
    const at = t.selectionStart, cur = t.value;
    while (arr.length <= i) arr.push('');
    arr[i] = cur.slice(0, at); arr.splice(i + 1, 0, cur.slice(at));
    bcSet(id, arr); bcRefresh(id, { i: i + 1, start: true });
  } else if (e.key === 'Backspace' && t.selectionStart === 0 && t.selectionEnd === 0 && i > 0) {
    e.preventDefault();                                // بک‌اسپیس اول خط = چسباندن به مورد قبلی
    const prev = String(arr[i - 1] ?? ''), cur = String(arr[i] ?? '');
    arr[i - 1] = prev + cur; arr.splice(i, 1);
    bcSet(id, arr); bcRefresh(id, { i: i - 1 });
    const el = $(`.bc-in[data-in="${id}"][data-i="${i - 1}"]`); if (el) el.setSelectionRange(prev.length, prev.length);
  }
});

document.addEventListener('click', e => {
  const wrap = e.target.closest('.bc-wrap'); if (!wrap) return;
  const q = s => e.target.closest(s);
  let b;
  if ((b = q('[data-bcview]'))) { BC.view = b.dataset.bcview; return bcBody(); }
  if ((b = q('[data-bcflt]'))) { BC.filter = b.dataset.bcflt; BC.view = 'form'; return bcBody(); }
  if ((b = q('[data-bcgo]'))) {
    e.preventDefault();
    if (BC.view !== 'form') { BC.view = 'form'; bcBody(); }
    const sec = $(`#bc-${b.dataset.bcgo}`);
    if (sec && sec.hidden) { BC.filter = 'all'; bcBody(); }
    return $(`#bc-${b.dataset.bcgo}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
  if (q('#bcNext')) return bcNext();
  if (q('#bcCopy')) return navigator.clipboard.writeText(BC.md).then(() => toast('✓ کپی شد'), () => toast('کپی نشد'));
  if ((b = q('[data-bcok]'))) {
    const id = b.dataset.bcok; bcSet(id, bcVal(id)); return toast('✓ تأیید شد');
  }
  if ((b = q('[data-bcadd]'))) {
    const id = b.dataset.bcadd, f = bcField(id), arr = bcArr(id);
    if (f.type === 'group' && !arr.length) arr.push({});   // کارت خالیِ نمایشی را هم نگه دار
    arr.push(f.type === 'list' ? '' : {});
    bcSet(id, arr);
    return bcRefresh(id, { i: arr.length - 1, k: f.type === 'group' ? f.item[0].id : f.type === 'palette' ? 'hex' : null });
  }
  if ((b = q('[data-palrole]'))) {
    const id = b.dataset.palrole, i = +b.dataset.i, arr = bcArr(id);
    arr[i] = { ...arr[i], role: arr[i].role === b.dataset.r ? '' : b.dataset.r };
    bcSet(id, arr); return bcRefresh(id);
  }
  if ((b = q('[data-imgbg]'))) {
    const id = b.dataset.imgbg, i = +b.dataset.i, arr = bcArr(id);
    arr[i] = { ...arr[i], bg: arr[i].bg === 'dark' ? 'light' : 'dark' };
    bcSet(id, arr); return bcRefresh(id);
  }
  if ((b = q('[data-imgdel]'))) {
    if (!confirm('این تصویر حذف شود؟')) return;
    const id = b.dataset.imgdel, arr = bcArr(id), [gone] = arr.splice(+b.dataset.i, 1);
    bcSet(id, arr); bcRefresh(id);
    if (gone && gone.file) post('/api/brand/asset/delete', { file: gone.file }).catch(() => {});
    return;
  }
  if ((b = q('[data-bcdel]'))) {
    const id = b.dataset.bcdel, arr = bcArr(id); arr.splice(+b.dataset.i, 1);
    bcSet(id, arr); return bcRefresh(id);
  }
  if ((b = q('[data-bcchip]'))) {
    const f = bcField(b.dataset.bcchip), c = b.dataset.c;
    if (f.type === 'list') {
      const arr = bcArr(f.id).filter(x => String(x).trim());
      if (arr.includes(c)) return toast('این مورد از قبل هست');
      arr.push(c); bcSet(f.id, arr); return bcRefresh(f.id);
    }
    bcSet(f.id, c); return bcRefresh(f.id);
  }
  if ((b = q('[data-bcscale]'))) {
    const f = bcField(b.dataset.bcscale), v = { ...(bcVal(f.id) || {}) }, n = +b.dataset.n;
    if (v[b.dataset.s] === n) delete v[b.dataset.s]; else v[b.dataset.s] = n;
    bcSet(f.id, v); return bcRefresh(f.id);
  }
});

function bcNext() {
  const all = bcAll();
  const f = all.find(x => x.level === 1 && !bcFilled(x)) || all.find(x => x.level === 2 && !bcFilled(x));
  if (!f) return toast('همه‌ی سؤال‌های ضروری و مهم جواب دارند');
  if (BC.view !== 'form' || BC.filter !== 'all') { BC.view = 'form'; BC.filter = 'all'; bcBody(); }
  const box = $(`.bc-f[data-f="${f.id}"]`); if (!box) return;
  box.scrollIntoView({ behavior: 'smooth', block: 'center' });
  box.classList.add('flash'); setTimeout(() => box.classList.remove('flash'), 1600);
  const el = box.querySelector('.bc-in'); if (el) setTimeout(() => el.focus({ preventScroll: true }), 350);
}

window.addEventListener('resize', () => $$('.bc-wrap .bc-in').forEach(bcGrow));
window.viewBrand = viewBrand;
