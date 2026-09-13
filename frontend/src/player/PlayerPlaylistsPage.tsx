import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { playerApi } from './playerApi'
import { IconHeart } from './icons'

export function PlayerPlaylistsPage() {
  const qc = useQueryClient()
  const builtins = useQuery({ queryKey: ['player-builtins'], queryFn: playerApi.builtins })
  const { data, isLoading, error } = useQuery({
    queryKey: ['player-playlists'],
    queryFn: playerApi.playlists,
  })
  const remove = useMutation({
    mutationFn: (id: number) => playerApi.deletePlaylist(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['player-playlists'] }),
  })

  if (isLoading) return <p className="muted">Loading…</p>
  if (error) return <p className="error">{(error as Error).message}</p>

  return (
    <div>
      <div className="page-header">
        <div>
          <h1>Playlists</h1>
          <p>Built-in mixes and your collections. Use + to create one.</p>
        </div>
      </div>

      <h2 className="section-label">Library mixes</h2>
      <div className="playlist-grid">
        {builtins.data?.map((p) => (
          <Link key={String(p.id)} to={`/player/playlists/${p.id}`} className="playlist-card builtin">
            <div className="playlist-card-art">
              {p.kind === 'liked' ? <IconHeart filled size={28} /> : null}
              {p.kind !== 'liked' && <span className="playlist-glyph">{(p.name[0] || 'P').toUpperCase()}</span>}
            </div>
            <strong>{p.name}</strong>
            <span className="muted">{p.track_count} tracks</span>
          </Link>
        ))}
      </div>

      <h2 className="section-label">Yours</h2>
      <div className="playlist-grid">
        {data?.map((p) => (
          <div key={p.id} className="playlist-card">
            <Link to={`/player/playlists/${p.id}`} className="playlist-card-link">
              <div className="playlist-card-art">
                <span className="playlist-glyph">{(p.name[0] || 'P').toUpperCase()}</span>
              </div>
              <strong>
                {p.name}
                {p.is_smart ? <span className="badge flac">Smart</span> : null}
              </strong>
              <span className="muted">{p.track_count} tracks</span>
            </Link>
            <button
              type="button"
              className="pill-icon-btn danger"
              aria-label="Delete"
              onClick={() => remove.mutate(Number(p.id))}
            >
              ×
            </button>
          </div>
        ))}
        {!data?.length && <p className="muted">No playlists yet — tap + to create one.</p>}
      </div>
    </div>
  )
}
