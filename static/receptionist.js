/* Reachmark AI receptionist — talks to /api/receptionist/message. Voice lives in this widget. */
(function () {
  var T_ = window.T || function (k, f) { return f; };
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
  var speakBtn = document.getElementById('rm-speak');
  var micBtn = document.getElementById('rm-mic');
  var KEY = 'reachmark.receptionist.thread';
  var voiceOn = false;
  var rec = null;

  function thread() {
    try { return localStorage.getItem(KEY) || ''; } catch (e) { return ''; }
  }
  function remember(id) { try { localStorage.setItem(KEY, id); } catch (e) {} }

  function lastAssistant() {
    var nodes = log.querySelectorAll('.rm-msg.assistant:not(.thinking):not(.note):not(.error)');
    return nodes.length ? nodes[nodes.length - 1].textContent : '';
  }

  function speak(text) {
    if (!text || !('speechSynthesis' in window)) return;
    try {
      window.speechSynthesis.cancel();
      var u = new SpeechSynthesisUtterance(text);
      u.rate = 1;
      window.speechSynthesis.speak(u);
    } catch (e) {}
  }

  function bubble(text, who) {
    var el = document.createElement('div');
    el.className = 'rm-msg ' + who;
    el.textContent = text;
    log.appendChild(el);
    log.scrollTop = log.scrollHeight;
    if (who === 'assistant' && voiceOn) speak(text);
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
    if ('speechSynthesis' in window) try { window.speechSynthesis.cancel(); } catch (e) {}
    if (rec) try { rec.stop(); } catch (e) {}
  }
  launch.addEventListener('click', function () { panel.hidden ? open() : shut(); });
  close.addEventListener('click', shut);
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && !panel.hidden) shut(); });

  if (speakBtn) {
    if (!('speechSynthesis' in window)) {
      speakBtn.disabled = true;
      speakBtn.title = T_('rx.w_speak_na', 'Voice is not available in this browser.');
    } else {
      speakBtn.addEventListener('click', function () {
        voiceOn = !voiceOn;
        speakBtn.setAttribute('aria-pressed', voiceOn ? 'true' : 'false');
        if (voiceOn) speak(lastAssistant());
        else try { window.speechSynthesis.cancel(); } catch (e) {}
      });
    }
  }

  var SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (micBtn) {
    if (!SR) {
      micBtn.hidden = true;
    } else {
      micBtn.addEventListener('click', function () {
        if (rec) {
          try { rec.stop(); } catch (e) {}
          rec = null;
          micBtn.setAttribute('aria-pressed', 'false');
          return;
        }
        rec = new SR();
        rec.lang = (document.documentElement.lang || 'en');
        rec.interimResults = false;
        rec.onresult = function (ev) {
          var said = ev.results && ev.results[0] && ev.results[0][0] ? ev.results[0][0].transcript : '';
          if (said) {
            input.value = (input.value ? input.value + ' ' : '') + said;
            input.focus();
          }
        };
        rec.onend = function () {
          rec = null;
          micBtn.setAttribute('aria-pressed', 'false');
        };
        rec.onerror = function () {
          rec = null;
          micBtn.setAttribute('aria-pressed', 'false');
        };
        micBtn.setAttribute('aria-pressed', 'true');
        try { rec.start(); } catch (e) { rec = null; micBtn.setAttribute('aria-pressed', 'false'); }
      });
    }
  }

  form.addEventListener('submit', function (event) {
    event.preventDefault();
    var message = (input.value || '').trim();
    if (message.length < 2) return;
    bubble(message, 'visitor');
    input.value = '';
    send.disabled = true;
    send.textContent = '…';
    var thinking = bubble(T_('rx.js_thinking', 'One moment.'), 'assistant');
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
        bubble(data.error || T_('rx.js_fail', 'Something went wrong. Please use the enquiry form.'), 'assistant error');
        return;
      }
      if (data.thread) remember(data.thread);
      bubble(data.reply, 'assistant');
      if ((data.actions || []).indexOf('handoff') !== -1 || (data.actions || []).indexOf('enquiry_created') !== -1) {
        nameField.hidden = false;
        emailField.hidden = false;
        if (!emailField.dataset.asked) {
          bubble(T_('rx.js_ask_contact', 'If you add a name and e-mail here, the studio owner replies to you personally.'), 'assistant note');
          emailField.dataset.asked = '1';
        }
      }
    }).catch(function () {
      thinking.remove();
      bubble(T_('rx.js_drop', 'The connection dropped. Please try again, or use /enquire.'), 'assistant error');
    }).then(function () {
      send.disabled = false;
      send.textContent = T_('rx.w_send', 'Send');
      input.focus();
    });
  });
})();
