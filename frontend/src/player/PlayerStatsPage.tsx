import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { playerApi } from './playerApi'

function formatMinutes(seconds: number): string {
  const m = Math.round((seconds || 0) / 60)
  if (m < 60) return `${m} min`
  const h = Math.floor(m / 60)
  const rem = m % 60
  return rem ? `${h}h ${rem}m` : `${h}h`
}

export function PlayerStatsPage() {
  const stats = useQuery({
    queryKey: ['player-stats', 30],
    queryFn: () => playerApi.stats(30),
  })

  if (stats.isLoading) return <p className="muted">Loading stats…</p>
  if (stats.error) return <p className="error">{(stats.error as Error).message}</p>
  const data = stats.data
  if (!data) return null

  return (
    <div className="player-page">
      <div className="page-header">
        <div>
          <h1>Listening stats</h1>
          <p className="muted">Last {data.range_days} days</p>
        </div>
      </div>

      <div className="toolbar" style={{ gap: '1.5rem', flexWrap: 'wrap' }}>
        <div>
          <div className="muted">Plays</div>
          <strong style={{ fontSize: '1.4rem' }}>{data.play_events}</strong>
        </div>
        <div>
          <div className="muted">Tracks</div>
          <strong style={{ fontSize: '1.4rem' }}>{data.unique_tracks}</strong>
        </div>
        <div>
          <div className="muted">Artists</div>
          <strong style={{ fontSize: '1.4rem' }}>{data.unique_artists}</strong>
        </div>
        <div>
          <div className="muted">Time</div>
          <strong style={{ fontSize: '1.4rem' }}>{formatMinutes(data.total_seconds)}</strong>
        </div>
      </div>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
          gap: '1.5rem',
          marginTop: '1.5rem',
        }}
      >
        <section>
          <h2 style={{ fontSize: '1.1rem' }}>Top artists</h2>
          {data.top_artists.length === 0 && <p className="muted">No plays yet.</p>}
          <ol style={{ paddingLeft: '1.2rem', margin: 0 }}>
            {data.top_artists.map((a) => (
              <li key={a.artist_id} style={{ marginBottom: '0.5rem' }}>
                <Link to={`/player/artists/${a.artist_id}`}>
                  <strong>{a.name}</strong>
                </Link>
                <div className="muted" style={{ fontSize: '0.85rem' }}>
                  {a.plays} plays · {formatMinutes(a.seconds)}
                </div>
              </li>
            ))}
          </ol>
        </section>
        <section>
          <h2 style={{ fontSize: '1.1rem' }}>Top tracks</h2>
          {data.top_tracks.length === 0 && <p className="muted">No plays yet.</p>}
          <ol style={{ paddingLeft: '1.2rem', margin: 0 }}>
            {data.top_tracks.map((t) => (
              <li key={t.track_id} style={{ marginBottom: '0.5rem' }}>
                <strong>{t.title}</strong>
                <div className="muted" style={{ fontSize: '0.85rem' }}>
                  {t.artist_name} · {t.plays} plays
                </div>
              </li>
            ))}
          </ol>
        </section>
      </div>
    </div>
  )
}
