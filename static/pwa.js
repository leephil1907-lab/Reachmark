/* PWA plumbing: service-worker registration, install prompt, and an offline notice.

   Deliberately small and dependency-free. Nothing here fetches data, and nothing here
   pretends stale content is live: if the browser is offline, the page says so.

   Install: Chrome/Edge fire `beforeinstallprompt`. We only capture that event on pages
   that actually have an Install button (`[data-install-app]`). Everywhere else the
   browser keeps its own install UI — stealing it on the homepage was why “Get the app”
   looked like a broken download. There is no App Store / Play Store package. */
(function () {
  'use strict';
  var T_ = (typeof T === 'function') ? T : function (k, f) { return f; };
  var ua = navigator.userAgent || '';
  var isIOS = /iphone|ipad|ipod/i.test(ua) ||
    (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  var isAndroid = /android/i.test(ua);
  var isChromium = /(chrome|crios|edg|edgios|brave)/i.test(ua) &&
    !/(fxios|firefox|opr\/|opera)/i.test(ua);
  var standalone = window.matchMedia('(display-mode: standalone)').matches ||
    window.navigator.standalone === true;
  var hasInstallButton = !!document.querySelector('[data-install-app]');

  var platform = 'other';
  if (standalone) platform = 'installed';
  else if (isIOS) platform = 'ios';
  else if (isAndroid) platform = 'android';
  else if (isChromium) platform = 'desktop';
  document.documentElement.setAttribute('data-platform', platform);
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
    var register = function () {
      return navigator.serviceWorker.register('/sw.js', { scope: '/' }).then(function (registration) {
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
        return registration;
      }).catch(function () {
        return navigator.serviceWorker.register('/static/sw.js', { scope: '/' }).catch(function () { return null; });
      });
    };
    /* Register immediately so /app can become installable on this visit, not the next. */
    register();
  }

  var deferred = null;
  var pendingClick = false;

  function setButtonLabel(kind) {
    document.querySelectorAll('[data-install-app]').forEach(function (button) {
      if (kind === 'installed') {
        button.hidden = true;
        return;
      }
      button.hidden = false;
      if (kind === 'ios') {
        button.textContent = T_('app.add_home', 'Add to Home Screen');
      } else if (kind === 'ready') {
        button.textContent = T_('app.install', 'Install Reachmark');
      } else {
        button.textContent = T_('app.install', 'Install Reachmark');
      }
    });
    var status = document.getElementById('install-status');
    if (!status) return;
    if (kind === 'installed') status.textContent = T_('app.installed', 'Reachmark is installed on this device. Open it from your home screen or app list.');
    else if (kind === 'ready') status.textContent = T_('app.ready', 'Your browser can install Reachmark now. Tap Install and confirm.');
    else if (kind === 'ios') status.textContent = T_('app.how_ios_status', 'iPhone cannot download an app file. Use Share → Add to Home Screen.');
    else if (kind === 'android') status.textContent = T_('app.how_android_status', 'On Android Chrome: tap Install, or the menu → Install app. There is no Play Store listing.');
    else if (kind === 'desktop') status.textContent = T_('app.how_desktop_status', 'Chrome and Edge can install this site as an app. Look for the install icon in the address bar, or tap Install when it lights up.');
    else status.textContent = T_('app.how_other_status', 'This browser cannot install apps. Open this page in Chrome or Edge, or keep using the website.');
  }

  function promptInstall() {
    if (!deferred) return Promise.resolve(false);
    var ev = deferred;
    deferred = null;
    return ev.prompt().then(function () {
      return ev.userChoice;
    }).then(function (choice) {
      document.documentElement.removeAttribute('data-installable');
      if (choice && choice.outcome === 'accepted') {
        document.documentElement.setAttribute('data-installed', '1');
        document.documentElement.setAttribute('data-platform', 'installed');
        setButtonLabel('installed');
      } else {
        setButtonLabel(platform);
      }
      return true;
    }).catch(function () {
      setButtonLabel(platform);
      return false;
    });
  }

  if (standalone) {
    setButtonLabel('installed');
  } else if (isIOS) {
    document.documentElement.setAttribute('data-show-ios', '1');
    setButtonLabel('ios');
  } else if (isAndroid) {
    setButtonLabel('android');
  } else if (isChromium) {
    setButtonLabel('desktop');
  } else {
    setButtonLabel('other');
  }

  window.addEventListener('beforeinstallprompt', function (event) {
    /* Pages without an Install button must keep Chrome’s native UI. Capturing the
       event on the homepage hid the Android install bar and left Get the app empty. */
    if (!hasInstallButton) return;
    event.preventDefault();
    deferred = event;
    document.documentElement.setAttribute('data-installable', '1');
    setButtonLabel('ready');
    if (pendingClick) {
      pendingClick = false;
      promptInstall();
    }
  });

  document.addEventListener('click', function (event) {
    var button = event.target.closest && event.target.closest('[data-install-app]');
    if (!button) return;
    event.preventDefault();
    if (deferred) {
      promptInstall();
      return;
    }
    pendingClick = true;
    if (location.pathname !== '/app') {
      location.href = '/app';
      return;
    }
    document.documentElement.setAttribute('data-show-how', '1');
    if (isIOS) document.documentElement.setAttribute('data-show-ios', '1');
    var how = document.getElementById('install-how');
    if (how) how.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  });

  window.addEventListener('appinstalled', function () {
    deferred = null;
    pendingClick = false;
    document.documentElement.setAttribute('data-installed', '1');
    document.documentElement.setAttribute('data-platform', 'installed');
    setButtonLabel('installed');
  });
})();
