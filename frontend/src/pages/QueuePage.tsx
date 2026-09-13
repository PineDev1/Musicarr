import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { api, type DownloadJob } from '../api'
import { useToast } from '../Toast'

export function QueuePage() {
  const qc = useQueryClient()
  const toast = useToast()
  const { data, isLoading, error } = useQuery({
    queryKey: ['queue'],
    queryFn: () => api.queue(true),
    refetchInterval: 2000,
  })
  const [live, setLive] = useState<DownloadJob[] | null>(null)

  useEffect(() => {
    const es = new EventSource('/api/events/queue')
    es.onmessage = (ev) => {
      try {
        const snap = JSON.parse(ev.data) as Array<{
          id: number
          artist_name: string
          album_title: string
          state: string
          progress: number
          error: string | null
          retries: number
        }>
        setLive(
          snap.map((j) => ({
            id: j.id,
            target_type: 'album',
            target_id: 0,
            album_id: null,
            artist_name: j.artist_name,
            album_title: j.album_title,
            state: j.state,
            progress: j.progress,
            error: j.error,
            retries: j.retries,
            created_at: '',
            started_at: null,
            finished_at: null,
          })),
        )
      } catch {
        /* ignore */
      }
    }
    return () => es.close()
  }, [])

  const cancel = useMutation({
    mutationFn: (id: number) => api.cancelJob(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['queue'] }),
  })
  const retry = useMutation({
    mutationFn: (id: number) => api.retryJob(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['queue'] }),
  })
  const clearFinished = useMutation({
    mutationFn: api.clearFinishedQueue,
    onSuccess: (res) => {
      toast.push(`Cleared ${res.cleared} finished job(s)`, 'ok')
      qc.invalidateQueries({ queryKey: ['queue'] })
    },
    onError: (err) => toast.push((err as Error).message, 'error'),
  })

  const jobs = data || []
  const merged = jobs.map((j) => {
    const liveJob = live?.find((l) => l.id === j.id)
    return liveJob
      ? { ...j, progress: liveJob.progress, state: liveJob.state, error: liveJob.error }
      : j
  })

  return (
    <div>
      <div className="page-header">
        <div>
          <h1>Queue</h1>
          <p>Download progress updates live while jobs run.</p>
        </div>
        <button
          className="btn secondary"
          onClick={() => clearFinished.mutate()}
          disabled={clearFinished.isPending}
        >
          Clear finished
        </button>
      </div>
      {isLoading && <p className="muted">Loading…</p>}
      {error && <p className="error">{(error as Error).message}</p>}
      {merged.length === 0 && (
        <div className="empty-state">
          <h2>Queue is empty</h2>
          <p className="muted">Add an artist or download a wanted album to get started.</p>
        </div>
      )}
      {merged.length > 0 && (
        <table className="table">
          <thead>
            <tr>
              <th>Album</th>
              <th>State</th>
              <th>Progress</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {merged.map((job) => (
              <tr key={job.id}>
                <td>
                  <strong>
                    {job.artist_name} – {job.album_title}
                  </strong>
                  {job.error && <div className="error">{job.error}</div>}
                  {job.retries > 0 && <div className="muted">Retries: {job.retries}</div>}
                </td>
                <td>
                  <span className={`badge ${job.state}`}>{job.state}</span>
                </td>
                <td style={{ minWidth: 140 }}>
                  {job.progress.toFixed(0)}%
                  <div className="progress">
                    <span style={{ width: `${Math.min(100, job.progress)}%` }} />
                  </div>
                </td>
                <td className="row-actions">
                  {(job.state === 'queued' || job.state === 'running') && (
                    <button className="btn ghost" onClick={() => cancel.mutate(job.id)}>
                      Cancel
                    </button>
                  )}
                  {job.state === 'failed' && (
                    <button className="btn secondary" onClick={() => retry.mutate(job.id)}>
                      Retry
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
