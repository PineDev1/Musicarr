import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { playerApi } from './playerApi'

function formatMinutes(seconds: number): string {
  const m = Math.round((seconds || 0) / 60)
  if (m < 60) return `${m} min`
  const h = Math.floor(m / 60)
  const rem = m % 60
  return rem ? `${h}h ${rem}m` : `${h}h`
}

const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

function hourLabel(h: number) {
  const suffix = h < 12 ? 'am' : 'pm'
  return `${h % 12 === 0 ? 12 : h % 12}${suffix}`
}

function Bars({ values, labels }: { values: number[]; labels: string[] }) {
  const max = Math.max(1, ...values)
  return (
    <div style={{ display: 'flex', gap: 3, alignItems: 'flex-end', height: 90 }}>
      {values.map((v, i) => (
        <div
          key={i}
          title={`${labels[i]}: ${v} plays`}
          style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2 }}
        >
          <div
            style={{
              width: '100%',
              height: `${Math.max(2, (v / max) * 70)}px`,
              background: 'var(--accent)',
              opacity: v ? 1 : 0.25,
              borderRadius: 2,
            }}
          />
          <span className="muted" style={{ fontSize: 9 }}>
            {labels[i]}
          </span>
        </div>
      ))}
    </div>
  )
}

type Period = { kind: 'days'; days: number } | { kind: 'year'; year: number }

