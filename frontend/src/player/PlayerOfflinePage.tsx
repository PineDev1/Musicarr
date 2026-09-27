import { useEffect, useState } from 'react'
import {
  clearAllOfflineTracks,
  isOfflineSupported,
  listOfflineTracks,
  removeOfflineTrack,
  storageEstimate,
  type OfflineTrackMeta,
} from './offlineCache'
import { usePlayerQueue } from './PlayerQueueContext'
import { IconPlay } from './icons'
import type { PlayerTrack } from './playerApi'

function toPlayerTrack(t: OfflineTrackMeta): PlayerTrack {
  return {
    id: t.id,
    title: t.title,
    track_no: 0,
    disc_no: 1,
    duration: t.duration,
    album_id: 0,
    album_title: t.album_title,
    artist_id: 0,
    artist_name: t.artist_name,
    cover_url: t.cover_url,
    quality: '',
    format: '',
  }
}

function formatBytes(n: number): string {
  if (!n) return '0 MB'
  const mb = n / (1024 * 1024)
  if (mb < 1024) return `${mb.toFixed(1)} MB`
  return `${(mb / 1024).toFixed(2)} GB`
}

export function PlayerOfflinePage() {
  const q = usePlayerQueue()
  const [tracks, setTracks] = useState<OfflineTrackMeta[]>(() => listOfflineTracks())
  const [usage, setUsage] = useState<{ usage: number; quota: number } | null>(null)

  useEffect(() => {
    storageEstimate().then(setUsage)
  }, [tracks.length])

  if (!isOfflineSupported()) {
    return (
      <div className="am-page">
        <h1>Offline downloads</h1>
        <p className="muted">Offline downloads aren't supported in this browser.</p>
      </div>
    )
  }

  const totalBytes = tracks.reduce((sum, t) => sum + (t.bytes || 0), 0)

  return (
    <div className="am-page">
      <div className="page-header">
        <div>
          <h1>Offline downloads</h1>
          <p className="muted">
            {tracks.length} song{tracks.length === 1 ? '' : 's'} · {formatBytes(totalBytes)} on this device
            {usage?.quota ? ` of ~${formatBytes(usage.quota)} available` : ''}
          </p>
        </div>
        <div className="toolbar">
          {!!tracks.length && (
            <button
              type="button"
              className="btn"
              onClick={() => q.playTracks(tracks.map(toPlayerTrack), 0, 'Offline downloads')}
            >
              <IconPlay size={16} /> Play all
            </button>
          )}
          {!!tracks.length && (
            <button
              type="button"
              className="btn ghost danger"
              onClick={async () => {
                if (!window.confirm('Remove all offline downloads from this device?')) return
                await clearAllOfflineTracks()
                setTracks([])
              }}
            >
              Remove all
            </button>
          )}
        </div>
      </div>

      {!tracks.length && (
        <p className="muted">
          Nothing downloaded yet — use "Download for offline" from a song's menu to save it for
          playback without a connection.
        </p>
      )}

      <div className="am-song-list bordered">
        {tracks.map((t) => (
          <div key={t.id} className="am-continue" style={{ marginBottom: '0.5rem' }}>
            {t.cover_url ? <img src={t.cover_url} alt="" /> : <div className="am-continue-ph" />}
            <div className="am-continue-meta">
              <strong>{t.title}</strong>
              <span className="muted">
                {t.artist_name}
                {t.album_title ? ` — ${t.album_title}` : ''} · {formatBytes(t.bytes)}
              </span>
            </div>
            <div className="toolbar">
              <button
                type="button"
                className="btn ghost"
                onClick={() => q.playTrack(toPlayerTrack(t), tracks.map(toPlayerTrack), 'Offline downloads')}
              >
                <IconPlay size={16} />
              </button>
              <button
                type="button"
                className="btn ghost danger"
                onClick={async () => {
                  await removeOfflineTrack(t.id)
                  setTracks(listOfflineTracks())
                }}
              >
                Remove
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
