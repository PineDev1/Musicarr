import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import {
  api,
  type DownloadClientRow,
  type Indexer,
  type PathMapping,
} from '../api'
import { useToast } from '../Toast'

export function AcquisitionPanels({ panel }: { panel: 'indexers' | 'clients' | 'paths' }) {
  if (panel === 'indexers') return <IndexersPanel />
  if (panel === 'clients') return <ClientsPanel />
  return <PathsPanel />
}

function IndexersPanel() {
  const qc = useQueryClient()
  const toast = useToast()
  const { data, isLoading } = useQuery({ queryKey: ['indexers'], queryFn: api.indexers })
  const [name, setName] = useState('')
  const [baseUrl, setBaseUrl] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [protocol, setProtocol] = useState('torrent')
  const [implementation, setImplementation] = useState('torznab')

  const create = useMutation({
    mutationFn: () =>
      api.createIndexer({
        name: name.trim(),
        base_url: baseUrl.trim(),
        api_key: apiKey.trim(),
        protocol,
        implementation,
        enabled: true,
        priority: 25,
        categories: [3000, 3010, 3040],
      }),
    onSuccess: () => {
      setName('')
      setBaseUrl('')
      setApiKey('')
      toast.push('Indexer added', 'ok')
      qc.invalidateQueries({ queryKey: ['indexers'] })
    },
    onError: (err) => toast.push((err as Error).message, 'error'),
  })
  const update = useMutation({
    mutationFn: ({ id, body }: { id: number; body: Record<string, unknown> }) =>
      api.updateIndexer(id, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['indexers'] }),
    onError: (err) => toast.push((err as Error).message, 'error'),
  })
  const remove = useMutation({
    mutationFn: (id: number) => api.deleteIndexer(id),
    onSuccess: () => {
      toast.push('Indexer removed', 'ok')
      qc.invalidateQueries({ queryKey: ['indexers'] })
    },
    onError: (err) => toast.push((err as Error).message, 'error'),
  })
  const test = useMutation({
    mutationFn: (id: number) => api.testIndexer(id),
    onSuccess: (res) => toast.push(res.message || (res.ok ? 'OK' : 'Failed'), res.ok ? 'ok' : 'error'),
    onError: (err) => toast.push((err as Error).message, 'error'),
  })

  return (
    <>
      <p className="muted">
        Add Newznab (Usenet) or Torznab (torrent) indexers. Prowlarr works by pointing at its
        Torznab/Newznab app feed URL.
      </p>
      <div className="card" style={{ marginBottom: '1rem' }}>
        <h3 style={{ marginTop: 0 }}>Add indexer</h3>
        <div className="field">
          <label>Name</label>
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Prowlarr" />
        </div>
        <div className="field">
          <label>Protocol</label>
          <select
            value={protocol}
            onChange={(e) => {
              const p = e.target.value
              setProtocol(p)
              setImplementation(p === 'usenet' ? 'newznab' : 'torznab')
            }}
          >
            <option value="torrent">Torrent (Torznab)</option>
            <option value="usenet">Usenet (Newznab)</option>
          </select>
        </div>
        <div className="field">
          <label>Base URL</label>
          <input
            value={baseUrl}
            onChange={(e) => setBaseUrl(e.target.value)}
            placeholder="http://prowlarr:9696/1/api"
          />
        </div>
        <div className="field">
          <label>API key</label>
          <input value={apiKey} onChange={(e) => setApiKey(e.target.value)} type="password" />
        </div>
        <button
          className="btn"
          type="button"
          disabled={!name.trim() || !baseUrl.trim() || create.isPending}
          onClick={() => create.mutate()}
        >
          Add indexer
        </button>
      </div>
      {isLoading && <p className="muted">Loading…</p>}
      <IndexerTable
        rows={data || []}
        onToggle={(row) => update.mutate({ id: row.id, body: { enabled: !row.enabled } })}
        onTest={(id) => test.mutate(id)}
        onDelete={(id) => {
          if (window.confirm('Remove this indexer?')) remove.mutate(id)
        }}
      />
    </>
  )
}

