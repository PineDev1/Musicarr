import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { Layout } from './Layout'
import { ToastProvider } from './Toast'
import { ActivityPage } from './pages/ActivityPage'
import { AddArtistPage } from './pages/AddArtistPage'
import { ArtistPage } from './pages/ArtistPage'
import { LibraryPage } from './pages/LibraryPage'
import { QueuePage } from './pages/QueuePage'
import { SettingsPage } from './pages/SettingsPage'
import { WantedPage } from './pages/WantedPage'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
})

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <BrowserRouter>
          <Routes>
            <Route element={<Layout />}>
              <Route index element={<LibraryPage />} />
              <Route path="add" element={<AddArtistPage />} />
              <Route path="artists/:id" element={<ArtistPage />} />
              <Route path="wanted" element={<WantedPage />} />
              <Route path="queue" element={<QueuePage />} />
              <Route path="activity" element={<ActivityPage />} />
              <Route path="settings" element={<SettingsPage />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </ToastProvider>
    </QueryClientProvider>
  )
}
