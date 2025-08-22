// sw.js
/* Minimal offline support with cache versioning and safe defaults */
const CACHE_VER = 'pangram-aid-v3';
const CORE_ASSETS = ['/', './', './index.html', './config.json'];

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

  // Network-first for config.json to avoid stale alphabet; cache-first otherwise.
  if (new URL(request.url).pathname.endsWith('/config.json')) {
    e.respondWith((async () => {
      try {
        const fresh = await fetch(request);
        const cache = await caches.open(CACHE_VER);
        cache.put(request, fresh.clone());
        return fresh;
      } catch {
        const cached = await caches.match(request);
        return cached || new Response('{"letters":"","locale":"pl-PL"}', { headers: { 'Content-Type':'application/json' }});
      }
    })());
    return;
  }

  e.respondWith((async () => {
    const cached = await caches.match(request);
    if (cached) return cached;
    try {
      const net = await fetch(request);
      const cache = await caches.open(CACHE_VER);
      // Only cache GET same-origin.
      if (request.method === 'GET' && new URL(request.url).origin === location.origin) {
        cache.put(request, net.clone());
      }
      return net;
    } catch {
      return cached || new Response('Offline', { status: 503, statusText: 'Offline' });
    }
  })());
});
