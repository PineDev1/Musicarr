import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import {
  api,
  type DownloadClientRow,
  type Indexer,
  type PathMapping,
} from '../api'
import { useToast } from '../Toast'

export function AcquisitionReadinessBanner({
  onGoTo,
}: {
  onGoTo?: (tab: 'indexers' | 'clients' | 'paths') => void
}) {
  const { data } = useQuery({
    queryKey: ['acquisition-status'],
    queryFn: api.acquisitionStatus,
  })
  if (!data?.messages?.length) return null
  return (
    <div className="banner warn" style={{ marginBottom: '1rem' }}>
      <strong>Acquisition setup</strong>
      <ul style={{ margin: '0.5rem 0 0', paddingLeft: '1.2rem' }}>
        {data.messages.map((m) => (
          <li key={m}>{m}</li>
        ))}
      </ul>
      {onGoTo && (
        <div className="toolbar" style={{ marginTop: '0.65rem', marginBottom: 0 }}>
          {!data.indexers_enabled && (
            <button type="button" className="btn secondary" onClick={() => onGoTo('indexers')}>
              Indexers
            </button>
          )}
          {(!data.torrent_client || !data.usenet_client) && (
            <button type="button" className="btn secondary" onClick={() => onGoTo('clients')}>
              Download clients
            </button>
          )}
          {!data.path_mappings && (data.torrent_client || data.usenet_client) && (
            <button type="button" className="btn secondary" onClick={() => onGoTo('paths')}>
              Path mappings
            </button>
          )}
        </div>
      )}
    </div>
  )
}

