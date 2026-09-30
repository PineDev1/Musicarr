import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { motion } from 'framer-motion'
import { useMemo, useState } from 'react'
import { api } from '../api'
import { useToast } from '../Toast'

export function LibraryPage() {
  const [filter, setFilter] = useState('')
  const [genre, setGenre] = useState('')
  const [tag, setTag] = useState('')
  const [selecting, setSelecting] = useState(false)
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [bulkAction, setBulkAction] = useState('')
  const [bulkValue, setBulkValue] = useState('')
  const [mergeGroup, setMergeGroup] = useState<
    { id: number; name: string; provider: string; provider_id: string }[] | null
  >(null)
  const qc = useQueryClient()
  const toast = useToast()
  const { data, isLoading, error } = useQuery({
    queryKey: ['artists', genre],
    queryFn: () => api.artists(genre || undefined),
  })
  const genres = useQuery({ queryKey: ['library-genres'], queryFn: api.libraryGenres })
  const { data: upgradable } = useQuery({
    queryKey: ['upgradable'],
    queryFn: api.upgradable,
  })
  const collisions = useQuery({
    queryKey: ['artist-collisions'],
    queryFn: api.artistCollisions,
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

  const bulk = useMutation({
    mutationFn: () => api.bulkArtistAction([...selected], bulkAction, bulkValue || null),
    onSuccess: (res) => {
      toast.push(`Updated ${res.affected} artist${res.affected === 1 ? '' : 's'}`, 'ok')
      qc.invalidateQueries({ queryKey: ['artists'] })
      qc.invalidateQueries({ queryKey: ['wanted'] })
      qc.invalidateQueries({ queryKey: ['history'] })
      setSelected(new Set())
      setBulkAction('')
      setBulkValue('')
    },
    onError: (err) => toast.push((err as Error).message, 'error'),
  })

  const runBulk = () => {
    if (!bulkAction || !selected.size) return
    if (
      bulkAction === 'delete' &&
      !window.confirm(
        `Remove ${selected.size} artist${selected.size === 1 ? '' : 's'} from Musicarr? Files on disk are kept.`,
      )
    ) {
      return
    }
    bulk.mutate()
  }

  const toggleSelected = (id: number) =>
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
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

  const merge = useMutation({
    mutationFn: (ids: number[]) => api.mergeArtists(ids),
    onSuccess: () => {
      toast.push('Artists merged', 'ok')
      setMergeGroup(null)
      qc.invalidateQueries({ queryKey: ['artists'] })
      qc.invalidateQueries({ queryKey: ['artist-collisions'] })
    },
    onError: (err) => toast.push((err as Error).message, 'error'),
  })

  const filtered = useMemo(() => {
    if (!data) return []
    const q = filter.trim().toLowerCase()
    return data.filter(
      (a) =>
        (!q || a.name.toLowerCase().includes(q)) &&
        (!tag || (a.tags || []).some((t) => t.toLowerCase() === tag.toLowerCase())),
    )
  }, [data, filter, tag])

  const allTags = useMemo(() => {
    const seen = new Map<string, string>()
    for (const a of data || []) for (const t of a.tags || []) seen.set(t.toLowerCase(), t)
    return [...seen.values()].sort((x, y) => x.localeCompare(y))
  }, [data])

  const upgradeCount = upgradable?.length || 0
  const collisionGroups = collisions.data?.groups || []

  return (
    <div>
      <div className="page-header">
        <div>
          <h1>Library</h1>
          <p>Artists you follow. New releases download automatically.</p>
        </div>
        <div className="toolbar" style={{ marginBottom: 0 }}>
          {upgradeCount > 0 && (
            <>
              <Link className="btn secondary" to="/upgrades">
                Upgrades ({upgradeCount})
              </Link>
              <button
                className="btn secondary"
                onClick={() => upgradeAll.mutate()}
                disabled={upgradeAll.isPending}
              >
                {upgradeAll.isPending ? 'Queuing…' : `Upgrade all (${upgradeCount})`}
              </button>
            </>
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

      {collisionGroups.length > 0 && (
        <div className="banner" style={{ marginBottom: '1rem' }}>
          <strong>{collisionGroups.length}</strong> possible duplicate artist name
          {collisionGroups.length === 1 ? '' : 's'}.{' '}
          <button
            type="button"
            className="btn ghost"
            style={{ display: 'inline' }}
            onClick={() => setMergeGroup(collisionGroups[0])}
          >
            Review first group
          </button>
        </div>
      )}

      {mergeGroup && (
        <div className="banner" style={{ marginBottom: '1rem' }}>
          <p style={{ marginTop: 0 }}>
            These look like the same artist — merge into one library entry?
          </p>
          <ul style={{ margin: '0.5rem 0' }}>
            {mergeGroup.map((a) => (
              <li key={a.id}>
                {a.name}{' '}
                <span className="muted">
                  ({a.provider} · {a.provider_id})
                </span>
              </li>
            ))}
          </ul>
          <div className="toolbar" style={{ marginBottom: 0 }}>
            <button
              className="btn"
              disabled={merge.isPending}
              onClick={() => merge.mutate(mergeGroup.map((a) => a.id))}
            >
              Merge
            </button>
            <button className="btn ghost" type="button" onClick={() => setMergeGroup(null)}>
              Keep separate
            </button>
            {collisionGroups.length > 1 && (
              <button
                className="btn ghost"
                type="button"
                onClick={() => {
                  const idx = collisionGroups.findIndex(
                    (g) => g[0]?.id === mergeGroup[0]?.id,
                  )
                  const next = collisionGroups[(idx + 1) % collisionGroups.length]
                  setMergeGroup(next)
                }}
              >
                Next group
              </button>
            )}
          </div>
        </div>
      )}

      {data && data.length > 0 && (
        <div className="toolbar">
          <input
            type="text"
            placeholder="Filter artists…"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            style={{ flex: 1, minWidth: 180 }}
          />
          <button
            type="button"
            className={`btn ${selecting ? '' : 'secondary'}`}
            onClick={() => {
              setSelecting((v) => !v)
              setSelected(new Set())
            }}
          >
            {selecting ? 'Done' : 'Select'}
          </button>
          {!!allTags.length && (
            <select value={tag} onChange={(e) => setTag(e.target.value)} style={{ minWidth: 140 }}>
              <option value="">All tags</option>
              {allTags.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          )}
          {!!genres.data?.length && (
            <select value={genre} onChange={(e) => setGenre(e.target.value)} style={{ minWidth: 160 }}>
              <option value="">All genres</option>
              {genres.data.map((g) => (
                <option key={g.genre} value={g.genre}>
                  {g.genre} ({g.count})
                </option>
              ))}
            </select>
          )}
        </div>
      )}

      {selecting && (
        <div className="toolbar" style={{ flexWrap: 'wrap' }}>
          <strong>{selected.size} selected</strong>
          <button
            type="button"
            className="btn ghost"
            onClick={() => setSelected(new Set(filtered.map((a) => a.id)))}
          >
            Select all {filtered.length}
          </button>
          <button type="button" className="btn ghost" onClick={() => setSelected(new Set())}>
            Clear
          </button>
          <select
            value={bulkAction}
            onChange={(e) => {
              setBulkAction(e.target.value)
              setBulkValue('')
            }}
          >
            <option value="">Action…</option>
            <option value="monitor">Monitor</option>
            <option value="unmonitor">Unmonitor</option>
            <option value="set_quality">Set quality</option>
            <option value="set_auto_grab">Set indexer auto-grab</option>
            <option value="add_tag">Add tag</option>
            <option value="remove_tag">Remove tag</option>
            <option value="delete">Remove from library</option>
          </select>
          {bulkAction === 'set_quality' && (
            <select value={bulkValue} onChange={(e) => setBulkValue(e.target.value)}>
              <option value="">Inherit default</option>
              <option value="flac">FLAC</option>
              <option value="320">MP3 320</option>
              <option value="128">MP3 128</option>
            </select>
          )}
          {bulkAction === 'set_auto_grab' && (
            <select value={bulkValue} onChange={(e) => setBulkValue(e.target.value)}>
              <option value="">Inherit default</option>
              <option value="on">Enabled</option>
              <option value="off">Disabled</option>
            </select>
          )}
          {(bulkAction === 'add_tag' || bulkAction === 'remove_tag') && (
            <input
              type="text"
              placeholder="Tag"
              value={bulkValue}
              maxLength={32}
              onChange={(e) => setBulkValue(e.target.value)}
            />
          )}
          <button
            type="button"
            className={`btn ${bulkAction === 'delete' ? 'danger' : ''}`}
            disabled={
              bulk.isPending ||
              !bulkAction ||
              !selected.size ||
              ((bulkAction === 'add_tag' || bulkAction === 'remove_tag') && !bulkValue.trim())
            }
            onClick={runBulk}
          >
            Apply
          </button>
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
              <Link
                to={`/artists/${artist.id}`}
                className="artist-tile"
                onClick={(e) => {
                  if (!selecting) return
                  e.preventDefault()
                  toggleSelected(artist.id)
                }}
                style={
                  selecting && selected.has(artist.id)
                    ? { outline: '3px solid var(--accent)', outlineOffset: 2, borderRadius: 8 }
                    : undefined
                }
              >
                {artist.image_url ? (
                  <img src={artist.image_url} alt="" />
                ) : (
                  <div className="placeholder-art">No art</div>
                )}
                <div className="name">
                  {selecting && (
                    <input
                      type="checkbox"
                      readOnly
                      checked={selected.has(artist.id)}
                      style={{ marginRight: 6 }}
                    />
                  )}
                  {artist.name}
                </div>
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
