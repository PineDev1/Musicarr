import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { IconPlay, IconShuffle } from './icons'
import { DEFAULT_PREFS, playerApi, type PlayerAlbum } from './playerApi'
import { usePlayerQueue } from './PlayerQueueContext'
import { AlbumShelf, ArtistShelf, Section, SongShelf } from './PlayerShelves'

/** Recently added albums are derived from the newest playable tracks. */
function albumsFromTracks(tracks: { album_id: number; album_title: string; artist_id: number; artist_name: string; cover_url: string | null }[]) {
  const seen = new Set<number>()
  const albums: PlayerAlbum[] = []
  for (const t of tracks) {
    if (!t.album_id || seen.has(t.album_id)) continue
    seen.add(t.album_id)
    albums.push({
      id: t.album_id,
      title: t.album_title,
      artist_id: t.artist_id,
      artist_name: t.artist_name,
      cover_url: t.cover_url,
      release_date: null,
      track_count: 0,
      quality: '',
      tracks: [],
    })
  }
  return albums
}

export function PlayerHomePage() {
  const q = usePlayerQueue()
  const prefsQ = useQuery({ queryKey: ['player-prefs'], queryFn: playerApi.prefs })
  const prefs = prefsQ.data || DEFAULT_PREFS

  const cont = useQuery({
    queryKey: ['player-continue'],
    queryFn: playerApi.continueListening,
    retry: false,
  })
  const recommended = useQuery({
    queryKey: ['player-recommended'],
    queryFn: playerApi.recommended,
    enabled: prefs.show_recommended,
  })
  const builtins = useQuery({ queryKey: ['player-builtins'], queryFn: playerApi.builtins })
  const artists = useQuery({ queryKey: ['player-artists'], queryFn: playerApi.artists })

  const recentlyPlayed = builtins.data?.find((p) => p.kind === 'recently-played')
  const recentlyAdded = builtins.data?.find((p) => p.kind === 'recently-added')
  const shuffleMix = builtins.data?.find((p) => p.kind === 'shuffle-mix')
  const continueTrack = cont.data?.track
  const continueAlbum = cont.data?.album

  const empty =
    !continueTrack &&
    !recommended.data?.length &&
    !recentlyPlayed?.tracks.length &&
    !recentlyAdded?.tracks.length &&
    !artists.data?.length

  return (
    <div className="am-page">
      <div className="page-header">
        <div>
          <h1>Listen Now</h1>
          <p>Your library, streamed at original quality — FLAC stays FLAC.</p>
        </div>
        {!!shuffleMix?.tracks.length && (
          <button
            type="button"
            className="btn secondary"
            onClick={() => q.playTracks(shuffleMix.tracks, 0, 'Shuffle Mix')}
          >
            <IconShuffle size={16} /> Shuffle Mix
          </button>
        )}
      </div>

      {builtins.isLoading && <p className="muted">Loading your library…</p>}
      {empty && !builtins.isLoading && (
        <p className="muted">No playable tracks yet. Download albums in Musicarr first.</p>
      )}

      {continueTrack && (
        <Section title="Continue listening" subtitle={cont.data?.source_label || undefined}>
          <div className="am-continue">
            {continueTrack.cover_url ? (
              <img src={continueTrack.cover_url} alt="" />
            ) : (
              <div className="am-continue-ph" />
            )}
            <div className="am-continue-meta">
              <strong>{continueTrack.title}</strong>
              <span className="muted">
                <Link to={`/player/artists/${continueTrack.artist_id}`}>
                  {continueTrack.artist_name}
                </Link>
                {continueTrack.album_title ? ` — ${continueTrack.album_title}` : ''}
              </span>
              <div className="toolbar">
                <button
                  type="button"
                  className="btn"
                  onClick={() => {
                    const queue = continueAlbum?.tracks?.length
                      ? continueAlbum.tracks
                      : [continueTrack]
                    q.playTrack(
                      continueTrack,
                      queue,
                      continueAlbum?.title || cont.data?.source_label || 'Continue listening',
                      cont.data?.position || 0,
                    )
                  }}
                >
                  <IconPlay size={16} /> Resume
                </button>
                {!!continueAlbum && (
                  <Link className="btn ghost" to={`/player/albums/${continueAlbum.id}`}>
                    Go to album
                  </Link>
                )}
              </div>
            </div>
          </div>
        </Section>
      )}

      {prefs.show_recommended && !!recommended.data?.length && (
        <Section title="Recommended for you" subtitle="Based on what you've been playing">
          <SongShelf tracks={recommended.data.slice(0, 12)} sourceLabel="Recommended for you" />
        </Section>
      )}

      {prefs.show_recently_played && !!recentlyPlayed?.tracks.length && (
        <Section
          title="Recently played"
          action={
            <Link className="am-section-link" to="/player/playlists/recently-played">
              See all
            </Link>
          }
        >
          <SongShelf tracks={recentlyPlayed.tracks.slice(0, 12)} sourceLabel="Recently Played" />
        </Section>
      )}

      {prefs.show_recently_added && !!recentlyAdded?.tracks.length && (
        <Section
          title="Recently added"
          action={
            <Link className="am-section-link" to="/player/albums">
              See all
            </Link>
          }
        >
          <AlbumShelf albums={albumsFromTracks(recentlyAdded.tracks).slice(0, 12)} />
        </Section>
      )}

      {!!artists.data?.length && (
        <Section
          title="Artists"
          action={
            <Link className="am-section-link" to="/player/artists">
              See all
            </Link>
          }
        >
          <ArtistShelf artists={artists.data.slice(0, 12)} />
        </Section>
      )}
    </div>
  )
}
