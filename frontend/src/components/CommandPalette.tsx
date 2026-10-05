import { useQuery } from '@tanstack/react-query'
import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import { useToast } from '../Toast'

type Item = { id: string; label: string; hint: string; run: () => void }

const PAGES: { to: string; label: string }[] = [
  { to: '/dashboard', label: 'Dashboard' },
  { to: '/', label: 'Library' },
  { to: '/add', label: 'Add Artist' },
  { to: '/wanted', label: 'Wanted' },
  { to: '/skipped', label: 'Skipped releases' },
  { to: '/upgrades', label: 'Upgrades' },
  { to: '/queue', label: 'Queue' },
  { to: '/pending-artists', label: 'Pending artists' },
  { to: '/import-review', label: 'Import review' },
  { to: '/import-lists', label: 'Import lists' },
  { to: '/discover', label: 'Discover' },
  { to: '/calendar', label: 'Release calendar' },
  { to: '/maintenance', label: 'Duplicate cleanup & trash' },
  { to: '/activity', label: 'Activity' },
  { to: '/system', label: 'System' },
  { to: '/now-playing', label: 'Now playing' },
  { to: '/settings', label: 'Settings' },
  { to: '/settings?tab=backup', label: 'Settings → Backup' },
  { to: '/settings?tab=indexers', label: 'Settings → Indexers' },
  { to: '/settings?tab=library', label: 'Settings → Library' },
  { to: '/settings?tab=player', label: 'Settings → Player (invite links)' },
  { to: '/settings?tab=security', label: 'Settings → Security' },
]

/** Cmd/Ctrl+K launcher: jump to any page, artist or album, or run a common action. */
export function CommandPalette() {
  const navigate = useNavigate()
  const toast = useToast()
  const [open, setOpen] = useState(false)
  const [term, setTerm] = useState('')
  const [debounced, setDebounced] = useState('')
  const [cursor, setCursor] = useState(0)
  const inputRef = useRef<HTMLInputElement | null>(null)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const typing = /^(INPUT|TEXTAREA|SELECT)$/.test((e.target as HTMLElement)?.tagName || '')
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        setOpen((o) => !o)
      } else if (e.key === '/' && !typing && !e.metaKey && !e.ctrlKey) {
        e.preventDefault()
        setOpen(true)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  useEffect(() => {
    if (open) {
      setTerm('')
      setDebounced('')
      setCursor(0)
      window.setTimeout(() => inputRef.current?.focus(), 0)
    }
  }, [open])

  useEffect(() => {
    const t = window.setTimeout(() => setDebounced(term.trim()), 200)
    return () => window.clearTimeout(t)
  }, [term])

  const results = useQuery({
    queryKey: ['palette-search', debounced],
    queryFn: () => api.search(debounced),
    enabled: open && debounced.length > 1,
  })

  const items = useMemo<Item[]>(() => {
    const go = (to: string) => () => {
      setOpen(false)
      navigate(to)
    }
    const act = (label: string, fn: () => Promise<unknown>, done: string) => () => {
      setOpen(false)
      fn()
        .then(() => toast.push(done, 'ok'))
        .catch((err: Error) => toast.push(`${label}: ${err.message}`, 'error'))
    }
    const actions: Item[] = [
      { id: 'act-monitor', label: 'Check for new releases', hint: 'Action', run: act('Check releases', api.runMonitor, 'Release check started') },
      { id: 'act-scan', label: 'Scan library', hint: 'Action', run: act('Scan', api.scan, 'Library scan started') },
      { id: 'act-backup', label: 'Back up now', hint: 'Action', run: act('Backup', api.runBackupNow, 'Backup saved') },
      {
        id: 'act-wanted',
        label: 'Search all wanted albums',
        hint: 'Action',
        run: () => {
          setOpen(false)
          navigate('/wanted')
        },
      },
    ]
    const pages = PAGES.map((p) => ({ id: `page-${p.to}`, label: p.label, hint: 'Go to', run: go(p.to) }))
    const needle = term.trim().toLowerCase()
    const match = (i: Item) => !needle || i.label.toLowerCase().includes(needle)
    const found: Item[] = []
    results.data?.artists.slice(0, 6).forEach((a) =>
      found.push({ id: `artist-${a.id}`, label: a.name, hint: 'Artist', run: go(`/artists/${a.id}`) }),
    )
    results.data?.albums.slice(0, 6).forEach((al) =>
      found.push({ id: `album-${al.id}`, label: `${al.title} — ${al.artist_name}`, hint: 'Album', run: go(`/albums/${al.id}`) }),
    )
    return [...found, ...actions.filter(match), ...pages.filter(match)].slice(0, 30)
  }, [term, results.data, navigate, toast])

  useEffect(() => setCursor(0), [term])

  if (!open) return null

  return (
    <div className="modal-backdrop palette-backdrop" onMouseDown={() => setOpen(false)} role="presentation">
      <div
        className="modal card palette"
        role="dialog"
        aria-modal="true"
        aria-label="Command palette"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <input
          ref={inputRef}
          className="palette-input"
          placeholder="Jump to a page, artist or album — or run an action…"
          value={term}
          onChange={(e) => setTerm(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Escape') setOpen(false)
            else if (e.key === 'ArrowDown') {
              e.preventDefault()
              setCursor((c) => Math.min(items.length - 1, c + 1))
            } else if (e.key === 'ArrowUp') {
              e.preventDefault()
              setCursor((c) => Math.max(0, c - 1))
            } else if (e.key === 'Enter') {
              e.preventDefault()
              items[cursor]?.run()
            }
          }}
        />
        <div className="palette-list" role="listbox">
          {items.length === 0 && <p className="muted" style={{ margin: '0.75rem' }}>No matches</p>}
          {items.map((it, i) => (
            <button
              key={it.id}
              type="button"
              role="option"
              aria-selected={i === cursor}
              className={`palette-row${i === cursor ? ' active' : ''}`}
              onMouseEnter={() => setCursor(i)}
              onClick={it.run}
            >
              <span>{it.label}</span>
              <span className="muted tiny">{it.hint}</span>
            </button>
          ))}
        </div>
        <div className="muted tiny" style={{ padding: '0.4rem 0.75rem' }}>
          ↑↓ to move · Enter to open · Esc to close · press / or ⌘K anywhere
        </div>
      </div>
    </div>
  )
}
