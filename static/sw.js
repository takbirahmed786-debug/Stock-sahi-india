// Offline app shell only. NEVER store reports or price quotes in the service-worker cache.
const CACHE = 'stocksahi-shell-v5';
const APP_SHELL = ['/', '/static/style.css', '/static/app.js', '/static/manifest.webmanifest', '/static/icon-192.png', '/static/icon-512.png'];
self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(APP_SHELL)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener('fetch', e => {
  const req=e.request;
  if (req.method !== 'GET') return;
  const url=new URL(req.url);
  if (url.origin !== self.location.origin) return;
  // No stale financial reports are ever delivered offline.
  if (url.pathname.startsWith('/api/')) return;
  if (url.pathname === '/' || url.pathname.startsWith('/static/')) {
    e.respondWith(fetch(req).then(response => {
      if(response.ok) {
        const clone=response.clone();
        e.waitUntil(caches.open(CACHE).then(c => c.put(req, clone)));
      }
      return response;
    }).catch(() => caches.match(req)));
  }
});
