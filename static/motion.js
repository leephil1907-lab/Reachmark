/* Reachmark motion runtime — dependency-free React Bits / Framer Motion kit.
   Menu, scroll reveals, split-text heroes, page veil, pipeline cycler,
   declarative count-ups. Everything degrades to the final state. */
(function () {
  'use strict';
  var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  function ready(fn) {
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', fn);
    else fn();
  }
  ready(function () {
    /* Mobile menu. */
    var btn = document.getElementById('pub-menu-btn'), head = document.getElementById('pub-head');
    if (btn && head) {
      btn.addEventListener('click', function () {
        var open = head.classList.toggle('open');
        btn.setAttribute('aria-expanded', open ? 'true' : 'false');
      });
      document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && head.classList.contains('open')) {
          head.classList.remove('open'); btn.setAttribute('aria-expanded', 'false'); btn.focus();
        }
      });
    }
    /* Scroll reveals (+ legacy premium hooks, harmless if already handled). */
    var revealEls = document.querySelectorAll('[data-motion], .premium-reveal:not(.in), .premium-stagger:not(.in)');
    if (!reduce && 'IntersectionObserver' in window && revealEls.length) {
      revealEls.forEach(function (el) {
        if (el.hasAttribute('data-motion')) el.classList.add('rm-pre');
      });
      var io = new IntersectionObserver(function (entries) {
        entries.forEach(function (en) {
          if (!en.isIntersecting) return;
          var el = en.target;
          var delay = parseInt(el.getAttribute('data-delay') || '0', 10);
          if (el.hasAttribute('data-motion')) {
            el.style.transitionDelay = (delay || 0) + 'ms';
            requestAnimationFrame(function () { el.classList.add('rm-in'); });
          } else { el.classList.add('in'); }
          io.unobserve(el);
        });
      }, { threshold: 0.12, rootMargin: '0px 0px -5% 0px' });
      revealEls.forEach(function (el) { io.observe(el); });
    }
    /* Split-text heroes: wrap words, blur-rise them in sequence. */
    document.querySelectorAll('[data-split]').forEach(function (el) {
      if (reduce || el.dataset.splitDone) return;
      el.dataset.splitDone = '1';
      var words = [];
      (function walk(node) {
        Array.prototype.slice.call(node.childNodes).forEach(function (child) {
          if (child.nodeType === 3) {
            var frag = document.createDocumentFragment();
            child.textContent.split(/(\s+)/).forEach(function (part) {
              if (!part) return;
              if (/^\s+$/.test(part)) { frag.appendChild(document.createTextNode(' ')); return; }
              var w = document.createElement('span'); w.className = 'w';
              var inner = document.createElement('span'); inner.textContent = part;
              w.appendChild(inner); frag.appendChild(w); words.push(inner);
            });
            node.replaceChild(frag, child);
          } else if (child.nodeType === 1) { walk(child); }
        });
      })(el);
      words.forEach(function (w, i) { w.style.transitionDelay = (i * 70) + 'ms'; });
      el.classList.add('rm-pre-split');
      requestAnimationFrame(function () {
        requestAnimationFrame(function () { el.classList.add('rm-split-in'); });
      });
    });
    /* Declarative count-ups: <b data-count="10">0</b>. Final value only. */
    document.querySelectorAll('[data-count]').forEach(function (el) {
      var target = parseFloat(el.getAttribute('data-count'));
      if (!isFinite(target)) return;
      if (reduce || !window.requestAnimationFrame || !('IntersectionObserver' in window)) {
        el.textContent = String(target); return;
      }
      var done = false;
      var cio = new IntersectionObserver(function (entries) {
        if (!entries[0].isIntersecting || done) return;
        done = true; cio.disconnect();
        var t0 = null, dur = 1100;
        function tick(now) {
          if (!t0) t0 = now;
          var p = Math.min(1, (now - t0) / dur), e = 1 - Math.pow(1 - p, 3);
          el.textContent = String(Math.round(target * e));
          if (p < 1) requestAnimationFrame(tick);
        }
        requestAnimationFrame(tick);
      }, { threshold: 0.4 });
      cio.observe(el);
    });
    /* Pipeline cycler: one live step at a time, dots to jump. */
    document.querySelectorAll('[data-pipeline]').forEach(function (pipe) {
      var steps = Array.prototype.slice.call(pipe.querySelectorAll('ol > li'));
      var dots = Array.prototype.slice.call(pipe.querySelectorAll('.pipeline-dots button'));
      if (!steps.length) return;
      var ix = 0, timer = null;
      function show(n) {
        ix = (n + steps.length) % steps.length;
        steps.forEach(function (s, i) { s.classList.toggle('on', i === ix); });
        dots.forEach(function (d, i) {
          d.classList.toggle('on', i === ix);
          d.setAttribute('aria-current', i === ix ? 'true' : 'false');
        });
      }
      dots.forEach(function (d, i) {
        d.addEventListener('click', function () { show(i); restart(); });
      });
      function restart() {
        if (timer) clearInterval(timer);
        if (!reduce) timer = setInterval(function () { show(ix + 1); }, 2600);
      }
      pipe.addEventListener('pointerenter', function () { if (timer) clearInterval(timer); timer = null; });
      pipe.addEventListener('pointerleave', restart);
      pipe.addEventListener('focusin', function () { if (timer) clearInterval(timer); timer = null; });
      pipe.addEventListener('focusout', restart);
      show(0); restart();
      if (!reduce) pipe.classList.add('run');
    });
    /* Page veil — Framer-style exit crossfade on plain internal clicks. */
    var veil = document.querySelector('.page-veil');
    window.addEventListener('pageshow', function () { if (veil) veil.classList.remove('on'); });
    if (veil && !reduce) {
      document.addEventListener('click', function (e) {
        if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
        var a = e.target && e.target.closest ? e.target.closest('a[href]') : null;
        if (!a || a.target === '_blank' || a.hasAttribute('download') || a.dataset.noVeil !== undefined) return;
        var href = a.getAttribute('href') || '';
        if (!href || href.charAt(0) === '#' || href.indexOf(':') !== -1) return;
        var url;
        try { url = new URL(href, location.href); } catch (err) { return; }
        if (url.origin !== location.origin) return;
        if (url.pathname === location.pathname && url.search === location.search) return;
        e.preventDefault();
        veil.classList.add('on');
        setTimeout(function () { location.href = url.href; }, 170);
      });
    }
  });
})();
