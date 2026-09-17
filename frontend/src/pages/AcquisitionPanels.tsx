import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { api, type DownloadClient, type Indexer, type RemotePathMapping } from '../api'
import { useToast } from '../Toast'

export function AcquisitionReadinessBanner() {
  const { data } = useQuery({ queryKey: ['acquisition-status'], queryFn: api.acquisitionStatus })
  if (!data?.messages?.length) return null
  return (
    <div className="banner warn" style={{ marginBottom: '1rem' }}>
      <strong>Indexers &amp; download clients</strong>
      <ul style={{ margin: '0.5rem 0 0', paddingLeft: '1.2rem' }}>
        {data.messages.map((m) => (
          <li key={m}>{m}</li>
        ))}
      </ul>
    </div>
  )
}

export function AcquisitionPanels() {
  return (
    <>
      <AcquisitionReadinessBanner />
      <IndexersPanel />
      <ClientsPanel />
      <PathMappingsPanel />
    </>
  )
}

function IndexersPanel() {
  const qc = useQueryClient()
  const toast = useToast()
  const { data, isLoading } = useQuery({ queryKey: ['indexers'], queryFn: api.indexers })
  const [name, setName] = useState('')
  const [baseUrl, setBaseUrl] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [protocol, setProtocol] = useState<'usenet' | 'torrent'>('torrent')
  const [testResult, setTestResult] = useState<Record<number, string>>({})

  const create = useMutation({
    mutationFn: () =>
      api.createIndexer({
        name: name.trim(),
        base_url: baseUrl.trim(),
        api_key: apiKey.trim(),
        protocol,
        implementation: protocol === 'torrent' ? 'torznab' : 'newznab',
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['indexers'] })
      qc.invalidateQueries({ queryKey: ['acquisition-status'] })
      setName('')
      setBaseUrl('')
      setApiKey('')
      toast.push('Indexer added', 'ok')
    },
    onError: (err) => toast.push((err as Error).message, 'error'),
  })

  const toggle = useMutation({
    mutationFn: (row: Indexer) => api.updateIndexer(row.id, { enabled: !row.enabled }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['indexers'] }),
  })

  const remove = useMutation({
    mutationFn: (id: number) => api.deleteIndexer(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['indexers'] })
      qc.invalidateQueries({ queryKey: ['acquisition-status'] })
    },
  })

  const test = useMutation({
    mutationFn: (id: number) => api.testIndexer(id),
    onSuccess: (result, id) => setTestResult((prev) => ({ ...prev, [id]: result.message })),
    onError: (err, id) => setTestResult((prev) => ({ ...prev, [id]: (err as Error).message })),
  })

  return (
    <div className="card" style={{ marginBottom: '1.5rem' }}>
      <h3 style={{ margin: '0 0 0.25rem', fontSize: '1.05rem' }}>Indexers</h3>
      <p className="muted" style={{ marginTop: 0, maxWidth: 640 }}>
        Newznab (Usenet) or Torznab (torrent) indexers — a Prowlarr Torznab/Newznab feed URL works
        directly. Used only for manual "Search releases" on an album; nothing is auto-grabbed
        unless it scores high enough to pass the legitimacy check.
      </p>
      <div className="toolbar" style={{ flexWrap: 'wrap', alignItems: 'flex-end' }}>
        <div className="field" style={{ margin: 0 }}>
          <label>Name</label>
          <input value={name} onChange={(e) => setName(e.target.value)} />
        </div>
        <div className="field" style={{ margin: 0 }}>
          <label>Protocol</label>
          <select value={protocol} onChange={(e) => setProtocol(e.target.value as 'usenet' | 'torrent')}>
            <option value="torrent">Torrent (Torznab)</option>
            <option value="usenet">Usenet (Newznab)</option>
          </select>
        </div>
        <div className="field" style={{ margin: 0, minWidth: 260 }}>
          <label>Base URL</label>
          <input
            value={baseUrl}
            onChange={(e) => setBaseUrl(e.target.value)}
            placeholder="https://prowlarr.example.com/1/api"
          />
        </div>
        <div className="field" style={{ margin: 0 }}>
          <label>API key</label>
          <input value={apiKey} onChange={(e) => setApiKey(e.target.value)} autoComplete="off" />
        </div>
        <button
          type="button"
          className="btn"
          disabled={!name.trim() || !baseUrl.trim() || create.isPending}
          onClick={() => create.mutate()}
        >
          Add indexer
        </button>
      </div>
      {isLoading && <p className="muted">Loading…</p>}
      {!isLoading && (data?.length ?? 0) === 0 && <p className="muted">No indexers configured.</p>}
      {(data?.length ?? 0) > 0 && (
        <table className="table" style={{ marginTop: '1rem' }}>
          <thead>
            <tr>
              <th>Name</th>
              <th>Protocol</th>
              <th>Base URL</th>
              <th>Enabled</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {data!.map((row) => (
              <tr key={row.id}>
                <td>
                  <strong>{row.name}</strong>
                </td>
                <td className="muted">{row.protocol}</td>
                <td className="muted">{row.base_url}</td>
                <td>{row.enabled ? 'Yes' : 'No'}</td>
                <td className="row-actions">
                  <button type="button" className="btn ghost" onClick={() => test.mutate(row.id)}>
                    Test
                  </button>
                  <button type="button" className="btn ghost" onClick={() => toggle.mutate(row)}>
                    {row.enabled ? 'Disable' : 'Enable'}
                  </button>
                  <button type="button" className="btn ghost danger" onClick={() => remove.mutate(row.id)}>
                    Delete
                  </button>
                  {testResult[row.id] && (
                    <span className="muted" style={{ marginLeft: 8 }}>
                      {testResult[row.id]}
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}

function ClientsPanel() {
  const qc = useQueryClient()
  const toast = useToast()
  const { data, isLoading } = useQuery({ queryKey: ['download-clients'], queryFn: api.downloadClients })
  const [name, setName] = useState('')
  const [implementation, setImplementation] = useState<'qbittorrent' | 'sabnzbd'>('qbittorrent')
  const [host, setHost] = useState('localhost')
  const [port, setPort] = useState(8080)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [testResult, setTestResult] = useState<Record<number, string>>({})

  const create = useMutation({
    mutationFn: () =>
      api.createDownloadClient({
        name: name.trim(),
        implementation,
        protocol: implementation === 'qbittorrent' ? 'torrent' : 'usenet',
        host: host.trim() || 'localhost',
        port,
        username: username.trim(),
        password,
        api_key: apiKey.trim(),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['download-clients'] })
      qc.invalidateQueries({ queryKey: ['acquisition-status'] })
      setName('')
      setPassword('')
      setApiKey('')
      toast.push('Download client added', 'ok')
    },
    onError: (err) => toast.push((err as Error).message, 'error'),
  })

  const toggle = useMutation({
    mutationFn: (row: DownloadClient) => api.updateDownloadClient(row.id, { enabled: !row.enabled }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['download-clients'] }),
  })

  const remove = useMutation({
    mutationFn: (id: number) => api.deleteDownloadClient(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['download-clients'] })
      qc.invalidateQueries({ queryKey: ['acquisition-status'] })
    },
  })

  const test = useMutation({
    mutationFn: (id: number) => api.testDownloadClient(id),
    onSuccess: (result, id) => setTestResult((prev) => ({ ...prev, [id]: result.message })),
    onError: (err, id) => setTestResult((prev) => ({ ...prev, [id]: (err as Error).message })),
  })

  return (
    <div className="card" style={{ marginBottom: '1.5rem' }}>
      <h3 style={{ margin: '0 0 0.25rem', fontSize: '1.05rem' }}>Download clients</h3>
      <p className="muted" style={{ marginTop: 0, maxWidth: 640 }}>
        qBittorrent (torrents) or SABnzbd (Usenet). If the client runs in a different container
        than Musicarr, add a path mapping below so completed downloads can be found.
      </p>
      <div className="toolbar" style={{ flexWrap: 'wrap', alignItems: 'flex-end' }}>
        <div className="field" style={{ margin: 0 }}>
          <label>Name</label>
          <input value={name} onChange={(e) => setName(e.target.value)} />
        </div>
        <div className="field" style={{ margin: 0 }}>
          <label>Client</label>
          <select
            value={implementation}
            onChange={(e) => setImplementation(e.target.value as 'qbittorrent' | 'sabnzbd')}
          >
            <option value="qbittorrent">qBittorrent</option>
            <option value="sabnzbd">SABnzbd</option>
          </select>
        </div>
        <div className="field" style={{ margin: 0 }}>
          <label>Host</label>
          <input value={host} onChange={(e) => setHost(e.target.value)} placeholder="qbittorrent" />
        </div>
        <div className="field" style={{ margin: 0, width: 90 }}>
          <label>Port</label>
          <input type="number" value={port} onChange={(e) => setPort(Number(e.target.value) || 0)} />
        </div>
        {implementation === 'qbittorrent' ? (
          <>
            <div className="field" style={{ margin: 0 }}>
              <label>Username</label>
              <input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="off" />
            </div>
            <div className="field" style={{ margin: 0 }}>
              <label>Password</label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="new-password"
              />
            </div>
          </>
        ) : (
          <div className="field" style={{ margin: 0 }}>
            <label>API key</label>
            <input value={apiKey} onChange={(e) => setApiKey(e.target.value)} autoComplete="off" />
          </div>
        )}
        <button
          type="button"
          className="btn"
          disabled={!name.trim() || !host.trim() || create.isPending}
          onClick={() => create.mutate()}
        >
          Add client
        </button>
      </div>
      {isLoading && <p className="muted">Loading…</p>}
      {!isLoading && (data?.length ?? 0) === 0 && <p className="muted">No download clients configured.</p>}
      {(data?.length ?? 0) > 0 && (
        <table className="table" style={{ marginTop: '1rem' }}>
          <thead>
            <tr>
              <th>Name</th>
              <th>Client</th>
              <th>Address</th>
              <th>Enabled</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {data!.map((row) => (
              <tr key={row.id}>
                <td>
                  <strong>{row.name}</strong>
                </td>
                <td className="muted">{row.implementation}</td>
                <td className="muted">{row.base_url}</td>
                <td>{row.enabled ? 'Yes' : 'No'}</td>
                <td className="row-actions">
                  <button type="button" className="btn ghost" onClick={() => test.mutate(row.id)}>
                    Test
                  </button>
                  <button type="button" className="btn ghost" onClick={() => toggle.mutate(row)}>
                    {row.enabled ? 'Disable' : 'Enable'}
                  </button>
                  <button type="button" className="btn ghost danger" onClick={() => remove.mutate(row.id)}>
                    Delete
                  </button>
                  {testResult[row.id] && (
                    <span className="muted" style={{ marginLeft: 8 }}>
                      {testResult[row.id]}
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}

function PathMappingsPanel() {
  const qc = useQueryClient()
  const { data, isLoading } = useQuery({ queryKey: ['path-mappings'], queryFn: api.pathMappings })
  const [remotePath, setRemotePath] = useState('')
  const [localPath, setLocalPath] = useState('')

  const create = useMutation({
    mutationFn: () =>
      api.createPathMapping({ remote_path: remotePath.trim(), local_path: localPath.trim() }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['path-mappings'] })
      qc.invalidateQueries({ queryKey: ['acquisition-status'] })
      setRemotePath('')
      setLocalPath('')
    },
  })

  const remove = useMutation({
    mutationFn: (id: number) => api.deletePathMapping(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['path-mappings'] })
      qc.invalidateQueries({ queryKey: ['acquisition-status'] })
    },
  })

  return (
    <div className="card">
      <h3 style={{ margin: '0 0 0.25rem', fontSize: '1.05rem' }}>Remote path mappings</h3>
      <p className="muted" style={{ marginTop: 0, maxWidth: 640 }}>
        If your download client runs in a different container, mount its completed-downloads
        folder into Musicarr too, then map the client's path to the path Musicarr sees it at.
      </p>
      <div className="toolbar" style={{ flexWrap: 'wrap', alignItems: 'flex-end' }}>
        <div className="field" style={{ margin: 0, minWidth: 220 }}>
          <label>Client path</label>
          <input
            value={remotePath}
            onChange={(e) => setRemotePath(e.target.value)}
            placeholder="/data/completed"
          />
        </div>
        <div className="field" style={{ margin: 0, minWidth: 220 }}>
          <label>Musicarr path</label>
          <input
            value={localPath}
            onChange={(e) => setLocalPath(e.target.value)}
            placeholder="/downloads"
          />
        </div>
        <button
          type="button"
          className="btn"
          disabled={!remotePath.trim() || !localPath.trim() || create.isPending}
          onClick={() => create.mutate()}
        >
          Add mapping
        </button>
      </div>
      {isLoading && <p className="muted">Loading…</p>}
      {!isLoading && (data?.length ?? 0) === 0 && <p className="muted">No path mappings configured.</p>}
      {(data?.length ?? 0) > 0 && (
        <table className="table" style={{ marginTop: '1rem' }}>
          <thead>
            <tr>
              <th>Client path</th>
              <th>Musicarr path</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {data!.map((row: RemotePathMapping) => (
              <tr key={row.id}>
                <td>{row.remote_path}</td>
                <td>{row.local_path}</td>
                <td className="row-actions">
                  <button type="button" className="btn ghost danger" onClick={() => remove.mutate(row.id)}>
                    Delete
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
