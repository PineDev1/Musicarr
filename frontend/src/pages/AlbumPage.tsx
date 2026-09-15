import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api } from '../api'
import { useToast } from '../Toast'

function formatDuration(sec: number) {
  if (!sec) return '—'
  const m = Math.floor(sec / 60)
  const s = sec % 60
  return `${m}:${String(s).padStart(2, '0')}`
}

export function AlbumPage() {
  const { id } = useParams()
  const albumId = Number(id)
  const qc = useQueryClient()
  const toast = useToast()
  const navigate = useNavigate()

  const { data, isLoading, error } = useQuery({
    queryKey: ['album', albumId],
    queryFn: () => api.album(albumId),
    enabled: Number.isFinite(albumId),
  })

  const download = useMutation({
    mutationFn: (upgrade: boolean) => api.downloadAlbum(albumId, upgrade),
    onSuccess: (res) => {
      if (!res.queued) {
        toast.push('Could not queue download', 'error')
        return
      }
      toast.push('Queued download', 'ok')
      qc.invalidateQueries({ queryKey: ['queue'] })
      qc.invalidateQueries({ queryKey: ['album', albumId] })
      qc.invalidateQueries({ queryKey: ['upgradable'] })
    },
    onError: (err) => toast.push((err as Error).message, 'error'),
  })

  const remove = useMutation({
    mutationFn: (deleteFiles: boolean) => api.deleteAlbum(albumId, deleteFiles),
    onSuccess: (_res, deleteFiles) => {
      toast.push(deleteFiles ? 'Album and files removed' : 'Album removed from library', 'ok')
      qc.invalidateQueries({ queryKey: ['artists'] })
      qc.invalidateQueries({ queryKey: ['wanted'] })
      if (data?.artist_id) navigate(`/artists/${data.artist_id}`)
      else navigate('/')
    },
    onError: (err) => toast.push((err as Error).message, 'error'),
  })

  if (isLoading) return <p className="muted">Loading…</p>
  if (error) return <p className="error">{(error as Error).message}</p>
  if (!data) return <p className="muted">Album not found.</p>

  const downloadedTracks = data.tracks.filter((t) => t.downloaded).length
  const isDownloaded = data.status === 'downloaded'

  return (
    <div>
      <div className="page-header">
        <div>
          <p className="muted" style={{ marginBottom: '0.5rem' }}>
            <Link to="/">Library</Link>
            {' / '}
            <Link to={`/artists/${data.artist_id}`}>{data.artist_name || 'Artist'}</Link>
            {' / '}
            {data.title}
          </p>
          <h1>{data.title}</h1>
          <p>
            <span className={`badge ${data.status}`}>{data.status}</span>{' '}
            <span className="badge queued">{data.album_type}</span>
            {data.quality ? (
              <>
                {' '}
                <span className="badge queued">{data.quality.toUpperCase()}</span>
              </>
            ) : null}
            {data.upgrade_available ? (
              <>
                {' '}
                <span className="badge upgrade">upgrade available</span>
              </>
            ) : null}
          </p>
          <p className="muted" style={{ marginTop: '0.35rem' }}>
            {data.release_date || 'Unknown date'} · {data.track_count || data.tracks.length} tracks
            {isDownloaded ? (
              <>
                {' '}
                · Via <span style={{ textTransform: 'capitalize' }}>{data.provider}</span>
              </>
            ) : (
              ' · Not downloaded'
            )}
          </p>
          {data.path && (
            <p className="muted" style={{ marginTop: '0.25rem', fontSize: '0.85rem', wordBreak: 'break-all' }}>
              {data.path}
            </p>
          )}
        </div>
        {data.cover_url && (
          <img
            src={data.cover_url}
            alt=""
            style={{ width: 140, height: 140, borderRadius: 10, objectFit: 'cover' }}
          />
        )}
      </div>

      <div className="toolbar">
        {!isDownloaded && (
          <button className="btn" onClick={() => download.mutate(false)} disabled={download.isPending}>
            Download
          </button>
        )}
        {isDownloaded && data.upgrade_available && (
          <button className="btn" onClick={() => download.mutate(true)} disabled={download.isPending}>
            Upgrade quality
          </button>
        )}
        {isDownloaded && (
          <button
            className="btn secondary"
            onClick={() => download.mutate(true)}
            disabled={download.isPending}
          >
            Re-download
          </button>
        )}
        <button
          className="btn ghost"
          onClick={() => {
            if (window.confirm(`Remove “${data.title}” from Musicarr (keep files on disk)?`)) {
              remove.mutate(false)
            }
          }}
          disabled={remove.isPending}
        >
          Remove from library
        </button>
        <button
          className="btn danger"
          onClick={() => {
            if (
              window.confirm(
                `Delete “${data.title}” and remove files from disk? This cannot be undone.`,
              )
            ) {
              remove.mutate(true)
            }
          }}
          disabled={remove.isPending}
        >
          Delete files
        </button>
      </div>

      <p className="muted" style={{ marginBottom: '0.75rem' }}>
        Tracks on disk: {downloadedTracks}/{data.tracks.length || data.track_count}
      </p>

      <table className="table">
        <thead>
          <tr>
            <th>#</th>
            <th>Title</th>
            <th>Duration</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {data.tracks.map((t) => (
            <tr key={t.id}>
              <td>
                {t.disc_no > 1 ? `${t.disc_no}-` : ''}
                {t.track_no || '—'}
              </td>
              <td>
                <strong>{t.title}</strong>
                {t.path && (
                  <div className="muted" style={{ fontSize: '0.8rem', wordBreak: 'break-all' }}>
                    {t.path}
                  </div>
                )}
              </td>
              <td>{formatDuration(t.duration)}</td>
              <td>
                {t.downloaded ? (
                  <span className="badge downloaded">on disk</span>
                ) : (
                  <span className="muted">missing</span>
                )}
              </td>
            </tr>
          ))}
          {data.tracks.length === 0 && (
            <tr>
              <td colSpan={4} className="muted">
                No track metadata yet. Download or refresh the artist to sync tracks.
              </td>
            </tr>
          )}
        </tbody>
      </table>

    </div>
  )
}
