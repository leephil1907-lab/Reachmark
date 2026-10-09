/* Receptionist page: open the live desk. Voice lives in the chat widget (speechSynthesis). */
(function () {
  'use strict';
  var status = document.querySelector('[data-frontdesk-status]');
  if (status && typeof fetch === 'function') {
    fetch('/api/frontdesk/status', { headers: { 'Accept': 'application/json' } })
      .then(function (response) {
        if (!response.ok) throw new Error('status unavailable');
        return response.json();
      })
      .then(function (data) {
        if (!data || !data.ok || data.receptionist !== 'live') throw new Error('front desk not live');
        var topics = Number(data.topics);
        status.textContent = 'Online · verified knowledge loaded' + (Number.isFinite(topics) ? ' · ' + topics + ' topics' : '');
        status.dataset.status = 'online';
      })
      .catch(function () {
        status.textContent = 'Live status unavailable — you can still ask a question.';
        status.dataset.status = 'unknown';
      });
  }

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
