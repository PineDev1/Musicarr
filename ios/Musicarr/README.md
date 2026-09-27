# Musicarr for iOS

A native SwiftUI client for the Musicarr Player — the same `/api/player/*`
backend the web player (`frontend/src/player/`) already talks to. Phase 1:
sign in, browse your library, and play — background audio, lock screen /
Control Center controls, matching the web player's dark + green theme.

Dynamic Island (Live Activity) and Home Screen widgets are planned next
phases, built on top of this playback engine.

## Requirements

- Full Xcode (not just the Command Line Tools) — check with:
  ```bash
  xcodebuild -version
  ```
  If `xcode-select -p` points at `CommandLineTools` instead of `Xcode.app`,
  fix it once (needs your admin password):
  ```bash
  sudo xcode-select -s /Applications/Xcode.app/Contents/Developer
  ```
- [XcodeGen](https://github.com/yonaskolb/XcodeGen) to generate the
  `.xcodeproj` from `project.yml` (the project file itself isn't committed —
  it's generated, same idea as a lockfile):
  ```bash
  brew install xcodegen
  ```

## Building

```bash
cd ios/Musicarr
xcodegen generate
open Musicarr.xcodeproj
```

Then Run in Xcode (a simulator or your own device). Or from the command
line:

```bash
xcodebuild -project Musicarr.xcodeproj -scheme Musicarr \
  -destination 'platform=iOS Simulator,name=iPhone 17 Pro' build
```

## Using the app

On first launch, enter your Musicarr server's address (e.g.
`192.168.1.10:8787` — no `http://` needed, it's added automatically) and
sign in with a Player account (Settings → Player in the Musicarr web admin
creates these; it's a separate account system from the admin login). The
server only needs to be reachable on your network — self-hosted instances
running plain HTTP are allowed (`NSAllowsArbitraryLoads` is set in
`project.yml`, same reasoning Infuse/Plex clients use for LAN servers
without TLS).

The session cookie persists across app relaunches automatically (iOS's
standard cookie storage), so signing in again isn't needed unless you sign
out or the server invalidates the session.

## Project layout

- `Musicarr/Models/` — Codable structs mirroring the backend's
  `PlayerTrackOut`/`PlayerAlbumOut`/etc. schemas
  (`backend/app/models/schemas.py`).
- `Musicarr/Networking/` — `APIClient` (base URL + cookie session) and
  `PlayerAPI` (one function per endpoint, mirroring
  `frontend/src/player/playerApi.ts`'s shape).
- `Musicarr/Session/` — auth state.
- `Musicarr/Playback/` — `PlaybackEngine`: AVPlayer-backed queue, background
  audio session, `MPNowPlayingInfoCenter`/`MPRemoteCommandCenter` wiring for
  lock screen and Control Center.
- `Musicarr/Views/` — SwiftUI screens; `Theme.swift` holds the exact color
  values from the web player's `index.css` so both clients read as the same
  product.
