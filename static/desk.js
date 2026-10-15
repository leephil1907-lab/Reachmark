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
  var busy = false;
  var THREAD_KEY = 'reachmark.owner-desk.thread';
  function thread() { try { return localStorage.getItem(THREAD_KEY) || ''; } catch (e) { return ''; } }
  function rememberThread(token) { try { if (token) localStorage.setItem(THREAD_KEY, token); } catch (e) {} }
  function post(message) {
    var options = { method: 'POST', headers: { 'Content-Type': 'application/json' } };
    var controller = typeof AbortController === 'function' ? new AbortController() : null;
    var timer = controller ? setTimeout(function () { controller.abort(); }, 30000) : null;
    if (controller) options.signal = controller.signal;
    var meta = document.querySelector('meta[name="csrf-token"]');
    if (meta) options.headers['X-CSRF-Token'] = meta.content;
    options.body = JSON.stringify({ message: message, desk: true, page: '/workspace', thread: thread() });
    return fetch('/api/receptionist/message', options).then(function (response) {
      return response.json().catch(function () { return {}; }).then(function (data) {
        if (!response.ok) throw new Error(data.error || 'request failed (' + response.status + ')');
        return data;
      });
    }).finally(function () { if (timer) clearTimeout(timer); });
  }
  function restoreThread() {
    var token = thread();
    if (!token) return Promise.resolve(false);
    return fetch('/api/receptionist/desk/thread?token=' + encodeURIComponent(token), {
      credentials: 'same-origin', headers: { 'Accept': 'application/json' }
    }).then(function (response) {
      return response.json().catch(function () { return {}; }).then(function (data) {
        if (!response.ok) throw new Error(data.error || 'Conversation history is unavailable.');
        return data;
      });
    }).then(function (data) {
      var rows = Array.isArray(data.transcript) ? data.transcript : [];
      if (!rows.length) return false;
      rows.forEach(function (row) {
        var who = row.role === 'visitor' ? 'user' : 'assistant';
        bubble(who, linkify(row.text || ''));
      });
      return true;
    }).catch(function () { return false; });
  }

  function send(text) {
    text = (text || '').trim();
    if (!text || busy) return;
    busy = true;
    var form = $('desk-form');
    var input = $('desk-input');
    var submit = form && form.querySelector('button[type="submit"]');
    if (submit) { submit.disabled = true; submit.textContent = 'Working…'; }
    if (form) form.setAttribute('aria-busy', 'true');
    bubble('user', linkify(text));
    var wait = bubble('assistant', esc(T_('ws.desk_wait', 'On it…')), true);
    post(text).then(function (data) {
      rememberThread(data.thread);
      wait.classList.remove('desk-thinking');
      wait.innerHTML = linkify(data.reply || 'I completed the request, but no reply text was returned.');
      var log = $('desk-log');
      if (log) log.scrollTop = log.scrollHeight;
      if (typeof window.loadOpportunityEngine === 'function' && data.intent === 'desk_find') {
        window.loadOpportunityEngine();
      }
      if (typeof window.refresh === 'function' && (data.intent === 'desk_find' || data.intent === 'desk_diagnose')) {
        try { window.refresh(); } catch (e) {}
      }
      if (typeof window.loadReachmarkActionCenter === 'function') {
        try { window.loadReachmarkActionCenter(false); } catch (e) {}
      }
    }).catch(function (err) {
      wait.classList.remove('desk-thinking');
      wait.classList.add('desk-error');
      wait.textContent = err && err.name === 'AbortError'
        ? 'That took longer than expected. Your request may not have finished. Please try again.'
        : ((err && err.message) || T_('ws.desk_err', 'Receptionist could not be reached. Try again.'));
      if (input && !input.value) input.value = text;
      if (input) input.focus();
    }).finally(function () {
      busy = false;
      if (submit) { submit.disabled = false; submit.textContent = T_('ws.desk_send', 'Send'); }
      if (form) form.removeAttribute('aria-busy');
    });
  }
  function init() {
    var form = $('desk-form'), input = $('desk-input'), log = $('desk-log');
    if (!form || !input || form.dataset.bound) return;
    form.dataset.bound = '1';
    if (log && !log.dataset.greeted) {
      log.dataset.greeted = '1';
      var greeting = T_('ws.desk_hello',
        'Start with a city and a trade — “find cafes in Lagos” — or ask what’s next in the pipeline.');
      if (thread()) {
        restoreThread().then(function (restored) {
          if (!restored) bubble('assistant', linkify(greeting));
        });
      } else {
        bubble('assistant', linkify(greeting));
      }
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
