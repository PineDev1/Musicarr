import { useQuery } from '@tanstack/react-query'
import { api } from '../api'

export function ActivityPage() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['history'],
    queryFn: api.history,
    refetchInterval: 5000,
  })

  return (
    <div>
      <div className="page-header">
        <div>
          <h1>Activity</h1>
          <p>Recent library and download events.</p>
        </div>
      </div>
      {isLoading && <p className="muted">Loading…</p>}
      {error && <p className="error">{(error as Error).message}</p>}
      {data && data.length === 0 && <p className="muted">No activity yet.</p>}
      <table className="table">
        <thead>
          <tr>
            <th>When</th>
            <th>Type</th>
            <th>Message</th>
          </tr>
        </thead>
        <tbody>
          {data?.map((ev) => (
            <tr key={ev.id}>
              <td className="muted">{new Date(ev.created_at).toLocaleString()}</td>
              <td>
                <span className="badge queued">{ev.event_type}</span>
              </td>
              <td>{ev.message}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
