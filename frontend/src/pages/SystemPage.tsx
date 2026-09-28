import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { api } from '../api'

function formatBytes(n: number) {
  if (!n) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.min(units.length - 1, Math.floor(Math.log(n) / Math.log(1024)))
  return `${(n / 1024 ** i).toFixed(i ? 1 : 0)} ${units[i]}`
}

function formatUptime(sec: number) {
  const d = Math.floor(sec / 86400)
  const h = Math.floor((sec % 86400) / 3600)
  const m = Math.floor((sec % 3600) / 60)
  return [d && `${d}d`, (d || h) && `${h}h`, `${m}m`].filter(Boolean).join(' ')
}

function when(iso: string | null) {
  if (!iso) return '—'
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString()
}

export function SystemPage() {
  const [level, setLevel] = useState('INFO')
  const [search, setSearch] = useState('')
  const status = useQuery({ queryKey: ['system-status'], queryFn: api.systemStatus, refetchInterval: 30000 })
  const logs = useQuery({
    queryKey: ['system-logs', level, search],
    queryFn: () => api.systemLogs(level, search),
    refetchInterval: 5000,
  })
  const s = status.data

  return (
    <div>
      <div className="page-header">
        <div>
          <h1>System</h1>
          <p>Server status, scheduled tasks, and recent logs.</p>
        </div>
      </div>
      {status.error && <div className="banner warn">{(status.error as Error).message}</div>}
      {s && (
        <div className="card" style={{ marginBottom: '1rem' }}>
          <div className="toolbar" style={{ gap: '2rem', flexWrap: 'wrap' }}>
            <div><div className="muted">Version</div><strong>{s.version}</strong></div>
            <div><div className="muted">Uptime</div><strong>{formatUptime(s.uptime_seconds)}</strong></div>
            <div><div className="muted">Database</div><strong>{formatBytes(s.db_bytes)}</strong></div>
            <div>
              <div className="muted">Library disk free</div>
              <strong>{s.disk ? `${formatBytes(s.disk.free)} of ${formatBytes(s.disk.total)}` : 'unknown'}</strong>
            </div>
            <div><div className="muted">Python</div><strong>{s.python}</strong></div>
            <div><div className="muted">Host</div><strong>{s.platform}</strong></div>
          </div>
          <p className="muted tiny" style={{ marginBottom: 0 }}>Data directory: {s.data_dir}</p>
        </div>
      )}

      {!!s?.tasks.length && (
        <>
          <h2>Scheduled tasks</h2>
          <table className="table">
            <thead>
              <tr>
                <th>Task</th>
                <th>Schedule</th>
                <th>Next run</th>
              </tr>
            </thead>
            <tbody>
              {s.tasks.map((t) => (
                <tr key={t.id}>
                  <td>{t.name}</td>
                  <td className="muted">{t.trigger}</td>
                  <td className="muted">{when(t.next_run)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}

      <div className="page-header" style={{ marginTop: '1.5rem' }}>
        <h2 style={{ margin: 0 }}>Logs</h2>
        <div className="toolbar">
          <select value={level} onChange={(e) => setLevel(e.target.value)}>
            <option value="INFO">Info and up</option>
            <option value="WARNING">Warnings and up</option>
            <option value="ERROR">Errors only</option>
          </select>
          <input
            type="text"
            placeholder="Filter…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
      </div>
      <p className="muted tiny">
        Since the server last started. Keys, tokens and passwords are masked. Newest first.
      </p>
      <pre
        style={{
          maxHeight: 480,
          overflow: 'auto',
          fontSize: 12,
          lineHeight: 1.45,
          background: 'var(--bg-soft)',
          padding: 12,
          borderRadius: 8,
          whiteSpace: 'pre-wrap',
          wordBreak: 'break-word',
        }}
      >
        {logs.data?.length
          ? logs.data
              .map((l) => `${l.time.slice(11, 19)} ${l.level.padEnd(7)} ${l.logger}: ${l.message}`)
              .join('\n')
          : 'No log lines match.'}
      </pre>
    </div>
  )
}