export function AcquisitionPanels({
  panel,
  onGoTo,
}: {
  panel: 'indexers' | 'clients' | 'paths'
  onGoTo?: (tab: 'indexers' | 'clients' | 'paths') => void
}) {
  return (
    <>
      <AcquisitionReadinessBanner onGoTo={onGoTo} />
      {panel === 'indexers' ? (
        <IndexersPanel />
      ) : panel === 'clients' ? (
        <ClientsPanel />
      ) : (
        <PathsPanel />
      )}
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
      qc.invalidateQueries({ queryKey: ['acquisition-status'] })
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
      qc.invalidateQueries({ queryKey: ['acquisition-status'] })
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

type ClientFormState = {
  name: string
  implementation: string
  host: string
  port: number
  username: string
  password: string
  apiKey: string
  category: string
  useSsl: boolean
  verifySsl: boolean
}

const EMPTY_CLIENT_FORM: ClientFormState = {
  name: '',
  implementation: 'qbittorrent',
  host: 'host.docker.internal',
  port: 8080,
  username: 'admin',
  password: '',
  apiKey: '',
  category: 'musicarr',
  useSsl: false,
  verifySsl: true,
}

function ClientsPanel() {
  const qc = useQueryClient()
  const toast = useToast()
  const { data, isLoading } = useQuery({
    queryKey: ['download-clients'],
    queryFn: api.downloadClients,
  })
  const [form, setForm] = useState<ClientFormState>(EMPTY_CLIENT_FORM)
  const [editingId, setEditingId] = useState<number | null>(null)

  const saveBody = () => {
    const body: Record<string, unknown> = {
      name: form.name.trim() || 'Draft',
      implementation: form.implementation,
      protocol: form.implementation === 'sabnzbd' ? 'usenet' : 'torrent',
      host: form.host.trim(),
      port: form.port,
      use_ssl: form.useSsl,
      verify_ssl: form.verifySsl,
      username: form.username.trim(),
      category: form.category.trim() || 'musicarr',
      enabled: true,
      priority: 1,
    }
    if (form.password) body.password = form.password
    else if (!editingId) body.password = ''
    if (form.apiKey) body.api_key = form.apiKey
    else if (!editingId) body.api_key = ''
    return body
  }

  const testDraftBody = () => ({
    implementation: form.implementation,
    host: form.host.trim(),
    port: form.port,
    use_ssl: form.useSsl,
    verify_ssl: form.verifySsl,
    username: form.username.trim(),
    password: form.password,
    api_key: form.apiKey.trim(),
    ...(editingId ? { client_id: editingId } : {}),
  })

  const resetForm = () => {
    setForm(EMPTY_CLIENT_FORM)
    setEditingId(null)
  }

  const save = useMutation({
    mutationFn: () => {
      const body = saveBody()
      if (editingId) return api.updateDownloadClient(editingId, body)
      return api.createDownloadClient(body)
    },
    onSuccess: (row) => {
      toast.push(
        editingId
          ? `Client updated · ${row.base_url || ''}`
          : `Client added · ${row.base_url || ''}`,
        'ok',
      )
      resetForm()
      qc.invalidateQueries({ queryKey: ['download-clients'] })
      qc.invalidateQueries({ queryKey: ['acquisition-status'] })
    },
    onError: (err) => toast.push((err as Error).message, 'error'),
  })
  const update = useMutation({
    mutationFn: ({ id, body }: { id: number; body: Record<string, unknown> }) =>
      api.updateDownloadClient(id, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['download-clients'] })
      qc.invalidateQueries({ queryKey: ['acquisition-status'] })
    },
    onError: (err) => toast.push((err as Error).message, 'error'),
  })
  const remove = useMutation({
    mutationFn: (id: number) => api.deleteDownloadClient(id),
    onSuccess: () => {
      toast.push('Client removed', 'ok')
      if (editingId) resetForm()
      qc.invalidateQueries({ queryKey: ['download-clients'] })
      qc.invalidateQueries({ queryKey: ['acquisition-status'] })
    },
    onError: (err) => toast.push((err as Error).message, 'error'),
  })
  const testSaved = useMutation({
    mutationFn: (id: number) => api.testDownloadClient(id),
    onSuccess: (res) => toast.push(res.message || (res.ok ? 'OK' : 'Failed'), res.ok ? 'ok' : 'error'),
    onError: (err) => toast.push((err as Error).message, 'error'),
  })
  const testDraft = useMutation({
    mutationFn: () => api.testDownloadClientDraft(testDraftBody()),
    onSuccess: (res) => toast.push(res.message || (res.ok ? 'OK' : 'Failed'), res.ok ? 'ok' : 'error'),
    onError: (err) => toast.push((err as Error).message, 'error'),
  })

  const startEdit = (row: DownloadClientRow) => {
    setEditingId(row.id)
    setForm({
      name: row.name,
      implementation: row.implementation,
      host: row.host,
      port: row.port,
      username: row.username || (row.implementation === 'qbittorrent' ? 'admin' : ''),
      password: '',
      apiKey: '',
      category: row.category || 'musicarr',
      useSsl: row.use_ssl,
      verifySsl: row.verify_ssl !== false,
    })
  }

  return (
    <>
      <p className="muted">
        Musicarr sends grabs to the client and imports finished files from the path the client
        reports — after remote path mapping. From Docker, <code>localhost</code> is the Musicarr
        container itself — use <code>host.docker.internal</code>, a compose service name, or a LAN
        IP. Share the completed-download volume with Musicarr and map it under Path mappings.
      </p>
      <div className="card" style={{ marginBottom: '1rem' }}>
        <h3 style={{ marginTop: 0 }}>{editingId ? 'Edit download client' : 'Add download client'}</h3>
        <div className="field">
          <label>Name</label>
          <input
            value={form.name}
            onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
            placeholder="qBittorrent"
          />
        </div>
        <div className="field">
          <label>Type</label>
          <select
            value={form.implementation}
            disabled={!!editingId}
            onChange={(e) => {
              const v = e.target.value
              setForm((f) => ({
                ...f,
                implementation: v,
                username: v === 'qbittorrent' ? f.username || 'admin' : f.username,
              }))
            }}
          >
            <option value="qbittorrent">qBittorrent</option>
            <option value="sabnzbd">SABnzbd</option>
          </select>
        </div>
        <div className="field">
          <label>Host</label>
          <input
            value={form.host}
            onChange={(e) => setForm((f) => ({ ...f, host: e.target.value }))}
            placeholder="host.docker.internal or qbittorrent"
          />
          <span className="muted tiny">
            Examples: <code>host.docker.internal</code>, <code>qbittorrent</code>,{' '}
            <code>192.168.1.10</code>, or <code>http://qbittorrent:8080/qbittorrent</code> (base
            path).
          </span>
        </div>
        <div className="field">
          <label>Port</label>
          <input
            type="number"
            value={form.port}
            onChange={(e) => setForm((f) => ({ ...f, port: Number(e.target.value) }))}
          />
        </div>
        <label className="checks">
          <input
            type="checkbox"
            checked={form.useSsl}
            onChange={(e) => setForm((f) => ({ ...f, useSsl: e.target.checked }))}
          />
          Use SSL
        </label>
        <label className="checks">
          <input
            type="checkbox"
            checked={form.verifySsl}
            onChange={(e) => setForm((f) => ({ ...f, verifySsl: e.target.checked }))}
          />
          Verify SSL certificate
        </label>
        {form.implementation === 'qbittorrent' ? (
          <>
            <div className="field">
              <label>Username</label>
              <input
                value={form.username}
                onChange={(e) => setForm((f) => ({ ...f, username: e.target.value }))}
                placeholder="admin"
              />
            </div>
            <div className="field">
              <label>Password{editingId ? ' (leave blank to keep)' : ''}</label>
              <input
                type="password"
                value={form.password}
                onChange={(e) => setForm((f) => ({ ...f, password: e.target.value }))}
              />
            </div>
          </>
        ) : (
          <>
            <div className="field">
              <label>API key{editingId ? ' (leave blank to keep)' : ''}</label>
              <input
                type="password"
                value={form.apiKey}
                onChange={(e) => setForm((f) => ({ ...f, apiKey: e.target.value }))}
              />
            </div>
            <div className="field">
              <label>Username (optional)</label>
              <input
                value={form.username}
                onChange={(e) => setForm((f) => ({ ...f, username: e.target.value }))}
              />
            </div>
            <div className="field">
              <label>Password (optional){editingId ? ' — leave blank to keep' : ''}</label>
              <input
                type="password"
                value={form.password}
                onChange={(e) => setForm((f) => ({ ...f, password: e.target.value }))}
              />
            </div>
          </>
        )}
        <div className="field">
          <label>Category</label>
          <input
            value={form.category}
            onChange={(e) => setForm((f) => ({ ...f, category: e.target.value }))}
          />
          <span className="muted tiny">Only this category is imported (default musicarr).</span>
        </div>
        <div className="toolbar" style={{ marginBottom: 0 }}>
          <button
            className="btn"
            type="button"
            disabled={!form.name.trim() || !form.host.trim() || save.isPending}
            onClick={() => save.mutate()}
          >
            {editingId ? 'Save changes' : 'Add client'}
          </button>
          <button
            className="btn secondary"
            type="button"
            disabled={!form.host.trim() || testDraft.isPending}
            onClick={() => testDraft.mutate()}
          >
            Test connection
          </button>
          {editingId && (
            <button className="btn ghost" type="button" onClick={resetForm}>
              Cancel edit
            </button>
          )}
        </div>
      </div>
      {isLoading && <p className="muted">Loading…</p>}
      <ClientTable
        rows={data || []}
        onToggle={(row) => update.mutate({ id: row.id, body: { enabled: !row.enabled } })}
        onTest={(id) => testSaved.mutate(id)}
        onEdit={startEdit}
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
  onEdit,
  onDelete,
}: {
  rows: DownloadClientRow[]
  onToggle: (row: DownloadClientRow) => void
  onTest: (id: number) => void
  onEdit: (row: DownloadClientRow) => void
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
            <td className="muted" style={{ wordBreak: 'break-all' }}>
              {row.base_url || `${row.use_ssl ? 'https' : 'http'}://${row.host}:${row.port}`}
            </td>
            <td>{row.category}</td>
            <td className="row-actions">
              <button className="btn ghost" type="button" onClick={() => onToggle(row)}>
                {row.enabled ? 'Disable' : 'Enable'}
              </button>
              <button className="btn secondary" type="button" onClick={() => onEdit(row)}>
                Edit
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
      qc.invalidateQueries({ queryKey: ['acquisition-status'] })
    },
    onError: (err) => toast.push((err as Error).message, 'error'),
  })
  const remove = useMutation({
    mutationFn: (id: number) => api.deletePathMapping(id),
    onSuccess: () => {
      toast.push('Mapping removed', 'ok')
      qc.invalidateQueries({ queryKey: ['path-mappings'] })
      qc.invalidateQueries({ queryKey: ['acquisition-status'] })
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
