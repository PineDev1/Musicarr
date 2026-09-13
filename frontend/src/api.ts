export type Health = {
  status: string
  active_provider: string
  provider_ok: boolean
  provider_error: string | null
  deezer_ok: boolean
  deezer_error: string | null
  tidal_ok: boolean
  tidal_error: string | null
  qobuz_ok: boolean
  qobuz_error: string | null
  library_path: string
  library_writable: boolean
  monitored_artists: number
  wanted_albums: number
  queue_size: number
}

export type Settings = {
  active_provider: string
  arl_set: boolean
  arl_masked: string
  tidal_logged_in: boolean
  qobuz_logged_in: boolean
  qobuz_email: string
  qobuz_user_id: string
  qobuz_app_id: string
  qobuz_app_secret_set: boolean
  qobuz_token_set: boolean
  library_path: string
  bitrate: string
  folder_template: string
  track_template: string
  monitor_interval_minutes: number
  include_albums: boolean
  include_eps: boolean
  include_singles: boolean
  include_compilations: boolean
  min_track_count: number
  ignore_junk_titles: boolean
  ignore_live_releases: boolean
  notify_webhook_url: string
  notify_on_complete: boolean
  notify_on_failure: boolean
  upgrade_enabled: boolean
  media_refresh_url: string
  media_refresh_token_set: boolean
  media_refresh_type: string
  auth_enabled: boolean
  auth_username: string
  auth_password_set: boolean
  ssl_enabled: boolean
  public_domain: string
  player_enabled: boolean
  player_sharing_enabled: boolean
  preferred_download_method: string
  completed_download_scan_interval_seconds: number
  import_mechanism: string
  remove_completed_downloads: boolean
  download_concurrency: number
  max_retries: number
  provider_ok: boolean | null
  provider_error: string | null
  deezer_ok: boolean | null
  deezer_error: string | null
  tidal_ok: boolean | null
  tidal_error: string | null
  qobuz_ok: boolean | null
  qobuz_error: string | null
}

export type AppAuthStatus = {
  enabled: boolean
  authenticated: boolean
  username: string | null
  password_set: boolean
}

export type ArtistSearchResult = {
  provider: string
  provider_id: string
  deezer_id: number | null
  name: string
  image_url: string | null
  nb_album: number | null
}

export type Track = {
  id: number
  provider: string
  provider_id: string
  deezer_id: number
  title: string
  track_no: number
  disc_no: number
  duration: number
  path: string | null
  downloaded: boolean
}

export type Album = {
  id: number
  provider: string
  provider_id: string
  deezer_id: number
  artist_id: number
  title: string
  album_type: string
  release_date: string | null
  cover_url: string | null
  track_count: number
  monitored: boolean
  status: string
  path: string | null
  quality?: string
  upgrade_available?: boolean
  artist_name?: string | null
  sources?: string[]
  tracks: Track[]
}

export type Artist = {
  id: number
  provider: string
  provider_id: string
  deezer_id: number
  name: string
  image_url: string | null
  monitored: boolean
  monitor_mode?: string
  include_singles?: boolean | null
  added_at: string
  last_synced_at: string | null
  album_count: number
  downloaded_count: number
  wanted_count: number
  providers?: string[]
  linked_artist_ids?: number[]
  name_collision?: boolean
  albums: Album[]
}

export type ImportReviewArtist = {
  id: number
  name: string
  provider: string
  album_count: number
  reason: string
  suggestions: ArtistSearchResult[]
}

export type ImportReviewAlbum = {
  id: number
  title: string
  artist_id: number
  artist_name: string
  reason: string
}

export type ImportReview = {
  local_artists: ImportReviewArtist[]
  weak_albums: ImportReviewAlbum[]
  message: string
}

export type DownloadJob = {
  id: number
  target_type: string
  target_id: number
  album_id: number | null
  artist_name: string
  album_title: string
  state: string
  progress: number
  error: string | null
  error_category?: string
  retries: number
  created_at: string
  started_at: string | null
  finished_at: string | null
  source?: string
  indexer_id?: number | null
  client_id?: number | null
  release_title?: string
  client_item_id?: string
  output_path?: string
}

export type Indexer = {
  id: number
  name: string
  protocol: string
  implementation: string
  base_url: string
  api_key_set: boolean
  categories: number[]
  enabled: boolean
  priority: number
}

export type DownloadClientRow = {
  id: number
  name: string
  protocol: string
  implementation: string
  host: string
  port: number
  use_ssl: boolean
  verify_ssl?: boolean
  username: string
  password_set: boolean
  api_key_set: boolean
  category: string
  enabled: boolean
  priority: number
  base_url?: string
}

export type ReleaseCandidate = {
  title: string
  size: number
  seeders: number
  protocol: string
  download_url: string
  magnet_url: string
  grab_url: string
  indexer_id: number
  indexer_name: string
  score: number
}

