import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { useToast } from '../Toast'

export function ImportReviewPage() {
  const qc = useQueryClient()
  const toast = useToast()
  const { data, isLoading, error } = useQuery({
    queryKey: ['import-review'],
    queryFn: () => api.importReview(true),
  })

  const link = useMutation({
    mutationFn: ({
      artistId,
      providerId,
      provider,
    }: {
      artistId: number
      providerId: string
      provider?: string
    }) => api.linkImportArtist(artistId, providerId, provider),
    onSuccess: (artist) => {
      toast.push(`Linked ${artist.name}`, 'ok')
      qc.invalidateQueries({ queryKey: ['import-review'] })
      qc.invalidateQueries({ queryKey: ['artists'] })
      qc.invalidateQueries({ queryKey: ['health'] })
    },
    onError: (err) => toast.push((err as Error).message, 'error'),
  })

  if (isLoading) return <p className="muted">Loading…</p>
  if (error) return <p className="error">{(error as Error).message}</p>

  const locals = data?.local_artists || []
  const weak = data?.weak_albums || []

  return (
    <div>
      <div className="page-header">
        <div>
          <p className="muted" style={{ marginBottom: '0.5rem' }}>
            <Link to="/settings">Settings</Link> / Import review
          </p>
          <h1>Import review</h1>
          <p>
            Fix local-only artists and weakly tagged folders after importing an existing library.
          </p>
        </div>
      </div>

      {data?.message && <p className="muted">{data.message}</p>}

      <h2 style={{ marginTop: '1.75rem', fontSize: '1.25rem' }}>Local artists</h2>
      {locals.length === 0 && <p className="muted">No local-only artists — nothing to link.</p>}
      <div className="album-list" style={{ marginTop: '0.75rem' }}>
        {locals.map((artist) => (
          <div key={artist.id} className="album-row" style={{ alignItems: 'flex-start' }}>
            <div style={{ minWidth: 0, flex: 1 }}>
              <div>
                <Link to={`/artists/${artist.id}`}>
                  <strong>{artist.name}</strong>
                </Link>{' '}
                <span className="badge queued">local</span>
              </div>
              <div className="muted">
                {artist.album_count} album(s) · {artist.reason}
              </div>
              {artist.suggestions.length > 0 && (
                <div style={{ marginTop: '0.65rem' }}>
                  <div className="muted" style={{ marginBottom: 6, fontSize: '0.85rem' }}>
                    Provider matches
                  </div>
                  <div className="toolbar" style={{ flexWrap: 'wrap', marginBottom: 0 }}>
                    {artist.suggestions.map((s) => (
                      <button
                        key={`${s.provider}-${s.provider_id}`}
                        className="btn secondary"
                        type="button"
                        disabled={link.isPending}
                        onClick={() =>
                          link.mutate({
                            artistId: artist.id,
                            providerId: s.provider_id,
                            provider: s.provider,
                          })
                        }
                      >
                        Link “{s.name}”
                        {s.nb_album != null ? ` (${s.nb_album})` : ''}
                      </button>
                    ))}
                  </div>
                </div>
              )}
              {artist.suggestions.length === 0 && (
                <p className="muted" style={{ marginTop: 8, fontSize: '0.85rem' }}>
                  No automatic suggestions. Search under Add Artist, then return here — or refresh
                  once the active source is connected.
                </p>
              )}
            </div>
          </div>
        ))}
      </div>

      <h2 style={{ marginTop: '2rem', fontSize: '1.25rem' }}>Weak albums</h2>
      {weak.length === 0 && <p className="muted">No weakly tagged albums flagged.</p>}
      {weak.length > 0 && (
        <table className="table" style={{ marginTop: '0.75rem' }}>
          <thead>
            <tr>
              <th>Album</th>
              <th>Artist</th>
              <th>Issue</th>
            </tr>
          </thead>
          <tbody>
            {weak.map((a) => (
              <tr key={a.id}>
                <td>
                  <Link to={`/albums/${a.id}`}>{a.title}</Link>
                </td>
                <td>
                  <Link to={`/artists/${a.artist_id}`}>{a.artist_name}</Link>
                </td>
                <td className="muted">{a.reason}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
