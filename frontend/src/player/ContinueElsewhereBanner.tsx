import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { getDeviceId } from './deviceInfo'
import { playerApi } from './playerApi'
import { usePlayerQueue } from './PlayerQueueContext'

const DISMISS_KEY = 'musicarr-continue-dismissed'
const MAX_AGE_MS = 24 * 60 * 60 * 1000

function readDismissed(): string | null {
  try {
    return sessionStorage.getItem(DISMISS_KEY)
  } catch {
    return null
  }
}

/** "Continue on this device": offers the queue another device was playing. */
export function ContinueElsewhereBanner() {
  const q = usePlayerQueue()
  const [dismissed, setDismissed] = useState<string | null>(readDismissed)
  const saved = useQuery({
    queryKey: ['player-saved-queue'],
    queryFn: playerApi.savedQueue,
    refetchInterval: 60_000,
    refetchOnWindowFocus: true,
  })
  const s = saved.data
  if (!s?.exists || !s.updated_at || q.playing) return null
  if (s.device_id === getDeviceId()) return null
  if (Date.now() - new Date(s.updated_at).getTime() > MAX_AGE_MS) return null
  if (dismissed === s.updated_at) return null

  const current = s.tracks[s.index]
  const dismiss = () => {
    try {
      sessionStorage.setItem(DISMISS_KEY, s.updated_at!)
    } catch {
      /* storage unavailable */
    }
    setDismissed(s.updated_at)
  }

  return (
    <div className="banner" style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
      <span style={{ flex: 1, minWidth: 200 }}>
        Playing on <strong>{s.device_name || 'another device'}</strong>
        {current ? (
          <>
            : {current.title} <span className="muted">· {current.artist_name}</span>
          </>
        ) : null}
      </span>
      <button
        type="button"
        className="btn"
        onClick={() => {
          q.playTracks(s.tracks, s.index, s.source_label || undefined, s.position)
          dismiss()
        }}
      >
        Continue here
      </button>
      <button type="button" className="btn ghost" onClick={dismiss}>
        Dismiss
      </button>
    </div>
  )
}