export type AcquisitionStatus = {
  indexers_enabled: number
  torrent_client: boolean
  usenet_client: boolean
  path_mappings: number
  messages: string[]
}

export type PathMapping = {
  id: number
  host: string
  remote_path: string
  local_path: string
}

export type TestResult = {
  ok: boolean
  message: string
}

export type HistoryEvent = {
  id: number
  event_type: string
  message: string
  created_at: string
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', ...(init?.headers || {}) },
    ...init,
  })
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = body.detail || JSON.stringify(body)
    } catch {
      /* ignore */
    }
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail))
  }
  if (res.status === 204) return undefined as T
  return res.json()
}

export const api = {
  authStatus: () => request<AppAuthStatus>('/auth/status'),
  appLogin: (username: string, password: string) =>
    request<AppAuthStatus>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    }),
  appLogout: () =>
    request<AppAuthStatus>('/auth/logout-session', { method: 'POST' }),
  health: () => request<Health>('/health'),
  settings: (validate = false) => request<Settings>(`/settings?validate=${validate}`),
  updateSettings: (body: Record<string, unknown>) =>
    request<Settings>('/settings', { method: 'PUT', body: JSON.stringify(body) }),
  logout: (provider: string) =>
    request<Settings>(`/auth/${provider}/logout`, { method: 'POST' }),
  tidalDeviceStart: () =>
    request<{
      user_code: string
      verification_uri: string
      verification_uri_complete: string | null
      expires_in: number
    }>('/auth/tidal/device', { method: 'POST' }),
  tidalDeviceStatus: () =>
    request<{ status: string; error?: string }>('/auth/tidal/device/status'),
  qobuzLogin: (email: string, password: string) =>
    request<Settings>('/auth/qobuz/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    }),
  qobuzTokenLogin: (body: {
    token: string
    user_id?: string
    app_id?: string
    app_secret?: string
  }) =>
    request<Settings>('/auth/qobuz/token', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  searchArtists: (q: string) =>
    request<ArtistSearchResult[]>(`/artists/search?q=${encodeURIComponent(q)}`),
  artists: () => request<Artist[]>('/artists'),
  artist: (id: number) => request<Artist>(`/artists/${id}`),
  addArtist: (provider_id: string, provider?: string) =>
    request<Artist>('/artists', {
      method: 'POST',
      body: JSON.stringify({ provider_id, provider, monitored: true, download_missing: true }),
    }),
  deleteArtist: (id: number) =>
    request<{ ok: boolean }>(`/artists/${id}`, { method: 'DELETE' }),
  patchArtist: (id: number, body: Record<string, unknown>) =>
    request<Artist>(`/artists/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  refreshArtist: (id: number) =>
    request<Artist>(`/artists/${id}/refresh`, { method: 'POST' }),
  downloadMissing: (id: number, method?: string) =>
    request<{ queued: number }>(
      `/artists/${id}/download-missing${method ? `?method=${encodeURIComponent(method)}` : ''}`,
      { method: 'POST' },
    ),
  wanted: (albumType?: string) =>
    request<Album[]>(
      albumType ? `/albums/wanted?album_type=${encodeURIComponent(albumType)}` : '/albums/wanted',
    ),
  downloadAllWanted: (method?: string) =>
    request<{ queued: number }>(
      `/albums/wanted/download-all${method ? `?method=${encodeURIComponent(method)}` : ''}`,
      { method: 'POST' },
    ),
  skipAllWanted: () =>
    request<{ skipped: number }>('/albums/wanted/skip-all', { method: 'POST' }),
  skipWantedSingles: () =>
    request<{ skipped: number }>('/albums/wanted/skip-singles', { method: 'POST' }),
  skipWantedJunk: () =>
    request<{ skipped: number }>('/albums/wanted/skip-junk', { method: 'POST' }),
  upgradable: () => request<Album[]>('/albums/upgradable'),
  upgradeAll: () =>
    request<{ queued: number; target?: string; message?: string }>('/albums/upgrade-all', {
      method: 'POST',
    }),
  album: (id: number) => request<Album>(`/albums/${id}`),
  patchAlbum: (id: number, body: Record<string, unknown>) =>
    request<Album>(`/albums/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  downloadAlbum: (id: number, upgrade = false, method?: string) => {
    const params = new URLSearchParams({ upgrade: String(upgrade) })
    if (method) params.set('method', method)
    return request<{ queued: boolean; job_id: number | null; source?: string | null }>(
      `/albums/${id}/download?${params}`,
      { method: 'POST' },
    )
  },
  deleteAlbum: (id: number, deleteFiles = false) =>
    request<{ ok: boolean; deleted_files: boolean }>(
      `/albums/${id}?delete_files=${deleteFiles}`,
      { method: 'DELETE' },
    ),
  queue: (all = false) => request<DownloadJob[]>(`/queue?all_jobs=${all}`),
  cancelJob: (id: number) =>
    request<DownloadJob>(`/queue/${id}/cancel`, { method: 'POST' }),
  retryJob: (id: number) =>
    request<DownloadJob>(`/queue/${id}/retry`, { method: 'POST' }),
  retryFailedJobs: (opts?: { category?: string; skipPermanent?: boolean }) => {
    const params = new URLSearchParams()
    if (opts?.category) params.set('category', opts.category)
    if (opts?.skipPermanent === false) params.set('skip_permanent', 'false')
    const q = params.toString()
    return request<{ retried: number }>(`/queue/retry-failed${q ? `?${q}` : ''}`, {
      method: 'POST',
    })
  },
  clearFinishedQueue: () =>
    request<{ cleared: number }>('/queue/clear-finished', { method: 'POST' }),
  history: () => request<HistoryEvent[]>('/history'),
  scan: () =>
    request<{ files_seen: number; matched: number; unmatched: number; message: string }>(
      '/library/scan',
      { method: 'POST' },
    ),
  importLibrary: (linkProviders = true) =>
    request<{
      files_seen: number
      artists_created: number
      albums_imported: number
      tracks_linked: number
      provider_linked: number
      matched: number
      unmatched: number
      message: string
    }>(`/library/import?link_providers=${linkProviders}`, { method: 'POST' }),
  importReview: (suggest = true) =>
    request<ImportReview>(`/library/review?suggest=${suggest}`),
  linkImportArtist: (artistId: number, providerId: string, provider?: string) =>
    request<Artist>(`/library/review/${artistId}/link`, {
      method: 'POST',
      body: JSON.stringify({ provider_id: providerId, provider }),
    }),
  reorganize: () =>
    request<{ moved: number; skipped: number; message: string }>('/library/reorganize', {
      method: 'POST',
    }),
  runMonitor: () =>
    request<{ artists_checked: number; new_albums: number }>('/monitor/run', {
      method: 'POST',
    }),
  indexers: () => request<Indexer[]>('/acquisition/indexers'),
  createIndexer: (body: Record<string, unknown>) =>
    request<Indexer>('/acquisition/indexers', { method: 'POST', body: JSON.stringify(body) }),
  updateIndexer: (id: number, body: Record<string, unknown>) =>
    request<Indexer>(`/acquisition/indexers/${id}`, { method: 'PUT', body: JSON.stringify(body) }),
  deleteIndexer: (id: number) =>
    request<{ ok: boolean }>(`/acquisition/indexers/${id}`, { method: 'DELETE' }),
  testIndexer: (id: number) =>
    request<TestResult>(`/acquisition/indexers/${id}/test`, { method: 'POST' }),
  downloadClients: () => request<DownloadClientRow[]>('/acquisition/download-clients'),
  createDownloadClient: (body: Record<string, unknown>) =>
    request<DownloadClientRow>('/acquisition/download-clients', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  updateDownloadClient: (id: number, body: Record<string, unknown>) =>
    request<DownloadClientRow>(`/acquisition/download-clients/${id}`, {
      method: 'PUT',
      body: JSON.stringify(body),
    }),
  deleteDownloadClient: (id: number) =>
    request<{ ok: boolean }>(`/acquisition/download-clients/${id}`, { method: 'DELETE' }),
  testDownloadClient: (id: number) =>
    request<TestResult>(`/acquisition/download-clients/${id}/test`, { method: 'POST' }),
  testDownloadClientDraft: (body: Record<string, unknown>) =>
    request<TestResult>('/acquisition/download-clients/test-draft', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  acquisitionStatus: () => request<AcquisitionStatus>('/acquisition/status'),
  pathMappings: () => request<PathMapping[]>('/acquisition/path-mappings'),
  createPathMapping: (body: Record<string, unknown>) =>
    request<PathMapping>('/acquisition/path-mappings', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  updatePathMapping: (id: number, body: Record<string, unknown>) =>
    request<PathMapping>(`/acquisition/path-mappings/${id}`, {
      method: 'PUT',
      body: JSON.stringify(body),
    }),
  deletePathMapping: (id: number) =>
    request<{ ok: boolean }>(`/acquisition/path-mappings/${id}`, { method: 'DELETE' }),
  searchReleases: (albumId: number) =>
    request<ReleaseCandidate[]>(`/acquisition/releases/search?album_id=${albumId}`),
  grabRelease: (body: {
    album_id: number
    title?: string
    grab_url: string
    protocol: string
    indexer_id?: number | null
    size?: number
    seeders?: number
  }) =>
    request<{ ok: boolean; job_id: number; client: string }>(
      '/acquisition/releases/grab',
      { method: 'POST', body: JSON.stringify(body) },
    ),
}
