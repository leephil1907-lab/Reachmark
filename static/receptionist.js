/* Reachmark AI receptionist — small, dependency-free chat widget.
   Talks to /api/receptionist/message. No external requests, no tracking, no storage
   beyond a per-visitor thread id in localStorage so a reload keeps the conversation. */
(function () {
  var launch = document.getElementById('rm-receptionist-launch');
  var panel = document.getElementById('rm-receptionist');
  if (!launch || !panel) return;
  var log = document.getElementById('rm-log');
  var form = document.getElementById('rm-form');
  var input = document.getElementById('rm-input');
  var nameField = document.getElementById('rm-name');
  var emailField = document.getElementById('rm-email');
  var send = document.getElementById('rm-send');
  var close = document.getElementById('rm-close');
  var KEY = 'reachmark.receptionist.thread';

  function thread() {
    try { return localStorage.getItem(KEY) || ''; } catch (e) { return ''; }
  }
  function remember(id) { try { localStorage.setItem(KEY, id); } catch (e) {} }

  function bubble(text, who) {
    var el = document.createElement('div');
    el.className = 'rm-msg ' + who;
    el.textContent = text;
    log.appendChild(el);
    log.scrollTop = log.scrollHeight;
    return el;
  }

  function open() {
    panel.hidden = false;
    launch.setAttribute('aria-expanded', 'true');
    setTimeout(function () { input.focus(); }, 60);
  }
  function shut() {
    panel.hidden = true;
    launch.setAttribute('aria-expanded', 'false');
  }
  launch.addEventListener('click', function () { panel.hidden ? open() : shut(); });
  close.addEventListener('click', shut);
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && !panel.hidden) shut(); });

  form.addEventListener('submit', function (event) {
    event.preventDefault();
    var message = (input.value || '').trim();
    if (message.length < 2) return;
    bubble(message, 'visitor');
    input.value = '';
    send.disabled = true;
    send.textContent = '…';
    var thinking = bubble('One moment — checking the published facts.', 'assistant');
    thinking.classList.add('thinking');

    fetch('/api/receptionist/message', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message: message,
        thread: thread(),
        name: (nameField.value || '').trim(),
        email: (emailField.value || '').trim(),
        page: location.pathname,
        company_url: ''
      })
    }).then(function (response) {
      return response.json().catch(function () { return {}; }).then(function (data) {
        return { ok: response.ok, data: data };
      });
    }).then(function (result) {
      thinking.remove();
      var data = result.data || {};
      if (!result.ok) {
        bubble(data.error || 'Something went wrong on the way. Please use the enquiry form at /enquire.', 'assistant error');
        return;
      }
      if (data.thread) remember(data.thread);
      bubble(data.reply, 'assistant');
      if ((data.actions || []).indexOf('handoff') !== -1 || (data.actions || []).indexOf('enquiry_created') !== -1) {
        nameField.hidden = false;
        emailField.hidden = false;
        if (!emailField.dataset.asked) {
          bubble('If you add a name and e-mail here, the studio owner replies to you personally.', 'assistant note');
          emailField.dataset.asked = '1';
        }
      }
      if ((data.actions || []).indexOf('offer_review_link') !== -1) {
        bubble('Tip: say “preview my business” with the business name and the studio will prepare a private review link.', 'assistant note');
      }
    }).catch(function () {
      thinking.remove();
      bubble('The connection dropped. Please try again, or use /enquire.', 'assistant error');
    }).then(function () {
      send.disabled = false;
      send.textContent = 'Send';
      input.focus();
    });
  });
})();
