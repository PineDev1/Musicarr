import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { api } from '../api'

function formatBytes(n: number) {
  if (!n) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  let i = 0
  let v = n
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024
    i += 1
  }
  return `${v.toFixed(v >= 10 || i === 0 ? 0 : 1)} ${units[i]}`
}

export function MaintenancePage() {
  const qc = useQueryClient()
  const { data, isLoading, error } = useQuery({
    queryKey: ['maintenance'],
    queryFn: api.maintenanceScan,
  })
  const [keepChoice, setKeepChoice] = useState<Record<string, number>>({})

  const resolve = useMutation({
    mutationFn: api.maintenanceResolve,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['maintenance'] }),
  })

  if (isLoading) return <p className="muted">Scanning library…</p>
  if (error) return <p className="error">{(error as Error).message}</p>
  if (!data) return null

  const nothingFound =
    !data.orphan_db_tracks.length && !data.orphan_files.length && !data.duplicate_groups.length

  return (
    <div>
      <div className="page-header">
        <div>
          <h1>Duplicate Cleanup</h1>
          <p>Orphaned files, missing files, and duplicate tracks found in your library.</p>
        </div>
      </div>

      {nothingFound && <p className="muted">Nothing to clean up — your library looks tidy.</p>}

      {!!data.orphan_db_tracks.length && (
        <>
          <h2 className="section-label">Missing files ({data.orphan_db_tracks.length})</h2>
          <p className="muted">Tracked in Musicarr but the file no longer exists on disk.</p>
          <table className="table">
            <tbody>
              {data.orphan_db_tracks.map((t) => (
                <tr key={t.track_id}>
                  <td>{t.title}</td>
                  <td className="muted">
                    {t.artist_name} — {t.album_title}
                  </td>
                  <td className="muted" style={{ wordBreak: 'break-all' }}>
                    {t.path}
                  </td>
                  <td>
                    <button
                      type="button"
                      className="btn ghost"
                      disabled={resolve.isPending}
                      onClick={() => {
                        if (window.confirm(`Clear the missing-file link for "${t.title}"?`)) {
                          resolve.mutate({ unlink_track_id: t.track_id })
                        }
                      }}
                    >
                      Clear link
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}

      {!!data.orphan_files.length && (
        <>
          <h2 className="section-label">Orphan files ({data.orphan_files.length})</h2>
          <p className="muted">Audio files on disk with no matching track in Musicarr.</p>
          <table className="table">
            <tbody>
              {data.orphan_files.map((f) => (
                <tr key={f.path}>
                  <td className="muted" style={{ wordBreak: 'break-all' }}>
                    {f.path}
                  </td>
                  <td className="muted" style={{ whiteSpace: 'nowrap' }}>
                    {formatBytes(f.size_bytes)}
                  </td>
                  <td>
                    <button
                      type="button"
                      className="btn danger"
                      disabled={resolve.isPending}
                      onClick={() => {
                        if (window.confirm(`Permanently delete this file?\n\n${f.path}`)) {
                          resolve.mutate({ delete_file_path: f.path })
                        }
                      }}
                    >
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}

      {!!data.duplicate_groups.length && (
        <>
          <h2 className="section-label">Duplicate tracks ({data.duplicate_groups.length})</h2>
          <p className="muted">Pick which copy to keep; the rest are deleted from disk.</p>
          {data.duplicate_groups.map((group) => {
            const keep = keepChoice[group.key] ?? group.tracks[0]?.track_id
            return (
              <div className="card" key={group.key} style={{ marginBottom: '1rem' }}>
                <div className="muted tiny" style={{ marginBottom: '0.5rem' }}>
                  Matched by {group.reason === 'isrc' ? 'ISRC' : 'album track position'}
                </div>
                {group.tracks.map((t) => (
                  <label
                    key={t.track_id}
                    style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '0.25rem 0' }}
                  >
                    <input
                      type="radio"
                      name={`keep-${group.key}`}
                      checked={keep === t.track_id}
                      onChange={() => setKeepChoice((prev) => ({ ...prev, [group.key]: t.track_id }))}
                    />
                    <span>
                      {t.title} — {t.artist_name} / {t.album_title}
                    </span>
                    <span className="muted tiny" style={{ wordBreak: 'break-all' }}>
                      {t.path}
                    </span>
                  </label>
                ))}
                <button
                  type="button"
                  className="btn danger"
                  style={{ marginTop: '0.5rem' }}
                  disabled={resolve.isPending}
                  onClick={() => {
                    const deleteIds = group.tracks.map((t) => t.track_id).filter((id) => id !== keep)
                    if (
                      window.confirm(
                        `Delete ${deleteIds.length} duplicate copy/copies, keeping the selected one?`
                      )
                    ) {
                      resolve.mutate({ keep_track_id: keep, delete_track_ids: deleteIds })
                    }
                  }}
                >
                  Keep selected, delete the rest
                </button>
              </div>
            )
          })}
        </>
      )}
    </div>
  )
}
