import { useMutation, useQuery } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { playerApi } from './playerApi'

/** Landing page for /player/invite/<token>: pick a username + password, get signed in. */
export function PlayerInvitePage({ token, onDone }: { token: string; onDone: () => void }) {
  const [username, setUsername] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const navigate = useNavigate()

  const invite = useQuery({
    queryKey: ['player-invite', token],
    queryFn: () => playerApi.checkInvite(token),
    retry: false,
  })
  const accept = useMutation({
    mutationFn: () =>
      playerApi.acceptInvite(token, {
        username: username.trim(),
        password,
        display_name: displayName.trim(),
      }),
    onSuccess: () => {
      // Drop the single-use token from the address bar/history, then enter the player.
      navigate('/player', { replace: true })
      onDone()
    },
  })

  const mismatch = confirm.length > 0 && confirm !== password
  const ready = username.trim().length > 0 && password.length >= 8 && password === confirm

  function onSubmit(e: FormEvent) {
    e.preventDefault()
    if (ready) accept.mutate()
  }

  if (invite.isLoading) {
    return (
      <div className="login-shell">
        <p className="muted">Checking your invite…</p>
      </div>
    )
  }

  if (invite.isError) {
    return (
      <div className="login-shell player-login">
        <div className="login-card">
          <div className="brand">
            Music<span>arr</span>
          </div>
          <h2 style={{ margin: '0.5rem 0' }}>Invite not valid</h2>
          <p className="muted">{(invite.error as Error).message}</p>
          <p className="muted">Ask whoever runs this server for a fresh invite link.</p>
          <a className="btn ghost" href="/player">
            Go to sign in
          </a>
        </div>
      </div>
    )
  }

  return (
    <div className="login-shell player-login">
      <form className="login-card" onSubmit={onSubmit}>
        <div className="brand">
          Music<span>arr</span>
        </div>
        <p className="muted" style={{ marginTop: 0 }}>
          You've been invited to listen{invite.data?.note ? ` (${invite.data.note})` : ''}. Choose how you'll sign in.
        </p>
        <div className="field">
          <label>Username</label>
          <input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" autoFocus />
        </div>
        <div className="field">
          <label>Display name (optional)</label>
          <input value={displayName} onChange={(e) => setDisplayName(e.target.value)} maxLength={128} />
        </div>
        <div className="field">
          <label>Password (at least 8 characters)</label>
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="new-password" />
        </div>
        <div className="field">
          <label>Confirm password</label>
          <input type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)} autoComplete="new-password" />
        </div>
        {mismatch && <p className="error">Passwords don't match.</p>}
        {accept.isError && <p className="error">{(accept.error as Error).message}</p>}
        <button className="btn" type="submit" disabled={!ready || accept.isPending}>
          {accept.isPending ? 'Creating account…' : 'Create my account'}
        </button>
      </form>
    </div>
  )
}
