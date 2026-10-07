/* PWA plumbing: service-worker registration, install prompt, and an offline notice.

   Deliberately small and dependency-free. Nothing here fetches data, and nothing here
   pretends stale content is live: if the browser is offline, the page says so. */
(function () {
  'use strict';
  var T_ = window.T || function (k, f) { return f; };
  var isIOS = /iphone|ipad|ipod/i.test(navigator.userAgent) ||
    (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  var standalone = window.matchMedia('(display-mode: standalone)').matches ||
    window.navigator.standalone === true;

  if (standalone) document.documentElement.setAttribute('data-installed', '1');

  var banner = null;
  function offlineBanner(show) {
    if (!show) {
      if (banner && banner.parentNode) banner.parentNode.removeChild(banner);
      banner = null;
      return;
    }
    if (banner) return;
    banner = document.createElement('div');
    banner.setAttribute('role', 'status');
    banner.setAttribute('data-offline-banner', '');
    banner.style.cssText = 'position:fixed;left:12px;right:12px;bottom:12px;z-index:9999;' +
      'background:#20251F;color:#F5F5EF;border-radius:12px;padding:12px 16px;font:600 13px/1.5 ' +
      'Manrope,system-ui,sans-serif;box-shadow:0 8px 24px rgba(0,0,0,.25);text-align:center';
    banner.textContent = T_('wsj.off', 'Offline — showing the last copy saved on this device. Nothing you see here is new data.');
    document.body.appendChild(banner);
  }

  window.addEventListener('online', function () { offlineBanner(false); });
  window.addEventListener('offline', function () { offlineBanner(true); });
  if (!navigator.onLine) {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', function () { offlineBanner(true); });
    } else {
      offlineBanner(true);
    }
  }

  if ('serviceWorker' in navigator) {
    window.addEventListener('load', function () {
      var swUrl = '/sw.js';
      navigator.serviceWorker.register(swUrl, { scope: '/' }).then(function (registration) {
        if (registration.waiting) registration.waiting.postMessage('skip-waiting');
        registration.addEventListener('updatefound', function () {
          var worker = registration.installing;
          if (!worker) return;
          worker.addEventListener('statechange', function () {
            if (worker.state === 'installed' && navigator.serviceWorker.controller) {
              worker.postMessage('skip-waiting');
            }
          });
        });
      }).catch(function () {
        navigator.serviceWorker.register('/static/sw.js', { scope: '/' }).catch(function () { /* bonus */ });
      });
    });
  }

  var deferred = null;
  function showInstallButtons(show) {
    document.querySelectorAll('[data-install-app]').forEach(function (button) {
      button.hidden = !show;
    });
  }

  if (standalone) {
    showInstallButtons(false);
  } else if (isIOS) {
    document.documentElement.setAttribute('data-show-ios', '1');
    showInstallButtons(true);
  }

  window.addEventListener('beforeinstallprompt', function (event) {
    event.preventDefault();
    deferred = event;
    document.documentElement.setAttribute('data-installable', '1');
    showInstallButtons(true);
  });

  document.addEventListener('click', function (event) {
    var button = event.target.closest && event.target.closest('[data-install-app]');
    if (!button) return;
    if (deferred) {
      deferred.prompt();
      deferred.userChoice.then(function () {
        deferred = null;
        document.documentElement.removeAttribute('data-installable');
        showInstallButtons(false);
      });
      return;
    }
    document.documentElement.setAttribute('data-show-ios', '1');
    var how = document.getElementById('install-how');
    if (how) how.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    else if (location.pathname !== '/app') location.href = '/app';
  });

  window.addEventListener('appinstalled', function () {
    document.documentElement.setAttribute('data-installed', '1');
    showInstallButtons(false);
  });
})();
