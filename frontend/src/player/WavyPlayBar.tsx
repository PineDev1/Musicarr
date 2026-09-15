import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState, type CSSProperties } from 'react'
import {
  IconHeart,
  IconMoon,
  IconNext,
  IconPause,
  IconPlay,
  IconPrev,
  IconQueue,
  IconRepeat,
  IconShuffle,
} from './icons'
import { DEFAULT_PREFS, playerApi } from './playerApi'
import { ExpandedNowPlaying } from './ExpandedNowPlaying'
import {
  TOGGLE_LOVE_EVENT,
  TOGGLE_QUEUE_EVENT,
  formatTime,
  usePlayerQueue,
} from './PlayerQueueContext'
import { QueueDrawer } from './QueueDrawer'
import { WavySeekBar } from './WavySeekBar'

export function WavyPlayBar() {
  const q = usePlayerQueue()
  const qc = useQueryClient()
  const [queueOpen, setQueueOpen] = useState(false)
  const [expanded, setExpanded] = useState(false)
  const track = q.tracks[q.index]
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

  const loveRef = useRef(toggleFav.mutate)
  useEffect(() => {
    loveRef.current = toggleFav.mutate
  }, [toggleFav.mutate])

  useEffect(() => {
    const onToggleQueue = () => setQueueOpen((o) => !o)
    const onToggleLove = () => loveRef.current()
    window.addEventListener(TOGGLE_QUEUE_EVENT, onToggleQueue)
    window.addEventListener(TOGGLE_LOVE_EVENT, onToggleLove)
    return () => {
      window.removeEventListener(TOGGLE_QUEUE_EVENT, onToggleQueue)
      window.removeEventListener(TOGGLE_LOVE_EVENT, onToggleLove)
    }
  }, [])

  const wave = prefs.data || DEFAULT_PREFS
  const isFlac = track && (track.format === 'flac' || track.quality === 'flac')
  const volPct = Math.round(q.volume * 100)

  return (
    <>
      <div className={`pill-player${track ? '' : ' empty'}${expanded ? ' sheet-open' : ''}`}>
        {track ? (
          <>
            {/* Mobile mini bar — Apple Music style */}
            <button
              type="button"
              className="pill-mini"
              aria-label="Open now playing"
              onClick={() => setExpanded(true)}
            >
              {track.cover_url ? (
                <img src={track.cover_url} alt="" className="pill-art" key={track.id} />
              ) : (
                <div className="pill-art placeholder" />
              )}
              <div className="pill-text">
                <div className="pill-title">{track.title}</div>
                <div className="pill-sub">{track.artist_name}</div>
              </div>
            </button>
            <div className="pill-mini-transport">
              <button
                type="button"
                className="pill-icon-btn"
                aria-label="Previous"
                onClick={(e) => {
                  e.stopPropagation()
                  q.prev()
                }}
              >
                <IconPrev size={22} />
              </button>
              <button
                type="button"
                className="pill-play sm"
                aria-label={q.playing ? 'Pause' : 'Play'}
                onClick={(e) => {
                  e.stopPropagation()
                  q.togglePlay()
                }}
              >
                {q.playing ? <IconPause size={18} /> : <IconPlay size={18} />}
              </button>
              <button
                type="button"
                className="pill-icon-btn"
                aria-label="Next"
                onClick={(e) => {
                  e.stopPropagation()
                  q.next()
                }}
              >
                <IconNext size={22} />
              </button>
            </div>

            {/* Desktop full bar */}
            <div className="pill-meta pill-desktop">
              <button
                type="button"
                className="pill-art-btn"
                aria-label="Expand now playing"
                onClick={() => setExpanded(true)}
              >
                {track.cover_url ? (
                  <img src={track.cover_url} alt="" className="pill-art" key={`d-${track.id}`} />
                ) : (
                  <div className="pill-art placeholder" />
                )}
              </button>
              <button
                type="button"
                className="pill-text pill-text-btn"
                aria-label="Expand now playing"
                onClick={() => setExpanded(true)}
              >
                <div className="pill-title">{track.title}</div>
                <div className="pill-sub">
                  {track.artist_name}
                  {isFlac && <span className="badge flac">FLAC</span>}
                </div>
                {q.sourceLabel && (
                  <div className="pill-source">Playing from {q.sourceLabel}</div>
                )}
              </button>
              <button
                type="button"
                className={`pill-icon-btn heart${liked ? ' on' : ''}`}
                aria-label={liked ? 'Unlike' : 'Like'}
                onClick={() => toggleFav.mutate()}
              >
                <IconHeart filled={liked} size={18} />
              </button>
            </div>

            <div className="pill-main pill-desktop">
              <WavySeekBar
                value={q.currentTime}
                max={q.duration || 1}
                playing={q.playing}
                prefs={wave}
                onSeek={q.seek}
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
                  <IconShuffle size={18} />
                </button>
                <button type="button" className="pill-icon-btn" aria-label="Previous" onClick={q.prev}>
                  <IconPrev size={20} />
                </button>
                <button
                  type="button"
                  className="pill-play"
                  aria-label={q.playing ? 'Pause' : 'Play'}
                  onClick={q.togglePlay}
                >
                  {q.playing ? <IconPause size={22} /> : <IconPlay size={22} />}
                </button>
                <button type="button" className="pill-icon-btn" aria-label="Next" onClick={q.next}>
                  <IconNext size={20} />
                </button>
                <button
                  type="button"
                  className={`pill-icon-btn${q.repeat !== 'off' ? ' on' : ''}`}
                  aria-label="Repeat"
                  onClick={q.cycleRepeat}
                >
                  <IconRepeat size={18} />
                  {q.repeat === 'one' && <span className="rep-one">1</span>}
                </button>
              </div>
            </div>

            <div className="pill-side pill-desktop">
              <label className="pill-vol-wrap">
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
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-valuenow={volPct}
                  className="pill-vol"
                  style={{ '--vol': `${volPct}%` } as CSSProperties}
                />
              </label>
              <button
                type="button"
                className={`pill-icon-btn${q.sleepMode != null ? ' on' : ''}`}
                aria-label="Sleep timer"
                title="Sleep timer"
                onClick={() => setExpanded(true)}
              >
                <IconMoon size={18} />
              </button>
              <button
                type="button"
                className="pill-icon-btn"
                aria-label="Queue"
                onClick={() => setQueueOpen((o) => !o)}
              >
                <IconQueue size={18} />
              </button>
            </div>
          </>
        ) : (
          <span className="muted">Nothing playing</span>
        )}
      </div>

      {queueOpen && <QueueDrawer onClose={() => setQueueOpen(false)} />}
      {expanded && track && <ExpandedNowPlaying onClose={() => setExpanded(false)} />}
    </>
  )
}
