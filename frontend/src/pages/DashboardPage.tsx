import { useQuery } from '@tanstack/react-query'
import { api } from '../api'
import { Sparkline } from '../components/Sparkline'
import { SetupChecklist } from './SetupChecklist'

function formatWhen(iso: string) {
  const raw = iso?.endsWith('Z') || /[+-]\d{2}:\d{2}$/.test(iso || '') ? iso : `${iso}Z`
  const d = new Date(raw)
  if (Number.isNaN(d.getTime())) return iso || '—'
  return d.toLocaleString()
}

function formatBytes(n: number) {
  if (!n) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let i = 0
  let v = n
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024
    i += 1
  }
  return `${v.toFixed(v >= 10 || i === 0 ? 0 : 1)} ${units[i]}`
}

const STATUS_LABELS: Record<string, string> = {
  downloaded: 'Downloaded',
  wanted: 'Wanted',
  skipped: 'Skipped',
  missing: 'Missing',
}

export function DashboardPage() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['stats'],
    queryFn: api.stats,
  })
  const history = useQuery({
    queryKey: ['stats-history'],
    queryFn: api.statsHistory,
  })

  if (isLoading) return <p className="muted">Loading…</p>
  if (error) return <p className="error">{(error as Error).message}</p>
  if (!data) return null

  const maxStorage = Math.max(1, ...(history.data?.storage_by_quality.map((r) => r.bytes) || [1]))
  const maxGenre = Math.max(1, ...(history.data?.top_genres.map((r) => r.track_count) || [1]))

  return (
    <div>
      <div className="page-header">
        <div>
          <h1>Dashboard</h1>
          <p>A library-wide overview.</p>
        </div>
      </div>

      <SetupChecklist />

      <div className="stat-grid">
        <div className="stat-card">
          <span className="stat-value">{data.artists}</span>
          <span className="muted">Artists</span>
        </div>
        <div className="stat-card">
          <span className="stat-value">{data.tracks}</span>
          <span className="muted">Tracks</span>
        </div>
        <div className="stat-card">
          <span className="stat-value">{formatBytes(data.disk_usage_bytes)}</span>
          <span className="muted">Disk usage</span>
        </div>
        <div className="stat-card">
          <span className="stat-value">
            {data.success_rate_30d == null ? '—' : `${Math.round(data.success_rate_30d * 100)}%`}
          </span>
          <span className="muted">Download success (30d)</span>
        </div>
      </div>

      <h2 className="section-label">Albums by status</h2>
      <div className="stat-grid">
        {Object.entries(data.albums_by_status).map(([status, count]) => (
          <div className="stat-card" key={status}>
            <span className="stat-value">{count}</span>
            <span className="muted">{STATUS_LABELS[status] || status}</span>
          </div>
        ))}
        {!Object.keys(data.albums_by_status).length && (
          <p className="muted">No albums yet.</p>
        )}
      </div>

      {history.data && (
        <>
          <h2 className="section-label">Growth (last 90 days)</h2>
          <div className="card">
            <Sparkline
              series={[
                {
                  label: 'Artists added',
                  color: 'var(--accent)',
                  values: history.data.growth.map((p) => p.artists_added),
                },
                {
                  label: 'Albums downloaded',
                  color: 'var(--wanted)',
                  values: history.data.growth.map((p) => p.albums_downloaded),
                },
              ]}
            />
            <div className="muted tiny" style={{ marginTop: '0.5rem', display: 'flex', gap: '1rem' }}>
              <span>
                <span style={{ color: 'var(--accent)' }}>●</span> Artists added
              </span>
              <span>
                <span style={{ color: 'var(--wanted)' }}>●</span> Albums downloaded
              </span>
            </div>
          </div>

          <h2 className="section-label">Download trend (last 30 days)</h2>
          <div className="card">
            <Sparkline
              series={[
                {
                  label: 'Completed',
                  color: 'var(--downloaded)',
                  values: history.data.download_trend.map((p) => p.completed),
                },
                {
                  label: 'Failed',
                  color: 'var(--danger)',
                  values: history.data.download_trend.map((p) => p.failed),
                },
              ]}
            />
            <div className="muted tiny" style={{ marginTop: '0.5rem', display: 'flex', gap: '1rem' }}>
              <span>
                <span style={{ color: 'var(--downloaded)' }}>●</span> Completed
              </span>
              <span>
                <span style={{ color: 'var(--danger)' }}>●</span> Failed
              </span>
            </div>
          </div>

          {!!history.data.storage_by_quality.length && (
            <>
              <h2 className="section-label">Storage by quality</h2>
              <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                {history.data.storage_by_quality.map((row) => (
                  <div key={row.quality}>
                    <div className="muted tiny" style={{ marginBottom: '0.15rem' }}>
                      {row.quality.toUpperCase()} — {formatBytes(row.bytes)}
                    </div>
                    <div style={{ background: 'var(--bg-soft)', borderRadius: 4, height: 8 }}>
                      <div
                        style={{
                          width: `${(row.bytes / maxStorage) * 100}%`,
                          background: 'var(--accent)',
                          height: 8,
                          borderRadius: 4,
                        }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            </>
          )}

          {!!history.data.top_genres.length && (
            <>
              <h2 className="section-label">Top genres</h2>
              <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                {history.data.top_genres.map((row) => (
                  <div key={row.genre}>
                    <div className="muted tiny" style={{ marginBottom: '0.15rem' }}>
                      {row.genre} — {row.track_count} track{row.track_count === 1 ? '' : 's'}
                    </div>
                    <div style={{ background: 'var(--bg-soft)', borderRadius: 4, height: 8 }}>
                      <div
                        style={{
                          width: `${(row.track_count / maxGenre) * 100}%`,
                          background: 'var(--accent)',
                          height: 8,
                          borderRadius: 4,
                        }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            </>
          )}
        </>
      )}

      <h2 className="section-label">Recent activity</h2>
      {!data.recent_events.length && <p className="muted">Nothing recent.</p>}
      {!!data.recent_events.length && (
        <table className="table">
          <thead>
            <tr>
              <th>When</th>
              <th>Type</th>
              <th>Message</th>
            </tr>
          </thead>
          <tbody>
            {data.recent_events.map((ev, i) => (
              <tr key={i}>
                <td className="muted" style={{ whiteSpace: 'nowrap' }}>
                  {formatWhen(ev.created_at)}
                </td>
                <td>
                  <span className="badge queued">{ev.event_type}</span>
                </td>
                <td>{ev.message}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
