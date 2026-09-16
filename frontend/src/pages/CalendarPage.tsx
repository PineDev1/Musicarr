import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { api, type CalendarEntry } from '../api'

function monthLabel(iso: string) {
  const d = new Date(`${iso}T00:00:00`)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleDateString(undefined, { month: 'long', year: 'numeric' })
}

function dayLabel(iso: string) {
  const d = new Date(`${iso}T00:00:00`)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' })
}

function groupByMonth(entries: CalendarEntry[]) {
  const groups: { month: string; entries: CalendarEntry[] }[] = []
  for (const entry of entries) {
    const key = entry.release_date ? monthLabel(entry.release_date) : 'Unknown date'
    let group = groups.find((g) => g.month === key)
    if (!group) {
      group = { month: key, entries: [] }
      groups.push(group)
    }
    group.entries.push(entry)
  }
  return groups
}

export function CalendarPage() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['calendar'],
    queryFn: api.calendar,
  })
  const today = new Date().toISOString().slice(0, 10)

  if (isLoading) return <p className="muted">Loading…</p>
  if (error) return <p className="error">{(error as Error).message}</p>

  const groups = groupByMonth(data || [])

  return (
    <div>
      <div className="page-header">
        <div>
          <h1>Release Calendar</h1>
          <p>Upcoming and recent releases from your monitored artists.</p>
        </div>
      </div>

      {!groups.length && <p className="muted">Nothing on the calendar right now.</p>}

      {groups.map((group) => (
        <div key={group.month}>
          <h2 className="section-label">{group.month}</h2>
          <table className="table">
            <tbody>
              {group.entries.map((entry) => (
                <tr key={entry.album_id} className={entry.release_date === today ? 'active' : ''}>
                  <td className="muted" style={{ whiteSpace: 'nowrap' }}>
                    {entry.release_date ? dayLabel(entry.release_date) : '—'}
                    {entry.release_date === today && (
                      <span className="badge queued" style={{ marginLeft: '0.5rem' }}>
                        Today
                      </span>
                    )}
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
        </div>
      ))}
    </div>
  )
}
