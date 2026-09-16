import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState, type CSSProperties, type PointerEvent as ReactPointerEvent } from 'react'
import { Link } from 'react-router-dom'
import { useToast } from '../Toast'
import {
  IconClose,
  IconHeart,
  IconMoon,
  IconNext,
  IconPause,
  IconPlay,
  IconPrev,
  IconRepeat,
  IconShare,
  IconShuffle,
} from './icons'
import { DEFAULT_PREFS, playerApi } from './playerApi'
import { formatTime, usePlayerQueue } from './PlayerQueueContext'
import { copyToClipboard } from './TrackMenu'
import { WavySeekBar } from './WavySeekBar'

type LyricLine = { time: number; text: string }

const LRC_LINE_RE = /^\[(\d+):(\d+(?:\.\d+)?)\](.*)$/

function parseLrc(raw: string): LyricLine[] {
  const lines: LyricLine[] = []
  for (const line of raw.split('\n')) {
    const match = LRC_LINE_RE.exec(line.trim())
    if (!match) continue
    const minutes = Number(match[1])
    const seconds = Number(match[2])
    const text = match[3].trim()
    if (!Number.isFinite(minutes) || !Number.isFinite(seconds)) continue
    lines.push({ time: minutes * 60 + seconds, text })
  }
  return lines.sort((a, b) => a.time - b.time)
}

const SLEEP_OPTIONS: { label: string; value: number | 'end' }[] = [
  { label: '15 min', value: 15 },
  { label: '30 min', value: 30 },
  { label: '60 min', value: 60 },
  { label: 'End of song', value: 'end' },
]

