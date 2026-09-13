# Musicarr

Self-hosted music library manager with a simple web UI. Add artists, download discographies from **one active source** (Deezer, Tidal, or Qobuz), rename/organize files, and automatically fetch new releases.

**Author:** [PineDev1](https://github.com/PineDev1)

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

---

## Features

- **Multi-source downloads** — Deezer (ARL), Tidal (device login), or Qobuz (token / app credentials). One active source at a time.
- **Artist library** — search, add, and monitor artists; same artist across sources is merged into one library entry.
- **Wanted / Queue / Activity** — track missing albums, live download progress, and history.
- **In-artist progress** — download bars appear under albums on the artist page.
- **Quality & naming** — FLAC / 320 / 128, upgrade flags when below target, and custom folder/track templates.
- **Artist monitor profiles** — all albums, new-only, or unmonitored; per-artist singles override.
- **Import review** — after importing a library, link local-only artists and review weak tags.
- **Media server hooks** — refresh Plex / Jellyfin / Navidrome (or a generic webhook) after downloads/imports.
- **Release monitor** — scheduled + manual “Scan for new music”.
- **Library tools** — import existing collections, match files, and reorganize by template.
- **Per-provider logout** — clear credentials without wiping the rest of your settings.
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

### 5. Logs / stop

```bash
docker compose logs -f musicarr
docker compose down
```

---

## Docker image

### Build locally

```bash
docker build -t musicarr:1.0 .
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
  musicarr:1.0
```

### Optional: GitHub Container Registry

After authenticating to GHCR (`gh auth token | docker login ghcr.io -u PineDev1 --password-stdin`):

```bash
docker tag musicarr:1.0 ghcr.io/pinedev1/musicarr:1.0
docker tag musicarr:1.0 ghcr.io/pinedev1/musicarr:latest
docker push ghcr.io/pinedev1/musicarr:1.0
docker push ghcr.io/pinedev1/musicarr:latest
```

Pull and run:

```bash
docker pull ghcr.io/pinedev1/musicarr:1.0
docker run -d --name musicarr -p 8787:8787 \
  -v "$(pwd)/data:/config" \
  -v "$(pwd)/music:/music" \
  ghcr.io/pinedev1/musicarr:1.0
```

> Image publishing requires package write access on the private repo. Keep the package private if the repo is private.

---

## First-time setup (UI)

1. Open Settings.
2. Choose **Active download source** (Deezer / Tidal / Qobuz).
3. Sign in for that source (ARL, device code, or Qobuz token fields).
4. Set your **library path** and quality.
5. **Add Artist** → Musicarr syncs releases and can queue missing albums.
6. Use **Wanted** / **Queue** to manage downloads; open an artist for per-album progress.

### Deezer ARL

1. Log in at [deezer.com](https://www.deezer.com)
2. DevTools → **Application** → **Cookies** → `https://www.deezer.com`
3. Copy the `arl` value into Musicarr Settings

### Qobuz token

Use the same token / user ID / app ID / app secret workflow as [QobuzDownloaderX](https://github.com/ImAiiR/QobuzDownloaderX).

---

## Local development

Branches:

| Branch | Use |
|--------|-----|
| `main` | Stable / releases |
| `dev` | Ongoing development |

### Backend

```bash
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

### v1.2 (on `dev`)

- **Quality upgrades** — track album quality, flag below-target releases, and **Upgrade all**
- **Artist monitor profiles** — all albums, new-only, or unmonitored; per-artist singles override
- **Import review** — link local-only artists and review weakly tagged folders after import
- **Media server refresh** — notify Plex, Jellyfin, Navidrome, or a generic webhook after download/import

### v1.1 (on `dev`)

- **Wanted filters** — skip singles/junk/live noise; minimum track count
- **Album detail** — tracks, re-download, delete (± files)
- **Queue failures** — clearer rematch/auth errors, grouped retry
- **Discord / webhook notifications** on download complete or failure
- **Import existing library** — build your library from files already on disk

---

## Releases

- **v1.0** — initial public release of the multi-provider Musicarr app (Docker + web UI).

See [Releases](https://github.com/PineDev1/Musicarr/releases) for tags and notes.

---

## Security notes

- Do **not** commit `data/`, `.env`, ARL cookies, Qobuz tokens, or app secrets.
- Prefer Docker volumes with permissions only you can read.
- Rotate provider credentials if they leak.

---

## License / liability

No warranty. Use at your own risk. See **Legal disclaimer** above. The author (**PineDev1**) accepts **no liability** for any use of this software.
