/*
 * COS Tesla service worker — hand-rolled, no libraries.
 *
 * Interception rule (locked by Phase 1 directive): same-origin GET only,
 * with explicit bypass of /api/*, /.auth/*, /.well-known/*, and /sw.js.
 * All cross-origin traffic (summitos-api, Google Maps, Esri tiles, unpkg,
 * Nominatim, Stripe, Microsoft login) passes through untouched.
 *
 * Bump CACHE_VERSION on ANY change to this file — activation deletes
 * every cache that doesn't match the current version.
 */
const CACHE_VERSION = 'costesla-pwa-v1';
const OFFLINE_URL = '/offline.html';
const PRECACHE_URLS = [OFFLINE_URL, '/manifest.json', '/icons/icon-192.png', '/logo.png'];

self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_VERSION)
            .then((cache) => cache.addAll(PRECACHE_URLS))
            .then(() => self.skipWaiting())
    );
});

self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys()
            .then((keys) => Promise.all(
                keys.filter((key) => key !== CACHE_VERSION).map((key) => caches.delete(key))
            ))
            .then(() => self.clients.claim())
    );
});

function bypassed(request, url) {
    if (request.method !== 'GET') return true;
    if (url.origin !== self.location.origin) return true;
    if (url.pathname.startsWith('/api/')) return true;
    if (url.pathname.startsWith('/.auth/')) return true;
    if (url.pathname.startsWith('/.well-known/')) return true;
    if (url.pathname === '/sw.js') return true;
    return false;
}

function cacheable(response) {
    return response
        && response.status === 200
        && response.type === 'basic'
        && response.headers.get('Vary') !== '*';
}

self.addEventListener('fetch', (event) => {
    const url = new URL(event.request.url);
    if (bypassed(event.request, url)) return;

    // Navigations: network-first; offline shows the precached fallback page.
    // HTML documents are never stored, so deploys are picked up immediately.
    if (event.request.mode === 'navigate') {
        event.respondWith(
            fetch(event.request).catch(() => caches.match(OFFLINE_URL))
        );
        return;
    }

    // Hashed build assets are immutable; static assets are cached per version.
    const immutable = url.pathname.startsWith('/_next/static/');
    const staticAsset = url.pathname.startsWith('/icons/')
        || /\.(png|jpg|jpeg|svg|gif|ico|webp|woff2?)$/.test(url.pathname);

    if (immutable || staticAsset) {
        event.respondWith(
            caches.match(event.request).then((hit) => {
                if (hit) return hit;
                return fetch(event.request).then((response) => {
                    if (cacheable(response)) {
                        const copy = response.clone();
                        caches.open(CACHE_VERSION).then((cache) => cache.put(event.request, copy));
                    }
                    return response;
                });
            })
        );
    }
    // Anything else same-origin: default browser behavior (no respondWith).
});
