import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import QRCode from 'qrcode'
import { api } from '../api'
import { useToast } from '../Toast'

export function TwoFactorPanel() {
  const qc = useQueryClient()
  const toast = useToast()
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const [setup, setSetup] = useState<{ secret: string; otpauth_url: string } | null>(null)
  const [confirmCode, setConfirmCode] = useState('')
  const [disableCode, setDisableCode] = useState('')
  const [showDisable, setShowDisable] = useState(false)

  const { data: users } = useQuery({ queryKey: ['admin-users'], queryFn: api.adminUsers })
  // Two-factor is per-AdminUser; this panel manages it for the account the
  // browser is currently signed in as. There's no "current user" endpoint,
  // so it operates on the first admin user row — fine for the common single
  // extra-admin setup this feature targets.
  const currentUser = users?.[0]

  useEffect(() => {
    if (!setup || !canvasRef.current) return
    QRCode.toCanvas(canvasRef.current, setup.otpauth_url, { width: 200 }).catch(() => {})
  }, [setup])

  const startSetup = useMutation({
    mutationFn: api.totpSetup,
    onSuccess: (res) => setSetup(res),
    onError: (err) => toast.push((err as Error).message, 'error'),
  })

  const confirm = useMutation({
    mutationFn: () => api.totpConfirm(confirmCode.trim()),
    onSuccess: () => {
      toast.push('Two-factor authentication enabled', 'ok')
      setSetup(null)
      setConfirmCode('')
      qc.invalidateQueries({ queryKey: ['admin-users'] })
    },
    onError: (err) => toast.push((err as Error).message, 'error'),
  })

  const disable = useMutation({
    mutationFn: () => api.totpDisable(disableCode.trim()),
    onSuccess: () => {
      toast.push('Two-factor authentication disabled', 'ok')
      setShowDisable(false)
      setDisableCode('')
      qc.invalidateQueries({ queryKey: ['admin-users'] })
    },
    onError: (err) => toast.push((err as Error).message, 'error'),
  })

  return (
    <div>
      <h3 style={{ margin: '0 0 0.25rem', fontSize: '1.05rem' }}>Two-factor authentication</h3>
      <p className="muted" style={{ marginTop: 0, maxWidth: 560 }}>
        Requires a named admin user (above) — the legacy admin/password login can't use 2FA.
      </p>

      {!currentUser && <p className="muted">Create an admin user above first.</p>}

      {currentUser && currentUser.totp_enabled && !showDisable && (
        <div className="toolbar">
          <span className="badge queued">Enabled</span>
          <button type="button" className="btn ghost" onClick={() => setShowDisable(true)}>
            Disable
          </button>
        </div>
      )}

      {currentUser && showDisable && (
        <div className="toolbar" style={{ flexWrap: 'wrap', alignItems: 'flex-end' }}>
          <div className="field" style={{ margin: 0 }}>
            <label>Enter a current code to disable</label>
            <input
              type="text"
              inputMode="numeric"
              maxLength={6}
              value={disableCode}
              onChange={(e) => setDisableCode(e.target.value.replace(/\D/g, ''))}
            />
          </div>
          <button
            type="button"
            className="btn danger"
            disabled={disableCode.length !== 6 || disable.isPending}
            onClick={() => disable.mutate()}
          >
            Confirm disable
          </button>
          <button type="button" className="btn ghost" onClick={() => setShowDisable(false)}>
            Cancel
          </button>
        </div>
      )}

      {currentUser && !currentUser.totp_enabled && !setup && (
        <button
          type="button"
          className="btn"
          disabled={startSetup.isPending}
          onClick={() => startSetup.mutate()}
        >
          Set up two-factor authentication
        </button>
      )}

      {setup && (
        <div style={{ marginTop: '1rem' }}>
          <p>Scan this with your authenticator app (Google Authenticator, 1Password, etc.):</p>
          <canvas ref={canvasRef} />
          <p className="muted" style={{ fontFamily: 'monospace' }}>
            Manual entry: {setup.secret}
          </p>
          <div className="toolbar" style={{ flexWrap: 'wrap', alignItems: 'flex-end' }}>
            <div className="field" style={{ margin: 0 }}>
              <label>Enter the 6-digit code to confirm</label>
              <input
                type="text"
                inputMode="numeric"
                maxLength={6}
                value={confirmCode}
                onChange={(e) => setConfirmCode(e.target.value.replace(/\D/g, ''))}
                autoFocus
              />
            </div>
            <button
              type="button"
              className="btn"
              disabled={confirmCode.length !== 6 || confirm.isPending}
              onClick={() => confirm.mutate()}
            >
              Confirm
            </button>
            <button type="button" className="btn ghost" onClick={() => setSetup(null)}>
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

export function ApiKeysPanel() {
  const qc = useQueryClient()
  const toast = useToast()
  const [name, setName] = useState('')
  const [revealedKey, setRevealedKey] = useState<string | null>(null)

  const { data, isLoading } = useQuery({ queryKey: ['api-keys'], queryFn: api.apiKeys })

  const create = useMutation({
    mutationFn: () => api.createApiKey(name.trim()),
    onSuccess: (res) => {
      setRevealedKey(res.key)
      setName('')
      qc.invalidateQueries({ queryKey: ['api-keys'] })
    },
    onError: (err) => toast.push((err as Error).message, 'error'),
  })

  const remove = useMutation({
    mutationFn: (id: number) => api.deleteApiKey(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['api-keys'] }),
    onError: (err) => toast.push((err as Error).message, 'error'),
  })

  return (
    <div>
      <h3 style={{ margin: '0 0 0.25rem', fontSize: '1.05rem' }}>API keys</h3>
      <p className="muted" style={{ marginTop: 0, maxWidth: 640 }}>
        For external automation (scripts, Overseerr, custom dashboards) — send the key as an{' '}
        <code>X-Api-Key</code> header instead of logging in. Works even when app login is enabled.
      </p>

      {revealedKey && (
        <div className="banner warn" style={{ marginBottom: '1rem' }}>
          <strong>Copy this key now — it won't be shown again:</strong>
          <div style={{ fontFamily: 'monospace', wordBreak: 'break-all', margin: '0.5rem 0' }}>
            {revealedKey}
          </div>
          <button type="button" className="btn ghost" onClick={() => setRevealedKey(null)}>
            Done
          </button>
        </div>
      )}

      <div className="toolbar" style={{ flexWrap: 'wrap', alignItems: 'flex-end' }}>
        <div className="field" style={{ margin: 0 }}>
          <label>Name</label>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Overseerr"
            autoComplete="off"
          />
        </div>
        <button
          type="button"
          className="btn"
          disabled={!name.trim() || create.isPending}
          onClick={() => create.mutate()}
        >
          Generate key
        </button>
      </div>

      {isLoading && <p className="muted">Loading…</p>}
      {!isLoading && (data?.length ?? 0) === 0 && <p className="muted">No API keys yet.</p>}
      {(data?.length ?? 0) > 0 && (
        <table className="table" style={{ marginTop: '1rem' }}>
          <thead>
            <tr>
              <th>Name</th>
              <th>Key</th>
              <th>Last used</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {data!.map((k) => (
              <tr key={k.id}>
                <td>{k.name}</td>
                <td className="muted" style={{ fontFamily: 'monospace' }}>
                  {k.key_prefix}…
                </td>
                <td className="muted">{k.last_used_at ? k.last_used_at.slice(0, 10) : 'Never'}</td>
                <td className="row-actions">
                  <button
                    type="button"
                    className="btn ghost"
                    onClick={() => {
                      if (window.confirm(`Revoke API key "${k.name}"?`)) remove.mutate(k.id)
                    }}
                  >
                    Revoke
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
