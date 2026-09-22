/* AI crew console — reads /api/crew, starts runs, decides approvals.
   Plain script, no dependencies, no external requests. All output is escaped. */
(function () {
  var state = { crew: null, run: null, orb: null, polling: null, openThread: '' };
  var $ = function (id) { return document.getElementById(id); };
  var esc = function (value) {
    return String(value === undefined || value === null ? '' : value)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  };
  var api = function (path, method, body) {
    var options = { method: method || 'GET', headers: { 'Content-Type': 'application/json' } };
    var meta = document.querySelector('meta[name="csrf-token"]');
    if (meta) options.headers['X-CSRF-Token'] = meta.content;
    if (body !== undefined) options.body = JSON.stringify(body);
    return fetch(path, options).then(function (response) {
      return response.json().catch(function () { return {}; }).then(function (data) {
        if (!response.ok) throw new Error(data.error || 'Request failed');
        return data;
      });
    });
  };
  var when = function (stamp) {
    try { return new Date(stamp).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }); }
    catch (e) { return stamp || ''; }
  };
  var toast = function (message, isError) {
    if (typeof window.toast === 'function') return window.toast(message, isError);
    alert(message);
  };

  // ---------------------------------------------------------------- loading
  window.loadCrew = function (force) {
    return api('/api/crew').then(function (data) {
      state.crew = data;
      renderAll();
      schedulePolling();
      return data;
    }).catch(function (error) {
      var target = $('crew-run-body');
      if (target) target.innerHTML = '<p class="small muted">Crew console could not load: ' + esc(error.message) + '</p>';
    });
  };

  function schedulePolling() {
    var onCrewPage = location.hash === '#crew' || !location.hash;
    var active = onCrewPage && state.crew && ['running', 'awaiting_approval', 'dispatching'].indexOf(topRunStatus()) !== -1;
    if (state.polling) { clearTimeout(state.polling); state.polling = null; }
    if (active) {
      state.polling = setTimeout(function () {
        window.loadCrew().then(function () { loadRunDetail(state.crew.runs[0] && state.crew.runs[0].id); });
      }, 3500);
    }
  }

  function topRunStatus() {
    var runs = (state.crew && state.crew.runs) || [];
    return runs.length ? runs[0].status : 'idle';
  }

  function loadRunDetail(runId) {
    if (!runId) return Promise.resolve();
    return api('/api/crew/runs/' + runId).then(function (data) {
      state.run = data.run;
      renderRun();
      return data.run;
    }).catch(function () {});
  }

  // ---------------------------------------------------------------- render
  function renderAll() {
    var data = state.crew;
    if (!data) return;
    renderOrb(data);
    renderStats(data);
    renderGuardrails(data);
    renderAgents(data);
    renderApprovals(data);
    renderLinks(data);
    renderThreads();
    renderFollowups(data);
    renderDispatch(data);
    renderPlaybook(data);
    renderEvents(data);
    renderRunControls(data);
    if (data.runs && data.runs.length) loadRunDetail(data.runs[0].id);
  }

  function renderOrb(data) {
    var host = $('crew-orb');
    if (!host || !window.ReachmarkCrewOrb) return;
    if (!state.orb) state.orb = window.ReachmarkCrewOrb.mount(host);
    var stages = window.ReachmarkCrewOrb.stages;
    var index = 0;
    var latest = (data.runs || [])[0];
    if (latest) {
      var order = ['scout', 'auditor', 'builder', 'scribe', 'receptionist', 'closer', 'brag'];
      var steps = latest.steps || [];
      index = steps.length ? Math.max(0, steps.length - (latest.status === 'completed' ? 0 : 1)) : 0;
      if (latest.agent) index = Math.max(index, 1);
    }
    var stage = Math.min(stages.length, Math.max(1, index + (latest && latest.status === 'completed' ? 0 : 1)));
    state.orb.setState({ stage: stage, running: !!(latest && latest.status === 'running') });
  }

  function renderStats(data) {
    var host = $('crew-stats');
    if (!host) return;
    var stats = data.stats || {};
    var linkStats = data.review_links || {};
    var cards = [
      { label: 'Runs', value: stats.runs || 0 },
      { label: 'Steps done', value: stats.steps_ok || 0 },
      { label: 'Review links', value: linkStats.total || 0 },
      { label: 'Links opened', value: linkStats.opened || 0 },
      { label: 'Answers', value: linkStats.answered || 0 },
      { label: 'Waiting on you', value: stats.pending_approvals || 0 }
    ];
    host.innerHTML = cards.map(function (card) {
      return '<div class="crew-stat"><b>' + esc(card.value) + '</b><span>' + esc(card.label) + '</span></div>';
    }).join('');
    var navBadge = $('crew-nav-badge');
    if (navBadge) navBadge.textContent = stats.pending_approvals ? ' ' + stats.pending_approvals : '';
    var badge = $('crew-provider-badge');
    if (badge) {
      var provider = data.provider || {};
      var local = provider.provider === 'ollama';
      badge.textContent = !provider.configured ? 'deterministic mode'
        : (local && provider.reachable === false ? 'local model asleep' : (provider.model || 'model ready'));
      badge.className = 'badge ' + (provider.configured && provider.reachable !== false ? 'green' : (provider.configured ? 'amber' : ''));
      badge.title = [provider.mode || '', provider.detail || '', provider.reason || ''].filter(Boolean).join(' — ');
    }
  }

  function renderGuardrails(data) {
    var host = $('crew-guardrails');
    if (!host) return;
    var rules = data.guardrails || {};
    host.innerHTML = '<b>Guardrails in force</b>' +
      '<p>' + esc(rules.outbound_rule || '') + '</p>' +
      '<p>' + esc(rules.caps || '') + '</p>' +
      '<p>' + esc(rules.suppression || '') + '</p>';
  }

  function renderAgents(data) {
    var host = $('crew-agent-grid');
    if (!host) return;
    var activeAgent = state.run && state.run.steps ? (state.run.steps.filter(function (step) { return step.status === 'running'; })[0] || {}).agent : '';
    host.innerHTML = (data.agents || []).map(function (agent) {
      return '<article class="crew-agent' + (agent.id === activeAgent ? ' active' : '') + '">' +
        '<span class="tag">' + esc(agent.tier) + '</span>' +
        '<h4>' + esc(agent.symbol) + ' ' + esc(agent.name) + '</h4>' +
        '<p>' + esc(agent.mission) + '</p>' +
        ((agent.skills || []).length ? '<p class="small muted">Playbook' + ((agent.skills || []).length > 1 ? 's' : '') +
          ': ' + (agent.skills || []).map(esc).join(' · ') + ' <span class="pill">' + esc(data.playbook_version || 'vendored') + '</span></p>' : '') +
        '<ul>' + (agent.guardrails || []).slice(0, 2).map(function (line) { return '<li>' + esc(line) + '</li>'; }).join('') + '</ul>' +
        '<div class="crew-actions"><button onclick="crewRunAgent(\'' + esc(agent.id) + '\')">Run ' + esc(agent.name) + ' only</button></div>' +
        '</article>';
    }).join('');
    var count = $('crew-agent-count');
    if (count) count.textContent = (data.agents || []).length + ' crew members';
  }

  function renderRunControls(data) {
    var select = $('crew-agent');
    if (select && !select.dataset.filled) {
      select.innerHTML = (data.agents || []).map(function (agent) {
        return '<option value="' + esc(agent.id) + '">' + esc(agent.name) + ' — ' + esc(agent.role) + '</option>';
      }).join('');
      select.dataset.filled = '1';
    }
    var categories = $('crew-category');
    if (categories && !categories.dataset.filled) {
      var list = (data && data.categories) || [];
      categories.innerHTML = ['<option value="">Any category</option>'].concat(list.map(function (name) {
        return '<option>' + esc(name) + '</option>';
      })).join('');
      categories.dataset.filled = '1';
    }
    var mode = $('crew-mode');
    var wrap = $('crew-agent-wrap');
    if (mode && wrap && !mode.dataset.wired) {
      mode.addEventListener('change', function () { wrap.hidden = mode.value !== 'single'; });
      mode.dataset.wired = '1';
    }
    var form = $('crew-run-form');
    if (form && !form.dataset.wired) {
      form.addEventListener('submit', startRun);
      form.dataset.wired = '1';
    }
  }

  function startRun(event) {
    event.preventDefault();
    var button = $('crew-submit');
    var body = {
      mode: $('crew-mode').value,
      agent: $('crew-agent').value,
      location: $('crew-location').value,
      category: $('crew-category').value,
      limit: parseInt($('crew-limit').value, 10) || 6,
      tone: $('crew-tone').value,
      include_review_link: $('crew-link').checked,
      sms_note: $('crew-sms').checked,
      fixtures: $('crew-fixtures').checked
    };
    button.disabled = true;
    button.textContent = 'Crew starting…';
    api('/api/crew/run', 'POST', body).then(function (result) {
      toast('Crew run started. Watch the timeline — everything outbound stops for your approval.');
      return window.loadCrew();
    }).catch(function (error) {
      toast(error.message, true);
    }).then(function () {
      button.disabled = false;
      button.textContent = 'Run the crew ↗';
    });
  }

  window.crewRunAgent = function (agentId) {
    var body = { mode: 'single', agent: agentId, limit: parseInt($('crew-limit').value, 10) || 6,
      location: $('crew-location').value, category: $('crew-category').value,
      tone: $('crew-tone').value, fixtures: $('crew-fixtures').checked,
      include_review_link: $('crew-link').checked };
    api('/api/crew/run', 'POST', body).then(function () {
      toast(agentId + ' is starting.');
      return window.loadCrew();
    }).catch(function (error) { toast(error.message, true); });
  };

  window.crewCancel = function () {
    var run = (state.crew.runs || [])[0];
    if (!run) return;
    api('/api/crew/runs/' + run.id + '/cancel', 'POST', {}).then(function () {
      toast('Cancellation requested — the crew stops before the next step.');
      return window.loadCrew();
    }).catch(function (error) { toast(error.message, true); });
  };

  function renderRun() {
    var run = state.run;
    var title = $('crew-run-title');
    var badge = $('crew-run-state');
    var body = $('crew-run-body');
    var cancel = $('crew-cancel');
    if (!run) {
      if (title) title.textContent = 'Latest run';
      if (badge) badge.textContent = 'no runs yet';
      if (body) body.innerHTML = '<p class="small muted">Run the crew with the offline demo switched on to see the whole loop without touching the network.</p>';
      if (cancel) cancel.hidden = true;
      return;
    }
    if (title) title.textContent = 'Run ' + run.mode + ' · ' + when(run.created);
    if (badge) {
      badge.textContent = run.status.replace(/_/g, ' ');
      badge.className = 'badge ' + (run.status === 'completed' ? 'green' :
        (run.status === 'failed' || run.status === 'blocked') ? 'amber' : '');
    }
    if (cancel) cancel.hidden = ['running', 'awaiting_approval'].indexOf(run.status) === -1;
    if (!body) return;
    var summary = '<p class="small">' + esc(run.summary || '') + '</p>';
    var steps = (run.steps || []).map(function (step) {
      var receipts = (step.receipts || []).slice(0, 8).map(function (item) {
        var link = item.url ? ' <a href="' + esc(item.url) + '" target="_blank" rel="noopener noreferrer">source ↗</a>' : '';
        return '<li><b>' + esc(item.kind) + '</b> · ' + esc(item.detail) + link + '</li>';
      }).join('');
      return '<article class="crew-step ' + esc(step.status) + '"><b>' + esc(step.agent) + ' · ' + esc(step.title) + '</b>' +
        '<small>' + esc(step.status) + (step.ms ? ' · ' + step.ms + ' ms' : '') + ' · ' + esc(when(step.started)) + '</small>' +
        '<p class="small">' + esc(step.summary || '') + '</p>' +
        (receipts ? '<ul class="crew-receipt">' + receipts + '</ul>' : '') + '</article>';
    }).join('');
    if ((run.events || []).length) {
      summary += '<details><summary class="small">Live log (' + run.events.length + ')</summary><div class="crew-transcript">' +
        run.events.slice(-25).map(function (event) {
          return '<div class="' + esc(event.level) + '"><b>' + esc(event.agent) + '</b> ' + esc(event.message) + '</div>';
        }).join('') + '</div></details>';
    }
    body.innerHTML = summary + steps;
  }

  function renderApprovals(data) {
    var host = $('crew-approvals');
    var badge = $('crew-approval-count');
    if (!host) return;
    var items = data.approvals || [];
    if (badge) {
      badge.textContent = items.length + ' waiting';
      badge.className = 'badge ' + (items.length ? 'amber' : 'green');
    }
    if (!items.length) {
      host.innerHTML = '<p class="small muted">Nothing waiting. Anything the crew wants to send will appear here first.</p>';
      return;
    }
    host.innerHTML = items.map(function (item) {
      var payload = item.payload || {};
      var warning = payload.preflight && payload.preflight !== 'ready' ? '<p class="warn">' + esc(payload.preflight) + '</p>' : '';
      var body = payload.body || payload.share_message || '';
      return '<article class="crew-approval"><header><h4>' + esc(item.title) + '</h4>' +
        '<span class="badge amber">' + esc(item.kind.replace(/_/g, ' ')) + '</span></header>' +
        (payload.subject ? '<p class="small"><b>Subject:</b> ' + esc(payload.subject) + '</p>' : '') +
        warning +
        '<pre>' + esc(body.slice(0, 2400)) + '</pre>' +
        (payload.review_link ? '<p class="small muted">Review link: <code>' + esc(payload.review_link) + '</code></p>' : '') +
        '<div class="actions">' +
        '<button class="primary" onclick="crewDecide(\'' + esc(item.id) + '\',\'approve\')">Approve</button>' +
        '<button onclick="crewDecide(\'' + esc(item.id) + '\',\'reject\')">Reject</button>' +
        '</div></article>';
    }).join('');
  }

  window.crewDecide = function (approvalId, decision) {
    var note = '';
    if (decision === 'reject') {
      note = window.prompt('Optional note for the record (why this one is not going out):') || '';
    } else {
      note = window.prompt('Optional note for the audit trail (for example the contact basis you confirmed):') || '';
    }
    api('/api/crew/approvals/' + approvalId, 'POST', { decision: decision, note: note }).then(function (result) {
      toast(decision === 'approve' ? 'Approved — it will dispatch on the next step.' : 'Rejected — nothing will be sent.');
      if (result.resumed) toast('All decisions are in; the crew resumed.');
      return window.loadCrew();
    }).catch(function (error) { toast(error.message, true); });
  };

  function renderLinks(data) {
    var host = $('crew-links');
    var badge = $('crew-link-count');
    if (!host) return;
    var links = (data.review_links || {}).links || [];
    if (badge) badge.textContent = links.length + ' total';
    if (!links.length) {
      host.innerHTML = '<p class="small muted">No review links yet. The Builder issues them during a run.</p>';
      return;
    }
    host.innerHTML = links.map(function (link) {
      var answer = link.last_choice ? '<span class="pill green">' + esc(link.last_choice) + '</span>' : '<span class="pill">no answer</span>';
      if (link.last_rating) answer += ' <span class="pill amber" title="Concept rating">' + '★'.repeat(link.last_rating) + '</span>';
      return '<div class="crew-row"><div class="grow"><b>' + esc(link.business || 'business') + '</b>' +
        '<small>' + esc(link.city || '') + ' · opened ' + esc(link.views || 0) + '×' +
        (link.first_view ? ' · first ' + esc(when(link.first_view)) : '') + ' · issued ' + esc(when(link.created)) + '</small>' +
        '<div class="crew-actions">' +
        '<button onclick="crewOpenLink(\'' + esc(link.token) + '\')">Open page</button>' +
        '<button onclick="crewCopy(\'/r/' + esc(link.token) + '\')">Copy link</button>' +
        ((link.chat_message || link.share_message) ? '<button onclick="crewCopyText(\'' + esc(link.id) + '\')">Copy chat text</button>' : '') +
        '</div></div><div>' + answer + '</div></div>';
    }).join('');
  }

  window.crewOpenLink = function (token) { window.open('/r/' + token, '_blank', 'noopener'); };

  /* Copy the short message built for WhatsApp or SMS, not the long e-mail text. */
  window.crewCopyText = function (id) {
    var links = (state.crew && state.crew.review_links && state.crew.review_links.links) || [];
    var link = links.filter(function (row) { return row.id === id; })[0];
    if (!link) return;
    var text = link.chat_message || link.share_message || '';
    if (!text) return toast('No message stored for this link yet.', true);
    if (navigator.clipboard) {
      navigator.clipboard.writeText(text).then(function () { toast('Chat message copied — paste it into WhatsApp or SMS.'); },
        function () { window.prompt('Copy this message:', text); });
    } else {
      window.prompt('Copy this message:', text);
    }
  };
  window.crewCopy = function (path) {
    var url = path.indexOf('http') === 0 ? path : (location.origin + path);
    if (navigator.clipboard) {
      navigator.clipboard.writeText(url).then(function () { toast('Copied: ' + url); },
        function () { window.prompt('Copy this link:', url); });
    } else {
      window.prompt('Copy this link:', url);
    }
  };

  function renderThreads() {
    var host = $('crew-threads');
    var badge = $('crew-thread-count');
    if (!host) return;
    var threads = (state.crew && state.crew.threads) || [];
    if (!threads.length) {
      host.innerHTML = '<p class="small muted">No conversations yet. The widget is already live on every review link — add the one-line receptionist include to any other public page and it appears there too.</p>';
      if (badge) badge.textContent = '0 open';
      return;
    }
    if (badge) badge.textContent = threads.filter(function (t) { return t.status === 'open'; }).length + ' open';
    host.innerHTML = threads.map(function (thread) {
      return '<div class="crew-row"><div class="grow"><b>' + esc(thread.business || thread.name || 'Visitor') + '</b>' +
        '<small>' + esc(thread.intent || 'unknown') + ' · ' + esc(thread.messages) + ' message(s) · ' + esc(when(thread.updated)) +
        (thread.email ? ' · ' + esc(thread.email) : '') + '</small>' +
        '<small>' + esc((thread.last_message || '').slice(0, 160)) + '</small>' +
        '<div class="crew-actions"><button onclick="crewOpenThread(\'' + esc(thread.id) + '\')">Read transcript</button>' +
        (thread.status === 'open' ? '<button onclick="crewThreadStatus(\'' + esc(thread.id) + '\',\'handled\')">Mark handled</button>' : '') +
        '</div></div><div><span class="pill ' + (thread.handoff ? 'amber' : '') + '">' + esc(thread.status) + '</span></div>' +
        '<div id="thread-' + esc(thread.id) + '"></div></div>';
    }).join('');
  }

  window.crewOpenThread = function (threadId) {
    var host = $('thread-' + threadId);
    if (!host) return;
    if (state.openThread === threadId) { host.innerHTML = ''; state.openThread = ''; return; }
    host.innerHTML = '<p class="small muted">Loading…</p>';
    state.openThread = threadId;
    api('/api/receptionist/threads/' + threadId).then(function (data) {
      host.innerHTML = '<div class="crew-transcript">' + (data.transcript || []).map(function (line) {
        return '<div class="' + esc(line.role) + '"><b>' + esc(line.role) + ':</b> ' + esc(line.text) + '</div>';
      }).join('') + '</div>';
    }).catch(function (error) { host.innerHTML = '<p class="small">' + esc(error.message) + '</p>'; });
  };

  window.crewThreadStatus = function (threadId, status) {
    api('/api/receptionist/threads/' + threadId, 'POST', { status: status }).then(function () {
      toast('Conversation marked ' + status + '.');
      return window.loadCrew();
    }).catch(function (error) { toast(error.message, true); });
  };

  function renderFollowups(data) {
    var host = $('crew-followups');
    var badge = $('crew-followup-count');
    if (!host) return;
    var items = data.followups || [];
    if (badge) badge.textContent = items.length + ' planned';
    if (!items.length) {
      host.innerHTML = '<p class="small muted">No follow-ups scheduled. The Scribe adds them when a draft is approved for a run.</p>';
      return;
    }
    host.innerHTML = items.map(function (item) {
      return '<div class="crew-row"><div class="grow"><b>' + esc(item.kind.replace(/_/g, ' ')) + '</b>' +
        '<small>due ' + esc(when(item.due)) + ' · ' + esc(item.channel) + ' · ' + esc(item.state) + '</small></div>' +
        '<div><span class="pill amber">planned</span></div></div>';
    }).join('');
  }

  function renderDispatch(data) {
    var host = $('crew-dispatch');
    var badge = $('crew-dispatch-count');
    if (!host) return;
    var items = data.dispatch || [];
    if (badge) badge.textContent = items.length + ' recent';
    if (!items.length) {
      host.innerHTML = '<p class="small muted">Nothing dispatched yet. Approved messages appear here with the exact result.</p>';
      return;
    }
    host.innerHTML = items.map(function (item) {
      var tone = item.state === 'sent' ? 'green' : (item.state === 'failed' || item.state === 'unknown') ? 'red' : 'amber';
      return '<div class="crew-row"><div class="grow"><b>' + esc(item.channel) + ' → ' + esc(item.recipient || 'no address') + '</b>' +
        '<small>' + esc(item.subject || '') + ' · ' + esc(item.detail || '') + '</small>' +
        '<small>' + esc(when(item.created)) + '</small></div>' +
        '<div><span class="pill ' + tone + '">' + esc(item.state) + '</span></div></div>';
    }).join('');
  }

  function renderPlaybook(data) {
    var host = $('crew-skills');
    var badge = $('crew-skill-count');
    var note = $('crew-skill-note');
    var playbook = data.playbook || {};
    if (!host) return;
    var skills = playbook.skills || [];
    if (badge) badge.textContent = skills.length + ' playbooks';
    if (note) {
      note.innerHTML = 'Vendored, unmodified copies of MIT-licensed skills, read at runtime: ' +
        (playbook.sources || []).map(function (source) {
          return '<a href="' + esc(source.repo) + '" target="_blank" rel="noopener noreferrer">' + esc(source.repo.replace('https://github.com/', '')) + '</a> (' + esc(source.license) + ')';
        }).join(' · ') + '. They shape <em>how</em> the crew writes and checks things — never what is true about a business.';
    }
    host.innerHTML = skills.map(function (skill) {
      return '<div class="crew-skill"><b>' + esc(skill.slug) + (skill.version ? ' <span class="pill">v' + esc(skill.version) + '</span>' : '') + '</b>' +
        '<small>used by ' + esc((skill.agents || []).join(', ')) + '</small>' +
        '<p>' + esc(skill.use) + '</p></div>';
    }).join('');
  }

  function renderEvents(data) {
    var host = $('crew-events');
    var badge = $('crew-event-count');
    if (!host) return;
    var events = (data.events || []).slice().reverse();
    if (badge) badge.textContent = events.length + ' entries';
    if (!events.length) {
      host.innerHTML = '<p class="small muted">The trail fills as the crew works — every step, decision and refusal is recorded.</p>';
      return;
    }
    host.innerHTML = events.map(function (event) {
      return '<div class="crew-event ' + esc(event.level) + '"><time>' + esc(when(event.created)) + '</time>' +
        '<span class="who">' + esc(event.agent) + '</span><span class="msg">' + esc(event.message) + '</span></div>';
    }).join('');
  }

  // ------------------------------------------------------------ receptionist
  window.loadCrewThreads = function () {
    return api('/api/receptionist/threads').then(function (data) {
      if (state.crew) state.crew.threads = data;
      renderThreads();
    }).catch(function () {});
  };

  // Boot when the page is shown. app.js calls loadCrew() on navigation.
  document.addEventListener('DOMContentLoaded', function () { loadCrew(); });
  window.addEventListener('hashchange', function () {
    if (location.hash === '#crew') loadCrew();
  });
  document.addEventListener('visibilitychange', function () {
    if (document.visibilityState === 'visible' && location.hash === '#crew') loadCrew();
  });
})();
