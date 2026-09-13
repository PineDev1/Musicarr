import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { playerApi } from '../player/playerApi'
import { useToast } from '../Toast'
import { AcquisitionPanels } from './AcquisitionPanels'

type TabId =
  | 'sources'
  | 'library'
  | 'downloads'
  | 'indexers'
  | 'clients'
  | 'paths'
  | 'notifications'
  | 'media'
  | 'security'
  | 'player'
  | 'tools'

const TABS: { id: TabId; label: string }[] = [
  { id: 'sources', label: 'Sources' },
  { id: 'library', label: 'Library' },
  { id: 'downloads', label: 'Downloads' },
  { id: 'indexers', label: 'Indexers' },
  { id: 'clients', label: 'Download clients' },
  { id: 'paths', label: 'Path mappings' },
  { id: 'notifications', label: 'Notifications' },
  { id: 'media', label: 'Media servers' },
  { id: 'security', label: 'Security' },
  { id: 'player', label: 'Player' },
  { id: 'tools', label: 'Tools' },
]

function traefikLabels(domainRaw: string): string {
  let host = (domainRaw || '').trim()
  if (!host) host = 'music.example.com'
  if (host.includes('://')) {
    try {
      host = new URL(host).hostname
    } catch {
      host = host.replace(/^https?:\/\//i, '').split('/')[0]
    }
  } else {
    host = host.split('/')[0]
  }
  host = host.toLowerCase() || 'music.example.com'
  return [
    'traefik.enable=true',
    `traefik.http.routers.musicarr.rule=Host(\`${host}\`)`,
    'traefik.http.routers.musicarr.entrypoints=websecure',
    'traefik.http.routers.musicarr.tls=true',
    'traefik.http.routers.musicarr.tls.certresolver=letsencrypt',
    'traefik.http.services.musicarr.loadbalancer.server.port=8787',
  ].join('\n')
}

export function SettingsPage() {
  const qc = useQueryClient()
  const toast = useToast()
  const [tab, setTab] = useState<TabId>('sources')
  const { data, isLoading, error } = useQuery({
    queryKey: ['settings'],
    queryFn: () => api.settings(true),
  })
  const { data: authStatus } = useQuery({
    queryKey: ['auth-status'],
    queryFn: api.authStatus,
  })

  const [arl, setArl] = useState('')
  const [activeProvider, setActiveProvider] = useState('deezer')
  const [libraryPath, setLibraryPath] = useState('')
  const [bitrate, setBitrate] = useState('flac')
  const [folderTemplate, setFolderTemplate] = useState('{artist}/{album} ({year})')
  const [trackTemplate, setTrackTemplate] = useState('{track:02d} - {title}')
  const [interval, setIntervalMinutes] = useState(60)
  const [maxRetries, setMaxRetries] = useState(3)
  const [includeAlbums, setIncludeAlbums] = useState(true)
  const [includeEps, setIncludeEps] = useState(true)
  const [includeSingles, setIncludeSingles] = useState(false)
  const [includeCompilations, setIncludeCompilations] = useState(false)
  const [minTrackCount, setMinTrackCount] = useState(0)
  const [ignoreJunk, setIgnoreJunk] = useState(true)
  const [ignoreLive, setIgnoreLive] = useState(false)
  const [notifyUrl, setNotifyUrl] = useState('')
  const [notifyComplete, setNotifyComplete] = useState(true)
  const [notifyFailure, setNotifyFailure] = useState(true)
  const [upgradeEnabled, setUpgradeEnabled] = useState(true)
  const [mediaRefreshUrl, setMediaRefreshUrl] = useState('')
  const [mediaRefreshToken, setMediaRefreshToken] = useState('')
  const [mediaRefreshType, setMediaRefreshType] = useState('webhook')
  const [authEnabled, setAuthEnabled] = useState(false)
  const [authUsername, setAuthUsername] = useState('admin')
  const [authPassword, setAuthPassword] = useState('')
  const [authPasswordConfirm, setAuthPasswordConfirm] = useState('')
  const [sslEnabled, setSslEnabled] = useState(false)
  const [publicDomain, setPublicDomain] = useState('')
  const [playerEnabled, setPlayerEnabled] = useState(false)
  const [playerSharingEnabled, setPlayerSharingEnabled] = useState(true)
  const [preferredMethod, setPreferredMethod] = useState('streaming')
  const [importMechanism, setImportMechanism] = useState('hardlink')
  const [scanInterval, setScanInterval] = useState(60)
  const [removeCompleted, setRemoveCompleted] = useState(false)
  const [newPlayerUser, setNewPlayerUser] = useState('')
  const [newPlayerPass, setNewPlayerPass] = useState('')
  const [newPlayerDisplay, setNewPlayerDisplay] = useState('')
  const [resetPassId, setResetPassId] = useState<number | null>(null)
  const [resetPassValue, setResetPassValue] = useState('')
  const [qobuzEmail, setQobuzEmail] = useState('')
  const [qobuzPassword, setQobuzPassword] = useState('')
  const [qobuzToken, setQobuzToken] = useState('')
  const [qobuzUserId, setQobuzUserId] = useState('')
  const [qobuzAppId, setQobuzAppId] = useState('')
  const [qobuzAppSecret, setQobuzAppSecret] = useState('')
  const [tidalCode, setTidalCode] = useState<string | null>(null)
  const [tidalUri, setTidalUri] = useState<string | null>(null)

  useEffect(() => {
    if (!data) return
    setActiveProvider(data.active_provider || 'deezer')
    setLibraryPath(data.library_path)
    setBitrate(data.bitrate)
    setFolderTemplate(data.folder_template)
    setTrackTemplate(data.track_template)
    setIntervalMinutes(data.monitor_interval_minutes)
    setMaxRetries(data.max_retries)
    setIncludeAlbums(data.include_albums)
    setIncludeEps(data.include_eps)
    setIncludeSingles(data.include_singles)
    setIncludeCompilations(data.include_compilations)
    setMinTrackCount(data.min_track_count ?? 0)
    setIgnoreJunk(data.ignore_junk_titles ?? true)
    setIgnoreLive(data.ignore_live_releases ?? false)
    setNotifyUrl(data.notify_webhook_url || '')
    setNotifyComplete(data.notify_on_complete ?? true)
    setNotifyFailure(data.notify_on_failure ?? true)
    setUpgradeEnabled(data.upgrade_enabled ?? true)
    setMediaRefreshUrl(data.media_refresh_url || '')
    setMediaRefreshType(data.media_refresh_type || 'webhook')
    setAuthEnabled(data.auth_enabled ?? false)
    setAuthUsername(data.auth_username || 'admin')
    setSslEnabled(data.ssl_enabled ?? false)
    setPublicDomain(data.public_domain || '')
    setPlayerEnabled(data.player_enabled ?? false)
    setPlayerSharingEnabled(data.player_sharing_enabled ?? true)
    setPreferredMethod(data.preferred_download_method || 'streaming')
    setImportMechanism(data.import_mechanism || 'hardlink')
    setScanInterval(data.completed_download_scan_interval_seconds ?? 60)
    setRemoveCompleted(data.remove_completed_downloads ?? false)
    setQobuzEmail(data.qobuz_email || '')
    setQobuzUserId(data.qobuz_user_id || '')
    setQobuzAppId(data.qobuz_app_id || '950096963')
  }, [data])

  const save = useMutation({
    mutationFn: () => {
      if (authEnabled && authPassword && authPassword !== authPasswordConfirm) {
        throw new Error('Password confirmation does not match')
      }
      if (authEnabled && !data?.auth_password_set && !authPassword.trim()) {
        throw new Error('Set a password before enabling login')
      }
      const body: Record<string, unknown> = {
        active_provider: activeProvider,
        library_path: libraryPath,
        bitrate,
        folder_template: folderTemplate,
        track_template: trackTemplate,
        monitor_interval_minutes: interval,
        max_retries: maxRetries,
        include_albums: includeAlbums,
        include_eps: includeEps,
        include_singles: includeSingles,
        include_compilations: includeCompilations,
        min_track_count: minTrackCount,
        ignore_junk_titles: ignoreJunk,
        ignore_live_releases: ignoreLive,
        notify_webhook_url: notifyUrl.trim(),
        notify_on_complete: notifyComplete,
        notify_on_failure: notifyFailure,
        upgrade_enabled: upgradeEnabled,
        media_refresh_url: mediaRefreshUrl.trim(),
        media_refresh_type: mediaRefreshType,
        auth_enabled: authEnabled,
        auth_username: authUsername.trim() || 'admin',
        ssl_enabled: sslEnabled,
        public_domain: publicDomain.trim(),
        player_enabled: playerEnabled,
        player_sharing_enabled: playerSharingEnabled,
        preferred_download_method: preferredMethod,
        import_mechanism: importMechanism,
        completed_download_scan_interval_seconds: scanInterval,
        remove_completed_downloads: removeCompleted,
        qobuz_app_id: qobuzAppId,
      }
      if (arl.trim()) body.arl = arl.trim()
      if (qobuzAppSecret.trim()) body.qobuz_app_secret = qobuzAppSecret.trim()
      if (mediaRefreshToken.trim()) body.media_refresh_token = mediaRefreshToken.trim()
      if (authPassword.trim()) body.auth_password = authPassword.trim()
      return api.updateSettings(body)
    },
    onSuccess: () => {
      setArl('')
      setQobuzAppSecret('')
      setMediaRefreshToken('')
      setAuthPassword('')
      setAuthPasswordConfirm('')
      toast.push('Settings saved', 'ok')
      qc.invalidateQueries({ queryKey: ['settings'] })
      qc.invalidateQueries({ queryKey: ['health'] })
      qc.invalidateQueries({ queryKey: ['auth-status'] })
    },
    onError: (err) => toast.push((err as Error).message, 'error'),
  })

  const logout = useMutation({
    mutationFn: (provider: string) => api.logout(provider),
    onSuccess: (_res, provider) => {
      toast.push(`Logged out of ${provider}`, 'ok')
      setTidalCode(null)
      setTidalUri(null)
      qc.invalidateQueries({ queryKey: ['settings'] })
      qc.invalidateQueries({ queryKey: ['health'] })
    },
    onError: (err) => toast.push((err as Error).message, 'error'),
  })

  const appLogout = useMutation({
    mutationFn: api.appLogout,
    onSuccess: () => {
      toast.push('Signed out', 'ok')
      qc.invalidateQueries({ queryKey: ['auth-status'] })
    },
    onError: (err) => toast.push((err as Error).message, 'error'),
  })

  const tidalStart = useMutation({
    mutationFn: api.tidalDeviceStart,
    onSuccess: (res) => {
      setTidalCode(res.user_code)
      setTidalUri(res.verification_uri_complete || res.verification_uri)
      toast.push('Open the Tidal link and enter the code', 'info')
    },
    onError: (err) => toast.push((err as Error).message, 'error'),
  })

  const qobuzTokenLogin = useMutation({
    mutationFn: () =>
      api.qobuzTokenLogin({
        token: qobuzToken,
        user_id: qobuzUserId,
        app_id: qobuzAppId,
        app_secret: qobuzAppSecret,
      }),
    onSuccess: () => {
      setQobuzToken('')
      setQobuzAppSecret('')
      toast.push('Logged in to Qobuz', 'ok')
      qc.invalidateQueries({ queryKey: ['settings'] })
      qc.invalidateQueries({ queryKey: ['health'] })
    },
    onError: (err) => toast.push((err as Error).message, 'error'),
  })

  const qobuzLogin = useMutation({
    mutationFn: () => api.qobuzLogin(qobuzEmail, qobuzPassword),
    onSuccess: () => {
      setQobuzPassword('')
      toast.push('Logged in to Qobuz', 'ok')
      qc.invalidateQueries({ queryKey: ['settings'] })
      qc.invalidateQueries({ queryKey: ['health'] })
    },
    onError: (err) => toast.push((err as Error).message, 'error'),
  })

  useEffect(() => {
    if (!tidalCode) return
    const id = window.setInterval(async () => {
      try {
        const status = await api.tidalDeviceStatus()
        if (status.status === 'authenticated') {
          setTidalCode(null)
          setTidalUri(null)
          toast.push('Logged in to Tidal', 'ok')
          qc.invalidateQueries({ queryKey: ['settings'] })
          qc.invalidateQueries({ queryKey: ['health'] })
        } else if (status.status === 'error') {
          toast.push(status.error || 'Tidal login failed', 'error')
          setTidalCode(null)
        }
      } catch {
        /* ignore poll errors */
      }
    }, 2500)
    return () => window.clearInterval(id)
  }, [tidalCode, qc, toast])

  const scan = useMutation({
    mutationFn: api.scan,
    onSuccess: (res) => toast.push(res.message, 'ok'),
    onError: (err) => toast.push((err as Error).message, 'error'),
  })
  const importLib = useMutation({
    mutationFn: () => api.importLibrary(true),
    onSuccess: (res) => {
      toast.push(res.message, 'ok')
      qc.invalidateQueries({ queryKey: ['artists'] })
      qc.invalidateQueries({ queryKey: ['wanted'] })
      qc.invalidateQueries({ queryKey: ['health'] })
      qc.invalidateQueries({ queryKey: ['import-review'] })
      qc.invalidateQueries({ queryKey: ['upgradable'] })
    },
    onError: (err) => toast.push((err as Error).message, 'error'),
  })
  const reorganize = useMutation({
    mutationFn: api.reorganize,
    onSuccess: (res) => toast.push(res.message, 'ok'),
    onError: (err) => toast.push((err as Error).message, 'error'),
  })
  const monitor = useMutation({
    mutationFn: api.runMonitor,
    onSuccess: (res) =>
      toast.push(`Monitor: ${res.artists_checked} artists, ${res.new_albums} new`, 'ok'),
    onError: (err) => toast.push((err as Error).message, 'error'),
  })

  const playerUsers = useQuery({
    queryKey: ['player-users'],
    queryFn: playerApi.users,
    enabled: tab === 'player',
    retry: false,
  })
  const createPlayerUser = useMutation({
    mutationFn: () =>
      playerApi.createUser({
        username: newPlayerUser.trim(),
        password: newPlayerPass,
        display_name: newPlayerDisplay.trim() || undefined,
      }),
    onSuccess: () => {
      setNewPlayerUser('')
      setNewPlayerPass('')
      setNewPlayerDisplay('')
      toast.push('Player user created', 'ok')
      qc.invalidateQueries({ queryKey: ['player-users'] })
    },
    onError: (err) => toast.push((err as Error).message, 'error'),
  })
  const updatePlayerUser = useMutation({
    mutationFn: ({ id, body }: { id: number; body: Record<string, unknown> }) =>
      playerApi.updateUser(id, body),
    onSuccess: () => {
      setResetPassId(null)
      setResetPassValue('')
      toast.push('Player user updated', 'ok')
      qc.invalidateQueries({ queryKey: ['player-users'] })
    },
    onError: (err) => toast.push((err as Error).message, 'error'),
  })
  const deletePlayerUser = useMutation({
    mutationFn: (id: number) => playerApi.deleteUser(id),
    onSuccess: () => {
      toast.push('Player user deleted', 'ok')
      qc.invalidateQueries({ queryKey: ['player-users'] })
    },
    onError: (err) => toast.push((err as Error).message, 'error'),
  })

  function onSubmit(e: FormEvent) {
    e.preventDefault()
    if (tab === 'tools') return
    save.mutate()
  }

  if (isLoading) return <p className="muted">Loading…</p>
  if (error) return <p className="error">{(error as Error).message}</p>

  return (
    <div>
      <div className="page-header">
        <div>
          <h1>Settings</h1>
          <p>Configure sources, library behavior, and access.</p>
        </div>
      </div>

      {data && data.provider_ok === false && tab === 'sources' && (
        <div className="banner warn">
          {data.provider_error || 'Active provider is not connected.'}
        </div>
      )}

      <div className="settings-tabs" role="tablist" aria-label="Settings groups">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            role="tab"
            aria-selected={tab === t.id}
            className={`settings-tab${tab === t.id ? ' active' : ''}`}
            onClick={() => setTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </div>

      <form className="form-grid settings-panel" onSubmit={onSubmit}>
        {tab === 'sources' && (
          <>
            <div className="field">
              <label>Active download source</label>
              <select
                value={activeProvider}
                onChange={(e) => {
                  const next = e.target.value
                  setActiveProvider(next)
                  api
                    .updateSettings({ active_provider: next })
                    .then(() => {
                      toast.push(`Active source set to ${next}`, 'ok')
                      qc.invalidateQueries({ queryKey: ['settings'] })
                      qc.invalidateQueries({ queryKey: ['health'] })
                      qc.invalidateQueries({ queryKey: ['wanted'] })
                    })
                    .catch((err) => toast.push((err as Error).message, 'error'))
                }}
              >
                <option value="deezer">Deezer</option>
                <option value="tidal">Tidal</option>
                <option value="qobuz">Qobuz</option>
              </select>
            </div>

            <div className="provider-card">
              <div className="provider-card-head">
                <h3>Deezer</h3>
                <span className={`badge ${data?.deezer_ok ? 'downloaded' : 'failed'}`}>
                  {data?.deezer_ok ? 'connected' : 'offline'}
                </span>
              </div>
              <div className="field">
                <label>ARL {data?.arl_set ? `(current ${data.arl_masked})` : ''}</label>
                <input
                  type="password"
                  placeholder={data?.arl_set ? 'Leave blank to keep current ARL' : 'Paste ARL cookie'}
                  value={arl}
                  onChange={(e) => setArl(e.target.value)}
                  autoComplete="off"
                />
              </div>
              {data?.arl_set && (
                <button
                  type="button"
                  className="btn ghost"
                  onClick={() => logout.mutate('deezer')}
                  disabled={logout.isPending}
                >
                  Logout Deezer
                </button>
              )}
            </div>

            <div className="provider-card">
              <div className="provider-card-head">
                <h3>Tidal</h3>
                <span className={`badge ${data?.tidal_ok ? 'downloaded' : 'failed'}`}>
                  {data?.tidal_ok ? 'connected' : 'offline'}
                </span>
              </div>
              <p className="muted">Log in with a device code (link.tidal.com).</p>
              <div className="toolbar">
                <button
                  type="button"
                  className="btn secondary"
                  onClick={() => tidalStart.mutate()}
                  disabled={tidalStart.isPending}
                >
                  {tidalStart.isPending ? 'Starting…' : 'Login with Tidal'}
                </button>
                {data?.tidal_logged_in && (
                  <button
                    type="button"
                    className="btn ghost"
                    onClick={() => logout.mutate('tidal')}
                    disabled={logout.isPending}
                  >
                    Logout Tidal
                  </button>
                )}
              </div>
              {tidalCode && (
                <div className="banner">
                  Code: <strong>{tidalCode}</strong>
                  {tidalUri && (
                    <>
                      {' '}
                      — open{' '}
                      <a href={tidalUri} target="_blank" rel="noreferrer">
                        {tidalUri}
                      </a>
                    </>
                  )}
                </div>
              )}
            </div>

            <div className="provider-card">
              <div className="provider-card-head">
                <h3>Qobuz</h3>
                <span className={`badge ${data?.qobuz_ok ? 'downloaded' : 'failed'}`}>
                  {data?.qobuz_ok ? 'connected' : 'offline'}
                </span>
              </div>
              <p className="muted">
                Same as QobuzDownloaderX: paste your <strong>token</strong>, <strong>user ID</strong>,{' '}
                <strong>app ID</strong>, and <strong>app secret</strong>.
              </p>
              <div className="field">
                <label>Token {data?.qobuz_token_set ? '(saved)' : ''}</label>
                <input
                  type="password"
                  placeholder={data?.qobuz_token_set ? 'Leave blank unless replacing' : 'Paste Qobuz token'}
                  value={qobuzToken}
                  onChange={(e) => setQobuzToken(e.target.value)}
                  autoComplete="off"
                />
              </div>
              <div className="field">
                <label>User ID</label>
                <input type="text" value={qobuzUserId} onChange={(e) => setQobuzUserId(e.target.value)} />
              </div>
              <div className="field">
                <label>App ID</label>
                <input type="text" value={qobuzAppId} onChange={(e) => setQobuzAppId(e.target.value)} />
              </div>
              <div className="field">
                <label>App secret {data?.qobuz_app_secret_set ? '(saved)' : ''}</label>
                <input
                  type="password"
                  placeholder={data?.qobuz_app_secret_set ? 'Leave blank to keep' : 'Paste app secret'}
                  value={qobuzAppSecret}
                  onChange={(e) => setQobuzAppSecret(e.target.value)}
                  autoComplete="off"
                />
              </div>
              <div className="toolbar">
                <button
                  type="button"
                  className="btn secondary"
                  onClick={() => qobuzTokenLogin.mutate()}
                  disabled={qobuzTokenLogin.isPending || (!qobuzToken && !data?.qobuz_token_set)}
                >
                  {qobuzTokenLogin.isPending ? 'Connecting…' : 'Connect with token'}
                </button>
                {data?.qobuz_logged_in && (
                  <button
                    type="button"
                    className="btn ghost"
                    onClick={() => logout.mutate('qobuz')}
                    disabled={logout.isPending}
                  >
                    Logout Qobuz
                  </button>
                )}
              </div>

              <details>
                <summary className="muted">Alternate: email / password</summary>
                <div className="field" style={{ marginTop: '0.75rem' }}>
                  <label>Email</label>
                  <input type="text" value={qobuzEmail} onChange={(e) => setQobuzEmail(e.target.value)} />
                </div>
                <div className="field">
                  <label>Password</label>
                  <input
                    type="password"
                    value={qobuzPassword}
                    onChange={(e) => setQobuzPassword(e.target.value)}
                    autoComplete="off"
                  />
                </div>
                <button
                  type="button"
                  className="btn ghost"
                  onClick={() => qobuzLogin.mutate()}
                  disabled={qobuzLogin.isPending || !qobuzEmail || !qobuzPassword}
                >
                  {qobuzLogin.isPending ? 'Logging in…' : 'Login with email'}
                </button>
              </details>
            </div>
          </>
        )}

        {tab === 'library' && (
          <>
            <div className="field">
              <label>Library path</label>
              <input type="text" value={libraryPath} onChange={(e) => setLibraryPath(e.target.value)} />
            </div>
            <div className="field">
              <label>Folder template</label>
              <input type="text" value={folderTemplate} onChange={(e) => setFolderTemplate(e.target.value)} />
            </div>
            <div className="field">
              <label>Track template</label>
              <input type="text" value={trackTemplate} onChange={(e) => setTrackTemplate(e.target.value)} />
            </div>
            <div className="field">
              <label>Release types to import</label>
              <div className="checks">
                <label>
                  <input type="checkbox" checked={includeAlbums} onChange={(e) => setIncludeAlbums(e.target.checked)} />
                  Albums
                </label>
                <label>
                  <input type="checkbox" checked={includeEps} onChange={(e) => setIncludeEps(e.target.checked)} />
                  EPs
                </label>
                <label>
                  <input
                    type="checkbox"
                    checked={includeSingles}
                    onChange={(e) => setIncludeSingles(e.target.checked)}
                  />
                  Singles
                </label>
                <label>
                  <input
                    type="checkbox"
                    checked={includeCompilations}
                    onChange={(e) => setIncludeCompilations(e.target.checked)}
                  />
                  Compilations
                </label>
              </div>
            </div>
            <div className="field">
              <label>Skip junk titles</label>
              <div className="checks">
                <label>
                  <input type="checkbox" checked={ignoreJunk} onChange={(e) => setIgnoreJunk(e.target.checked)} />
                  Ignore junk titles on import
                </label>
                <label>
                  <input type="checkbox" checked={ignoreLive} onChange={(e) => setIgnoreLive(e.target.checked)} />
                  Ignore live releases on import
                </label>
              </div>
            </div>
            <div className="field">
              <label>Minimum tracks (albums/EPs; 0 = off)</label>
              <input
                type="number"
                min={0}
                max={100}
                value={minTrackCount}
                onChange={(e) => setMinTrackCount(Number(e.target.value))}
              />
            </div>
          </>
        )}

        {tab === 'downloads' && (
          <>
            <div className="field">
              <label>Quality</label>
              <select value={bitrate} onChange={(e) => setBitrate(e.target.value)}>
                <option value="flac">FLAC</option>
                <option value="320">MP3 320</option>
                <option value="128">MP3 128</option>
              </select>
            </div>
            <div className="field">
              <label>Quality upgrades</label>
              <div className="checks">
                <label>
                  <input
                    type="checkbox"
                    checked={upgradeEnabled}
                    onChange={(e) => setUpgradeEnabled(e.target.checked)}
                  />
                  Flag albums below target quality and allow Upgrade all
                </label>
              </div>
            </div>
            <div className="field">
              <label>Monitor interval (minutes)</label>
              <input
                type="number"
                min={5}
                value={interval}
                onChange={(e) => setIntervalMinutes(Number(e.target.value))}
              />
            </div>
            <div className="field">
              <label>Max download retries</label>
              <input
                type="number"
                min={0}
                max={10}
                value={maxRetries}
                onChange={(e) => setMaxRetries(Number(e.target.value))}
              />
            </div>
            <div className="field">
              <label>Preferred download method</label>
              <select value={preferredMethod} onChange={(e) => setPreferredMethod(e.target.value)}>
                <option value="streaming">Streaming provider (Deezer / Tidal / Qobuz)</option>
                <option value="indexer">Indexers → download client</option>
                <option value="streaming_then_indexer">Streaming, then indexer on failure</option>
              </select>
            </div>
            <div className="field">
              <label>Import mechanism (indexer downloads)</label>
              <select value={importMechanism} onChange={(e) => setImportMechanism(e.target.value)}>
                <option value="hardlink">Hardlink (best for seeding)</option>
                <option value="copy">Copy</option>
                <option value="move">Move (breaks torrents)</option>
              </select>
            </div>
            <div className="field">
              <label>Completed download scan interval (seconds)</label>
              <input
                type="number"
                min={15}
                max={3600}
                value={scanInterval}
                onChange={(e) => setScanInterval(Number(e.target.value))}
              />
            </div>
            <label className="checks">
              <input
                type="checkbox"
                checked={removeCompleted}
                onChange={(e) => setRemoveCompleted(e.target.checked)}
              />
              Remove from download client after import
            </label>
          </>
        )}

        {tab === 'indexers' && <AcquisitionPanels panel="indexers" />}
        {tab === 'clients' && <AcquisitionPanels panel="clients" />}
        {tab === 'paths' && <AcquisitionPanels panel="paths" />}

        {tab === 'notifications' && (
          <>
            <div className="field">
              <label>Notification webhook URL (Discord or generic)</label>
              <input
                type="url"
                placeholder="https://discord.com/api/webhooks/…"
                value={notifyUrl}
                onChange={(e) => setNotifyUrl(e.target.value)}
              />
            </div>
            <div className="field">
              <label>Notify when</label>
              <div className="checks">
                <label>
                  <input
                    type="checkbox"
                    checked={notifyComplete}
                    onChange={(e) => setNotifyComplete(e.target.checked)}
                  />
                  Download complete
                </label>
                <label>
                  <input
                    type="checkbox"
                    checked={notifyFailure}
                    onChange={(e) => setNotifyFailure(e.target.checked)}
                  />
                  Download / auth failure
                </label>
              </div>
            </div>
          </>
        )}

        {tab === 'media' && (
          <>
            <div className="field">
              <label>Media server refresh</label>
              <select value={mediaRefreshType} onChange={(e) => setMediaRefreshType(e.target.value)}>
                <option value="webhook">Generic webhook</option>
                <option value="plex">Plex</option>
                <option value="jellyfin">Jellyfin</option>
                <option value="navidrome">Navidrome</option>
              </select>
            </div>
            <div className="field">
              <label>Media refresh URL</label>
              <input
                type="url"
                placeholder={
                  mediaRefreshType === 'jellyfin'
                    ? 'https://jellyfin.example'
                    : mediaRefreshType === 'plex'
                      ? 'http://plex:32400/library/sections/X/refresh'
                      : 'https://…'
                }
                value={mediaRefreshUrl}
                onChange={(e) => setMediaRefreshUrl(e.target.value)}
              />
            </div>
            <div className="field">
              <label>Media refresh token {data?.media_refresh_token_set ? '(saved)' : ''}</label>
              <input
                type="password"
                placeholder={
                  data?.media_refresh_token_set ? 'Leave blank to keep' : 'Optional API token'
                }
                value={mediaRefreshToken}
                onChange={(e) => setMediaRefreshToken(e.target.value)}
                autoComplete="off"
              />
            </div>
          </>
        )}

        {tab === 'security' && (
          <>
            <h3 style={{ margin: '0 0 0.25rem', fontSize: '1.05rem' }}>App login</h3>
            <p className="muted" style={{ marginTop: 0, maxWidth: 560 }}>
              Optional form login for Musicarr itself. When enabled, the UI and API require a
              username and password. Leave disabled for LAN-only use.
            </p>
            <div className="field">
              <label>App login</label>
              <div className="checks">
                <label>
                  <input
                    type="checkbox"
                    checked={authEnabled}
                    onChange={(e) => setAuthEnabled(e.target.checked)}
                  />
                  Require login to open Musicarr
                </label>
              </div>
            </div>
            <div className="field">
              <label>Username</label>
              <input
                type="text"
                value={authUsername}
                onChange={(e) => setAuthUsername(e.target.value)}
                autoComplete="username"
              />
            </div>
            <div className="field">
              <label>
                Password{' '}
                {data?.auth_password_set ? '(saved — leave blank to keep)' : '(required to enable)'}
              </label>
              <input
                type="password"
                value={authPassword}
                onChange={(e) => setAuthPassword(e.target.value)}
                autoComplete="new-password"
                placeholder={data?.auth_password_set ? 'Leave blank to keep' : 'Choose a password'}
              />
            </div>
            <div className="field">
              <label>Confirm password</label>
              <input
                type="password"
                value={authPasswordConfirm}
                onChange={(e) => setAuthPasswordConfirm(e.target.value)}
                autoComplete="new-password"
                placeholder={authPassword ? 'Repeat password' : 'Only needed when setting a password'}
              />
            </div>
            {authStatus?.enabled && authStatus.authenticated && (
              <div className="toolbar">
                <button
                  type="button"
                  className="btn ghost"
                  onClick={() => appLogout.mutate()}
                  disabled={appLogout.isPending}
                >
                  Sign out of Musicarr
                </button>
              </div>
            )}

            <hr className="settings-divider" />

            <h3 style={{ margin: '0 0 0.25rem', fontSize: '1.05rem' }}>SSL / reverse proxy</h3>
            <p className="muted" style={{ marginTop: 0, maxWidth: 560 }}>
              For Traefik (or another reverse proxy). Traefik terminates HTTPS; Musicarr stays on
              HTTP port <strong>8787</strong>. Enabling this marks session cookies as Secure so
              login works over HTTPS.
            </p>
            {sslEnabled && !authEnabled && (
              <div className="banner warn">
                You are exposing Musicarr behind HTTPS without app login. Enable login above before
                publishing off your LAN.
              </div>
            )}
            <div className="field">
              <label>HTTPS / Traefik mode</label>
              <div className="checks">
                <label>
                  <input
                    type="checkbox"
                    checked={sslEnabled}
                    onChange={(e) => setSslEnabled(e.target.checked)}
                  />
                  Behind HTTPS (Traefik terminates SSL)
                </label>
              </div>
            </div>
            <div className="field">
              <label>Public domain</label>
              <input
                type="text"
                value={publicDomain}
                onChange={(e) => setPublicDomain(e.target.value)}
                placeholder="music.example.com"
                autoComplete="off"
              />
            </div>
            {sslEnabled && publicDomain.trim() && (
              <p className="muted" style={{ margin: 0 }}>
                Public URL:{' '}
                <a
                  href={`https://${publicDomain.replace(/^https?:\/\//i, '').split('/')[0]}`}
                  target="_blank"
                  rel="noreferrer"
                >
                  https://{publicDomain.replace(/^https?:\/\//i, '').split('/')[0]}
                </a>
              </p>
            )}
            <div className="field">
              <label>Traefik labels (copy into your compose service)</label>
              <textarea
                className="code-block"
                readOnly
                rows={7}
                value={traefikLabels(publicDomain)}
              />
              <div className="toolbar" style={{ marginBottom: 0 }}>
                <button
                  type="button"
                  className="btn secondary"
                  onClick={() => {
                    void navigator.clipboard.writeText(traefikLabels(publicDomain)).then(
                      () => toast.push('Traefik labels copied', 'ok'),
                      () => toast.push('Could not copy to clipboard', 'error'),
                    )
                  }}
                >
                  Copy labels
                </button>
              </div>
            </div>
          </>
        )}

        {tab === 'player' && (
          <>
            <h3 style={{ margin: '0 0 0.25rem', fontSize: '1.05rem' }}>Music player</h3>
            <p className="muted" style={{ marginTop: 0, maxWidth: 560 }}>
              Optional multi-user listening app at{' '}
              <a href="/player" target="_blank" rel="noreferrer">
                /player
              </a>
              . Separate logins from admin. Streams original library files (FLAC stays FLAC — no
              transcode).
            </p>
            <div className="field">
              <label>Enable player</label>
              <div className="checks">
                <label>
                  <input
                    type="checkbox"
                    checked={playerEnabled}
                    onChange={(e) => setPlayerEnabled(e.target.checked)}
                  />
                  Enable music player (/player)
                </label>
                <label>
                  <input
                    type="checkbox"
                    checked={playerSharingEnabled}
                    onChange={(e) => setPlayerSharingEnabled(e.target.checked)}
                    disabled={!playerEnabled}
                  />
                  Allow listeners to create public share links (/s/…)
                </label>
              </div>
            </div>

            <hr className="settings-divider" />

            <h3 style={{ margin: '0 0 0.25rem', fontSize: '1.05rem' }}>Player users</h3>
            <p className="muted" style={{ marginTop: 0, maxWidth: 560 }}>
              Create listener accounts. They can change their own password inside the player.
            </p>
            <div className="toolbar" style={{ flexWrap: 'wrap', alignItems: 'flex-end' }}>
              <div className="field" style={{ margin: 0 }}>
                <label>Username</label>
                <input
                  value={newPlayerUser}
                  onChange={(e) => setNewPlayerUser(e.target.value)}
                  autoComplete="off"
                />
              </div>
              <div className="field" style={{ margin: 0 }}>
                <label>Display name</label>
                <input
                  value={newPlayerDisplay}
                  onChange={(e) => setNewPlayerDisplay(e.target.value)}
                  autoComplete="off"
                />
              </div>
              <div className="field" style={{ margin: 0 }}>
                <label>Password</label>
                <input
                  type="password"
                  value={newPlayerPass}
                  onChange={(e) => setNewPlayerPass(e.target.value)}
                  autoComplete="new-password"
                />
              </div>
              <button
                type="button"
                className="btn"
                disabled={!newPlayerUser.trim() || newPlayerPass.length < 4 || createPlayerUser.isPending}
                onClick={() => createPlayerUser.mutate()}
              >
                Create user
              </button>
            </div>
            {playerUsers.isError && (
              <p className="error">{(playerUsers.error as Error).message}</p>
            )}
            <table className="table" style={{ marginTop: '1rem' }}>
              <thead>
                <tr>
                  <th>Username</th>
                  <th>Display</th>
                  <th>Active</th>
                  <th>Created</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {playerUsers.data?.map((u) => (
                  <tr key={u.id}>
                    <td>
                      <strong>{u.username}</strong>
                    </td>
                    <td>{u.display_name || '—'}</td>
                    <td>{u.is_active ? 'Yes' : 'No'}</td>
                    <td className="muted">{u.created_at?.slice(0, 10) || '—'}</td>
                    <td className="row-actions">
                      <button
                        type="button"
                        className="btn ghost"
                        onClick={() =>
                          updatePlayerUser.mutate({ id: u.id, body: { is_active: !u.is_active } })
                        }
                      >
                        {u.is_active ? 'Disable' : 'Enable'}
                      </button>
                      <button
                        type="button"
                        className="btn ghost"
                        onClick={() => {
                          setResetPassId(u.id)
                          setResetPassValue('')
                        }}
                      >
                        Reset password
                      </button>
                      <button
                        type="button"
                        className="btn ghost"
                        onClick={() => {
                          if (window.confirm(`Delete player user ${u.username}?`)) {
                            deletePlayerUser.mutate(u.id)
                          }
                        }}
                      >
                        Delete
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {resetPassId != null && (
              <div className="toolbar" style={{ marginTop: '0.75rem' }}>
                <input
                  type="password"
                  placeholder="New password"
                  value={resetPassValue}
                  onChange={(e) => setResetPassValue(e.target.value)}
                  autoComplete="new-password"
                />
                <button
                  type="button"
                  className="btn secondary"
                  disabled={resetPassValue.length < 4}
                  onClick={() =>
                    updatePlayerUser.mutate({
                      id: resetPassId,
                      body: { password: resetPassValue },
                    })
                  }
                >
                  Save password
                </button>
                <button type="button" className="btn ghost" onClick={() => setResetPassId(null)}>
                  Cancel
                </button>
              </div>
            )}
          </>
        )}

        {tab === 'tools' && (
          <>
            <p className="muted" style={{ marginTop: 0, maxWidth: 640 }}>
              Point Library path at your music folder, then import an existing collection or match
              files to artists you already added.
            </p>
            <div className="toolbar" style={{ flexWrap: 'wrap' }}>
              <button
                type="button"
                className="btn"
                onClick={() => {
                  if (
                    window.confirm(
                      'Import everything under your library path into Musicarr? Artists/albums will be created from tags and folders. Matching names may link to your active download source.',
                    )
                  ) {
                    importLib.mutate()
                  }
                }}
                disabled={importLib.isPending}
              >
                {importLib.isPending ? 'Importing…' : 'Import existing library'}
              </button>
              <Link className="btn secondary" to="/import-review">
                Review imports
              </Link>
              <button
                type="button"
                className="btn secondary"
                onClick={() => scan.mutate()}
                disabled={scan.isPending}
              >
                {scan.isPending ? 'Scanning…' : 'Match files to library'}
              </button>
              <button
                type="button"
                className="btn secondary"
                onClick={() => reorganize.mutate()}
                disabled={reorganize.isPending}
              >
                Reorganize files
              </button>
              <button
                type="button"
                className="btn secondary"
                onClick={() => monitor.mutate()}
                disabled={monitor.isPending}
              >
                Check for new releases
              </button>
            </div>
            <p className="muted" style={{ marginTop: '0.75rem', maxWidth: 640 }}>
              <strong>Import existing library</strong> creates artists/albums from what’s already on
              disk. <strong>Review imports</strong> links local-only artists and flags weak tags.{' '}
              <strong>Match files</strong> only links files to releases already in Musicarr.
            </p>
          </>
        )}

        {tab !== 'tools' && (
          <div className="toolbar">
            <button className="btn" type="submit" disabled={save.isPending}>
              Save settings
            </button>
          </div>
        )}
      </form>
    </div>
  )
}
