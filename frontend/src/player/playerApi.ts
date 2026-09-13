export type PlayerAuthStatus = {
  enabled: boolean
  authenticated: boolean
  username: string | null
  user_id: number | null
  display_name: string | null
  avatar_url: string | null
}

export type PlayerUser = {
  id: number
  username: string
  display_name: string
  is_active: boolean
  created_at: string
}

export type PlayerTrack = {
  id: number
  title: string
  track_no: number
  disc_no: number
  duration: number
  album_id: number
  album_title: string
  artist_id: number
  artist_name: string
  cover_url: string | null
  quality: string
  format: string
}

export type PlayerAlbum = {
  id: number
  title: string
  artist_id: number
  artist_name: string
  cover_url: string | null
  release_date: string | null
  track_count: number
  quality: string
  tracks: PlayerTrack[]
}

export type PlayerArtist = {
  id: number
  name: string
  image_url: string | null
  album_count: number
}

export type PlayerArtistDetail = PlayerArtist & {
  featured_album: PlayerAlbum | null
  top_songs: PlayerTrack[]
  essential_albums: PlayerAlbum[]
  albums: PlayerAlbum[]
}

export type PlayerSearchGrouped = {
  top: PlayerTrack | null
  songs: PlayerTrack[]
  albums: PlayerAlbum[]
  artists: PlayerArtist[]
}

export type PlayerShare = {
  token: string
  url: string
  expires_at: string
  track_title: string
  artist_name: string
  cover_url: string | null
  play_count: number
  revoked: boolean
  created_at: string
}

export type PlayerSharePublic = {
  title: string
  artist: string
  album: string
  cover_url: string | null
  duration: number
  shared_by_display_name: string
  shared_by_avatar_url: string | null
}

export type PlayerContinue = {
  album: PlayerAlbum | null
  track: PlayerTrack | null
  position: number
  source_label: string
}

export type PlayerSongsPage = {
  items: PlayerTrack[]
  total: number
  offset: number
  limit: number
}

export type PlayerRepeatMode = 'off' | 'all' | 'one'

export type PlayerPlaylist = {
  id: number | string
  name: string
  track_count: number
  created_at: string | null
  updated_at: string | null
  tracks: PlayerTrack[]
  is_smart?: boolean
  builtin?: boolean
  kind?: string | null
}

export type PlayerPrefs = {
  show_recently_played: boolean
  show_shuffle_mix: boolean
  wave_height: number
  wave_length: number
  wave_speed: number
  wave_thickness: number
  wave_color: string
  wave_flatten_when_paused: boolean
  pinned_playlist_ids: number[]
  crossfade_enabled: boolean
  show_recommended: boolean
  show_recently_added: boolean
  default_shuffle: boolean
  default_repeat: PlayerRepeatMode
}

