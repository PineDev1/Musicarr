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
  added_at: string
  last_synced_at: string | null
  album_count: number
  downloaded_count: number
  wanted_count: number
  providers?: string[]
  linked_artist_ids?: number[]
  albums: Album[]
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
  retries: number
  created_at: string
  started_at: string | null
  finished_at: string | null
}

export type HistoryEvent = {
  id: number
  event_type: string
  message: string
  created_at: string
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
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
  refreshArtist: (id: number) =>
    request<Artist>(`/artists/${id}/refresh`, { method: 'POST' }),
  downloadMissing: (id: number) =>
    request<{ queued: number }>(`/artists/${id}/download-missing`, { method: 'POST' }),
  wanted: () => request<Album[]>('/albums/wanted'),
  downloadAllWanted: () =>
    request<{ queued: number }>('/albums/wanted/download-all', { method: 'POST' }),
  skipAllWanted: () =>
    request<{ skipped: number }>('/albums/wanted/skip-all', { method: 'POST' }),
  patchAlbum: (id: number, body: Record<string, unknown>) =>
    request<Album>(`/albums/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  downloadAlbum: (id: number) =>
    request<{ queued: boolean; job_id: number | null }>(`/albums/${id}/download`, {
      method: 'POST',
    }),
  queue: (all = false) => request<DownloadJob[]>(`/queue?all_jobs=${all}`),
  cancelJob: (id: number) =>
    request<DownloadJob>(`/queue/${id}/cancel`, { method: 'POST' }),
  retryJob: (id: number) =>
    request<DownloadJob>(`/queue/${id}/retry`, { method: 'POST' }),
  clearFinishedQueue: () =>
    request<{ cleared: number }>('/queue/clear-finished', { method: 'POST' }),
  history: () => request<HistoryEvent[]>('/history'),
  scan: () =>
    request<{ files_seen: number; matched: number; unmatched: number; message: string }>(
      '/library/scan',
      { method: 'POST' },
    ),
  reorganize: () =>
    request<{ moved: number; skipped: number; message: string }>('/library/reorganize', {
      method: 'POST',
    }),
  runMonitor: () =>
    request<{ artists_checked: number; new_albums: number }>('/monitor/run', {
      method: 'POST',
    }),
}
