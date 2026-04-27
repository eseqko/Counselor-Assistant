const CACHE = 'counselor-shell-v2';
// CSS/JS are versioned via ?v=<mtime> query strings from the server, so we
// don't pre-cache them here — stale copies were being served after updates.
const SHELL = [
  '/static/manifest.json'
];

self.addEventListener('install', e => {
  self.skipWaiting();
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)));
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', e => {
  if (e.request.method !== 'GET') return;
  const url = new URL(e.request.url);
  if (!url.pathname.startsWith('/static/')) return;
  e.respondWith(fetch(e.request).catch(() => caches.match(e.request)));
});
