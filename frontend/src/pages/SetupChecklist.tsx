import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'

const DISMISS_KEY = 'musicarr-checklist-dismissed'

/** Dashboard card: what's left to set up, each with a link straight to the fix. */
export function SetupChecklist() {
  const { data } = useQuery({ queryKey: ['setup-checklist'], queryFn: api.checklist, refetchInterval: 60000 })
  const [dismissed, setDismissed] = useState(() => {
    try {
      return localStorage.getItem(DISMISS_KEY) === '1'
    } catch {
      return false
    }
  })
  if (!data || dismissed || data.items.every((i) => i.status === 'ok')) return null

  return (
    <div className="card" style={{ marginBottom: '1rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: '1rem' }}>
        <h3 style={{ margin: 0 }}>
          Setup checklist{' '}
          <span className="muted" style={{ fontSize: '0.85rem', fontWeight: 400 }}>
            {data.done} of {data.total} done
          </span>
        </h3>
        <button
          type="button"
          className="btn ghost"
          onClick={() => {
            try {
              localStorage.setItem(DISMISS_KEY, '1')
            } catch {
              /* storage unavailable */
            }
            setDismissed(true)
          }}
        >
          Hide
        </button>
      </div>
      <div style={{ marginTop: '0.5rem' }}>
        {data.items.map((item) => (
          <div className="checklist-item" key={item.key}>
            <span className={`checklist-dot ${item.status}`} aria-hidden>
              {item.status === 'ok' ? '✓' : ''}
            </span>
            <div style={{ flex: 1 }}>
              <div>
                {item.status === 'ok' ? (
                  item.label
                ) : (
                  <Link to={item.link}>{item.label}</Link>
                )}
                {item.status === 'optional' && (
                  <span className="muted" style={{ fontSize: '0.8rem' }}>
                    {' '}
                    · optional
                  </span>
                )}
              </div>
              <div className="muted" style={{ fontSize: '0.82rem' }}>
                {item.detail}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
