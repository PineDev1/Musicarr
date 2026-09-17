import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import { useQuery } from '@tanstack/react-query'
import { DEFAULT_PREFS, playerApi, type PlayerTrack } from './playerApi'

type RepeatMode = 'off' | 'all' | 'one'
type Slot = 'A' | 'B'

export type SleepMode = number | 'end'

/** Fired by keyboard shortcut `q`; WavyPlayBar listens and toggles the queue drawer. */
export const TOGGLE_QUEUE_EVENT = 'musicarr-toggle-queue'
/** Fired by keyboard shortcut `l`; WavyPlayBar listens and likes the current track. */
export const TOGGLE_LOVE_EVENT = 'musicarr-toggle-love'
/** Fired by keyboard shortcut `f`; ExpandedNowPlaying listens and toggles itself. */
export const TOGGLE_EXPANDED_EVENT = 'musicarr-toggle-expanded'

type QueueState = {
  tracks: PlayerTrack[]
  index: number
  playing: boolean
  shuffle: boolean
  repeat: RepeatMode
  currentTime: number
  duration: number
  volume: number
  muted: boolean
  analyser: AnalyserNode | null
  audioEl: HTMLAudioElement | null
  sourceLabel: string | null
  sleepMode: SleepMode | null
  sleepUntil: number | null
}

type QueueApi = QueueState & {
  playTracks: (
    tracks: PlayerTrack[],
    startIndex?: number,
    sourceLabel?: string,
    startAt?: number,
  ) => void
  playTrack: (
    track: PlayerTrack,
    queue?: PlayerTrack[],
    sourceLabel?: string,
    startAt?: number,
  ) => void
  addNext: (track: PlayerTrack) => void
  addEnd: (track: PlayerTrack) => void
  togglePlay: () => void
  next: () => void
  prev: () => void
  seek: (t: number) => void
  setVolume: (v: number) => void
  toggleMute: () => void
  toggleShuffle: () => void
  cycleRepeat: () => void
  clearQueue: () => void
  jumpTo: (index: number) => void
  removeAt: (index: number) => void
  reorder: (from: number, to: number) => void
  forceStop: () => void
  setSleepMinutes: (mode: SleepMode) => void
  clearSleep: () => void
}

const Ctx = createContext<QueueApi | null>(null)

const CROSSFADE_MS = 700
/** Start preloading the next track once this many seconds remain — long enough
 * on any reasonable connection to fully buffer before playback reaches it,
 * which is what makes the track-boundary swap gapless. */
const PRELOAD_LEAD_SECONDS = 15

function otherSlot(slot: Slot): Slot {
  return slot === 'A' ? 'B' : 'A'
}

function storageKey(userId: number | null) {
  return `musicarr-player-queue-v1-${userId ?? 'anon'}`
}

function applyMediaSession(track: PlayerTrack) {
  if (!('mediaSession' in navigator)) return
  try {
    navigator.mediaSession.metadata = new MediaMetadata({
      title: track.title,
      artist: track.artist_name,
      album: track.album_title,
      artwork: track.cover_url
        ? [{ src: track.cover_url, sizes: '512x512', type: 'image/jpeg' }]
        : [],
    })
  } catch {
    /* ignore */
  }
}

