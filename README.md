# Musicarr

**Your library. Your sources. Your rules.**

Self-hosted music library manager with a sharp web UI — grab discographies from **Deezer**, **Tidal**, or **Qobuz**, keep FLAC pristine, and spin up a multi-user listening room at `/player`.

```
  ♫  Musicarr  ·  library OS vibes  ·  port 8787
```

**Author:** [PineDev1](https://github.com/PineDev1) · **Latest:** [v1.6](https://github.com/PineDev1/Musicarr/releases/tag/v1.6)

---

## Why Musicarr

- One active download source, three providers ready when you are
- Import the collection you already own — then fill the gaps
- Optional **music player** with lossless streaming (FLAC stays FLAC)
- Optional login + Traefik HTTPS when you take it off the LAN
- One Docker container. Open **http://localhost:8787** and go

---

## Features

- **Multi-source downloads** — Deezer (ARL), Tidal (device login), or Qobuz (token / app credentials). One active source at a time.
- **Artist library** — search, add, and monitor artists. Each provider artist is its own library entry (same display names stay separate). Cross-source merge is only via an explicit link later — not by name.
- **Wanted / Queue / Activity** — track missing albums, live download progress, and history.
- **In-artist progress** — download bars appear under albums on the artist page.
- **Quality & naming** — FLAC / 320 / 128, upgrade flags when below target, and custom folder/track templates.
- **Artist monitor profiles** — all albums, new-only, or unmonitored; per-artist singles override.
- **Import review** — after importing a library, link local-only artists and review weak tags.
- **Media server hooks** — refresh Plex / Jellyfin / Navidrome (or a generic webhook) after downloads/imports.
- **Release monitor** — scheduled + manual “Scan for new music”.
- **Library tools** — import existing collections, match files, and reorganize by template.
- **Optional app login + Traefik HTTPS mode** — form login and Secure cookies when behind a reverse proxy.
- **Multi-user music player** — `/player` with its own logins, playlists, drag-and-drop queue, wavy seek bar, and lossless streaming.
- **Admin Now Playing** — see who’s listening and force-pause a session.
- **Docker-first deploy** — single container, web UI on port `8787`.

## Download sources

| Provider | Auth | Notes |
|----------|------|-------|
| Deezer | ARL cookie | FLAC needs a HiFi-capable account |
| Tidal | Device link login | Premium typically required |
| Qobuz | Token + user ID + app ID + app secret | Same style as QobuzDownloaderX; email/password optional |

---

## Requirements

- Docker + Docker Compose **(recommended)**, **or**
- Python 3.12+, Node.js 22+ (local development)

---

## Install with Docker (recommended)

### 1. Clone

```bash
git clone git@github.com:PineDev1/Musicarr.git
cd Musicarr
```

Private repo: make sure your SSH key or `gh` auth can access `PineDev1/Musicarr`.

### 2. Start

```bash
docker compose up -d --build
```

Open **http://localhost:8787**.

Musicarr is designed as a **single process** (one container / one `uvicorn` worker). Do not run
multiple workers or replicas against the same SQLite database — downloads and the release monitor
are in-process and would race.

### 3. Volumes

| Host path | Container | Purpose |
|-----------|-----------|---------|
| `./data`  | `/config` | SQLite DB, settings, download staging |
| `./music` | `/music`  | Your music library |

Point Musicarr’s library path at `/music` inside the container (default), or mount a different host folder:

```yaml
volumes:
  - /path/on/host/Music:/music
```

### 4. Update

```bash
git pull
docker compose up -d --build
```

Or pull the prebuilt image:

```bash
docker pull ghcr.io/pinedev1/musicarr:1.6
```

### 5. Logs / stop

```bash
docker compose logs -f musicarr
docker compose down
```

### 6. Reverse proxy (Traefik)

Musicarr does **not** terminate TLS itself. Put Traefik (or another reverse proxy) in front and keep Musicarr on port `8787`.

1. Point DNS at Traefik and route `Host(\`music.example.com\`)` to the Musicarr service (port **8787**).
2. Example compose file: [`docker-compose.traefik.yml`](docker-compose.traefik.yml) (expects an external Docker network named `proxy`).
3. In **Settings → Security**:
   - Enable **app login** before exposing off your LAN
   - Enable **Behind HTTPS (Traefik terminates SSL)**
   - Set **Public domain** to the same hostname (e.g. `music.example.com`)
4. Copy the generated Traefik labels from that page if you are not using the example compose file.

With HTTPS mode on, Musicarr sets `Secure` session cookies so form login works through Traefik.

---

## Music player

Optional listening UI at **`/player`** — completely separate from the admin library manager.

1. In **Settings → Player**, enable **Enable music player**.
2. Create listener users (username + password). These are **not** the admin login.
3. Open `http(s)://your-host:8787/player` and sign in.
4. Browse with cover art, like tracks, use built-in mixes (Liked / Recently Added / Recently Played / Shuffle Mix), and create playlists with the **+** button.
5. Playback uses a floating pill bar with an **Android 13–style wavy seek scrubber** (customize under player Settings). Drag-and-drop to reorder the queue. Smart playlists suggest similar songs after you seed 10 tracks.

**Admin:** **Now Playing** in the main sidebar shows active listeners and can **Stop** (force-pause) their playback.

**Quality:** Musicarr streams the **original file bytes** (HTTP Range for seeking). FLAC stays FLAC — no server-side transcode or downsample.

Player users cannot download, manage Wanted/Queue, or change admin settings.

---

## Docker image

### Build locally

```bash
docker build -t musicarr:1.6 .
```

Run without Compose:

```bash
mkdir -p data music
docker run -d --name musicarr \
  -p 8787:8787 \
  -v "$(pwd)/data:/config" \
  -v "$(pwd)/music:/music" \
  -e MUSICARR_DATA_DIR=/config \
  -e MUSICARR_MUSIC_DIR=/music \
  musicarr:1.6
```

### GitHub Container Registry

```bash
echo YOUR_GITHUB_TOKEN | docker login ghcr.io -u PineDev1 --password-stdin
docker pull ghcr.io/pinedev1/musicarr:1.6
docker pull ghcr.io/pinedev1/musicarr:latest
```

```bash
docker run -d --name musicarr -p 8787:8787 \
  -v "$(pwd)/data:/config" -v "$(pwd)/music:/music" \
  ghcr.io/pinedev1/musicarr:1.6
```

---

## Quick start (first run)

1. Open the UI → **Settings → Sources** and connect Deezer, Tidal, or Qobuz.
2. Set **Library path** (Docker default: `/music`).
3. Optionally enable **app login** and **HTTPS / Traefik** under **Security**.
4. Optionally enable the **Player** tab and create listener accounts.
5. **Add Artist** → Musicarr syncs releases and can queue missing albums.
6. Or **Import existing library** if the files are already on disk.

---

## Local development

```bash
# Backend
cd backend
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python run.py
```

API: http://127.0.0.1:8787 · Docs: http://127.0.0.1:8787/docs

### Frontend (hot reload)

```bash
cd frontend
npm install
npm run dev
```

Vite: http://127.0.0.1:5173 (proxies `/api` to the backend).

Production UI into `backend/static`:

```bash
cd frontend && npm run build
```

---

## Branches

| Branch | Purpose |
|--------|---------|
| `main` | Stable / releases |
| `dev` | Active development |

---

## Import an existing library

1. In **Settings**, set **Library path** to the folder that already contains your music
   (e.g. `Artist/Album/01 - Track.flac`).
2. Click **Import existing library**.
3. Musicarr reads tags (and folder names as fallback), creates artists/albums/tracks, marks them
   downloaded, and when possible links artists to your **active** download source so you can
   grab missing releases later.
4. Open **Review imports** to link local-only artists to your active source and check weakly tagged
   albums.
5. Use **Match files to library** anytime to re-link files to artists you already added in Musicarr
   without creating new entries.

Supported audio: `.flac` `.mp3` `.m4a` `.ogg` `.opus` `.wav` `.aac` `.aiff`

- Folders: `{artist}/{album} ({year})`
- Tracks: `{track:02d} - {title}`

---

## What's new

### v1.6 — Local MusicBrainz + streaming-first library

- **Local MusicBrainz catalog** — Settings → MusicBrainz downloads a slim MetaBrainz dump (core + derived) into SQLite under ~20 GiB; artist resolve, catalogs, and credits run locally without live API 503 spam
- **Add Artist counts from MusicBrainz** — release counts come from the local catalog when Ready (not provider album totals)
- **Collaborator / featured-artist sync** — richer credits, shared-collab album IDs, and safer featured-artist linking
- **Streaming-only again** — indexers, qBittorrent/SABnzbd, path mappings, and Lidarr-style release grab removed
- **Player bar** — fixed volume (Web Audio GainNode), wider desktop titles, Apple Music–style mobile mini bar with expand + swipe-down sheet
- **Security & ops** — player admin routes require app login; CORS allowlist (no `*` + credentials); SQLite WAL + busy timeout; `download_concurrency` 1–4 honored; deterministic legacy IDs; collaborator name lookup without a silent 500-row cap

### Removed — Indexers / download clients

Indexer search, qBittorrent/SABnzbd clients, path mappings, and release grab are **removed**. Musicarr is streaming-only again (Deezer / Tidal / Qobuz). Those acquisition features may return in a future project.

### v1.5 — Lidarr-style release search (historical)

- Manual indexer grabs and download-client connectivity (since removed)

### v1.4 — Indexers + artist identity (historical)

- Indexers / download clients (since removed)
- **Same-name artists stay separate** — identity by provider ID; folders disambiguate on collision
- **pytest coverage** for artist identity guards

### v1.3 — Player + remote-ready

- **Multi-user `/player`** — separate logins, playlists, drag-and-drop queue, Liked Songs & mixes
- **Lossless streaming** — original files with HTTP Range; FLAC served as FLAC (no transcode)
- **Pill play bar + wavy seek** — Android 13–style scrubber with personal wave prefs
- **Smart playlists** — seed ≥10 tracks, get similar-song suggestions
- **Admin Now Playing** — live listeners + force-pause
- **Traefik / HTTPS mode** — Secure cookies, public domain, copyable labels
- **Optional app login** — protect the admin UI when exposing Musicarr

### v1.2

- Quality upgrades, artist monitor profiles, import review
- Media server refresh (Plex / Jellyfin / Navidrome / webhook)
- Tabbed settings

### v1.1

- Wanted filters, album detail, queue failure rematch
- Discord / webhook notifications, import existing library

### v1.0

- Initial multi-provider Musicarr (Docker + web UI)

---

## What's coming (v2.0)

v2.0 moves Musicarr from a download manager toward a **library OS**.

| Milestone | Focus |
|-----------|--------|
| **2.0a** | Metadata brain (MusicBrainz / ISRC-first) + stronger rematch/import review |
| **2.0b** | Multi-root library paths + tag/cover writeback |
| **2.0c** | Provider fallback for grab/upgrade |
| **2.0d** | Release calendar / discover, backup/restore, denser UI |

**Pillars:** canonical metadata separate from provider IDs; multiple library roots; smarter fulfillment across Deezer/Tidal/Qobuz; consistent tags & artwork; remote-ready access; backup/restore; UI leap.

**Not planned as v2.0 flagships:** full SSO / enterprise identity, or Spotify/YouTube download sources.

---

## Releases

- **[v1.6](https://github.com/PineDev1/Musicarr/releases/tag/v1.6)** — local MusicBrainz catalog, streaming-only, player UX + security hardening
- **[v1.5](https://github.com/PineDev1/Musicarr/releases/tag/v1.5)** — (historical) release search + download-client fixes; acquisition features later removed
- **[v1.4](https://github.com/PineDev1/Musicarr/releases/tag/v1.4)** — same-name artist identity (+ historical indexers)
- **[v1.3](https://github.com/PineDev1/Musicarr/releases/tag/v1.3)** — multi-user player, Traefik SSL, Now Playing
- **v1.0** — initial public release

See [Releases](https://github.com/PineDev1/Musicarr/releases) for tags and notes. Images: `ghcr.io/pinedev1/musicarr:1.6` · `latest`

---

## Security notes

- Do **not** commit `data/`, `.env`, ARL cookies, Qobuz tokens, or app secrets.
- Prefer Docker volumes with permissions only you can read.
- Rotate provider credentials if they leak.
- If you expose Musicarr through Traefik or another public hostname, enable **app login** and **HTTPS / Traefik mode** under Settings → Security.

---

## License / liability

No warranty. Use at your own risk. The author (**PineDev1**) accepts **no liability** for any use of this software.

---

## Legal disclaimer

**Musicarr is provided “as is”, without warranty of any kind, express or implied.**

By using this software you acknowledge and agree that:

1. **You alone are responsible** for how you use Musicarr, including compliance with the terms of service of Deezer, Tidal, Qobuz, and any other third party, as well as all applicable local copyright and intellectual-property laws.
2. Downloading or copying copyrighted music without authorization from the rights holder **may be illegal** in your jurisdiction and/or a violation of a streaming service’s terms.
3. **PineDev1 / the author / contributors hold no accountability** for misuse, account bans, legal claims, damages, data loss, or any other consequence arising from use of this project.
4. Credentials you paste into Musicarr (ARL cookies, tokens, app secrets, etc.) are stored **on your machine**. Protect them. Never commit them to git or share them publicly.
5. This software is intended for **personal, local use** on libraries you are legally entitled to manage. The author does not encourage or endorse piracy.

**If you do not agree, do not use Musicarr.**
