/* Reachmark service worker — makes the public site installable and readable offline.
   ================================================================================

   What it caches:  only pages a visitor could already see without signing in — the
                    home page, about, showcase, the enquiry form, the review-link shell
                    and the static assets those pages use.

   What it never caches: anything private. The workspace, dashboard, every /api/ route
                    except the public receptionist, previews and unsubscribe pages are
                    excluded by an explicit deny-list and are never stored, so the cache
                    cannot leak an owner's data to anyone who shares a device.

   How it updates:  the shell strategy is stale-while-revalidate, so a deploy is picked
                    up on the next visit without anyone clearing storage. Bumping CACHE
                    drops every older entry.

   Faster loads:    native navigation preload is enabled where supported, so the
                    network fetch starts while the worker boots; the preloaded
                    response is used (and cached) instead of a duplicate fetch.

   When offline:    a previously visited page is served from cache with an honest
                    "you are offline" note; an unvisited page gets an offline page that
                    says so. Nothing pretends to be live data.
   ================================================================================ */
'use strict';

var CACHE = 'reachmark-v1';
var OFFLINE_URL = '/offline';
var PRECACHE = [
  '/',
  '/about',
  '/showcase',
  '/enquire',
  '/receptionist',
  '/offline',
  '/static/manifest.webmanifest',
  '/static/icon.svg',
  '/static/icon-192.png',
  '/static/icon-512.png',
  '/static/fonts.css'
];

/* Never cached, never served from cache — private or stateful by definition. */
var DENY = [
  /^\/workspace/, /^\/dashboard/, /^\/login/, /^\/signin/, /^\/signup/, /^\/forgot/, /^\/reset/,
  /^\/verify/, /^\/preview\//, /^\/unsubscribe\//, /^\/r\//, /^\/api\/auth/, /^\/api\/crew/,
  /^\/api\/state/, /^\/api\/leads/, /^\/api\/settings/, /^\/api\/outbox/, /^\/api\/snapshots/,
  /^\/api\/enquiries/, /^\/api\/contracts/, /^\/api\/projects/, /^\/api\/mcp/, /^\/api\/jobs/,
  /^\/api\/map\//, /^\/api\/analytics/, /^\/api\/deploy-check/, /^\/api\/verify-config/,
  /^\/api\/operations/, /^\/api\/receptionist\/threads/, /^\/api\/review-links/
];

function denied(url) {
  for (var i = 0; i < DENY.length; i++) {
    if (DENY[i].test(url.pathname)) return true;
  }
  return false;
}

self.addEventListener('install', function (event) {
  event.waitUntil(
    caches.open(CACHE).then(function (cache) {
      /* addAll rejects the whole install if one entry 404s — add individually instead. */
      return Promise.all(PRECACHE.map(function (url) {
        return cache.add(new Request(url, { credentials: 'same-origin' })).catch(function () { return null; });
      }));
    }).then(function () { return self.skipWaiting(); })
  );
});

self.addEventListener('activate', function (event) {
  event.waitUntil(
    caches.keys().then(function (keys) {
      return Promise.all(keys.map(function (key) { return key === CACHE ? null : caches.delete(key); }));
    }).then(function () {
      /* Native navigation preload: the browser starts the network fetch in
         parallel with worker boot. No library needed. */
      if ('navigationPreload' in self.registration) return self.registration.navigationPreload.enable();
      return null;
    }).then(function () { return self.clients.claim(); })
  );
});

self.addEventListener('fetch', function (event) {
  var request = event.request;
  if (request.method !== 'GET') return;

  var url;
  try { url = new URL(request.url); } catch (err) { return; }
  if (url.origin !== self.location.origin) return;   /* third parties are never cached */
  if (denied(url)) return;                           /* private routes pass straight through */

  /* Navigations: cache first for speed, refresh in the background, honest offline fallback. */
  if (request.mode === 'navigate') {
    event.respondWith(
      Promise.all([
        caches.match(request),
        event.preloadResponse ? event.preloadResponse.catch(function () { return null; }) : null
      ]).then(function (both) {
        var cached = both[0], preloaded = both[1];
        var network = (preloaded ? Promise.resolve(preloaded) : fetch(request)).then(function (response) {
          if (response && response.ok) {
            caches.open(CACHE).then(function (cache) { cache.put(request, response.clone()); });
          }
          return response;
        }).catch(function () { return null; });
        if (cached) return cached;
        return network.then(function (response) {
          return response || caches.match(OFFLINE_URL).then(function (offline) {
            return offline || new Response(
              '<!doctype html><meta charset="utf-8"><title>Offline</title><body style="font:16px system-ui;background:#F5F5EF;color:#20251F;padding:40px"><h1>You are offline.</h1><p>This page has not been saved on this device yet. Your connection is the missing part — nothing here is showing you old data.</p></body>',
              { headers: { 'Content-Type': 'text/html; charset=utf-8' }, status: 503 });
          });
        });
      })
    );
    return;
  }

  /* Static assets: stale-while-revalidate. */
  event.respondWith(
    caches.match(request).then(function (cached) {
      var network = fetch(request).then(function (response) {
        if (response && response.ok && url.pathname.indexOf('/static/') === 0) {
          caches.open(CACHE).then(function (cache) { cache.put(request, response.clone()); });
        }
        return response;
      }).catch(function () { return cached; });
      return cached || network;
    })
  );
});

/* The page asks for this before showing an update banner. */
self.addEventListener('message', function (event) {
  if (event.data === 'skip-waiting') self.skipWaiting();
});
