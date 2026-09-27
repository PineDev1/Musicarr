import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { api } from '../api'

function dayLabel(iso: string) {
  const d = new Date(`${iso}T00:00:00`)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' })
}

export function DiscoverPage() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['discovery'],
    queryFn: api.discovery,
  })

  if (isLoading) return <p className="muted">Loading…</p>
  if (error) return <p className="error">{(error as Error).message}</p>
  if (!data) return null

  return (
    <div>
      <div className="page-header">
        <div>
          <h1>Discover</h1>
          <p>Recommendations and upcoming releases based on the artists you follow.</p>
        </div>
      </div>

      <h2 className="section-label">You might also like</h2>
      {!data.similar_artists.length && (
        <p className="muted">
          No suggestions yet — follow a few artists, or add a Last.fm API key under
          Settings → Notifications.
        </p>
      )}
      {!!data.similar_artists.length && (
        <div className="card" style={{ display: 'flex', flexWrap: 'wrap', gap: '0.6rem' }}>
          {data.similar_artists.map((s, i) => (
            <span key={`${s.name}-${i}`} className="badge" title={`Because you follow ${s.seed_artist_name}`}>
              {s.already_in_library ? (
                <Link to={`/artists/${s.already_in_library}`}>{s.name}</Link>
              ) : (
                <Link to={`/add?q=${encodeURIComponent(s.name)}`}>{s.name}</Link>
              )}
            </span>
          ))}
        </div>
      )}

      <h2 className="section-label" style={{ marginTop: '1.5rem' }}>
        Coming up from artists you follow
      </h2>
      {!data.upcoming.length && <p className="muted">Nothing upcoming right now.</p>}
      {!!data.upcoming.length && (
        <table className="table">
          <tbody>
            {data.upcoming.map((entry) => (
              <tr key={entry.album_id}>
                <td className="muted" style={{ whiteSpace: 'nowrap' }}>
                  {entry.release_date ? dayLabel(entry.release_date) : '—'}
                </td>
                <td>
                  <Link to={`/albums/${entry.album_id}`}>{entry.title}</Link>
                </td>
                <td className="muted">
                  <Link to={`/artists/${entry.artist_id}`}>{entry.artist_name}</Link>
                </td>
                <td>
                  <span className={`badge ${entry.status}`}>{entry.status}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
