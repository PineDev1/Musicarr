import { useMutation } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { api } from '../api'

type Props = {
  onLoggedIn: () => void
}

export function LoginPage({ onLoggedIn }: Props) {
  const [username, setUsername] = useState('admin')
  const [password, setPassword] = useState('')

  const login = useMutation({
    mutationFn: () => api.appLogin(username.trim(), password),
    onSuccess: (res) => {
      if (res.authenticated) onLoggedIn()
    },
  })

  function onSubmit(e: FormEvent) {
    e.preventDefault()
    login.mutate()
  }

  return (
    <div className="login-shell">
      <form className="login-card" onSubmit={onSubmit}>
        <div className="brand" style={{ marginBottom: '0.25rem' }}>
          Music<span>arr</span>
        </div>
        <p className="muted" style={{ marginTop: 0 }}>
          Sign in to continue
        </p>
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
        {login.isError && <p className="error">{(login.error as Error).message}</p>}
        <button className="btn" type="submit" disabled={login.isPending || !password}>
          {login.isPending ? 'Signing in…' : 'Sign in'}
        </button>
      </form>
    </div>
  )
}
