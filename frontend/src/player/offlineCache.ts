import { playerApi, type PlayerTrack } from './playerApi'

// Must match sw.js's TRACKS_CACHE name exactly — this module writes the
// cache directly from the page (simpler than message-passing to the
// worker), and sw.js's fetch handler reads from the same cache to serve a
// downloaded track's stream request whether online or offline.
const TRACKS_CACHE = 'musicarr-offline-tracks-v1'
const MANIFEST_KEY = 'musicarr-offline-manifest'

export type OfflineTrackMeta = {
  id: number
  title: string
  artist_name: string
  album_title: string
  cover_url: string | null
  duration: number
  bytes: number
  cached_at: number
}

function readManifest(): OfflineTrackMeta[] {
  try {
    const raw = localStorage.getItem(MANIFEST_KEY)
    return raw ? JSON.parse(raw) : []
  } catch {
    return []
  }
}

function writeManifest(list: OfflineTrackMeta[]) {
  try {
    localStorage.setItem(MANIFEST_KEY, JSON.stringify(list))
  } catch {
    /* storage full or unavailable — offline downloads just won't persist across reloads */
  }
}

export function isOfflineSupported(): boolean {
  return typeof caches !== 'undefined' && 'serviceWorker' in navigator
}

export function listOfflineTracks(): OfflineTrackMeta[] {
  return readManifest().sort((a, b) => b.cached_at - a.cached_at)
}

export function isTrackOffline(trackId: number): boolean {
  return readManifest().some((t) => t.id === trackId)
}

export async function downloadTrackForOffline(track: PlayerTrack): Promise<void> {
  const url = playerApi.streamUrl(track.id)
  const res = await fetch(url)
  if (!res.ok) throw new Error('Could not download this track for offline listening')
  const bytes = Number(res.headers.get('content-length') || 0)
  const cache = await caches.open(TRACKS_CACHE)
  await cache.put(url, res.clone())
  const manifest = readManifest().filter((t) => t.id !== track.id)
  manifest.push({
    id: track.id,
    title: track.title,
    artist_name: track.artist_name,
    album_title: track.album_title,
    cover_url: track.cover_url,
    duration: track.duration,
    bytes,
    cached_at: Date.now(),
  })
  writeManifest(manifest)
}

export async function removeOfflineTrack(trackId: number): Promise<void> {
  const cache = await caches.open(TRACKS_CACHE)
  await cache.delete(playerApi.streamUrl(trackId))
  writeManifest(readManifest().filter((t) => t.id !== trackId))
}

export async function clearAllOfflineTracks(): Promise<void> {
  await caches.delete(TRACKS_CACHE)
  writeManifest([])
}

export async function storageEstimate(): Promise<{ usage: number; quota: number } | null> {
  if (!navigator.storage?.estimate) return null
  const est = await navigator.storage.estimate()
  return { usage: est.usage || 0, quota: est.quota || 0 }
}
