/* Minimal shell cache — no offline streaming.
 *
 * The HTML shell (/player) references a content-hashed JS/CSS bundle
 * (e.g. /assets/index-XXXX.js). Caching that HTML cache-first meant a
 * browser with this worker already installed would keep serving an old
 * shell pointing at a bundle hash that no longer exists after a new
 * deploy — the app would fail to load with a 404 until the cache was
 * manually cleared. Go network-first for the shell itself so a new
 * deploy is picked up immediately; only fall back to the cached shell
 * when actually offline. Hashed asset files are still safe to serve
 * cache-first, since their URL itself changes when their content does.
 */
const CACHE = 'musicarr-player-shell-v4'
const SHELL_URL = '/player'
// Explicit "download for offline" audio cache, written directly by the page
// (offlineCache.ts) via the Cache API — not by this worker. Kept as its own
// cache name so the shell-cache cleanup in `activate` never touches tracks
// a listener deliberately downloaded.
const TRACKS_CACHE = 'musicarr-offline-tracks-v1'

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches
      .open(CACHE)
      .then((c) =>
        c.addAll([
          SHELL_URL,
          '/manifest.webmanifest',
          '/favicon.svg',
          '/icon-192.png',
          '/icon-512.png',
        ]),
      )
      .then(() => self.skipWaiting()),
  )
})

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys.filter((k) => k !== CACHE && k !== TRACKS_CACHE).map((k) => caches.delete(k)),
      ),
    ).then(() => self.clients.claim()),
  )
})

self.addEventListener('fetch', (event) => {
  const req = event.request
  if (req.method !== 'GET') return
  const url = new URL(req.url)

  // A track downloaded for offline listening (offlineCache.ts wrote it into
  // TRACKS_CACHE directly) — serve it straight from cache, online or not.
  // Cache.match ignores request headers like Range by default, matching
  // purely on URL, so a <audio> element's ranged seek request still finds
  // the cached full response.
  if (url.pathname.startsWith('/api/player/stream/')) {
    event.respondWith(
      caches.open(TRACKS_CACHE).then((c) => c.match(req)).then((hit) => hit || fetch(req)),
    )
    return
  }

  if (url.pathname.startsWith('/api/')) return

  // This worker now registers for the whole origin (not just /player), so
  // it can receive push events on admin pages too. A bare `req.mode ===
  // 'navigate'` check here would treat *any* navigation — including the
  // admin app's own routes — as "the player shell", cache that admin page's
  // HTML under the SHELL_URL key, and later serve it back in place of the
  // real player shell (or vice versa) whenever offline. Scope this to
  // actual /player navigations only.
  const isShell = url.pathname === SHELL_URL || (req.mode === 'navigate' && url.pathname.startsWith('/player'))
  if (isShell) {
    event.respondWith(
      fetch(req)
        .then((res) => {
          caches.open(CACHE).then((c) => c.put(SHELL_URL, res.clone()))
          return res
        })
        .catch(() => caches.match(SHELL_URL)),
    )
    return
  }

  event.respondWith(
    caches.match(req).then((hit) => hit || fetch(req).catch(() => caches.match(SHELL_URL))),
  )
})

self.addEventListener('push', (event) => {
  let payload = { title: 'Musicarr', body: '' }
  try {
    if (event.data) payload = { ...payload, ...event.data.json() }
  } catch {
    /* ignore malformed payload */
  }
  event.waitUntil(
    self.registration.showNotification(payload.title || 'Musicarr', {
      body: payload.body || '',
      icon: '/icon-192.png',
      badge: '/icon-192.png',
      data: { url: payload.url || '/' },
    }),
  )
})

self.addEventListener('notificationclick', (event) => {
  event.notification.close()
  const url = (event.notification.data && event.notification.data.url) || '/'
  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((list) => {
      for (const client of list) {
        if (client.url.includes(url) && 'focus' in client) return client.focus()
      }
      if (self.clients.openWindow) return self.clients.openWindow(url)
    }),
  )
})
