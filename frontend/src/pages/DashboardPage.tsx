import { useQuery } from '@tanstack/react-query'
import { api } from '../api'

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

  if (isLoading) return <p className="muted">Loading…</p>
  if (error) return <p className="error">{(error as Error).message}</p>
  if (!data) return null

  return (
    <div>
      <div className="page-header">
        <div>
          <h1>Dashboard</h1>
          <p>A library-wide overview.</p>
        </div>
      </div>

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
