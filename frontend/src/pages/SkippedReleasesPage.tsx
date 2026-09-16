import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { motion } from 'framer-motion'
import { useMemo, useState } from 'react'
import { api } from '../api'
import { useToast } from '../Toast'

const REASON_LABELS: Record<string, string> = {
  junk: 'Junk title',
  live: 'Live release',
  type_disabled: 'Type disabled',
  singles_disabled: 'Singles disabled',
  not_on_provider: 'Not on provider',
  min_tracks: 'Below min tracks',
  manual: 'Manually skipped',
  other: 'Other',
}

export function SkippedReleasesPage() {
  const qc = useQueryClient()
  const toast = useToast()
  const [reasonFilter, setReasonFilter] = useState<string>('')
  const [typeFilter, setTypeFilter] = useState<string>('')
  const [sort, setSort] = useState<'artist' | 'date'>('artist')
  const [selected, setSelected] = useState<Set<number>>(new Set())

  const { data, isLoading, error } = useQuery({
    queryKey: ['skipped', reasonFilter, typeFilter, sort],
    queryFn: () =>
      api.skippedAlbums({
        reason_code: reasonFilter || undefined,
        album_type: typeFilter || undefined,
        sort,
      }),
    refetchInterval: 15000,
  })

  const counts = useMemo(() => {
    const all = data || []
    const byReason: Record<string, number> = {}
    for (const a of all) {
      const code = a.skip_reason_code || 'other'
      byReason[code] = (byReason[code] || 0) + 1
    }
    return byReason
  }, [data])

  const allSelected = (data || []).length > 0 && (data || []).every((a) => selected.has(a.id))

  function toggleOne(id: number) {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  function toggleAll() {
    setSelected((prev) => {
      const next = new Set(prev)
      if (allSelected) {
        for (const a of data || []) next.delete(a.id)
      } else {
        for (const a of data || []) next.add(a.id)
      }
      return next
    })
  }

  const restore = useMutation({
    mutationFn: (ids: number[]) => api.restoreSkippedAlbums(ids),
    onSuccess: (res) => {
      toast.push(`Restored ${res.restored} release(s) to Wanted`, 'ok')
      setSelected(new Set())
      qc.invalidateQueries({ queryKey: ['skipped'] })
      qc.invalidateQueries({ queryKey: ['wanted'] })
      qc.invalidateQueries({ queryKey: ['health'] })
    },
    onError: (err) => toast.push((err as Error).message, 'error'),
  })
  const dismiss = useMutation({
    mutationFn: (ids: number[]) => api.dismissSkippedAlbums(ids),
    onSuccess: (res) => {
      toast.push(`Dismissed ${res.dismissed} release(s)`, 'ok')
      setSelected(new Set())
      qc.invalidateQueries({ queryKey: ['skipped'] })
      qc.invalidateQueries({ queryKey: ['health'] })
    },
    onError: (err) => toast.push((err as Error).message, 'error'),
  })

  return (
    <div>
      <div className="page-header">
        <div>
          <h1>Skipped Releases</h1>
          <p className="muted">
            Everything auto-filtered as junk, live, wrong type, or manually skipped — review and
            restore anything that got caught by mistake.
          </p>
        </div>
        {selected.size > 0 && (
          <div className="toolbar" style={{ marginBottom: 0 }}>
            <button
              className="btn"
              onClick={() => restore.mutate([...selected])}
              disabled={restore.isPending}
            >
              Restore selected ({selected.size})
            </button>
            <button
              className="btn ghost"
              onClick={() => dismiss.mutate([...selected])}
              disabled={dismiss.isPending}
            >
              Dismiss selected
            </button>
          </div>
        )}
      </div>

      <div className="toolbar" style={{ flexWrap: 'wrap' }}>
        <label className="muted" style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          Reason
          <select value={reasonFilter} onChange={(e) => setReasonFilter(e.target.value)}>
            <option value="">All ({data?.length || 0})</option>
            {Object.entries(REASON_LABELS).map(([code, label]) => (
              <option key={code} value={code}>
                {label} ({counts[code] || 0})
              </option>
            ))}
          </select>
        </label>
        <label className="muted" style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          Type
          <select value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)}>
            <option value="">All</option>
            <option value="album">Albums</option>
            <option value="ep">EPs</option>
            <option value="single">Singles</option>
            <option value="compilation">Compilations</option>
          </select>
        </label>
        <label className="muted" style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          Sort
          <select value={sort} onChange={(e) => setSort(e.target.value as 'artist' | 'date')}>
            <option value="artist">Artist name</option>
            <option value="date">Release date</option>
          </select>
        </label>
        {(data || []).length > 0 && (
          <label className="muted" style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <input type="checkbox" checked={allSelected} onChange={toggleAll} />
            Select shown
          </label>
        )}
      </div>

      {isLoading && <p className="muted">Loading…</p>}
      {error && <p className="error">{(error as Error).message}</p>}
      {data && data.length === 0 && (
        <div className="empty-state">
          <h2>Nothing skipped</h2>
          <p className="muted">Anything filtered out or manually skipped will show up here.</p>
        </div>
      )}
      <div className="album-list">
        {(data || []).map((album, i) => (
          <motion.div
            key={album.id}
            className="album-row"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: Math.min(i * 0.03, 0.3) }}
          >
            <label style={{ display: 'flex', alignItems: 'center', marginRight: 4 }}>
              <input
                type="checkbox"
                checked={selected.has(album.id)}
                onChange={() => toggleOne(album.id)}
              />
            </label>
            {album.cover_url ? (
              <img src={album.cover_url} alt="" />
            ) : (
              <div className="placeholder-art" style={{ width: 64, height: 64 }} />
            )}
            <div>
              <div>
                <Link to={`/albums/${album.id}`}>
                  <strong>{album.title}</strong>
                </Link>{' '}
                <span className="badge skipped">
                  {REASON_LABELS[album.skip_reason_code || 'other'] || 'Skipped'}
                </span>{' '}
                <span className="badge queued">{album.album_type}</span>
              </div>
              <div className="muted">
                <Link to={`/artists/${album.artist_id}`}>
                  {album.artist_name || `Artist #${album.artist_id}`}
                </Link>
                {album.release_date ? ` · ${album.release_date}` : ''}
              </div>
              {album.status_reason ? (
                <div className="muted" style={{ fontSize: '0.85rem', marginTop: 2 }}>
                  {album.status_reason}
                </div>
              ) : null}
            </div>
            <div className="row-actions">
              <button className="btn" onClick={() => restore.mutate([album.id])}>
                Restore
              </button>
              <button className="btn ghost" onClick={() => dismiss.mutate([album.id])}>
                Dismiss
              </button>
            </div>
          </motion.div>
        ))}
      </div>
    </div>
  )
}
