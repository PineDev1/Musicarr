import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AnimatePresence, motion } from 'framer-motion'
import { api } from './api'

const links = [
  { to: '/', label: 'Library', end: true },
  { to: '/add', label: 'Add Artist' },
  { to: '/pending-artists', label: 'Pending Artists' },
  { to: '/wanted', label: 'Wanted' },
  { to: '/skipped', label: 'Skipped' },
  { to: '/upgrades', label: 'Upgrades' },
  { to: '/queue', label: 'Queue' },
  { to: '/import-review', label: 'Import Review' },
  { to: '/import-lists', label: 'Import Lists' },
  { to: '/now-playing', label: 'Now Playing' },
  { to: '/activity', label: 'Activity' },
  { to: '/settings', label: 'Settings' },
]

export function Layout() {
  const qc = useQueryClient()
  const health = useQuery({ queryKey: ['health'], queryFn: api.health, refetchInterval: 15000 })
  const auth = useQuery({ queryKey: ['auth-status'], queryFn: api.authStatus })
  // suggest=false keeps this a cheap DB-only count, safe to poll in the nav.
  const importReview = useQuery({
    queryKey: ['import-review-count'],
    queryFn: () => api.importReview(false),
    refetchInterval: 60000,
  })
  const importReviewCount =
    (importReview.data?.local_artists.length || 0) + (importReview.data?.weak_albums.length || 0)
  const location = useLocation()
  const provider = health.data?.active_provider || 'deezer'

  const signOut = useMutation({
    mutationFn: api.appLogout,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['auth-status'] }),
  })

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          Music<span>arr</span>
        </div>
        <nav className="nav">
          {links.map((l) => (
            <NavLink
              key={l.to}
              to={l.to}
              end={l.end}
              className={({ isActive }) => (isActive ? 'active' : '')}
            >
              {l.label}
              {l.to === '/queue' && health.data && health.data.queue_size > 0
                ? ` (${health.data.queue_size})`
                : ''}
              {l.to === '/wanted' && health.data && health.data.wanted_albums > 0
                ? ` (${health.data.wanted_albums})`
                : ''}
              {l.to === '/import-review' && importReviewCount > 0 ? ` (${importReviewCount})` : ''}
              {l.to === '/pending-artists' && health.data && health.data.pending_artists > 0
                ? ` (${health.data.pending_artists})`
                : ''}
              {l.to === '/skipped' && health.data && health.data.skipped_albums > 0
                ? ` (${health.data.skipped_albums})`
                : ''}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-meta">
          <div className="muted" style={{ fontSize: '0.85rem' }}>
            Source: <strong style={{ color: 'var(--text)', textTransform: 'capitalize' }}>{provider}</strong>
          </div>
          <div className="muted" style={{ fontSize: '0.85rem', marginTop: '0.25rem' }}>
            {health.data?.provider_ok ? 'Connected' : 'Not ready'}
          </div>
          {auth.data?.enabled && auth.data.authenticated && (
            <button
              type="button"
              className="btn ghost"
              style={{ marginTop: '0.75rem', width: '100%' }}
              onClick={() => signOut.mutate()}
              disabled={signOut.isPending}
            >
              Sign out
            </button>
          )}
          <div className="pindev">Produced by Pindev</div>
        </div>
      </aside>
      <main className="main">
        {health.data && !health.data.provider_ok && (
          <div className="banner danger">
            {health.data.provider_error ||
              `Configure a valid ${provider} account in Settings to download music.`}
          </div>
        )}
        <AnimatePresence mode="wait">
          <motion.div
            key={location.pathname}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
          >
            <Outlet />
          </motion.div>
        </AnimatePresence>
      </main>
    </div>
  )
}
