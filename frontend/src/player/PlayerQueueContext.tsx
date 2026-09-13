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
import { playerApi, type PlayerTrack } from './playerApi'

type RepeatMode = 'off' | 'all' | 'one'

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
}

type QueueApi = QueueState & {
  playTracks: (tracks: PlayerTrack[], startIndex?: number) => void
  playTrack: (track: PlayerTrack, queue?: PlayerTrack[]) => void
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
}

const Ctx = createContext<QueueApi | null>(null)

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
  const orderRef = useRef<number[]>([])
  const skipAutoPlayRef = useRef(false)

  const ensureAudioGraph = useCallback(() => {
    const audio = audioRef.current
    if (!audio) return
    if (!ctxRef.current) {
      const CtxAudio = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext
      ctxRef.current = new CtxAudio()
    }
    const ctx = ctxRef.current
    if (!sourceRef.current) {
      sourceRef.current = ctx.createMediaElementSource(audio)
      const analyserNode = ctx.createAnalyser()
      analyserNode.fftSize = 64
      sourceRef.current.connect(analyserNode)
      analyserNode.connect(ctx.destination)
      analyserRef.current = analyserNode
      setAnalyser(analyserNode)
    }
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
    const onEnded = () => {
      setPlaying(false)
      // handled via effect below through ended listener that calls next
    }
    audio.addEventListener('timeupdate', onTime)
    audio.addEventListener('loadedmetadata', onMeta)
    audio.addEventListener('play', onPlay)
    audio.addEventListener('pause', onPause)
    audio.addEventListener('ended', onEnded)
    return () => {
      audio.pause()
      audio.removeEventListener('timeupdate', onTime)
      audio.removeEventListener('loadedmetadata', onMeta)
      audio.removeEventListener('play', onPlay)
      audio.removeEventListener('pause', onPause)
      audio.removeEventListener('ended', onEnded)
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
      const data = JSON.parse(raw) as { tracks: PlayerTrack[]; index: number; shuffle: boolean; repeat: RepeatMode; volume: number }
      if (Array.isArray(data.tracks) && data.tracks.length) {
        skipAutoPlayRef.current = true
        setTracks(data.tracks)
        setIndex(Math.min(data.index || 0, data.tracks.length - 1))
        setShuffle(!!data.shuffle)
        setRepeat(data.repeat || 'off')
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
      JSON.stringify({ tracks, index, shuffle, repeat, volume }),
    )
  }, [userId, tracks, index, shuffle, repeat, volume])

  const loadTrack = useCallback(
    async (track: PlayerTrack, autoplay: boolean) => {
      const audio = audioRef.current
      if (!audio) return
      ensureAudioGraph()
      if (ctxRef.current?.state === 'suspended') await ctxRef.current.resume()
      audio.src = playerApi.streamUrl(track.id)
      if (autoplay) {
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
    [ensureAudioGraph],
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

  useEffect(() => {
    const audio = audioRef.current
    if (!audio) return
    const onEnded = () => next()
    audio.addEventListener('ended', onEnded)
    return () => audio.removeEventListener('ended', onEnded)
  }, [next])

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

  const playTracks = useCallback((list: PlayerTrack[], startIndex = 0) => {
    if (!list.length) return
    orderRef.current = []
    setTracks(list)
    setIndex(Math.max(0, Math.min(startIndex, list.length - 1)))
  }, [])

  const playTrack = useCallback(
    (track: PlayerTrack, queue?: PlayerTrack[]) => {
      if (queue?.length) {
        const i = queue.findIndex((t) => t.id === track.id)
        playTracks(queue, i >= 0 ? i : 0)
      } else {
        playTracks([track], 0)
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
    if (audioRef.current) audioRef.current.volume = nv
  }, [])

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
      playTracks,
      playTrack,
      addNext,
      addEnd,
      togglePlay,
      next,
      prev,
      seek,
      setVolume,
      toggleShuffle: () => {
        orderRef.current = []
        setShuffle((s) => !s)
      },
      cycleRepeat: () =>
        setRepeat((r) => (r === 'off' ? 'all' : r === 'all' ? 'one' : 'off')),
      clearQueue: () => {
        setTracks([])
        setIndex(0)
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
      playTracks,
      playTrack,
      addNext,
      addEnd,
      togglePlay,
      next,
      prev,
      seek,
      setVolume,
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
