import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { api, type ReleaseCandidate } from '../api'
import { useToast } from '../Toast'

function formatSize(bytes: number) {
  if (!bytes || bytes < 0) return '—'
  const mb = bytes / (1024 * 1024)
  if (mb < 1024) return `${mb.toFixed(0)} MB`
  return `${(mb / 1024).toFixed(2)} GB`
}

export function ReleaseSearchModal({
  albumId,
  albumLabel,
  onClose,
}: {
  albumId: number
  albumLabel: string
  onClose: () => void
}) {
  const toast = useToast()
  const qc = useQueryClient()
  const [protocolFilter, setProtocolFilter] = useState<'all' | 'torrent' | 'usenet'>('all')
  const [grabbing, setGrabbing] = useState<string | null>(null)

  const status = useQuery({
    queryKey: ['acquisition-status'],
    queryFn: api.acquisitionStatus,
  })

  const search = useQuery({
    queryKey: ['releases', albumId],
    queryFn: () => api.searchReleases(albumId),
    refetchOnWindowFocus: false,
  })

  const rows = useMemo(() => {
    const list = search.data || []
    const filtered =
      protocolFilter === 'all'
        ? list
        : list.filter((r) => (r.protocol || '').toLowerCase() === protocolFilter)
    return [...filtered].sort((a, b) => (b.score || 0) - (a.score || 0))
  }, [search.data, protocolFilter])

  const grab = useMutation({
    mutationFn: (row: ReleaseCandidate) =>
      api.grabRelease({
        album_id: albumId,
        title: row.title,
        grab_url: row.grab_url || row.magnet_url || row.download_url,
        protocol: row.protocol || 'torrent',
        indexer_id: row.indexer_id || null,
        size: row.size,
        seeders: row.seeders,
      }),
    onSuccess: (res) => {
      toast.push(`Sent to ${res.client}`, 'ok')
      qc.invalidateQueries({ queryKey: ['queue'] })
      qc.invalidateQueries({ queryKey: ['wanted'] })
      qc.invalidateQueries({ queryKey: ['health'] })
      onClose()
    },
    onError: (err) => toast.push((err as Error).message, 'error'),
    onSettled: () => setGrabbing(null),
  })

  const canGrab = (row: ReleaseCandidate) => {
    const proto = (row.protocol || '').toLowerCase()
    if (proto === 'torrent' && !status.data?.torrent_client) return false
    if (proto === 'usenet' && !status.data?.usenet_client) return false
    return Boolean(row.grab_url || row.magnet_url || row.download_url)
  }

  const grabReason = (row: ReleaseCandidate) => {
    const proto = (row.protocol || '').toLowerCase()
    if (proto === 'torrent' && !status.data?.torrent_client) {
      return 'Add an enabled qBittorrent client first'
    }
    if (proto === 'usenet' && !status.data?.usenet_client) {
      return 'Add an enabled SABnzbd client first'
    }
    if (!(row.grab_url || row.magnet_url || row.download_url)) return 'No download URL'
    return ''
  }

  return (
    <div className="modal-backdrop" onClick={onClose} role="presentation">
      <div
        className="modal card"
        style={{ maxWidth: 920, width: '92vw', maxHeight: '85vh', overflow: 'auto' }}
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-label="Search indexers"
      >
        <div className="page-header" style={{ marginBottom: '0.75rem' }}>
          <div>
            <h2 style={{ margin: 0 }}>Search indexers</h2>
            <p className="muted" style={{ margin: '0.35rem 0 0' }}>
              Pick a release for <strong>{albumLabel}</strong>. Nothing is sent until you click
              Grab.
            </p>
          </div>
          <button type="button" className="btn ghost" onClick={onClose}>
            Close
          </button>
        </div>

        {!!status.data?.messages?.length && (
          <div className="banner warn" style={{ marginBottom: '0.75rem' }}>
            {status.data.messages.map((m) => (
              <div key={m}>{m}</div>
            ))}
          </div>
        )}

        <div className="toolbar" style={{ marginBottom: '0.75rem' }}>
          <label className="muted" style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            Protocol
            <select
              value={protocolFilter}
              onChange={(e) =>
                setProtocolFilter(e.target.value as 'all' | 'torrent' | 'usenet')
              }
            >
              <option value="all">All</option>
              <option value="torrent">Torrent</option>
              <option value="usenet">Usenet</option>
            </select>
          </label>
          <button
            type="button"
            className="btn secondary"
            onClick={() => search.refetch()}
            disabled={search.isFetching}
          >
            {search.isFetching ? 'Searching…' : 'Re-search'}
          </button>
        </div>

        {search.isLoading && <p className="muted">Querying indexers…</p>}
        {search.error && <p className="error">{(search.error as Error).message}</p>}
        {!search.isLoading && !search.error && rows.length === 0 && (
          <div className="empty-state">
            <h3>No releases found</h3>
            <p className="muted">
              Check that an indexer is enabled, categories include music (3000/3010/3040), and
              Prowlarr has synced indexers.
            </p>
          </div>
        )}

        {rows.length > 0 && (
          <table className="table">
            <thead>
              <tr>
                <th>Title</th>
                <th>Indexer</th>
                <th>Protocol</th>
                <th>Size</th>
                <th>Seeders</th>
                <th>Score</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row, i) => {
                const key = `${row.indexer_id}-${row.title}-${i}`
                const ok = canGrab(row)
                return (
                  <tr key={key}>
                    <td>
                      <div title={row.title} style={{ maxWidth: 320 }}>
                        {row.title}
                      </div>
                    </td>
                    <td className="muted">{row.indexer_name || '—'}</td>
                    <td>{row.protocol}</td>
                    <td className="muted">{formatSize(row.size)}</td>
                    <td className="muted">
                      {(row.protocol || '').toLowerCase() === 'torrent' ? row.seeders : '—'}
                    </td>
                    <td>{Math.round(row.score)}</td>
                    <td className="row-actions">
                      <button
                        type="button"
                        className="btn"
                        disabled={!ok || grab.isPending}
                        title={grabReason(row) || 'Send to download client'}
                        onClick={() => {
                          setGrabbing(key)
                          grab.mutate(row)
                        }}
                      >
                        {grabbing === key && grab.isPending ? 'Grabbing…' : 'Grab'}
                      </button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
        {!!search.data?.length && (
          <p className="muted tiny" style={{ marginTop: '0.75rem' }}>
            {search.data.length} result(s) from enabled indexers
            {protocolFilter !== 'all' ? ` · showing ${rows.length}` : ''}.
          </p>
        )}
      </div>
    </div>
  )
}