export function PlayerStatsPage() {
  const thisYear = new Date().getFullYear()
  const [period, setPeriod] = useState<Period>({ kind: 'days', days: 30 })
  const stats = useQuery({
    queryKey: ['player-stats', period],
    queryFn: () =>
      period.kind === 'year' ? playerApi.stats(30, period.year) : playerApi.stats(period.days),
  })

  const isActive = (p: Period) => JSON.stringify(p) === JSON.stringify(period)
  const choices: { label: string; p: Period }[] = [
    { label: '7 days', p: { kind: 'days', days: 7 } },
    { label: '30 days', p: { kind: 'days', days: 30 } },
    { label: '90 days', p: { kind: 'days', days: 90 } },
    { label: String(thisYear), p: { kind: 'year', year: thisYear } },
    { label: String(thisYear - 1), p: { kind: 'year', year: thisYear - 1 } },
  ]

  const data = stats.data
  return (
    <div className="player-page">
      <div className="page-header">
        <div>
          <h1>{period.kind === 'year' ? `Your ${period.year} in music` : 'Listening stats'}</h1>
          <p className="muted">
            {period.kind === 'year' ? 'Year in review' : `Last ${period.days} days`}
          </p>
        </div>
        <div className="toolbar" style={{ flexWrap: 'wrap' }}>
          {choices.map((c) => (
            <button
              key={c.label}
              type="button"
              className={`btn ${isActive(c.p) ? '' : 'secondary'}`}
              onClick={() => setPeriod(c.p)}
            >
              {c.label}
            </button>
          ))}
        </div>
      </div>

      {stats.isLoading && <p className="muted">Loading stats…</p>}
      {stats.error && <p className="error">{(stats.error as Error).message}</p>}
      {data && (
        <>
          <div className="toolbar" style={{ gap: '1.5rem', flexWrap: 'wrap' }}>
            <div>
              <div className="muted">Plays</div>
              <strong style={{ fontSize: '1.4rem' }}>{data.play_events}</strong>
            </div>
            <div>
              <div className="muted">Tracks</div>
              <strong style={{ fontSize: '1.4rem' }}>{data.unique_tracks}</strong>
            </div>
            <div>
              <div className="muted">Artists</div>
              <strong style={{ fontSize: '1.4rem' }}>{data.unique_artists}</strong>
            </div>
            <div>
              <div className="muted">Time</div>
              <strong style={{ fontSize: '1.4rem' }}>{formatMinutes(data.total_seconds)}</strong>
            </div>
            <div>
              <div className="muted">Active days</div>
              <strong style={{ fontSize: '1.4rem' }}>{data.active_days}</strong>
            </div>
            <div>
              <div className="muted">Current streak</div>
              <strong style={{ fontSize: '1.4rem' }}>{data.current_streak_days}d</strong>
            </div>
            <div>
              <div className="muted">Longest streak</div>
              <strong style={{ fontSize: '1.4rem' }}>{data.longest_streak_days}d</strong>
            </div>
          </div>

          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
              gap: '1.5rem',
              marginTop: '1.5rem',
            }}
          >
            <section>
              <h2 style={{ fontSize: '1.1rem' }}>When you listen</h2>
              <Bars
                values={data.plays_by_hour}
                labels={data.plays_by_hour.map((_, h) => (h % 3 === 0 ? hourLabel(h) : ''))}
              />
            </section>
            <section>
              <h2 style={{ fontSize: '1.1rem' }}>Busiest days</h2>
              <Bars values={data.plays_by_weekday} labels={WEEKDAYS} />
            </section>
          </div>

          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
              gap: '1.5rem',
              marginTop: '1.5rem',
            }}
          >
            <section>
              <h2 style={{ fontSize: '1.1rem' }}>Top artists</h2>
              {data.top_artists.length === 0 && <p className="muted">No plays yet.</p>}
              <ol style={{ paddingLeft: '1.2rem', margin: 0 }}>
                {data.top_artists.map((a) => (
                  <li key={a.artist_id} style={{ marginBottom: '0.5rem' }}>
                    <Link to={`/player/artists/${a.artist_id}`}>
                      <strong>{a.name}</strong>
                    </Link>
                    <div className="muted" style={{ fontSize: '0.85rem' }}>
                      {a.plays} plays · {formatMinutes(a.seconds)}
                    </div>
                  </li>
                ))}
              </ol>
            </section>
            <section>
              <h2 style={{ fontSize: '1.1rem' }}>Top tracks</h2>
              {data.top_tracks.length === 0 && <p className="muted">No plays yet.</p>}
              <ol style={{ paddingLeft: '1.2rem', margin: 0 }}>
                {data.top_tracks.map((t) => (
                  <li key={t.track_id} style={{ marginBottom: '0.5rem' }}>
                    <strong>{t.title}</strong>
                    <div className="muted" style={{ fontSize: '0.85rem' }}>
                      {t.artist_name} · {t.plays} plays
                    </div>
                  </li>
                ))}
              </ol>
            </section>
            <section>
              <h2 style={{ fontSize: '1.1rem' }}>Top albums</h2>
              {data.top_albums.length === 0 && <p className="muted">No plays yet.</p>}
              <ol style={{ paddingLeft: '1.2rem', margin: 0 }}>
                {data.top_albums.map((a) => (
                  <li key={a.album_id} style={{ marginBottom: '0.5rem' }}>
                    <Link to={`/player/albums/${a.album_id}`}>
                      <strong>{a.title}</strong>
                    </Link>
                    <div className="muted" style={{ fontSize: '0.85rem' }}>
                      {a.artist_name} · {a.plays} plays
                    </div>
                  </li>
                ))}
              </ol>
            </section>
            <section>
              <h2 style={{ fontSize: '1.1rem' }}>Top genres</h2>
              {data.top_genres.length === 0 && <p className="muted">No genre data yet.</p>}
              <ol style={{ paddingLeft: '1.2rem', margin: 0 }}>
                {data.top_genres.map((g) => (
                  <li key={g.genre} style={{ marginBottom: '0.5rem' }}>
                    <strong>{g.genre}</strong>
                    <div className="muted" style={{ fontSize: '0.85rem' }}>
                      {g.plays} plays · {formatMinutes(g.seconds)}
                    </div>
                  </li>
                ))}
              </ol>
            </section>
          </div>
        </>
      )}
    </div>
  )
}
