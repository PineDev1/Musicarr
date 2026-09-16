import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useRef } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { useToast } from '../Toast'
import { playerApi } from './playerApi'
import { IconHeart } from './icons'

export function PlayerPlaylistsPage() {
  const qc = useQueryClient()
  const navigate = useNavigate()
  const toast = useToast()
  const fileRef = useRef<HTMLInputElement | null>(null)
  const builtins = useQuery({ queryKey: ['player-builtins'], queryFn: playerApi.builtins })
  const { data, isLoading, error } = useQuery({
    queryKey: ['player-playlists'],
    queryFn: playerApi.playlists,
  })
  const remove = useMutation({
    mutationFn: (id: number) => playerApi.deletePlaylist(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['player-playlists'] }),
  })
  const importM3u = useMutation({
    mutationFn: (file: File) => playerApi.importPlaylist(file),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ['player-playlists'] })
      toast.push(`Imported ${res.matched}/${res.total} tracks`, 'ok')
      navigate(`/player/playlists/${res.playlist_id}`)
    },
    onError: (err) => toast.push((err as Error).message, 'error'),
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
        <button type="button" className="btn secondary" onClick={() => fileRef.current?.click()}>
          Import M3U
        </button>
        <input
          ref={fileRef}
          type="file"
          accept=".m3u,.m3u8,audio/x-mpegurl"
          style={{ display: 'none' }}
          onChange={(e) => {
            const file = e.target.files?.[0]
            if (file) importM3u.mutate(file)
            e.target.value = ''
          }}
        />
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
