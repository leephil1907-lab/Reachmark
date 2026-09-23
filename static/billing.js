/* Workspace plan gating: hide tabs above the client's tier, offer an upgrade. */
(function () {
  var T_ = window.T || function (k, f) { return f; };
  var NEED = {overview: 'free', portfolio: 'free', invoices: 'free', projects: 'free',
    leads: 'starter', health: 'starter', global: 'starter',
    outreach: 'pro', crew: 'pro',
    enquiries: 'owner', contracts: 'owner', settings: 'owner', clients: 'owner'};
  var RANK = {free: 0, starter: 1, pro: 2, owner: 9};
  function ready(fn) {
    if (document.readyState !== 'loading') fn();
    else document.addEventListener('DOMContentLoaded', fn);
  }
  ready(function () {
    if (/[?&]upgraded=1/.test(location.search) && window.toast) {
      try { toast(T_('wsj.up_toast','Your plan is active — the unlocked tabs are ready.')); } catch (e) {}
    }
    fetch('/api/auth/me', {headers: {'Accept': 'application/json'}}).then(function (r) {
      return r.ok ? r.json() : null;
    }).then(function (me) {
      if (!me || me.role !== 'client') return;
      var have = RANK[me.tier] || 0;
      document.querySelectorAll('.nav[data-page]').forEach(function (btn) {
        var need = RANK[NEED[btn.dataset.page]];
        if (need === undefined) need = 9;
        if (need > have) btn.style.display = 'none';
      });
      if (have >= 2) return;
      var nav = document.querySelector('.sidebar nav');
      if (nav && !nav.querySelector('[data-upgrade-link]')) {
        var a = document.createElement('a');
        a.href = '/pricing';
        a.setAttribute('data-upgrade-link', '1');
        a.className = 'nav upgrade-link';
        a.innerHTML = '<span>&#9733;</span>' + (have > 0 ? T_('wsj.up_pro','Upgrade to Pro') : T_('wsj.up_see','See plans & upgrade'));
        nav.appendChild(a);
      }
    }).catch(function () {});
  });
})();
