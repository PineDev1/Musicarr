import { useQuery } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { IconPlay, IconSearch } from './icons'
import { playerApi } from './playerApi'
import { usePlayerQueue } from './PlayerQueueContext'
import { AlbumShelf, ArtistShelf, Section, SongRow } from './PlayerShelves'

export function PlayerSearchPage() {
  const [params, setParams] = useSearchParams()
  const initial = params.get('q') || ''
  const [term, setTerm] = useState(initial)
  const [debounced, setDebounced] = useState(initial.trim())
  const queue = usePlayerQueue()

  useEffect(() => {
    const id = window.setTimeout(() => {
      const next = term.trim()
      setDebounced(next)
      setParams(next ? { q: next } : {}, { replace: true })
    }, 250)
    return () => window.clearTimeout(id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [term])

  const { data, isFetching, error } = useQuery({
    queryKey: ['player-search-grouped', debounced],
    queryFn: () => playerApi.searchGrouped(debounced),
    enabled: debounced.length >= 1,
  })

  const top = data?.top
  const songs = data?.songs || []
  const nothing =
    !!debounced &&
    !isFetching &&
    !!data &&
    !songs.length &&
    !data.albums.length &&
    !data.artists.length

  return (
    <div className="am-page">
      <div className="page-header">
        <div>
          <h1>Search</h1>
          <p>Songs, albums, and artists in your downloaded library.</p>
        </div>
      </div>

      <div className="am-inline-search big">
        <IconSearch size={18} />
        <input
          type="search"
          placeholder="Artists, albums, or songs…"
          value={term}
          onChange={(e) => setTerm(e.target.value)}
          autoFocus
        />
      </div>

      {isFetching && <p className="muted">Searching…</p>}
      {error && <p className="error">{(error as Error).message}</p>}
      {nothing && <p className="muted">No results for “{debounced}”.</p>}

      {top && (
        <Section title="Top result">
          <button
            type="button"
            className="am-top-result"
            onClick={() => queue.playTrack(top, songs, `Search: ${debounced}`)}
          >
            {top.cover_url ? <img src={top.cover_url} alt="" /> : <div className="am-cover-ph" />}
            <span className="am-top-meta">
              <strong>{top.title}</strong>
              <span className="muted tiny">
                Song · {top.artist_name} — {top.album_title}
              </span>
            </span>
            <span className="pill-icon-btn" aria-hidden>
              <IconPlay size={18} />
            </span>
          </button>
        </Section>
      )}

      {!!data?.artists.length && (
        <Section title="Artists">
          <ArtistShelf artists={data.artists} />
        </Section>
      )}

      {!!data?.albums.length && (
        <Section title="Albums">
          <AlbumShelf albums={data.albums} />
        </Section>
      )}

      {!!songs.length && (
        <Section title="Songs">
          <div className="am-song-list bordered">
            {songs.map((t) => (
              <SongRow
                key={t.id}
                track={t}
                queue={songs}
                sourceLabel={`Search: ${debounced}`}
              />
            ))}
          </div>
        </Section>
      )}
    </div>
  )
}
