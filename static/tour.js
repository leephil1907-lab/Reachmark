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
  var keyHandler = null;
  var trigger = null;
  var previousTabindex = null;

  function mark() {
    try { window.localStorage.setItem(KEY, '1'); } catch (e) { /* private mode: tour simply repeats */ }
  }
  function seen() {
    try { return !!window.localStorage.getItem(KEY); } catch (e) { return true; }
  }
  function clearTarget() {
    if (!target) return;
    target.classList.remove('tour-spot');
    target.removeAttribute('data-tour-active');
    if (previousTabindex === null) target.removeAttribute('tabindex');
    else target.setAttribute('tabindex', previousTabindex);
    target = null;
    previousTabindex = null;
  }
  function end() {
    clearTarget();
    if (overlay && overlay.parentNode) overlay.parentNode.removeChild(overlay);
    if (card && card.parentNode) card.parentNode.removeChild(card);
    overlay = null;
    card = null;
    if (keyHandler) {
      document.removeEventListener('keydown', keyHandler);
      keyHandler = null;
    }
    mark();
    if (trigger && trigger.isConnected && typeof trigger.focus === 'function') trigger.focus({ preventScroll: true });
    trigger = null;
  }
  function show(i) {
    index = Math.max(0, Math.min(STEPS.length - 1, i));
    var step = STEPS[index];
    clearTarget();
    if (typeof window.navigate === 'function') window.navigate(step.page);
    target = document.querySelector(step.sel) ||
      document.querySelector('#page-' + step.page + ' .page-heading') ||
      document.getElementById('page-' + step.page);
    if (target) {
      previousTabindex = target.hasAttribute('tabindex') ? target.getAttribute('tabindex') : null;
      if (!target.hasAttribute('tabindex')) target.setAttribute('tabindex', '-1');
      target.classList.add('tour-spot');
      target.setAttribute('data-tour-active', 'true');
      if (target.scrollIntoView) {
        var reduceMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
        target.scrollIntoView({ block: 'center', behavior: reduceMotion ? 'auto' : 'smooth' });
      }
    }
    var dots = STEPS.map(function (_, n) {
      return '<span class="' + (n === index ? 'on' : '') + '"></span>';
    }).join('');
    card.innerHTML = '<p class="tour-step">' + T_('wsj.t_step','Step {n} of {m}').replace('{n}', index + 1).replace('{m}', STEPS.length) + '</p>' +
      '<h3>' + step.title + '</h3><p>' + step.body + '</p>' +
      '<div class="tour-dots" aria-hidden="true">' + dots + '</div>' +
      '<div class="tour-btns"><button type="button" data-tour="back"' +
      (index === 0 ? ' disabled' : '') + '>' + T_('wsj.t_back','Back') + '</button>' +
      '<button type="button" data-tour="skip">' + T_('wsj.t_skip','Skip') + '</button>' +
      '<button type="button" data-tour="next" class="primary">' +
      (index === STEPS.length - 1 ? T_('wsj.t_finish','Finish') : T_('wsj.t_next','Next')) + '</button></div>';
    var nextButton = card.querySelector('[data-tour="next"]');
    if (nextButton) nextButton.focus({ preventScroll: true });
  }
  function start() {
    if (overlay) end();
    trigger = document.activeElement;
    overlay = document.createElement('div');
    overlay.className = 'tour-overlay';
    overlay.setAttribute('aria-label', T_('wsj.t_aria','Workspace tour'));
    card = document.createElement('div');
    card.className = 'tour-card';
    card.setAttribute('role', 'dialog');
    card.setAttribute('aria-label', T_('wsj.t_aria','Workspace tour'));
    document.body.appendChild(overlay);
    document.body.appendChild(card);
    card.addEventListener('click', function (event) {
      var el = event.target;
      var action = el && el.getAttribute ? el.getAttribute('data-tour') : '';
      if (action === 'next') {
        if (index === STEPS.length - 1) end();
        else show(index + 1);
      } else if (action === 'back') show(index - 1);
      else if (action === 'skip') end();
    });
    keyHandler = function (event) {
      if (!overlay) return;
      if (event.key === 'Escape') {
        event.preventDefault();
        end();
      } else if (event.key === 'ArrowRight' && index < STEPS.length - 1) {
        event.preventDefault();
        show(index + 1);
      } else if (event.key === 'ArrowLeft' && index > 0) {
        event.preventDefault();
        show(index - 1);
      }
    };
    document.addEventListener('keydown', keyHandler);
    show(0);
  }
  function startIfNew() { if (!seen() && !location.hash) start(); }  // deep links win: the tour must not steal them
  window.startTour = start;
  window.startTourIfNew = startIfNew;
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', startIfNew);
  else startIfNew();
})();
