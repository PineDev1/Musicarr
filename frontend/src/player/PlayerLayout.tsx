import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState, type ChangeEvent, type FormEvent } from 'react'
import { useToast } from '../Toast'
import {
  IconBack,
  IconClose,
  IconForward,
  IconHeart,
  IconHome,
  IconLibrary,
  IconMusic,
  IconPlus,
  IconQueue,
  IconSearch,
  IconSettings,
  IconUser,
} from './icons'
import { DEFAULT_PREFS, playerApi, type PlayerPrefs, type PlayerRepeatMode } from './playerApi'
import { copyToClipboard } from './TrackMenu'
import { WavyPlayBar } from './WavyPlayBar'

type Props = {
  displayName: string
  avatarUrl: string | null
  userId: number | null
}

const LIBRARY_LINKS = [
  { to: '/player', label: 'Home', icon: IconHome, end: true },
  { to: '/player/playlists/recently-added', label: 'Recently Added', icon: IconQueue },
  { to: '/player/history', label: 'History', icon: IconQueue },
  { to: '/player/stats', label: 'Stats', icon: IconMusic },
  { to: '/player/artists', label: 'Artists', icon: IconUser },
  { to: '/player/albums', label: 'Albums', icon: IconLibrary },
  { to: '/player/songs', label: 'Songs', icon: IconMusic },
]