export function ExpandedNowPlaying({ onClose }: { onClose: () => void }) {
  const q = usePlayerQueue()
  const qc = useQueryClient()
  const toast = useToast()
  const track = q.tracks[q.index]
  const [sleepRemaining, setSleepRemaining] = useState<number | null>(null)
  const [dragY, setDragY] = useState(0)
  const [dragging, setDragging] = useState(false)
  const dragStartY = useRef<number | null>(null)

  useEffect(() => {
    if (q.sleepUntil == null) {
      setSleepRemaining(null)
      return
    }
    const deadline = q.sleepUntil
    const update = () => setSleepRemaining(Math.max(0, (deadline - Date.now()) / 1000))
    update()
    const id = window.setInterval(update, 1000)
    return () => window.clearInterval(id)
  }, [q.sleepUntil])

  const prefs = useQuery({
    queryKey: ['player-prefs'],
    queryFn: playerApi.prefs,
    staleTime: 30_000,
  })
  const favIds = useQuery({
    queryKey: ['player-favorite-ids'],
    queryFn: playerApi.favoriteIds,
    staleTime: 15_000,
  })
  const liked = track ? (favIds.data?.ids || []).includes(track.id) : false

  const lyricsQ = useQuery({
    queryKey: ['player-lyrics', track?.id],
    queryFn: () => playerApi.lyrics(track!.id),
    enabled: !!track,
    staleTime: 5 * 60_000,
  })
  const syncedLines = lyricsQ.data?.synced ? parseLrc(lyricsQ.data.synced) : []
  const activeLyricIndex = syncedLines.length
    ? syncedLines.reduce(
        (acc, line, i) => (line.time <= q.currentTime ? i : acc),
        -1,
      )
    : -1

  const toggleFav = useMutation({
    mutationFn: async () => {
      if (!track) return
      if (liked) await playerApi.removeFavorite(track.id)
      else await playerApi.addFavorite(track.id)
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['player-favorite-ids'] })
      qc.invalidateQueries({ queryKey: ['player-builtins'] })
    },
  })
  const share = useMutation({
    mutationFn: () => {
      if (!track) throw new Error('Nothing playing')
      return playerApi.createShare(track.id)
    },
    onSuccess: async (link) => {
      const url = playerApi.sharePageUrl(link.token)
      const copied = await copyToClipboard(url)
      toast.push(copied ? 'Share link copied' : `Share link: ${url}`, 'ok')
      qc.invalidateQueries({ queryKey: ['player-shares'] })
    },
    onError: (err) => toast.push((err as Error).message, 'error'),
  })

  const onHandlePointerDown = (e: ReactPointerEvent<HTMLDivElement>) => {
    dragStartY.current = e.clientY
    setDragging(true)
    e.currentTarget.setPointerCapture(e.pointerId)
  }

  const onHandlePointerMove = (e: ReactPointerEvent<HTMLDivElement>) => {
    if (dragStartY.current == null) return
    const dy = Math.max(0, e.clientY - dragStartY.current)
    setDragY(dy)
  }

  const endDrag = (e: ReactPointerEvent<HTMLDivElement>) => {
    if (dragStartY.current == null) return
    const dy = Math.max(0, e.clientY - dragStartY.current)
    dragStartY.current = null
    setDragging(false)
    if (dy > 120) {
      onClose()
      return
    }
    setDragY(0)
  }

  if (!track) return null
  const wave = prefs.data || DEFAULT_PREFS
  const upNext = q.tracks.slice(q.index + 1, q.index + 6)
  const volPct = Math.round(q.volume * 100)

  return (
    <div
      className={`expanded-np${dragging ? ' dragging' : ''}`}
      role="dialog"
      aria-label="Now playing"
      style={{ transform: dragY ? `translateY(${dragY}px)` : undefined, opacity: dragY ? Math.max(0.35, 1 - dragY / 480) : undefined }}
    >
      <div
        className="expanded-np-handle"
        onPointerDown={onHandlePointerDown}
        onPointerMove={onHandlePointerMove}
        onPointerUp={endDrag}
        onPointerCancel={endDrag}
        role="button"
        tabIndex={0}
        aria-label="Swipe down to close"
        onKeyDown={(e) => {
          if (e.key === 'Escape' || e.key === 'ArrowDown') onClose()
        }}
      >
        <span className="expanded-np-grabber" />
      </div>

      <div className="expanded-np-top">
        <button type="button" className="pill-icon-btn" aria-label="Close" onClick={onClose}>
          <IconClose size={20} />
        </button>
        <span className="muted tiny">
          {q.sourceLabel ? `Playing from ${q.sourceLabel}` : 'Now playing'}
        </span>
        <button
          type="button"
          className="pill-icon-btn"
          aria-label="Share song"
          onClick={() => share.mutate()}
          disabled={share.isPending}
        >
          <IconShare size={18} />
        </button>
      </div>

      <div className="expanded-np-body">
        <div className="expanded-np-art">
          {track.cover_url ? (
            <img src={track.cover_url} alt="" />
          ) : (
            <div className="expanded-np-ph" />
          )}
        </div>

        <div className="expanded-np-info">
          <h2>{track.title}</h2>
          <p className="muted">
            <Link to={`/player/artists/${track.artist_id}`} onClick={onClose}>
              {track.artist_name}
            </Link>
            {' — '}
            <Link to={`/player/albums/${track.album_id}`} onClick={onClose}>
              {track.album_title}
            </Link>
          </p>

          <WavySeekBar
            value={q.currentTime}
            max={q.duration || 1}
            playing={q.playing}
            prefs={wave}
            onSeek={q.seek}
            className="wavy-seek lg"
          />
          <div className="pill-times">
            <span>{formatTime(q.currentTime)}</span>
            <span>{formatTime(q.duration)}</span>
          </div>

          <div className="pill-controls">
            <button
              type="button"
              className={`pill-icon-btn${q.shuffle ? ' on' : ''}`}
              aria-label="Shuffle"
              onClick={q.toggleShuffle}
            >
              <IconShuffle size={20} />
            </button>
            <button type="button" className="pill-icon-btn" aria-label="Previous" onClick={q.prev}>
              <IconPrev size={24} />
            </button>
            <button
              type="button"
              className="pill-play lg"
              aria-label={q.playing ? 'Pause' : 'Play'}
              onClick={q.togglePlay}
            >
              {q.playing ? <IconPause size={28} /> : <IconPlay size={28} />}
            </button>
            <button type="button" className="pill-icon-btn" aria-label="Next" onClick={q.next}>
              <IconNext size={24} />
            </button>
            <button
              type="button"
              className={`pill-icon-btn${q.repeat !== 'off' ? ' on' : ''}`}
              aria-label="Repeat"
              onClick={q.cycleRepeat}
            >
              <IconRepeat size={20} />
              {q.repeat === 'one' && <span className="rep-one">1</span>}
            </button>
          </div>

          <div className="expanded-np-extras">
            <button
              type="button"
              className={`pill-icon-btn heart${liked ? ' on' : ''}`}
              aria-label={liked ? 'Unlike' : 'Like'}
              onClick={() => toggleFav.mutate()}
            >
              <IconHeart filled={liked} size={20} />
            </button>
            <label className="pill-vol-wrap wide">
              <span className="sr-only">Volume</span>
              <input
                type="range"
                min={0}
                max={1}
                step={0.01}
                value={q.volume}
                onChange={(e) => q.setVolume(Number(e.target.value))}
                onInput={(e) => q.setVolume(Number((e.target as HTMLInputElement).value))}
                aria-label="Volume"
                className="pill-vol"
                style={{ '--vol': `${volPct}%` } as CSSProperties}
              />
            </label>
          </div>

          <div className="sleep-timer">
            <span className="sleep-label">
              <IconMoon size={16} /> Sleep timer
            </span>
            <div className="sleep-options">
              {SLEEP_OPTIONS.map((opt) => (
                <button
                  key={String(opt.value)}
                  type="button"
                  className={`btn ghost${q.sleepMode === opt.value ? ' active' : ''}`}
                  onClick={() => q.setSleepMinutes(opt.value)}
                >
                  {opt.label}
                </button>
              ))}
              {q.sleepMode != null && (
                <button type="button" className="btn ghost danger" onClick={q.clearSleep}>
                  Off
                </button>
              )}
            </div>
            {sleepRemaining != null && (
              <span className="muted tiny">Pausing in {formatTime(sleepRemaining)}</span>
            )}
            {q.sleepMode === 'end' && <span className="muted tiny">Pausing after this song</span>}
          </div>

          <div className="lyrics-panel">
            <div className="section-label">Lyrics</div>
            {lyricsQ.isLoading && <span className="muted tiny">Loading lyrics…</span>}
            {!lyricsQ.isLoading && syncedLines.length > 0 && (
              <div className="lyrics-synced">
                {syncedLines.map((line, i) => (
                  <p
                    key={`${line.time}-${i}`}
                    className={i === activeLyricIndex ? 'lyric-line active' : 'lyric-line'}
                    onClick={() => q.seek(line.time)}
                  >
                    {line.text || ' '}
                  </p>
                ))}
              </div>
            )}
            {!lyricsQ.isLoading && syncedLines.length === 0 && lyricsQ.data?.plain && (
              <pre className="lyrics-plain">{lyricsQ.data.plain}</pre>
            )}
            {!lyricsQ.isLoading && !lyricsQ.data?.plain && !syncedLines.length && (
              <span className="muted tiny">No lyrics found</span>
            )}
          </div>
        </div>
      </div>

      {!!upNext.length && (
        <div className="expanded-np-queue">
          <div className="section-label">Up next</div>
          {upNext.map((t, i) => (
            <button
              key={`${t.id}-${i}`}
              type="button"
              className="queue-row"
              onClick={() => q.jumpTo(q.index + 1 + i)}
            >
              {t.cover_url ? <img src={t.cover_url} alt="" /> : <div className="q-art" />}
              <span className="queue-meta">
                <span className="queue-title">{t.title}</span>
                <span className="muted tiny">{t.artist_name}</span>
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
