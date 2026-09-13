import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Navigate, Route, Routes } from 'react-router-dom'
import { PlayerAlbumPage } from './PlayerAlbumPage'
import { PlayerArtistPage } from './PlayerArtistPage'
import { PlayerHomePage } from './PlayerHomePage'
import { PlayerLayout } from './PlayerLayout'
import { PlayerLoginPage } from './PlayerLoginPage'
import { PlayerPlaylistDetailPage } from './PlayerPlaylistDetailPage'
import { PlayerPlaylistsPage } from './PlayerPlaylistsPage'
import { PlayerQueueProvider } from './PlayerQueueContext'
import { PlayerSearchPage } from './PlayerSearchPage'
import { playerApi } from './playerApi'

export function PlayerApp() {
  const qc = useQueryClient()
  const status = useQuery({
    queryKey: ['player-status'],
    queryFn: playerApi.status,
    retry: false,
  })

  if (status.isLoading) {
    return (
      <div className="login-shell">
        <p className="muted">Loading player…</p>
      </div>
    )
  }

  if (status.isError) {
    return (
      <div className="login-shell">
        <div className="login-card">
          <h1>Player unavailable</h1>
          <p className="muted">{(status.error as Error).message}</p>
          <p className="muted">Enable the player under Musicarr Settings → Player.</p>
        </div>
      </div>
    )
  }

  if (!status.data?.enabled) {
    return (
      <div className="login-shell">
        <div className="login-card">
          <div className="brand">
            Music<span>arr</span>
          </div>
          <h2 style={{ margin: '0.5rem 0' }}>Player is disabled</h2>
          <p className="muted">
            An admin can turn it on in Settings → Player, then create listener accounts.
          </p>
        </div>
      </div>
    )
  }

  if (!status.data.authenticated) {
    return (
      <PlayerLoginPage
        onLoggedIn={() => {
          qc.invalidateQueries({ queryKey: ['player-status'] })
        }}
      />
    )
  }

  return (
    <PlayerQueueProvider userId={status.data.user_id}>
      <Routes>
        <Route element={<PlayerLayout displayName={status.data.display_name || status.data.username || ''} />}>
          <Route index element={<PlayerHomePage />} />
          <Route path="artists/:id" element={<PlayerArtistPage />} />
          <Route path="albums/:id" element={<PlayerAlbumPage />} />
          <Route path="playlists" element={<PlayerPlaylistsPage />} />
          <Route path="playlists/:id" element={<PlayerPlaylistDetailPage />} />
          <Route path="search" element={<PlayerSearchPage />} />
          <Route path="*" element={<Navigate to="/player" replace />} />
        </Route>
      </Routes>
    </PlayerQueueProvider>
  )
}
