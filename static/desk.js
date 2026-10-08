/* Owner desk — talk to the workspace receptionist on the pipeline page.
   Plain script. Posts to the existing receptionist endpoint with desk:true
   so the owner conversation can run discovery, queue and audits. */
(function () {
  var T_ = window.T || function (k, f) { return f; };
  function $(id) { return document.getElementById(id); }
  function esc(value) {
    return String(value === undefined || value === null ? '' : value)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/\"/g, '&quot;').replace(/'/g, '&#39;');
  }
  function linkify(text) {
    return esc(text).replace(/(https?:\/\/[^\s<]+)/g, function (url) {
      return '<a href="' + url + '" target="_blank" rel="noopener">' + url + '</a>';
    }).replace(/\n/g, '<br>');
  }
  function bubble(who, html, thinking) {
    var log = $('desk-log');
    if (!log) return null;
    var div = document.createElement('div');
    div.className = 'desk-msg desk-' + who + (thinking ? ' desk-thinking' : '');
    if (html !== null && html !== undefined) div.innerHTML = html;
    log.appendChild(div);
    log.scrollTop = log.scrollHeight;
    return div;
  }
  function post(message) {
    var options = { method: 'POST', headers: { 'Content-Type': 'application/json' } };
    var meta = document.querySelector('meta[name="csrf-token"]');
    if (meta) options.headers['X-CSRF-Token'] = meta.content;
    options.body = JSON.stringify({ message: message, desk: true, page: '/workspace' });
    return fetch('/api/receptionist/message', options).then(function (response) {
      return response.json().catch(function () { return {}; }).then(function (data) {
        if (!response.ok) throw new Error(data.error || 'request failed');
        return data;
      });
    });
  }
  function send(text) {
    text = (text || '').trim();
    if (!text) return;
    bubble('user', linkify(text));
    var wait = bubble('assistant', esc(T_('ws.desk_wait', 'On it…')), true);
    post(text).then(function (data) {
      wait.classList.remove('desk-thinking');
      wait.innerHTML = linkify(data.reply || '');
      $('desk-log').scrollTop = $('desk-log').scrollHeight;
      if (typeof window.loadOpportunityEngine === 'function' && data.intent === 'desk_find') {
        window.loadOpportunityEngine();
      }
      if (typeof window.refresh === 'function' && (data.intent === 'desk_find' || data.intent === 'desk_diagnose')) {
        try { window.refresh(); } catch (e) {}
      }
    }).catch(function () {
      wait.classList.remove('desk-thinking');
      wait.innerHTML = esc(T_('ws.desk_err', 'Receptionist could not be reached. Try again.'));
    });
  }
  function init() {
    var form = $('desk-form'), input = $('desk-input'), log = $('desk-log');
    if (!form || !input || form.dataset.bound) return;
    form.dataset.bound = '1';
    if (log && !log.dataset.greeted) {
      log.dataset.greeted = '1';
      bubble('assistant', linkify(T_('ws.desk_hello',
        'Start with a city and a trade — “find cafes in Lagos” — or ask what’s next in the pipeline.')));
    }
    form.addEventListener('submit', function (e) {
      e.preventDefault();
      send(input.value);
      input.value = '';
      input.focus();
    });
    var chips = $('desk-chips');
    if (chips) chips.addEventListener('click', function (e) {
      var cmd = e.target && e.target.dataset ? e.target.dataset.cmd : '';
      if (cmd) send(cmd);
    });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
