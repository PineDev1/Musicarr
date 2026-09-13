import { useQuery } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'
import { IconPlay, IconShuffle } from './icons'
import { playerApi } from './playerApi'
import { formatTime, usePlayerQueue } from './PlayerQueueContext'
import { AlbumShelf, Section, SongRow } from './PlayerShelves'

export function PlayerAlbumPage() {
  const { id } = useParams()
  const albumId = Number(id)
  const q = usePlayerQueue()
  const { data, isLoading, error } = useQuery({
    queryKey: ['player-album', albumId],
    queryFn: () => playerApi.album(albumId),
    enabled: Number.isFinite(albumId),
  })
  const artist = useQuery({
    queryKey: ['player-artist', data?.artist_id],
    queryFn: () => playerApi.artistDetail(data!.artist_id),
    enabled: !!data?.artist_id,
  })

  if (isLoading) return <p className="muted">Loading…</p>
  if (error) return <p className="error">{(error as Error).message}</p>
  if (!data) return null

  const year = (data.release_date || '').slice(0, 4)
  const totalSeconds = data.tracks.reduce((sum, t) => sum + (t.duration || 0), 0)
  const moreByArtist = (artist.data?.albums || []).filter((a) => a.id !== data.id).slice(0, 12)

  return (
    <div className="am-page">
      <header className="am-album-hero">
        <div className="am-album-cover">
          {data.cover_url ? <img src={data.cover_url} alt="" /> : <div className="am-cover-ph" />}
        </div>
        <div className="am-album-info">
          <h1>{data.title}</h1>
          <p className="am-album-artist">
            <Link to={`/player/artists/${data.artist_id}`}>{data.artist_name}</Link>
          </p>
          <p className="muted tiny">
            {year || 'Unknown year'} · {data.track_count} song{data.track_count === 1 ? '' : 's'}
            {totalSeconds ? ` · ${formatTime(totalSeconds)}` : ''}
            {data.quality ? ` · ${data.quality.toUpperCase()}` : ''}
          </p>
          <div className="toolbar">
            <button
              type="button"
              className="btn"
              disabled={!data.tracks.length}
              onClick={() => q.playTracks(data.tracks, 0, data.title)}
            >
              <IconPlay size={16} /> Play
            </button>
            <button
              type="button"
              className="btn secondary"
              disabled={!data.tracks.length}
              onClick={() => {
                if (!q.shuffle) q.toggleShuffle()
                q.playTracks(data.tracks, 0, data.title)
              }}
            >
              <IconShuffle size={16} /> Shuffle
            </button>
          </div>
        </div>
      </header>

      <div className="am-song-list bordered">
        {data.tracks.map((t, i) => (
          <SongRow
            key={t.id}
            track={t}
            queue={data.tracks}
            sourceLabel={data.title}
            number={t.track_no || i + 1}
            showArt={false}
            hideNavigation
          />
        ))}
        {!data.tracks.length && <p className="muted">No playable files in this album yet.</p>}
      </div>

      {!!moreByArtist.length && (
        <Section title={`More by ${data.artist_name}`}>
          <AlbumShelf albums={moreByArtist} />
        </Section>
      )}
    </div>
  )
}
