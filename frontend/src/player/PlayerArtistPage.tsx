import { useQuery } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'
import { IconPlay, IconShuffle, IconUser } from './icons'
import { playerApi, type PlayerArtistDetail } from './playerApi'
import { usePlayerQueue } from './PlayerQueueContext'
import { AlbumShelf, Section, SongRow } from './PlayerShelves'

async function loadArtistDetail(artistId: number): Promise<PlayerArtistDetail> {
  try {
    return await playerApi.artistDetail(artistId)
  } catch (err) {
    // Older backends may lack GET /artists/{id}; compose from albums list.
    const msg = (err as Error).message || ''
    if (!/not found/i.test(msg) && !/404/i.test(msg)) throw err
    const [albums, artists] = await Promise.all([
      playerApi.artistAlbums(artistId),
      playerApi.artists(),
    ])
    const artist = artists.find((a) => a.id === artistId)
    if (!artist && !albums.length) throw err
    const sorted = [...albums].sort((a, b) =>
      (b.release_date || '').localeCompare(a.release_date || ''),
    )
    return {
      id: artistId,
      name: artist?.name || albums[0]?.artist_name || 'Artist',
      image_url: artist?.image_url ?? null,
      album_count: albums.length,
      featured_album: sorted[0] || null,
      top_songs: [],
      essential_albums: sorted.slice(0, 6),
      albums: sorted,
    }
  }
}

export function PlayerArtistPage() {
  const { id } = useParams()
  const artistId = Number(id)
  const q = usePlayerQueue()
  const { data, isLoading, error } = useQuery({
    queryKey: ['player-artist', artistId],
    queryFn: () => loadArtistDetail(artistId),
    enabled: Number.isFinite(artistId) && artistId > 0,
    retry: false,
  })

  if (isLoading) return <p className="muted">Loading…</p>
  if (error) return <p className="error">{(error as Error).message}</p>
  if (!data) return null

  const featured = data.featured_album

  return (
    <div className="am-page">
      <header className="am-artist-hero">
        <div className="am-artist-avatar">
          {data.image_url ? <img src={data.image_url} alt="" /> : <IconUser size={44} />}
        </div>
        <div>
          <h1>{data.name}</h1>
          <p className="muted">
            {data.album_count} album{data.album_count === 1 ? '' : 's'} in your library
          </p>
          <div className="toolbar">
            <button
              type="button"
              className="btn"
              disabled={!data.top_songs.length && !featured}
              onClick={() => {
                if (data.top_songs.length) q.playTracks(data.top_songs, 0, data.name)
                else if (featured) void playerApi.album(featured.id).then((a) => q.playTracks(a.tracks, 0, data.name))
              }}
            >
              <IconPlay size={16} /> Play
            </button>
            <button
              type="button"
              className="btn secondary"
              disabled={!data.top_songs.length && !featured}
              onClick={() => {
                if (!q.shuffle) q.toggleShuffle()
                if (data.top_songs.length) q.playTracks(data.top_songs, 0, data.name)
                else if (featured) void playerApi.album(featured.id).then((a) => q.playTracks(a.tracks, 0, data.name))
              }}
            >
              <IconShuffle size={16} /> Shuffle
            </button>
          </div>
        </div>
      </header>

      {(featured || !!data.top_songs.length) && (
        <div className="am-featured-grid">
          {featured && (
            <Section title="Featured album">
              <Link to={`/player/albums/${featured.id}`} className="am-featured-album">
                <div className="am-cover-lg">
                  {featured.cover_url ? (
                    <img src={featured.cover_url} alt="" />
                  ) : (
                    <span className="am-cover-ph" />
                  )}
                </div>
                <strong>{featured.title}</strong>
                <span className="muted tiny">
                  {(featured.release_date || '').slice(0, 4) || 'Unknown year'} ·{' '}
                  {featured.track_count} tracks
                  {featured.quality ? ` · ${featured.quality.toUpperCase()}` : ''}
                </span>
              </Link>
            </Section>
          )}

          {!!data.top_songs.length && (
            <Section title="Top songs">
              <div className="am-song-list">
                {data.top_songs.map((t, i) => (
                  <SongRow
                    key={t.id}
                    track={t}
                    queue={data.top_songs}
                    sourceLabel={data.name}
                    number={i + 1}
                    showArt={false}
                  />
                ))}
              </div>
            </Section>
          )}
        </div>
      )}

      {!!data.essential_albums.length && (
        <Section title="Essential albums">
          <AlbumShelf albums={data.essential_albums} />
        </Section>
      )}

      {!!data.albums.length && (
        <Section title="Albums" subtitle={`${data.albums.length} in your library`}>
          <AlbumShelf albums={data.albums} />
        </Section>
      )}

      {!data.albums.length && (
        <p className="muted">Nothing downloaded for this artist yet.</p>
      )}
    </div>
  )
}
