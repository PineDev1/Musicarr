# Musicarr for iOS

A native SwiftUI client for the Musicarr Player — the same `/api/player/*`
backend the web player (`frontend/src/player/`) already talks to.

- **Phase 1**: sign in, browse your library, search, play — background
  audio, lock screen / Control Center controls, AirPlay, favorites, synced
  lyrics, matching the web player's dark + green theme.
- **Phase 2**: Dynamic Island / lock-screen Live Activity for Now Playing,
  with play/pause/skip controls.
- **Phase 3**: a Home Screen widget (small + medium) showing Now Playing,
  also with playback controls.

Phase 2 and 3 share a `MusicarrWidgets` WidgetKit extension target (in
`ios/Musicarr/MusicarrWidgets/`) and a small `Shared/` module used by both
the app and the extension:

- The app writes a snapshot of what's playing (title/artist/artwork) into an
  App Group container (`group.com.musicarr.player`) whenever playback state
  changes, and asks WidgetKit to reload — the widget/Live Activity never
  call the backend or hold any auth state themselves, they only read that
  snapshot.
- Play/pause/skip buttons in the widget and Live Activity are App Intents
  that run in the extension process; since a widget extension has no access
  to the app's in-memory `AVPlayer`, each button just posts a Darwin
  notification, and `PlaybackEngine` (kept alive in the main app by its own
  background-audio session while anything is playing) is listening for
  those and performs the real action — the same cross-process pattern most
  audio apps use for this.

Verified end to end in the iOS Simulator: the Live Activity starts and
renders in the Dynamic Island (confirmed via the Home Screen — it doesn't
render while Musicarr itself is in the foreground, which is normal iOS
behavior) and the widget extension renders without errors per the system
log. Try it on a real device for the full experience, including the
interactive buttons.

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
- `Musicarr/Views/` — SwiftUI screens.
- `Shared/` — compiled into both the app and `MusicarrWidgets`: `Theme.swift`
  (the exact color values from the web player's `index.css`, so both clients
  and the widget/Live Activity read as the same product),
  `MusicarrActivityAttributes.swift` (the Live Activity's data shape), and
  `AppGroup.swift` (the shared snapshot + Darwin notification names).
- `MusicarrWidgets/` — the WidgetKit extension: `NowPlayingWidget.swift`
  (Home Screen widget), `MusicarrLiveActivity.swift` (Dynamic Island / lock
  screen), `PlaybackIntents.swift` (the interactive buttons' App Intents).