export function PlayerLayout({ displayName, avatarUrl, userId }: Props) {
  const qc = useQueryClient()
  const navigate = useNavigate()
  const location = useLocation()
  const toast = useToast()
  const fileRef = useRef<HTMLInputElement | null>(null)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [createOpen, setCreateOpen] = useState(false)
  const [plName, setPlName] = useState('')
  const [plSmart, setPlSmart] = useState(false)
  const [currentPw, setCurrentPw] = useState('')
  const [newPw, setNewPw] = useState('')
  const [pwMsg, setPwMsg] = useState<string | null>(null)
  const [searchTerm, setSearchTerm] = useState('')
  const [avatarVersion, setAvatarVersion] = useState(0)

  const prefsQ = useQuery({ queryKey: ['player-prefs'], queryFn: playerApi.prefs })
  const prefs = prefsQ.data || DEFAULT_PREFS
  const playlists = useQuery({ queryKey: ['player-playlists'], queryFn: playerApi.playlists })
  const shares = useQuery({
    queryKey: ['player-shares'],
    queryFn: playerApi.listShares,
    enabled: settingsOpen,
    retry: false,
  })
  const lastfm = useQuery({
    queryKey: ['player-lastfm-status'],
    queryFn: playerApi.lastfmStatus,
    enabled: settingsOpen,
    retry: false,
  })
  const connectLastfm = useMutation({
    mutationFn: playerApi.lastfmStart,
    onSuccess: (data) => {
      const cb = `${window.location.origin}/player?lastfm_token=1`
      window.location.href = `${data.auth_url}&cb=${encodeURIComponent(cb)}`
    },
    onError: (err: Error) => toast.push(err.message, 'error'),
  })
  const disconnectLastfm = useMutation({
    mutationFn: playerApi.lastfmDisconnect,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['player-lastfm-status'] }),
  })
  const completeLastfm = useMutation({
    mutationFn: playerApi.lastfmCallback,
    onSuccess: (data) => {
      toast.push(
        data.username ? `Connected to Last.fm as ${data.username}` : 'Connected to Last.fm',
        'ok'
      )
      qc.invalidateQueries({ queryKey: ['player-lastfm-status'] })
    },
    onError: (err: Error) => toast.push(err.message, 'error'),
  })
  useEffect(() => {
    const params = new URLSearchParams(location.search)
    const token = params.get('token')
    if (params.get('lastfm_token') && token) {
      completeLastfm.mutate(token)
      navigate(location.pathname, { replace: true })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.search])
  const [installPrompt, setInstallPrompt] = useState<any>(null)
  useEffect(() => {
    const onPrompt = (e: Event) => {
      e.preventDefault()
      setInstallPrompt(e)
    }
    const onInstalled = () => setInstallPrompt(null)
    window.addEventListener('beforeinstallprompt', onPrompt)
    window.addEventListener('appinstalled', onInstalled)
    return () => {
      window.removeEventListener('beforeinstallprompt', onPrompt)
      window.removeEventListener('appinstalled', onInstalled)
    }
  }, [])

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
  const uploadAvatar = useMutation({
    mutationFn: (file: File) => playerApi.uploadAvatar(file),
    onSuccess: () => {
      toast.push('Photo updated', 'ok')
      setAvatarVersion((v) => v + 1)
      qc.invalidateQueries({ queryKey: ['player-status'] })
    },
    onError: (err) => toast.push((err as Error).message, 'error'),
  })
  const removeAvatar = useMutation({
    mutationFn: playerApi.deleteAvatar,
    onSuccess: () => {
      toast.push('Photo removed', 'ok')
      qc.invalidateQueries({ queryKey: ['player-status'] })
    },
    onError: (err) => toast.push((err as Error).message, 'error'),
  })
  const revokeShare = useMutation({
    mutationFn: (token: string) => playerApi.revokeShare(token),
    onSuccess: () => {
      toast.push('Share revoked', 'ok')
      qc.invalidateQueries({ queryKey: ['player-shares'] })
    },
    onError: (err) => toast.push((err as Error).message, 'error'),
  })

  function patchPref<K extends keyof PlayerPrefs>(key: K, value: PlayerPrefs[K]) {
    const next = { ...prefs, [key]: value }
    qc.setQueryData(['player-prefs'], next)
    savePrefs.mutate({ [key]: value })
  }

  function togglePin(playlistId: number) {
    const pinned = prefs.pinned_playlist_ids || []
    const next = pinned.includes(playlistId)
      ? pinned.filter((id) => id !== playlistId)
      : [...pinned, playlistId]
    patchPref('pinned_playlist_ids', next)
  }

  function onAvatarPicked(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (file) uploadAvatar.mutate(file)
    e.target.value = ''
  }

  const pinned = prefs.pinned_playlist_ids || []
  const sortedPlaylists = [...(playlists.data || [])].sort((a, b) => {
    const aPinned = pinned.includes(Number(a.id)) ? 0 : 1
    const bPinned = pinned.includes(Number(b.id)) ? 0 : 1
    if (aPinned !== bPinned) return aPinned - bPinned
    return a.name.localeCompare(b.name)
  })

  // Avatar URLs are stable per user, so bump a version after uploads to dodge the image cache.
  const avatar =
    avatarUrl && userId != null ? `${playerApi.avatarUrl(userId)}?v=${avatarVersion}` : avatarUrl

  function goBack() {
    if (location.key !== 'default') navigate(-1)
    else navigate('/player')
  }

  return (
    <div className="player-shell">
      <aside className="player-sidebar">
        <div className="player-sidebar-brand">
          <div className="brand">
            Music<span>arr</span>
          </div>
          <span className="player-tag">Player</span>
        </div>

        <form
          className="player-sidebar-search"
          onSubmit={(e: FormEvent) => {
            e.preventDefault()
            navigate(`/player/search?q=${encodeURIComponent(searchTerm.trim())}`)
          }}
        >
          <IconSearch size={16} />
          <input
            type="search"
            placeholder="Search"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            onFocus={() => {
              if (!location.pathname.startsWith('/player/search')) navigate('/player/search')
            }}
          />
        </form>

        <nav className="player-side-nav">
          <div className="player-side-label">Library</div>
          {LIBRARY_LINKS.map(({ to, label, icon: Icon, end }) => (
            <NavLink key={to} to={to} end={end}>
              <Icon size={17} />
              {label}
            </NavLink>
          ))}
        </nav>

        <nav className="player-side-nav playlists">
          <div className="player-side-label">
            Playlists
            <button
              type="button"
              className="pill-icon-btn small"
              aria-label="Create playlist"
              onClick={() => setCreateOpen(true)}
            >
              <IconPlus size={14} />
            </button>
          </div>
          <NavLink to="/player/playlists/liked">
            <IconHeart filled size={16} />
            Liked Songs
          </NavLink>
          {sortedPlaylists.map((pl) => (
            <NavLink key={pl.id} to={`/player/playlists/${pl.id}`}>
              <IconMusic size={16} />
              <span className="truncate">{pl.name}</span>
              {pinned.includes(Number(pl.id)) && <span className="pin-dot" aria-label="Pinned" />}
            </NavLink>
          ))}
          <NavLink to="/player/playlists" end className="player-side-all">
            All playlists
          </NavLink>
        </nav>

        <div className="player-user-chip">
          <span className="player-avatar">
            {avatar ? <img src={avatar} alt="" /> : <IconUser size={18} />}
          </span>
          <span className="truncate">{displayName}</span>
          <button
            type="button"
            className="pill-icon-btn small"
            aria-label="Settings"
            onClick={() => setSettingsOpen(true)}
          >
            <IconSettings size={16} />
          </button>
          <button
            type="button"
            className="pill-icon-btn small"
            aria-label="Sign out"
            title="Sign out"
            onClick={() => logout.mutate()}
            disabled={logout.isPending}
          >
            <IconClose size={16} />
          </button>
        </div>
      </aside>

      <div className="player-content">
        <div className="player-content-top">
          <button type="button" className="pill-icon-btn" aria-label="Back" onClick={goBack}>
            <IconBack size={18} />
          </button>
          <button
            type="button"
            className="pill-icon-btn"
            aria-label="Forward"
            onClick={() => navigate(1)}
          >
            <IconForward size={18} />
          </button>
        </div>
        <main className="player-main">
          <Outlet />
        </main>
      </div>

      <nav className="player-bottom-tabs">
        <NavLink to="/player" end>
          <IconHome size={20} />
          Home
        </NavLink>
        <NavLink to="/player/search">
          <IconSearch size={20} />
          Search
        </NavLink>
        <NavLink to="/player/albums">
          <IconLibrary size={20} />
          Library
        </NavLink>
        <NavLink to="/player/playlists" end>
          <IconMusic size={20} />
          Playlists
        </NavLink>
      </nav>

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
          <div className="player-modal wide scroll" onClick={(e) => e.stopPropagation()}>
            <div className="player-modal-head">
              <h2>Personal settings</h2>
              <button type="button" className="pill-icon-btn" onClick={() => setSettingsOpen(false)}>
                <IconClose size={18} />
              </button>
            </div>

            <h3>Profile photo</h3>
            <div className="avatar-row">
              <span className="player-avatar lg">
                {avatar ? <img src={avatar} alt="" /> : <IconUser size={28} />}
              </span>
              <div className="toolbar">
                <button
                  type="button"
                  className="btn secondary"
                  onClick={() => fileRef.current?.click()}
                  disabled={uploadAvatar.isPending}
                >
                  {avatar ? 'Change photo' : 'Upload photo'}
                </button>
                {avatar && (
                  <button
                    type="button"
                    className="btn ghost"
                    onClick={() => removeAvatar.mutate()}
                    disabled={removeAvatar.isPending}
                  >
                    Remove
                  </button>
                )}
                <input
                  ref={fileRef}
                  type="file"
                  accept="image/jpeg,image/png,image/webp"
                  hidden
                  onChange={onAvatarPicked}
                />
              </div>
            </div>
            <p className="muted tiny" style={{ marginTop: 0 }}>
              JPEG, PNG, or WebP up to 2MB.
            </p>

            <h3>Home shelves</h3>
            <label className="checks">
              <input
                type="checkbox"
                checked={prefs.show_recommended}
                onChange={(e) => patchPref('show_recommended', e.target.checked)}
              />
              Show Recommended for you
            </label>
            <label className="checks">
              <input
                type="checkbox"
                checked={prefs.show_recently_added}
                onChange={(e) => patchPref('show_recently_added', e.target.checked)}
              />
              Show Recently Added
            </label>
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

            <h3>Playback</h3>
            <label className="checks">
              <input
                type="checkbox"
                checked={prefs.crossfade_enabled}
                onChange={(e) => patchPref('crossfade_enabled', e.target.checked)}
              />
              Crossfade between tracks
            </label>
            <label className="checks">
              <input
                type="checkbox"
                checked={prefs.default_shuffle}
                onChange={(e) => patchPref('default_shuffle', e.target.checked)}
              />
              Start new sessions with shuffle on
            </label>
            <div className="field">
              <label>Default repeat</label>
              <select
                value={prefs.default_repeat}
                onChange={(e) => patchPref('default_repeat', e.target.value as PlayerRepeatMode)}
              >
                <option value="off">Off</option>
                <option value="all">Repeat all</option>
                <option value="one">Repeat one</option>
              </select>
            </div>

            <h3>Last.fm</h3>
            {lastfm.data?.connected ? (
              <div className="toolbar" style={{ alignItems: 'center', gap: '0.75rem' }}>
                <span className="muted">Connected as {lastfm.data.username}</span>
                <button
                  type="button"
                  className="btn ghost"
                  onClick={() => disconnectLastfm.mutate()}
                  disabled={disconnectLastfm.isPending}
                >
                  Disconnect
                </button>
              </div>
            ) : (
              <div className="toolbar" style={{ alignItems: 'center', gap: '0.75rem' }}>
                <span className="muted tiny">Scrobble what you play to your Last.fm account.</span>
                <button
                  type="button"
                  className="btn secondary"
                  onClick={() => connectLastfm.mutate()}
                  disabled={connectLastfm.isPending}
                >
                  Connect Last.fm
                </button>
              </div>
            )}

            {installPrompt && (
              <>
                <h3>Install app</h3>
                <div className="toolbar" style={{ alignItems: 'center', gap: '0.75rem' }}>
                  <span className="muted tiny">Install the player as an app on this device.</span>
                  <button
                    type="button"
                    className="btn secondary"
                    onClick={async () => {
                      installPrompt.prompt()
                      await installPrompt.userChoice
                      setInstallPrompt(null)
                    }}
                  >
                    Install app
                  </button>
                </div>
              </>
            )}

            <h3>Pinned playlists</h3>
            <p className="muted tiny" style={{ marginTop: 0 }}>
              Pinned playlists sort to the top of the sidebar.
            </p>
            <div className="pin-list">
              {sortedPlaylists.map((pl) => (
                <label key={pl.id} className="checks">
                  <input
                    type="checkbox"
                    checked={pinned.includes(Number(pl.id))}
                    onChange={() => togglePin(Number(pl.id))}
                  />
                  {pl.name}
                </label>
              ))}
              {!sortedPlaylists.length && <span className="muted tiny">No playlists yet.</span>}
            </div>

            <h3>Shared songs</h3>
            {shares.isLoading && <p className="muted tiny">Loading…</p>}
            {shares.isError && <p className="muted tiny">{(shares.error as Error).message}</p>}
            {shares.isSuccess && !shares.data.length && (
              <p className="muted tiny" style={{ marginTop: 0 }}>
                You haven’t shared anything yet.
              </p>
            )}
            <div className="share-list">
              {shares.data?.map((s) => (
                <div key={s.token} className={`share-row${s.revoked ? ' revoked' : ''}`}>
                  <div className="share-meta">
                    <strong>{s.track_title}</strong>
                    <span className="muted tiny">
                      {s.artist_name} · {s.play_count} play{s.play_count === 1 ? '' : 's'}
                      {s.revoked ? ' · revoked' : ''}
                    </span>
                  </div>
                  {!s.revoked && (
                    <>
                      <button
                        type="button"
                        className="btn ghost"
                        onClick={async () => {
                          const url = playerApi.sharePageUrl(s.token)
                          const ok = await copyToClipboard(url)
                          toast.push(ok ? 'Link copied' : url, 'ok')
                        }}
                      >
                        Copy
                      </button>
                      <button
                        type="button"
                        className="btn ghost danger"
                        onClick={() => revokeShare.mutate(s.token)}
                        disabled={revokeShare.isPending}
                      >
                        Revoke
                      </button>
                    </>
                  )}
                </div>
              ))}
            </div>

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

            <h3>Keyboard shortcuts</h3>
            <p className="muted tiny" style={{ marginTop: 0 }}>
              Space play/pause · ← → seek 5s · ↑ ↓ volume · N/P next/previous · S shuffle · R
              repeat · M mute · F expand · L love · Q queue
            </p>
          </div>
        </div>
      )}
    </div>
  )
}
