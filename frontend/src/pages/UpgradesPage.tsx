import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { motion } from 'framer-motion'
import { useState } from 'react'
import { api, type Album } from '../api'
import { useToast } from '../Toast'

export function UpgradesPage() {
  const qc = useQueryClient()
  const toast = useToast()
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const settings = useQuery({ queryKey: ['settings', false], queryFn: () => api.settings() })
  const { data, isLoading, error } = useQuery({
    queryKey: ['upgradable'],
    queryFn: api.upgradable,
  })

  const target = (settings.data?.bitrate || 'flac').toLowerCase()
  const enabled = settings.data?.upgrade_enabled !== false

  const allSelected = Boolean(data?.length) && data!.every((a) => selected.has(a.id))

  function toggleOne(id: number) {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  function toggleAll() {
    if (!data) return
    if (allSelected) setSelected(new Set())
    else setSelected(new Set(data.map((a) => a.id)))
  }

  const upgradeOne = useMutation({
    mutationFn: (id: number) => api.downloadAlbum(id, true),
    onSuccess: (res) => {
      toast.push(res.queued ? 'Queued upgrade' : 'Could not queue upgrade', res.queued ? 'ok' : 'error')
      qc.invalidateQueries({ queryKey: ['upgradable'] })
      qc.invalidateQueries({ queryKey: ['queue'] })
    },
    onError: (err) => toast.push((err as Error).message, 'error'),
  })

  const upgradeSelected = useMutation({
    mutationFn: async () => {
      let queued = 0
      for (const id of selected) {
        const res = await api.downloadAlbum(id, true)
        if (res.queued) queued += 1
      }
      return queued
    },
    onSuccess: (queued) => {
      toast.push(`Queued ${queued} upgrade(s)`, 'ok')
      setSelected(new Set())
      qc.invalidateQueries({ queryKey: ['upgradable'] })
      qc.invalidateQueries({ queryKey: ['queue'] })
    },
    onError: (err) => toast.push((err as Error).message, 'error'),
  })

  const upgradeAll = useMutation({
    mutationFn: api.upgradeAll,
    onSuccess: (res) => {
      toast.push(
        res.queued
          ? `Queued ${res.queued} upgrade(s) to ${res.target || target}`
          : res.message || 'Nothing to upgrade',
        'ok',
      )
      qc.invalidateQueries({ queryKey: ['upgradable'] })
      qc.invalidateQueries({ queryKey: ['queue'] })
    },
    onError: (err) => toast.push((err as Error).message, 'error'),
  })

  const rows: Album[] = data || []

  return (
    <div>
      <div className="page-header">
        <div>
          <h1>Quality upgrades</h1>
          <p>
            Downloaded albums below target quality (<strong>{target}</strong>).
          </p>
        </div>
        <div className="toolbar" style={{ marginBottom: 0 }}>
          <Link className="btn ghost" to="/">
            Back to Library
          </Link>
          {enabled && rows.length > 0 && (
            <button className="btn" onClick={() => upgradeAll.mutate()} disabled={upgradeAll.isPending}>
              Upgrade all ({rows.length})
            </button>
          )}
        </div>
      </div>

      {!enabled && (
        <div className="banner danger">
          Upgrades are disabled. Enable them in Settings → Downloads.
        </div>
      )}

      {rows.length > 0 && (
        <div className="toolbar">
          <label className="muted" style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <input type="checkbox" checked={allSelected} onChange={toggleAll} />
            Select all
          </label>
          {selected.size > 0 && (
            <button
              className="btn"
              onClick={() => upgradeSelected.mutate()}
              disabled={upgradeSelected.isPending || !enabled}
            >
              Upgrade selected ({selected.size})
            </button>
          )}
        </div>
      )}

      {isLoading && <p className="muted">Loading…</p>}
      {error && <p className="error">{(error as Error).message}</p>}
      {!isLoading && rows.length === 0 && (
        <div className="empty-state">
          <h2>Nothing to upgrade</h2>
          <p className="muted">All downloaded albums already meet {target}.</p>
        </div>
      )}

      <div className="album-list">
        {rows.map((album, i) => (
          <motion.div
            key={album.id}
            className="album-row"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: Math.min(i * 0.03, 0.3) }}
          >
            <label style={{ display: 'flex', alignItems: 'center' }}>
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
                </Link>
              </div>
              <div className="muted">
                <Link to={`/artists/${album.artist_id}`}>
                  {album.artist_name || `Artist #${album.artist_id}`}
                </Link>
                {` · have ${album.quality || 'unknown'} → want ${target}`}
              </div>
            </div>
            <div className="row-actions">
              <button
                className="btn"
                disabled={!enabled || upgradeOne.isPending}
                onClick={() => upgradeOne.mutate(album.id)}
              >
                Upgrade
              </button>
            </div>
          </motion.div>
        ))}
      </div>
    </div>
  )
}
