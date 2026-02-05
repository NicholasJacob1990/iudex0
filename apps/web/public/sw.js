/**
 * Service Worker — Iudex
 *
 * Estratégias:
 *   - Cache-first  : assets estáticos (JS, CSS, fonts, imagens)
 *   - Network-first : chamadas de API
 *   - Stale-while-revalidate : dados de API não-críticos (catalogs, stats)
 *   - Offline fallback : página offline quando sem rede
 */

// Bump this to force clients to drop old cached _next assets when UI changes.
const CACHE_VERSION = 'iudex-v3';
const STATIC_CACHE = `${CACHE_VERSION}-static`;
const API_CACHE = `${CACHE_VERSION}-api`;
const OFFLINE_URL = '/offline.html';

// Assets para pre-cache na instalação
const PRECACHE_URLS = [OFFLINE_URL];

// ─── Helpers ────────────────────────────────────────────────────────

function isStaticAsset(url) {
  return (
    url.pathname.startsWith('/_next/static/') ||
    url.pathname.startsWith('/fonts/') ||
    url.pathname.startsWith('/logos/') ||
    url.pathname.startsWith('/images/') ||
    /\.(js|css|woff2?|ttf|otf|png|jpg|jpeg|gif|svg|ico|webp)$/.test(url.pathname)
  );
}

function isApiCall(url) {
  return url.pathname.startsWith('/api/');
}

function isSSEEndpoint(url) {
  return (
    url.pathname.includes('/stream') ||
    url.pathname.includes('/sse') ||
    url.pathname.includes('/chat/') ||
    url.searchParams.has('stream')
  );
}

function isNavigationRequest(request) {
  return request.mode === 'navigate';
}

function isSWRApiCall(url) {
  return (
    url.pathname.includes('/catalog') ||
    url.pathname.includes('/stats') ||
    url.pathname.includes('/playbooks') && !url.pathname.includes('/analyze')
  );
}

// ─── Install ────────────────────────────────────────────────────────

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(STATIC_CACHE).then((cache) => cache.addAll(PRECACHE_URLS))
  );
  // Ativar imediatamente sem esperar tabs fecharem
  self.skipWaiting();
});

// ─── Activate ───────────────────────────────────────────────────────

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((key) => key.startsWith('iudex-') && key !== STATIC_CACHE && key !== API_CACHE)
          .map((key) => caches.delete(key))
      )
    )
  );
  // Tomar controle de todas as tabs imediatamente
  self.clients.claim();
});

// ─── Fetch ──────────────────────────────────────────────────────────

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // Ignorar requests que não são GET
  if (event.request.method !== 'GET') return;

  // Não interferir em ambientes locais (dev/staging local). Um SW “preso” no browser
  // pode quebrar HMR e deixar a UI sem CSS/JS.
  if (url.hostname === 'localhost' || url.hostname === '127.0.0.1') return;

  // Ignorar SSE/streaming endpoints
  if (isSSEEndpoint(url)) return;

  // 1) Assets estáticos → Cache-first
  if (isStaticAsset(url)) {
    event.respondWith(cacheFirst(event.request, STATIC_CACHE));
    return;
  }

  // 2) API calls com SWR (catálogos, stats) → Stale-while-revalidate
  if (isApiCall(url) && isSWRApiCall(url)) {
    event.respondWith(staleWhileRevalidate(event.request, API_CACHE));
    return;
  }

  // 3) Outras API calls → Network-first
  if (isApiCall(url)) {
    event.respondWith(networkFirst(event.request, API_CACHE));
    return;
  }

  // 4) Navegação → Network-first com fallback offline
  if (isNavigationRequest(event.request)) {
    event.respondWith(
      fetch(event.request).catch(() => caches.match(OFFLINE_URL))
    );
    return;
  }
});

// ─── Estratégias de Cache ───────────────────────────────────────────

async function cacheFirst(request, cacheName) {
  const cached = await caches.match(request);
  if (cached) return cached;

  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(cacheName);
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    return new Response('', { status: 503, statusText: 'Service Unavailable' });
  }
}

async function networkFirst(request, cacheName) {
  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(cacheName);
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    const cached = await caches.match(request);
    return cached || new Response('{"error":"offline"}', {
      status: 503,
      headers: { 'Content-Type': 'application/json' },
    });
  }
}

async function staleWhileRevalidate(request, cacheName) {
  const cache = await caches.open(cacheName);
  const cached = await cache.match(request);

  const fetchPromise = fetch(request)
    .then((response) => {
      if (response.ok) {
        cache.put(request, response.clone());
      }
      return response;
    })
    .catch(() => cached);

  return cached || fetchPromise;
}

// ─── Messages ───────────────────────────────────────────────────────

self.addEventListener('message', (event) => {
  if (event.data === 'skipWaiting') {
    self.skipWaiting();
  }

  if (event.data === 'clearCaches') {
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k.startsWith('iudex-')).map((k) => caches.delete(k)))
    );
  }
});
