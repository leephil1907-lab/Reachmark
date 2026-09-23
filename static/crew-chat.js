/* Chief chat — talk to the crew chief from the AI-crew page.
   Plain script, no dependencies. All output is escaped; URLs linkify. */
(function () {
  var T_ = window.T || function (k, f) { return f; };
  function $(id) { return document.getElementById(id); }
  function esc(value) {
    return String(value === undefined || value === null ? '' : value)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }
  function linkify(text) {
    return esc(text).replace(/(https?:\/\/[^\s<]+)/g, function (url) {
      return '<a href="' + url + '" target="_blank" rel="noopener">' + url + '</a>';
    });
  }
  function bubble(who, html, thinking) {
    var log = $('chief-log');
    if (!log) return null;
    var div = document.createElement('div');
    div.className = 'chief-msg chief-' + who + (thinking ? ' chief-thinking' : '');
    if (html !== null && html !== undefined) div.innerHTML = html;
    log.appendChild(div);
    log.scrollTop = log.scrollHeight;
    return div;
  }
  function post(message) {
    var options = { method: 'POST', headers: { 'Content-Type': 'application/json' } };
    var meta = document.querySelector('meta[name="csrf-token"]');
    if (meta) options.headers['X-CSRF-Token'] = meta.content;
    options.body = JSON.stringify({ message: message });
    return fetch('/api/crew/chat', options).then(function (response) {
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
    var wait = bubble('chief', esc(T_('ws.cc_thinking', 'Chief is on it…')), true);
    post(text).then(function (data) {
      wait.classList.remove('chief-thinking');
      wait.innerHTML = linkify(data.reply || '');
      $('chief-log').scrollTop = $('chief-log').scrollHeight;
    }).catch(function (err) {
      wait.classList.remove('chief-thinking');
      wait.innerHTML = esc(T_('ws.cc_err', 'Chief could not be reached. Try again.'));
    });
  }
  function init() {
    var form = $('chief-form'), input = $('chief-input');
    if (!form || !input || form.dataset.bound) return;
    form.dataset.bound = '1';
    form.addEventListener('submit', function (e) {
      e.preventDefault();
      send(input.value);
      input.value = '';
      input.focus();
    });
    var chips = $('chief-chips');
    if (chips) chips.addEventListener('click', function (e) {
      var cmd = e.target && e.target.dataset ? e.target.dataset.cmd : '';
      if (cmd) send(cmd);
    });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
