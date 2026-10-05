import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { api } from '../api'
import { useToast } from '../Toast'
import { FolderPicker } from '../components/FolderPicker'

export function LibraryRootsPanel() {
  const qc = useQueryClient()
  const toast = useToast()
  const [path, setPath] = useState('')
  const [label, setLabel] = useState('')
  const [picking, setPicking] = useState(false)

  const { data, isLoading } = useQuery({ queryKey: ['library-roots'], queryFn: api.libraryRoots })

  const create = useMutation({
    mutationFn: () => api.createLibraryRoot({ path: path.trim(), label: label.trim() }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['library-roots'] })
      setPath('')
      setLabel('')
      toast.push('Library folder added', 'ok')
    },
    onError: (err) => toast.push((err as Error).message, 'error'),
  })

  const remove = useMutation({
    mutationFn: (id: number) => api.deleteLibraryRoot(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['library-roots'] }),
    onError: (err) => toast.push((err as Error).message, 'error'),
  })

  return (
    <div className="field">
      <label>Additional library folders</label>
      <p className="muted" style={{ marginTop: 0, fontSize: '0.85rem', maxWidth: 560 }}>
        Point Musicarr at other folders (an old library, a second drive) so Library Scan, Import,
        and Duplicate Cleanup pick up files there too. New downloads and Reorganize always use the
        primary library path above.
      </p>
      <div className="toolbar" style={{ flexWrap: 'wrap', alignItems: 'flex-end' }}>
        <div className="field" style={{ margin: 0, minWidth: 260 }}>
          <label>Folder path</label>
          <input
            value={path}
            onChange={(e) => setPath(e.target.value)}
            placeholder="/mnt/old-music"
            autoComplete="off"
          />
        </div>
        <button type="button" className="btn ghost" onClick={() => setPicking(true)}>
          Browse…
        </button>
        {picking && (
          <FolderPicker
            title="Choose a folder to add"
            initialPath={path}
            onClose={() => setPicking(false)}
            onSelect={(p) => {
              setPath(p)
              setPicking(false)
            }}
          />
        )}
        <div className="field" style={{ margin: 0 }}>
          <label>Label (optional)</label>
          <input
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            placeholder="Old drive"
            autoComplete="off"
          />
        </div>
        <button
          type="button"
          className="btn"
          disabled={!path.trim() || create.isPending}
          onClick={() => create.mutate()}
        >
          Add folder
        </button>
      </div>
      {isLoading && <p className="muted">Loading…</p>}
      {!isLoading && (data?.length ?? 0) === 0 && (
        <p className="muted">No additional folders configured.</p>
      )}
      {(data?.length ?? 0) > 0 && (
        <table className="table" style={{ marginTop: '0.75rem' }}>
          <thead>
            <tr>
              <th>Path</th>
              <th>Label</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {data!.map((r) => (
              <tr key={r.id}>
                <td style={{ fontFamily: 'monospace' }}>{r.path}</td>
                <td>{r.label || '—'}</td>
                <td className="row-actions">
                  <button
                    type="button"
                    className="btn ghost"
                    onClick={() => {
                      if (window.confirm(`Remove "${r.path}" from library roots?`)) remove.mutate(r.id)
                    }}
                  >
                    Remove
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
