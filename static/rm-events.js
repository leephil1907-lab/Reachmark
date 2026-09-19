/* Reachmark event delegation — replaces inline on* handlers so pages can ship
   a Content-Security-Policy without 'unsafe-inline' in script-src.

   Usage on any element (static markup or JS-generated):
     data-rm-click="fn"                 no args
     data-rm-click="fn" data-rm-arg="x" one string arg
     data-rm-click="fn" data-rm-json='["a","b"]'   multiple args (JSON array)
     data-rm-click="fn" data-rm-arg="event"        pass the DOM event
     data-rm-click="fn" data-rm-arg="this"         pass the element
     data-rm-keydown="fn" data-rm-key="Enter"      key filter (keydown only)
     data-rm-change / data-rm-input / data-rm-submit work the same way

   The handler must exist as a global function (window[fn]). Only the nearest
   element with the matching attribute fires, matching the old inline
   on*="..." semantics (handlers did not bubble).
*/
(function () {
  'use strict';
  var EVENTS = ['click', 'change', 'input', 'keydown', 'submit', 'load'];
  function invoke(el, ev, type) {
    var name = el.getAttribute('data-rm-' + type);
    var fn = window[name];
    if (typeof fn !== 'function') { return; }
    if (type === 'keydown' && el.getAttribute('data-rm-key') && ev.key !== el.getAttribute('data-rm-key')) { return; }
    var args = [];
    if (el.hasAttribute('data-rm-arg')) {
      var a = el.getAttribute('data-rm-arg');
      args.push(a === 'event' ? ev : (a === 'this' ? el : a));
    }
    if (el.hasAttribute('data-rm-json')) {
      try { args.push.apply(args, JSON.parse(el.getAttribute('data-rm-json'))); } catch (_) { /* malformed: ignore */ }
    }
    try { fn.apply(window, args); } catch (err) { if (window.console) { console.error(err); } }
  }
  EVENTS.forEach(function (type) {
    // 'load' does not bubble — listen on document in the capture phase; the
    // others bubble from their target up through document.
    document.addEventListener(type, function (ev) {
      var node = ev.target;
      if (!node || node.nodeType !== 1 || typeof node.closest !== 'function') { return; }
      var el = node.closest('[data-rm-' + type + ']');
      if (el) { invoke(el, ev, type); }
    }, type === 'load');
  });
})();
