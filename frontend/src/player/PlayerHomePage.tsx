import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { playerApi } from './playerApi'

export function PlayerHomePage() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['player-artists'],
    queryFn: playerApi.artists,
  })

  if (isLoading) return <p className="muted">Loading library…</p>
  if (error) return <p className="error">{(error as Error).message}</p>

  return (
    <div>
      <div className="page-header">
        <div>
          <h1>Library</h1>
          <p>Downloaded music — streamed at original quality (FLAC when available).</p>
        </div>
      </div>
      {!data?.length && <p className="muted">No playable tracks yet. Download albums in Musicarr first.</p>}
      <div className="grid">
        {data?.map((a) => (
          <Link key={a.id} to={`/player/artists/${a.id}`} className="artist-tile">
            {a.image_url ? <img src={a.image_url} alt="" /> : <div className="placeholder-art">No art</div>}
            <div className="name">{a.name}</div>
            <div className="meta">{a.album_count} albums</div>
          </Link>
        ))}
      </div>
    </div>
  )
}
