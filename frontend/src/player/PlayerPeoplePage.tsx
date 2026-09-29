import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { playerApi, type PlayerPerson } from './playerApi'

export function PersonAvatar({ p, size = 44 }: { p: { avatar_url: string | null; username: string }; size?: number }) {
  return p.avatar_url ? (
    <img
      src={p.avatar_url}
      alt=""
      style={{ width: size, height: size, borderRadius: '50%', objectFit: 'cover' }}
    />
  ) : (
    <div
      style={{
        width: size,
        height: size,
        borderRadius: '50%',
        background: 'var(--bg-soft)',
        display: 'grid',
        placeItems: 'center',
        fontWeight: 700,
      }}
    >
      {p.username.slice(0, 1).toUpperCase()}
    </div>
  )
}

export function FollowButton({ person }: { person: Pick<PlayerPerson, 'id' | 'is_following'> }) {
  const qc = useQueryClient()
  const m = useMutation({
    mutationFn: () => (person.is_following ? playerApi.unfollow(person.id) : playerApi.follow(person.id)),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['player-people'] })
      qc.invalidateQueries({ queryKey: ['player-profile', person.id] })
    },
  })
  return (
    <button
      type="button"
      className={person.is_following ? 'btn secondary' : 'btn'}
      disabled={m.isPending}
      onClick={() => m.mutate()}
    >
      {person.is_following ? 'Following' : 'Follow'}
    </button>
  )
}

export function PlayerPeoplePage() {
  const q = useQuery({ queryKey: ['player-people'], queryFn: playerApi.people })
  if (q.isLoading) return <p className="muted">Loading…</p>
  if (q.error) return <p className="error">{(q.error as Error).message}</p>
  const people = q.data || []
  return (
    <div className="player-page">
      <div className="page-header">
        <div>
          <h1>People</h1>
          <p className="muted">Other accounts on this server. Follow them and share playlists.</p>
        </div>
      </div>
      {!people.length && <p className="muted">No other accounts yet.</p>}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        {people.map((p) => (
          <div key={p.id} className="toolbar" style={{ justifyContent: 'space-between' }}>
            <Link to={`/player/people/${p.id}`} style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
              <PersonAvatar p={p} />
              <div>
                <strong>{p.display_name || p.username}</strong>
                <div className="muted tiny">
                  @{p.username}
                  {p.follows_you ? ' · follows you' : ''}
                </div>
              </div>
            </Link>
            <FollowButton person={p} />
          </div>
        ))}
      </div>
    </div>
  )
}
