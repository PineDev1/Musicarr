import { useQuery } from '@tanstack/react-query'
import { useCallback, useEffect, useRef, useState, type CSSProperties } from 'react'
import { useParams } from 'react-router-dom'
import { IconPause, IconPlay, IconUser } from './icons'
import { playerApi } from './playerApi'

function formatTime(sec: number) {
  if (!Number.isFinite(sec) || sec < 0) return '0:00'
  const m = Math.floor(sec / 60)
  const s = Math.floor(sec % 60)
  return `${m}:${String(s).padStart(2, '0')}`
}

/**
 * Public single-song mini player at /s/:token.
 * Token-gated stream only — no library, login, or other tracks.
 */
export function ShareSongPage() {
  const { token: rawToken } = useParams()
  const token = (rawToken || '').trim()
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const [playing, setPlaying] = useState(false)
  const [currentTime, setCurrentTime] = useState(0)
  const [duration, setDuration] = useState(0)
  const [playError, setPlayError] = useState<string | null>(null)
  const [avatarBroken, setAvatarBroken] = useState(false)
  const [ready, setReady] = useState(false)

  const { data, isLoading, error } = useQuery({
    queryKey: ['share-meta', token],
    queryFn: () => playerApi.shareMeta(token),
    enabled: token.length > 8,
    retry: false,
  })

  useEffect(() => {
    const audio = new Audio()
    audio.preload = 'metadata'
    audioRef.current = audio

    const onTime = () => setCurrentTime(audio.currentTime || 0)
    const onMeta = () => {
      setDuration(audio.duration || 0)
      setReady(true)
    }
    const onPlay = () => {
      setPlaying(true)
      setPlayError(null)
    }
    const onPause = () => setPlaying(false)
    const onEnded = () => setPlaying(false)
    const onErr = () => {
      setPlaying(false)
      setPlayError('Could not play this file in your browser.')
    }

    audio.addEventListener('timeupdate', onTime)
    audio.addEventListener('loadedmetadata', onMeta)
    audio.addEventListener('play', onPlay)
    audio.addEventListener('pause', onPause)
    audio.addEventListener('ended', onEnded)
    audio.addEventListener('error', onErr)

    return () => {
      audio.pause()
      audio.removeAttribute('src')
      audio.removeEventListener('timeupdate', onTime)
      audio.removeEventListener('loadedmetadata', onMeta)
      audio.removeEventListener('play', onPlay)
      audio.removeEventListener('pause', onPause)
      audio.removeEventListener('ended', onEnded)
      audio.removeEventListener('error', onErr)
      audioRef.current = null
    }
  }, [])

  useEffect(() => {
    const audio = audioRef.current
    if (!audio || !token || !data) return
    setReady(false)
    setPlayError(null)
    setCurrentTime(0)
    audio.src = playerApi.shareStreamUrl(token)
    audio.load()
  }, [token, data])

  const toggle = useCallback(async () => {
    const audio = audioRef.current
    if (!audio || !token) return
    setPlayError(null)
    if (!audio.paused) {
      audio.pause()
      return
    }
    if (!audio.src) {
      audio.src = playerApi.shareStreamUrl(token)
    }
    try {
      await audio.play()
    } catch (err) {
      setPlaying(false)
      setPlayError(err instanceof Error ? err.message : 'Playback failed')
    }
  }, [token])

  const seek = useCallback((t: number) => {
    const audio = audioRef.current
    if (!audio || !Number.isFinite(t)) return
    audio.currentTime = Math.max(0, Math.min(t, audio.duration || t))
  }, [])

  if (!token || token.length < 8) {
    return (
      <div className="share-shell">
        <div className="share-mini">
          <div className="brand">
            Music<span>arr</span>
          </div>
          <h1>Invalid link</h1>
          <p className="muted">This share link is incomplete.</p>
        </div>
      </div>
    )
  }

  if (isLoading) {
    return (
      <div className="share-shell">
        <div className="share-mini">
          <p className="muted">Loading shared song…</p>
        </div>
      </div>
    )
  }

  if (error || !data) {
    return (
      <div className="share-shell">
        <div className="share-mini">
          <div className="brand">
            Music<span>arr</span>
          </div>
          <h1>Link unavailable</h1>
          <p className="muted">
            {error
              ? (error as Error).message
              : 'This share link is invalid, expired, or was revoked.'}
          </p>
        </div>
      </div>
    )
  }

  const max = duration > 0 ? duration : data.duration || 1
  const progress = max > 0 ? Math.min(1, currentTime / max) : 0

  return (
    <div className="share-shell">
      <div className="share-mini" role="main">
        <div className="brand">
          Music<span>arr</span> <span className="player-tag">Share</span>
        </div>

        <button type="button" className="share-art-btn" onClick={() => void toggle()} aria-label={playing ? 'Pause' : 'Play'}>
          {data.cover_url ? (
            <img src={data.cover_url} alt="" className="share-art-img" />
          ) : (
            <div className="share-art-img ph" />
          )}
          <span className={`share-play-fab${playing ? ' playing' : ''}`}>
            {playing ? <IconPause size={28} /> : <IconPlay size={28} />}
          </span>
        </button>

        <h1 title={data.title}>{data.title}</h1>
        <p className="share-artist">
          {data.artist}
          {data.album ? <span className="muted"> · {data.album}</span> : null}
        </p>

        <div className="share-transport">
          <button
            type="button"
            className="share-play-main"
            aria-label={playing ? 'Pause' : 'Play'}
            onClick={() => void toggle()}
          >
            {playing ? <IconPause size={22} /> : <IconPlay size={22} />}
            <span>{playing ? 'Pause' : 'Play'}</span>
          </button>

          <div className="share-seek-wrap">
            <input
              type="range"
              min={0}
              max={max}
              step={0.25}
              value={Math.min(currentTime, max)}
              aria-label="Seek"
              className="share-seek"
              style={{ '--share-progress': `${progress * 100}%` } as CSSProperties}
              onChange={(e) => seek(Number(e.target.value))}
            />
            <div className="share-times">
              <span>{formatTime(currentTime)}</span>
              <span>{formatTime(max)}</span>
            </div>
          </div>
        </div>

        {playError && <p className="error share-error">{playError}</p>}
        {!ready && !playError && <p className="muted tiny">Preparing audio…</p>}

        <div className="share-by">
          <span className="player-avatar sm">
            {data.shared_by_avatar_url && !avatarBroken ? (
              <img
                src={data.shared_by_avatar_url}
                alt=""
                onError={() => setAvatarBroken(true)}
              />
            ) : (
              <IconUser size={16} />
            )}
          </span>
          <span className="muted tiny">
            Shared by {data.shared_by_display_name || 'a Musicarr listener'}
          </span>
        </div>

        <p className="muted tiny share-note">This link only plays this song — nothing else in the library.</p>
      </div>
    </div>
  )
}
