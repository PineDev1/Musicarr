import { Link } from 'react-router-dom'
import type { ReactNode } from 'react'
import { IconPlay, IconUser } from './icons'
import type { PlayerAlbum, PlayerArtist, PlayerTrack } from './playerApi'
import { formatTime, usePlayerQueue } from './PlayerQueueContext'
import { TrackMenu } from './TrackMenu'

export function Section({
  title,
  subtitle,
  action,
  children,
}: {
  title: string
  subtitle?: string
  action?: ReactNode
  children: ReactNode
}) {
  return (
    <section className="am-section">
      <div className="am-section-head">
        <div>
          <h2>{title}</h2>
          {subtitle && <p className="muted tiny">{subtitle}</p>}
        </div>
        {action}
      </div>
      {children}
    </section>
  )
}

export function AlbumCard({ album }: { album: PlayerAlbum }) {
  const year = (album.release_date || '').slice(0, 4)
  return (
    <Link to={`/player/albums/${album.id}`} className="am-card">
      <div className="am-cover-lg">
        {album.cover_url ? <img src={album.cover_url} alt="" /> : <span className="am-cover-ph" />}
      </div>
      <strong className="truncate">{album.title}</strong>
      <span className="muted tiny truncate">
        {album.artist_name}
        {year ? ` · ${year}` : ''}
      </span>
    </Link>
  )
}

export function AlbumShelf({ albums }: { albums: PlayerAlbum[] }) {
  if (!albums.length) return null
  return (
    <div className="am-shelf">
      {albums.map((a) => (
        <AlbumCard key={a.id} album={a} />
      ))}
    </div>
  )
}

export function ArtistShelf({ artists }: { artists: PlayerArtist[] }) {
  if (!artists.length) return null
  return (
    <div className="am-shelf">
      {artists.map((a) => (
        <Link key={a.id} to={`/player/artists/${a.id}`} className="am-card artist">
          <div className="am-cover-lg round">
            {a.image_url ? <img src={a.image_url} alt="" /> : <IconUser size={34} />}
          </div>
          <strong className="truncate">{a.name}</strong>
          <span className="muted tiny">
            {a.album_count} album{a.album_count === 1 ? '' : 's'}
          </span>
        </Link>
      ))}
    </div>
  )
}

export function SongRow({
  track,
  queue,
  sourceLabel,
  number,
  showArt = true,
  hideNavigation,
  onRemove,
  removeLabel,
}: {
  track: PlayerTrack
  queue: PlayerTrack[]
  sourceLabel?: string
  number?: number
  showArt?: boolean
  hideNavigation?: boolean
  onRemove?: () => void
  removeLabel?: string
}) {
  const q = usePlayerQueue()
  const play = () => q.playTrack(track, queue, sourceLabel)
  const isFlac = track.format === 'flac' || track.quality === 'flac'

  return (
    <div
      className="am-song-row"
      role="button"
      tabIndex={0}
      onClick={play}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          play()
        }
      }}
    >
      {number != null && <span className="am-song-no">{number}</span>}
      {showArt &&
        (track.cover_url ? (
          <img src={track.cover_url} alt="" className="am-song-art" />
        ) : (
          <div className="am-song-art q-art" />
        ))}
      <div className="am-song-meta">
        <strong className="truncate">{track.title}</strong>
        <span className="muted tiny truncate">
          {track.artist_name}
          {track.album_title ? ` — ${track.album_title}` : ''}
        </span>
      </div>
      {isFlac && <span className="badge flac">FLAC</span>}
      <span className="muted tiny am-song-time">{formatTime(track.duration)}</span>
      <div className="am-song-actions">
        <button type="button" className="pill-icon-btn" aria-label="Play" onClick={play}>
          <IconPlay size={16} />
        </button>
        <TrackMenu
          track={track}
          queue={queue}
          hideNavigation={hideNavigation}
          onRemove={onRemove}
          removeLabel={removeLabel}
        />
      </div>
    </div>
  )
}

export function SongShelf({
  tracks,
  sourceLabel,
}: {
  tracks: PlayerTrack[]
  sourceLabel?: string
}) {
  const q = usePlayerQueue()
  if (!tracks.length) return null
  return (
    <div className="am-shelf">
      {tracks.map((t) => (
        <div key={t.id} className="am-card song">
          <button
            type="button"
            className="am-cover-lg as-button"
            aria-label={`Play ${t.title}`}
            onClick={() => q.playTrack(t, tracks, sourceLabel)}
          >
            {t.cover_url ? <img src={t.cover_url} alt="" /> : <span className="am-cover-ph" />}
            <span className="am-cover-play">
              <IconPlay size={20} />
            </span>
          </button>
          <strong className="truncate">{t.title}</strong>
          <span className="muted tiny truncate">{t.artist_name}</span>
        </div>
      ))}
    </div>
  )
}
