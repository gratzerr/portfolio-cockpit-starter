/* network-first for page loads: a cached index.html must never stick (iOS
   home-screen apps pin HTML aggressively). Falls back to cache only offline. */
const C = 'pc-v1';
self.addEventListener('install', e => self.skipWaiting());
self.addEventListener('activate', e => e.waitUntil(clients.claim()));
self.addEventListener('fetch', e => {
  const r = e.request;
  if (r.mode === 'navigate') {
    e.respondWith(
      fetch(r).then(res => {
        const cp = res.clone();
        caches.open(C).then(c => c.put(r, cp));
        return res;
      }).catch(() => caches.match(r))
    );
  }
});
