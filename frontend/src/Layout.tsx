import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { AnimatePresence, motion } from 'framer-motion'
import { api } from './api'

const links = [
  { to: '/', label: 'Library', end: true },
  { to: '/add', label: 'Add Artist' },
  { to: '/wanted', label: 'Wanted' },
  { to: '/queue', label: 'Queue' },
  { to: '/activity', label: 'Activity' },
  { to: '/settings', label: 'Settings' },
]

export function Layout() {
  const health = useQuery({ queryKey: ['health'], queryFn: api.health, refetchInterval: 15000 })
  const location = useLocation()
  const provider = health.data?.active_provider || 'deezer'

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
