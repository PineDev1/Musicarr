import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../api'
import { useToast } from '../Toast'

function fmtBytes(n: number): string {
  if (n >= 1024 ** 3) return `${(n / 1024 ** 3).toFixed(1)} GB`
  if (n >= 1024 ** 2) return `${(n / 1024 ** 2).toFixed(1)} MB`
  return `${Math.max(1, Math.round(n / 1024))} KB`
}

/** Backups already saved on the server (nightly job + "Back up now"): download, restore, delete. */
export function BackupFilesPanel({ restoreBusy }: { restoreBusy: boolean }) {
  const qc = useQueryClient()
  const toast = useToast()
  const files = useQuery({ queryKey: ['saved-backups'], queryFn: api.savedBackups })

  const run = useMutation({
    mutationFn: api.runBackupNow,
    onSuccess: (r) => {
      toast.push(`Backup saved (${r.name})`, 'ok')
      qc.invalidateQueries({ queryKey: ['saved-backups'] })
      qc.invalidateQueries({ queryKey: ['setup-checklist'] })
    },
    onError: (err) => toast.push((err as Error).message, 'error'),
  })
  const remove = useMutation({
    mutationFn: (name: string) => api.deleteSavedBackup(name),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['saved-backups'] }),
    onError: (err) => toast.push((err as Error).message, 'error'),
  })
  const restore = useMutation({
    mutationFn: (name: string) => api.restoreSavedBackup(name),
    onSuccess: () => {
      toast.push('Restore started', 'ok')
      qc.invalidateQueries({ queryKey: ['restore-job'] })
    },
    onError: (err) => toast.push((err as Error).message, 'error'),
  })

  const list = files.data?.files ?? []

  return (
    <div className="field">
      <label>Saved backups</label>
      <p className="muted" style={{ marginTop: 0, maxWidth: 640, fontSize: '0.85rem' }}>
        Backups kept on this server (the nightly one below and any you create here). Restoring one
        replaces your current library data.
      </p>
      <div className="toolbar" style={{ marginBottom: '0.5rem' }}>
        <button type="button" className="btn" disabled={run.isPending} onClick={() => run.mutate()}>
          {run.isPending ? 'Backing up…' : 'Back up now'}
        </button>
      </div>
      {files.isLoading && <p className="muted">Loading…</p>}
      {!files.isLoading && list.length === 0 && <p className="muted">No saved backups yet.</p>}
      {list.length > 0 && (
        <table className="table" style={{ maxWidth: 720 }}>
          <thead>
            <tr>
              <th>Backup</th>
              <th>Created</th>
              <th>Size</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {list.map((f) => (
              <tr key={f.name}>
                <td>{f.name}</td>
                <td>{new Date(f.created_at).toLocaleString()}</td>
                <td>{fmtBytes(f.size)}</td>
                <td style={{ whiteSpace: 'nowrap', textAlign: 'right' }}>
                  <a className="btn ghost" href={`/api/backup/files/${encodeURIComponent(f.name)}`} download>
                    Download
                  </a>{' '}
                  <button
                    type="button"
                    className="btn ghost"
                    disabled={restore.isPending || restoreBusy}
                    onClick={() => {
                      if (
                        window.confirm(
                          `Restore ${f.name}? Your current settings and library metadata will be replaced (the existing database is kept as a .before-restore file). You'll need to restart Musicarr afterward and re-enter provider credentials.`,
                        )
                      )
                        restore.mutate(f.name)
                    }}
                  >
                    Restore
                  </button>{' '}
                  <button
                    type="button"
                    className="btn ghost danger"
                    disabled={remove.isPending}
                    onClick={() => {
                      if (window.confirm(`Delete ${f.name}? This can't be undone.`)) remove.mutate(f.name)
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
