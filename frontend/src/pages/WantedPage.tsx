import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { motion } from 'framer-motion'
import { useMemo, useState } from 'react'
import { api } from '../api'
import { useToast } from '../Toast'

export function WantedPage() {
  const qc = useQueryClient()
  const toast = useToast()
  const [typeFilter, setTypeFilter] = useState<string>('')
  const health = useQuery({ queryKey: ['health'], queryFn: api.health })
  const active = health.data?.active_provider || 'deezer'
  const { data, isLoading, error } = useQuery({
    queryKey: ['wanted', active],
    queryFn: () => api.wanted(),
    refetchInterval: 10000,
  })

  const filtered = useMemo(() => {
    if (!data) return []
    if (!typeFilter) return data
    return data.filter((a) => (a.album_type || '').toLowerCase() === typeFilter)
  }, [data, typeFilter])

  const counts = useMemo(() => {
    const all = data || []
    return {
      album: all.filter((a) => a.album_type === 'album').length,
      ep: all.filter((a) => a.album_type === 'ep').length,
      single: all.filter((a) => a.album_type === 'single').length,
      compilation: all.filter((a) => a.album_type === 'compilation').length,
    }
  }, [data])

  const settings = useQuery({ queryKey: ['settings'], queryFn: () => api.settings(false) })
  const preferred = settings.data?.preferred_download_method || 'streaming'

  const download = useMutation({
    mutationFn: ({ id, method }: { id: number; method?: string }) =>
      api.downloadAlbum(id, false, method),
    onSuccess: (res) => {
      toast.push(
        res.source === 'indexer' ? 'Searching indexers…' : 'Queued streaming download',
        'ok',
      )
      qc.invalidateQueries({ queryKey: ['wanted'] })
      qc.invalidateQueries({ queryKey: ['queue'] })
    },
    onError: (err) => toast.push((err as Error).message, 'error'),
  })
  const skip = useMutation({
    mutationFn: (id: number) => api.patchAlbum(id, { status: 'skipped', monitored: false }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['wanted'] }),
  })
  const downloadAll = useMutation({
    mutationFn: (method?: string) => api.downloadAllWanted(method),
    onSuccess: (res) => {
      toast.push(`Queued ${res.queued} album(s)`, 'ok')
      qc.invalidateQueries({ queryKey: ['wanted'] })
      qc.invalidateQueries({ queryKey: ['queue'] })
    },
    onError: (err) => toast.push((err as Error).message, 'error'),
  })
  const skipAll = useMutation({
    mutationFn: api.skipAllWanted,
    onSuccess: (res) => {
      toast.push(`Skipped ${res.skipped} album(s)`, 'ok')
      qc.invalidateQueries({ queryKey: ['wanted'] })
    },
    onError: (err) => toast.push((err as Error).message, 'error'),
  })
  const skipSingles = useMutation({
    mutationFn: api.skipWantedSingles,
    onSuccess: (res) => {
      toast.push(`Skipped ${res.skipped} single(s)`, 'ok')
      qc.invalidateQueries({ queryKey: ['wanted'] })
    },
    onError: (err) => toast.push((err as Error).message, 'error'),
  })
  const skipJunk = useMutation({
    mutationFn: api.skipWantedJunk,
    onSuccess: (res) => {
      toast.push(`Skipped ${res.skipped} junk release(s)`, 'ok')
      qc.invalidateQueries({ queryKey: ['wanted'] })
    },
    onError: (err) => toast.push((err as Error).message, 'error'),
  })

  return (
    <div>
      <div className="page-header">
        <div>
          <h1>Wanted</h1>
          <p>
            Missing releases from <strong style={{ textTransform: 'capitalize' }}>{active}</strong>.
            Default grab method: <strong>{preferred.replaceAll('_', ' ')}</strong> (Settings →
            Downloads).
          </p>
        </div>
        {data && data.length > 0 && (
          <div className="toolbar" style={{ marginBottom: 0, flexWrap: 'wrap' }}>
            <button className="btn" onClick={() => downloadAll.mutate(undefined)} disabled={downloadAll.isPending}>
              Download all
            </button>
            <button
              className="btn secondary"
              onClick={() => downloadAll.mutate('indexer')}
              disabled={downloadAll.isPending}
            >
              Grab all via indexers
            </button>
            <button className="btn ghost" onClick={() => skipSingles.mutate()} disabled={skipSingles.isPending}>
              Skip all singles
            </button>
            <button className="btn ghost" onClick={() => skipJunk.mutate()} disabled={skipJunk.isPending}>
              Skip junk
            </button>
            <button className="btn ghost" onClick={() => skipAll.mutate()} disabled={skipAll.isPending}>
              Skip all
            </button>
          </div>
        )}
      </div>

      <div className="toolbar">
        <label className="muted" style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          Type
          <select value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)}>
            <option value="">All ({data?.length || 0})</option>
            <option value="album">Albums ({counts.album})</option>
            <option value="ep">EPs ({counts.ep})</option>
            <option value="single">Singles ({counts.single})</option>
            <option value="compilation">Compilations ({counts.compilation})</option>
          </select>
        </label>
      </div>

      {isLoading && <p className="muted">Loading…</p>}
      {error && <p className="error">{(error as Error).message}</p>}
      {data && filtered.length === 0 && (
        <div className="empty-state">
          <h2>You’re caught up</h2>
          <p className="muted">Nothing wanted right now.</p>
        </div>
      )}
      <div className="album-list">
        {filtered.map((album, i) => (
          <motion.div
            key={album.id}
            className="album-row"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: Math.min(i * 0.03, 0.3) }}
          >
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
                <span className="badge wanted">wanted</span>{' '}
                <span className="badge queued">{album.album_type}</span>
              </div>
              <div className="muted">
                <Link to={`/artists/${album.artist_id}`}>
                  {album.artist_name || `Artist #${album.artist_id}`}
                </Link>
                {album.release_date ? ` · ${album.release_date}` : ''}
                {album.track_count ? ` · ${album.track_count} tracks` : ''}
              </div>
            </div>
            <div className="row-actions">
              <button className="btn" onClick={() => download.mutate({ id: album.id })}>
                Download
              </button>
              <button
                className="btn secondary"
                onClick={() => download.mutate({ id: album.id, method: 'indexer' })}
              >
                Indexer
              </button>
              <button className="btn ghost" onClick={() => skip.mutate(album.id)}>
                Skip
              </button>
            </div>
          </motion.div>
        ))}
      </div>
    </div>
  )
}
