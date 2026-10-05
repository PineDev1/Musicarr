import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { playerApi } from './playerApi'

export function SubsonicPanel() {
  const qc = useQueryClient()
  const [shown, setShown] = useState(false)
  const q = useQuery({ queryKey: ['player-subsonic'], queryFn: playerApi.subsonic })
  const regen = useMutation({
    mutationFn: playerApi.regenerateSubsonic,
    onSuccess: () => {
      setShown(true)
      qc.invalidateQueries({ queryKey: ['player-subsonic'] })
    },
  })
  const revoke = useMutation({
    mutationFn: playerApi.revokeSubsonic,
    onSuccess: () => {
      setShown(false)
      qc.invalidateQueries({ queryKey: ['player-subsonic'] })
    },
  })
  const secret = q.data?.secret
  return (
    <div className="audio-settings">
      <h3>Other music apps (Subsonic)</h3>
      <p className="muted tiny" style={{ marginTop: 0 }}>
        Use Symfonium, DSub, Feishin, Substreamer or any Subsonic-compatible app. Add this server as a
        Subsonic / OpenSubsonic server with the details below. This secret only works for those apps.
        It is not your login password and can be revoked any time.
      </p>
      <div className="muted tiny">Server: {window.location.origin}</div>
      <div className="muted tiny">Username: {q.data?.username}</div>
      {secret ? (
        <div className="muted tiny">
          Password: <code>{shown ? secret : '••••••••••••••••'}</code>{' '}
          <button type="button" className="btn ghost" onClick={() => setShown((v) => !v)}>
            {shown ? 'Hide' : 'Show'}
          </button>
        </div>
      ) : (
        <div className="muted tiny">No secret yet.</div>
      )}
      <div className="sleep-options">
        <button type="button" className="btn ghost" disabled={regen.isPending} onClick={() => regen.mutate()}>
          {secret ? 'Regenerate secret' : 'Create secret'}
        </button>
        {secret && (
          <button type="button" className="btn ghost danger" onClick={() => revoke.mutate()}>
            Revoke
          </button>
        )}
      </div>
    </div>
  )
}
