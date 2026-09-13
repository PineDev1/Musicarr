import { useQuery } from '@tanstack/react-query'
import { api } from '../api'

function formatWhen(iso: string) {
  const raw = iso?.endsWith('Z') || /[+-]\d{2}:\d{2}$/.test(iso || '') ? iso : `${iso}Z`
  const d = new Date(raw)
  if (Number.isNaN(d.getTime())) return iso || '—'
  return d.toLocaleString()
}

export function ActivityPage() {
  const { data, isLoading, error, isFetching, refetch } = useQuery({
    queryKey: ['history'],
    queryFn: api.history,
    refetchInterval: 5000,
    retry: 1,
  })

  return (
    <div>
      <div className="page-header">
        <div>
          <h1>Activity</h1>
          <p>Recent library and download events.</p>
        </div>
        <button type="button" className="btn secondary" onClick={() => refetch()} disabled={isFetching}>
          Refresh
        </button>
      </div>
      {isLoading && <p className="muted">Loading…</p>}
      {error && (
        <div className="banner warn">
          Couldn’t load activity: {(error as Error).message}
        </div>
      )}
      {!isLoading && !error && data && data.length === 0 && (
        <p className="muted">No activity yet. Downloads, imports, and settings changes show up here.</p>
      )}
      {!!data?.length && (
        <table className="table">
          <thead>
            <tr>
              <th>When</th>
              <th>Type</th>
              <th>Message</th>
            </tr>
          </thead>
          <tbody>
            {data.map((ev) => (
              <tr key={ev.id}>
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
