/* Offline support with cache versioning and safe defaults */
const CACHE_VER = 'pangram-aid-v4';
const CORE_ASSETS = ['/', './', './index.html', './config.json', './sw.js'];

self.addEventListener('install', (e) => {
  e.waitUntil((async () => {
    const c = await caches.open(CACHE_VER);
    await c.addAll(CORE_ASSETS);
    await self.skipWaiting();
  })());
});

self.addEventListener('activate', (e) => {
  e.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(keys.filter(k => k !== CACHE_VER).map(k => caches.delete(k)));
    await self.clients.claim();
  })());
});

self.addEventListener('fetch', (e) => {
  const { request } = e;
  const url = new URL(request.url);

  // Only handle same-origin requests to avoid caching 3rd-party unintentionally
  if (url.origin !== location.origin) return;

  // Network-first for config.json to avoid stale alphabet/locale
  if (url.pathname.endsWith('/config.json')) {
    e.respondWith((async () => {
      try {
        const fresh = await fetch(request, { cache: 'no-store' });
        const cache = await caches.open(CACHE_VER);
        cache.put(request, fresh.clone());
        return fresh;
      } catch {
        const cached = await caches.match(request);
        return cached || new Response('{"letters":"","locale":"pl-PL"}', {
          headers: { 'Content-Type': 'application/json; charset=utf-8' }
        });
      }
    })());
    return;
  }

  // Cache-first for everything else (HTML, SW, assets)
  e.respondWith((async () => {
    const cached = await caches.match(request, { ignoreSearch: true });
    if (cached) return cached;
    try {
      const net = await fetch(request);
      const cache = await caches.open(CACHE_VER);
      if (request.method === 'GET') cache.put(request, net.clone());
      return net;
    } catch {
      // Fallback to cached root for navigation requests
      if (request.mode === 'navigate') {
        const offline = await caches.match('./index.html');
        if (offline) return offline;
      }
      return new Response('Offline', { status: 503, statusText: 'Offline' });
    }
  })());
});