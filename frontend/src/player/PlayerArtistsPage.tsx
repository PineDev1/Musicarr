import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { IconUser } from './icons'
import { playerApi } from './playerApi'

export function PlayerArtistsPage() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['player-artists'],
    queryFn: playerApi.artists,
  })

  return (
    <div className="am-page">
      <div className="page-header">
        <div>
          <h1>Artists</h1>
          <p>{data ? `${data.length} artists with downloaded music` : 'Your library artists.'}</p>
        </div>
      </div>

      {isLoading && <p className="muted">Loading artists…</p>}
      {error && <p className="error">{(error as Error).message}</p>}
      {data && !data.length && (
        <p className="muted">No playable tracks yet. Download albums in Musicarr first.</p>
      )}

      <div className="am-grid">
        {data?.map((a) => (
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
    </div>
  )
}
