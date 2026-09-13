import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { motion } from 'framer-motion'
import { useMemo, useState } from 'react'
import { api } from '../api'
import { useToast } from '../Toast'

export function LibraryPage() {
  const [filter, setFilter] = useState('')
  const qc = useQueryClient()
  const toast = useToast()
  const { data, isLoading, error } = useQuery({
    queryKey: ['artists'],
    queryFn: api.artists,
  })
  const { data: upgradable } = useQuery({
    queryKey: ['upgradable'],
    queryFn: api.upgradable,
  })

  const scan = useMutation({
    mutationFn: api.runMonitor,
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ['artists'] })
      qc.invalidateQueries({ queryKey: ['wanted'] })
      qc.invalidateQueries({ queryKey: ['queue'] })
      qc.invalidateQueries({ queryKey: ['health'] })
      toast.push(
        `Scan complete: ${res.artists_checked} artists, ${res.new_albums} new album(s)`,
        'ok',
      )
    },
    onError: (err) => toast.push((err as Error).message, 'error'),
  })

  const upgradeAll = useMutation({
    mutationFn: api.upgradeAll,
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ['upgradable'] })
      qc.invalidateQueries({ queryKey: ['queue'] })
      qc.invalidateQueries({ queryKey: ['health'] })
      toast.push(
        res.queued
          ? `Queued ${res.queued} upgrade(s) to ${res.target || 'target quality'}`
          : res.message || 'Nothing to upgrade',
        'ok',
      )
    },
    onError: (err) => toast.push((err as Error).message, 'error'),
  })

  const filtered = useMemo(() => {
    if (!data) return []
    const q = filter.trim().toLowerCase()
    if (!q) return data
    return data.filter((a) => a.name.toLowerCase().includes(q))
  }, [data, filter])

  const upgradeCount = upgradable?.length || 0

  return (
    <div>
      <div className="page-header">
        <div>
          <h1>Library</h1>
          <p>Artists you follow. New releases download automatically.</p>
        </div>
        <div className="toolbar" style={{ marginBottom: 0 }}>
          {upgradeCount > 0 && (
            <button
              className="btn secondary"
              onClick={() => upgradeAll.mutate()}
              disabled={upgradeAll.isPending}
            >
              {upgradeAll.isPending ? 'Queuing…' : `Upgrade all (${upgradeCount})`}
            </button>
          )}
          <button
            className="btn secondary"
            onClick={() => scan.mutate()}
            disabled={scan.isPending}
          >
            {scan.isPending ? 'Scanning…' : 'Scan for new music'}
          </button>
          <Link className="btn" to="/add">
            Add Artist
          </Link>
        </div>
      </div>

      {data && data.length > 0 && (
        <div className="toolbar">
          <input
            type="text"
            placeholder="Filter artists…"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            style={{ flex: 1, minWidth: 180 }}
          />
        </div>
      )}

      {isLoading && <p className="muted">Loading…</p>}
      {error && <p className="error">{(error as Error).message}</p>}
      {data && data.length === 0 && (
        <div className="empty-state">
          <h2>No artists yet</h2>
          <p className="muted">Add an artist to start building your library.</p>
          <Link className="btn" to="/add">
            Add your first artist
          </Link>
        </div>
      )}
      {data && data.length > 0 && filtered.length === 0 && (
        <p className="muted">No artists match “{filter}”.</p>
      )}
      {filtered.length > 0 && (
        <div className="grid">
          {filtered.map((artist, i) => (
            <motion.div
              key={artist.id}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: Math.min(i * 0.03, 0.35), duration: 0.28 }}
            >
              <Link to={`/artists/${artist.id}`} className="artist-tile">
                {artist.image_url ? (
                  <img src={artist.image_url} alt="" />
                ) : (
                  <div className="placeholder-art">No art</div>
                )}
                <div className="name">{artist.name}</div>
                <div className="meta">
                  {artist.downloaded_count}/{artist.album_count} albums
                  {artist.wanted_count > 0 ? ` · ${artist.wanted_count} wanted` : ''}
                  {artist.name_collision
                    ? ` · ${(artist.provider || 'source').toLowerCase()} ${artist.provider_id}`
                    : artist.providers && artist.providers.length > 1
                      ? ` · ${artist.providers.join(' + ')}`
                      : ''}
                </div>
              </Link>
            </motion.div>
          ))}
        </div>
      )}
    </div>
  )
}
