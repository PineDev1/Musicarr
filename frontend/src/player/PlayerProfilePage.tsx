import { useQuery } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'
import { playerApi } from './playerApi'
import { FollowButton, PersonAvatar } from './PlayerPeoplePage'
import { SongRow } from './PlayerShelves'

export function PlayerProfilePage() {
  const { id } = useParams()
  const uid = Number(id)
  const q = useQuery({
    queryKey: ['player-profile', uid],
    queryFn: () => playerApi.profile(uid),
    enabled: Number.isFinite(uid),
  })
  if (q.isLoading) return <p className="muted">Loading…</p>
  if (q.error) return <p className="error">{(q.error as Error).message}</p>
  const p = q.data
  if (!p) return null
  return (
    <div className="player-page">
      <p className="muted">
        <Link to="/player/people">People</Link> / {p.display_name || p.username}
      </p>
      <div className="page-header">
        <div style={{ display: 'flex', gap: 16, alignItems: 'center' }}>
          <PersonAvatar p={p} size={84} />
          <div>
            <h1 style={{ margin: 0 }}>{p.display_name || p.username}</h1>
            <p className="muted" style={{ margin: 0 }}>
              @{p.username}
              {p.follows_you ? ' · follows you' : ''}
            </p>
          </div>
        </div>
        {!p.is_self && <FollowButton person={p} />}
      </div>
      <div className="toolbar" style={{ gap: '1.5rem', flexWrap: 'wrap' }}>
        <div>
          <div className="muted">Followers</div>
          <strong style={{ fontSize: '1.4rem' }}>{p.followers}</strong>
        </div>
        <div>
          <div className="muted">Following</div>
          <strong style={{ fontSize: '1.4rem' }}>{p.following}</strong>
        </div>
        {p.activity_shared && (
          <>
            <div>
              <div className="muted">Favorites</div>
              <strong style={{ fontSize: '1.4rem' }}>{p.favorites}</strong>
            </div>
            <div>
              <div className="muted">Plays (30d)</div>
              <strong style={{ fontSize: '1.4rem' }}>{p.plays_30d}</strong>
            </div>
          </>
        )}
      </div>
      {!p.activity_shared && (
        <p className="muted">This person isn't sharing their listening activity.</p>
      )}
      {p.recent.length > 0 && (
        <>
          <h2>Recently played</h2>
          <div className="am-song-list bordered">
            {p.recent.map((t, i) => (
              <SongRow key={`${t.id}-${i}`} track={t} queue={p.recent} sourceLabel="Recently played" number={i + 1} />
            ))}
          </div>
        </>
      )}
    </div>
  )
}
