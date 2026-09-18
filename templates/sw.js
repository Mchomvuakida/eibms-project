const CACHE_NAME = 'eibms-static-v1';

self.addEventListener('install', event => {
  self.skipWaiting();
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(names =>
      Promise.all(
        names.filter(n => n !== CACHE_NAME).map(n => caches.delete(n))
      )
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', event => {
  const req = event.request;

  // Never touch anything but simple GETs.
  if (req.method !== 'GET') return;

  const url = new URL(req.url);

  // Only cache our own static assets. Everything else (pages, forms,
  // API data) always goes straight to the network so figures are never stale.
  const isStaticAsset =
    url.origin === self.location.origin && url.pathname.startsWith('/static/');

  if (!isStaticAsset) return;

  event.respondWith(
    caches.match(req).then(cached => {
      const fetchAndCache = fetch(req).then(res => {
        if (res && res.status === 200) {
          const copy = res.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(req, copy));
        }
        return res;
      }).catch(() => cached);

      return cached || fetchAndCache;
    })
  );
});