import { useInfiniteQuery } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'
import { IconPlay, IconSearch, IconShuffle } from './icons'
import { playerApi } from './playerApi'
import { usePlayerQueue } from './PlayerQueueContext'
import { SongRow } from './PlayerShelves'

const PAGE_SIZE = 60

export function PlayerSongsPage() {
  const q = usePlayerQueue()
  const [term, setTerm] = useState('')
  const [debounced, setDebounced] = useState('')

  useEffect(() => {
    const id = window.setTimeout(() => setDebounced(term.trim()), 250)
    return () => window.clearTimeout(id)
  }, [term])

  const songs = useInfiniteQuery({
    queryKey: ['player-library-songs', debounced],
    queryFn: ({ pageParam }) =>
      playerApi.librarySongs({ q: debounced, offset: pageParam, limit: PAGE_SIZE }),
    initialPageParam: 0,
    getNextPageParam: (last) => {
      const nextOffset = last.offset + last.items.length
      return nextOffset < last.total ? nextOffset : undefined
    },
  })

  const tracks = useMemo(
    () => songs.data?.pages.flatMap((p) => p.items) || [],
    [songs.data],
  )
  const total = songs.data?.pages[0]?.total ?? 0
  const sourceLabel = debounced ? `Search: ${debounced}` : 'Songs'

  return (
    <div className="am-page">
      <div className="page-header">
        <div>
          <h1>Songs</h1>
          <p>{total ? `${total} songs in your library` : 'Every playable track.'}</p>
        </div>
        <div className="toolbar">
          <button
            type="button"
            className="btn"
            disabled={!tracks.length}
            onClick={() => q.playTracks(tracks, 0, sourceLabel)}
          >
            <IconPlay size={16} /> Play
          </button>
          <button
            type="button"
            className="btn secondary"
            disabled={!tracks.length}
            onClick={() => {
              if (!q.shuffle) q.toggleShuffle()
              q.playTracks(tracks, 0, sourceLabel)
            }}
          >
            <IconShuffle size={16} /> Shuffle
          </button>
        </div>
      </div>

      <div className="am-inline-search">
        <IconSearch size={16} />
        <input
          type="search"
          placeholder="Filter songs…"
          value={term}
          onChange={(e) => setTerm(e.target.value)}
        />
      </div>

      {songs.isLoading && <p className="muted">Loading songs…</p>}
      {songs.isError && <p className="error">{(songs.error as Error).message}</p>}
      {songs.isSuccess && !tracks.length && <p className="muted">No songs matched.</p>}

      <div className="am-song-list bordered">
        {tracks.map((t) => (
          <SongRow key={t.id} track={t} queue={tracks} sourceLabel={sourceLabel} />
        ))}
      </div>

      {songs.hasNextPage && (
        <div className="am-load-more">
          <button
            type="button"
            className="btn secondary"
            onClick={() => songs.fetchNextPage()}
            disabled={songs.isFetchingNextPage}
          >
            {songs.isFetchingNextPage ? 'Loading…' : 'Load more'}
          </button>
        </div>
      )}
    </div>
  )
}
