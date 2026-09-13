import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { IconClose, IconPlus, IconSettings } from './icons'
import { DEFAULT_PREFS, playerApi, type PlayerPrefs } from './playerApi'
import { WavyPlayBar } from './WavyPlayBar'

export function PlayerLayout({ displayName }: { displayName: string }) {
  const qc = useQueryClient()
  const navigate = useNavigate()
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [createOpen, setCreateOpen] = useState(false)
  const [plName, setPlName] = useState('')
  const [plSmart, setPlSmart] = useState(false)
  const [currentPw, setCurrentPw] = useState('')
  const [newPw, setNewPw] = useState('')
  const [pwMsg, setPwMsg] = useState<string | null>(null)

  const prefsQ = useQuery({ queryKey: ['player-prefs'], queryFn: playerApi.prefs })
  const prefs = prefsQ.data || DEFAULT_PREFS

  const logout = useMutation({
    mutationFn: playerApi.logout,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['player-status'] }),
  })
  const changePw = useMutation({
    mutationFn: () => playerApi.changePassword(currentPw, newPw),
    onSuccess: () => {
      setCurrentPw('')
      setNewPw('')
      setPwMsg('Password updated')
    },
    onError: (err) => setPwMsg((err as Error).message),
  })
  const savePrefs = useMutation({
    mutationFn: (body: Partial<PlayerPrefs>) => playerApi.updatePrefs(body),
    onSuccess: (data) => {
      qc.setQueryData(['player-prefs'], data)
      qc.invalidateQueries({ queryKey: ['player-builtins'] })
    },
  })
  const createPl = useMutation({
    mutationFn: () => playerApi.createPlaylist(plName.trim(), plSmart),
    onSuccess: (pl) => {
      setCreateOpen(false)
      setPlName('')
      setPlSmart(false)
      qc.invalidateQueries({ queryKey: ['player-playlists'] })
      navigate(`/player/playlists/${pl.id}`)
    },
  })

  function patchPref<K extends keyof PlayerPrefs>(key: K, value: PlayerPrefs[K]) {
    const next = { ...prefs, [key]: value }
    qc.setQueryData(['player-prefs'], next)
    savePrefs.mutate({ [key]: value })
  }

  return (
    <div className="player-shell">
      <header className="player-top">
        <div className="brand">
          Music<span>arr</span> <span className="player-tag">Player</span>
        </div>
        <nav className="player-nav">
          <NavLink to="/player" end>
            Library
          </NavLink>
          <NavLink to="/player/playlists">Playlists</NavLink>
          <NavLink to="/player/search">Search</NavLink>
        </nav>
        <div className="player-user">
          <span className="muted">{displayName}</span>
          <button
            type="button"
            className="pill-icon-btn"
            aria-label="Settings"
            onClick={() => setSettingsOpen(true)}
          >
            <IconSettings size={18} />
          </button>
          <button type="button" className="btn ghost" onClick={() => logout.mutate()} disabled={logout.isPending}>
            Sign out
          </button>
        </div>
      </header>

      <main className="player-main">
        <Outlet />
      </main>

      <button
        type="button"
        className="player-fab"
        aria-label="Create playlist"
        onClick={() => setCreateOpen(true)}
      >
        <IconPlus size={26} />
      </button>

      <WavyPlayBar />

      {createOpen && (
        <div className="player-modal-backdrop" onClick={() => setCreateOpen(false)}>
          <form
            className="player-modal"
            onClick={(e) => e.stopPropagation()}
            onSubmit={(e: FormEvent) => {
              e.preventDefault()
              if (plName.trim()) createPl.mutate()
            }}
          >
            <div className="player-modal-head">
              <h2>New playlist</h2>
              <button type="button" className="pill-icon-btn" onClick={() => setCreateOpen(false)}>
                <IconClose size={18} />
              </button>
            </div>
            <div className="field">
              <label>Name</label>
              <input value={plName} onChange={(e) => setPlName(e.target.value)} autoFocus />
            </div>
            <label className="checks">
              <input type="checkbox" checked={plSmart} onChange={(e) => setPlSmart(e.target.checked)} />
              Smart playlist (suggest similar songs after 10 tracks)
            </label>
            <button className="btn" type="submit" disabled={!plName.trim() || createPl.isPending}>
              Create
            </button>
          </form>
        </div>
      )}

      {settingsOpen && (
        <div className="player-modal-backdrop" onClick={() => setSettingsOpen(false)}>
          <div className="player-modal wide" onClick={(e) => e.stopPropagation()}>
            <div className="player-modal-head">
              <h2>Personal settings</h2>
              <button type="button" className="pill-icon-btn" onClick={() => setSettingsOpen(false)}>
                <IconClose size={18} />
              </button>
            </div>

            <h3>Built-in playlists</h3>
            <label className="checks">
              <input
                type="checkbox"
                checked={prefs.show_recently_played}
                onChange={(e) => patchPref('show_recently_played', e.target.checked)}
              />
              Show Recently Played
            </label>
            <label className="checks">
              <input
                type="checkbox"
                checked={prefs.show_shuffle_mix}
                onChange={(e) => patchPref('show_shuffle_mix', e.target.checked)}
              />
              Show Shuffle Mix
            </label>

            <h3>Wavy seek bar</h3>
            <p className="muted" style={{ marginTop: 0 }}>
              Android-style squiggly scrubber — Musicarr themed, yours to tune.
            </p>
            <div className="pref-grid">
              <label>
                Height
                <input
                  type="range"
                  min={0}
                  max={16}
                  step={0.5}
                  value={prefs.wave_height}
                  onChange={(e) => patchPref('wave_height', Number(e.target.value))}
                />
              </label>
              <label>
                Length
                <input
                  type="range"
                  min={8}
                  max={48}
                  step={1}
                  value={prefs.wave_length}
                  onChange={(e) => patchPref('wave_length', Number(e.target.value))}
                />
              </label>
              <label>
                Speed
                <input
                  type="range"
                  min={0}
                  max={40}
                  step={1}
                  value={prefs.wave_speed}
                  onChange={(e) => patchPref('wave_speed', Number(e.target.value))}
                />
              </label>
              <label>
                Thickness
                <input
                  type="range"
                  min={1}
                  max={8}
                  step={0.5}
                  value={prefs.wave_thickness}
                  onChange={(e) => patchPref('wave_thickness', Number(e.target.value))}
                />
              </label>
              <label>
                Color
                <input
                  type="color"
                  value={prefs.wave_color || '#3dba7a'}
                  onChange={(e) => patchPref('wave_color', e.target.value)}
                />
              </label>
            </div>
            <label className="checks">
              <input
                type="checkbox"
                checked={prefs.wave_flatten_when_paused}
                onChange={(e) => patchPref('wave_flatten_when_paused', e.target.checked)}
              />
              Flatten wave when paused
            </label>

            <h3>Password</h3>
            <form
              className="player-pw-panel inline"
              onSubmit={(e) => {
                e.preventDefault()
                changePw.mutate()
              }}
            >
              <input
                type="password"
                placeholder="Current password"
                value={currentPw}
                onChange={(e) => setCurrentPw(e.target.value)}
              />
              <input
                type="password"
                placeholder="New password"
                value={newPw}
                onChange={(e) => setNewPw(e.target.value)}
              />
              <button className="btn secondary" type="submit" disabled={newPw.length < 4}>
                Update
              </button>
              {pwMsg && <span className="muted">{pwMsg}</span>}
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
