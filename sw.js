/* The installable app's service worker. Deliberately conservative: every
   request goes to the network first, so the app is never staler than the
   site. The cache is only a fallback for when there is no connection, which
   is when a driver in a car park needs it most.

   Never cached: other hosts (map tiles, analytics, ads, fonts), anything but
   GET. Map tiles are left to the browser's own HTTP cache; storing them here
   would be bulk tile caching, which OpenStreetMap's tile policy forbids.

   To retire it, bump VERSION and delete the fetch handler: old caches go on
   activate and the browser picks up the new file within a day. */
var VERSION = 'v2-20261023';
var CACHE = 'cp-' + VERSION;
/* the extensionless URL: Cloudflare redirects the .html one, and a cached
   redirect cannot answer a navigation */
var SHELL = ['/offline', '/ev-charging', '/search', '/site.css', '/favicon.svg', '/icons/icon-192.png'];
var MAX_ENTRIES = 120;   // pages and data files kept for offline use

self.addEventListener('install', function (e) {
  /* one at a time, failures ignored: addAll is all-or-nothing, and one moved
     URL would stop the worker installing at all */
  e.waitUntil(caches.open(CACHE).then(function (c) {
    return Promise.all(SHELL.map(function (u) { return c.add(u).catch(function () {}); }));
  }).then(function () { return self.skipWaiting(); }));
});

self.addEventListener('activate', function (e) {
  e.waitUntil(caches.keys().then(function (keys) {
    return Promise.all(keys.filter(function (k) { return k.indexOf('cp-') === 0 && k !== CACHE; })
                           .map(function (k) { return caches.delete(k); }));
  }).then(function () { return self.clients.claim(); }));
});

function trim(c) {
  return c.keys().then(function (keys) {
    if (keys.length <= MAX_ENTRIES) return;
    return Promise.all(keys.slice(0, keys.length - MAX_ENTRIES).map(function (k) { return c.delete(k); }));
  });
}

self.addEventListener('fetch', function (e) {
  var req = e.request;
  if (req.method !== 'GET') return;
  var url = new URL(req.url);
  if (url.origin !== self.location.origin) return;

  e.respondWith(fetch(req).then(function (res) {
    if (res.ok && res.type === 'basic') {
      var copy = res.clone();
      caches.open(CACHE).then(function (c) { return c.put(req, copy).then(function () { return trim(c); }); });
    }
    return res;
  }).catch(function () {
    return caches.match(req, { ignoreSearch: req.mode === 'navigate' }).then(function (hit) {
      if (hit) return hit;
      if (req.mode === 'navigate') return caches.match('/offline');
      return Response.error();
    });
  }));
});
