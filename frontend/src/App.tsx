import { QueryClient, QueryClientProvider, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { Layout } from './Layout'
import { ToastProvider } from './Toast'
import { api } from './api'
import { ActivityPage } from './pages/ActivityPage'
import { AddArtistPage } from './pages/AddArtistPage'
import { AlbumPage } from './pages/AlbumPage'
import { ArtistPage } from './pages/ArtistPage'
import { CalendarPage } from './pages/CalendarPage'
import { DashboardPage } from './pages/DashboardPage'
import { ImportListsPage } from './pages/ImportListsPage'
import { ImportReviewPage } from './pages/ImportReviewPage'
import { LibraryPage } from './pages/LibraryPage'
import { LoginPage } from './pages/LoginPage'
import { MaintenancePage } from './pages/MaintenancePage'
import { PendingArtistsPage } from './pages/PendingArtistsPage'
import { QueuePage } from './pages/QueuePage'
import { SettingsPage } from './pages/SettingsPage'
import { SetupWizardPage, isSetupComplete, markSetupDone } from './pages/SetupWizardPage'
import { SkippedReleasesPage } from './pages/SkippedReleasesPage'
import { UpgradesPage } from './pages/UpgradesPage'
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
  const health = useQuery({
    queryKey: ['health'],
    queryFn: api.health,
    retry: false,
    enabled: Boolean(auth.data && (!auth.data.enabled || auth.data.authenticated)),
  })

  const anyProvider =
    Boolean(health.data?.deezer_ok) ||
    Boolean(health.data?.tidal_ok) ||
    Boolean(health.data?.qobuz_ok)
  const configured = Boolean(health.data?.library_writable) && anyProvider
  const needsSetup = Boolean(health.data) && !isSetupComplete() && !configured

  useEffect(() => {
    if (configured && !isSetupComplete()) {
      markSetupDone()
    }
  }, [configured])

  if (auth.isLoading || (auth.data && (!auth.data.enabled || auth.data.authenticated) && health.isLoading)) {
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
      <Route path="setup" element={<SetupWizardPage />} />
      {needsSetup ? (
        <Route path="*" element={<Navigate to="/setup" replace />} />
      ) : (
        <Route element={<Layout />}>
          <Route index element={<LibraryPage />} />
          <Route path="dashboard" element={<DashboardPage />} />
          <Route path="add" element={<AddArtistPage />} />
          <Route path="artists/:id" element={<ArtistPage />} />
          <Route path="albums/:id" element={<AlbumPage />} />
          <Route path="wanted" element={<WantedPage />} />
          <Route path="skipped" element={<SkippedReleasesPage />} />
          <Route path="pending-artists" element={<PendingArtistsPage />} />
          <Route path="upgrades" element={<UpgradesPage />} />
          <Route path="queue" element={<QueuePage />} />
          <Route path="now-playing" element={<NowPlayingPage />} />
          <Route path="activity" element={<ActivityPage />} />
          <Route path="settings" element={<SettingsPage />} />
          <Route path="import-review" element={<ImportReviewPage />} />
          <Route path="import-lists" element={<ImportListsPage />} />
          <Route path="calendar" element={<CalendarPage />} />
          <Route path="maintenance" element={<MaintenancePage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      )}
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
