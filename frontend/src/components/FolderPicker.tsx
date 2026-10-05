import { useQuery } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { api } from '../api'

/**
 * Modal folder browser backed by GET /api/fs/browse (folders only). Docker users
 * otherwise have to guess container paths like /music by hand.
 */
export function FolderPicker({
  initialPath,
  title = 'Choose a folder',
  onSelect,
  onClose,
}: {
  initialPath?: string
  title?: string
  onSelect: (path: string) => void
  onClose: () => void
}) {
  const [path, setPath] = useState<string | undefined>(initialPath?.trim() || undefined)
  const listing = useQuery({
    queryKey: ['fs-browse', path ?? ''],
    queryFn: () => api.browseFolders(path),
    retry: false,
  })

  // A typed path that doesn't exist yet falls back to the default listing.
  useEffect(() => {
    if (listing.isError && path) setPath(undefined)
  }, [listing.isError, path])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const data = listing.data

  return (
    <div className="modal-backdrop" onMouseDown={onClose} role="presentation">
      <div
        className="modal card folder-picker"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onMouseDown={(e) => e.stopPropagation()}
      >
        <h3 style={{ margin: '0 0 0.5rem' }}>{title}</h3>
        {data && data.shortcuts.length > 0 && (
          <div className="folder-picker-shortcuts">
            {data.shortcuts.map((s) => (
              <button key={s.path} type="button" className="btn ghost" onClick={() => setPath(s.path)}>
                {s.name}
              </button>
            ))}
          </div>
        )}
        <div className="folder-picker-path" title={data?.path}>
          {data?.path ?? '…'}
        </div>
        <div className="folder-picker-list">
          {data?.parent && (
            <button type="button" className="folder-picker-row" onClick={() => setPath(data.parent ?? undefined)}>
              ⬆ <span>..</span>
            </button>
          )}
          {listing.isLoading && <p className="muted">Loading…</p>}
          {data?.error && <p className="error">{data.error}</p>}
          {data && !data.error && data.entries.length === 0 && (
            <p className="muted" style={{ margin: '0.5rem' }}>
              No sub-folders here.
            </p>
          )}
          {data?.entries.map((e) => (
            <button key={e.path} type="button" className="folder-picker-row" onClick={() => setPath(e.path)}>
              📁 <span>{e.name}</span>
            </button>
          ))}
          {data?.truncated && <p className="muted tiny">Only the first entries are shown.</p>}
        </div>
        {data && !data.writable && (
          <p className="muted" style={{ fontSize: '0.8rem', margin: '0.5rem 0 0' }}>
            Musicarr can't write to this folder. That's fine for a read-only extra library, but not for
            the main library path.
          </p>
        )}
        <div className="toolbar" style={{ marginTop: '0.75rem', justifyContent: 'flex-end' }}>
          <button type="button" className="btn ghost" onClick={onClose}>
            Cancel
          </button>
          <button type="button" className="btn" disabled={!data} onClick={() => data && onSelect(data.path)}>
            Use this folder
          </button>
        </div>
      </div>
    </div>
  )
}
