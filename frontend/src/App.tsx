import { QueryClient, QueryClientProvider, useQuery, useQueryClient } from '@tanstack/react-query'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { Layout } from './Layout'
import { ToastProvider } from './Toast'
import { api } from './api'
import { ActivityPage } from './pages/ActivityPage'
import { AddArtistPage } from './pages/AddArtistPage'
import { AlbumPage } from './pages/AlbumPage'
import { ArtistPage } from './pages/ArtistPage'
import { ImportReviewPage } from './pages/ImportReviewPage'
import { LibraryPage } from './pages/LibraryPage'
import { LoginPage } from './pages/LoginPage'
import { QueuePage } from './pages/QueuePage'
import { SettingsPage } from './pages/SettingsPage'
import { WantedPage } from './pages/WantedPage'
import { NowPlayingPage } from './pages/NowPlayingPage'
import { PlayerApp } from './player/PlayerApp'
import { ShareSongPage } from './player/ShareSongPage'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
})

function AdminApp() {
  const qc = useQueryClient()
  const auth = useQuery({
    queryKey: ['auth-status'],
    queryFn: api.authStatus,
    retry: false,
    refetchOnWindowFocus: true,
  })

  if (auth.isLoading) {
    return (
      <div className="login-shell">
        <p className="muted">Loading…</p>
      </div>
    )
  }

  if (auth.data?.enabled && !auth.data.authenticated) {
    return (
      <LoginPage
        onLoggedIn={() => {
          qc.invalidateQueries({ queryKey: ['auth-status'] })
        }}
      />
    )
  }

  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<LibraryPage />} />
        <Route path="add" element={<AddArtistPage />} />
        <Route path="artists/:id" element={<ArtistPage />} />
        <Route path="albums/:id" element={<AlbumPage />} />
        <Route path="wanted" element={<WantedPage />} />
        <Route path="queue" element={<QueuePage />} />
        <Route path="now-playing" element={<NowPlayingPage />} />
        <Route path="activity" element={<ActivityPage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="import-review" element={<ImportReviewPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/s/:token" element={<ShareSongPage />} />
            <Route path="/player/*" element={<PlayerApp />} />
            <Route path="/*" element={<AdminApp />} />
          </Routes>
        </BrowserRouter>
      </ToastProvider>
    </QueryClientProvider>
  )
}
