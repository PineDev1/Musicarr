import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../api'
import { useToast } from '../Toast'

function fmtBytes(n: number): string {
  if (n >= 1024 ** 3) return `${(n / 1024 ** 3).toFixed(1)} GB`
  if (n >= 1024 ** 2) return `${(n / 1024 ** 2).toFixed(1)} MB`
  if (n >= 1024) return `${Math.round(n / 1024)} KB`
  return `${n} B`
}

const REASONS: Record<string, string> = {
  album_deleted: 'Album deleted',
  orphan_file: 'Orphan file',
  duplicate_track: 'Duplicate track',
}

/** Files removed from the UI wait here until they expire, so a mistaken delete can be undone. */
export function TrashPanel() {
  const qc = useQueryClient()
  const toast = useToast()
  const trash = useQuery({ queryKey: ['trash'], queryFn: api.trash })

  const refresh = () => qc.invalidateQueries({ queryKey: ['trash'] })
  const restore = useMutation({
    mutationFn: (id: number) => api.restoreTrash(id),
    onSuccess: (r) => {
      toast.push(`Restored to ${r.restored_to}. Run a library scan to re-add it.`, 'ok')
      refresh()
    },
    onError: (err) => toast.push((err as Error).message, 'error'),
  })
  const purge = useMutation({
    mutationFn: (id: number) => api.deleteTrash(id),
    onSuccess: refresh,
    onError: (err) => toast.push((err as Error).message, 'error'),
  })
  const empty = useMutation({
    mutationFn: api.emptyTrash,
    onSuccess: (r) => {
      toast.push(`Emptied trash (${r.removed} item(s))`, 'ok')
      refresh()
    },
    onError: (err) => toast.push((err as Error).message, 'error'),
  })

  const data = trash.data
  const items = data?.items ?? []

  return (
    <div className="card" style={{ marginTop: '1.25rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: '1rem', alignItems: 'baseline' }}>
        <h3 style={{ margin: 0 }}>Trash</h3>
        {items.length > 0 && (
          <button
            type="button"
            className="btn ghost danger"
            disabled={empty.isPending}
            onClick={() => {
              if (window.confirm(`Permanently delete ${items.length} item(s) (${fmtBytes(data?.total_bytes ?? 0)})?`))
                empty.mutate()
            }}
          >
            Empty trash
          </button>
        )}
      </div>
      <p className="muted" style={{ marginTop: '0.25rem', fontSize: '0.85rem', maxWidth: 640 }}>
        {data && data.retention_days > 0
          ? `Deleted files are kept for ${data.retention_days} days before they're removed for good.`
          : 'The trash is switched off, so deletes are permanent (Settings → Backup).'}{' '}
        Restoring puts the files back; run a library scan afterward to re-add them to Musicarr.
      </p>
      {trash.isLoading && <p className="muted">Loading…</p>}
      {!trash.isLoading && items.length === 0 && <p className="muted">The trash is empty.</p>}
      {items.length > 0 && (
        <table className="table">
          <thead>
            <tr>
              <th>Item</th>
              <th>Why</th>
              <th>Deleted</th>
              <th>Size</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {items.map((i) => (
              <tr key={i.id}>
                <td title={i.original_path}>
                  {i.is_dir ? '📁 ' : ''}
                  {i.label}
                </td>
                <td>{REASONS[i.reason] || i.reason}</td>
                <td>{i.deleted_at ? new Date(i.deleted_at).toLocaleString() : '—'}</td>
                <td>{fmtBytes(i.size_bytes)}</td>
                <td style={{ whiteSpace: 'nowrap', textAlign: 'right' }}>
                  <button type="button" className="btn ghost" disabled={restore.isPending} onClick={() => restore.mutate(i.id)}>
                    Restore
                  </button>{' '}
                  <button
                    type="button"
                    className="btn ghost danger"
                    disabled={purge.isPending}
                    onClick={() => {
                      if (window.confirm(`Permanently delete "${i.label}"?`)) purge.mutate(i.id)
                    }}
                  >
                    Delete
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
