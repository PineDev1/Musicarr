import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AnimatePresence, motion } from 'framer-motion'
import { useEffect, useRef, useState } from 'react'
import { api } from './api'

const topLinks = [
  { to: '/dashboard', label: 'Dashboard' },
  { to: '/', label: 'Library', end: true },
  { to: '/add', label: 'Add Artist' },
]

const activityLinks = [
  { to: '/pending-artists', label: 'Pending Artists' },
  { to: '/wanted', label: 'Wanted' },
  { to: '/skipped', label: 'Skipped' },
  { to: '/upgrades', label: 'Upgrades' },
  { to: '/queue', label: 'Queue' },
  { to: '/import-review', label: 'Import Review' },
  { to: '/import-lists', label: 'Import Lists' },
]

const toolsLinks = [
  { to: '/calendar', label: 'Release Calendar' },
  { to: '/maintenance', label: 'Duplicate Cleanup' },
  { to: '/activity', label: 'Activity' },
]

const bottomLinks = [
  { to: '/now-playing', label: 'Now Playing' },
  { to: '/settings', label: 'Settings' },
]

type NavLinkDef = { to: string; label: string; end?: boolean }

function badgeFor(
  to: string,
  health: any,
  importReviewCount: number
): number {
  switch (to) {
    case '/queue':
      return health?.queue_size || 0
    case '/wanted':
      return health?.wanted_albums || 0
    case '/import-review':
      return importReviewCount || 0
    case '/pending-artists':
      return health?.pending_artists || 0
    case '/skipped':
      return health?.skipped_albums || 0
    default:
      return 0
  }
}

function NavLinks({
  items,
  health,
  importReviewCount,
}: {
  items: NavLinkDef[]
  health: any
  importReviewCount: number
}) {
  return (
    <nav className="nav">
      {items.map((l) => {
        const count = badgeFor(l.to, health, importReviewCount)
        return (
          <NavLink
            key={l.to}
            to={l.to}
            end={l.end}
            className={({ isActive }) => (isActive ? 'active' : '')}
          >
            {l.label}
            {count > 0 ? ` (${count})` : ''}
          </NavLink>
        )
      })}
    </nav>
  )
}

function NavGroup({
  title,
  items,
  health,
  importReviewCount,
}: {
  title: string
  items: NavLinkDef[]
  health: any
  importReviewCount: number
}) {
  const aggregate = items.reduce(
    (sum, l) => sum + badgeFor(l.to, health, importReviewCount),
    0
  )
  return (
    <details className="nav-group" open={aggregate > 0}>
      <summary>
        {title}
        {aggregate > 0 ? ` (${aggregate})` : ''}
      </summary>
      <NavLinks items={items} health={health} importReviewCount={importReviewCount} />
    </details>
  )
}

function GlobalSearch() {
  const navigate = useNavigate()
  const [term, setTerm] = useState('')
  const [debounced, setDebounced] = useState('')
  const [open, setOpen] = useState(false)
  const boxRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    const t = window.setTimeout(() => setDebounced(term.trim()), 300)
    return () => window.clearTimeout(t)
  }, [term])

  const results = useQuery({
    queryKey: ['global-search', debounced],
    queryFn: () => api.search(debounced),
    enabled: debounced.length > 1,
  })

  useEffect(() => {
    const onDocClick = (e: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onDocClick)
    return () => document.removeEventListener('mousedown', onDocClick)
  }, [])

  const hasResults = !!(results.data?.artists.length || results.data?.albums.length)

  function go(path: string) {
    setOpen(false)
    setTerm('')
    navigate(path)
  }

  return (
    <div className="global-search" ref={boxRef}>
      <input
        type="search"
        placeholder="Search artists & albums…"
        value={term}
        onChange={(e) => {
          setTerm(e.target.value)
          setOpen(true)
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={(e) => {
          if (e.key === 'Escape') setOpen(false)
        }}
      />
      {open && debounced.length > 1 && (
        <div className="global-search-results">
          {results.isLoading && <div className="muted tiny">Searching…</div>}
          {!results.isLoading && !hasResults && <div className="muted tiny">No matches</div>}
          {results.data?.artists.map((a) => (
            <button key={`a-${a.id}`} type="button" onClick={() => go(`/artists/${a.id}`)}>
              {a.image_url ? <img src={a.image_url} alt="" /> : <span className="ph" />}
              <span>{a.name}</span>
              <span className="muted tiny">Artist</span>
            </button>
          ))}
          {results.data?.albums.map((al) => (
            <button key={`al-${al.id}`} type="button" onClick={() => go(`/albums/${al.id}`)}>
              {al.cover_url ? <img src={al.cover_url} alt="" /> : <span className="ph" />}
              <span>
                {al.title} <span className="muted tiny">— {al.artist_name}</span>
              </span>
              <span className="muted tiny">Album</span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

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
        <NavLinks items={topLinks} health={health.data} importReviewCount={importReviewCount} />
        <NavGroup
          title="Activity"
          items={activityLinks}
          health={health.data}
          importReviewCount={importReviewCount}
        />
        <NavGroup
          title="Tools"
          items={toolsLinks}
          health={health.data}
          importReviewCount={importReviewCount}
        />
        <NavLinks items={bottomLinks} health={health.data} importReviewCount={importReviewCount} />
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
        <div className="main-topbar">
          <GlobalSearch />
        </div>
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
