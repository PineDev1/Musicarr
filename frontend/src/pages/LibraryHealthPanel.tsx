import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'

export function LibraryHealthPanel() {
  const [open, setOpen] = useState<string | null>(null)
  const q = useQuery({ queryKey: ['library-health'], queryFn: api.libraryHealth })

  return (
    <div className="card" style={{ marginTop: '1.5rem' }}>
      <div className="page-header" style={{ marginBottom: 8 }}>
        <div>
          <h2 style={{ margin: 0 }}>Library health</h2>
          <p className="muted tiny" style={{ margin: 0 }}>
            Albums and artists that need a look: nothing here changes your files.
          </p>
        </div>
        <button type="button" className="btn secondary" onClick={() => q.refetch()} disabled={q.isFetching}>
          {q.isFetching ? 'Scanning…' : 'Rescan'}
        </button>
      </div>
      {q.isLoading && <p className="muted">Scanning…</p>}
      {q.error && <p className="error">{(q.error as Error).message}</p>}
      {q.data && q.data.total_issues === 0 && <p className="muted">No problems found.</p>}
      {q.data?.sections
        .filter((s) => s.count > 0)
        .map((s) => (
          <div key={s.key} style={{ borderTop: '1px solid var(--border)', padding: '0.6rem 0' }}>
            <button
              type="button"
              className="btn ghost"
              onClick={() => setOpen(open === s.key ? null : s.key)}
              style={{ width: '100%', display: 'flex', justifyContent: 'space-between' }}
            >
              <span>
                <strong>{s.label}</strong> <span className="badge queued">{s.count}</span>
              </span>
              <span>{open === s.key ? '▾' : '▸'}</span>
            </button>
            {open === s.key && (
              <>
                <p className="muted tiny">{s.hint}</p>
                <table className="table">
                  <tbody>
                    {s.items.map((it, i) => (
                      <tr key={`${it.album_id ?? 'a'}-${it.artist_id}-${i}`}>
                        <td>
                          <Link to={`/artists/${it.artist_id}`}>{it.artist_name}</Link>
                          {it.title ? <> · {it.title}</> : null}
                        </td>
                        <td className="muted">{it.detail}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {s.count > s.items.length && (
                  <p className="muted tiny">
                    Showing the first {s.items.length} of {s.count}.
                  </p>
                )}
              </>
            )}
          </div>
        ))}
    </div>
  )
}
