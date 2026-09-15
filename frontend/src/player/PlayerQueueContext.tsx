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

export type SleepMode = number | 'end'

/** Fired by keyboard shortcut `q`; WavyPlayBar listens and toggles the queue drawer. */
export const TOGGLE_QUEUE_EVENT = 'musicarr-toggle-queue'
/** Fired by keyboard shortcut `l`; WavyPlayBar listens and likes the current track. */
export const TOGGLE_LOVE_EVENT = 'musicarr-toggle-love'

type QueueState = {
  tracks: PlayerTrack[]
  index: number
  playing: boolean
  shuffle: boolean
  repeat: RepeatMode
  currentTime: number
  duration: number
  volume: number
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

function storageKey(userId: number | null) {
  return `musicarr-player-queue-v1-${userId ?? 'anon'}`
}

export function PlayerQueueProvider({
  userId,
  children,
}: {
  userId: number | null
  children: ReactNode
}) {
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const ctxRef = useRef<AudioContext | null>(null)
  const sourceRef = useRef<MediaElementAudioSourceNode | null>(null)
  const gainRef = useRef<GainNode | null>(null)
  const analyserRef = useRef<AnalyserNode | null>(null)
  const [tracks, setTracks] = useState<PlayerTrack[]>([])
  const [index, setIndex] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [shuffle, setShuffle] = useState(false)
  const [repeat, setRepeat] = useState<RepeatMode>('off')
  const [currentTime, setCurrentTime] = useState(0)
  const [duration, setDuration] = useState(0)
  const [volume, setVolumeState] = useState(0.9)
  const [analyser, setAnalyser] = useState<AnalyserNode | null>(null)
  const [sourceLabel, setSourceLabel] = useState<string | null>(null)
  const [sleepMode, setSleepMode] = useState<SleepMode | null>(null)
  const [sleepUntil, setSleepUntil] = useState<number | null>(null)
  const orderRef = useRef<number[]>([])
  const skipAutoPlayRef = useRef(false)
  const volumeRef = useRef(volume)
  const fadeRef = useRef<number | null>(null)
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

  const ensureAudioGraph = useCallback(() => {
    const audio = audioRef.current
    if (!audio) return
    if (!ctxRef.current) {
      const CtxAudio = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext
      ctxRef.current = new CtxAudio()
    }
    const ctx = ctxRef.current
    if (!sourceRef.current) {
      // Once routed through Web Audio, element.volume is unreliable — use a GainNode.
      audio.volume = 1
      sourceRef.current = ctx.createMediaElementSource(audio)
      const analyserNode = ctx.createAnalyser()
      analyserNode.fftSize = 64
      const gain = ctx.createGain()
      gain.gain.value = Math.max(0, Math.min(1, volumeRef.current))
      sourceRef.current.connect(analyserNode)
      analyserNode.connect(gain)
      gain.connect(ctx.destination)
      analyserRef.current = analyserNode
      gainRef.current = gain
      setAnalyser(analyserNode)
    }
  }, [])

  /** Ramp gain from 0 to the user level so track changes don't hard-cut. */
  const fadeIn = useCallback(() => {
    const gain = gainRef.current
    const audio = audioRef.current
    if (!gain && !audio) return
    if (fadeRef.current) window.clearInterval(fadeRef.current)
    const target = Math.max(0, Math.min(1, volumeRef.current))
    const started = performance.now()
    if (gain) gain.gain.value = 0
    else if (audio) audio.volume = 0
    fadeRef.current = window.setInterval(() => {
      const ratio = Math.min(1, (performance.now() - started) / CROSSFADE_MS)
      const level = Math.max(0, Math.min(1, volumeRef.current * ratio))
      if (gainRef.current) gainRef.current.gain.value = level
      else if (audioRef.current) audioRef.current.volume = level
      if (ratio >= 1) {
        window.clearInterval(fadeRef.current!)
        fadeRef.current = null
        if (gainRef.current) gainRef.current.gain.value = target
        else if (audioRef.current) audioRef.current.volume = target
      }
    }, 40)
  }, [])

  useEffect(() => {
    const audio = new Audio()
    audio.preload = 'metadata'
    audioRef.current = audio
    audio.volume = volume

    const onTime = () => setCurrentTime(audio.currentTime || 0)
    const onMeta = () => setDuration(audio.duration || 0)
    const onPlay = () => setPlaying(true)
    const onPause = () => setPlaying(false)
    audio.addEventListener('timeupdate', onTime)
    audio.addEventListener('loadedmetadata', onMeta)
    audio.addEventListener('play', onPlay)
    audio.addEventListener('pause', onPause)
    return () => {
      audio.pause()
      audio.removeEventListener('timeupdate', onTime)
      audio.removeEventListener('loadedmetadata', onMeta)
      audio.removeEventListener('play', onPlay)
      audio.removeEventListener('pause', onPause)
      if (fadeRef.current) window.clearInterval(fadeRef.current)
      audioRef.current = null
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

  const loadTrack = useCallback(
    async (track: PlayerTrack, autoplay: boolean) => {
      const audio = audioRef.current
      if (!audio) return
      ensureAudioGraph()
      if (ctxRef.current?.state === 'suspended') await ctxRef.current.resume()
      audio.src = playerApi.streamUrl(track.id)
      const seekTo = pendingSeekRef.current
      pendingSeekRef.current = null
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
        if (crossfadeRef.current) fadeIn()
        try {
          await audio.play()
        } catch {
          setPlaying(false)
        }
      } else {
        audio.pause()
        setPlaying(false)
      }
      if ('mediaSession' in navigator) {
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
    },
    [ensureAudioGraph, fadeIn],
  )

  const loadAndPlay = useCallback(
    (track: PlayerTrack) => loadTrack(track, true),
    [loadTrack],
  )

  const current = tracks[index]

  useEffect(() => {
    if (!current) return
    const autoplay = !skipAutoPlayRef.current
    skipAutoPlayRef.current = false
    void loadTrack(current, autoplay)
  }, [current?.id]) // eslint-disable-line react-hooks/exhaustive-deps

  const nextIndex = useCallback(() => {
    if (!tracks.length) return null
    if (repeat === 'one') return index
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
    const n = nextIndex()
    if (n == null) {
      audioRef.current?.pause()
      setPlaying(false)
      return
    }
    setIndex(n)
  }, [nextIndex])

  const prev = useCallback(() => {
    const audio = audioRef.current
    if (audio && audio.currentTime > 3) {
      audio.currentTime = 0
      return
    }
    setIndex((i) => (i > 0 ? i - 1 : tracks.length - 1))
  }, [tracks.length])

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

  useEffect(() => {
    const audio = audioRef.current
    if (!audio) return
    const onEnded = () => {
      if (sleepAtEndRef.current) {
        sleepAtEndRef.current = false
        setSleepMode(null)
        setPlaying(false)
        return
      }
      next()
    }
    audio.addEventListener('ended', onEnded)
    return () => audio.removeEventListener('ended', onEnded)
  }, [next])

  // Countdown sleep timer: pause playback when the deadline passes.
  useEffect(() => {
    if (sleepUntil == null) return
    const id = window.setInterval(() => {
      if (Date.now() < sleepUntil) return
      audioRef.current?.pause()
      setPlaying(false)
      clearSleep()
    }, 1000)
    return () => window.clearInterval(id)
  }, [sleepUntil, clearSleep])

  const forceStop = useCallback(() => {
    const audio = audioRef.current
    if (audio) {
      audio.pause()
      audio.removeAttribute('src')
      audio.load()
    }
    setTracks([])
    setIndex(0)
    setPlaying(false)
    setCurrentTime(0)
    setDuration(0)
    setSourceLabel(null)
  }, [])

  // Presence heartbeat + admin stop commands
  useEffect(() => {
    if (userId == null) return
    const tick = () => {
      const track = tracks[index]
      void playerApi
        .reportPlaying({
          track_id: track?.id ?? null,
          position: audioRef.current?.currentTime || 0,
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
  }, [userId, tracks, index, playing, forceStop])

  const playTracks = useCallback(
    (list: PlayerTrack[], startIndex = 0, label?: string, startAt?: number) => {
      if (!list.length) return
      orderRef.current = []
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
    const audio = audioRef.current
    if (!audio) return
    ensureAudioGraph()
    if (ctxRef.current?.state === 'suspended') await ctxRef.current.resume()
    if (audio.paused) {
      if (!audio.src && current) await loadAndPlay(current)
      else await audio.play().catch(() => undefined)
    } else {
      audio.pause()
    }
  }, [current, ensureAudioGraph, loadAndPlay])

  const seek = useCallback((t: number) => {
    const audio = audioRef.current
    if (!audio || !Number.isFinite(t)) return
    audio.currentTime = Math.max(0, Math.min(t, audio.duration || t))
  }, [])

  const setVolume = useCallback((v: number) => {
    const nv = Math.max(0, Math.min(1, v))
    setVolumeState(nv)
    volumeRef.current = nv
    if (fadeRef.current) {
      window.clearInterval(fadeRef.current)
      fadeRef.current = null
    }
    if (gainRef.current) {
      gainRef.current.gain.value = nv
    } else if (audioRef.current) {
      audioRef.current.volume = nv
    }
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
      const audio = audioRef.current
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
  }, [togglePlay, seek, setVolume, next, prev])

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
      analyser,
      audioEl: audioRef.current,
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
      setSleepMinutes,
      clearSleep,
      toggleShuffle: () => {
        orderRef.current = []
        setShuffle((s) => !s)
      },
      cycleRepeat: () =>
        setRepeat((r) => (r === 'off' ? 'all' : r === 'all' ? 'one' : 'off')),
      clearQueue: () => {
        setTracks([])
        setIndex(0)
        setSourceLabel(null)
        audioRef.current?.pause()
      },
      forceStop,
      jumpTo: (i) => setIndex(i),
      removeAt: (i) => {
        setTracks((prev) => {
          const nextTracks = prev.filter((_, idx) => idx !== i)
          setIndex((cur) => {
            if (i < cur) return cur - 1
            if (i === cur) return Math.min(cur, Math.max(0, nextTracks.length - 1))
            return cur
          })
          return nextTracks
        })
      },
      reorder: (from, to) => {
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
      },
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
      setSleepMinutes,
      clearSleep,
      forceStop,
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
