import { useMutation } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { api } from '../api'

type Props = {
  onLoggedIn: () => void
}

export function LoginPage({ onLoggedIn }: Props) {
  const [username, setUsername] = useState('admin')
  const [password, setPassword] = useState('')
  const [totpCode, setTotpCode] = useState('')
  const [needsTotp, setNeedsTotp] = useState(false)

  const login = useMutation({
    mutationFn: () => api.appLogin(username.trim(), password, needsTotp ? totpCode.trim() : undefined),
    onSuccess: (res) => {
      if (res.authenticated) onLoggedIn()
    },
    onError: (err) => {
      if ((err as Error).message === 'totp_required') setNeedsTotp(true)
    },
  })

  function onSubmit(e: FormEvent) {
    e.preventDefault()
    login.mutate()
  }

  const totpError = login.isError && (login.error as Error).message === 'totp_required'
  const otherError = login.isError && (login.error as Error).message !== 'totp_required'

  return (
    <div className="login-shell">
      <form className="login-card" onSubmit={onSubmit}>
        <div className="brand" style={{ marginBottom: '0.25rem' }}>
          Music<span>arr</span>
        </div>
        <p className="muted" style={{ marginTop: 0 }}>
          Sign in to continue
        </p>
        {!needsTotp && (
          <>
            <div className="field">
              <label>Username</label>
              <input
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoComplete="username"
                autoFocus
              />
            </div>
            <div className="field">
              <label>Password</label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
              />
            </div>
          </>
        )}
        {needsTotp && (
          <div className="field">
            <label>Two-factor code</label>
            <p className="muted" style={{ marginTop: 0, fontSize: '0.85rem' }}>
              Enter the 6-digit code from your authenticator app.
            </p>
            <input
              type="text"
              inputMode="numeric"
              maxLength={6}
              value={totpCode}
              onChange={(e) => setTotpCode(e.target.value.replace(/\D/g, ''))}
              autoComplete="one-time-code"
              autoFocus
            />
          </div>
        )}
        {totpError && !needsTotp && null}
        {otherError && <p className="error">{(login.error as Error).message}</p>}
        <button
          className="btn"
          type="submit"
          disabled={login.isPending || (needsTotp ? totpCode.length !== 6 : !password)}
        >
          {login.isPending ? 'Signing in…' : needsTotp ? 'Verify' : 'Sign in'}
        </button>
        {needsTotp && (
          <button
            type="button"
            className="btn ghost"
            style={{ marginTop: '0.5rem' }}
            onClick={() => {
              setNeedsTotp(false)
              setTotpCode('')
            }}
          >
            Back
          </button>
        )}
      </form>
    </div>
  )
}
