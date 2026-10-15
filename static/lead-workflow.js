/* Reachmark lead activity: durable notes, scheduled follow-ups, and a readable timeline. */
(function () {
  'use strict';
  const $ = (id) => document.getElementById(id);
  let activeLeadId = null;
  let requestSequence = 0;

  function esc(value) {
    return String(value == null ? '' : value).replace(/[&<>"']/g, (c) =>
      ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
  }
  function csrf() { return document.querySelector('meta[name="csrf-token"]')?.content || ''; }
  async function request(url, options) {
    const headers = Object.assign({ Accept: 'application/json' }, options && options.headers || {});
    if (options && options.body) headers['Content-Type'] = 'application/json';
    if (options && options.method && options.method !== 'GET' && csrf()) headers['X-CSRF-Token'] = csrf();
    const response = await fetch(url, Object.assign({ credentials: 'same-origin' }, options || {}, { headers }));
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || 'The request could not be completed.');
    return data;
  }
  function dateLabel(value) {
    if (!value) return '';
    const d = new Date(value.length === 10 ? value + 'T12:00:00' : value);
    return Number.isNaN(d.getTime()) ? value : d.toLocaleString(undefined, {
      year: 'numeric', month: 'short', day: 'numeric',
      ...(value.length > 10 ? { hour: 'numeric', minute: '2-digit' } : {})
    });
  }
  function setStatus(message, isError) {
    const el = $('lead-memory-status');
    if (!el) return;
    el.textContent = message || '';
    el.classList.toggle('is-error', !!isError);
  }
  function renderHistory(items) {
    const list = $('lead-activity-list');
    const count = $('lead-history-count');
    if (!list || !count) return;
    count.textContent = items.length + (items.length === 1 ? ' saved item' : ' saved items');
    if (!items.length) {
      list.innerHTML = '<p class="lead-history-empty">No activity recorded yet. Add a note or schedule a follow-up above.</p>';
      return;
    }
    list.innerHTML = items.map((item) => {
      const kind = String(item.kind || 'note').replace(/_/g, ' ');
      const follow = item.follow_up_at ? '<span>Follow-up · ' + esc(dateLabel(item.follow_up_at)) + (item.status === 'done' ? ' · completed' : '') + '</span>' : '';
      const potential = item.potential && item.potential !== 'unknown'
        ? '<span>Priority · ' + esc(item.potential) + '</span>' : '';
      return '<article class="lead-activity-item"><span class="lead-activity-marker" aria-hidden="true"></span>' +
        '<div><strong>' + esc(item.reason || kind) + '</strong><div class="lead-activity-meta"><span>' +
        esc(kind) + '</span><span>' + esc(dateLabel(item.created)) + '</span>' + follow + potential +
        '</div>' + (item.note ? '<p>' + esc(item.note) + '</p>' : '') + '</div></article>';
    }).join('');
  }
  async function load(leadId) {
    if (!leadId) return;
    activeLeadId = String(leadId);
    const seq = ++requestSequence;
    const list = $('lead-activity-list');
    if (list) list.innerHTML = '<p class="lead-history-empty">Loading saved activity…</p>';
    try {
      const data = await request('/api/platform/lead/' + encodeURIComponent(activeLeadId) + '/memory');
      if (seq !== requestSequence || activeLeadId !== String(leadId)) return;
      renderHistory(Array.isArray(data.items) ? data.items : []);
      setStatus('', false);
    } catch (error) {
      if (seq !== requestSequence) return;
      if (list) list.innerHTML = '<p class="lead-history-empty">Activity history could not load. Check your connection and try again.</p>';
      setStatus(error.message || 'Could not load activity history.', true);
    }
  }

  function init() {
    const form = $('lead-memory-form');
    if (!form || form.dataset.bound) return;
    form.dataset.bound = '1';
    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      if (!activeLeadId) {
        setStatus('Open a business before saving activity.', true);
        return;
      }
      if (!form.reportValidity()) return;
      const submit = $('lead-memory-save');
      const data = Object.fromEntries(new FormData(form));
      data.follow_up_at = String(data.follow_up_at || '').trim();
      submit.disabled = true;
      submit.textContent = 'Saving…';
      setStatus('Saving this activity to the business record…', false);
      try {
        await request('/api/platform/lead/' + encodeURIComponent(activeLeadId) + '/memory', {
          method: 'POST', body: JSON.stringify(data)
        });
        form.reset();
        await load(activeLeadId);
        setStatus('Saved. The activity is now attached to this business.', false);
        if (typeof window.loadReachmarkActionCenter === 'function') window.loadReachmarkActionCenter(false);
      } catch (error) {
        setStatus(error.message || 'Could not save this activity. Your text is still here so you can retry.', true);
      } finally {
        submit.disabled = false;
        submit.textContent = 'Save activity';
      }
    });
  }

  window.loadLeadWorkflow = load;
  window.addEventListener('reachmark:lead-opened', (event) => {
    if (event.detail && event.detail.id) load(event.detail.id);
  });
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
