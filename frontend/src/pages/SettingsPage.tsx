import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState, type FormEvent } from 'react'
import { api } from '../api'
import { useToast } from '../Toast'

export function SettingsPage() {
  const qc = useQueryClient()
  const toast = useToast()
  const { data, isLoading, error } = useQuery({
    queryKey: ['settings'],
    queryFn: () => api.settings(true),
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
    setQobuzEmail(data.qobuz_email || '')
    setQobuzUserId(data.qobuz_user_id || '')
    setQobuzAppId(data.qobuz_app_id || '950096963')
  }, [data])

  const save = useMutation({
    mutationFn: () => {
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
        qobuz_app_id: qobuzAppId,
      }
      if (arl.trim()) body.arl = arl.trim()
      if (qobuzAppSecret.trim()) body.qobuz_app_secret = qobuzAppSecret.trim()
      return api.updateSettings(body)
    },
    onSuccess: () => {
      setArl('')
      setQobuzAppSecret('')
      toast.push('Settings saved', 'ok')
      qc.invalidateQueries({ queryKey: ['settings'] })
      qc.invalidateQueries({ queryKey: ['health'] })
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
  })
  const reorganize = useMutation({
    mutationFn: api.reorganize,
    onSuccess: (res) => toast.push(res.message, 'ok'),
  })
  const monitor = useMutation({
    mutationFn: api.runMonitor,
    onSuccess: (res) =>
      toast.push(`Monitor: ${res.artists_checked} artists, ${res.new_albums} new`, 'ok'),
  })

  function onSubmit(e: FormEvent) {
    e.preventDefault()
    save.mutate()
  }

  if (isLoading) return <p className="muted">Loading…</p>
  if (error) return <p className="error">{(error as Error).message}</p>

  return (
    <div>
      <div className="page-header">
        <div>
          <h1>Settings</h1>
          <p>Choose one download source, sign in, and tune your library.</p>
        </div>
      </div>

      {data && data.provider_ok === false && (
        <div className="banner warn">
          {data.provider_error || 'Active provider is not connected.'}
        </div>
      )}

      <form className="form-grid" onSubmit={onSubmit}>
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

        <div className="field">
          <label>Library path</label>
          <input type="text" value={libraryPath} onChange={(e) => setLibraryPath(e.target.value)} />
        </div>
        <div className="field">
          <label>Quality</label>
          <select value={bitrate} onChange={(e) => setBitrate(e.target.value)}>
            <option value="flac">FLAC</option>
            <option value="320">MP3 320</option>
            <option value="128">MP3 128</option>
          </select>
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
              <input type="checkbox" checked={includeSingles} onChange={(e) => setIncludeSingles(e.target.checked)} />
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
        <div className="toolbar">
          <button className="btn" type="submit" disabled={save.isPending}>
            Save settings
          </button>
        </div>
      </form>

      <div className="page-header" style={{ marginTop: '2.5rem' }}>
        <div>
          <h1 style={{ fontSize: '1.8rem' }}>Library tools</h1>
          <p>Scan existing files or re-apply naming templates.</p>
        </div>
      </div>
      <div className="toolbar">
        <button className="btn secondary" onClick={() => scan.mutate()} disabled={scan.isPending}>
          Scan library
        </button>
        <button className="btn secondary" onClick={() => reorganize.mutate()} disabled={reorganize.isPending}>
          Reorganize files
        </button>
        <button className="btn secondary" onClick={() => monitor.mutate()} disabled={monitor.isPending}>
          Check for new releases
        </button>
      </div>
    </div>
  )
}
