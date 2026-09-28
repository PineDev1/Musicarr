import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, type DownloadJob } from '../api'
import { useToast } from '../Toast'
import { ReleaseResultsTable } from '../components/ReleaseResultsTable'

type LiveJob = {
  id: number
  album_id: number | null
  artist_name: string
  album_title: string
  state: string
  progress: number
  error: string | null
}

function normTitle(title: string) {
  return title.trim().toLowerCase().replace(/\s+/g, ' ')
}

export function ArtistPage() {
  const { id } = useParams()
  const artistId = Number(id)
  const qc = useQueryClient()
  const toast = useToast()
  const [liveJobs, setLiveJobs] = useState<LiveJob[]>([])
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [showIndexerSearch, setShowIndexerSearch] = useState(false)
  const { data, isLoading, error } = useQuery({
    queryKey: ['artist', artistId],
    queryFn: () => api.artist(artistId),
    enabled: Number.isFinite(artistId),
  })
  const health = useQuery({ queryKey: ['health'], queryFn: api.health })
  const artistReleases = useQuery({
    queryKey: ['artist-releases', artistId],
    queryFn: () => api.searchReleasesForArtist(artistId),
    enabled: showIndexerSearch && Number.isFinite(artistId),
  })
  const grabFromArtist = useMutation({
    mutationFn: (release: {
      grab_url: string
      protocol: 'usenet' | 'torrent'
      indexer_id: number
      title: string
      matched_album_id: number | null
    }) =>
      api.grabRelease(
        release.matched_album_id != null
          ? {
              album_id: release.matched_album_id,
              grab_url: release.grab_url,
              protocol: release.protocol,
              indexer_id: release.indexer_id,
              title: release.title,
            }
          : {
              artist_id: artistId,
              grab_url: release.grab_url,
              protocol: release.protocol,
              indexer_id: release.indexer_id,
              title: release.title,
            },
      ),
    onSuccess: () => {
      toast.push('Sent to download client', 'ok')
      qc.invalidateQueries({ queryKey: ['queue'] })
      qc.invalidateQueries({ queryKey: ['artist', artistId] })
    },
    onError: (err) => toast.push((err as Error).message, 'error'),
  })
  const { data: queueJobs } = useQuery({
    queryKey: ['queue'],
    queryFn: () => api.queue(true),
    refetchInterval: 2000,
  })
  const similar = useQuery({
    queryKey: ['similar-artists', artistId],
    queryFn: () => api.similarArtists(artistId),
    enabled: Number.isFinite(artistId),
    retry: false,
  })

  useEffect(() => {
    const es = new EventSource('/api/events/queue')
    es.onmessage = (ev) => {
      try {
        const snap = JSON.parse(ev.data) as LiveJob[]
        setLiveJobs(snap)
      } catch {
        /* ignore */
      }
    }
    return () => es.close()
  }, [])

  const activeJobs = useMemo(() => {
    const byId = new Map<number, LiveJob | DownloadJob>()
    for (const j of queueJobs || []) {
      if (j.state === 'queued' || j.state === 'running' || j.state === 'failed') {
        byId.set(j.id, j)
      }
    }
    for (const j of liveJobs) {
      const prev = byId.get(j.id)
      byId.set(j.id, prev ? { ...prev, ...j } : j)
    }
    return Array.from(byId.values())
  }, [queueJobs, liveJobs])

  const jobForAlbum = (albumId: number, albumTitle: string) => {
    const byId = activeJobs.find(
      (j) => j.album_id === albumId && (j.state === 'queued' || j.state === 'running' || j.state === 'failed'),
    )
    if (byId) return byId
    const title = normTitle(albumTitle)
    return activeJobs.find(
      (j) =>
        (j.state === 'queued' || j.state === 'running' || j.state === 'failed') &&
        normTitle(j.album_title) === title &&
        (!data?.name || normTitle(j.artist_name) === normTitle(data.name)),
    )
  }

  const hasActiveDownload = useMemo(() => {
    if (!data?.albums?.length) return false
    return data.albums.some((a) => {
      const j = activeJobs.find(
        (job) =>
          (job.state === 'queued' || job.state === 'running') &&
          (job.album_id === a.id ||
            (normTitle(job.album_title) === normTitle(a.title) &&
              normTitle(job.artist_name) === normTitle(data.name))),
      )
      return !!j
    })
  }, [activeJobs, data])

  useEffect(() => {
    if (!hasActiveDownload) return
    const t = window.setInterval(() => {
      qc.invalidateQueries({ queryKey: ['artist', artistId] })
      qc.invalidateQueries({ queryKey: ['queue'] })
    }, 3000)
    return () => window.clearInterval(t)
  }, [hasActiveDownload, artistId, qc])

  const hadActiveRef = useRef(false)
  useEffect(() => {
    if (hadActiveRef.current && !hasActiveDownload) {
      qc.invalidateQueries({ queryKey: ['artist', artistId] })
      qc.invalidateQueries({ queryKey: ['artists'] })
      qc.invalidateQueries({ queryKey: ['health'] })
    }
    hadActiveRef.current = hasActiveDownload
  }, [hasActiveDownload, artistId, qc])

  const refresh = useMutation({
    mutationFn: () => api.refreshArtist(artistId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['artist', artistId] })
      toast.push('Metadata refreshed', 'ok')
    },
    onError: (err) => toast.push((err as Error).message, 'error'),
  })
  const downloadMissing = useMutation({
    mutationFn: () => api.downloadMissing(artistId),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ['queue'] })
      qc.invalidateQueries({ queryKey: ['health'] })
      toast.push(`Queued ${res.queued} album(s)`, 'ok')
    },
    onError: (err) => toast.push((err as Error).message, 'error'),
  })
  const remove = useMutation({
    mutationFn: () => api.deleteArtist(artistId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['artists'] })
      window.location.href = '/'
    },
    onError: (err) => toast.push((err as Error).message, 'error'),
  })
  const patchArtist = useMutation({
    mutationFn: (body: Record<string, unknown>) => api.patchArtist(artistId, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['artist', artistId] })
      qc.invalidateQueries({ queryKey: ['artists'] })
      qc.invalidateQueries({ queryKey: ['wanted'] })
      toast.push('Artist monitoring updated', 'ok')
    },
    onError: (err) => toast.push((err as Error).message, 'error'),
  })
  const approve = useMutation({
    mutationFn: () => api.approveArtist(artistId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['artist', artistId] })
      qc.invalidateQueries({ queryKey: ['pending-artists'] })
      qc.invalidateQueries({ queryKey: ['health'] })
      toast.push('Artist approved', 'ok')
    },
    onError: (err) => toast.push((err as Error).message, 'error'),
  })
  const reject = useMutation({
    mutationFn: () => api.rejectArtist(artistId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['pending-artists'] })
      qc.invalidateQueries({ queryKey: ['health'] })
      toast.push('Artist rejected', 'ok')
      window.location.href = '/pending-artists'
    },
    onError: (err) => toast.push((err as Error).message, 'error'),
  })
  const patchAlbum = useMutation({
    mutationFn: ({ albumId, body }: { albumId: number; body: Record<string, unknown> }) =>
      api.patchAlbum(albumId, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['artist', artistId] }),
    onError: (err) => toast.push((err as Error).message, 'error'),
  })
  const downloadAlbum = useMutation({
    mutationFn: ({ albumId, upgrade }: { albumId: number; upgrade?: boolean }) =>
      api.downloadAlbum(albumId, upgrade),
    onSuccess: (res) => {
      if (!res.queued) {
        toast.push('Could not queue download', 'error')
        return
      }
      qc.invalidateQueries({ queryKey: ['queue'] })
      qc.invalidateQueries({ queryKey: ['health'] })
      qc.invalidateQueries({ queryKey: ['upgradable'] })
      toast.push('Queued download', 'ok')
    },
    onError: (err) => toast.push((err as Error).message, 'error'),
  })
  const cancelJob = useMutation({
    mutationFn: (jobId: number) => api.cancelJob(jobId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['queue'] }),
    onError: (err) => toast.push((err as Error).message, 'error'),
  })
  const bulkDownload = useMutation({
    mutationFn: () => api.bulkDownloadAlbums([...selected]),
    onSuccess: (res) => {
      toast.push(`Queued ${res.queued} album(s)`, 'ok')
      setSelected(new Set())
      qc.invalidateQueries({ queryKey: ['artist', artistId] })
      qc.invalidateQueries({ queryKey: ['queue'] })
      qc.invalidateQueries({ queryKey: ['health'] })
    },
    onError: (err) => toast.push((err as Error).message, 'error'),
  })
  const bulkSkip = useMutation({
    mutationFn: () => api.bulkSkipAlbums([...selected]),
    onSuccess: (res) => {
      toast.push(`Skipped ${res.skipped} album(s)`, 'ok')
      setSelected(new Set())
      qc.invalidateQueries({ queryKey: ['artist', artistId] })
    },
    onError: (err) => toast.push((err as Error).message, 'error'),
  })

  if (isLoading) return <p className="muted">Loading…</p>
  if (error) return <p className="error">{(error as Error).message}</p>
  if (!data) return <p className="muted">Artist not found.</p>

  const sources = data.providers?.length ? data.providers : [data.provider]
  const monitorMode = data.monitor_mode || (data.monitored ? 'all' : 'none')
  const skippedOfficialHint = (data.albums || []).filter(
    (a) => a.status === 'skipped' && !a.monitored,
  ).length
  const missingCount =
    data.missing_count ??
    (data.albums || []).filter((a) => a.status === 'missing').length
  const related = data.related_artists || []
  // Skipped albums and singles clutter the main list without adding much —
  // tuck them into the same collapsed section junk releases already use,
  // hidden by default, so the main list only shows what's actually wanted
  // or downloaded.
  const isHidden = (a: (typeof data.albums)[number]) =>
    a.skip_reason_code === 'junk' || a.status === 'skipped' || a.album_type === 'single'
  const mainAlbums = data.albums.filter((a) => !isHidden(a))
  const junkAlbums = data.albums.filter(isHidden)

  const jobForRow = (album: (typeof data.albums)[number]) => jobForAlbum(album.id, album.title)
  const selectableIds = mainAlbums
    .filter((a) => {
      const job = jobForRow(a)
      const downloading = job && (job.state === 'queued' || job.state === 'running')
      return !downloading && a.status !== 'downloaded' && a.status !== 'missing'
    })
    .map((a) => a.id)
  const allSelectableSelected =
    selectableIds.length > 0 && selectableIds.every((id) => selected.has(id))

  function toggleOne(id: number) {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  function toggleAllSelectable() {
    setSelected((prev) => {
      const next = new Set(prev)
      if (allSelectableSelected) {
        for (const id of selectableIds) next.delete(id)
      } else {
        for (const id of selectableIds) next.add(id)
      }
      return next
    })
  }

  return (
    <div>
      {data.status === 'pending' && (
        <div className="banner" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12 }}>
          <span>
            This artist is awaiting your approval
            {data.pending_reason === 'import_list' ? ' (added by an import list)' : ''}
            {data.pending_reason === 'featured' ? ' (discovered as a featured artist)' : ''}
            {' '}— nothing will download until you approve it.
          </span>
          <div className="row-actions">
            <button className="btn" onClick={() => approve.mutate()} disabled={approve.isPending}>
              Approve
            </button>
            <button className="btn ghost" onClick={() => reject.mutate()} disabled={reject.isPending}>
              Reject
            </button>
          </div>
        </div>
      )}
      <div className="page-header">
        <div>
          <p className="muted" style={{ marginBottom: '0.5rem' }}>
            <Link to="/">Library</Link> / {data.name}
          </p>
          <h1>{data.name}</h1>
          <p>
            {data.downloaded_count} downloaded · {data.wanted_count} wanted
            {missingCount > 0 ? ` · ${missingCount} missing on provider` : ''} ·{' '}
            {data.album_count} total
          </p>
          <p className="muted" style={{ marginTop: '0.35rem' }}>
            Source:{' '}
            {sources.map((p) => (
              <span key={p} className="badge queued" style={{ marginRight: 6, textTransform: 'capitalize' }}>
                {p}
              </span>
            ))}
            {data.musicbrainz_id ? (
              <span className="muted" title={data.musicbrainz_id}>
                · Catalog from MusicBrainz
              </span>
            ) : null}
            {data.name_collision ? (
              <span className="muted" title="Another artist in your library shares this name">
                · id {data.provider_id} (same name as another artist — kept separate)
              </span>
            ) : null}
          </p>
          {missingCount > 0 && (
            <p className="error" style={{ marginTop: '0.35rem' }}>
              {missingCount} official MusicBrainz release(s) are not available on{' '}
              {sources.join(' / ')}. See albums marked missing below.
            </p>
          )}
          {skippedOfficialHint > 0 && (
            <p className="muted" style={{ marginTop: '0.35rem' }}>
              {skippedOfficialHint} provider-only album(s) skipped (not on MusicBrainz) — use Want
              on a row to keep one.
            </p>
          )}
          {related.length > 0 && (
            <p className="muted" style={{ marginTop: '0.5rem' }}>
              Featured / related:{' '}
              {related.map((r, i) => (
                <span key={`${r.name}-${i}`}>
                  {i > 0 ? ', ' : ''}
                  {r.id ? <Link to={`/artists/${r.id}`}>{r.name}</Link> : r.name}
                </span>
              ))}
            </p>
          )}
          {!!similar.data?.length && (
            <p className="muted" style={{ marginTop: '0.5rem' }}>
              You might also like:{' '}
              {similar.data.map((s, i) => (
                <span key={`${s.name}-${i}`}>
                  {i > 0 ? ', ' : ''}
                  {s.already_in_library ? (
                    <Link to={`/artists/${s.already_in_library}`}>{s.name}</Link>
                  ) : (
                    <Link to={`/add?q=${encodeURIComponent(s.name)}`}>{s.name}</Link>
                  )}
                </span>
              ))}
            </p>
          )}
        </div>
        {data.image_url && (
          <img
            src={data.image_url}
            alt=""
            style={{ width: 120, height: 120, borderRadius: 10, objectFit: 'cover' }}
          />
        )}
      </div>

      <div className="toolbar" style={{ flexWrap: 'wrap', alignItems: 'flex-end' }}>
        <div className="field" style={{ margin: 0, minWidth: 180 }}>
          <label>Monitor</label>
          <select
            value={monitorMode}
            onChange={(e) => patchArtist.mutate({ monitor_mode: e.target.value })}
            disabled={patchArtist.isPending}
          >
            <option value="all">All albums</option>
            <option value="new">New albums only</option>
            <option value="none">Unmonitored</option>
          </select>
        </div>
        <div className="field" style={{ margin: 0, minWidth: 180 }}>
          <label>Downloads</label>
          <select
            value={data.download_mode || ''}
            onChange={(e) =>
              patchArtist.mutate({ download_mode: e.target.value || null })
            }
            disabled={patchArtist.isPending}
          >
            <option value="">Use default</option>
            <option value="auto">Auto-download</option>
            <option value="manual">Manual approval</option>
          </select>
        </div>
        <div className="field" style={{ margin: 0, minWidth: 180 }}>
          <label>Quality</label>
          <select
            value={data.quality_pref || ''}
            onChange={(e) =>
              patchArtist.mutate({ quality_pref: e.target.value || null })
            }
            disabled={patchArtist.isPending}
          >
            <option value="">Inherit default</option>
            <option value="flac">FLAC (lossless)</option>
            <option value="320">MP3 320kbps</option>
            <option value="128">MP3 128kbps</option>
          </select>
        </div>
        <div className="field" style={{ margin: 0, minWidth: 180 }}>
          <label>Auto-grab (indexers)</label>
          <select
            value={data.auto_grab_override || ''}
            onChange={(e) =>
              patchArtist.mutate({ auto_grab_override: e.target.value || null })
            }
            disabled={patchArtist.isPending}
          >
            <option value="">Inherit default</option>
            <option value="on">Enabled</option>
            <option value="off">Disabled</option>
          </select>
        </div>
        <TagsEditor
          tags={data.tags || []}
          disabled={patchArtist.isPending}
          onChange={(tags) => patchArtist.mutate({ tags })}
        />
        <div className="field" style={{ margin: 0, minWidth: 220 }}>
          <label>Include singles</label>
          <label className="muted" style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <input
              type="checkbox"
              checked={data.include_singles === true}
              onChange={(e) => {
                patchArtist.mutate({
                  include_singles: e.target.checked ? true : false,
                })
              }}
              disabled={patchArtist.isPending}
            />
            Match &amp; queue MusicBrainz singles
          </label>
          <span className="muted tiny">Changing this rescans MusicBrainz like Lidarr.</span>
        </div>
        <button className="btn secondary" onClick={() => refresh.mutate()} disabled={refresh.isPending}>
          Refresh metadata
        </button>
        <button className="btn" onClick={() => downloadMissing.mutate()} disabled={downloadMissing.isPending}>
          Download missing
        </button>
        <button
          className="btn danger"
          onClick={() => {
            if (
              window.confirm(
                `Remove ${data.name} from your library (all linked sources: ${sources.join(', ')})?`,
              )
            ) {
              remove.mutate()
            }
          }}
          disabled={remove.isPending}
        >
          Remove artist
        </button>
        {health.data && health.data.resolved_acquisition_mode !== 'streaming' && (
          <button className="btn secondary" onClick={() => setShowIndexerSearch((v) => !v)}>
            {showIndexerSearch ? 'Hide indexer search' : 'Search indexers for this artist'}
          </button>
        )}
      </div>

      {showIndexerSearch && (
        <div className="card" style={{ marginBottom: '1rem' }}>
          <h3 style={{ margin: '0 0 0.25rem', fontSize: '1.05rem' }}>Indexer releases for {data.name}</h3>
          <p className="muted" style={{ marginTop: 0 }}>
            Every indexer result for this artist, mixed across all their releases. Rows tagged
            "New release" don't match an album Musicarr already knows about — grabbing one
            resolves or creates the right album automatically (via MusicBrainz when possible).
          </p>
          <ReleaseResultsTable
            results={artistReleases.data?.results}
            errors={artistReleases.data?.errors}
            isLoading={artistReleases.isLoading}
            error={artistReleases.error as Error | null}
            grabPending={grabFromArtist.isPending}
            showAlbumBadge
            onGrab={(r) =>
              grabFromArtist.mutate({
                grab_url: r.grab_url,
                protocol: r.protocol as 'usenet' | 'torrent',
                indexer_id: r.indexer_id,
                title: r.title,
                matched_album_id: r.matched_album_id,
              })
            }
          />
        </div>
      )}

      {selectableIds.length > 0 && (
        <div className="toolbar" style={{ flexWrap: 'wrap' }}>
          <label className="muted" style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <input type="checkbox" checked={allSelectableSelected} onChange={toggleAllSelectable} />
            Select all
          </label>
          {selected.size > 0 && (
            <>
              <button className="btn" onClick={() => bulkDownload.mutate()} disabled={bulkDownload.isPending}>
                Download selected ({selected.size})
              </button>
              <button className="btn ghost" onClick={() => bulkSkip.mutate()} disabled={bulkSkip.isPending}>
                Skip selected
              </button>
            </>
          )}
        </div>
      )}

      <div className="album-list">
        {mainAlbums.map((album) => {
          const isDownloaded = album.status === 'downloaded'
          const via = (album.provider || 'unknown').toLowerCase()
          const job = jobForAlbum(album.id, album.title)
          const downloading = job && (job.state === 'queued' || job.state === 'running')
          const failed = job && job.state === 'failed'
          const selectable = !downloading && album.status !== 'downloaded' && album.status !== 'missing'
          return (
            <div key={album.id} className="album-row">
              {selectable && (
                <label style={{ display: 'flex', alignItems: 'center', marginRight: 4 }}>
                  <input
                    type="checkbox"
                    checked={selected.has(album.id)}
                    onChange={() => toggleOne(album.id)}
                  />
                </label>
              )}
              {album.cover_url ? (
                <img src={album.cover_url} alt="" />
              ) : (
                <div className="placeholder-art" style={{ width: 64, height: 64 }} />
              )}
              <div style={{ minWidth: 0 }}>
                <div>
                  <Link to={`/albums/${album.id}`}>
                    <strong>{album.title}</strong>
                  </Link>{' '}
                  {album.artist_credit ? (
                    <span className="muted" style={{ fontWeight: 400 }}>
                      · {album.artist_credit}
                    </span>
                  ) : null}{' '}
                  {downloading ? (
                    <span className={`badge ${job.state}`}>{job.state}</span>
                  ) : failed ? (
                    <span className="badge failed">failed</span>
                  ) : (
                    <span className={`badge ${album.status}`}>{album.status}</span>
                  )}
                  {album.upgrade_available && (
                    <span className="badge upgrade" style={{ marginLeft: 6 }}>
                      upgrade
                    </span>
                  )}
                </div>
                <div className="muted">
                  {album.release_date || 'Unknown date'} · {album.album_type} · {album.track_count}{' '}
                  tracks
                  {album.quality ? ` · ${album.quality.toUpperCase()}` : ''}
                </div>
                {album.status === 'missing' && album.status_reason ? (
                  <div className="error" style={{ marginTop: 4, fontSize: '0.85rem' }}>
                    {album.status_reason}
                  </div>
                ) : null}
                {album.status === 'skipped' && album.status_reason ? (
                  <div className="muted" style={{ marginTop: 4, fontSize: '0.85rem' }}>
                    {album.status_reason}
                  </div>
                ) : null}
                <div style={{ marginTop: 6 }}>
                  {downloading ? (
                    <div>
                      <div className="muted" style={{ fontSize: '0.85rem' }}>
                        {job.state === 'queued' ? 'Queued…' : `Downloading… ${job.progress.toFixed(0)}%`}
                      </div>
                      <div className="progress">
                        <span style={{ width: `${Math.min(100, Math.max(2, job.progress))}%` }} />
                      </div>
                    </div>
                  ) : failed ? (
                    <div className="error" style={{ fontSize: '0.85rem' }}>
                      {job.error || 'Download failed'}
                    </div>
                  ) : isDownloaded ? (
                    <span className="badge downloaded" style={{ textTransform: 'capitalize' }}>
                      Via {via}
                    </span>
                  ) : (
                    <span className="muted">Not downloaded</span>
                  )}
                </div>
              </div>
              <div className="row-actions">
                {downloading && job && (
                  <button className="btn ghost" onClick={() => cancelJob.mutate(job.id)}>
                    Cancel
                  </button>
                )}
                {!downloading && album.upgrade_available && (
                  <button
                    className="btn secondary"
                    onClick={() => downloadAlbum.mutate({ albumId: album.id, upgrade: true })}
                    disabled={downloadAlbum.isPending}
                  >
                    Upgrade
                  </button>
                )}
                {!downloading && album.status !== 'downloaded' && album.status !== 'missing' && (
                  <button
                    className="btn secondary"
                    onClick={() => downloadAlbum.mutate({ albumId: album.id })}
                    disabled={downloadAlbum.isPending}
                  >
                    {failed ? 'Retry' : 'Download'}
                  </button>
                )}
                {album.status === 'missing' && (
                  <span className="muted" style={{ fontSize: '0.85rem' }}>
                    Unavailable on provider
                  </span>
                )}
                {album.status !== 'skipped' ? (
                  <button
                    className="btn ghost"
                    onClick={() =>
                      patchAlbum.mutate({
                        albumId: album.id,
                        body: { status: 'skipped', monitored: false },
                      })
                    }
                    disabled={!!downloading}
                  >
                    Skip
                  </button>
                ) : (
                  <button
                    className="btn ghost"
                    onClick={() =>
                      patchAlbum.mutate({
                        albumId: album.id,
                        body: { status: 'wanted', monitored: true },
                      })
                    }
                  >
                    Want
                  </button>
                )}
              </div>
            </div>
          )
        })}
      </div>

      {junkAlbums.length > 0 && (
        <details className="junk-releases">
          <summary>Skipped, singles &amp; junk ({junkAlbums.length})</summary>
          <div className="album-list">
            {junkAlbums.map((album) => {
              const via = (album.provider || 'unknown').toLowerCase()
              const isDownloaded = album.status === 'downloaded'
              return (
                <div key={album.id} className="album-row">
                  {album.cover_url ? (
                    <img src={album.cover_url} alt="" />
                  ) : (
                    <div className="placeholder-art" style={{ width: 64, height: 64 }} />
                  )}
                  <div style={{ minWidth: 0 }}>
                    <div>
                      <Link to={`/albums/${album.id}`}>
                        <strong>{album.title}</strong>
                      </Link>{' '}
                      <span className={`badge ${album.status}`}>{album.status}</span>
                    </div>
                    <div className="muted">
                      {album.release_date || 'Unknown date'} · {album.album_type} ·{' '}
                      {album.track_count} tracks
                    </div>
                    {album.status_reason ? (
                      <div className="muted" style={{ marginTop: 4, fontSize: '0.85rem' }}>
                        {album.status_reason}
                      </div>
                    ) : null}
                    {isDownloaded && (
                      <span className="badge downloaded" style={{ textTransform: 'capitalize' }}>
                        Via {via}
                      </span>
                    )}
                  </div>
                  <div className="row-actions">
                    {album.status === 'skipped' ? (
                      <button
                        className="btn ghost"
                        onClick={() =>
                          patchAlbum.mutate({
                            albumId: album.id,
                            body: { status: 'wanted', monitored: true },
                          })
                        }
                      >
                        Want
                      </button>
                    ) : album.status !== 'downloaded' && album.status !== 'missing' ? (
                      <>
                        <button
                          className="btn secondary"
                          onClick={() => downloadAlbum.mutate({ albumId: album.id })}
                          disabled={downloadAlbum.isPending}
                        >
                          Download
                        </button>
                        <button
                          className="btn ghost"
                          onClick={() =>
                            patchAlbum.mutate({
                              albumId: album.id,
                              body: { status: 'skipped', monitored: false },
                            })
                          }
                        >
                          Skip
                        </button>
                      </>
                    ) : null}
                  </div>
                </div>
              )
            })}
          </div>
        </details>
      )}
    </div>
  )
}

function TagsEditor({
  tags,
  disabled,
  onChange,
}: {
  tags: string[]
  disabled: boolean
  onChange: (tags: string[]) => void
}) {
  const [draft, setDraft] = useState('')
  const add = () => {
    const t = draft.trim()
    if (!t) return
    onChange([...tags, t])
    setDraft('')
  }
  return (
    <div className="field" style={{ margin: 0, minWidth: 220 }}>
      <label>Tags</label>
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
        {tags.map((t) => (
          <span key={t} className="badge queued" style={{ display: 'inline-flex', gap: 4 }}>
            {t}
            <button
              type="button"
              aria-label={`Remove tag ${t}`}
              disabled={disabled}
              onClick={() => onChange(tags.filter((x) => x !== t))}
              style={{ background: 'none', border: 0, color: 'inherit', cursor: 'pointer', padding: 0 }}
            >
              ×
            </button>
          </span>
        ))}
        <input
          type="text"
          value={draft}
          maxLength={32}
          placeholder="Add tag…"
          disabled={disabled}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault()
              add()
            }
          }}
          style={{ width: 110 }}
        />
      </div>
    </div>
  )
}