function IndexerTable({
  rows,
  onToggle,
  onTest,
  onDelete,
}: {
  rows: Indexer[]
  onToggle: (row: Indexer) => void
  onTest: (id: number) => void
  onDelete: (id: number) => void
}) {
  if (!rows.length) return <p className="muted">No indexers configured yet.</p>
  return (
    <table className="table">
      <thead>
        <tr>
          <th>Name</th>
          <th>Protocol</th>
          <th>URL</th>
          <th>Priority</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.id}>
            <td>
              <strong>{row.name}</strong>
              <div className="muted tiny">{row.enabled ? 'Enabled' : 'Disabled'}</div>
            </td>
            <td>
              {row.protocol} / {row.implementation}
            </td>
            <td className="muted" style={{ wordBreak: 'break-all' }}>
              {row.base_url}
            </td>
            <td>{row.priority}</td>
            <td className="row-actions">
              <button className="btn ghost" type="button" onClick={() => onToggle(row)}>
                {row.enabled ? 'Disable' : 'Enable'}
              </button>
              <button className="btn secondary" type="button" onClick={() => onTest(row.id)}>
                Test
              </button>
              <button className="btn ghost" type="button" onClick={() => onDelete(row.id)}>
                Delete
              </button>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function ClientsPanel() {
  const qc = useQueryClient()
  const toast = useToast()
  const { data, isLoading } = useQuery({
    queryKey: ['download-clients'],
    queryFn: api.downloadClients,
  })
  const [name, setName] = useState('')
  const [implementation, setImplementation] = useState('qbittorrent')
  const [host, setHost] = useState('localhost')
  const [port, setPort] = useState(8080)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [category, setCategory] = useState('musicarr')
  const [useSsl, setUseSsl] = useState(false)

  const create = useMutation({
    mutationFn: () =>
      api.createDownloadClient({
        name: name.trim(),
        implementation,
        protocol: implementation === 'sabnzbd' ? 'usenet' : 'torrent',
        host: host.trim(),
        port,
        use_ssl: useSsl,
        username: username.trim(),
        password: password,
        api_key: apiKey.trim(),
        category: category.trim() || 'musicarr',
        enabled: true,
        priority: 1,
      }),
    onSuccess: () => {
      setName('')
      setPassword('')
      setApiKey('')
      toast.push('Download client added', 'ok')
      qc.invalidateQueries({ queryKey: ['download-clients'] })
    },
    onError: (err) => toast.push((err as Error).message, 'error'),
  })
  const update = useMutation({
    mutationFn: ({ id, body }: { id: number; body: Record<string, unknown> }) =>
      api.updateDownloadClient(id, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['download-clients'] }),
    onError: (err) => toast.push((err as Error).message, 'error'),
  })
  const remove = useMutation({
    mutationFn: (id: number) => api.deleteDownloadClient(id),
    onSuccess: () => {
      toast.push('Client removed', 'ok')
      qc.invalidateQueries({ queryKey: ['download-clients'] })
    },
    onError: (err) => toast.push((err as Error).message, 'error'),
  })
  const test = useMutation({
    mutationFn: (id: number) => api.testDownloadClient(id),
    onSuccess: (res) => toast.push(res.message || (res.ok ? 'OK' : 'Failed'), res.ok ? 'ok' : 'error'),
    onError: (err) => toast.push((err as Error).message, 'error'),
  })

  return (
    <>
      <p className="muted">
        Musicarr sends grabs to the client and imports finished files from the path the client
        reports — after remote path mapping.
      </p>
      <div className="card" style={{ marginBottom: '1rem' }}>
        <h3 style={{ marginTop: 0 }}>Add download client</h3>
        <div className="field">
          <label>Name</label>
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="qBittorrent" />
        </div>
        <div className="field">
          <label>Type</label>
          <select
            value={implementation}
            onChange={(e) => {
              const v = e.target.value
              setImplementation(v)
              setPort(v === 'sabnzbd' ? 8080 : 8080)
            }}
          >
            <option value="qbittorrent">qBittorrent</option>
            <option value="sabnzbd">SABnzbd</option>
          </select>
        </div>
        <div className="field">
          <label>Host</label>
          <input value={host} onChange={(e) => setHost(e.target.value)} />
        </div>
        <div className="field">
          <label>Port</label>
          <input
            type="number"
            value={port}
            onChange={(e) => setPort(Number(e.target.value))}
          />
        </div>
        <label className="checks">
          <input type="checkbox" checked={useSsl} onChange={(e) => setUseSsl(e.target.checked)} />
          Use SSL
        </label>
        {implementation === 'qbittorrent' ? (
          <>
            <div className="field">
              <label>Username</label>
              <input value={username} onChange={(e) => setUsername(e.target.value)} />
            </div>
            <div className="field">
              <label>Password</label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </div>
          </>
        ) : (
          <div className="field">
            <label>API key</label>
            <input type="password" value={apiKey} onChange={(e) => setApiKey(e.target.value)} />
          </div>
        )}
        <div className="field">
          <label>Category</label>
          <input value={category} onChange={(e) => setCategory(e.target.value)} />
          <span className="muted tiny">Only this category is imported (default musicarr).</span>
        </div>
        <button
          className="btn"
          type="button"
          disabled={!name.trim() || !host.trim() || create.isPending}
          onClick={() => create.mutate()}
        >
          Add client
        </button>
      </div>
      {isLoading && <p className="muted">Loading…</p>}
      <ClientTable
        rows={data || []}
        onToggle={(row) => update.mutate({ id: row.id, body: { enabled: !row.enabled } })}
        onTest={(id) => test.mutate(id)}
        onDelete={(id) => {
          if (window.confirm('Remove this download client?')) remove.mutate(id)
        }}
      />
    </>
  )
}

