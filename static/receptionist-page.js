/* Reachmark AI receptionist page — stepper, tabs, tone previews. No dependencies.
   Tone previews use the visitor's own speech synthesis: nothing is pre-recorded,
   so the demo can never drift from the printed words. */
(function () {
  'use strict';
  var T_=window.T||function(k,f){return f;};

  /* "Try it live" opens the real chat widget on this page. */
  document.querySelectorAll('[data-open-widget]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var launch = document.getElementById('rm-receptionist-launch');
      var panel = document.getElementById('rm-receptionist');
      if (!launch || !panel) return;
      if (panel.hidden) launch.click();
      panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    });
  });

  /* Footer year. */
  document.querySelectorAll('[data-year]').forEach(function (el) {
    el.textContent = String(new Date().getFullYear());
  });

  /* 4-step conversation demo: click a step, or let it cycle. */
  var stepBtns = Array.prototype.slice.call(document.querySelectorAll('.rx-steps [data-step]'));
  var screens = Array.prototype.slice.call(document.querySelectorAll('.rx-screen'));
  var current = 0, timer = null;
  var reduceMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  function show(n) {
    current = (n + stepBtns.length) % stepBtns.length;
    stepBtns.forEach(function (b, i) { b.setAttribute('aria-selected', i === current ? 'true' : 'false'); });
    screens.forEach(function (s, i) { s.hidden = i !== current; });
  }
  function cycle() {
    stop();
    if (!reduceMotion && stepBtns.length > 1) timer = setInterval(function () { show(current + 1); }, 5200);
  }
  function stop() { if (timer) { clearInterval(timer); timer = null; } }
  if (stepBtns.length && screens.length) {
    stepBtns.forEach(function (b) {
      b.addEventListener('click', function () { show(parseInt(b.getAttribute('data-step'), 10) || 0); cycle(); });
    });
    var demo = document.getElementById('demo');
    if (demo) {
      demo.addEventListener('pointerenter', stop);
      demo.addEventListener('pointerleave', cycle);
      demo.addEventListener('focusin', stop);
      demo.addEventListener('focusout', cycle);
    }
    cycle();
  }

  /* Industry tabs. */
  var tabBtns = Array.prototype.slice.call(document.querySelectorAll('.rx-tabs [data-tab]'));
  var panels = Array.prototype.slice.call(document.querySelectorAll('.rx-tabpanels [data-panel]'));
  tabBtns.forEach(function (b) {
    b.addEventListener('click', function () {
      var n = b.getAttribute('data-tab');
      tabBtns.forEach(function (x) { x.setAttribute('aria-selected', x === b ? 'true' : 'false'); });
      panels.forEach(function (p) { p.hidden = p.getAttribute('data-panel') !== n; });
    });
  });

  /* Tone previews — spoken live by the browser, or an honest note when it cannot. */
  var VOICES = { warm: { rate: 1.02, pitch: 1.1 }, brief: { rate: 1.05, pitch: 0.95 }, patient: { rate: 0.88, pitch: 1.0 } };
  var note = document.querySelector('[data-tts-note]');
  var ttsOK = 'speechSynthesis' in window && 'SpeechSynthesisUtterance' in window;
  if (!ttsOK && note) note.hidden = false;
  document.querySelectorAll('[data-say]').forEach(function (btn) {
    if (!ttsOK) { btn.disabled = true; return; }
    btn.addEventListener('click', function () {
      var card = btn.closest('[data-tone]');
      var quote = card ? card.querySelector('blockquote') : null;
      if (!quote) return;
      try {
        window.speechSynthesis.cancel();
        var say = new SpeechSynthesisUtterance(quote.textContent.trim());
        var tune = VOICES[card.getAttribute('data-tone')] || { rate: 1, pitch: 1 };
        say.rate = tune.rate; say.pitch = tune.pitch;
        btn.disabled = true;
        say.onend = say.onerror = function () { btn.disabled = false; };
        window.speechSynthesis.speak(say);
        setTimeout(function () { btn.disabled = false; }, 15000);
      } catch (e) {
        btn.disabled = false;
        if (note) note.hidden = false;
      }
    });
  });
  /* Live front-desk heartbeat: counts come from the same file the chat answers from. */
  (function () {
    var pill = document.querySelector('[data-frontdesk-status]');
    if (!pill || !('fetch' in window)) return;
    fetch('/api/frontdesk/status').then(function (r) { return r.json(); }).then(function (s) {
      if (!s || !s.ok) return;
      pill.textContent = T_('rx.js_live','Front desk live — {t} topics, {q} answers (brain {b}).').replace('{t}',s.topics).replace('{q}',s.questions).replace('{b}',s.brain);
    }).catch(function () {
      pill.textContent = T_('rx.js_unavail','Front desk status: unavailable right now.');
    });
  })();
})();
