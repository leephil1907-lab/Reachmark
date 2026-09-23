/* PWA plumbing: service-worker registration, install prompt, and an offline notice.

   Deliberately small and dependency-free. Nothing here fetches data, and nothing here
   pretends stale content is live: if the browser is offline, the page says so. */
(function () {
  'use strict';
  var T_ = window.T || function (k, f) { return f; };
  if (!('serviceWorker' in navigator)) return;

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
    banner.textContent = T_('wsj.off','Offline — showing the last copy saved on this device. Nothing you see here is new data.');
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

  window.addEventListener('load', function () {
    navigator.serviceWorker.register('/static/sw.js', { scope: '/' }).then(function (registration) {
      /* A waiting worker means a new version is ready; activate it on the next load. */
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
    }).catch(function () { /* installability is a bonus, never a requirement */ });
  });

  /* Chrome/Edge install prompt: keep it, offer it from the footer instead of hijacking. */
  var deferred = null;
  window.addEventListener('beforeinstallprompt', function (event) {
    event.preventDefault();
    deferred = event;
    document.documentElement.setAttribute('data-installable', '1');
    var button = document.querySelector('[data-install-app]');
    if (button) button.hidden = false;
  });
  document.addEventListener('click', function (event) {
    var button = event.target.closest && event.target.closest('[data-install-app]');
    if (!button || !deferred) return;
    deferred.prompt();
    deferred.userChoice.then(function () {
      deferred = null;
      document.documentElement.removeAttribute('data-installable');
      button.hidden = true;
    });
  });

  window.addEventListener('appinstalled', function () {
    document.documentElement.setAttribute('data-installed', '1');
  });
})();
