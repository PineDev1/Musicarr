import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'
import { playerApi } from './playerApi'
import { formatTime, usePlayerQueue } from './PlayerQueueContext'
import { IconHeart, IconPlay, IconPlus } from './icons'

export function PlayerPlaylistDetailPage() {
  const { id } = useParams()
  const isBuiltin = id != null && Number.isNaN(Number(id))
  const playlistId = Number(id)
  const q = usePlayerQueue()
  const qc = useQueryClient()

  const { data, isLoading, error } = useQuery({
    queryKey: ['player-playlist', id],
    queryFn: () => (isBuiltin ? playerApi.builtin(String(id)) : playerApi.playlist(playlistId)),
    enabled: !!id,
  })

  const favIds = useQuery({ queryKey: ['player-favorite-ids'], queryFn: playerApi.favoriteIds })
  const suggestions = useQuery({
    queryKey: ['player-suggestions', playlistId],
    queryFn: () => playerApi.suggestions(playlistId),
    enabled: !isBuiltin && !!data?.is_smart && (data?.track_count || 0) >= 10,
    retry: false,
  })

  const remove = useMutation({
    mutationFn: (trackId: number) => playerApi.removeFromPlaylist(playlistId, trackId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['player-playlist', id] })
      qc.invalidateQueries({ queryKey: ['player-playlists'] })
      qc.invalidateQueries({ queryKey: ['player-suggestions', playlistId] })
    },
  })
  const addSuggested = useMutation({
    mutationFn: (trackIds: number[]) => playerApi.addToPlaylist(playlistId, trackIds),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['player-playlist', id] })
      qc.invalidateQueries({ queryKey: ['player-playlists'] })
      qc.invalidateQueries({ queryKey: ['player-suggestions', playlistId] })
    },
  })
  const toggleSmart = useMutation({
    mutationFn: () => playerApi.updatePlaylist(playlistId, { is_smart: !data?.is_smart }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['player-playlist', id] })
      qc.invalidateQueries({ queryKey: ['player-playlists'] })
    },
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

  const needMore = !!data.is_smart && data.track_count < 10

  return (
    <div>
      <p className="muted">
        <Link to="/player/playlists">Playlists</Link> / {data.name}
      </p>
      <div className="page-header">
        <div>
          <h1>{data.name}</h1>
          <p className="muted">
            {data.track_count} tracks
            {data.is_smart ? ' · Smart' : ''}
            {data.builtin ? ' · Built-in' : ''}
          </p>
        </div>
        <div className="toolbar">
          {!data.builtin && (
            <button type="button" className="btn secondary" onClick={() => toggleSmart.mutate()}>
              {data.is_smart ? 'Disable Smart' : 'Enable Smart'}
            </button>
          )}
          <button
            className="btn"
            type="button"
            disabled={!data.tracks.length}
            onClick={() => q.playTracks(data.tracks, 0)}
          >
            <IconPlay size={16} /> Play all
          </button>
        </div>
      </div>

      {needMore && (
        <div className="banner warn">
          Add at least {10 - data.track_count} more song{10 - data.track_count === 1 ? '' : 's'} to unlock
          smart suggestions.
        </div>
      )}

      {!isBuiltin && data.is_smart && !needMore && (
        <section className="suggest-block">
          <div className="page-header" style={{ marginBottom: '0.5rem' }}>
            <h2 style={{ margin: 0, fontSize: '1.1rem' }}>Suggested for you</h2>
            {!!suggestions.data?.length && (
              <button
                type="button"
                className="btn secondary"
                onClick={() => addSuggested.mutate(suggestions.data!.map((t) => t.id))}
              >
                Add all
              </button>
            )}
          </div>
          {suggestions.isError && (
            <p className="muted">{(suggestions.error as Error).message}</p>
          )}
          <div className="suggest-list">
            {suggestions.data?.map((t) => (
              <div key={t.id} className="suggest-row">
                {t.cover_url ? <img src={t.cover_url} alt="" /> : <div className="q-art" />}
                <div>
                  <strong>{t.title}</strong>
                  <div className="muted">
                    {t.artist_name} · {t.album_title}
                  </div>
                </div>
                <button
                  type="button"
                  className="pill-icon-btn"
                  aria-label="Add"
                  onClick={() => addSuggested.mutate([t.id])}
                >
                  <IconPlus size={18} />
                </button>
              </div>
            ))}
            {suggestions.isSuccess && !suggestions.data?.length && (
              <p className="muted">No more similar tracks found in the library.</p>
            )}
          </div>
        </section>
      )}

      <div className="track-list">
        {data.tracks.map((t, i) => {
          const liked = (favIds.data?.ids || []).includes(t.id)
          return (
            <div key={t.id} className="track-row">
              <span className="track-no">{i + 1}</span>
              {t.cover_url ? <img src={t.cover_url} alt="" className="track-art" /> : <div className="track-art q-art" />}
              <div className="track-info">
                <strong>{t.title}</strong>
                <span className="muted">
                  {t.artist_name}
                  {(t.format === 'flac' || t.quality === 'flac') && (
                    <span className="badge flac" style={{ marginLeft: 6 }}>
                      FLAC
                    </span>
                  )}
                </span>
              </div>
              <span className="muted tiny">{formatTime(t.duration)}</span>
              <div className="row-actions">
                <button type="button" className="pill-icon-btn" aria-label="Play" onClick={() => q.playTrack(t, data.tracks)}>
                  <IconPlay size={16} />
                </button>
                <button
                  type="button"
                  className={`pill-icon-btn heart${liked ? ' on' : ''}`}
                  aria-label="Like"
                  onClick={() => toggleFav.mutate(t.id)}
                >
                  <IconHeart filled={liked} size={16} />
                </button>
                {!data.builtin && (
                  <button type="button" className="pill-icon-btn" onClick={() => remove.mutate(t.id)}>
                    ×
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
