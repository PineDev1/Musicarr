import { useQuery } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'
import { playerApi } from './playerApi'

export function PlayerArtistPage() {
  const { id } = useParams()
  const artistId = Number(id)
  const { data, isLoading, error } = useQuery({
    queryKey: ['player-artist-albums', artistId],
    queryFn: () => playerApi.artistAlbums(artistId),
    enabled: Number.isFinite(artistId),
  })

  if (isLoading) return <p className="muted">Loading…</p>
  if (error) return <p className="error">{(error as Error).message}</p>

  return (
    <div>
      <p className="muted">
        <Link to="/player">Library</Link>
      </p>
      <h1>Albums</h1>
      <div className="album-list">
        {data?.map((album) => (
          <Link key={album.id} to={`/player/albums/${album.id}`} className="album-row">
            {album.cover_url ? (
              <img src={album.cover_url} alt="" />
            ) : (
              <div className="placeholder-art" style={{ width: 64, height: 64 }} />
            )}
            <div>
              <strong>{album.title}</strong>
              <div className="muted">
                {album.release_date || 'Unknown date'} · {album.track_count} tracks
                {album.quality ? ` · ${album.quality.toUpperCase()}` : ''}
              </div>
            </div>
          </Link>
        ))}
      </div>
    </div>
  )
}
