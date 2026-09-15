import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { motion } from 'framer-motion'
import { useState } from 'react'
import { api } from '../api'
import { useToast } from '../Toast'

const REASON_LABELS: Record<string, string> = {
  import_list: 'From an import list',
  featured: 'Discovered as a featured artist',
}

export function PendingArtistsPage() {
  const qc = useQueryClient()
  const toast = useToast()
  const [selected, setSelected] = useState<Set<number>>(new Set())

  const { data, isLoading, error } = useQuery({
    queryKey: ['pending-artists'],
    queryFn: api.pendingArtists,
    refetchInterval: 15000,
  })

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

  function invalidate() {
    qc.invalidateQueries({ queryKey: ['pending-artists'] })
    qc.invalidateQueries({ queryKey: ['artists'] })
    qc.invalidateQueries({ queryKey: ['health'] })
    qc.invalidateQueries({ queryKey: ['queue'] })
  }

  const approve = useMutation({
    mutationFn: (id: number) => api.approveArtist(id),
    onSuccess: () => {
      toast.push('Artist approved', 'ok')
      invalidate()
    },
    onError: (err) => toast.push((err as Error).message, 'error'),
  })
  const reject = useMutation({
    mutationFn: (id: number) => api.rejectArtist(id),
    onSuccess: () => {
      toast.push('Artist rejected', 'ok')
      invalidate()
    },
    onError: (err) => toast.push((err as Error).message, 'error'),
  })
  const bulkApprove = useMutation({
    mutationFn: () => api.bulkApproveArtists([...selected]),
    onSuccess: (res) => {
      toast.push(`Approved ${res.approved} artist(s)`, 'ok')
      setSelected(new Set())
      invalidate()
    },
    onError: (err) => toast.push((err as Error).message, 'error'),
  })
  const bulkReject = useMutation({
    mutationFn: () => api.bulkRejectArtists([...selected]),
    onSuccess: (res) => {
      toast.push(`Rejected ${res.rejected} artist(s)`, 'ok')
      setSelected(new Set())
      invalidate()
    },
    onError: (err) => toast.push((err as Error).message, 'error'),
  })

  return (
    <div>
      <div className="page-header">
        <div>
          <h1>Pending Artists</h1>
          <p className="muted">
            Artists added automatically — by an import list or discovered as a collaborator —
            wait here for your OK before anything downloads.
          </p>
        </div>
        {selected.size > 0 && (
          <div className="toolbar" style={{ marginBottom: 0 }}>
            <button
              className="btn"
              onClick={() => bulkApprove.mutate()}
              disabled={bulkApprove.isPending}
            >
              Approve selected ({selected.size})
            </button>
            <button
              className="btn ghost"
              onClick={() => bulkReject.mutate()}
              disabled={bulkReject.isPending}
            >
              Reject selected
            </button>
          </div>
        )}
      </div>

      {(data || []).length > 0 && (
        <div className="toolbar">
          <label className="muted" style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <input type="checkbox" checked={allSelected} onChange={toggleAll} />
            Select all
          </label>
        </div>
      )}

      {isLoading && <p className="muted">Loading…</p>}
      {error && <p className="error">{(error as Error).message}</p>}
      {data && data.length === 0 && (
        <div className="empty-state">
          <h2>Nothing waiting on you</h2>
          <p className="muted">
            New artists you add yourself go live right away — this list is only for unattended
            adds (import lists, discovered collaborators).
          </p>
        </div>
      )}
      <div className="album-list">
        {(data || []).map((artist, i) => (
          <motion.div
            key={artist.id}
            className="album-row"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: Math.min(i * 0.03, 0.3) }}
          >
            <label style={{ display: 'flex', alignItems: 'center', marginRight: 4 }}>
              <input
                type="checkbox"
                checked={selected.has(artist.id)}
                onChange={() => toggleOne(artist.id)}
              />
            </label>
            {artist.image_url ? (
              <img src={artist.image_url} alt="" />
            ) : (
              <div className="placeholder-art" style={{ width: 64, height: 64 }} />
            )}
            <div>
              <div>
                <Link to={`/artists/${artist.id}`}>
                  <strong>{artist.name}</strong>
                </Link>{' '}
                <span className="badge queued">
                  {REASON_LABELS[artist.pending_reason || ''] || 'Pending review'}
                </span>
              </div>
              <div className="muted">
                {artist.album_count} albums · {artist.provider}
              </div>
            </div>
            <div className="row-actions">
              <button className="btn" onClick={() => approve.mutate(artist.id)}>
                Approve
              </button>
              <button className="btn ghost" onClick={() => reject.mutate(artist.id)}>
                Reject
              </button>
            </div>
          </motion.div>
        ))}
      </div>
    </div>
  )
}
