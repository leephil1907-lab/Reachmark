/* Workspace guided tour.
   A fixed "spotlight" layer is drawn over the target's on-screen rectangle (instead of
   lifting the element with z-index, which breaks inside stacking contexts), and the card
   is placed next to the spotlight so it never covers what it describes.
   Completion is remembered in localStorage. Start any time with window.startTour()
   or the "Take the tour" button. */
(function () {
  'use strict';
  // Resolve strings at render time: locale strings load asynchronously.
  function T_(k, f) { return typeof window.T === 'function' ? window.T(k, f) : f; }
  function tr(pair) { return T_(pair[0], pair[1]); }
  var KEY = 'rm-tour-seen';
  var STEPS = [
    { page: 'overview', sel: ['#page-overview .ws-start', '#page-overview .page-heading'], title: ['wsj.t_t1', 'Your live overview'], body: ['wsj.t_b1', 'Every number here comes from saved records. Nothing is estimated.'] },
    { page: 'global', sel: ['#page-global .global-grid', '#page-global .page-heading'], title: ['wsj.t_t3', 'Global finder'], body: ['wsj.t_b3', 'Discover real businesses from OpenStreetMap, one bounded job at a time.'] },
    { page: 'leads', sel: ['#page-leads .directory', '#page-leads .page-heading'], title: ['wsj.t_t2', 'Lead directory'], body: ['wsj.t_b2', 'Search, filter and sort saved businesses. Click a row to open its workspace.'] },
    { page: 'health', sel: ['#page-health .card', '#page-health .page-heading'], title: ['wsj.t_t4', 'Website health'], body: ['wsj.t_b4', 'Evidence-first URL checks. A failure is never called a dead site.'] },
    { page: 'outreach', sel: ['#page-outreach .page-heading'], title: ['wsj.t_t7', 'Outreach studio'], body: ['wsj.t_b7', 'Build campaigns from saved businesses. Nothing is sent until you approve it.'] },
    { page: 'enquiries', sel: ['#page-enquiries .page-heading'], title: ['wsj.t_t8', 'Enquiry inbox'], body: ['wsj.t_b8', 'Messages from your public pages land here, ready to answer or turn into a project.'] },
    { page: 'crew', sel: ['#page-crew .crew-hero', '#page-crew .page-heading'], title: ['wsj.t_t5', 'AI crew'], body: ['wsj.t_b5', 'Scout, verify, concept, outreach — eight agents, and you approve every send.'] },
    { page: 'portfolio', sel: ['#page-portfolio .page-heading'], title: ['wsj.t_t9', 'Website samples'], body: ['wsj.t_b9', 'Concept sites you can show a prospect before any build starts.'] },
    { page: 'invoices', sel: ['#page-invoices .page-heading'], title: ['wsj.t_t10', 'Contracts, invoices and clients'], body: ['wsj.t_b10', 'Keep the paperwork beside the work: contracts, invoices and client plans in one place.'] },
    { page: 'settings', sel: ['#page-settings .settings-grid', '#page-settings .page-heading'], title: ['wsj.t_t6', 'Sender profile'], body: ['wsj.t_b6', 'Put your name behind outreach before the crew talks to anyone.'] },
    { page: null, sel: ['#tour-btn'], title: ['wsj.t_t11', 'Replay any time'], body: ['wsj.t_b11', 'Open this tour again from “Take the tour” whenever you want a refresher.'] }
  ];
  var PAD = 8;            // spotlight padding around the target
  var GAP = 14;           // distance between spotlight and card
  var index = 0, steps = STEPS;
  var overlay = null, hole = null, card = null, target = null;
  var keyHandler = null, trigger = null, settleTimer = null, raf = 0, observer = null;

  function reduceMotion() { return !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches); }
  function mobile() { return window.innerWidth <= 640; }
  function mark() { try { window.localStorage.setItem(KEY, '1'); } catch (e) { /* private mode */ } }
  function seen() { try { return !!window.localStorage.getItem(KEY); } catch (e) { return true; } }
  function visible(el) { if (!el) return false; var r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; }
  function find(step) {
    for (var i = 0; i < step.sel.length; i++) {
      var el = document.querySelector(step.sel[i]);
      if (visible(el)) return el;
    }
    return step.page ? document.getElementById('page-' + step.page) : null;
  }
  function topInset() {
    var bar = document.querySelector('.topbar');
    var h = bar ? bar.getBoundingClientRect().bottom : 0;
    return Math.max(16, Math.min(h, 120)) + 12;
  }
  function bottomInset() {
    if (!mobile()) return 16;
    var nav = document.getElementById('sidebar');  // becomes a fixed bottom bar on phones
    var r = nav && visible(nav) ? nav.getBoundingClientRect() : null;
    return (r && r.bottom >= window.innerHeight - 2 && r.height < 160 ? r.height : 0) + 12;
  }

  function place() {
    raf = 0;
    if (!card || !hole) return;
    var vw = window.innerWidth, vh = window.innerHeight;
    var cw = card.offsetWidth, ch = card.offsetHeight;
    var top = topInset(), bottom = vh - bottomInset();
    if (!target || !visible(target)) {
      hole.style.opacity = '0';
      card.style.left = Math.round((vw - cw) / 2) + 'px';
      card.style.top = Math.round(Math.max(top, (vh - ch) / 2)) + 'px';
      return;
    }
    var r = target.getBoundingClientRect();
    var box = { l: r.left - PAD, t: r.top - PAD, r: r.right + PAD, b: r.bottom + PAD };
    // Keep the spotlight inside the viewport, and leave room for the card when the target is tall.
    box.l = Math.max(6, box.l); box.r = Math.min(vw - 6, box.r);
    // Only push the spotlight below the top bar when the target scrolls underneath it;
    // targets that live in the top bar itself (e.g. the tour button) keep their position.
    if (r.top < top && r.bottom > top + 40) box.t = Math.max(top - PAD, box.t);
    else box.t = Math.max(4, box.t);
    var roomForCard = mobile() ? ch + GAP : 0;
    box.b = Math.min(bottom - roomForCard, box.b);
    if (!mobile() && box.b - box.t > bottom - top - ch - GAP) box.b = Math.max(box.t + 80, bottom - ch - GAP);
    hole.style.opacity = box.b > box.t ? '1' : '0';
    hole.style.left = box.l + 'px';
    hole.style.top = box.t + 'px';
    hole.style.width = Math.max(0, box.r - box.l) + 'px';
    hole.style.height = Math.max(0, box.b - box.t) + 'px';

    var x, y;
    if (mobile()) {
      x = Math.round((vw - cw) / 2);
      y = Math.max(box.b + GAP, Math.min(bottom - ch, vh - ch - 12));
      if (y + ch > vh - 4) y = Math.max(top, vh - ch - 12);
    } else if (box.b + GAP + ch <= bottom) {              // below
      y = box.b + GAP; x = box.l;
    } else if (box.t - GAP - ch >= top - PAD) {           // above
      y = box.t - GAP - ch; x = box.l;
    } else if (vw - box.r - GAP >= cw + 12) {             // right
      x = box.r + GAP; y = box.t;
    } else if (box.l - GAP >= cw + 12) {                  // left
      x = box.l - GAP - cw; y = box.t;
    } else {                                              // dock inside, bottom-right
      x = box.r - cw - 16; y = bottom - ch;
    }
    x = Math.max(12, Math.min(vw - cw - 12, x));
    y = Math.max(12, Math.min(vh - ch - 12, y));
    card.style.left = Math.round(x) + 'px';
    card.style.top = Math.round(y) + 'px';
  }
  function schedule() { if (!raf) raf = window.requestAnimationFrame(place); }

  function scrollToTarget() {
    if (!target) return;
    var r = target.getBoundingClientRect();
    var want = window.scrollY + r.top - topInset() - PAD;
    var fits = r.top >= topInset() && r.bottom <= window.innerHeight - bottomInset() - (mobile() ? card.offsetHeight + GAP : 0);
    if (!fits) window.scrollTo({ top: Math.max(0, want), behavior: 'auto' });
  }

  function render() {
    var step = steps[index];
    var dots = steps.map(function (_, n) { return '<span class="' + (n === index ? 'on' : (n < index ? 'done' : '')) + '"></span>'; }).join('');
    card.innerHTML =
      '<p class="tour-step">' + T_('wsj.t_step', 'Step {n} of {m}').replace('{n}', index + 1).replace('{m}', steps.length) + '</p>' +
      '<h3 id="tour-title">' + tr(step.title) + '</h3><p id="tour-body">' + tr(step.body) + '</p>' +
      '<div class="tour-dots" aria-hidden="true">' + dots + '</div>' +
      '<div class="tour-btns">' +
      '<button type="button" data-tour="skip" class="ghost">' + T_('wsj.t_skip', 'Skip') + '</button>' +
      '<span class="tour-btns-gap"></span>' +
      '<button type="button" data-tour="back"' + (index === 0 ? ' disabled' : '') + '>' + T_('wsj.t_back', 'Back') + '</button>' +
      '<button type="button" data-tour="next" class="primary">' +
      (index === steps.length - 1 ? T_('wsj.t_finish', 'Finish') : T_('wsj.t_next', 'Next')) + '</button></div>';
    card.setAttribute('aria-labelledby', 'tour-title');
    card.setAttribute('aria-describedby', 'tour-body');
  }

  function show(i) {
    index = Math.max(0, Math.min(steps.length - 1, i));
    var step = steps[index];
    if (settleTimer) { clearTimeout(settleTimer); settleTimer = null; }
    if (target) target.removeAttribute('data-tour-active');
    render();
    card.classList.add('moving');
    var current = location.hash.replace('#', '');
    if (step.page && typeof window.navigate === 'function' && current !== step.page) window.navigate(step.page);
    // navigate() smooth-scrolls to the top and pages load data asynchronously,
    // so wait for the layout to settle before measuring.
    var token = index;
    settleTimer = setTimeout(function () {
      if (!card || token !== index) return;
      target = find(step);
      if (target) target.setAttribute('data-tour-active', 'true');
      scrollToTarget();
      place();
      card.classList.remove('moving');
      var next = card.querySelector('[data-tour="next"]');
      if (next) next.focus({ preventScroll: true });
      // late layout shifts (charts, lists) — re-measure a few times
      [250, 700, 1400].forEach(function (ms) { setTimeout(function () { if (token === index) schedule(); }, ms); });
    }, step.page ? 420 : 60);
  }

  function end() {
    if (settleTimer) { clearTimeout(settleTimer); settleTimer = null; }
    if (target) target.removeAttribute('data-tour-active');
    target = null;
    [overlay, hole, card].forEach(function (el) { if (el && el.parentNode) el.parentNode.removeChild(el); });
    overlay = hole = card = null;
    if (keyHandler) { document.removeEventListener('keydown', keyHandler, true); keyHandler = null; }
    window.removeEventListener('resize', schedule);
    window.removeEventListener('scroll', schedule, true);
    if (observer) { observer.disconnect(); observer = null; }
    document.documentElement.classList.remove('tour-open');
    mark();
    if (trigger && trigger.isConnected && typeof trigger.focus === 'function') trigger.focus({ preventScroll: true });
    trigger = null;
  }

  function start() {
    if (card) end();
    // Skip steps whose page does not exist in this workspace (e.g. client accounts).
    steps = STEPS.filter(function (s) { return !s.page || document.getElementById('page-' + s.page); });
    trigger = document.activeElement;
    overlay = document.createElement('div');
    overlay.className = 'tour-overlay';
    hole = document.createElement('div');
    hole.className = 'tour-hole';
    hole.setAttribute('aria-hidden', 'true');
    card = document.createElement('div');
    card.className = 'tour-card';
    card.setAttribute('role', 'dialog');
    card.setAttribute('aria-modal', 'true');
    document.body.appendChild(overlay);
    document.body.appendChild(hole);
    document.body.appendChild(card);
    document.documentElement.classList.add('tour-open');
    card.addEventListener('click', function (event) {
      var el = event.target.closest ? event.target.closest('[data-tour]') : null;
      var action = el ? el.getAttribute('data-tour') : '';
      if (action === 'next') { if (index === steps.length - 1) end(); else show(index + 1); }
      else if (action === 'back') show(index - 1);
      else if (action === 'skip') end();
    });
    overlay.addEventListener('click', function () { var n = card && card.querySelector('[data-tour="next"]'); if (n) n.focus(); });
    keyHandler = function (event) {
      if (!card) return;
      if (event.key === 'Escape') { event.preventDefault(); end(); }
      else if (event.key === 'ArrowRight' && index < steps.length - 1) { event.preventDefault(); show(index + 1); }
      else if (event.key === 'ArrowLeft' && index > 0) { event.preventDefault(); show(index - 1); }
      else if (event.key === 'Tab') {               // keep focus inside the card
        var f = card.querySelectorAll('button:not([disabled])');
        if (!f.length) return;
        var first = f[0], last = f[f.length - 1];
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
      }
    };
    document.addEventListener('keydown', keyHandler, true);
    window.addEventListener('resize', schedule);
    window.addEventListener('scroll', schedule, true);
    if (window.ResizeObserver) { observer = new ResizeObserver(schedule); observer.observe(document.body); }
    show(0);
  }

  // First visit only; deep links win (the tour must not steal them). Wait until the
  // workspace has painted so the first spotlight lands on real content.
  function startIfNew() {
    if (seen() || location.hash) return;
    setTimeout(function () { if (!seen() && !card) start(); }, 900);
  }
  window.startTour = start;
  window.startTourIfNew = startIfNew;
  window.endTour = end;
  if (document.readyState === 'complete') startIfNew();
  else window.addEventListener('load', startIfNew);
})();
