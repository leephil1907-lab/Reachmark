/* Magnetic buttons: [data-magnet] CTAs lean a few pixels toward the cursor.
   Touch, keyboard and reduced-motion visitors get the plain button. */
(function () {
  'use strict';
  function init() {
    if (!window.matchMedia) return;
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    if (window.matchMedia('(pointer: coarse)').matches) return;
    document.querySelectorAll('[data-magnet]').forEach(function (el) {
      el.addEventListener('pointermove', function (event) {
        var rect = el.getBoundingClientRect();
        var x = (event.clientX - rect.left - rect.width / 2) / rect.width;
        var y = (event.clientY - rect.top - rect.height / 2) / rect.height;
        el.style.transform = 'translate(' + (x * 8).toFixed(1) + 'px,' + (y * 6).toFixed(1) + 'px)';
      });
      el.addEventListener('pointerleave', function () { el.style.transform = ''; });
    });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
