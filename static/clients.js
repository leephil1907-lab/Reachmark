/* Studio console: client records, manual plan control, payment approvals. Owner only. */
var CLIENTS = {users: [], pending: [], news: 0};
function clientsApi(path, method, body) {
  var options = {method: method || 'GET', headers: {'Content-Type': 'application/json'}};
  var meta = document.querySelector('meta[name="csrf-token"]');
  if (meta) options.headers['X-CSRF-Token'] = meta.content;
  if (body !== undefined) options.body = JSON.stringify(body);
  return fetch(path, options).then(function (r) {
    return r.json().catch(function () { return {}; }).then(function (data) {
      if (!r.ok) throw new Error(data.error || 'Request failed');
      return data;
    });
  });
}
function clientsWhen(stamp) {
  try { return new Date(stamp).toLocaleDateString(undefined, {month: 'short', day: 'numeric', year: 'numeric'}); }
  catch (e) { return stamp || '—'; }
}
function loadClients() {
  var list = document.getElementById('client-list');
  if (list && !CLIENTS.users.length) list.innerHTML = '<div class="sk" aria-hidden="true"><i></i><i></i><i></i></div>';
  Promise.all([
    clientsApi('/api/admin/users').catch(function (e) { return {users: [], _err: e.message}; }),
    clientsApi('/api/admin/payments?status=awaiting_approval').catch(function () { return {payments: []}; }),
    clientsApi('/api/admin/newsletter').catch(function () { return {subscribers: []}; })
  ]).then(function (out) {
    if (out[0]._err) {
      if (list) list.innerHTML = '<p class="small muted">' + esc(out[0]._err) + '</p>';
      return;
    }
    CLIENTS.users = out[0].users || [];
    CLIENTS.pending = out[1].payments || [];
    CLIENTS.news = (out[2].subscribers || []).length;
    renderClients();
  }).catch(function (e) { if (window.toast) toast(e.message, true); });
}
function renderClients() {
  var q = (document.getElementById('client-search').value || '').toLowerCase();
  var tier = document.getElementById('client-tier').value;
  var banner = document.getElementById('clients-pending');
  if (CLIENTS.pending.length) {
    banner.style.display = '';
    banner.innerHTML = '<strong>' + CLIENTS.pending.length + ' crypto payment' +
      (CLIENTS.pending.length > 1 ? 's' : '') + ' awaiting approval.</strong> Confirm the coins in your wallet app, then approve below. ' +
      CLIENTS.pending.map(function (p) {
        return '<span style="white-space:nowrap">' + esc(p.email) + ' → ' + esc(p.tier) +
          ' <button class="secondary" onclick="approvePayment(\'' + esc(p.reference) + '\')">Approve</button>' +
          ' <button class="secondary" onclick="rejectPayment(\'' + esc(p.reference) + '\')">Reject</button></span>';
      }).join(' · ');
  } else { banner.style.display = 'none'; banner.innerHTML = ''; }
  document.getElementById('newsletter-count').textContent = CLIENTS.news + ' newsletter subscriber' + (CLIENTS.news === 1 ? '' : 's');
  var rows = CLIENTS.users.filter(function (u) {
    if (tier && u.tier !== tier) return false;
    if (q && (u.email || '').toLowerCase().indexOf(q) < 0 && (u.name || '').toLowerCase().indexOf(q) < 0) return false;
    return true;
  });
  var html = rows.map(function (u) {
    var pays = (u.payments || []).map(function (p) {
      var label = esc(p.reference.slice(0, 12)) + ' · ' + esc(p.tier) + ' · ' + esc(p.status);
      if (p.status === 'paid') label = '<a href="/api/billing/receipt/' + esc(p.reference) + '.pdf">' + label + ' ↓</a>';
      else if (p.status === 'awaiting_approval') label += ' <button class="secondary" onclick="approvePayment(\'' + esc(p.reference) + '\')">Approve</button> <button class="secondary" onclick="rejectPayment(\'' + esc(p.reference) + '\')">Reject</button>';
      return '<div class="small">' + label + (p.tx_hash ? ' <span class="muted">tx ' + esc(String(p.tx_hash).slice(0, 18)) + '…</span>' : '') + '</div>';
    }).join('') || '<div class="small muted">No payments yet.</div>';
    return '<article class="card" style="margin-bottom:14px"><div class="section-top"><div><h3>' + esc(u.name || u.email) + '</h3>' +
      '<p class="small muted">' + esc(u.email) + ' · since ' + clientsWhen(u.created) +
      (u.email_verified ? ' · ✓ verified' : ' · unverified') + '</p></div>' +
      '<span class="badge">' + esc(u.tier) + (u.tier_expires ? ' → ' + clientsWhen(u.tier_expires) : '') + '</span></div>' +
      pays +
      '<div class="table-toolbar" style="margin-top:10px"><label class="small">Plan <select id="tier-' + esc(u.id) + '">' +
      ['free', 'starter', 'pro'].map(function (t) { return '<option value="' + t + '"' + (u.tier === t ? ' selected' : '') + '>' + t + '</option>'; }).join('') +
      '</select></label><label class="small">Days <input id="days-' + esc(u.id) + '" type="number" value="30" min="1" max="3650" style="width:70px"></label>' +
      '<label class="small">Note <input id="note-' + esc(u.id) + '" placeholder="bank transfer, goodwill…" style="width:170px"></label>' +
      '<button class="primary" onclick="saveClient(\'' + esc(u.id) + '\')">Save plan</button>' +
      '<button class="secondary" onclick="toggleClient(\'' + esc(u.id) + '\',' + (u.is_active ? '0' : '1') + ')">' + (u.is_active ? 'Pause account' : 'Unpause') + '</button></div></article>';
  }).join('');
  document.getElementById('client-list').innerHTML = html || '<p class="small muted">No clients match.</p>';
}
function saveClient(uid) {
  var tier = document.getElementById('tier-' + uid).value;
  var days = parseInt(document.getElementById('days-' + uid).value, 10) || 30;
  var note = document.getElementById('note-' + uid).value;
  clientsApi('/api/admin/users/' + uid, 'PATCH', {tier: tier, days: days, note: note}).then(function () {
    if (window.toast) toast('Plan saved.');
    loadClients();
  }).catch(function (e) { if (window.toast) toast(e.message, true); });
}
function toggleClient(uid, active) {
  clientsApi('/api/admin/users/' + uid, 'PATCH', {is_active: !!active}).then(function () {
    if (window.toast) toast(active ? 'Account unpaused.' : 'Account paused.');
    loadClients();
  }).catch(function (e) { if (window.toast) toast(e.message, true); });
}
function approvePayment(ref) {
  clientsApi('/api/admin/payments/' + ref + '/approve', 'POST', {}).then(function () {
    if (window.toast) toast('Payment approved — plan activated.');
    loadClients();
  }).catch(function (e) { if (window.toast) toast(e.message, true); });
}
function rejectPayment(ref) {
  if (!confirm('Reject this payment? The client keeps their current plan.')) return;
  clientsApi('/api/admin/payments/' + ref + '/reject', 'POST', {}).then(function () {
    if (window.toast) toast('Payment rejected.');
    loadClients();
  }).catch(function (e) { if (window.toast) toast(e.message, true); });
}
