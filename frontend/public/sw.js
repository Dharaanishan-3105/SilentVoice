/**
 * SilentVoice Service Worker — Offline Support
 *
 * Caches essential assets and vocabulary for offline use.
 * Emergency mode and basic sign recognition work without internet.
 */

const CACHE_NAME = "silentvoice-v2";
const OFFLINE_URLS = [
    "/app",
    "/",
    "/login",
    "/register",
];

// Install: cache shell
self.addEventListener("install", (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) => {
            return cache.addAll(OFFLINE_URLS);
        })
    );
    self.skipWaiting();
});

// Activate: clean old caches
self.addEventListener("activate", (event) => {
    event.waitUntil(
        caches.keys().then((keys) =>
            Promise.all(
                keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k))
            )
        )
    );
    self.clients.claim();
});

// Fetch: network-first, fall back to cache
self.addEventListener("fetch", (event) => {
    // Skip non-GET requests and WebSocket
    if (event.request.method !== "GET") return;
    if (event.request.url.includes("/ws/")) return;

    event.respondWith(
        fetch(event.request)
            .then((response) => {
                // Cache successful responses
                const clone = response.clone();
                caches.open(CACHE_NAME).then((cache) => {
                    cache.put(event.request, clone);
                });
                return response;
            })
            .catch(() => {
                // Offline: serve from cache
                return caches.match(event.request).then((cached) => {
                    return cached || new Response("Offline", { status: 503 });
                });
            })
    );
});
