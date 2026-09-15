import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState, type FormEvent } from 'react'
import { api } from '../api'
import { useToast } from '../Toast'

const SETUP_DONE_KEY = 'musicarr_setup_done'
const SETUP_SKIP_KEY = 'musicarr_setup_skipped'

export function isSetupComplete(): boolean {
  try {
    return (
      localStorage.getItem(SETUP_DONE_KEY) === '1' ||
      localStorage.getItem(SETUP_SKIP_KEY) === '1'
    )
  } catch {
    return true
  }
}

export function markSetupDone() {
  try {
    localStorage.setItem(SETUP_DONE_KEY, '1')
    localStorage.removeItem(SETUP_SKIP_KEY)
  } catch {
    /* ignore */
  }
}

export function markSetupSkipped() {
  try {
    localStorage.setItem(SETUP_SKIP_KEY, '1')
  } catch {
    /* ignore */
  }
}

function leaveSetup(path: string) {
  // Full navigation avoids React Router races when swapping setup ↔ main routes.
  window.location.assign(path)
}

type Step = 1 | 2 | 3

export function SetupWizardPage() {
  const qc = useQueryClient()
  const toast = useToast()
  const [step, setStep] = useState<Step>(1)
  const [libraryPath, setLibraryPath] = useState('')
  const [activeProvider, setActiveProvider] = useState('qobuz')
  const [arl, setArl] = useState('')
  const [qobuzEmail, setQobuzEmail] = useState('')
  const [qobuzPassword, setQobuzPassword] = useState('')
  const [qobuzToken, setQobuzToken] = useState('')
  const [qobuzUserId, setQobuzUserId] = useState('')
  const [qobuzAppId, setQobuzAppId] = useState('')
  const [qobuzAppSecret, setQobuzAppSecret] = useState('')
  const [authEnabled, setAuthEnabled] = useState(false)
  const [authUsername, setAuthUsername] = useState('admin')
  const [authPassword, setAuthPassword] = useState('')
  const [playerEnabled, setPlayerEnabled] = useState(false)
  const [tidalCode, setTidalCode] = useState<string | null>(null)
  const [tidalUri, setTidalUri] = useState<string | null>(null)

  const settings = useQuery({
    queryKey: ['settings'],
    queryFn: () => api.settings(true),
  })
  const health = useQuery({
    queryKey: ['health'],
    queryFn: api.health,
    refetchInterval: 5000,
  })

  useEffect(() => {
    if (!settings.data) return
    setLibraryPath(settings.data.library_path || '')
    setActiveProvider(settings.data.active_provider || 'qobuz')
    setAuthEnabled(Boolean(settings.data.auth_enabled))
    setAuthUsername(settings.data.auth_username || 'admin')
    setPlayerEnabled(Boolean(settings.data.player_enabled))
    setQobuzEmail(settings.data.qobuz_email || '')
    setQobuzUserId(settings.data.qobuz_user_id || '')
    setQobuzAppId(settings.data.qobuz_app_id || '')
  }, [settings.data])

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
        /* ignore */
      }
    }, 2500)
    return () => window.clearInterval(id)
  }, [tidalCode, qc, toast])

  const saveLibrary = useMutation({
    mutationFn: () => api.updateSettings({ library_path: libraryPath.trim() }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['settings'] })
      qc.invalidateQueries({ queryKey: ['health'] })
      toast.push('Library path saved', 'ok')
      setStep(2)
    },
    onError: (err) => toast.push((err as Error).message, 'error'),
  })

  const saveProvider = useMutation({
    mutationFn: async () => {
      await api.updateSettings({
        active_provider: activeProvider,
        ...(activeProvider === 'qobuz' && qobuzAppId.trim()
          ? { qobuz_app_id: qobuzAppId.trim() }
          : {}),
        ...(activeProvider === 'qobuz' && qobuzAppSecret.trim()
          ? { qobuz_app_secret: qobuzAppSecret.trim() }
          : {}),
      })
      if (activeProvider === 'deezer') {
        if (!arl.trim()) throw new Error('Paste your Deezer ARL cookie')
        await api.updateSettings({ arl: arl.trim() })
      } else if (activeProvider === 'tidal') {
        if (!health.data?.tidal_ok) {
          throw new Error('Finish Tidal device login before continuing')
        }
      } else if (activeProvider === 'qobuz') {
        const hasToken = Boolean(qobuzToken.trim() || settings.data?.qobuz_token_set)
        const hasEmail = Boolean(qobuzEmail.trim() && qobuzPassword)
        if (hasToken) {
          if (!qobuzAppId.trim() && !settings.data?.qobuz_app_id) {
            throw new Error('Qobuz app ID is required')
          }
          if (!qobuzAppSecret.trim() && !settings.data?.qobuz_app_secret_set) {
            throw new Error('Qobuz app secret is required')
          }
          await api.qobuzTokenLogin({
            token: qobuzToken.trim(),
            user_id: qobuzUserId.trim() || undefined,
            app_id: qobuzAppId.trim() || undefined,
            app_secret: qobuzAppSecret.trim() || undefined,
          })
        } else if (hasEmail) {
          if (qobuzAppId.trim() || qobuzAppSecret.trim()) {
            await api.updateSettings({
              ...(qobuzAppId.trim() ? { qobuz_app_id: qobuzAppId.trim() } : {}),
              ...(qobuzAppSecret.trim() ? { qobuz_app_secret: qobuzAppSecret.trim() } : {}),
            })
          }
          await api.qobuzLogin(qobuzEmail.trim(), qobuzPassword)
        } else {
          throw new Error(
            'Qobuz needs token + user ID + app ID + app secret (recommended), or email/password',
          )
        }
      }
    },
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ['settings'] })
      await qc.invalidateQueries({ queryKey: ['health'] })
      const h = await api.health()
      if (!h.provider_ok) {
        toast.push(h.provider_error || 'Provider still not connected', 'error')
        return
      }
      toast.push('Provider connected', 'ok')
      setStep(3)
    },
    onError: (err) => toast.push((err as Error).message, 'error'),
  })

  const finish = useMutation({
    mutationFn: () =>
      api.updateSettings({
        auth_enabled: authEnabled,
        auth_username: authUsername.trim() || 'admin',
        ...(authEnabled && authPassword ? { auth_password: authPassword } : {}),
        player_enabled: playerEnabled,
      }),
    onSuccess: () => {
      markSetupDone()
      // Land on Tools so importing an existing collection is obvious.
      leaveSetup('/settings?tab=tools')
    },
    onError: (err) => toast.push((err as Error).message, 'error'),
  })

  function skip() {
    markSetupSkipped()
    leaveSetup('/settings?tab=tools')
  }

  async function startTidal(e: FormEvent) {
    e.preventDefault()
    try {
      await api.updateSettings({ active_provider: 'tidal' })
      const res = await api.tidalDeviceStart()
      setTidalCode(res.user_code)
      setTidalUri(res.verification_uri_complete || res.verification_uri)
    } catch (err) {
      toast.push((err as Error).message, 'error')
    }
  }

  // Already finished/skipped in another tab — leave without trapping in this page.
  useEffect(() => {
    if (isSetupComplete()) leaveSetup('/')
  }, [])

  const providerOk = Boolean(health.data?.provider_ok)
  const libraryOk = Boolean(health.data?.library_writable)

  return (
    <div className="login-shell">
      <div className="login-card" style={{ maxWidth: 560, width: '100%' }}>
        <div className="brand" style={{ marginBottom: '0.5rem' }}>
          Music<span>arr</span>
        </div>
        <h1 style={{ margin: '0 0 0.35rem', fontSize: '1.4rem' }}>Welcome</h1>
        <p className="muted" style={{ marginTop: 0 }}>
          Step {step} of 3 — library path, download source, then optional security.
        </p>

        {step === 1 && (
          <form
            onSubmit={(e) => {
              e.preventDefault()
              saveLibrary.mutate()
            }}
          >
            <label>
              Library folder
              <input
                value={libraryPath}
                onChange={(e) => setLibraryPath(e.target.value)}
                placeholder="/music"
                required
              />
            </label>
            <p className="muted" style={{ fontSize: '0.85rem' }}>
              {libraryOk
                ? 'Path looks writable. This only sets the folder — it does not import files yet.'
                : 'Must be an existing writable directory.'}
            </p>
            <p className="muted" style={{ fontSize: '0.85rem' }}>
              After setup, use <strong>Settings → Tools → Import existing library</strong> to scan
              what’s already on disk.
            </p>
            <div className="toolbar" style={{ marginTop: '1rem' }}>
              <button className="btn" type="submit" disabled={saveLibrary.isPending}>
                {saveLibrary.isPending ? 'Saving…' : 'Continue'}
              </button>
              <button className="btn ghost" type="button" onClick={skip}>
                Skip setup
              </button>
            </div>
          </form>
        )}

        {step === 2 && (
          <div>
            <label>
              Active provider
              <select
                value={activeProvider}
                onChange={(e) => setActiveProvider(e.target.value)}
              >
                <option value="qobuz">Qobuz</option>
                <option value="deezer">Deezer</option>
                <option value="tidal">Tidal</option>
              </select>
            </label>

            {activeProvider === 'deezer' && (
              <label style={{ display: 'block', marginTop: '0.75rem' }}>
                Deezer ARL cookie
                <input
                  value={arl}
                  onChange={(e) => setArl(e.target.value)}
                  placeholder="Paste arl…"
                />
              </label>
            )}

            {activeProvider === 'tidal' && (
              <div style={{ marginTop: '0.75rem' }}>
                {tidalCode ? (
                  <p>
                    Enter code <strong>{tidalCode}</strong> at{' '}
                    <a href={tidalUri || '#'} target="_blank" rel="noreferrer">
                      {tidalUri}
                    </a>
                  </p>
                ) : (
                  <button className="btn secondary" type="button" onClick={startTidal}>
                    Start Tidal device login
                  </button>
                )}
              </div>
            )}

            {activeProvider === 'qobuz' && (
              <div style={{ marginTop: '0.75rem', display: 'grid', gap: '0.65rem' }}>
                <p className="muted" style={{ margin: 0, fontSize: '0.85rem' }}>
                  Same as Settings: paste <strong>token</strong>, <strong>user ID</strong>,{' '}
                  <strong>app ID</strong>, and <strong>app secret</strong> (QobuzDownloaderX-style).
                  Email/password is optional if you have those instead.
                </p>
                <label>
                  Token {settings.data?.qobuz_token_set ? '(saved)' : ''}
                  <input
                    type="password"
                    value={qobuzToken}
                    onChange={(e) => setQobuzToken(e.target.value)}
                    placeholder={
                      settings.data?.qobuz_token_set
                        ? 'Leave blank unless replacing'
                        : 'Paste Qobuz token'
                    }
                  />
                </label>
                <label>
                  User ID
                  <input
                    type="text"
                    value={qobuzUserId}
                    onChange={(e) => setQobuzUserId(e.target.value)}
                    placeholder="Qobuz user id"
                  />
                </label>
                <label>
                  App ID
                  <input
                    type="text"
                    value={qobuzAppId}
                    onChange={(e) => setQobuzAppId(e.target.value)}
                    placeholder="App id"
                  />
                </label>
                <label>
                  App secret {settings.data?.qobuz_app_secret_set ? '(saved)' : ''}
                  <input
                    type="password"
                    value={qobuzAppSecret}
                    onChange={(e) => setQobuzAppSecret(e.target.value)}
                    placeholder={
                      settings.data?.qobuz_app_secret_set
                        ? 'Leave blank to keep'
                        : 'Paste app secret'
                    }
                  />
                </label>
                <details>
                  <summary className="muted" style={{ cursor: 'pointer' }}>
                    Or login with email / password
                  </summary>
                  <div style={{ display: 'grid', gap: '0.5rem', marginTop: '0.5rem' }}>
                    <label>
                      Email
                      <input
                        value={qobuzEmail}
                        onChange={(e) => setQobuzEmail(e.target.value)}
                        type="email"
                      />
                    </label>
                    <label>
                      Password
                      <input
                        value={qobuzPassword}
                        onChange={(e) => setQobuzPassword(e.target.value)}
                        type="password"
                      />
                    </label>
                  </div>
                </details>
              </div>
            )}

            <p className="muted" style={{ fontSize: '0.85rem' }}>
              {providerOk
                ? 'Provider connected.'
                : health.data?.provider_error || 'Connect a provider to continue.'}
            </p>

            <div className="toolbar" style={{ marginTop: '1rem' }}>
              <button className="btn ghost" type="button" onClick={() => setStep(1)}>
                Back
              </button>
              <button
                className="btn"
                type="button"
                disabled={saveProvider.isPending}
                onClick={() => saveProvider.mutate()}
              >
                {saveProvider.isPending ? 'Connecting…' : 'Connect & continue'}
              </button>
              <button className="btn ghost" type="button" onClick={skip}>
                Skip setup
              </button>
            </div>
          </div>
        )}

        {step === 3 && (
          <form
            onSubmit={(e) => {
              e.preventDefault()
              if (authEnabled && authPassword.length < 4) {
                toast.push('Password must be at least 4 characters', 'error')
                return
              }
              finish.mutate()
            }}
          >
            <label style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <input
                type="checkbox"
                checked={authEnabled}
                onChange={(e) => setAuthEnabled(e.target.checked)}
              />
              Require admin login (recommended on public hosts)
            </label>
            {authEnabled && (
              <div style={{ marginTop: '0.75rem', display: 'grid', gap: '0.5rem' }}>
                <label>
                  Username
                  <input
                    value={authUsername}
                    onChange={(e) => setAuthUsername(e.target.value)}
                  />
                </label>
                <label>
                  Password
                  <input
                    type="password"
                    value={authPassword}
                    onChange={(e) => setAuthPassword(e.target.value)}
                    required={authEnabled}
                  />
                </label>
              </div>
            )}
            <label
              style={{ display: 'flex', gap: 8, alignItems: 'center', marginTop: '0.75rem' }}
            >
              <input
                type="checkbox"
                checked={playerEnabled}
                onChange={(e) => setPlayerEnabled(e.target.checked)}
              />
              Enable multi-user player at /player
            </label>
            <p className="muted" style={{ fontSize: '0.85rem' }}>
              Next you’ll land on Settings → Tools. Use <strong>Import existing library</strong> if
              you already have files under the library path.
            </p>
            <div className="toolbar" style={{ marginTop: '1rem' }}>
              <button className="btn ghost" type="button" onClick={() => setStep(2)}>
                Back
              </button>
              <button className="btn" type="submit" disabled={finish.isPending}>
                {finish.isPending ? 'Finishing…' : 'Finish'}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  )
}
