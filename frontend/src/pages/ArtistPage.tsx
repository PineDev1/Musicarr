import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, type DownloadJob } from '../api'
import { useToast } from '../Toast'

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

  const { data, isLoading, error } = useQuery({
    queryKey: ['artist', artistId],
    queryFn: () => api.artist(artistId),
    enabled: Number.isFinite(artistId),
  })

  const { data: queueJobs } = useQuery({
    queryKey: ['queue'],
    queryFn: () => api.queue(true),
    refetchInterval: 2000,
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
  const patchAlbum = useMutation({
    mutationFn: ({ albumId, body }: { albumId: number; body: Record<string, unknown> }) =>
      api.patchAlbum(albumId, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['artist', artistId] }),
  })
  const downloadAlbum = useMutation({
    mutationFn: (albumId: number) => api.downloadAlbum(albumId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['queue'] })
      qc.invalidateQueries({ queryKey: ['health'] })
    },
    onError: (err) => toast.push((err as Error).message, 'error'),
  })
  const cancelJob = useMutation({
    mutationFn: (jobId: number) => api.cancelJob(jobId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['queue'] }),
  })

  if (isLoading) return <p className="muted">Loading…</p>
  if (error) return <p className="error">{(error as Error).message}</p>
  if (!data) return <p className="muted">Artist not found.</p>

  const sources = data.providers?.length ? data.providers : [data.provider]

  return (
    <div>
      <div className="page-header">
        <div>
          <p className="muted" style={{ marginBottom: '0.5rem' }}>
            <Link to="/">Library</Link> / {data.name}
          </p>
          <h1>{data.name}</h1>
          <p>
            {data.downloaded_count} downloaded · {data.wanted_count} wanted · {data.album_count}{' '}
            total
          </p>
          <p className="muted" style={{ marginTop: '0.35rem' }}>
            Linked sources:{' '}
            {sources.map((p) => (
              <span key={p} className="badge queued" style={{ marginRight: 6, textTransform: 'capitalize' }}>
                {p}
              </span>
            ))}
          </p>
        </div>
        {data.image_url && (
          <img
            src={data.image_url}
            alt=""
            style={{ width: 120, height: 120, borderRadius: 10, objectFit: 'cover' }}
          />
        )}
      </div>

      <div className="toolbar">
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
      </div>

      <div className="album-list">
        {data.albums.map((album) => {
          const isDownloaded = album.status === 'downloaded'
          const via = (album.provider || 'unknown').toLowerCase()
          const job = jobForAlbum(album.id, album.title)
          const downloading = job && (job.state === 'queued' || job.state === 'running')
          const failed = job && job.state === 'failed'
          return (
            <div key={album.id} className="album-row">
              {album.cover_url ? (
                <img src={album.cover_url} alt="" />
              ) : (
                <div className="placeholder-art" style={{ width: 64, height: 64 }} />
              )}
              <div style={{ minWidth: 0 }}>
                <div>
                  <strong>{album.title}</strong>{' '}
                  {downloading ? (
                    <span className={`badge ${job.state}`}>{job.state}</span>
                  ) : failed ? (
                    <span className="badge failed">failed</span>
                  ) : (
                    <span className={`badge ${album.status}`}>{album.status}</span>
                  )}
                </div>
                <div className="muted">
                  {album.release_date || 'Unknown date'} · {album.album_type} · {album.track_count}{' '}
                  tracks
                </div>
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
                {!downloading && album.status !== 'downloaded' && (
                  <button
                    className="btn secondary"
                    onClick={() => downloadAlbum.mutate(album.id)}
                    disabled={downloadAlbum.isPending}
                  >
                    {failed ? 'Retry' : 'Download'}
                  </button>
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
    </div>
  )
}
