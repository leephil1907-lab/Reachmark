/* Admin › Activity — live record of what visitors and customers do on the website.
 * Polls /api/admin/activity every 15 s while the tab is visible. A badge on the
 * nav item counts entries the owner has not looked at yet, and a new sign-up
 * pops a toast wherever the owner is in the console. */
(function () {
  var T_ = window.T || function (k, f) { return f; };
  var page = document.getElementById('page-activity');
  if (!page) return; // owner-only panel; clients never get it

  var POLL_MS = 15000;
  var SEEN_KEY = 'rm-act-seen';
  var state = { data: null, filter: 'all', latest: 0, timer: null, busy: false };

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function icon(kind) {
    var tpl = document.getElementById('act-icons');
    var el = tpl && tpl.content.querySelector('[data-ic="' + kind + '"]');
    if (!el) el = tpl && tpl.content.querySelector('[data-ic="other"]');
    return el ? el.innerHTML : '';
  }
  function seen() { return parseInt(localStorage.getItem(SEEN_KEY) || '0', 10) || 0; }
  function markSeen(id) { try { localStorage.setItem(SEEN_KEY, String(id || 0)); } catch (e) {} }
  function onPage() { return page.classList.contains('active'); }

  function ago(iso) {
    var t = Date.parse(iso);
    if (!t) return '';
    var s = Math.max(0, Math.round((Date.now() - t) / 1000));
    if (s < 45) return T_('ws.act_now', 'just now');
    var m = Math.round(s / 60);
    if (m < 60) return T_('ws.act_min', '{n} min ago').replace('{n}', m);
    var h = Math.round(m / 60);
    if (h < 24) return T_('ws.act_hr', '{n} h ago').replace('{n}', h);
    var d = Math.round(h / 24);
    if (d < 30) return T_('ws.act_day', '{n} d ago').replace('{n}', d);
    return new Date(t).toLocaleDateString();
  }
  function stamp(iso) { var t = Date.parse(iso); return t ? new Date(t).toLocaleString() : ''; }

  /* Map a stored activity row to an icon + filter group. */
  function classify(row) {
    var m = row.message || '';
    if (row.kind === 'account') {
      if (/account created|Client created via/i.test(m)) return { ic: 'signup', group: 'account', hot: true };
      if (/signed in/i.test(m)) return { ic: 'signin', group: 'account' };
      if (/verified/i.test(m)) return { ic: 'verified', group: 'account' };
      if (/password/i.test(m)) return { ic: 'password', group: 'account' };
      if (/closed/i.test(m)) return { ic: 'closed', group: 'account' };
      return { ic: 'other', group: 'account' };
    }
    if (row.kind === 'billing') return { ic: 'billing', group: 'billing', hot: /upgraded|awaiting/i.test(m) };
    if (row.kind === 'enquiry' || row.kind === 'receptionist' || row.kind === 'ticket') {
      return { ic: row.kind, group: 'enquiry', hot: row.kind !== 'ticket' };
    }
    return { ic: row.kind, group: 'site' };
  }

  function renderKpis(d) {
    page.querySelectorAll('[data-act-k]').forEach(function (b) {
      var path = b.getAttribute('data-act-k').split('.');
      var v = d[path[0]] ? d[path[0]][path[1]] : 0;
      b.textContent = (v == null ? 0 : v).toLocaleString();
    });
  }

  function renderSignups(d) {
    var box = document.getElementById('act-signups');
    var rows = d.signups || [];
    if (!rows.length) {
      box.innerHTML = '<div class="act-empty">' + icon('signup') + '<p><b>' + esc(T_('ws.act_nosign_t', 'No sign-ups yet')) +
        '</b><span>' + esc(T_('ws.act_nosign_d', 'New accounts appear here the moment someone signs up.')) + '</span></p></div>';
      return;
    }
    box.innerHTML = '<div class="act-table" role="table">' +
      '<div class="act-tr act-th" role="row"><span role="columnheader">' + esc(T_('ws.act_c_who', 'Person')) + '</span><span role="columnheader">' +
      esc(T_('ws.act_c_joined', 'Joined')) + '</span><span role="columnheader">' + esc(T_('ws.act_c_status', 'Status')) + '</span></div>' +
      rows.map(function (u) {
        var initial = (u.name || u.email || '?').trim().charAt(0).toUpperCase();
        var plan = (u.tier && u.tier !== 'free') ? '<span class="act-chip lime">' + esc(u.tier) + '</span>' : '<span class="act-chip">' + esc(T_('ws.act_free', 'Free')) + '</span>';
        var ver = u.email_verified ? '<span class="act-chip ok">' + esc(T_('ws.act_ver', 'Verified')) + '</span>' : '<span class="act-chip warn">' + esc(T_('ws.act_unver', 'Unverified')) + '</span>';
        var fresh = Date.parse(u.created) > Date.now() - 86400000 ? '<span class="act-new">' + esc(T_('ws.act_new', 'New')) + '</span>' : '';
        return '<div class="act-tr" role="row"><span role="cell" class="act-who"><i class="act-av" aria-hidden="true">' + esc(initial) + '</i><span><b>' +
          esc(u.name || T_('ws.act_noname', 'No name given')) + fresh + '</b><small>' + esc(u.email) + ' · ' + esc(u.via || 'Email') + '</small></span></span>' +
          '<span role="cell" title="' + esc(stamp(u.created)) + '">' + esc(ago(u.created)) + '</span>' +
          '<span role="cell" class="act-status">' + ver + plan + '</span></div>';
      }).join('') + '</div>';
  }

  function renderFeed(d) {
    var list = document.getElementById('act-feed');
    var mark = seen();
    var rows = (d.feed || []).filter(function (r) { return state.filter === 'all' || classify(r).group === state.filter; });
    if (!rows.length) {
      list.innerHTML = '<li class="act-empty">' + icon('other') + '<p><b>' + esc(T_('ws.act_nofeed_t', 'Nothing here yet')) + '</b><span>' +
        esc(T_('ws.act_nofeed_d', 'Sign-ups, sign-ins, enquiries, payments and front-desk hand-offs are recorded here as they happen.')) + '</span></p></li>';
      return;
    }
    list.innerHTML = rows.map(function (r) {
      var c = classify(r);
      var isNew = mark && r.id > mark;
      return '<li class="act-item' + (c.hot ? ' hot' : '') + (isNew ? ' unseen' : '') + '" data-group="' + c.group + '">' +
        '<span class="act-ic">' + icon(c.ic) + '</span><span class="act-msg">' + esc(r.message) + '</span>' +
        '<time datetime="' + esc(r.created) + '" title="' + esc(stamp(r.created)) + '">' + esc(ago(r.created)) + '</time></li>';
    }).join('');
  }

  function setBadge(n) {
    var b = document.getElementById('activity-badge');
    if (!b) return;
    b.textContent = n > 0 ? (n > 99 ? '99+' : String(n)) : '';
    b.classList.toggle('on', n > 0);
  }

  function announceNewSignups(prev, next) {
    if (!prev || typeof toast !== 'function') return;
    var known = {};
    (prev.signups || []).forEach(function (u) { known[u.id] = 1; });
    (next.signups || []).filter(function (u) { return !known[u.id]; }).slice(0, 3).forEach(function (u) {
      toast(T_('ws.act_toast', 'New sign-up: {who}').replace('{who}', u.name || u.email));
    });
  }

  function render() {
    var d = state.data;
    if (!d) return;
    renderKpis(d);
    renderSignups(d);
    renderFeed(d);
    var up = document.getElementById('act-updated');
    if (up) up.textContent = T_('ws.act_updated', 'Live · updated {t}').replace('{t}', new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }));
    var unseen = (d.feed || []).filter(function (r) { return r.id > seen(); }).length;
    if (!seen() && d.latest_id) { markSeen(d.latest_id); unseen = 0; } // first visit: start clean
    if (onPage() && !document.hidden) {
      // Keep the highlight visible for this render, then clear it for the next one.
      setTimeout(function () { markSeen(d.latest_id); setBadge(0); }, 4000);
    }
    setBadge(onPage() ? 0 : unseen);
  }

  function load(manual) {
    if (state.busy) return;
    state.busy = true;
    fetch('/api/admin/activity?since=' + seen(), { headers: { Accept: 'application/json' }, credentials: 'same-origin' })
      .then(function (r) {
        if (r.status === 401) { location.href = '/admin'; throw new Error('signed out'); }
        return r.json();
      })
      .then(function (d) {
        announceNewSignups(state.data, d);
        state.data = d;
        render();
        if (manual && typeof toast === 'function') toast(T_('ws.act_refreshed', 'Activity is up to date.'));
      })
      .catch(function () {})
      .then(function () { state.busy = false; });
  }
  window.loadActivity = load;

  page.querySelectorAll('[data-act-filter]').forEach(function (b) {
    b.addEventListener('click', function () {
      page.querySelectorAll('[data-act-filter]').forEach(function (x) { x.classList.toggle('on', x === b); });
      state.filter = b.getAttribute('data-act-filter');
      if (state.data) renderFeed(state.data);
    });
  });

  function tick() { if (!document.hidden) load(false); }
  state.timer = setInterval(tick, POLL_MS);
  document.addEventListener('visibilitychange', function () { if (!document.hidden) load(false); });
  // Refresh relative times between polls.
  setInterval(function () { if (state.data && onPage()) { renderSignups(state.data); renderFeed(state.data); } }, 60000);

  // The admin console opens on Activity unless a specific page was requested.
  // On the owner's very first visit the guided tour runs instead: navigate()
  // writes #activity into the address, and tour.js never starts over a deep link.
  function tourPending() {
    try { return !localStorage.getItem('rm-tour-seen'); } catch (e) { return false; }
  }
  function landing() {
    if (!location.hash && !tourPending() && typeof navigate === 'function') navigate('activity');
    load(false);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', landing); else landing();
})();
