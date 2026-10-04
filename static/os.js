(function () {
  'use strict';
  function esc(s) {
    return String(s ?? '').replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function csrf() {
    return document.querySelector('meta[name="csrf-token"]')?.content || '';
  }
  async function get(url) {
    const r = await fetch(url, { credentials: 'same-origin' });
    const j = await r.json().catch(function () { return {}; });
    if (!r.ok) throw new Error(j.error || 'Request failed');
    return j;
  }
  async function post(url, data) {
    const r = await fetch(url, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf() },
      body: JSON.stringify(data || {}),
    });
    const j = await r.json().catch(function () { return {}; });
    if (!r.ok) throw new Error(j.error || 'Request failed');
    return j;
  }
  function renderInbox(data) {
    const el = document.getElementById('os-inbox');
    if (!el) return;
    const items = data.items || [];
    if (!items.length) {
      el.innerHTML = '<p class="small muted">No conversations yet.</p>';
      return;
    }
    el.innerHTML = items.map(function (it) {
      return '<div class="pf-row"><div><strong>' + esc(it.lead_name || 'Business') + '</strong><span>' +
        esc(it.last_intent || 'unclassified') + ' → ' + esc(it.suggested_action || 'review') +
        '<br>' + esc((it.last_body || '').slice(0, 160)) + '</span></div>' +
        '<button class="text-link" type="button" data-open="' + esc(it.lead_id) + '">Open</button></div>';
    }).join('');
    el.querySelectorAll('[data-open]').forEach(function (b) {
      b.addEventListener('click', function () {
        if (typeof openLead === 'function') openLead(b.getAttribute('data-open'));
      });
    });
  }
  function renderGrowth(data) {
    const el = document.getElementById('os-growth');
    if (!el) return;
    const items = data.items || [];
    if (!items.length) {
      el.innerHTML = '<p class="small muted">No delivered work on record.</p>';
      return;
    }
    el.innerHTML = items.map(function (it) {
      const amt = it.amount == null ? 'amount not set' : String(it.amount);
      return '<div class="pf-row"><div><strong>' + esc(it.lead_name || it.lead_id || 'Client') + '</strong><span>' +
        esc(it.offer || '') + ' · ' + esc(amt) + '</span></div></div>';
    }).join('');
  }
  function renderCommand(data) {
    const el = document.getElementById('os-command-body');
    if (!el) return;
    const att = data.attention || {};
    const money = data.money || {};
    const hot = data.hottest || [];
    const happened = data.happened || [];
    const replies = att.replies || [];
    const approvals = att.approvals || [];
    const upsells = att.upsells || [];
    function list(items, empty, fmt) {
      if (!items.length) return '<p class="small muted">' + esc(empty) + '</p>';
      return items.slice(0, 6).map(fmt).join('');
    }
    el.innerHTML =
      '<div class="oe-split pf-split">' +
      '<article><div class="mini-eyebrow">Needs attention</div>' +
      list(replies, 'No replies waiting.', function (r) {
        return '<div class="pf-row"><div><strong>' + esc(r.lead_name) + '</strong><span>intent ' +
          esc(r.last_intent || 'unknown') + '</span></div></div>';
      }) +
      list(approvals, 'No pending sends.', function (a) {
        return '<div class="pf-row"><div><strong>' + esc(a.title || 'Approval') + '</strong><span>' +
          esc(a.kind) + '</span></div></div>';
      }) +
      '</article><article><div class="mini-eyebrow">Hottest (commercial index)</div>' +
      list(hot, 'No commercial scores yet. Run a report.', function (h) {
        return '<div class="pf-row"><div><strong>' + esc(h.lead_name) + '</strong><span>' +
          esc(h.index_score ?? '—') + ' · ' + esc(h.why || '') + '</span></div></div>';
      }) +
      '<p class="small muted">Paid invoice sum: ' + esc(money.paid_minor_sum || 0) +
      ' · unpaid invoices: ' + esc(money.unpaid_invoices || 0) + '</p>' +
      list(upsells, 'No post-delivery upsells.', function (u) {
        return '<div class="pf-row"><div><strong>' + esc(u.lead_name) + '</strong><span>' +
          esc(u.offer || '') + '</span></div></div>';
      }) +
      '</article></div>' +
      '<div class="mini-eyebrow">What happened</div>' +
      list(happened, 'No thread events yet.', function (e) {
        return '<div class="pf-row"><div><strong>' + esc(e.stage) + ' · ' + esc(e.lead_name || '') +
          '</strong><span>' + esc(e.detail) + '</span></div></div>';
      });
    const note = document.getElementById('os-command-note');
    if (note && data.disclaimer) note.textContent = data.disclaimer;
  }
  window.loadRevenueOs = async function () {
    try { renderInbox(await get('/api/os/inbox')); } catch (e) { /* empty */ }
    try { renderGrowth(await get('/api/os/growth')); } catch (e) { /* empty */ }
    try { renderCommand(await get('/api/os/command')); } catch (e) { /* empty */ }
  };

  function renderDossier(data) {
    const box = document.getElementById('os-d-body');
    if (!box) return;
    const r = data.ranking || {};
    const rec = data.recommend || {};
    const built = data.built || {};
    const prop = data.proposal;
    const conv = data.conversation || {};
    box.innerHTML =
      '<p><strong>Why</strong> ' + esc(data.why || 'Not ranked yet.') + '</p>' +
      '<p>Work-first ' + esc(r.work_score ?? '—') + ' · gap ' + esc(r.gap_score ?? '—') +
      ' · ' + esc(r.coverage ?? 0) + '/' + esc(r.coverage_of ?? 0) + ' factors known</p>' +
      '<p><strong>Recommend</strong> ' + esc(rec.name || '') + ' — ' + esc(rec.why || '') + '</p>' +
      '<p>' + (built.prototype ? '<a class="text-link" href="' + esc(built.prototype) + '" target="_blank" rel="noopener">Prototype</a> ' : 'No prototype. ') +
      (prop ? '<a class="text-link" href="' + esc(prop.url) + '" target="_blank" rel="noopener">Proposal</a>' : 'No proposal.') + '</p>' +
      '<p><strong>Next</strong> ' + esc(data.next_action || 'review') +
      (conv.last_intent ? ' · last intent ' + esc(conv.last_intent) : '') + '</p>' +
      ((data.thread && data.thread.commercial)
        ? '<p><strong>Commercial</strong> ' + esc(data.thread.commercial.index_score ?? '—') +
          ' · ' + esc(data.thread.commercial.why || '') + '</p>'
        : '') +
      '<p class="small muted">' + esc(data.disclaimer || '') + '</p>';
  }

  window.mountOsDrawer = function () {
    const details = document.getElementById('tab-details');
    if (!details || document.getElementById('os-drawer')) return;
    const wrap = document.createElement('div');
    wrap.className = 'pf-drawer';
    wrap.id = 'os-drawer';
    wrap.innerHTML =
      '<h3>Revenue OS · why → send</h3>' +
      '<div id="os-d-body"><p>Open a lead.</p></div>' +
      '<div class="button-group">' +
      '<button class="primary" type="button" id="os-advance">One click → proposal</button>' +
      '<button class="secondary" type="button" id="os-accept">Accept → contract</button>' +
      '</div>' +
      '<label>Record a reply<textarea id="os-reply" rows="3" placeholder="How much would something like this cost?"></textarea></label>' +
      '<button class="secondary" type="button" id="os-reply-btn">Classify reply</button>' +
      '<div id="os-reply-out"></div>';
    const after = document.getElementById('pf-drawer') || document.getElementById('oe-drawer') || document.getElementById('detail-meta');
    if (after && after.parentNode) after.parentNode.insertBefore(wrap, after.nextSibling);
    else details.insertBefore(wrap, details.firstChild);

    async function load() {
      const id = window.__oeLeadId;
      if (!id) return;
      try { renderDossier(await get('/api/os/lead/' + encodeURIComponent(id))); }
      catch (e) {
        const box = document.getElementById('os-d-body');
        if (box) box.innerHTML = '<p>' + esc(e.message) + '</p>';
      }
    }
    wrap.__load = load;
    wrap.addEventListener('click', async function (e) {
      const id = window.__oeLeadId;
      const out = document.getElementById('os-reply-out');
      if (!id) return;
      try {
        if (e.target.id === 'os-reply-btn') {
          const r = await post('/api/os/lead/' + encodeURIComponent(id) + '/reply', {
            body: document.getElementById('os-reply').value,
          });
          out.innerHTML = '<p><strong>' + esc(r.intent) + '</strong> → ' + esc(r.suggested_action) +
            '</p><pre style="white-space:pre-wrap;font:13px/1.5 Manrope,sans-serif">' + esc(r.suggested_response) + '</pre>';
          await load();
          if (typeof loadRevenueOs === 'function') loadRevenueOs();
        }
        if (e.target.id === 'os-advance') {
          const r = await post('/api/os/lead/' + encodeURIComponent(id) + '/advance', {});
          out.innerHTML = '<p>Steps: ' + esc((r.steps || []).join(' → ')) +
            (r.proposal_url ? ' · <a href="' + esc(r.proposal_url) + '" target="_blank" rel="noopener">Open proposal</a>' : '') +
            '</p>';
          await load();
          if (typeof loadRevenueOs === 'function') loadRevenueOs();
        }
        if (e.target.id === 'os-accept') {
          const r = await post('/api/os/lead/' + encodeURIComponent(id) + '/accept', {});
          out.innerHTML = '<p>' + esc(r.note || 'Accepted.') +
            (r.invoice_id ? ' Invoice ' + esc(r.invoice_id.slice(0, 8)) : '') + '</p>';
          await load();
          if (typeof loadRevenueOs === 'function') loadRevenueOs();
        }
      } catch (err) {
        out.innerHTML = '<p>' + esc(err.message) + '</p>';
      }
    });
  };

  function hookOpenLead() {
    const orig = window.openLead;
    if (typeof orig !== 'function' || orig.__osHooked) return;
    window.openLead = function () {
      const result = orig.apply(this, arguments);
      window.mountOsDrawer();
      const d = document.getElementById('os-drawer');
      if (d && d.__load) d.__load();
      return result;
    };
    window.openLead.__osHooked = true;
  }

  document.addEventListener('DOMContentLoaded', function () {
    hookOpenLead();
    window.mountOsDrawer();
    const g = document.getElementById('os-growth-refresh');
    if (g) g.addEventListener('click', async function () {
      try {
        await post('/api/os/growth/refresh', {});
        await loadRevenueOs();
      } catch (e) {
        if (typeof toast === 'function') toast(e.message, true);
      }
    });
    const cr = document.getElementById('os-command-refresh');
    if (cr) cr.addEventListener('click', function () {
      if (typeof loadRevenueOs === 'function') loadRevenueOs();
    });
  });
})();
