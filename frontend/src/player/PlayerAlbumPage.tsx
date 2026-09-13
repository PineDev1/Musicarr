import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'
import { useState } from 'react'
import { playerApi } from './playerApi'
import { formatTime, usePlayerQueue } from './PlayerQueueContext'
import { IconHeart, IconPlay, IconPlus, IconQueue } from './icons'

export function PlayerAlbumPage() {
  const { id } = useParams()
  const albumId = Number(id)
  const q = usePlayerQueue()
  const qc = useQueryClient()
  const [playlistId, setPlaylistId] = useState<number | ''>('')
  const { data, isLoading, error } = useQuery({
    queryKey: ['player-album', albumId],
    queryFn: () => playerApi.album(albumId),
    enabled: Number.isFinite(albumId),
  })
  const playlists = useQuery({ queryKey: ['player-playlists'], queryFn: playerApi.playlists })
  const favIds = useQuery({ queryKey: ['player-favorite-ids'], queryFn: playerApi.favoriteIds })

  const addPl = useMutation({
    mutationFn: (trackId: number) => {
      if (!playlistId) throw new Error('Pick a playlist')
      return playerApi.addToPlaylist(Number(playlistId), [trackId])
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['player-playlists'] }),
  })
  const toggleFav = useMutation({
    mutationFn: async (trackId: number) => {
      const liked = (favIds.data?.ids || []).includes(trackId)
      if (liked) await playerApi.removeFavorite(trackId)
      else await playerApi.addFavorite(trackId)
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['player-favorite-ids'] })
      qc.invalidateQueries({ queryKey: ['player-builtins'] })
    },
  })

  if (isLoading) return <p className="muted">Loading…</p>
  if (error) return <p className="error">{(error as Error).message}</p>
  if (!data) return null

  return (
    <div>
      <p className="muted">
        <Link to="/player">Library</Link>
        {data.artist_id ? (
          <>
            {' / '}
            <Link to={`/player/artists/${data.artist_id}`}>{data.artist_name}</Link>
          </>
        ) : null}
      </p>
      <div className="album-hero">
        {data.cover_url ? <img src={data.cover_url} alt="" /> : <div className="album-hero-ph" />}
        <div>
          <h1>{data.title}</h1>
          <p className="muted">
            {data.artist_name}
            {data.quality ? ` · ${data.quality.toUpperCase()}` : ''}
          </p>
          <div className="toolbar">
            <button className="btn" type="button" onClick={() => q.playTracks(data.tracks, 0)}>
              <IconPlay size={16} /> Play
            </button>
            <select value={playlistId} onChange={(e) => setPlaylistId(e.target.value ? Number(e.target.value) : '')}>
              <option value="">Add to playlist…</option>
              {playlists.data?.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>
      <div className="track-list">
        {data.tracks.map((t, i) => {
          const liked = (favIds.data?.ids || []).includes(t.id)
          return (
            <div key={t.id} className="track-row">
              <span className="track-no">{t.track_no || i + 1}</span>
              <div className="track-info">
                <strong>{t.title}</strong>
                {(t.format === 'flac' || t.quality === 'flac') && (
                  <span className="badge flac" style={{ marginLeft: 6 }}>
                    FLAC
                  </span>
                )}
              </div>
              <span className="muted tiny">{formatTime(t.duration)}</span>
              <div className="row-actions">
                <button type="button" className="pill-icon-btn" onClick={() => q.playTrack(t, data.tracks)}>
                  <IconPlay size={16} />
                </button>
                <button type="button" className="pill-icon-btn" onClick={() => q.addNext(t)}>
                  <IconQueue size={16} />
                </button>
                <button
                  type="button"
                  className={`pill-icon-btn heart${liked ? ' on' : ''}`}
                  onClick={() => toggleFav.mutate(t.id)}
                >
                  <IconHeart filled={liked} size={16} />
                </button>
                {playlistId !== '' && (
                  <button type="button" className="pill-icon-btn" onClick={() => addPl.mutate(t.id)}>
                    <IconPlus size={16} />
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
