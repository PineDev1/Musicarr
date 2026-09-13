import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { playerApi } from './playerApi'
import { formatTime, usePlayerQueue } from './PlayerQueueContext'
import { IconPlay, IconQueue } from './icons'

export function PlayerSearchPage() {
  const [q, setQ] = useState('')
  const queue = usePlayerQueue()
  const { data, isFetching } = useQuery({
    queryKey: ['player-search', q],
    queryFn: () => playerApi.search(q),
    enabled: q.trim().length >= 1,
  })

  return (
    <div>
      <div className="page-header">
        <div>
          <h1>Search</h1>
          <p>Find tracks in your downloaded library.</p>
        </div>
      </div>
      <input
        type="search"
        placeholder="Artist, album, or track…"
        value={q}
        onChange={(e) => setQ(e.target.value)}
        className="player-search-input"
      />
      {isFetching && <p className="muted">Searching…</p>}
      <div className="track-list">
        {data?.map((t) => (
          <div key={t.id} className="track-row">
            {t.cover_url ? <img src={t.cover_url} alt="" className="track-art" /> : <div className="track-art q-art" />}
            <div className="track-info">
              <strong>{t.title}</strong>
              <span className="muted">
                {t.artist_name} · {t.album_title}
                {(t.format === 'flac' || t.quality === 'flac') && (
                  <span className="badge flac" style={{ marginLeft: 6 }}>
                    FLAC
                  </span>
                )}
              </span>
            </div>
            <span className="muted tiny">{formatTime(t.duration)}</span>
            <div className="row-actions">
              <button type="button" className="pill-icon-btn" onClick={() => queue.playTrack(t)}>
                <IconPlay size={16} />
              </button>
              <button type="button" className="pill-icon-btn" onClick={() => queue.addEnd(t)}>
                <IconQueue size={16} />
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