export type NowPlayingRow = {
  user_id: number
  username: string
  display_name: string
  track_id: number | null
  title: string | null
  artist_name: string | null
  cover_url: string | null
  playing: boolean
  position: number
  updated_at: number
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api/player${path}`, {
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

export const DEFAULT_PREFS: PlayerPrefs = {
  show_recently_played: true,
  show_shuffle_mix: true,
  wave_height: 6,
  wave_length: 20,
  wave_speed: 12,
  wave_thickness: 3,
  wave_color: '#3dba7a',
  wave_flatten_when_paused: true,
  pinned_playlist_ids: [],
  crossfade_enabled: false,
  show_recommended: true,
  show_recently_added: true,
  default_shuffle: false,
  default_repeat: 'off',
}

export const playerApi = {
  status: () => request<PlayerAuthStatus>('/status'),
  login: (username: string, password: string) =>
    request<PlayerAuthStatus>('/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    }),
  logout: () => request<PlayerAuthStatus>('/logout', { method: 'POST' }),
  changePassword: (current_password: string, new_password: string) =>
    request<{ ok: boolean }>('/me/password', {
      method: 'POST',
      body: JSON.stringify({ current_password, new_password }),
    }),
  prefs: () => request<PlayerPrefs>('/me/prefs'),
  updatePrefs: (body: Partial<PlayerPrefs>) =>
    request<PlayerPrefs>('/me/prefs', { method: 'PATCH', body: JSON.stringify(body) }),
  reportPlaying: (body: {
    track_id: number | null
    position: number
    playing: boolean
    title?: string
    artist_name?: string
    cover_url?: string | null
  }) => request<{ ok: boolean }>('/me/playing', { method: 'POST', body: JSON.stringify(body) }),
  commands: () => request<{ stop: boolean }>('/me/commands'),
  users: () => request<PlayerUser[]>('/users'),
  createUser: (body: { username: string; password: string; display_name?: string }) =>
    request<PlayerUser>('/users', { method: 'POST', body: JSON.stringify(body) }),
  updateUser: (id: number, body: Record<string, unknown>) =>
    request<PlayerUser>(`/users/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  deleteUser: (id: number) => request<{ ok: boolean }>(`/users/${id}`, { method: 'DELETE' }),
  artists: () => request<PlayerArtist[]>('/artists'),
  artistDetail: (id: number) => request<PlayerArtistDetail>(`/artists/${id}`),
  artistAlbums: (id: number) => request<PlayerAlbum[]>(`/artists/${id}/albums`),
  album: (id: number) => request<PlayerAlbum>(`/albums/${id}`),
  search: (q: string) => request<PlayerTrack[]>(`/search?q=${encodeURIComponent(q)}`),
  searchGrouped: (q: string) =>
    request<PlayerSearchGrouped>(`/search?grouped=1&q=${encodeURIComponent(q)}`),
  recommended: () => request<PlayerTrack[]>('/library/recommended'),
  libraryAlbums: (sort: 'recent' | 'name' | 'year' = 'recent') =>
    request<PlayerAlbum[]>(`/library/albums?sort=${encodeURIComponent(sort)}`),
  librarySongs: ({ q = '', offset = 0, limit = 50 }: { q?: string; offset?: number; limit?: number } = {}) =>
    request<PlayerSongsPage>(
      `/library/songs?q=${encodeURIComponent(q)}&offset=${offset}&limit=${limit}`,
    ),
  continueListening: () => request<PlayerContinue>('/library/continue'),
  listenHistory: () => request<PlayerPlaylist>('/library/history'),
  clearHistory: () => request<{ ok: boolean }>('/library/history', { method: 'DELETE' }),
  streamUrl: (trackId: number) => `/api/player/stream/${trackId}`,
  favoriteIds: () => request<{ ids: number[] }>('/favorites/ids'),
  addFavorite: (trackId: number) =>
    request<PlayerTrack>(`/favorites/${trackId}`, { method: 'POST' }),
  removeFavorite: (trackId: number) =>
    request<{ ok: boolean }>(`/favorites/${trackId}`, { method: 'DELETE' }),
  builtins: () => request<PlayerPlaylist[]>('/library/builtins'),
  builtin: (kind: string) => request<PlayerPlaylist>(`/library/builtins/${kind}`),
  playlists: () => request<PlayerPlaylist[]>('/playlists'),
  playlist: (id: number) => request<PlayerPlaylist>(`/playlists/${id}`),
  createPlaylist: (name: string, is_smart = false) =>
    request<PlayerPlaylist>('/playlists', {
      method: 'POST',
      body: JSON.stringify({ name, is_smart }),
    }),
  updatePlaylist: (id: number, body: { name?: string; is_smart?: boolean }) =>
    request<PlayerPlaylist>(`/playlists/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),
  deletePlaylist: (id: number) =>
    request<{ ok: boolean }>(`/playlists/${id}`, { method: 'DELETE' }),
  addToPlaylist: (id: number, track_ids: number[]) =>
    request<PlayerPlaylist>(`/playlists/${id}/tracks`, {
      method: 'POST',
      body: JSON.stringify({ track_ids }),
    }),
  removeFromPlaylist: (id: number, trackId: number) =>
    request<{ ok: boolean }>(`/playlists/${id}/tracks/${trackId}`, { method: 'DELETE' }),
  suggestions: (id: number) => request<PlayerTrack[]>(`/playlists/${id}/suggestions`),
  uploadAvatar: async (file: File) => {
    const body = new FormData()
    body.append('file', file)
    // Browser sets the multipart boundary — never send an explicit Content-Type here.
    const res = await fetch('/api/player/me/avatar', {
      method: 'POST',
      credentials: 'include',
      body,
    })
    if (!res.ok) {
      let detail = res.statusText
      try {
        const payload = await res.json()
        detail = payload.detail || JSON.stringify(payload)
      } catch {
        /* ignore */
      }
      throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail))
    }
    return (await res.json()) as { ok: boolean; avatar_url: string | null }
  },
  deleteAvatar: () => request<{ ok: boolean }>('/me/avatar', { method: 'DELETE' }),
  avatarUrl: (userId: number) => `/api/player/avatars/${userId}`,
  createShare: (trackId: number) =>
    request<PlayerShare>('/shares', {
      method: 'POST',
      body: JSON.stringify({ track_id: trackId }),
    }),
  listShares: () => request<PlayerShare[]>('/shares'),
  revokeShare: (token: string) =>
    request<{ ok: boolean }>(`/shares/${encodeURIComponent(token)}`, { method: 'DELETE' }),
  /** Absolute share page URL for the host the user is currently on. */
  sharePageUrl: (token: string) =>
    `${typeof window !== 'undefined' ? window.location.origin : ''}/s/${encodeURIComponent(token)}`,
  shareMeta: async (token: string) => {
    // Public endpoint — no session cookies required (avoids auth-gate confusion).
    const res = await fetch(`/api/player/share/${encodeURIComponent(token)}`, {
      credentials: 'omit',
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
    return res.json() as Promise<PlayerSharePublic>
  },
  shareStreamUrl: (token: string) => `/api/player/share/${encodeURIComponent(token)}/stream`,
  nowPlaying: () => request<NowPlayingRow[]>('/admin/now-playing'),
  stopListener: (userId: number) =>
    request<{ ok: boolean }>(`/admin/now-playing/${userId}/stop`, { method: 'POST' }),
}
