import { QueryClient, QueryClientProvider, useQuery, useQueryClient } from '@tanstack/react-query'
import { Suspense, useEffect } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { Layout } from './Layout'
import { ToastProvider } from './Toast'
import { lazyPage } from './lazyPage'
import { api } from './api'
import { LoginPage } from './pages/LoginPage'
import { SetupWizardPage, isSetupComplete, markSetupDone } from './pages/SetupWizardPage'

// Route-level code splitting: each page (and the whole player) is its own chunk, so a
// visit downloads only what it opens instead of one ~800 KB bundle.
const ActivityPage = lazyPage(() => import('./pages/ActivityPage').then((m) => ({ default: m.ActivityPage })))
const AddArtistPage = lazyPage(() => import('./pages/AddArtistPage').then((m) => ({ default: m.AddArtistPage })))
const AlbumPage = lazyPage(() => import('./pages/AlbumPage').then((m) => ({ default: m.AlbumPage })))
const ArtistPage = lazyPage(() => import('./pages/ArtistPage').then((m) => ({ default: m.ArtistPage })))
const CalendarPage = lazyPage(() => import('./pages/CalendarPage').then((m) => ({ default: m.CalendarPage })))
const SystemPage = lazyPage(() => import('./pages/SystemPage').then((m) => ({ default: m.SystemPage })))
const DiscoverPage = lazyPage(() => import('./pages/DiscoverPage').then((m) => ({ default: m.DiscoverPage })))
const DashboardPage = lazyPage(() => import('./pages/DashboardPage').then((m) => ({ default: m.DashboardPage })))
const ImportListsPage = lazyPage(() => import('./pages/ImportListsPage').then((m) => ({ default: m.ImportListsPage })))
const ImportReviewPage = lazyPage(() => import('./pages/ImportReviewPage').then((m) => ({ default: m.ImportReviewPage })))
const LibraryPage = lazyPage(() => import('./pages/LibraryPage').then((m) => ({ default: m.LibraryPage })))
const MaintenancePage = lazyPage(() => import('./pages/MaintenancePage').then((m) => ({ default: m.MaintenancePage })))
const PendingArtistsPage = lazyPage(() => import('./pages/PendingArtistsPage').then((m) => ({ default: m.PendingArtistsPage })))
const QueuePage = lazyPage(() => import('./pages/QueuePage').then((m) => ({ default: m.QueuePage })))
const SettingsPage = lazyPage(() => import('./pages/SettingsPage').then((m) => ({ default: m.SettingsPage })))
const SkippedReleasesPage = lazyPage(() => import('./pages/SkippedReleasesPage').then((m) => ({ default: m.SkippedReleasesPage })))
const UpgradesPage = lazyPage(() => import('./pages/UpgradesPage').then((m) => ({ default: m.UpgradesPage })))
const WantedPage = lazyPage(() => import('./pages/WantedPage').then((m) => ({ default: m.WantedPage })))
const NowPlayingPage = lazyPage(() => import('./pages/NowPlayingPage').then((m) => ({ default: m.NowPlayingPage })))
const PlayerApp = lazyPage(() => import('./player/PlayerApp').then((m) => ({ default: m.PlayerApp })))
const ShareSongPage = lazyPage(() => import('./player/ShareSongPage').then((m) => ({ default: m.ShareSongPage })))

function PageFallback() {
  return (
    <div className="login-shell">
      <p className="muted">Loading…</p>
    </div>
  )
}

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
    <Suspense fallback={<PageFallback />}>
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
          <Route path="discover" element={<DiscoverPage />} />
          <Route path="maintenance" element={<MaintenancePage />} />
          <Route path="system" element={<SystemPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      )}
    </Routes>
    </Suspense>
  )
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <BrowserRouter>
          <Suspense fallback={<PageFallback />}>
          <Routes>
            <Route path="/s/:token" element={<ShareSongPage />} />
            <Route path="/player/*" element={<PlayerApp />} />
            <Route path="/*" element={<AdminApp />} />
          </Routes>
          </Suspense>
        </BrowserRouter>
      </ToastProvider>
    </QueryClientProvider>
  )
}
