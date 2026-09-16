import { playerApi, type PlayerTrack } from './playerApi'

/** Minimal Google Cast Sender SDK typings — the SDK only exposes a global. */
declare global {
  interface Window {
    __onGCastApiAvailable?: (isAvailable: boolean) => void
    chrome?: {
      cast?: {
        AutoJoinPolicy: { ORIGIN_SCOPED: string }
        media?: {
          DEFAULT_MEDIA_RECEIVER_APP_ID: string
          MediaInfo: new (contentId: string, contentType: string) => unknown
          GenericMediaMetadata: new () => Record<string, unknown>
          MetadataType: { GENERIC: number }
          LoadRequest: new (mediaInfo: unknown) => unknown
        }
      }
    }
    cast?: {
      framework: {
        CastContext: { getInstance: () => CastContextLike }
        CastContextEventType: { SESSION_STATE_CHANGED: string }
        SessionState: { SESSION_ENDED: string; SESSION_STARTED: string; SESSION_RESUMED: string }
      }
    }
  }
}

type CastContextLike = {
  setOptions: (opts: Record<string, unknown>) => void
  requestSession: () => Promise<void>
  getCurrentSession: () => CastSessionLike | null
  addEventListener: (type: string, cb: (event: { sessionState: string }) => void) => void
}

type CastSessionLike = {
  loadMedia: (request: unknown) => Promise<void>
  endSession: (stopCasting: boolean) => void
}

let sdkLoadPromise: Promise<boolean> | null = null

function loadCastSdk(): Promise<boolean> {
  if (sdkLoadPromise) return sdkLoadPromise
  sdkLoadPromise = new Promise((resolve) => {
    if (window.cast?.framework) {
      resolve(true)
      return
    }
    window.__onGCastApiAvailable = (isAvailable: boolean) => {
      if (!isAvailable || !window.chrome?.cast || !window.cast?.framework) {
        resolve(false)
        return
      }
      window.cast.framework.CastContext.getInstance().setOptions({
        receiverApplicationId: window.chrome.cast.media?.DEFAULT_MEDIA_RECEIVER_APP_ID,
        autoJoinPolicy: window.chrome.cast.AutoJoinPolicy.ORIGIN_SCOPED,
      })
      resolve(true)
    }
    const script = document.createElement('script')
    script.src =
      'https://www.gstatic.com/cv/js/sender/v1/cast_sender.js?loadCastFramework=1'
    script.onerror = () => resolve(false)
    document.head.appendChild(script)
  })
  return sdkLoadPromise
}

export function chromecastSupported(): boolean {
  return typeof window !== 'undefined' && /Chrome/.test(navigator.userAgent) && !/Edg/.test(navigator.userAgent)
}

export function airplaySupported(): boolean {
  return typeof window !== 'undefined' && 'WebKitPlaybackTargetAvailabilityEvent' in window
}

export function showAirplayPicker(audio: HTMLAudioElement | null) {
  const el = audio as HTMLAudioElement & { webkitShowPlaybackTargetPicker?: () => void }
  el?.webkitShowPlaybackTargetPicker?.()
}

/** Cast the given track to whatever Chromecast device the user picks. Loads
 * the SDK lazily on first use. Re-call on each track change to follow the
 * queue; the browser's own cast overlay provides play/pause/volume controls
 * on the receiver once a session is active. */
export async function castTrack(track: PlayerTrack): Promise<boolean> {
  const ok = await loadCastSdk()
  if (!ok || !window.cast?.framework || !window.chrome?.cast?.media) return false
  const context = window.cast.framework.CastContext.getInstance()
  let session = context.getCurrentSession()
  if (!session) {
    await context.requestSession()
    session = context.getCurrentSession()
  }
  if (!session) return false

  const { token } = await playerApi.mintCastToken()
  const url = playerApi.castStreamUrl(token, track.id)
  const contentType =
    track.format === 'flac' ? 'audio/flac' : track.format === 'mp3' ? 'audio/mpeg' : 'audio/mp4'
  const mediaInfo = new window.chrome.cast.media.MediaInfo(url, contentType) as {
    metadata?: Record<string, unknown>
  }
  const metadata = new window.chrome.cast.media.GenericMediaMetadata()
  metadata.metadataType = window.chrome.cast.media.MetadataType.GENERIC
  metadata.title = track.title
  metadata.subtitle = track.artist_name
  if (track.cover_url) metadata.images = [{ url: track.cover_url }]
  mediaInfo.metadata = metadata
  const request = new window.chrome.cast.media.LoadRequest(mediaInfo)
  await session.loadMedia(request)
  return true
}

export function isCasting(): boolean {
  return !!window.cast?.framework?.CastContext.getInstance().getCurrentSession()
}

export function stopCasting() {
  window.cast?.framework?.CastContext.getInstance().getCurrentSession()?.endSession(true)
}

export function onCastSessionChanged(cb: (active: boolean) => void): () => void {
  let cancelled = false
  loadCastSdk().then((ok) => {
    if (!ok || cancelled || !window.cast?.framework) return
    const ctx = window.cast.framework.CastContext.getInstance()
    ctx.addEventListener(window.cast.framework.CastContextEventType.SESSION_STATE_CHANGED, (e) => {
      const active =
        e.sessionState === window.cast!.framework.SessionState.SESSION_STARTED ||
        e.sessionState === window.cast!.framework.SessionState.SESSION_RESUMED
      cb(active)
    })
  })
  return () => {
    cancelled = true
  }
}
