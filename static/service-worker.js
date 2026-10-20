const CACHE = 'neighbouraid-static-v1';
const STATIC = ['/static/css/site.css','/static/js/app.js','/static/manifest.webmanifest','/static/icons/icon-192.svg','/static/icons/icon-512.svg','/offline/'];
self.addEventListener('install', event => event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(STATIC))));
self.addEventListener('activate', event => event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(key => key !== CACHE).map(key => caches.delete(key))))));
self.addEventListener('fetch', event => {
  const request = event.request; const url = new URL(request.url);
  if (request.method !== 'GET' || url.origin !== location.origin || url.pathname.startsWith('/api/') || url.pathname.startsWith('/admin/') || url.pathname.startsWith('/incidents/') || url.pathname.startsWith('/dashboard/') || url.pathname.startsWith('/notifications/')) return;
  if (url.pathname.startsWith('/static/')) event.respondWith(caches.match(request).then(cached => cached || fetch(request)));
  else if (request.mode === 'navigate') event.respondWith(fetch(request).catch(() => caches.match('/offline/')));
});
