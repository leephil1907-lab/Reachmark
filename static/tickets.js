/* Signed-in client tickets + owner list. No extra agent. */
(function () {
  var T_ = window.T || function (k, f) { return f; };
  function csrf() {
    var m = document.querySelector('meta[name="csrf-token"]');
    return (m && m.content) || '';
  }
  function esc(s) {
    return String(s || '').replace(/[&<>"']/g, function (c) {
      return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c];
    });
  }
  var form = document.getElementById('ticket-form');
  if (form) {
    form.addEventListener('submit', function (e) {
      e.preventDefault();
      var status = document.getElementById('ticket-status');
      var fd = new FormData(form);
      var payload = { subject: (fd.get('subject') || '').toString().trim(), body: (fd.get('body') || '').toString().trim() };
      if (status) status.textContent = '…';
      fetch('/api/support/tickets', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf() },
        body: JSON.stringify(payload)
      }).then(function (r) { return r.json().then(function (j) { return { ok: r.ok, j: j }; }); })
        .then(function (o) {
          if (!o.ok) throw new Error(o.j.error || T_('tk.err', 'Could not send.'));
          form.reset();
          if (status) status.textContent = T_('tk.ok', 'Sent to support@reachmarkdigital.xyz.');
        })
        .catch(function (err) {
          if (status) status.textContent = err.message || T_('tk.err', 'Could not send.');
        });
    });
  }
  function loadTickets() {
    var list = document.getElementById('ticket-list');
    if (!list) return;
    fetch('/api/support/tickets').then(function (r) { return r.json(); }).then(function (j) {
      var rows = j.tickets || [];
      if (!rows.length) {
        list.innerHTML = '<p class="small muted">' + esc(T_('tk.empty', 'No tickets yet.')) + '</p>';
        return;
      }
      list.innerHTML = rows.map(function (t) {
        return '<article class="ticket-row" style="padding:12px 0;border-bottom:1px solid rgba(32,37,31,.08)">' +
          '<strong>' + esc(t.subject) + '</strong> · <span class="small muted">' + esc(t.status) + '</span>' +
          '<div class="small muted">' + esc(t.name || t.email) + ' · ' + esc((t.created || '').slice(0, 16)) + '</div>' +
          '<p style="margin:8px 0 0;white-space:pre-wrap">' + esc(t.body) + '</p></article>';
      }).join('');
    }).catch(function () {
      list.innerHTML = '<p class="small muted">' + esc(T_('tk.err', 'Could not load tickets.')) + '</p>';
    });
  }
  var refresh = document.getElementById('ticket-refresh');
  if (refresh) refresh.addEventListener('click', loadTickets);
  if (document.getElementById('ticket-list')) loadTickets();
})();