function ClientTable({
  rows,
  onToggle,
  onTest,
  onDelete,
}: {
  rows: DownloadClientRow[]
  onToggle: (row: DownloadClientRow) => void
  onTest: (id: number) => void
  onDelete: (id: number) => void
}) {
  if (!rows.length) return <p className="muted">No download clients configured yet.</p>
  return (
    <table className="table">
      <thead>
        <tr>
          <th>Name</th>
          <th>Type</th>
          <th>Endpoint</th>
          <th>Category</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.id}>
            <td>
              <strong>{row.name}</strong>
              <div className="muted tiny">{row.enabled ? 'Enabled' : 'Disabled'}</div>
            </td>
            <td>{row.implementation}</td>
            <td className="muted">
              {row.use_ssl ? 'https' : 'http'}://{row.host}:{row.port}
            </td>
            <td>{row.category}</td>
            <td className="row-actions">
              <button className="btn ghost" type="button" onClick={() => onToggle(row)}>
                {row.enabled ? 'Disable' : 'Enable'}
              </button>
              <button className="btn secondary" type="button" onClick={() => onTest(row.id)}>
                Test
              </button>
              <button className="btn ghost" type="button" onClick={() => onDelete(row.id)}>
                Delete
              </button>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function PathsPanel() {
  const qc = useQueryClient()
  const toast = useToast()
  const { data, isLoading } = useQuery({ queryKey: ['path-mappings'], queryFn: api.pathMappings })
  const [remote, setRemote] = useState('')
  const [local, setLocal] = useState('')
  const [host, setHost] = useState('')

  const create = useMutation({
    mutationFn: () =>
      api.createPathMapping({
        remote_path: remote.trim(),
        local_path: local.trim(),
        host: host.trim(),
      }),
    onSuccess: () => {
      setRemote('')
      setLocal('')
      setHost('')
      toast.push('Path mapping added', 'ok')
      qc.invalidateQueries({ queryKey: ['path-mappings'] })
    },
    onError: (err) => toast.push((err as Error).message, 'error'),
  })
  const remove = useMutation({
    mutationFn: (id: number) => api.deletePathMapping(id),
    onSuccess: () => {
      toast.push('Mapping removed', 'ok')
      qc.invalidateQueries({ queryKey: ['path-mappings'] })
    },
    onError: (err) => toast.push((err as Error).message, 'error'),
  })

  return (
    <>
      <p className="muted">
        Map the path your download client reports to the path Musicarr can see. Example: client
        writes <code>/data/completed/Album</code>, Musicarr mounts that volume at{' '}
        <code>/downloads</code> → remote <code>/data/completed</code>, local <code>/downloads</code>.
      </p>
      <div className="card" style={{ marginBottom: '1rem' }}>
        <h3 style={{ marginTop: 0 }}>Add mapping</h3>
        <div className="field">
          <label>Remote path (as seen by the client)</label>
          <input
            value={remote}
            onChange={(e) => setRemote(e.target.value)}
            placeholder="/data/completed"
          />
        </div>
        <div className="field">
          <label>Local path (as seen by Musicarr)</label>
          <input
            value={local}
            onChange={(e) => setLocal(e.target.value)}
            placeholder="/downloads"
          />
        </div>
        <div className="field">
          <label>Host match (optional)</label>
          <input
            value={host}
            onChange={(e) => setHost(e.target.value)}
            placeholder="Leave blank for any"
          />
        </div>
        <button
          className="btn"
          type="button"
          disabled={!remote.trim() || !local.trim() || create.isPending}
          onClick={() => create.mutate()}
        >
          Add mapping
        </button>
      </div>
      {isLoading && <p className="muted">Loading…</p>}
      <MappingTable
        rows={data || []}
        onDelete={(id) => {
          if (window.confirm('Remove this path mapping?')) remove.mutate(id)
        }}
      />
    </>
  )
}

function MappingTable({
  rows,
  onDelete,
}: {
  rows: PathMapping[]
  onDelete: (id: number) => void
}) {
  if (!rows.length) return <p className="muted">No path mappings yet.</p>
  return (
    <table className="table">
      <thead>
        <tr>
          <th>Remote</th>
          <th>Local</th>
          <th>Host</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.id}>
            <td>
              <code>{row.remote_path}</code>
            </td>
            <td>
              <code>{row.local_path}</code>
            </td>
            <td className="muted">{row.host || '—'}</td>
            <td className="row-actions">
              <button className="btn ghost" type="button" onClick={() => onDelete(row.id)}>
                Delete
              </button>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}
