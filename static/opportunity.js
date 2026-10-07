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
  function renderFunnel(data) {
    const el = document.getElementById('oe-funnel');
    if (!el) return;
    const steps = data.steps || [];
    if (!steps.length) {
      el.innerHTML = '<li>No funnel data.</li>';
      return;
    }
    el.innerHTML = steps.map(function (s) {
      return '<li><small>' + esc(s.label) + '</small><strong>' + esc(s.count) + '</strong><span>' + esc(s.basis) + '</span></li>';
    }).join('');
    const disc = document.getElementById('oe-disclaimer');
    if (disc && data.disclaimer) disc.textContent = data.disclaimer;
  }
  function renderReports(data) {
    const el = document.getElementById('oe-reports');
    const count = document.getElementById('oe-report-count');
    if (count) count.textContent = String(data.count || 0);
    if (!el) return;
    const rows = data.reports || [];
    if (!rows.length) {
      el.innerHTML = '<p class="small muted">No reports yet. Open a lead and run the Opportunity Engine.</p>';
      return;
    }
    el.innerHTML = rows.slice(0, 24).map(function (r) {
      const href = '/o/' + encodeURIComponent(r.token);
      const contact = r.contactable ? ' · contactable' : '';
      return '<div class="oe-report-row"><div><strong>' + esc(r.lead_name || 'Business') + '</strong><span>' +
        esc(r.priority) + ' · ' + esc(r.score) + '/100 · ' + esc(r.leak_count) + ' issues' + contact + '</span></div>' +
        '<div class="button-group"><a class="text-link" href="' + href + '" target="_blank" rel="noopener">Open report</a></div></div>';
    }).join('');
  }
  window.runOpportunityQueue = async function () {
    const note = document.getElementById('oe-queue-note');
    const btn = document.getElementById('oe-run-queue');
    if (btn) btn.disabled = true;
    if (note) note.textContent = 'Diagnosing the next contactable businesses from stored evidence…';
    try {
      const r = await post('/api/opportunity/run-queue', {});
      const ran = r.ran || 0;
      if (note) {
        note.textContent = ran
          ? ('Stored ' + ran + ' diagnosis ' + (ran === 1 ? 'report' : 'reports') + '. ' + (r.note || ''))
          : ('No businesses waiting for a new diagnosis. ' + (r.note || ''));
      }
      if (typeof loadOpportunityEngine === 'function') await loadOpportunityEngine();
      if (typeof toast === 'function') toast(ran ? ('Stored ' + ran + ' report' + (ran === 1 ? '' : 's') + '.') : 'Queue is clear.');
    } catch (e) {
      if (note) note.textContent = e.message;
      if (typeof toast === 'function') toast(e.message, true);
    }
    if (btn) btn.disabled = false;
  };
  window.loadOpportunityEngine = async function () {
    try {
      const funnel = await get('/api/opportunity/funnel');
      renderFunnel(funnel);
    } catch (e) {
      const el = document.getElementById('oe-funnel');
      if (el) el.innerHTML = '<li>' + esc(e.message) + '</li>';
    }
    try {
      const reports = await get('/api/opportunity/reports');
      renderReports(reports);
    } catch (e) {
      const el = document.getElementById('oe-reports');
      if (el) el.innerHTML = '<p class="small muted">' + esc(e.message) + '</p>';
    }
  };
  window.runOpportunityReport = async function (leadId, live) {
    const box = document.getElementById('oe-drawer');
    if (box) box.innerHTML = '<p>Building the diagnosis from saved evidence…</p>';
    try {
      const r = await post('/api/opportunity/lead/' + encodeURIComponent(leadId) + '/run', { live: !!live });
      const report = r.report || {};
      const href = '/o/' + encodeURIComponent(report.token);
      if (box) {
        box.innerHTML =
          '<h3>Report stored · ' + esc(report.score) + '/100 · ' + esc(report.priority) + '</h3>' +
          '<p>' + esc((report.solution && report.solution.name) || '') + '</p>' +
          '<p>' + esc((report.solution && report.solution.why) || '') + '</p>' +
          '<div class="button-group">' +
          '<a class="primary" href="' + href + '" target="_blank" rel="noopener">Open report</a>' +
          '<button class="secondary" type="button" onclick="drawerTab(\'compose\')">Use the evidence in outreach</button>' +
          '</div>';
      }
      if (typeof loadOpportunityEngine === 'function') loadOpportunityEngine();
      if (typeof toast === 'function') toast('Opportunity report saved.');
    } catch (e) {
      if (box) box.innerHTML = '<p>' + esc(e.message) + '</p>';
      if (typeof toast === 'function') toast(e.message, true);
    }
  };
  function mountDrawer() {
    const details = document.getElementById('tab-details');
    if (!details || document.getElementById('oe-drawer')) return;
    const wrap = document.createElement('div');
    wrap.className = 'oe-drawer';
    wrap.id = 'oe-drawer';
    wrap.innerHTML =
      '<h3>Opportunity Engine</h3>' +
      '<p>Sell the diagnosis first. This stores a Digital Opportunity Report from the listing and any measured page check — no invented revenue.</p>' +
      '<div class="button-group">' +
      '<button class="primary" type="button" id="oe-run-saved">Generate report from saved evidence</button>' +
      '<button class="secondary" type="button" id="oe-run-live">Re-check the live page, then report</button>' +
      '</div>';
    const meta = document.getElementById('detail-meta');
    if (meta && meta.parentNode) meta.parentNode.insertBefore(wrap, meta.nextSibling);
    else details.insertBefore(wrap, details.firstChild);
    wrap.addEventListener('click', function (e) {
      const id = window.__oeLeadId;
      if (!id) return;
      if (e.target.id === 'oe-run-saved') runOpportunityReport(id, false);
      if (e.target.id === 'oe-run-live') runOpportunityReport(id, true);
    });
  }
  function hookOpenLead() {
    const origOpen = window.openLead;
    if (typeof origOpen !== 'function' || origOpen.__oeHooked) return;
    window.openLead = function (id, tab) {
      window.__oeLeadId = id;
      const result = origOpen.apply(this, arguments);
      mountDrawer();
      return result;
    };
    window.openLead.__oeHooked = true;
  }
  document.addEventListener('DOMContentLoaded', function () {
    hookOpenLead();
    mountDrawer();
    if (document.getElementById('oe-board')) loadOpportunityEngine();
  });
})();
