/* پیش‌نمایش زنده‌ی ترکیب در استودیو (فقط preview.html؛ در رندر نیست).
   HyperFrames در رندر خودش زمان را جلو می‌برد؛ این‌جا ویدیوی سبکِ برش‌خورده ساعت است:
   تایم‌لاین GSAP و دیده‌شدن clipها هر فریم با video.currentTime هم‌گام می‌شوند.
   صفحه‌ی مادر با postMessage فرمان می‌دهد: play / pause / toggle / seek {t}.
   زیرنویس را می‌شود گرفت و بالا-پایین کشید؛ جای تازه با {hf:"capmove", id, y} به صفحه‌ی مادر می‌رود.
   افکت‌های صوتی (window.__sfx = [{t, src, g}]) با WebAudio روی همین ساعت پخش می‌شوند؛ در رندر نیستند، آن‌جا ffmpeg میکسشان می‌کند. */
(function () {
  var root = document.querySelector("[data-composition-id]");
  var H = parseFloat(root.getAttribute("data-height")) || 1920;
  var tl = window.__timelines && window.__timelines[root.getAttribute("data-composition-id")];
  var v = document.querySelector("video");
  var clips = Array.prototype.filter.call(root.children, function (el) { return el.classList.contains("clip"); });
  var spans = clips.map(function (el) {
    var s = parseFloat(el.getAttribute("data-start")) || 0;
    return [el, s, s + (parseFloat(el.getAttribute("data-duration")) || 0)];
  });
  // افکت‌ها: فقط وقتی پخش جلو می‌رود. توقف و جست‌وجو همه را قطع می‌کند و از همان‌جا دوباره برنامه می‌چیند.
  // صداها با OfflineAudioContext از قبل باز می‌شوند (بدون نیاز به کلیک)؛ AudioContext اصلی با اولین پخش ساخته می‌شود.
  var cues = (window.__sfx || []).slice().sort(function (a, b) { return a.t - b.t; });
  var AC = window.AudioContext || window.webkitAudioContext, OAC = window.OfflineAudioContext || window.webkitOfflineAudioContext;
  var actx = null, dec = null, bufs = {}, live = [], nextCue = 0;
  function load(src) {
    if (!bufs[src]) {
      if (!dec) dec = OAC ? new OAC(2, 1, 48000) : (actx || (actx = AC ? new AC() : null));
      bufs[src] = fetch(src).then(function (r) { return r.arrayBuffer(); })
        .then(function (ab) { return new Promise(function (res, rej) { dec.decodeAudioData(ab, res, rej); }); })
        .catch(function () { return null; });
    }
    return bufs[src];
  }
  cues.forEach(function (q) { load(q.src); });
  function sfxStop() { live.forEach(function (s) { try { s.stop(); } catch (_) {} }); live = []; }
  function sfxFrom(t) { sfxStop(); nextCue = 0; while (nextCue < cues.length && cues[nextCue].t < t - 0.05) nextCue++; }
  function sfxTick(t) {
    if (!cues.length || !v || v.paused || v.seeking || !AC) return;
    if (!actx) actx = new AC();
    if (actx.state === "suspended") actx.resume();
    while (nextCue < cues.length && cues[nextCue].t <= t + 0.25) {
      (function (q) {
        var when = actx.currentTime + (q.t - t);
        load(q.src).then(function (b) {
          if (!b || v.paused) return;
          var late = Math.max(0, actx.currentTime - when);
          if (late >= b.duration) return;
          var s = actx.createBufferSource(), g = actx.createGain();
          s.buffer = b; g.gain.value = q.g; s.connect(g); g.connect(actx.destination);
          s.start(Math.max(when, actx.currentTime), late);
          live.push(s);
          s.onended = function () { live = live.filter(function (x) { return x !== s; }); };
        });
      })(cues[nextCue]);
      nextCue++;
    }
  }
  // ویدیوهای روی تصویر (عکس و ویدیوی کاربر): بی‌صدا، هم‌گام با ساعت ویدیوی اصلی
  var ovv = Array.prototype.map.call(document.querySelectorAll("video.ovv"), function (el) {
    var s = parseFloat(el.getAttribute("data-start")) || 0;
    el.muted = true;
    return [el, s, s + (parseFloat(el.getAttribute("data-duration")) || 0), parseFloat(el.getAttribute("data-media-start")) || 0];
  });
  function ovSync(t) {
    for (var i = 0; i < ovv.length; i++) {
      var o = ovv[i], el = o[0];
      if (t >= o[1] && t <= o[2]) {
        var want = o[3] + (t - o[1]);
        if (Math.abs(el.currentTime - want) > 0.25) el.currentTime = want;
        if (v && !v.paused && el.paused) { var pr = el.play(); if (pr && pr.catch) pr.catch(function () {}); }
        if (v && v.paused && !el.paused) el.pause();
      } else if (!el.paused) el.pause();
    }
  }

  window.__sfxState = function () { return { ctx: actx ? actx.state : "none", cues: cues.length, next: nextCue, live: live.length }; };

  var last = -1;
  function frame() {
    var t = v ? v.currentTime : 0;
    if (t !== last) {
      last = t;
      if (tl) tl.seek(t, false);
      for (var i = 0; i < spans.length; i++) {
        var on = t >= spans[i][1] && t <= spans[i][2];
        spans[i][0].style.visibility = on ? "visible" : "hidden";
      }
    }
    sfxTick(t);
    ovSync(t);
    requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
  function post() {
    if (!v || !window.parent) return;
    window.parent.postMessage({ hf: "time", t: v.currentTime, d: v.duration || 0, paused: v.paused }, "*");
  }
  if (v) {
    v.muted = false;
    v.preload = "auto";
    ["timeupdate", "play", "pause", "seeked", "loadedmetadata", "ended"].forEach(function (e) { v.addEventListener(e, post); });
    ["play", "seeked"].forEach(function (e) { v.addEventListener(e, function () { sfxFrom(v.currentTime); }); });
    ["pause", "seeking", "ended"].forEach(function (e) { v.addEventListener(e, sfxStop); });
  }
  window.addEventListener("message", function (e) {
    var m = e.data || {};
    if (!v || !m.cmd) return;
    if (m.cmd === "play") v.play();
    else if (m.cmd === "pause") v.pause();
    else if (m.cmd === "toggle") (v.paused ? v.play() : v.pause());
    else if (m.cmd === "seek") { v.currentTime = Math.max(0, +m.t || 0); }
  });

  // کشیدن زیرنویس (فقط عمودی). مختصات داخل iframe همان پیکسل‌های ترکیب است، حتی وقتی صفحه‌ی مادر کوچکش کرده.
  var st = document.createElement("style");
  st.textContent = ".cap .line{cursor:grab;touch-action:none}.cap.drag .line{cursor:grabbing;outline:3px dashed rgba(135,206,250,.9);outline-offset:8px}";
  document.head.appendChild(st);
  var drag = null, justDragged = false;
  root.addEventListener("pointerdown", function (e) {
    var cap = e.target.closest && e.target.closest(".cap");
    if (!cap) return;
    e.preventDefault();
    if (v) v.pause();
    drag = { cap: cap, y0: e.clientY, top0: parseFloat(cap.style.top) || cap.offsetTop, moved: false };
    cap.classList.add("drag");
    try { root.setPointerCapture(e.pointerId); } catch (_) {}
  });
  root.addEventListener("pointermove", function (e) {
    if (!drag) return;
    var dy = e.clientY - drag.y0;
    if (Math.abs(dy) > 4) drag.moved = true;
    drag.cap.style.top = Math.round(Math.min(H * 0.9, Math.max(H * 0.02, drag.top0 + dy))) + "px";
  });
  function end() {
    if (!drag) return;
    var d = drag; drag = null;
    d.cap.classList.remove("drag");
    if (d.moved) {
      justDragged = true;
      setTimeout(function () { justDragged = false; }, 300);
      window.parent.postMessage({ hf: "capmove", id: d.cap.id, y: (parseFloat(d.cap.style.top) || 0) / H }, "*");
    }
  }
  root.addEventListener("pointerup", end);
  root.addEventListener("pointercancel", end);

  document.addEventListener("click", function (e) {
    if (justDragged || (e.target.closest && e.target.closest(".cap"))) return;
    if (v) (v.paused ? v.play() : v.pause());
  });
})();
