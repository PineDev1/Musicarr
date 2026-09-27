import { useQuery } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'
import { playerApi } from './playerApi'
import { usePlayerQueue } from './PlayerQueueContext'
import { SongRow } from './PlayerShelves'
import { IconPlay } from './icons'

export function PlayerGenreDetailPage({ kind }: { kind: 'genre' | 'mood' }) {
  const { name } = useParams()
  const q = usePlayerQueue()
  const decoded = name ? decodeURIComponent(name) : ''

  const { data, isLoading, error } = useQuery({
    queryKey: ['player', kind, decoded],
    queryFn: () => (kind === 'genre' ? playerApi.genre(decoded) : playerApi.mood(decoded)),
    enabled: !!decoded,
  })

  if (isLoading) return <p className="muted">Loading…</p>
  if (error) return <p className="error">{(error as Error).message}</p>
  if (!data) return null

  return (
    <div>
      <p className="muted">
        <Link to="/player/explore">Explore</Link> / {data.name}
      </p>
      <div className="page-header">
        <div>
          <h1>{data.name}</h1>
          <p className="muted">{data.track_count} tracks</p>
        </div>
        <button
          className="btn"
          type="button"
          disabled={!data.tracks.length}
          onClick={() => q.playTracks(data.tracks, 0, data.name)}
        >
          <IconPlay size={16} /> Play all
        </button>
      </div>

      <div className="am-song-list bordered">
        {data.tracks.map((t, i) => (
          <SongRow key={t.id} track={t} queue={data.tracks} sourceLabel={data.name} number={i + 1} />
        ))}
      </div>
    </div>
  )
}
