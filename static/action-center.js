(function () {
  'use strict';

  const rootId = 'rm-action-center';
  const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (char) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  })[char]);

  async function get(url) {
    const response = await fetch(url, { credentials: 'same-origin', headers: { Accept: 'application/json' } });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || 'Could not load workspace actions.');
    return data;
  }

  function openLead(id) {
    if (!id) return;
    if (typeof window.openLead === 'function') {
      window.openLead(id);
      return;
    }
    if (typeof window.navigate === 'function') window.navigate('leads');
  }

  function openLeadButton(id, label) {
    return '<button type="button" data-action-open="' + esc(id || '') + '"' +
      (id ? '' : ' disabled') + '>' + esc(label || 'Open') + '</button>';
  }

  function empty(text) {
    return '<div class="action-center-empty">' + esc(text) + '</div>';
  }

  function renderRows(items, getTitle, getDetail, emptyText, max, action) {
    if (!items.length) return empty(emptyText);
    return '<div class="action-center-list">' + items.slice(0, max || 4).map((item) => {
      const control = action === 'complete-followup'
        ? '<button type="button" data-followup-complete="' + esc(item.id || '') + '" data-followup-lead="' + esc(item.lead_id || '') + '">Mark done ✓</button>'
        : openLeadButton(item.lead_id, 'Open ↗');
      return '<div class="action-center-row"><div><strong>' + esc(getTitle(item)) + '</strong><span>' +
        esc(getDetail(item)) + '</span></div>' + control + '</div>';
    }).join('') + '</div>';
  }

  function render(root, command, due, metrics) {
    const next = command.next_to_win;
    const attention = command.attention || {};
    const replies = attention.replies || [];
    const approvals = attention.approvals || [];
    const upsells = attention.upsells || [];
    const hot = command.hottest || [];
    const followups = due.items || [];
    const waitingCount = replies.length + approvals.length + followups.length;
    const rate = (value) => value == null ? '—' : Math.round(Number(value) * 100) + '%';
    const stages = ['New', 'Drafted', 'Contacted', 'Replied', 'Won', 'Not now', 'Not a fit'];
    const stageCounts = Object.fromEntries(((metrics && metrics.by_stage) || []).map((item) => [item.k || 'New', Number(item.n) || 0]));
    const pipelineCard = metrics ? (
      '<article class="action-center-card action-pipeline-board"><div class="action-pipeline-head"><div><h3>Manage your pipeline</h3>' +
      '<p class="action-muted">Select a stage to open the matching saved leads.</p></div><span class="action-center-pill">LIVE RECORDS</span></div>' +
      '<div class="action-pipeline-stages">' + stages.map((stage) =>
        '<button type="button" class="action-pipeline-stage" data-pipeline-stage="' + esc(stage) + '">' +
        '<span>' + esc(stage) + '</span><strong>' + esc(stageCounts[stage] || 0) + '</strong><small>Open leads</small></button>'
      ).join('') + '</div></article>'
    ) : '';
    const conversion = metrics ? (
      '<article class="action-center-card action-center-metrics"><h3>Recorded conversions</h3>' +
      '<div class="action-metric-grid">' +
      '<div class="action-metric"><strong>' + esc(metrics.leads ?? 0) + '</strong><span>Leads</span></div>' +
      '<div class="action-metric"><strong>' + esc(metrics.contacted ?? 0) + '</strong><span>Contacted</span></div>' +
      '<div class="action-metric"><strong>' + esc(metrics.replies ?? 0) + '</strong><span>Replied</span></div>' +
      '<div class="action-metric"><strong>' + esc(metrics.won ?? 0) + '</strong><span>Won</span></div>' +
      '</div><div class="action-rate-row"><span>Contact rate <b>' + rate(metrics.contact_rate) + '</b></span>' +
      '<span>Reply rate <b>' + rate(metrics.reply_rate) + '</b></span>' +
      '<span>Win rate <b>' + rate(metrics.win_rate) + '</b></span></div>' +
      '<p class="action-muted">Calculated from saved lead stages. Rates show “—” when there is no denominator; these are recorded outcomes, not forecasts.</p></article>'
    ) : '';
    const priorityLead = next && next.lead_id
      ? '<div class="action-center-pill">NEXT BEST MOVE</div><p class="action-center-main">' + esc(next.lead_name || 'Priority business') + '</p>' +
        '<p class="action-muted">' + esc((next.next && next.next.label) || 'Review opportunity') +
        (next.wedge ? ' · ' + esc(next.wedge.replace(/_/g, ' ')) : '') + '</p>' +
        (next.blockers && next.blockers[0] ? '<p class="action-muted">' + esc(next.blockers[0].text) + '</p>' : '') +
        '<div class="action-center-buttons">' + openLeadButton(next.lead_id, 'Continue with this lead') +
        '<button type="button" class="secondary" data-action-discover>Discover businesses</button></div>'
      : '<div class="action-center-pill">READY WHEN YOU ARE</div><p class="action-center-main">Find your next opportunity.</p>' +
        '<p class="action-muted">Discover a business, review the evidence, then choose the next step.</p>' +
        '<div class="action-center-buttons"><button type="button" class="primary" data-action-discover>Discover businesses ↗</button></div>';

    root.innerHTML =
      '<div class="action-center-head"><div><div class="eyebrow">YOUR WORKDAY</div><h2 id="rm-action-center-title">Today’s next moves</h2>' +
      '<p>Evidence first. Then one clear action at a time. These lists are based on records in your workspace.</p></div>' +
      '<button class="secondary" type="button" data-action-refresh>Refresh actions ↻</button></div>' +
      '<div class="action-center-grid">' +
        '<article class="action-center-card is-primary">' + priorityLead + '</article>' +
        '<article class="action-center-card"><h3>Follow-ups due</h3>' +
          renderRows(followups, (item) => item.lead_name || 'Business', (item) =>
            [item.kind, item.reason, item.follow_up_at ? 'Due ' + item.follow_up_at : 'Due now'].filter(Boolean).join(' · '),
            'No follow-ups are due right now.', 4, 'complete-followup') + '</article>' +
        '<article class="action-center-card"><h3>Needs your attention</h3>' +
          renderRows(replies, (item) => item.lead_name || 'Business', (item) =>
            'Reply waiting · ' + (item.last_intent || 'intent not classified'),
            'No replies waiting for review.', 3) +
          renderRows(approvals, (item) => item.title || 'Approval required', (item) =>
            [item.kind, item.created ? 'Created ' + item.created : 'Awaiting review'].filter(Boolean).join(' · '),
            'No pending approvals.', 3) + '</article>' +
        '<article class="action-center-card"><h3>Priority opportunities</h3>' +
          renderRows(hot.filter((item) => item.lead_id !== (next && next.lead_id)), (item) => item.lead_name || 'Business', (item) =>
            (item.index_score == null ? 'Not scored' : 'Commercial index ' + item.index_score) +
            (item.city ? ' · ' + item.city : '') + (item.why ? ' · ' + item.why : ''),
            'No ranked opportunities yet. Generate a report to start scoring from recorded evidence.', 4) +
          (upsells.length ? '<p class="action-center-status">Post-delivery growth opportunities: ' + esc(upsells.length) + '</p>' : '') +
        '</article>' + conversion + pipelineCard +
      '</div>' +
      '<p class="action-center-status" role="status" aria-live="polite" id="rm-action-center-status">' +
      esc(waitingCount ? (waitingCount + ' follow-up or review item(s) need attention.') : 'Workspace actions refreshed from saved records.') +
      '</p>';

    root.querySelectorAll('[data-action-open]').forEach((button) => {
      button.addEventListener('click', () => openLead(button.getAttribute('data-action-open')));
    });
    root.querySelectorAll('[data-action-discover]').forEach((button) => {
      button.addEventListener('click', () => {
        if (typeof window.navigate === 'function') window.navigate('global');
      });
    });
    root.querySelectorAll('[data-followup-complete]').forEach((button) => {
      button.addEventListener('click', async () => {
        const memoryId = button.getAttribute('data-followup-complete');
        const leadId = button.getAttribute('data-followup-lead');
        if (!memoryId || !leadId || button.disabled) return;
        button.disabled = true;
        button.textContent = 'Saving…';
        try {
          const meta = document.querySelector('meta[name="csrf-token"]');
          const headers = { 'Content-Type': 'application/json', Accept: 'application/json' };
          if (meta && meta.content) headers['X-CSRF-Token'] = meta.content;
          const response = await fetch('/api/platform/lead/' + encodeURIComponent(leadId) + '/memory/' + encodeURIComponent(memoryId) + '/complete', {
            method: 'POST', credentials: 'same-origin', headers, body: JSON.stringify({})
          });
          const data = await response.json().catch(() => ({}));
          if (!response.ok) throw new Error(data.error || 'Could not complete this follow-up.');
          await load(true);
        } catch (error) {
          const status = document.getElementById('rm-action-center-status');
          if (status) status.textContent = error.message || 'Could not complete this follow-up.';
          button.disabled = false;
          button.textContent = 'Retry';
        }
      });
    });
    root.querySelectorAll('[data-pipeline-stage]').forEach((button) => {
      button.addEventListener('click', () => {
        const filter = document.getElementById('filter-stage');
        if (filter) filter.value = button.getAttribute('data-pipeline-stage') || '';
        if (typeof window.navigate === 'function') window.navigate('leads');
        if (typeof window.renderLeads === 'function') window.renderLeads();
      });
    });
    const refreshButton = root.querySelector('[data-action-refresh]');
    if (refreshButton) refreshButton.addEventListener('click', () => load(true));
  }

  async function load(showLoading) {
    const root = document.getElementById(rootId);
    if (!root) return;
    const status = document.getElementById('rm-action-center-status');
    if (showLoading && status) status.textContent = 'Refreshing saved workspace actions…';
    try {
      const results = await Promise.allSettled([
        get('/api/os/command'),
        get('/api/platform/memory/due'),
        get('/api/os/metrics')
      ]);
      const commandResult = results[0];
      const dueResult = results[1];
      const metricsResult = results[2];
      if (commandResult.status !== 'fulfilled') throw commandResult.reason;
      const command = commandResult.value;
      const due = dueResult.status === 'fulfilled' ? dueResult.value : { items: [] };
      const metrics = metricsResult.status === 'fulfilled' ? metricsResult.value : null;
      render(root, command, due, metrics);
      if (dueResult.status !== 'fulfilled' || metricsResult.status !== 'fulfilled') {
        const note = document.getElementById('rm-action-center-status');
        if (note) note.textContent = dueResult.status !== 'fulfilled' ? 'Priority leads and replies loaded. Follow-up reminders could not be loaded.' : 'Workspace actions loaded. Conversion metrics are temporarily unavailable.';
      }
    } catch (error) {
      root.innerHTML = '<div class="action-center-head"><div><div class="eyebrow">YOUR WORKDAY</div>' +
        '<h2>Today’s next moves</h2><p>We couldn’t load the action list just now. Your leads and reports remain available.</p></div>' +
        '<button class="secondary" type="button" data-action-retry>Try again</button></div>' +
        '<p class="action-center-status" role="status">' + esc(error.message || 'Please try again.') + '</p>';
      const retry = root.querySelector('[data-action-retry]');
      if (retry) retry.addEventListener('click', () => load(true));
    }
  }

  window.loadReachmarkActionCenter = load;
  document.addEventListener('DOMContentLoaded', () => load(false));
})();
