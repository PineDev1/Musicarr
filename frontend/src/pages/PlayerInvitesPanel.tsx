import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { api } from '../api'
import { useToast } from '../Toast'

/** One-time sign-up links for new listeners, so you never have to hand out a password. */
export function PlayerInvitesPanel() {
  const qc = useQueryClient()
  const toast = useToast()
  const [note, setNote] = useState('')
  const [days, setDays] = useState(7)
  const [fresh, setFresh] = useState<string | null>(null)
  const invites = useQuery({ queryKey: ['player-invites'], queryFn: api.playerInvites, retry: false })

  const create = useMutation({
    mutationFn: () => api.createPlayerInvite({ note: note.trim(), days }),
    onSuccess: (r) => {
      setFresh(`${window.location.origin}${r.path}`)
      setNote('')
      qc.invalidateQueries({ queryKey: ['player-invites'] })
    },
    onError: (err) => toast.push((err as Error).message, 'error'),
  })
  const revoke = useMutation({
    mutationFn: (id: number) => api.revokePlayerInvite(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['player-invites'] }),
    onError: (err) => toast.push((err as Error).message, 'error'),
  })

  async function copy(text: string) {
    try {
      await navigator.clipboard.writeText(text)
      toast.push('Link copied', 'ok')
    } catch {
      toast.push('Copy failed — select the link and copy it manually', 'error')
    }
  }

  return (
    <div className="field">
      <label>Invite a listener</label>
      <p className="muted" style={{ marginTop: 0, maxWidth: 600, fontSize: '0.85rem' }}>
        Create a one-time link. The person opens it, picks their own username and password, and is
        signed in. Links expire and stop working after one use.
      </p>
      <div className="toolbar" style={{ flexWrap: 'wrap', alignItems: 'flex-end' }}>
        <div className="field" style={{ margin: 0, minWidth: 220 }}>
          <label>Note (optional)</label>
          <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="For Sam" maxLength={128} />
        </div>
        <div className="field" style={{ margin: 0 }}>
          <label>Expires in</label>
          <select value={days} onChange={(e) => setDays(Number(e.target.value))}>
            <option value={1}>1 day</option>
            <option value={7}>7 days</option>
            <option value={30}>30 days</option>
          </select>
        </div>
        <button type="button" className="btn" disabled={create.isPending} onClick={() => create.mutate()}>
          Create invite link
        </button>
      </div>
      {fresh && (
        <div className="banner" style={{ marginTop: '0.75rem', maxWidth: 680 }}>
          <div style={{ marginBottom: '0.35rem' }}>
            Copy this link now — it won't be shown again:
          </div>
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <input readOnly value={fresh} onFocus={(e) => e.currentTarget.select()} style={{ flex: 1 }} />
            <button type="button" className="btn" onClick={() => copy(fresh)}>
              Copy
            </button>
          </div>
        </div>
      )}
      {invites.isError && (
        <p className="muted" style={{ marginTop: '0.5rem' }}>
          {(invites.error as Error).message}
        </p>
      )}
      {(invites.data?.length ?? 0) > 0 && (
        <table className="table" style={{ marginTop: '0.75rem', maxWidth: 680 }}>
          <thead>
            <tr>
              <th>Note</th>
              <th>Status</th>
              <th>Expires</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {invites.data?.map((i) => (
              <tr key={i.id}>
                <td>{i.note || '—'}</td>
                <td>{i.status}</td>
                <td>{i.expires_at ? new Date(i.expires_at).toLocaleDateString() : '—'}</td>
                <td style={{ textAlign: 'right' }}>
                  <button type="button" className="btn ghost danger" onClick={() => revoke.mutate(i.id)}>
                    {i.status === 'pending' ? 'Revoke' : 'Remove'}
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
