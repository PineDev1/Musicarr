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
  official_releases_only: boolean
  mb_catalog_mode: string
  notify_webhook_url: string
  notify_channel: string
  notify_token_set: boolean
  notify_on_complete: boolean
  notify_on_failure: boolean
  upgrade_enabled: boolean
  fallback_providers_enabled: boolean
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

export type BulkArtistSearchResult = {
  query: string
  results: ArtistSearchResult[]
  error?: string | null
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
  status_reason?: string
  musicbrainz_id?: string | null
  artist_credit?: string
  path: string | null
  quality?: string
  upgrade_available?: boolean
  artist_name?: string | null
  sources?: string[]
  tracks: Track[]
}

export type RelatedArtist = {
  id: number | null
  name: string
  musicbrainz_id?: string | null
  provider?: string | null
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
  musicbrainz_id?: string | null
  added_at: string
  last_synced_at: string | null
  album_count: number
  downloaded_count: number
  wanted_count: number
  missing_count?: number
  providers?: string[]
  linked_artist_ids?: number[]
  related_artists?: RelatedArtist[]
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
}







export type RestoreJob = {
  state: string
  phase: string
  progress_pct: number
  message: string
  error: string
  detail: string
  started_at: string
  finished_at: string
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
  notifyTest: (body: { notify_webhook_url?: string; notify_channel?: string; notify_token?: string } = {}) =>
    request<{ ok: boolean }>('/settings/notify-test', { method: 'POST', body: JSON.stringify(body) }),
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
  bulkSearchArtists: (names: string) =>
    request<BulkArtistSearchResult[]>('/artists/bulk-search', {
      method: 'POST',
      body: JSON.stringify({ names }),
    }),
  artistCollisions: () =>
    request<{
      groups: {
        id: number
        name: string
        provider: string
        provider_id: string
        musicbrainz_id?: string | null
        link_group_id?: string | null
        image_url?: string | null
      }[][]
    }>('/artists/collisions'),
  mergeArtists: (artistIds: number[], preferredId?: number) =>
    request<Artist[]>('/artists/merge', {
      method: 'POST',
      body: JSON.stringify({ artist_ids: artistIds, preferred_id: preferredId }),
    }),
  artists: () => request<Artist[]>('/artists'),
  artist: (id: number) => request<Artist>(`/artists/${id}`),
  addArtist: (
    provider_id: string,
    provider?: string,
    opts?: { include_singles?: boolean | null; download_missing?: boolean },
  ) =>
    request<Artist>('/artists', {
      method: 'POST',
      body: JSON.stringify({
        provider_id,
        provider,
        monitored: true,
        download_missing: opts?.download_missing ?? true,
        include_singles: opts?.include_singles ?? null,
      }),
    }),
  deleteArtist: (id: number) =>
    request<{ ok: boolean }>(`/artists/${id}`, { method: 'DELETE' }),
  patchArtist: (id: number, body: Record<string, unknown>) =>
    request<Artist>(`/artists/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  refreshArtist: (id: number) =>
    request<Artist>(`/artists/${id}/refresh`, { method: 'POST' }),
  downloadMissing: (id: number) =>
    request<{ queued: number }>(`/artists/${id}/download-missing`, { method: 'POST' }),
  wanted: (albumType?: string) =>
    request<Album[]>(
      albumType ? `/albums/wanted?album_type=${encodeURIComponent(albumType)}` : '/albums/wanted',
    ),
  downloadAllWanted: () =>
    request<{ queued: number }>('/albums/wanted/download-all', { method: 'POST' }),
  skipAllWanted: () =>
    request<{ skipped: number }>('/albums/wanted/skip-all', { method: 'POST' }),
  skipWantedSingles: () =>
    request<{ skipped: number }>('/albums/wanted/skip-singles', { method: 'POST' }),
  skipWantedJunk: () =>
    request<{ skipped: number }>('/albums/wanted/skip-junk', { method: 'POST' }),
  bulkSkipAlbums: (albumIds: number[]) =>
    request<{ skipped: number }>('/albums/bulk/skip', {
      method: 'POST',
      body: JSON.stringify({ album_ids: albumIds }),
    }),
  bulkDownloadAlbums: (albumIds: number[]) =>
    request<{ queued: number }>('/albums/bulk/download', {
      method: 'POST',
      body: JSON.stringify({ album_ids: albumIds }),
    }),
  upgradable: () => request<Album[]>('/albums/upgradable'),
  upgradeAll: () =>
    request<{ queued: number; target?: string; message?: string }>('/albums/upgrade-all', {
      method: 'POST',
    }),
  album: (id: number) => request<Album>(`/albums/${id}`),
  patchAlbum: (id: number, body: Record<string, unknown>) =>
    request<Album>(`/albums/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  downloadAlbum: (id: number, upgrade = false) =>
    request<{ queued: boolean; job_id: number | null; source?: string | null }>(
      `/albums/${id}/download?upgrade=${upgrade}`,
      { method: 'POST' },
    ),
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
    request<LibraryJob>('/library/scan', { method: 'POST' }),
  importLibrary: (linkProviders = true) =>
    request<LibraryJob>(`/library/import?link_providers=${linkProviders}`, { method: 'POST' }),
  importReview: (suggest = true) =>
    request<ImportReview>(`/library/review?suggest=${suggest}`),
  linkImportArtist: (artistId: number, providerId: string, provider?: string) =>
    request<Artist>(`/library/review/${artistId}/link`, {
      method: 'POST',
      body: JSON.stringify({ provider_id: providerId, provider }),
    }),
  reorganize: () => request<LibraryJob>('/library/reorganize', { method: 'POST' }),
  libraryJob: () => request<LibraryJob>('/library/job'),
  restoreBackup: async (file: File) => {
    const form = new FormData()
    form.append('file', file)
    const res = await fetch('/api/backup/restore', {
      method: 'POST',
      credentials: 'include',
      body: form,
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
    return res.json() as Promise<RestoreJob>
  },
  restoreJob: () => request<RestoreJob>('/backup/restore/job'),
  runMonitor: () =>
    request<{ artists_checked: number; new_albums: number }>('/monitor/run', {
      method: 'POST',
    }),
  mbCatalogStatus: () =>
    request<{
      status: string
      ready: boolean
      path: string
      size_bytes: number
      dump_version: string
      imported_at: string
      mode: string
      max_bytes: number
      job: MbCatalogJob
    }>('/musicbrainz-catalog/status'),
  mbCatalogCheckVersion: () =>
    request<{
      installed: string
      latest: string
      update_available: boolean
      ready: boolean
    }>('/musicbrainz-catalog/check-version', { method: 'POST' }),
  mbCatalogUpdate: () =>
    request<MbCatalogJob>('/musicbrainz-catalog/update', { method: 'POST' }),
  mbCatalogJob: () => request<MbCatalogJob>('/musicbrainz-catalog/job'),
  mbCatalogSetMode: (mode: string) =>
    request<{
      status: string
      ready: boolean
      path: string
      size_bytes: number
      dump_version: string
      imported_at: string
      mode: string
      max_bytes: number
      job: MbCatalogJob
    }>('/musicbrainz-catalog/mode', {
      method: 'PUT',
      body: JSON.stringify({ mode }),
    }),
}

export type MbCatalogJob = {
  state: string
  phase: string
  progress_pct: number
  bytes_done: number
  bytes_total: number
  message: string
  error: string
  dump_version: string
  started_at: string
  finished_at: string
}

export type LibraryJob = {
  state: string
  kind: string
  phase: string
  progress_pct: number
  message: string
  error: string
  started_at: string
  finished_at: string
  files_seen: number
  files_done: number
  artists_created: number
  albums_imported: number
  tracks_linked: number
  provider_linked: number
  matched: number
  unmatched: number
  moved: number
  skipped: number
  result: Record<string, unknown>
  link_providers: boolean
}
