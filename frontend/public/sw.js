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
const CACHE = 'musicarr-player-shell-v3'
const SHELL_URL = '/player'

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
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))),
    ).then(() => self.clients.claim()),
  )
})

self.addEventListener('fetch', (event) => {
  const req = event.request
  if (req.method !== 'GET') return
  const url = new URL(req.url)
  if (url.pathname.startsWith('/api/')) return

  const isShell = req.mode === 'navigate' || url.pathname === SHELL_URL
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
