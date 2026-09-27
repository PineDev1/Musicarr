import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { playerApi } from './playerApi'
import { Section } from './PlayerShelves'

export function PlayerExplorePage() {
  const genres = useQuery({ queryKey: ['player-genres'], queryFn: playerApi.genres })
  const moods = useQuery({ queryKey: ['player-moods'], queryFn: playerApi.moods })

  const empty = !genres.data?.length && !moods.data?.length

  return (
    <div className="am-page">
      <div className="page-header">
        <div>
          <h1>Explore</h1>
          <p>Browse your library by genre and mood instead of just artist or album.</p>
        </div>
      </div>

      {(genres.isLoading || moods.isLoading) && <p className="muted">Loading…</p>}
      {empty && !genres.isLoading && !moods.isLoading && (
        <p className="muted">
          Nothing tagged with a genre yet — genres come from your downloaded files' own tags.
        </p>
      )}

      {!!moods.data?.length && (
        <Section title="Moods" subtitle="A rough starting point, based on genre tags">
          <div className="am-shelf">
            {moods.data.map((m) => (
              <Link key={m.mood} to={`/player/moods/${encodeURIComponent(m.mood)}`} className="am-card">
                <div className="am-cover-lg am-cover-ph" />
                <strong className="truncate">{m.mood}</strong>
                <span className="muted tiny">
                  {m.track_count} song{m.track_count === 1 ? '' : 's'}
                </span>
              </Link>
            ))}
          </div>
        </Section>
      )}

      {!!genres.data?.length && (
        <Section title="Genres">
          <div className="am-shelf">
            {genres.data.map((g) => (
              <Link key={g.genre} to={`/player/genres/${encodeURIComponent(g.genre)}`} className="am-card">
                <div className="am-cover-lg am-cover-ph" />
                <strong className="truncate">{g.genre}</strong>
                <span className="muted tiny">
                  {g.track_count} song{g.track_count === 1 ? '' : 's'}
                </span>
              </Link>
            ))}
          </div>
        </Section>
      )}
    </div>
  )
}
