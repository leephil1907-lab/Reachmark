/* Receptionist page: open the live desk. Voice lives in the chat widget (speechSynthesis). */
(function () {
  'use strict';
  document.querySelectorAll('[data-open-widget]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var launch = document.getElementById('rm-receptionist-launch');
      var panel = document.getElementById('rm-receptionist');
      if (!launch || !panel) return;
      if (panel.hidden) launch.click();
      panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    });
  });
})();
