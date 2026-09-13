import { useMutation } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { playerApi } from './playerApi'

export function PlayerLoginPage({ onLoggedIn }: { onLoggedIn: () => void }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const login = useMutation({
    mutationFn: () => playerApi.login(username.trim(), password),
    onSuccess: (res) => {
      if (res.authenticated) onLoggedIn()
    },
  })

  function onSubmit(e: FormEvent) {
    e.preventDefault()
    login.mutate()
  }

  return (
    <div className="login-shell player-login">
      <form className="login-card" onSubmit={onSubmit}>
        <div className="brand">
          Music<span>arr</span>
        </div>
        <p className="muted" style={{ marginTop: 0 }}>
          Player sign in — listening only
        </p>
        <div className="field">
          <label>Username</label>
          <input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" autoFocus />
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
        <button className="btn" type="submit" disabled={login.isPending || !username || !password}>
          {login.isPending ? 'Signing in…' : 'Sign in'}
        </button>
      </form>
    </div>
  )
}
