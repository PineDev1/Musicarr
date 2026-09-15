import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { api, type ImportList } from '../api'
import { useToast } from '../Toast'

function IntervalLabel({ minutes }: { minutes: number }) {
  if (minutes % 1440 === 0) return <>{minutes / 1440}d</>
  if (minutes % 60 === 0) return <>{minutes / 60}h</>
  return <>{minutes}m</>
}

export function ImportListsPage() {
  const qc = useQueryClient()
  const toast = useToast()
  const { data, isLoading, error } = useQuery({
    queryKey: ['import-lists'],
    queryFn: api.importLists,
  })

  const [creating, setCreating] = useState(false)
  const [name, setName] = useState('')
  const [namesRaw, setNamesRaw] = useState('')
  const [interval, setInterval] = useState(720)

  const create = useMutation({
    mutationFn: () =>
      api.createImportList({ name, names_raw: namesRaw, interval_minutes: interval, enabled: true }),
    onSuccess: () => {
      toast.push('Import list created', 'ok')
      setCreating(false)
      setName('')
      setNamesRaw('')
      setInterval(720)
      qc.invalidateQueries({ queryKey: ['import-lists'] })
    },
    onError: (err) => toast.push((err as Error).message, 'error'),
  })

  const toggle = useMutation({
    mutationFn: ({ id, enabled }: { id: number; enabled: boolean }) =>
      api.updateImportList(id, { enabled }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['import-lists'] }),
    onError: (err) => toast.push((err as Error).message, 'error'),
  })

  const remove = useMutation({
    mutationFn: (id: number) => api.deleteImportList(id),
    onSuccess: () => {
      toast.push('Import list deleted', 'ok')
      qc.invalidateQueries({ queryKey: ['import-lists'] })
    },
    onError: (err) => toast.push((err as Error).message, 'error'),
  })

  const run = useMutation({
    mutationFn: (id: number) => api.runImportList(id),
    onSuccess: (res) => {
      toast.push(res.summary, res.errors.length ? 'error' : 'ok')
      qc.invalidateQueries({ queryKey: ['import-lists'] })
    },
    onError: (err) => toast.push((err as Error).message, 'error'),
  })

  return (
    <div>
      <div className="page-header">
        <div>
          <h1>Import lists</h1>
          <p>
            Paste a list of artist names once — Musicarr re-checks it on a schedule and adds any
            that are missing from your library.
          </p>
        </div>
        <button className="btn" onClick={() => setCreating((v) => !v)}>
          {creating ? 'Cancel' : 'New import list'}
        </button>
      </div>

      {creating && (
        <div className="album-row" style={{ flexDirection: 'column', alignItems: 'stretch', gap: 10 }}>
          <div className="field" style={{ margin: 0 }}>
            <label>Name</label>
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Favorites" />
          </div>
          <div className="field" style={{ margin: 0 }}>
            <label>Artist names (one per line)</label>
            <textarea
              rows={6}
              value={namesRaw}
              onChange={(e) => setNamesRaw(e.target.value)}
              placeholder={'Luke Combs\nEd Sheeran\nShenandoah'}
            />
          </div>
          <div className="field" style={{ margin: 0, maxWidth: 220 }}>
            <label>Check every</label>
            <select value={interval} onChange={(e) => setInterval(Number(e.target.value))}>
              <option value={60}>1 hour</option>
              <option value={360}>6 hours</option>
              <option value={720}>12 hours</option>
              <option value={1440}>1 day</option>
              <option value={10080}>1 week</option>
            </select>
          </div>
          <div className="toolbar" style={{ marginBottom: 0 }}>
            <button
              className="btn"
              onClick={() => create.mutate()}
              disabled={create.isPending || !name.trim() || !namesRaw.trim()}
            >
              Create
            </button>
          </div>
        </div>
      )}

      {isLoading && <p className="muted">Loading…</p>}
      {error && <p className="error">{(error as Error).message}</p>}
      {data && data.length === 0 && !creating && (
        <div className="empty-state">
          <h2>No import lists yet</h2>
          <p className="muted">Create one to auto-add artists from a pasted list on a schedule.</p>
        </div>
      )}

      <div className="album-list">
        {(data || []).map((list: ImportList) => {
          const names = list.names_raw.split('\n').filter((n) => n.trim()).length
          return (
            <div key={list.id} className="album-row">
              <div style={{ minWidth: 0, flex: 1 }}>
                <div>
                  <strong>{list.name}</strong>{' '}
                  <span className={`badge ${list.enabled ? 'downloaded' : 'skipped'}`}>
                    {list.enabled ? 'enabled' : 'disabled'}
                  </span>
                </div>
                <div className="muted">
                  {names} artist{names === 1 ? '' : 's'} · every <IntervalLabel minutes={list.interval_minutes} />
                  {list.last_run_at ? ` · last run ${new Date(list.last_run_at).toLocaleString()}` : ' · never run'}
                </div>
                {list.last_result && (
                  <div className="muted" style={{ fontSize: '0.85rem', marginTop: 4 }}>
                    {list.last_result}
                  </div>
                )}
              </div>
              <div className="row-actions">
                <button
                  className="btn secondary"
                  onClick={() => run.mutate(list.id)}
                  disabled={run.isPending}
                >
                  Run now
                </button>
                <button
                  className="btn ghost"
                  onClick={() => toggle.mutate({ id: list.id, enabled: !list.enabled })}
                  disabled={toggle.isPending}
                >
                  {list.enabled ? 'Disable' : 'Enable'}
                </button>
                <button
                  className="btn danger"
                  onClick={() => {
                    if (window.confirm(`Delete import list "${list.name}"?`)) remove.mutate(list.id)
                  }}
                  disabled={remove.isPending}
                >
                  Delete
                </button>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
