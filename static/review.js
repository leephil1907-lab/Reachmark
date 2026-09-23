/* Review link page — the three-answer question.
   One POST to /api/r/<token>/respond. No analytics, no third parties, no cookies. */
(function () {
  var T_ = window.T || function (k, f) { return f; };
  var body = document.body;
  var token = body.getAttribute('data-token');
  var form = document.getElementById('answer-form');
  var done = document.getElementById('answer-done');
  var doneCopy = document.getElementById('done-copy');
  var label = document.getElementById('chosen-label');
  var button = document.getElementById('send-answer');
  var choices = Array.prototype.slice.call(document.querySelectorAll('.choice'));
  var chosen = '';
  var LABELS = {
    want: T_('rv.want','Yes — build my website'),
    later: T_('rv.later','Not right now'),
    have: T_('rv.have','I already have a website')
  };
  var CONFIRM = {
    want: T_('rv.c_want','The studio owner has your answer and will come back with scope and a fixed price. Nothing is charged until you approve it.'),
    later: T_('rv.c_later','Your answer is saved and nothing else will be sent. The concept stays on file in case it becomes a priority.'),
    have: T_('rv.c_have','Understood — the studio will not pitch a rebuild. If you add a note about what you would improve, they will read it.')
  };

  choices.forEach(function (choice) {
    choice.addEventListener('click', function () {
      chosen = choice.getAttribute('data-choice');
      choices.forEach(function (other) { other.classList.toggle('selected', other === choice); });
      label.textContent = T_('rv.your','Your answer: {l}').replace('{l}', LABELS[chosen]);
      form.hidden = false;
      form.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    });
  });

  if (!form) return;
  form.addEventListener('submit', function (event) {
    event.preventDefault();
    if (!chosen) { label.textContent = T_('rv.pick','Pick one of the three answers first.'); return; }
    var payload = {
      choice: chosen,
      name: (form.elements.name.value || '').trim(),
      email: (form.elements.email.value || '').trim(),
      note: (form.elements.note.value || '').trim(),
      rating: (form.querySelector('input[name="rating"]:checked') || {}).value || '',
      company_url: (form.elements.company_url.value || '').trim()
    };
    button.disabled = true;
    button.textContent = T_('rv.sending','Sending…');
    fetch('/api/r/' + encodeURIComponent(token) + '/respond', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    }).then(function (response) {
      return response.json().catch(function () { return {}; }).then(function (data) { return { ok: response.ok, data: data }; });
    }).then(function (result) {
      if (!result.ok) {
        button.disabled = false;
        button.textContent = T_('rv.send','Send my answer ↗');
        label.textContent = (result.data && result.data.error) || T_('rv.err','Something went wrong — please try again.');
        return;
      }
      form.hidden = true;
      done.hidden = false;
      doneCopy.textContent = CONFIRM[chosen] || T_('rv.sent','Your answer has been sent.');
      done.scrollIntoView({ block: 'center', behavior: 'smooth' });
    }).catch(function () {
      button.disabled = false;
      button.textContent = T_('rv.send','Send my answer ↗');
      label.textContent = T_('rv.drop','The connection dropped — please try again.');
    });
  });

  // Keep the last-view timestamp honest for long reads.
  document.addEventListener('visibilitychange', function () {
    if (document.visibilityState === 'visible' && token) {
      fetch('/api/r/' + encodeURIComponent(token) + '/seen', { method: 'POST' }).catch(function () {});
    }
  });
})();
