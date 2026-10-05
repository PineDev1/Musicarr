import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { motion } from 'framer-motion'
import { useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../api'
import { useToast } from '../Toast'

export function WantedPage() {
  const qc = useQueryClient()
  const toast = useToast()
  const [typeFilter, setTypeFilter] = useState<string>('')
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const health = useQuery({ queryKey: ['health'], queryFn: api.health })
  const active = health.data?.active_provider || 'deezer'
  const { data, isLoading, error } = useQuery({
    queryKey: ['wanted', active],
    queryFn: () => api.wanted(),
    refetchInterval: 10000,
  })

  // "Search all wanted" runs in the background on the server; poll its progress.
  const search = useQuery({
    queryKey: ['search-wanted'],
    queryFn: api.searchAllWantedStatus,
    refetchInterval: (q) => (q.state.data?.state === 'running' ? 1500 : false),
  })
  const searchRunning = search.data?.state === 'running'
  const searchAll = useMutation({
    mutationFn: api.searchAllWanted,
    onSuccess: () => {
      toast.push('Searching your indexers for every wanted album…', 'ok')
      qc.invalidateQueries({ queryKey: ['search-wanted'] })
    },
    onError: (err) => toast.push((err as Error).message, 'error'),
  })
  // Surface the result once when a run we watched finishes.
  const lastState = useRef(search.data?.state)
  useEffect(() => {
    const now = search.data
    if (lastState.current === 'running' && now && now.state !== 'running') {
      if (now.state === 'done') {
        toast.push(`Checked ${now.checked ?? 0} album(s), grabbed ${now.grabbed ?? 0}`, 'ok')
        qc.invalidateQueries({ queryKey: ['wanted'] })
        qc.invalidateQueries({ queryKey: ['health'] })
      } else if (now.state === 'error') {
        toast.push(now.error || 'Wanted search failed', 'error')
      }
    }
    lastState.current = now?.state
  }, [search.data, toast, qc])

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

  const allFilteredSelected =
    filtered.length > 0 && filtered.every((a) => selected.has(a.id))

  function toggleOne(id: number) {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  function toggleAllFiltered() {
    setSelected((prev) => {
      const next = new Set(prev)
      if (allFilteredSelected) {
        for (const a of filtered) next.delete(a.id)
      } else {
        for (const a of filtered) next.add(a.id)
      }
      return next
    })
  }

  const download = useMutation({
    mutationFn: (id: number) => api.downloadAlbum(id, false),
    onSuccess: (res) => {
      if (!res.queued) {
        toast.push('Could not queue download', 'error')
        return
      }
      toast.push('Queued download', 'ok')
      qc.invalidateQueries({ queryKey: ['wanted'] })
      qc.invalidateQueries({ queryKey: ['queue'] })
    },
    onError: (err) => toast.push((err as Error).message, 'error'),
  })
  const skip = useMutation({
    mutationFn: (id: number) => api.patchAlbum(id, { status: 'skipped', monitored: false }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['wanted'] }),
    onError: (err) => toast.push((err as Error).message, 'error'),
  })
  const bulkDownload = useMutation({
    mutationFn: () => api.bulkDownloadAlbums([...selected]),
    onSuccess: (res) => {
      toast.push(`Queued ${res.queued} album(s)`, 'ok')
      setSelected(new Set())
      qc.invalidateQueries({ queryKey: ['wanted'] })
      qc.invalidateQueries({ queryKey: ['queue'] })
    },
    onError: (err) => toast.push((err as Error).message, 'error'),
  })
  const bulkSkip = useMutation({
    mutationFn: () => api.bulkSkipAlbums([...selected]),
    onSuccess: (res) => {
      toast.push(`Skipped ${res.skipped} album(s)`, 'ok')
      setSelected(new Set())
      qc.invalidateQueries({ queryKey: ['wanted'] })
    },
    onError: (err) => toast.push((err as Error).message, 'error'),
  })
  const downloadAll = useMutation({
    mutationFn: () => api.downloadAllWanted(),
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
          </p>
        </div>
        {data && data.length > 0 && (
          <div className="toolbar" style={{ marginBottom: 0, flexWrap: 'wrap' }}>
            <button className="btn" onClick={() => downloadAll.mutate()} disabled={downloadAll.isPending}>
              Download all
            </button>
            {health.data && health.data.resolved_acquisition_mode !== 'streaming' && (
              <button
                className="btn"
                title="Search your indexers for every wanted album and grab the best match for each (the auto-grab minimum score and the blocklist still apply)"
                disabled={searchAll.isPending || searchRunning}
                onClick={() => {
                  if (
                    window.confirm(
                      `Search your indexers for all ${data.length} wanted album(s) and download the best match for each? Releases below your auto-grab minimum score or on the blocklist are skipped.`,
                    )
                  )
                    searchAll.mutate()
                }}
              >
                {searchRunning
                  ? `Searching… ${search.data?.checked ?? 0}/${search.data?.total || data.length}`
                  : 'Search all wanted'}
              </button>
            )}
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

      <div className="toolbar" style={{ flexWrap: 'wrap' }}>
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
        {filtered.length > 0 && (
          <label className="muted" style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <input type="checkbox" checked={allFilteredSelected} onChange={toggleAllFiltered} />
            Select shown
          </label>
        )}
        {selected.size > 0 && (
          <>
            <button
              className="btn"
              onClick={() => bulkDownload.mutate()}
              disabled={bulkDownload.isPending}
            >
              Download selected ({selected.size})
            </button>
            <button
              className="btn ghost"
              onClick={() => bulkSkip.mutate()}
              disabled={bulkSkip.isPending}
            >
              Skip selected
            </button>
          </>
        )}
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
              {album.status_reason ? (
                <div className="muted" style={{ fontSize: '0.85rem', marginTop: 2 }} title={album.status_reason}>
                  Why missing: {album.status_reason}
                </div>
              ) : null}
            </div>
            <div className="row-actions">
              <button className="btn" onClick={() => download.mutate(album.id)}>
                Download
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
