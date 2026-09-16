import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { playerApi, type PlayerSmartCriteria, type PlayerSmartRule } from './playerApi'
import { usePlayerQueue } from './PlayerQueueContext'
import { SongRow } from './PlayerShelves'
import { IconPlay, IconPlus } from './icons'

const RULE_FIELDS: PlayerSmartRule['field'][] = [
  'favorited',
  'genre',
  'format',
  'artist_id',
  'play_count',
  'last_played_days',
]

const EMPTY_CRITERIA: PlayerSmartCriteria = {
  match: 'all',
  rules: [],
  sort: 'random',
  limit: 50,
}

function SmartCriteriaEditor({
  playlistId,
  initial,
  onSaved,
}: {
  playlistId: number
  initial: PlayerSmartCriteria | null | undefined
  onSaved: () => void
}) {
  const [criteria, setCriteria] = useState<PlayerSmartCriteria>(initial || EMPTY_CRITERIA)
  const save = useMutation({
    mutationFn: () => playerApi.updatePlaylistCriteria(playlistId, criteria),
    onSuccess: onSaved,
  })
  const clear = useMutation({
    mutationFn: () => playerApi.clearPlaylistCriteria(playlistId),
    onSuccess: onSaved,
  })

  const updateRule = (i: number, patch: Partial<PlayerSmartRule>) => {
    setCriteria((c) => ({
      ...c,
      rules: c.rules.map((r, idx) => (idx === i ? { ...r, ...patch } : r)),
    }))
  }

  return (
    <div className="smart-criteria-editor">
      <div className="toolbar">
        <label>
          Match
          <select
            value={criteria.match}
            onChange={(e) => setCriteria((c) => ({ ...c, match: e.target.value as 'all' | 'any' }))}
          >
            <option value="all">All rules</option>
            <option value="any">Any rule</option>
          </select>
        </label>
        <label>
          Sort
          <select
            value={criteria.sort}
            onChange={(e) => setCriteria((c) => ({ ...c, sort: e.target.value as PlayerSmartCriteria['sort'] }))}
          >
            <option value="random">Random</option>
            <option value="recently_added">Recently added</option>
            <option value="most_played">Most played</option>
            <option value="title">Title</option>
            <option value="artist">Artist</option>
          </select>
        </label>
        <label>
          Limit
          <input
            type="number"
            min={1}
            max={500}
            value={criteria.limit}
            onChange={(e) => setCriteria((c) => ({ ...c, limit: Number(e.target.value) || 50 }))}
          />
        </label>
      </div>

      {criteria.rules.map((rule, i) => (
        <div className="toolbar" key={i}>
          <select value={rule.field} onChange={(e) => updateRule(i, { field: e.target.value as PlayerSmartRule['field'] })}>
            {RULE_FIELDS.map((f) => (
              <option key={f} value={f}>
                {f}
              </option>
            ))}
          </select>
          <select value={rule.op} onChange={(e) => updateRule(i, { op: e.target.value as PlayerSmartRule['op'] })}>
            <option value="eq">is</option>
            <option value="ne">is not</option>
            <option value="gte">≥</option>
            <option value="lte">≤</option>
            <option value="gt">&gt;</option>
            <option value="lt">&lt;</option>
          </select>
          {rule.field === 'favorited' ? (
            <select
              value={String(rule.value)}
              onChange={(e) => updateRule(i, { value: e.target.value === 'true' })}
            >
              <option value="true">Yes</option>
              <option value="false">No</option>
            </select>
          ) : (
            <input
              value={rule.value == null ? '' : String(rule.value)}
              onChange={(e) => {
                const raw = e.target.value
                const num = Number(raw)
                updateRule(i, { value: raw !== '' && !Number.isNaN(num) ? num : raw })
              }}
              placeholder="value"
            />
          )}
          <button
            type="button"
            className="pill-icon-btn danger"
            onClick={() =>
              setCriteria((c) => ({ ...c, rules: c.rules.filter((_, idx) => idx !== i) }))
            }
          >
            ×
          </button>
        </div>
      ))}

      <button
        type="button"
        className="btn secondary"
        onClick={() =>
          setCriteria((c) => ({
            ...c,
            rules: [...c.rules, { field: 'favorited', op: 'eq', value: true }],
          }))
        }
      >
        Add rule
      </button>

      <div className="toolbar" style={{ marginTop: '0.5rem' }}>
        <button type="button" className="btn" onClick={() => save.mutate()} disabled={save.isPending}>
          Save rules
        </button>
        {initial && (
          <button type="button" className="btn secondary" onClick={() => clear.mutate()} disabled={clear.isPending}>
            Remove smart rules
          </button>
        )}
      </div>
    </div>
  )
}

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

  const suggestions = useQuery({
    queryKey: ['player-suggestions', playlistId],
    queryFn: () => playerApi.suggestions(playlistId),
    enabled: !isBuiltin && !!data?.is_smart && !data?.criteria && (data?.track_count || 0) >= 10,
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
  const [editingRules, setEditingRules] = useState(false)
  if (isLoading) return <p className="muted">Loading…</p>
  if (error) return <p className="error">{(error as Error).message}</p>
  if (!data) return null

  const hasCriteria = !!data.criteria
  const needMore = !!data.is_smart && !hasCriteria && data.track_count < 10

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
          {!data.builtin && !hasCriteria && (
            <button type="button" className="btn secondary" onClick={() => toggleSmart.mutate()}>
              {data.is_smart ? 'Disable Smart' : 'Enable Smart'}
            </button>
          )}
          {!data.builtin && (
            <button type="button" className="btn secondary" onClick={() => setEditingRules((v) => !v)}>
              {hasCriteria ? 'Edit smart rules' : 'Make smart (rules)'}
            </button>
          )}
          {!data.builtin && (
            <a className="btn secondary" href={playerApi.exportPlaylistUrl(playlistId)}>
              Export M3U
            </a>
          )}
          <button
            className="btn"
            type="button"
            disabled={!data.tracks.length}
            onClick={() => q.playTracks(data.tracks, 0, data.name)}
          >
            <IconPlay size={16} /> Play all
          </button>
        </div>
      </div>

      {editingRules && (
        <SmartCriteriaEditor
          playlistId={playlistId}
          initial={data.criteria}
          onSaved={() => {
            setEditingRules(false)
            qc.invalidateQueries({ queryKey: ['player-playlist', id] })
            qc.invalidateQueries({ queryKey: ['player-playlists'] })
          }}
        />
      )}

      {needMore && (
        <div className="banner warn">
          Add at least {10 - data.track_count} more song{10 - data.track_count === 1 ? '' : 's'} to unlock
          smart suggestions.
        </div>
      )}

      {!isBuiltin && data.is_smart && !hasCriteria && !needMore && (
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

      <div className="am-song-list bordered">
        {data.tracks.map((t, i) => (
          <SongRow
            key={t.id}
            track={t}
            queue={data.tracks}
            sourceLabel={data.name}
            number={i + 1}
            onRemove={data.builtin || hasCriteria ? undefined : () => remove.mutate(t.id)}
            removeLabel="Remove from playlist"
          />
        ))}
      </div>
    </div>
  )
}
