import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { motion } from 'framer-motion'
import { api } from '../api'
import { useToast } from '../Toast'

export function WantedPage() {
  const qc = useQueryClient()
  const toast = useToast()
  const health = useQuery({ queryKey: ['health'], queryFn: api.health })
  const active = health.data?.active_provider || 'deezer'
  const { data, isLoading, error } = useQuery({
    queryKey: ['wanted', active],
    queryFn: api.wanted,
    refetchInterval: 10000,
  })

  const download = useMutation({
    mutationFn: (id: number) => api.downloadAlbum(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['wanted'] })
      qc.invalidateQueries({ queryKey: ['queue'] })
    },
  })
  const skip = useMutation({
    mutationFn: (id: number) => api.patchAlbum(id, { status: 'skipped', monitored: false }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['wanted'] }),
  })
  const downloadAll = useMutation({
    mutationFn: api.downloadAllWanted,
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

  return (
    <div>
      <div className="page-header">
        <div>
          <h1>Wanted</h1>
          <p>
            Missing releases from <strong style={{ textTransform: 'capitalize' }}>{active}</strong>.
            Switch source in Settings to see another catalog.
          </p>
        </div>
        {data && data.length > 0 && (
          <div className="toolbar" style={{ marginBottom: 0 }}>
            <button className="btn" onClick={() => downloadAll.mutate()} disabled={downloadAll.isPending}>
              Download all
            </button>
            <button className="btn ghost" onClick={() => skipAll.mutate()} disabled={skipAll.isPending}>
              Skip all
            </button>
          </div>
        )}
      </div>
      {isLoading && <p className="muted">Loading…</p>}
      {error && <p className="error">{(error as Error).message}</p>}
      {data && data.length === 0 && (
        <div className="empty-state">
          <h2>You’re caught up</h2>
          <p className="muted">Nothing wanted right now.</p>
        </div>
      )}
      <div className="album-list">
        {data?.map((album, i) => (
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
                <strong>{album.title}</strong>{' '}
                <span className="badge wanted">wanted</span>{' '}
                <span className="badge queued">{album.provider}</span>
              </div>
              <div className="muted">
                <Link to={`/artists/${album.artist_id}`}>
                  {album.artist_name || `Artist #${album.artist_id}`}
                </Link>
                {album.release_date ? ` · ${album.release_date}` : ''}
              </div>
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
