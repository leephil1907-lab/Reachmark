/* First-run workspace tour (onboarding-style): six stops across the pages you will
   actually use. Completion is remembered in localStorage. Start any time with
   window.startTour() or the "Take the tour" button. */
(function () {
  'use strict';
  var T_ = window.T || function (k, f) { return f; };
  var KEY = 'rm-tour-seen';
  var STEPS = [
    { page: 'overview', sel: '#page-overview .analytics-heading', title: T_('wsj.t_t1','Your live overview'), body: T_('wsj.t_b1','Every number here comes from saved records. Nothing is estimated.') },
    { page: 'leads', sel: '#page-leads .directory', title: T_('wsj.t_t2','Lead directory'), body: T_('wsj.t_b2','Search, filter and sort saved businesses. Click a row to open its workspace.') },
    { page: 'global', sel: '#page-global .global-grid', title: T_('wsj.t_t3','Global finder'), body: T_('wsj.t_b3','Discover real businesses from OpenStreetMap, one bounded job at a time.') },
    { page: 'health', sel: '#page-health .card', title: T_('wsj.t_t4','Website health'), body: T_('wsj.t_b4','Evidence-first URL checks. A failure is never called a dead site.') },
    { page: 'crew', sel: '#page-crew', title: T_('wsj.t_t5','AI crew'), body: T_('wsj.t_b5','Scout, verify, concept, outreach — eight agents, and you approve every send.') },
    { page: 'settings', sel: '#page-settings .settings-grid', title: T_('wsj.t_t6','Sender profile'), body: T_('wsj.t_b6','Put your name behind outreach before the crew talks to anyone.') }
  ];
  var index = 0;
  var overlay = null;
  var card = null;
  var target = null;

  function mark() {
    try { window.localStorage.setItem(KEY, '1'); } catch (e) { /* private mode: tour simply repeats */ }
  }
  function seen() {
    try { return !!window.localStorage.getItem(KEY); } catch (e) { return true; }
  }
  function clearTarget() {
    if (target) { target.classList.remove('tour-spot'); target = null; }
  }
  function end() {
    clearTarget();
    if (overlay && overlay.parentNode) overlay.parentNode.removeChild(overlay);
    overlay = null;
    card = null;
    mark();
  }
  function show(i) {
    index = Math.max(0, Math.min(STEPS.length - 1, i));
    var step = STEPS[index];
    clearTarget();
    if (typeof window.navigate === 'function') window.navigate(step.page);
    target = document.querySelector(step.sel) || document.getElementById('page-' + step.page);
    if (target) {
      target.classList.add('tour-spot');
      if (target.scrollIntoView) target.scrollIntoView({ block: 'center', behavior: 'smooth' });
    }
    var dots = STEPS.map(function (_, n) {
      return '<span class="' + (n === index ? 'on' : '') + '"></span>';
    }).join('');
    card.innerHTML = '<p class="tour-step">' + T_('wsj.t_step','Step {n} of {m}').replace('{n}', index + 1).replace('{m}', STEPS.length) + '</p>' +
      '<h3>' + step.title + '</h3><p>' + step.body + '</p>' +
      '<div class="tour-dots">' + dots + '</div>' +
      '<div class="tour-btns"><button type="button" data-tour="back"' +
      (index === 0 ? ' disabled' : '') + '>' + T_('wsj.t_back','Back') + '</button>' +
      '<button type="button" data-tour="skip">' + T_('wsj.t_skip','Skip') + '</button>' +
      '<button type="button" data-tour="next" class="primary">' +
      (index === STEPS.length - 1 ? T_('wsj.t_finish','Finish') : T_('wsj.t_next','Next')) + '</button></div>';
  }
  function start() {
    if (overlay) end();
    overlay = document.createElement('div');
    overlay.className = 'tour-overlay';
    card = document.createElement('div');
    card.className = 'tour-card';
    card.setAttribute('role', 'dialog');
    card.setAttribute('aria-label', T_('wsj.t_aria','Workspace tour'));
    overlay.appendChild(card);
    document.body.appendChild(overlay);
    card.addEventListener('click', function (event) {
      var el = event.target;
      var action = el && el.getAttribute ? el.getAttribute('data-tour') : '';
      if (action === 'next') {
        if (index === STEPS.length - 1) end();
        else show(index + 1);
      } else if (action === 'back') show(index - 1);
      else if (action === 'skip') end();
    });
    document.addEventListener('keydown', function esc(event) {
      if (event.key === 'Escape' && overlay) {
        end();
        document.removeEventListener('keydown', esc);
      }
    });
    show(0);
  }
  function startIfNew() { if (!seen() && !location.hash) start(); }  // deep links win: the tour must not steal them
  window.startTour = start;
  window.startTourIfNew = startIfNew;
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', startIfNew);
  else startIfNew();
})();
