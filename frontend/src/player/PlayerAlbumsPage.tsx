import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { playerApi } from './playerApi'
import { AlbumCard } from './PlayerShelves'

type Sort = 'recent' | 'name' | 'year'

const SORTS: { value: Sort; label: string }[] = [
  { value: 'recent', label: 'Recently added' },
  { value: 'name', label: 'Title' },
  { value: 'year', label: 'Release year' },
]

export function PlayerAlbumsPage() {
  const [sort, setSort] = useState<Sort>('recent')
  const { data, isLoading, error } = useQuery({
    queryKey: ['player-library-albums', sort],
    queryFn: () => playerApi.libraryAlbums(sort),
  })

  return (
    <div className="am-page">
      <div className="page-header">
        <div>
          <h1>Albums</h1>
          <p>{data ? `${data.length} albums in your library` : 'Everything downloaded.'}</p>
        </div>
        <label className="am-sort">
          Sort
          <select value={sort} onChange={(e) => setSort(e.target.value as Sort)}>
            {SORTS.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </select>
        </label>
      </div>

      {isLoading && <p className="muted">Loading albums…</p>}
      {error && <p className="error">{(error as Error).message}</p>}
      {data && !data.length && <p className="muted">No albums downloaded yet.</p>}

      <div className="am-grid">
        {data?.map((a) => (
          <AlbumCard key={a.id} album={a} />
        ))}
      </div>
    </div>
  )
}
