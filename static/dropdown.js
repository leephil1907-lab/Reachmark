/* Standard dropdown: progressively enhances native single-selects.
   The original <select> stays in the DOM (name, value, events intact) so all
   forms and scripts keep working; the custom UI is purely presentational. */
(function () {
  'use strict';
  function enhance(sel) {
    if (!sel || sel.tagName !== 'SELECT' || sel.dataset.ddDone) return;
    if (sel.multiple || (sel.size || 0) > 1 || sel.hasAttribute('data-native')) return;
    sel.dataset.ddDone = '1';
    var wrap = document.createElement(sel.style.display === 'block' || sel.clientWidth > 320 ? 'div' : 'span');
    wrap.className = 'ui-dd' + (wrap.tagName === 'DIV' ? ' block' : '');
    sel.classList.add('ui-dd-src');
    sel.parentNode.insertBefore(wrap, sel);
    wrap.appendChild(sel);
    var btn = document.createElement('button');
    btn.type = 'button'; btn.className = 'ui-dd-btn'; btn.setAttribute('aria-haspopup', 'listbox');
    btn.innerHTML = '<span class="lbl"></span><span class="chev">▼</span>';
    var menu = document.createElement('div');
    menu.className = 'ui-dd-menu'; menu.setAttribute('role', 'listbox');
    wrap.appendChild(btn); wrap.appendChild(menu);
    var lbl = btn.querySelector('.lbl'), focusIx = -1;
    function sync() {
      var o = sel.options[sel.selectedIndex];
      lbl.textContent = o ? o.text : '';
      btn.setAttribute('aria-expanded', wrap.classList.contains('open') ? 'true' : 'false');
      wrap.classList.toggle('disabled', sel.disabled);
    }
    function build() {
      menu.innerHTML = '';
      Array.prototype.forEach.call(sel.options, function (o, ix) {
        if (o.disabled && o.value === '' && sel.selectedIndex !== ix) return;
        var b = document.createElement('button');
        b.type = 'button'; b.className = 'ui-dd-opt' + (ix === sel.selectedIndex ? ' on' : '');
        b.setAttribute('role', 'option'); b.disabled = o.disabled;
        b.setAttribute('aria-selected', ix === sel.selectedIndex ? 'true' : 'false');
        b.textContent = o.text;
        if (ix === sel.selectedIndex) { var t = document.createElement('span'); t.className = 'tick'; t.textContent = '✓'; b.appendChild(t); }
        b.addEventListener('click', function (e) { e.stopPropagation(); pick(ix); });
        menu.appendChild(b);
      });
    }
    function open() {
      if (sel.disabled) return;
      closeAll(wrap); build(); wrap.classList.add('open'); sync();
      var r = menu.getBoundingClientRect();
      menu.classList.toggle('up', r.bottom > window.innerHeight - 12 && r.top > window.innerHeight / 2);
    }
    function close() { wrap.classList.remove('open'); sync(); focusIx = -1; }
    function pick(ix) {
      if (sel.options[ix] && !sel.options[ix].disabled) {
        sel.selectedIndex = ix;
        sel.dispatchEvent(new Event('change', { bubbles: true }));
      }
      close(); btn.focus({ preventScroll: true });
    }
    btn.addEventListener('click', function (e) { e.stopPropagation(); wrap.classList.contains('open') ? close() : open(); });
    btn.addEventListener('keydown', function (e) {
      var items = menu.querySelectorAll('.ui-dd-opt:not(:disabled)');
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault();
        if (!wrap.classList.contains('open')) open();
        focusIx = e.key === 'ArrowDown' ? 0 : items.length - 1;
        if (items[focusIx]) items[focusIx].focus();
      } else if (e.key === 'Enter' || e.key === ' ') {
        if (!wrap.classList.contains('open')) { e.preventDefault(); open(); }
      } else if (e.key === 'Escape') close();
    });
    menu.addEventListener('keydown', function (e) {
      var items = Array.prototype.filter.call(menu.querySelectorAll('.ui-dd-opt'), function (x) { return !x.disabled; });
      var at = items.indexOf(document.activeElement);
      if (e.key === 'ArrowDown') { e.preventDefault(); (items[at + 1] || items[0]).focus(); }
      else if (e.key === 'ArrowUp') { e.preventDefault(); (items[at - 1] || items[items.length - 1]).focus(); }
      else if (e.key === 'Home') { e.preventDefault(); items[0].focus(); }
      else if (e.key === 'End') { e.preventDefault(); items[items.length - 1].focus(); }
      else if (e.key === 'Escape') { close(); btn.focus({ preventScroll: true }); }
      else if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); if (document.activeElement && document.activeElement !== menu) document.activeElement.click(); }
    });
    sel.addEventListener('change', sync);
    sync();
    sel._ddSync = sync;
  }
  function closeAll(except) {
    document.querySelectorAll('.ui-dd.open').forEach(function (w) { if (w !== except) w.classList.remove('open'); });
  }
  document.addEventListener('click', function () { closeAll(null); });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') closeAll(null); });
  function scan(root) {
    (root || document).querySelectorAll('select').forEach(enhance);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', function () { scan(document); });
  else scan(document);
  if ('MutationObserver' in window) {
    new MutationObserver(function (muts) {
      muts.forEach(function (m) {
        m.addedNodes.forEach(function (n) {
          if (n.nodeType !== 1) return;
          if (n.tagName === 'SELECT') enhance(n);
          else if (n.querySelectorAll) n.querySelectorAll('select').forEach(enhance);
        });
      });
    }).observe(document.documentElement, { childList: true, subtree: true });
  }
  window.ReachmarkDropdown = { enhance: enhance, scan: scan };
})();
