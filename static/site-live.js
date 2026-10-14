/* Reachmark live layer — icon draw-in + the "Signal" hero audit loop.
   Progressive: without JS every icon and panel row is simply visible. */
(function () {
  'use strict';
  var root = document.documentElement;
  var reduce = window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* 1. Icons draw themselves in when they scroll into view. */
  function initDraw() {
    var icons = [].slice.call(document.querySelectorAll('.ic.draw'));
    if (!icons.length || reduce || !('IntersectionObserver' in window)) return;
    root.classList.add('rm-live');
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (!e.isIntersecting) return;
        var el = e.target;
        setTimeout(function () { el.classList.add('is-drawn'); }, (+el.getAttribute('data-delay') || 0));
        io.unobserve(el);
      });
    }, { rootMargin: '0px 0px -8% 0px', threshold: 0.2 });
    icons.forEach(function (el, i) { el.setAttribute('data-delay', String((i % 4) * 90)); io.observe(el); });
    /* Safety net: never leave an icon undrawn. */
    setTimeout(function () { icons.forEach(function (el) { el.classList.add('is-drawn'); }); }, 6000);
  }

  /* 2. Hero: type a URL, scan, reveal findings, count the score, hand over the report. */
  function initHero() {
    var panel = document.querySelector('[data-hx]');
    if (!panel) return;
    var demos;
    try { demos = JSON.parse(panel.getAttribute('data-demos') || '[]'); } catch (e) { demos = []; }
    if (!demos.length) return;
    var $ = function (s) { return panel.querySelector(s); };
    var url = $('[data-hx-url]'), name = $('[data-hx-name]'), cat = $('[data-hx-cat]'), av = $('[data-hx-av]');
    var score = $('[data-hx-score]'), ring = $('[data-hx-ring]'), bar = $('[data-hx-bar]'), state = $('[data-hx-state]');
    var speed = $('[data-hx-speed]'), out = $('[data-hx-out]');
    var rows = [].slice.call(panel.querySelectorAll('[data-hx-row]'));
    if (reduce) return; /* static, fully rendered first demo */

    var timers = [], idx = 0, visible = true, running = false;
    function later(fn, ms) { timers.push(setTimeout(fn, ms)); }
    function clear() { timers.forEach(clearTimeout); timers = []; }
    function setScore(v) { if (score) score.textContent = String(v); if (ring) ring.style.strokeDashoffset = String(100 - v); }

    function run() {
      clear(); running = true;
      var d = demos[idx % demos.length];
      panel.classList.add('is-running', 'is-swapping');
      rows.forEach(function (r) { r.classList.remove('in'); });
      if (out) out.classList.remove('in');
      setScore(0); if (score) score.textContent = '–';
      if (bar) { bar.style.transition = 'none'; bar.style.width = '0%'; }
      if (state) state.textContent = state.getAttribute('data-scan') || '';
      later(function () {
        if (name) name.textContent = d.name;
        if (cat) cat.textContent = d.cat;
        if (av) av.textContent = (d.name || '?').charAt(0);
        if (speed) speed.textContent = d.speed || '';
        panel.classList.remove('is-swapping');
      }, 260);
      /* type the address */
      var text = d.url || '', i = 0;
      if (url) url.textContent = '';
      (function type() {
        if (!url) return;
        url.textContent = text.slice(0, i);
        if (i++ < text.length) later(type, 34 + Math.random() * 30);
        else scan();
      })();
      function scan() {
        panel.classList.add('is-scanning');
        if (bar) { void bar.offsetWidth; bar.style.transition = 'width 1.7s cubic-bezier(.4,0,.2,1)'; bar.style.width = '100%'; }
        rows.forEach(function (r, k) { later(function () { r.classList.add('in'); }, 380 + k * 360); });
        later(function () {
          panel.classList.remove('is-scanning');
          if (state) state.textContent = state.getAttribute('data-done') || '';
          var target = +d.score || 0, start = performance.now(), dur = 1100;
          (function tick(now) {
            var p = Math.min(1, (now - start) / dur), e = 1 - Math.pow(1 - p, 3);
            setScore(Math.round(target * e));
            if (p < 1) timers.push(requestAnimationFrame(tick));
          })(start);
          later(function () { if (out) out.classList.add('in'); }, 650);
          later(function () { idx++; if (visible && !document.hidden) run(); else running = false; }, 4600);
        }, 1900);
      }
    }
    if ('IntersectionObserver' in window) {
      new IntersectionObserver(function (es) {
        visible = es[0].isIntersecting;
        if (visible && !running && !document.hidden) run();
      }, { threshold: 0.15 }).observe(panel);
    } else { run(); }
    document.addEventListener('visibilitychange', function () {
      if (!document.hidden && visible && !running) run();
    });
  }

  function boot() { initDraw(); initHero(); }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
})();
