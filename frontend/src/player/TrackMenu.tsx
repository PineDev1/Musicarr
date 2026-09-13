import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState, type MouseEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { useToast } from '../Toast'
import { IconMore } from './icons'
import { playerApi, type PlayerTrack } from './playerApi'
import { usePlayerQueue } from './PlayerQueueContext'

type Props = {
  track: PlayerTrack
  /** Queue used when the menu plays the track in context. */
  queue?: PlayerTrack[]
  /** Hide the album/artist jump items (e.g. already on that page). */
  hideNavigation?: boolean
  onRemove?: () => void
  removeLabel?: string
}

export async function copyToClipboard(text: string) {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    return false
  }
}

export function TrackMenu({ track, queue, hideNavigation, onRemove, removeLabel }: Props) {
  const [open, setOpen] = useState(false)
  const [playlistsOpen, setPlaylistsOpen] = useState(false)
  const wrapRef = useRef<HTMLDivElement | null>(null)
  const q = usePlayerQueue()
  const qc = useQueryClient()
  const toast = useToast()
  const navigate = useNavigate()

  const playlists = useQuery({
    queryKey: ['player-playlists'],
    queryFn: playerApi.playlists,
    enabled: playlistsOpen,
  })
  const favIds = useQuery({
    queryKey: ['player-favorite-ids'],
    queryFn: playerApi.favoriteIds,
    staleTime: 15_000,
  })
  const liked = (favIds.data?.ids || []).includes(track.id)

  const toggleFav = useMutation({
    mutationFn: async () => {
      if (liked) await playerApi.removeFavorite(track.id)
      else await playerApi.addFavorite(track.id)
      return !liked
    },
    onSuccess: (nowLiked) => {
      toast.push(nowLiked ? 'Added to Liked Songs' : 'Removed from Liked Songs', 'ok')
      qc.invalidateQueries({ queryKey: ['player-favorite-ids'] })
      qc.invalidateQueries({ queryKey: ['player-builtins'] })
    },
    onError: (err) => toast.push((err as Error).message, 'error'),
  })

  const addPl = useMutation({
    mutationFn: (playlistId: number) => playerApi.addToPlaylist(playlistId, [track.id]),
    onSuccess: (pl) => {
      toast.push(`Added to ${pl.name}`, 'ok')
      qc.invalidateQueries({ queryKey: ['player-playlists'] })
    },
    onError: (err) => toast.push((err as Error).message, 'error'),
  })

  const share = useMutation({
    mutationFn: () => playerApi.createShare(track.id),
    onSuccess: async (link) => {
      const url = playerApi.sharePageUrl(link.token)
      const copied = await copyToClipboard(url)
      toast.push(copied ? 'Share link copied' : `Share link: ${url}`, 'ok')
      qc.invalidateQueries({ queryKey: ['player-shares'] })
    },
    onError: (err) => toast.push((err as Error).message, 'error'),
  })

  useEffect(() => {
    if (!open) return
    const onDocClick = (e: Event) => {
      if (!wrapRef.current?.contains(e.target as Node)) {
        setOpen(false)
        setPlaylistsOpen(false)
      }
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setOpen(false)
        setPlaylistsOpen(false)
      }
    }
    document.addEventListener('mousedown', onDocClick)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDocClick)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  function run(fn: () => void) {
    return (e: MouseEvent) => {
      e.stopPropagation()
      e.preventDefault()
      fn()
      setOpen(false)
      setPlaylistsOpen(false)
    }
  }

  return (
    <div className="track-menu-wrap" ref={wrapRef} onClick={(e) => e.stopPropagation()}>
      <button
        type="button"
        className="pill-icon-btn"
        aria-label="More options"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={(e) => {
          e.stopPropagation()
          setOpen((o) => !o)
          setPlaylistsOpen(false)
        }}
      >
        <IconMore size={18} />
      </button>

      {open && (
        <div className="track-menu" role="menu">
          <button type="button" role="menuitem" onClick={run(() => q.playTrack(track, queue))}>
            Play
          </button>
          <button
            type="button"
            role="menuitem"
            onClick={run(() => {
              q.addNext(track)
              toast.push('Playing next', 'ok')
            })}
          >
            Play Next
          </button>
          <button
            type="button"
            role="menuitem"
            onClick={run(() => {
              q.addEnd(track)
              toast.push('Added to end of queue', 'ok')
            })}
          >
            Add to End
          </button>

          <div className="track-menu-sep" />

          <button
            type="button"
            role="menuitem"
            className="has-sub"
            onClick={(e) => {
              e.stopPropagation()
              setPlaylistsOpen((o) => !o)
            }}
          >
            Add to playlist…
          </button>
          {playlistsOpen && (
            <div className="track-menu-sub">
              {playlists.isLoading && <span className="muted tiny">Loading…</span>}
              {playlists.data?.map((pl) => (
                <button
                  key={pl.id}
                  type="button"
                  role="menuitem"
                  onClick={run(() => addPl.mutate(Number(pl.id)))}
                >
                  {pl.name}
                </button>
              ))}
              {playlists.isSuccess && !playlists.data?.length && (
                <span className="muted tiny">No playlists yet</span>
              )}
            </div>
          )}

          <button type="button" role="menuitem" onClick={run(() => toggleFav.mutate())}>
            {liked ? 'Remove from Liked Songs' : 'Love'}
          </button>
          <button type="button" role="menuitem" onClick={run(() => share.mutate())}>
            Share song…
          </button>

          {!hideNavigation && (
            <>
              <div className="track-menu-sep" />
              {!!track.album_id && (
                <button
                  type="button"
                  role="menuitem"
                  onClick={run(() => navigate(`/player/albums/${track.album_id}`))}
                >
                  Go to album
                </button>
              )}
              {!!track.artist_id && (
                <button
                  type="button"
                  role="menuitem"
                  onClick={run(() => navigate(`/player/artists/${track.artist_id}`))}
                >
                  Go to artist
                </button>
              )}
            </>
          )}

          {onRemove && (
            <>
              <div className="track-menu-sep" />
              <button type="button" role="menuitem" className="danger" onClick={run(onRemove)}>
                {removeLabel || 'Remove'}
              </button>
            </>
          )}
        </div>
      )}
    </div>
  )
}
