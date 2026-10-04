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
  function setModeButtons(mode) {
    document.querySelectorAll('.pf-mode [data-mode]').forEach(function (b) {
      b.setAttribute('aria-pressed', b.dataset.mode === mode ? 'true' : 'false');
    });
  }
  function renderStats(state) {
    const el = document.getElementById('pf-stats');
    if (!el) return;
    const c = state.counts || {};
    const rows = [
      ['Mode', state.mode || '—', 'Manual · Assisted · Autopilot'],
      ['Ranked', c.ranked || 0, 'Leads with a stored score'],
      ['Due', c.due_memory || 0, 'Memory follow-ups whose date has arrived'],
      ['Proposals', c.proposals || 0, 'Drafts generated from reports'],
      ['Prototypes', c.prototypes || 0, 'First-section concepts stored'],
      ['Briefs', c.briefs || 0, 'Marketplace intake still open'],
    ];
    el.innerHTML = rows.map(function (r) {
      return '<li><small>' + esc(r[0]) + '</small><strong>' + esc(r[1]) + '</strong><span>' + esc(r[2]) + '</span></li>';
    }).join('');
    const disc = document.getElementById('pf-disclaimer');
    if (disc && state.disclaimer) disc.textContent = state.disclaimer;
  }
  function renderQueue(data) {
    const el = document.getElementById('pf-queue');
    const count = document.getElementById('pf-queue-count');
    if (count) count.textContent = String(data.count || 0);
    if (!el) return;
    const items = data.items || [];
    if (!items.length) {
      el.innerHTML = '<p class="small muted">No saved businesses yet.</p>';
      return;
    }
    el.innerHTML = items.map(function (it) {
      const score = it.score == null ? 'Unscored' : (it.score + '/100');
      const cov = it.coverage == null ? '' : (' · ' + it.coverage + ' factors known');
      return '<div class="pf-row"><div><strong>' + esc(it.name) + '</strong><span>' +
        esc(score + cov) + ' · ' + esc(it.city || '') + ' · ' + esc(it.stage || '') +
        '<br>' + esc(it.why || 'Rescore to see why.') + '</span></div>' +
        '<div class="button-group"><button class="text-link" type="button" data-open="' + esc(it.id) + '">Open</button></div></div>';
    }).join('');
    el.querySelectorAll('[data-open]').forEach(function (b) {
      b.addEventListener('click', function () {
        if (typeof openLead === 'function') openLead(b.getAttribute('data-open'));
      });
    });
  }
  function renderDue(data) {
    const el = document.getElementById('pf-due');
    if (!el) return;
    const items = data.items || [];
    if (!items.length) {
      el.innerHTML = '<p class="small muted">Nothing due.</p>';
      return;
    }
    el.innerHTML = items.map(function (it) {
      return '<div class="pf-row"><div><strong>' + esc(it.lead_name || 'Business') + '</strong><span>' +
        esc(it.kind) + ' · ' + esc(it.reason) + ' · follow ' + esc(it.follow_up_at) + '</span></div></div>';
    }).join('');
  }
  function renderPrices(book) {
    const form = document.getElementById('pf-prices');
    if (!form) return;
    const packs = book.packages || [];
    form.innerHTML =
      '<label>Currency <input name="currency" maxlength="8" value="' + esc(book.currency || '') + '" placeholder="NGN, USD…"></label>' +
      packs.map(function (p, i) {
        return '<div class="pf-pack"><strong>' + esc(p.name) + '</strong>' +
          '<input name="amount-' + i + '" inputmode="numeric" placeholder="Amount in whole units (empty = not set)" value="' +
          esc(p.amount == null ? '' : p.amount) + '">' +
          '<input type="hidden" name="id-' + i + '" value="' + esc(p.id) + '">' +
          '<input type="hidden" name="name-' + i + '" value="' + esc(p.name) + '">' +
          '<p class="small muted">' + esc((p.includes || []).join(' · ')) + '</p></div>';
      }).join('') +
      '<p class="small muted">' + esc(book.note || book.history_note || '') + '</p>' +
      '<button class="secondary" type="submit">Save price book</button>';
    form.onsubmit = async function (e) {
      e.preventDefault();
      const fd = new FormData(form);
      const packages = packs.map(function (p, i) {
        const raw = fd.get('amount-' + i);
        const amount = String(raw || '').trim() === '' ? null : Number(raw);
        return { id: fd.get('id-' + i), name: fd.get('name-' + i), amount: Number.isFinite(amount) ? amount : null, includes: p.includes || [] };
      });
      try {
        await post('/api/platform/prices', { currency: fd.get('currency'), packages: packages });
        if (typeof toast === 'function') toast('Price book saved.');
      } catch (err) {
        if (typeof toast === 'function') toast(err.message, true);
      }
    };
  }
  function renderDelivery(data) {
    const el = document.getElementById('pf-delivery');
    if (!el) return;
    const watches = data.watches || [];
    const projects = data.projects || [];
    if (!watches.length && !projects.length) {
      el.innerHTML = '<p class="small muted">' + esc(data.note || 'No delivered projects on record.') + '</p>';
      return;
    }
    el.innerHTML = (watches.length ? watches.map(function (w) {
      return '<div class="pf-row"><div><strong>' + esc(w.lead_id || 'Watch') + '</strong><span>' +
        esc(w.next_offer || '') + '</span></div></div>';
    }).join('') : '<p class="small muted">Projects on file: ' + projects.length + '. Refresh watches after delivery.</p>') +
      '<p class="small muted">Paid invoices on record: ' + esc(data.paid_invoices || 0) + '</p>';
  }
  function renderMarket(data) {
    const el = document.getElementById('pf-market');
    if (!el) return;
    const rows = data.briefs || [];
    if (!rows.length) {
      el.innerHTML = '<p class="small muted">No briefs yet.</p>';
      return;
    }
    el.innerHTML = rows.map(function (b) {
      return '<div class="pf-row"><div><strong>' + esc(b.name) + '</strong><span>' +
        esc(b.category || '') + ' · ' + esc(b.status) + '</span></div>' +
        '<a class="text-link" href="/brief/' + encodeURIComponent(b.token) + '" target="_blank" rel="noopener">Open</a></div>';
    }).join('');
  }
  window.loadPlatform = async function () {
    if (!document.getElementById('page-platform')) return;
    try {
      const state = await get('/api/platform/state');
      renderStats(state);
      setModeButtons(state.mode);
    } catch (e) {
      const el = document.getElementById('pf-stats');
      if (el) el.innerHTML = '<li>' + esc(e.message) + '</li>';
    }
    try { renderQueue(await get('/api/platform/queue')); } catch (e) { /* keep empty */ }
    try { renderDue(await get('/api/platform/memory/due')); } catch (e) { /* keep empty */ }
    try { renderPrices(await get('/api/platform/prices')); } catch (e) { /* keep empty */ }
    try { renderDelivery(await get('/api/platform/delivery')); } catch (e) { /* keep empty */ }
    try { renderMarket(await get('/api/platform/market')); } catch (e) { /* keep empty */ }
  };

  function factorsHtml(ranking) {
    const factors = (ranking && ranking.factors) || [];
    if (!factors.length) return '<p>Not scored yet.</p>';
    return '<p><strong>' + esc(ranking.score) + '/100</strong> · ' + esc(ranking.coverage) + '/' +
      esc(ranking.coverage_of) + ' factors known</p><ul class="pf-factors">' +
      factors.map(function (f) {
        return '<li><b>' + esc(f.label) + '</b><span>' + esc(f.points) + '/' + esc(f.max) +
          ' · ' + esc(f.state) + '</span><small>' + esc(f.evidence) + '</small></li>';
      }).join('') + '</ul><p>' + esc(ranking.why || '') + '</p>';
  }

  window.mountPlatformDrawer = function () {
    const details = document.getElementById('tab-details');
    if (!details || document.getElementById('pf-drawer')) return;
    const wrap = document.createElement('div');
    wrap.className = 'pf-drawer';
    wrap.id = 'pf-drawer';
    wrap.innerHTML =
      '<h3>Work-first dossier</h3>' +
      '<div id="pf-d-rank"><p>Open a lead, then score it.</p></div>' +
      '<div class="button-group">' +
      '<button class="primary" type="button" id="pf-d-score">Score this lead</button>' +
      '<button class="secondary" type="button" id="pf-d-comp">Compare competitors</button>' +
      '<button class="secondary" type="button" id="pf-d-proto">Build first-section concept</button>' +
      '<button class="secondary" type="button" id="pf-d-prop">Generate proposal</button>' +
      '</div>' +
      '<div id="pf-d-extra"></div>' +
      '<h3>Memory</h3>' +
      '<label>Why they said no / what happened' +
      '<input id="pf-mem-reason" maxlength="400" placeholder="Timing — call back after rainy season"></label>' +
      '<label>Kind <select id="pf-mem-kind">' +
      '<option value="not_now">Not now</option><option value="no_budget">No budget</option>' +
      '<option value="has_site">Has a site</option><option value="timing">Timing</option>' +
      '<option value="reply">Reply</option><option value="note">Note</option>' +
      '</select></label>' +
      '<label>Potential <select id="pf-mem-pot">' +
      '<option value="high">High</option><option value="medium">Medium</option>' +
      '<option value="low">Low</option><option value="unknown" selected>Unknown</option>' +
      '</select></label>' +
      '<label>Follow up on <input id="pf-mem-date" type="date"></label>' +
      '<button class="secondary" type="button" id="pf-d-mem">Store memory</button>' +
      '<h3>Timing signal</h3>' +
      '<p>Sourced only. A tweet with no URL is not evidence.</p>' +
      '<select id="pf-sig-kind">' +
      '<option value="site_changed">Website changed</option>' +
      '<option value="new_location">New location</option>' +
      '<option value="hiring">Hiring</option>' +
      '<option value="funding">Funding</option>' +
      '<option value="reviews_worsening">Reviews worsening</option>' +
      '<option value="operator_note">Operator note</option>' +
      '</select>' +
      '<input id="pf-sig-detail" maxlength="500" placeholder="What you observed (12+ characters)">' +
      '<input id="pf-sig-source" maxlength="200" placeholder="Source name">' +
      '<input id="pf-sig-url" maxlength="500" placeholder="https://…">' +
      '<button class="secondary" type="button" id="pf-d-sig">Record signal</button>';
    const after = document.getElementById('oe-drawer') || document.getElementById('detail-meta');
    if (after && after.parentNode) after.parentNode.insertBefore(wrap, after.nextSibling);
    else details.insertBefore(wrap, details.firstChild);

    async function loadDossier() {
      const id = window.__oeLeadId;
      const box = document.getElementById('pf-d-rank');
      if (!id || !box) return;
      try {
        const data = await get('/api/platform/lead/' + encodeURIComponent(id));
        box.innerHTML = factorsHtml(data.ranking);
        const extra = document.getElementById('pf-d-extra');
        if (extra) {
          const peers = data.peers || [];
          extra.innerHTML = '<p class="small muted">' + peers.length + ' workspace peer(s) in this city/category. ' +
            esc((data.comparison && data.comparison.note) || '') + '</p>';
        }
      } catch (e) {
        box.innerHTML = '<p>' + esc(e.message) + '</p>';
      }
    }
    wrap.addEventListener('click', async function (e) {
      const id = window.__oeLeadId;
      if (!id) return;
      const extra = document.getElementById('pf-d-extra');
      try {
        if (e.target.id === 'pf-d-score') {
          await post('/api/platform/lead/' + encodeURIComponent(id) + '/score', {});
          await loadDossier();
          if (typeof loadPlatform === 'function') loadPlatform();
        }
        if (e.target.id === 'pf-d-comp') {
          const r = await post('/api/platform/lead/' + encodeURIComponent(id) + '/competitors', { live: false });
          extra.innerHTML = '<p>' + esc(r.note) + '</p>' + (r.rows || []).slice(0, 8).map(function (row) {
            return '<div class="pf-row"><div><strong>' + esc(row.name) + '</strong><span>' +
              esc(row.origin) + (row.website ? ' · site listed' : ' · no site listed') +
              (row.audited ? ' · audited' : '') + '</span></div></div>';
          }).join('') + '<p class="small muted">' + esc((r.comparison && r.comparison.note) || '') + '</p>';
        }
        if (e.target.id === 'pf-d-proto') {
          const r = await post('/api/platform/lead/' + encodeURIComponent(id) + '/prototype', {});
          extra.innerHTML = '<p><a class="primary" href="' + esc(r.url) + '" target="_blank" rel="noopener">Open first-section concept</a></p>';
        }
        if (e.target.id === 'pf-d-prop') {
          const r = await post('/api/platform/lead/' + encodeURIComponent(id) + '/proposal', {});
          extra.innerHTML = '<p><a class="primary" href="' + esc(r.url) + '" target="_blank" rel="noopener">Open draft proposal</a></p>';
        }
        if (e.target.id === 'pf-d-mem') {
          await post('/api/platform/lead/' + encodeURIComponent(id) + '/memory', {
            kind: document.getElementById('pf-mem-kind').value,
            potential: document.getElementById('pf-mem-pot').value,
            reason: document.getElementById('pf-mem-reason').value,
            follow_up_at: document.getElementById('pf-mem-date').value,
          });
          extra.innerHTML = '<p>Memory stored.</p>';
          if (typeof loadPlatform === 'function') loadPlatform();
        }
        if (e.target.id === 'pf-d-sig') {
          await post('/api/platform/lead/' + encodeURIComponent(id) + '/signal', {
            kind: document.getElementById('pf-sig-kind').value,
            detail: document.getElementById('pf-sig-detail').value,
            source: document.getElementById('pf-sig-source').value,
            source_url: document.getElementById('pf-sig-url').value,
          });
          extra.innerHTML = '<p>Signal recorded.</p>';
          await loadDossier();
        }
      } catch (err) {
        extra.innerHTML = '<p>' + esc(err.message) + '</p>';
      }
    });
    wrap.__load = loadDossier;
  };

  function hookOpenLead() {
    const orig = window.openLead;
    if (typeof orig !== 'function' || orig.__pfHooked) return;
    window.openLead = function () {
      const result = orig.apply(this, arguments);
      window.mountPlatformDrawer();
      const drawer = document.getElementById('pf-drawer');
      if (drawer && drawer.__load) drawer.__load();
      return result;
    };
    window.openLead.__pfHooked = true;
  }

  document.addEventListener('DOMContentLoaded', function () {
    hookOpenLead();
    window.mountPlatformDrawer();
    const root = document.getElementById('page-platform');
    if (root) {
      root.querySelectorAll('.pf-mode [data-mode]').forEach(function (b) {
        b.addEventListener('click', async function () {
          try {
            const r = await post('/api/platform/mode', { mode: b.dataset.mode });
            setModeButtons(r.mode);
          } catch (e) {
            if (typeof toast === 'function') toast(e.message, true);
          }
        });
      });
      const refresh = document.getElementById('pf-refresh');
      if (refresh) refresh.addEventListener('click', async function () {
        try {
          await post('/api/platform/queue/refresh', {});
          await loadPlatform();
        } catch (e) {
          if (typeof toast === 'function') toast(e.message, true);
        }
      });
      const tick = document.getElementById('pf-tick');
      if (tick) tick.addEventListener('click', async function () {
        try {
          const r = await post('/api/platform/autopilot/tick', {});
          if (typeof toast === 'function') toast((r.actions || []).join(' · ') || 'Tick complete');
          await loadPlatform();
        } catch (e) {
          if (typeof toast === 'function') toast(e.message, true);
        }
      });
      const dref = document.getElementById('pf-delivery-refresh');
      if (dref) dref.addEventListener('click', async function () {
        try { renderDelivery(await post('/api/platform/delivery/refresh', {})); }
        catch (e) { if (typeof toast === 'function') toast(e.message, true); }
      });
    }
  });
})();
