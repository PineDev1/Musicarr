import { useMutation } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { useToast } from '../Toast'

function urlBase64ToUint8Array(base64: string): BufferSource {
  const padding = '='.repeat((4 - (base64.length % 4)) % 4)
  const base64Safe = (base64 + padding).replace(/-/g, '+').replace(/_/g, '/')
  const raw = window.atob(base64Safe)
  const out = new Uint8Array(raw.length)
  for (let i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i)
  return out.buffer
}

export function PushNotificationsPanel() {
  const toast = useToast()
  const [supported, setSupported] = useState(false)
  const [subscribed, setSubscribed] = useState(false)
  const [checking, setChecking] = useState(true)

  useEffect(() => {
    let cancelled = false
    async function check() {
      const ok = 'serviceWorker' in navigator && 'PushManager' in window
      setSupported(ok)
      if (!ok) {
        setChecking(false)
        return
      }
      try {
        const reg = await navigator.serviceWorker.ready
        const sub = await reg.pushManager.getSubscription()
        if (!cancelled) setSubscribed(!!sub)
      } catch {
        /* ignore */
      } finally {
        if (!cancelled) setChecking(false)
      }
    }
    check()
    return () => {
      cancelled = true
    }
  }, [])

  const subscribe = useMutation({
    mutationFn: async () => {
      const permission = await Notification.requestPermission()
      if (permission !== 'granted') throw new Error('Notification permission denied')
      const reg = await navigator.serviceWorker.ready
      const keyRes = await fetch('/api/push/vapid-public-key', { credentials: 'include' })
      const { public_key } = await keyRes.json()
      const sub = await reg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(public_key),
      })
      const json = sub.toJSON()
      await fetch('/api/push/subscribe', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          endpoint: json.endpoint,
          p256dh: json.keys?.p256dh || '',
          auth: json.keys?.auth || '',
        }),
      })
    },
    onSuccess: () => {
      setSubscribed(true)
      toast.push('Push notifications enabled on this device', 'ok')
    },
    onError: (err) => toast.push((err as Error).message, 'error'),
  })

  const unsubscribe = useMutation({
    mutationFn: async () => {
      const reg = await navigator.serviceWorker.ready
      const sub = await reg.pushManager.getSubscription()
      if (!sub) return
      const endpoint = sub.endpoint
      await sub.unsubscribe()
      await fetch('/api/push/unsubscribe', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ endpoint, p256dh: '', auth: '' }),
      })
    },
    onSuccess: () => {
      setSubscribed(false)
      toast.push('Push notifications disabled on this device', 'ok')
    },
    onError: (err) => toast.push((err as Error).message, 'error'),
  })

  const test = useMutation({
    mutationFn: async () => {
      const res = await fetch('/api/push/test', { method: 'POST', credentials: 'include' })
      return res.json()
    },
    onSuccess: (res) =>
      toast.push(res.sent > 0 ? `Sent to ${res.sent} device(s)` : 'No devices subscribed', res.sent > 0 ? 'ok' : 'error'),
    onError: (err) => toast.push((err as Error).message, 'error'),
  })

  return (
    <div>
      <h3 style={{ margin: '0 0 0.25rem', fontSize: '1.05rem' }}>Browser push notifications</h3>
      <p className="muted" style={{ marginTop: 0, maxWidth: 560 }}>
        Get download-complete, failure, maintenance, and health alerts as browser notifications on
        this device — no webhook receiver needed.
      </p>
      {!supported && <p className="muted">Not supported in this browser.</p>}
      {supported && !checking && (
        <div className="toolbar">
          {!subscribed && (
            <button
              type="button"
              className="btn"
              disabled={subscribe.isPending}
              onClick={() => subscribe.mutate()}
            >
              Enable on this device
            </button>
          )}
          {subscribed && (
            <>
              <span className="badge queued">Enabled on this device</span>
              <button
                type="button"
                className="btn ghost"
                disabled={unsubscribe.isPending}
                onClick={() => unsubscribe.mutate()}
              >
                Disable
              </button>
              <button
                type="button"
                className="btn secondary"
                disabled={test.isPending}
                onClick={() => test.mutate()}
              >
                Send test push
              </button>
            </>
          )}
        </div>
      )}
    </div>
  )
}