export function PlayerQueueProvider({
  userId,
  children,
}: {
  userId: number | null
  children: ReactNode
}) {
  // Two alternating <audio> elements so the next track can be fully preloaded
  // on the idle one before the current one ends — no network gap at the
  // boundary, and (when crossfade is enabled) a true overlapping fade instead
  // of a fade-through-silence on a single element.
  const audioRefs = useRef<Record<Slot, HTMLAudioElement | null>>({ A: null, B: null })
  const sourceRefs = useRef<Record<Slot, MediaElementAudioSourceNode | null>>({
    A: null,
    B: null,
  })
  const trackGainRefs = useRef<Record<Slot, GainNode | null>>({ A: null, B: null })
  const ctxRef = useRef<AudioContext | null>(null)
  const masterGainRef = useRef<GainNode | null>(null)
  const analyserRef = useRef<AnalyserNode | null>(null)
  const slotRef = useRef<Slot>('A')
  /** Track id currently buffered on the inactive slot, if any. */
  const preloadedTrackIdRef = useRef<number | null>(null)
  /** Set right before a gapless swap's setIndex() so the track-change effect
   * doesn't also reload the (already playing) newly-active element. */
  const swapInProgressRef = useRef(false)

  const [tracks, setTracks] = useState<PlayerTrack[]>([])
  const [index, setIndex] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [shuffle, setShuffle] = useState(false)
  const [repeat, setRepeat] = useState<RepeatMode>('off')
  const [currentTime, setCurrentTime] = useState(0)
  const [duration, setDuration] = useState(0)
  const [volume, setVolumeState] = useState(0.9)
  const [muted, setMuted] = useState(false)
  const [analyser, setAnalyser] = useState<AnalyserNode | null>(null)
  const [sourceLabel, setSourceLabel] = useState<string | null>(null)
  const [sleepMode, setSleepMode] = useState<SleepMode | null>(null)
  const [sleepUntil, setSleepUntil] = useState<number | null>(null)
  const orderRef = useRef<number[]>([])
  const skipAutoPlayRef = useRef(false)
  const volumeRef = useRef(volume)
  const mutedVolumeRef = useRef(volume)
  const sleepAtEndRef = useRef(false)
  const defaultsAppliedRef = useRef(false)
  const pendingSeekRef = useRef<number | null>(null)

  volumeRef.current = volume

  const prefsQ = useQuery({
    queryKey: ['player-prefs'],
    queryFn: playerApi.prefs,
    staleTime: 30_000,
  })
  const prefs = prefsQ.data || DEFAULT_PREFS
  const crossfadeRef = useRef(prefs.crossfade_enabled)
  crossfadeRef.current = prefs.crossfade_enabled

  const activeAudio = useCallback(() => audioRefs.current[slotRef.current], [])

  const ensureAudioGraph = useCallback(() => {
    if (!ctxRef.current) {
      const CtxAudio =
        window.AudioContext ||
        (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext
      ctxRef.current = new CtxAudio()
    }
    const ctx = ctxRef.current
    if (!masterGainRef.current) {
      const analyserNode = ctx.createAnalyser()
      analyserNode.fftSize = 64
      const master = ctx.createGain()
      master.gain.value = Math.max(0, Math.min(1, volumeRef.current))
      analyserNode.connect(master)
      master.connect(ctx.destination)
      analyserRef.current = analyserNode
      masterGainRef.current = master
      setAnalyser(analyserNode)
    }
    ;(['A', 'B'] as Slot[]).forEach((slot) => {
      const audio = audioRefs.current[slot]
      if (!audio || sourceRefs.current[slot]) return
      audio.volume = 1
      const src = ctx.createMediaElementSource(audio)
      const trackGain = ctx.createGain()
      trackGain.gain.value = slot === slotRef.current ? 1 : 0
      src.connect(trackGain)
      trackGain.connect(analyserRef.current!)
      sourceRefs.current[slot] = src
      trackGainRefs.current[slot] = trackGain
    })
  }, [])

  /** Ramp a single slot's gain from 0 to full — used for a fresh manual load
   * with crossfade enabled (no second source to overlap with yet). */
  const fadeInSlot = useCallback((slot: Slot) => {
    const gain = trackGainRefs.current[slot]
    const ctx = ctxRef.current
    if (!gain || !ctx) return
    const now = ctx.currentTime
    gain.gain.cancelScheduledValues(now)
    gain.gain.setValueAtTime(0, now)
    gain.gain.linearRampToValueAtTime(1, now + CROSSFADE_MS / 1000)
  }, [])

  /** True overlapping crossfade between the outgoing and incoming slots. */
  const crossfadeSwap = useCallback((fromSlot: Slot, toSlot: Slot) => {
    const ctx = ctxRef.current
    const outGain = trackGainRefs.current[fromSlot]
    const inGain = trackGainRefs.current[toSlot]
    if (!ctx || !outGain || !inGain) return
    const now = ctx.currentTime
    outGain.gain.cancelScheduledValues(now)
    outGain.gain.setValueAtTime(outGain.gain.value, now)
    outGain.gain.linearRampToValueAtTime(0, now + CROSSFADE_MS / 1000)
    inGain.gain.cancelScheduledValues(now)
    inGain.gain.setValueAtTime(0, now)
    inGain.gain.linearRampToValueAtTime(1, now + CROSSFADE_MS / 1000)
  }, [])

  // Holds the latest versions of values/callbacks the (mount-once) audio
  // element event handlers need, so they never see stale closures without
  // having to recreate the two <audio> elements every render.
  const latestRef = useRef<{
    tracks: PlayerTrack[]
    nextIndex: () => number | null
    crossfadeEnabled: boolean
  }>({ tracks: [], nextIndex: () => null, crossfadeEnabled: false })

  const loadIntoSlot = useCallback(
    async (slot: Slot, track: PlayerTrack, autoplay: boolean, seekTo?: number | null) => {
      const audio = audioRefs.current[slot]
      if (!audio) return
      ensureAudioGraph()
      audio.src = playerApi.streamUrl(track.id)
      audio.load()
      if (seekTo != null && seekTo > 0) {
        const applySeek = () => {
          if (Number.isFinite(audio.duration) && audio.duration > 0) {
            audio.currentTime = Math.min(seekTo, Math.max(0, audio.duration - 0.25))
          } else {
            audio.currentTime = seekTo
          }
        }
        audio.addEventListener('loadedmetadata', applySeek, { once: true })
      }
      if (autoplay) {
        if (ctxRef.current?.state === 'suspended') await ctxRef.current.resume()
        if (crossfadeRef.current) fadeInSlot(slot)
        else {
          const gain = trackGainRefs.current[slot]
          if (gain && ctxRef.current) gain.gain.setValueAtTime(1, ctxRef.current.currentTime)
        }
        try {
          await audio.play()
        } catch {
          setPlaying(false)
        }
      } else {
        audio.pause()
        setPlaying(false)
      }
    },
    [ensureAudioGraph, fadeInSlot],
  )

  /** Load the current track into the active slot (fresh load: manual play,
   * skip, or restoring a saved queue). Resets any stale preload bookkeeping. */
  const loadTrack = useCallback(
    async (track: PlayerTrack, autoplay: boolean) => {
      const slot = slotRef.current
      preloadedTrackIdRef.current = null
      const seekTo = pendingSeekRef.current
      pendingSeekRef.current = null
      await loadIntoSlot(slot, track, autoplay, seekTo)
      applyMediaSession(track)
    },
    [loadIntoSlot],
  )

  const loadAndPlay = useCallback((track: PlayerTrack) => loadTrack(track, true), [loadTrack])

  const current = tracks[index]

  useEffect(() => {
    if (!current) return
    if (swapInProgressRef.current) {
      swapInProgressRef.current = false
      return
    }
    const autoplay = !skipAutoPlayRef.current
    skipAutoPlayRef.current = false
    void loadTrack(current, autoplay)
  }, [current?.id]) // eslint-disable-line react-hooks/exhaustive-deps

  const nextIndex = useCallback((forceAdvance = false) => {
    if (!tracks.length) return null
    // repeat==='one' should replay the current track when it ends naturally,
    // but pressing Next/skip must still advance — otherwise the skip control
    // becomes a no-op (same index → no state change → nothing happens).
    if (repeat === 'one' && !forceAdvance) return index
    if (shuffle) {
      if (!orderRef.current.length) {
        orderRef.current = tracks.map((_, i) => i).filter((i) => i !== index)
      }
      if (!orderRef.current.length) return repeat === 'all' ? 0 : null
      const n = orderRef.current.shift()!
      return n
    }
    if (index + 1 < tracks.length) return index + 1
    return repeat === 'all' ? 0 : null
  }, [tracks, index, shuffle, repeat])

  const next = useCallback(() => {
    const n = nextIndex(true)
    if (n == null) {
      activeAudio()?.pause()
      setPlaying(false)
      return
    }
    setIndex(n)
  }, [nextIndex, activeAudio])

  const prev = useCallback(() => {
    const audio = activeAudio()
    if (audio && audio.currentTime > 3) {
      audio.currentTime = 0
      return
    }
    setIndex((i) => (i > 0 ? i - 1 : tracks.length - 1))
  }, [tracks.length, activeAudio])

  // Keep the mount-once audio element handlers pointed at the latest state.
  useEffect(() => {
    latestRef.current = { tracks, nextIndex, crossfadeEnabled: prefs.crossfade_enabled }
  })

  const clearSleep = useCallback(() => {
    sleepAtEndRef.current = false
    setSleepMode(null)
    setSleepUntil(null)
  }, [])

  const setSleepMinutes = useCallback((mode: SleepMode) => {
    if (mode === 'end') {
      sleepAtEndRef.current = true
      setSleepMode('end')
      setSleepUntil(null)
      return
    }
    sleepAtEndRef.current = false
    setSleepMode(mode)
    setSleepUntil(Date.now() + mode * 60_000)
  }, [])

  // Create the two audio elements once and wire slot-aware listeners.
  useEffect(() => {
    const a = new Audio()
    const b = new Audio()
    a.preload = 'metadata'
    b.preload = 'none'
    for (const audio of [a, b]) {
      audio.setAttribute('x-webkit-airplay', 'allow')
      audio.volume = 1
    }
    audioRefs.current.A = a
    audioRefs.current.B = b

    function maybePreloadNext(slot: Slot) {
      const audio = audioRefs.current[slot]
      if (!audio || !Number.isFinite(audio.duration) || audio.duration <= 0) return
      const remaining = audio.duration - audio.currentTime
      if (remaining > PRELOAD_LEAD_SECONDS) return
      const { nextIndex: getNext, tracks: currentTracks } = latestRef.current
      const n = getNext()
      if (n == null) return
      const nextTrack = currentTracks[n]
      if (!nextTrack || preloadedTrackIdRef.current === nextTrack.id) return
      const inactive = otherSlot(slot)
      const inactiveAudio = audioRefs.current[inactive]
      if (!inactiveAudio) return
      preloadedTrackIdRef.current = nextTrack.id
      ensureAudioGraph()
      inactiveAudio.preload = 'auto'
      inactiveAudio.src = playerApi.streamUrl(nextTrack.id)
      inactiveAudio.load()
      const inGain = trackGainRefs.current[inactive]
      if (inGain && ctxRef.current) inGain.gain.setValueAtTime(0, ctxRef.current.currentTime)
    }

    function handleEnded(slot: Slot) {
      if (sleepAtEndRef.current) {
        sleepAtEndRef.current = false
        setSleepMode(null)
        setPlaying(false)
        return
      }
      const { nextIndex: getNext, tracks: currentTracks, crossfadeEnabled } = latestRef.current
      const n = getNext()
      if (n == null) {
        setPlaying(false)
        return
      }
      const nextTrack = currentTracks[n]
      const inactive = otherSlot(slot)
      const inactiveAudio = audioRefs.current[inactive]
      const preloadReady =
        !!nextTrack &&
        !!inactiveAudio &&
        preloadedTrackIdRef.current === nextTrack.id &&
        inactiveAudio.readyState >= 2

      if (nextTrack && preloadReady && inactiveAudio) {
        // Fast path: the next track is already buffered on the idle element,
        // so we can swap straight to it with no network round-trip — this is
        // what makes the boundary gapless.
        slotRef.current = inactive
        preloadedTrackIdRef.current = null
        if (crossfadeEnabled) crossfadeSwap(slot, inactive)
        else {
          const now = ctxRef.current?.currentTime ?? 0
          trackGainRefs.current[inactive]?.gain.setValueAtTime(1, now)
          trackGainRefs.current[slot]?.gain.setValueAtTime(0, now)
        }
        swapInProgressRef.current = true
        void inactiveAudio.play().catch(() => setPlaying(false))
        applyMediaSession(nextTrack)
        setCurrentTime(inactiveAudio.currentTime || 0)
        setDuration(inactiveAudio.duration || 0)
        setPlaying(true)
        setIndex(n)
      } else {
        // No time to preload (very short track, or user just seeked past the
        // preload window) — falls back to a normal reload, same as a skip.
        setIndex(n)
      }
    }

    const cleanups: Array<() => void> = []
    for (const [audio, slot] of [
      [a, 'A'],
      [b, 'B'],
    ] as Array<[HTMLAudioElement, Slot]>) {
      const onTime = () => {
        if (slotRef.current !== slot) return
        setCurrentTime(audio.currentTime || 0)
        maybePreloadNext(slot)
      }
      const onMeta = () => {
        if (slotRef.current !== slot) return
        setDuration(audio.duration || 0)
      }
      const onPlay = () => {
        if (slotRef.current === slot) setPlaying(true)
      }
      const onPause = () => {
        if (slotRef.current === slot) setPlaying(false)
      }
      const onEnded = () => {
        if (slotRef.current === slot) handleEnded(slot)
      }
      audio.addEventListener('timeupdate', onTime)
      audio.addEventListener('loadedmetadata', onMeta)
      audio.addEventListener('play', onPlay)
      audio.addEventListener('pause', onPause)
      audio.addEventListener('ended', onEnded)
      cleanups.push(() => {
        audio.pause()
        audio.removeEventListener('timeupdate', onTime)
        audio.removeEventListener('loadedmetadata', onMeta)
        audio.removeEventListener('play', onPlay)
        audio.removeEventListener('pause', onPause)
        audio.removeEventListener('ended', onEnded)
      })
    }
    return () => {
      cleanups.forEach((fn) => fn())
      audioRefs.current.A = null
      audioRefs.current.B = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Restore queue
  useEffect(() => {
    if (userId == null) return
    try {
      const raw = localStorage.getItem(storageKey(userId))
      if (!raw) return
      const data = JSON.parse(raw) as {
        tracks: PlayerTrack[]
        index: number
        shuffle: boolean
        repeat: RepeatMode
        volume: number
        sourceLabel?: string | null
      }
      if (Array.isArray(data.tracks) && data.tracks.length) {
        skipAutoPlayRef.current = true
        setTracks(data.tracks)
        setIndex(Math.min(data.index || 0, data.tracks.length - 1))
        setShuffle(!!data.shuffle)
        setRepeat(data.repeat || 'off')
        setSourceLabel(data.sourceLabel || null)
        if (typeof data.volume === 'number') setVolumeState(data.volume)
      }
    } catch {
      /* ignore */
    }
  }, [userId])

  // Persist
  useEffect(() => {
    if (userId == null) return
    localStorage.setItem(
      storageKey(userId),
      JSON.stringify({ tracks, index, shuffle, repeat, volume, sourceLabel }),
    )
  }, [userId, tracks, index, shuffle, repeat, volume, sourceLabel])

  // Default shuffle/repeat come from saved prefs, applied once per session.
  useEffect(() => {
    if (defaultsAppliedRef.current || !prefsQ.data) return
    defaultsAppliedRef.current = true
    if (prefsQ.data.default_shuffle) setShuffle(true)
    if (prefsQ.data.default_repeat && prefsQ.data.default_repeat !== 'off') {
      setRepeat(prefsQ.data.default_repeat)
    }
  }, [prefsQ.data])

  // Countdown sleep timer: pause playback when the deadline passes.
  useEffect(() => {
    if (sleepUntil == null) return
    const id = window.setInterval(() => {
      if (Date.now() < sleepUntil) return
      activeAudio()?.pause()
      setPlaying(false)
      clearSleep()
    }, 1000)
    return () => window.clearInterval(id)
  }, [sleepUntil, clearSleep, activeAudio])

  const forceStop = useCallback(() => {
    for (const slot of ['A', 'B'] as Slot[]) {
      const audio = audioRefs.current[slot]
      if (audio) {
        audio.pause()
        audio.removeAttribute('src')
        audio.load()
      }
      const now = ctxRef.current?.currentTime ?? 0
      trackGainRefs.current[slot]?.gain.setValueAtTime(slot === 'A' ? 1 : 0, now)
    }
    slotRef.current = 'A'
    preloadedTrackIdRef.current = null
    setTracks([])
    setIndex(0)
    setPlaying(false)
    setCurrentTime(0)
    setDuration(0)
    setSourceLabel(null)
  }, [])

  // Live websocket for near-instant multi-device sync (stop commands, future
  // presence pushes). Kept in its own effect keyed only on userId/forceStop
  // (both stable) so frequent playback-state changes below don't tear down
  // and reconnect the socket on every tick.
  const pollActiveRef = useRef(true)
  useEffect(() => {
    if (userId == null) return
    let socket: WebSocket | null = null
    try {
      const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
      socket = new WebSocket(`${proto}//${window.location.host}/api/player/ws`)
      socket.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data)
          if (msg?.type === 'stop') forceStop()
        } catch {
          /* ignore malformed message */
        }
      }
      socket.onopen = () => {
        pollActiveRef.current = false
      }
      socket.onclose = () => {
        pollActiveRef.current = true
      }
      socket.onerror = () => {
        pollActiveRef.current = true
      }
    } catch {
      pollActiveRef.current = true
    }
    return () => {
      pollActiveRef.current = true
      socket?.close()
    }
  }, [userId, forceStop])

  // Presence heartbeat + admin stop commands; the poll is a fallback for any
  // client that can't (or doesn't yet) have the websocket open.
  useEffect(() => {
    if (userId == null) return
    const tick = () => {
      const track = tracks[index]
      void playerApi
        .reportPlaying({
          track_id: track?.id ?? null,
          position: activeAudio()?.currentTime || 0,
          playing,
          title: track?.title,
          artist_name: track?.artist_name,
          cover_url: track?.cover_url,
        })
        .catch(() => undefined)
    }
    tick()
    const hb = window.setInterval(tick, 10000)
    const cmd = window.setInterval(() => {
      if (!pollActiveRef.current) return
      void playerApi
        .commands()
        .then((res) => {
          if (res.stop) forceStop()
        })
        .catch(() => undefined)
    }, 3000)
    return () => {
      window.clearInterval(hb)
      window.clearInterval(cmd)
    }
  }, [userId, tracks, index, playing, forceStop, activeAudio])

  const playTracks = useCallback(
    (list: PlayerTrack[], startIndex = 0, label?: string, startAt?: number) => {
      if (!list.length) return
      orderRef.current = []
      preloadedTrackIdRef.current = null
      pendingSeekRef.current = startAt != null && startAt > 0 ? startAt : null
      setTracks(list)
      setIndex(Math.max(0, Math.min(startIndex, list.length - 1)))
      if (label !== undefined) setSourceLabel(label || null)
    },
    [],
  )

  const playTrack = useCallback(
    (track: PlayerTrack, queue?: PlayerTrack[], label?: string, startAt?: number) => {
      if (queue?.length) {
        const i = queue.findIndex((t) => t.id === track.id)
        playTracks(queue, i >= 0 ? i : 0, label, startAt)
      } else {
        playTracks([track], 0, label, startAt)
      }
    },
    [playTracks],
  )

  const addNext = useCallback(
    (track: PlayerTrack) => {
      setTracks((prev) => {
        const copy = [...prev]
        copy.splice(index + 1, 0, track)
        return copy
      })
    },
    [index],
  )

  const addEnd = useCallback((track: PlayerTrack) => {
    setTracks((prev) => [...prev, track])
  }, [])

  const togglePlay = useCallback(async () => {
    const audio = activeAudio()
    if (!audio) return
    ensureAudioGraph()
    if (ctxRef.current?.state === 'suspended') await ctxRef.current.resume()
    if (audio.paused) {
      if (!audio.src && current) await loadAndPlay(current)
      else await audio.play().catch(() => undefined)
    } else {
      audio.pause()
    }
  }, [current, ensureAudioGraph, loadAndPlay, activeAudio])

  const seek = useCallback(
    (t: number) => {
      const audio = activeAudio()
      if (!audio || !Number.isFinite(t)) return
      audio.currentTime = Math.max(0, Math.min(t, audio.duration || t))
    },
    [activeAudio],
  )

  const setVolume = useCallback((v: number) => {
    const nv = Math.max(0, Math.min(1, v))
    setVolumeState(nv)
    volumeRef.current = nv
    setMuted(nv <= 0)
    if (masterGainRef.current) {
      masterGainRef.current.gain.value = nv
    } else {
      if (audioRefs.current.A) audioRefs.current.A.volume = nv
      if (audioRefs.current.B) audioRefs.current.B.volume = nv
    }
  }, [])

  const toggleMute = useCallback(() => {
    if (volumeRef.current > 0) {
      mutedVolumeRef.current = volumeRef.current
      setVolume(0)
    } else {
      setVolume(mutedVolumeRef.current || 0.9)
    }
  }, [setVolume])

  const toggleShuffle = useCallback(() => {
    orderRef.current = []
    setShuffle((s) => !s)
  }, [])

  const cycleRepeat = useCallback(() => {
    setRepeat((r) => (r === 'off' ? 'all' : r === 'all' ? 'one' : 'off'))
  }, [])

  const clearQueue = useCallback(() => {
    preloadedTrackIdRef.current = null
    setTracks([])
    setIndex(0)
    setSourceLabel(null)
    activeAudio()?.pause()
  }, [activeAudio])

  const jumpTo = useCallback((i: number) => setIndex(i), [])

  const removeAt = useCallback((i: number) => {
    setTracks((prev) => {
      const nextTracks = prev.filter((_, idx) => idx !== i)
      setIndex((cur) => {
        if (i < cur) return cur - 1
        if (i === cur) return Math.min(cur, Math.max(0, nextTracks.length - 1))
        return cur
      })
      return nextTracks
    })
  }, [])

  const reorder = useCallback((from: number, to: number) => {
    if (from === to || from < 0 || to < 0) return
    setTracks((prev) => {
      if (from >= prev.length || to >= prev.length) return prev
      const next = [...prev]
      const [item] = next.splice(from, 1)
      next.splice(to, 0, item)
      return next
    })
    setIndex((cur) => {
      if (from === cur) return to
      if (from < cur && to >= cur) return cur - 1
      if (from > cur && to <= cur) return cur + 1
      return cur
    })
    orderRef.current = []
  }, [])

  // Global keyboard shortcuts, suppressed while typing.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return
      const target = e.target as HTMLElement | null
      if (target) {
        const tag = target.tagName
        if (
          tag === 'INPUT' ||
          tag === 'TEXTAREA' ||
          tag === 'SELECT' ||
          target.isContentEditable
        ) {
          return
        }
      }
      const audio = activeAudio()
      switch (e.key) {
        case ' ':
          e.preventDefault()
          void togglePlay()
          break
        case 'ArrowLeft':
          e.preventDefault()
          seek((audio?.currentTime || 0) - 5)
          break
        case 'ArrowRight':
          e.preventDefault()
          seek((audio?.currentTime || 0) + 5)
          break
        case 'ArrowUp':
          e.preventDefault()
          setVolume(volumeRef.current + 0.05)
          break
        case 'ArrowDown':
          e.preventDefault()
          setVolume(volumeRef.current - 0.05)
          break
        case 'n':
          next()
          break
        case 'p':
          prev()
          break
        case 's':
          toggleShuffle()
          break
        case 'r':
          cycleRepeat()
          break
        case 'm':
          toggleMute()
          break
        case 'f':
          window.dispatchEvent(new CustomEvent(TOGGLE_EXPANDED_EVENT))
          break
        case 'l':
          window.dispatchEvent(new CustomEvent(TOGGLE_LOVE_EVENT))
          break
        case 'q':
          window.dispatchEvent(new CustomEvent(TOGGLE_QUEUE_EVENT))
          break
        default:
          break
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [togglePlay, seek, setVolume, next, prev, toggleShuffle, cycleRepeat, toggleMute, activeAudio])

  const value = useMemo<QueueApi>(
    () => ({
      tracks,
      index,
      playing,
      shuffle,
      repeat,
      currentTime,
      duration,
      volume,
      muted,
      analyser,
      audioEl: audioRefs.current[slotRef.current],
      sourceLabel,
      sleepMode,
      sleepUntil,
      playTracks,
      playTrack,
      addNext,
      addEnd,
      togglePlay,
      next,
      prev,
      seek,
      setVolume,
      toggleMute,
      setSleepMinutes,
      clearSleep,
      toggleShuffle,
      cycleRepeat,
      clearQueue,
      forceStop,
      jumpTo,
      removeAt,
      reorder,
    }),
    [
      tracks,
      index,
      playing,
      shuffle,
      repeat,
      currentTime,
      duration,
      volume,
      muted,
      analyser,
      sourceLabel,
      sleepMode,
      sleepUntil,
      playTracks,
      playTrack,
      addNext,
      addEnd,
      togglePlay,
      next,
      prev,
      seek,
      setVolume,
      toggleMute,
      setSleepMinutes,
      clearSleep,
      toggleShuffle,
      cycleRepeat,
      clearQueue,
      forceStop,
      jumpTo,
      removeAt,
      reorder,
    ],
  )

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function usePlayerQueue() {
  const ctx = useContext(Ctx)
  if (!ctx) throw new Error('usePlayerQueue outside provider')
  return ctx
}

export function formatTime(sec: number) {
  if (!Number.isFinite(sec) || sec < 0) return '0:00'
  const m = Math.floor(sec / 60)
  const s = Math.floor(sec % 60)
  return `${m}:${String(s).padStart(2, '0')}`
}
