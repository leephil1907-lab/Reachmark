/* Animated metric counters (CountUp-style): workspace stats count from the shown
   value to the new one. Honest numbers only — it never invents a target.
   Reduced motion or no animation frame: sets the final value instantly. */
(function () {
  'use strict';
  var reduceMotion = window.matchMedia &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  function parseShown(el) {
    var n = parseFloat(String(el.textContent).replace(/[^0-9.\-]/g, ''));
    return isFinite(n) ? n : 0;
  }

  function setCount(id, value) {
    var el = typeof id === 'string' ? document.getElementById(id) : id;
    if (!el) return;
    var target = Number(value);
    if (!isFinite(target)) { el.textContent = String(value); return; }
    var from = parseShown(el);
    if (reduceMotion || !window.requestAnimationFrame || from === target) {
      el.textContent = String(Math.round(target));
      return;
    }
    var start = null;
    var duration = 650;
    function frame(now) {
      if (!start) start = now;
      var t = Math.min(1, (now - start) / duration);
      var eased = 1 - Math.pow(1 - t, 3);
      el.textContent = String(Math.round(from + (target - from) * eased));
      if (t < 1) window.requestAnimationFrame(frame);
    }
    window.requestAnimationFrame(frame);
  }
  window.setCount = setCount;
})();
