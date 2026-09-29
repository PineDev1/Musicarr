# Musicarr for iOS

> **Status: very early beta.** This has been built and smoke-tested in the
> iOS Simulator against a real local Musicarr instance — sign-in, browsing,
> playback, lyrics, sharing, the queue, and the Dynamic Island/widget have
> all been individually exercised and confirmed working. It has **not**
> been run on a real device yet, hasn't been used for extended real-world
> listening, and almost certainly has rough edges: missing error states,
> untested network-loss/backgrounding edge cases, and features that work in
> the simulator but haven't been proven under real cellular/Wi-Fi
> conditions. Treat it as a first working build to try and break, not a
> finished app — expect to file (or just fix) bugs as you use it.

A native SwiftUI client for the Musicarr Player — the same `/api/player/*`
backend the web player (`frontend/src/player/`) already talks to.

- **Phase 1**: sign in, browse your library, search, play — background
  audio, lock screen / Control Center controls, AirPlay, favorites, synced
  lyrics (swipe up on the artwork, or tap the LYRICS pill), shuffle/repeat,
  a queue you can view/reorder/remove from, creating and adding to
  playlists from the app (shared with the web player — same account, same
  server-side playlists), sharing a song, a sleep timer, Last.fm
  connect/disconnect (scrobbling itself already happens server-side, the
  same way it does for the web player), and your account avatar — all
  matching the web player's dark + green theme.
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

## Installing on your own iPhone

No paid Apple Developer account needed — a free Apple ID is enough to run
this on your own device for personal use (it just needs reinstalling every
7 days, see below).

1. **Connect your iPhone** to the Mac with a cable (or over Wi-Fi once
   you've paired it once in Xcode: Window → Devices and Simulators).
2. **Generate and open the project** (see Building, above):
   ```bash
   cd ios/Musicarr
   xcodegen generate
   open Musicarr.xcodeproj
   ```
3. **Add your Apple ID to Xcode**, if it isn't already: Xcode → Settings →
   Accounts → `+` → sign in with your regular Apple ID (no enrollment,
   no payment).
4. **Set the signing team on both targets** — this project has two:
   `Musicarr` (the app) and `MusicarrWidgets` (the widget/Dynamic Island
   extension), and both need it. For each: select it in the project
   navigator's target list → **Signing & Capabilities** tab → check
   "Automatically manage signing" → set **Team** to your Apple ID (shown as
   "your name (Personal Team)").
5. **Pick your iPhone** as the run destination in Xcode's device/scheme
   picker at the top of the window (instead of a Simulator), then press
   Run (▶). First build/install can take a minute.
6. **Trust the developer certificate on the phone** (only needed once): on
   the iPhone, go to Settings → General → VPN & Device Management → under
   "Developer App", tap your Apple ID → Trust.
7. On first launch, enter your Musicarr server's **real, reachable
   address** — not `localhost` (that only makes sense from a Mac/Simulator
   reaching a server running on the same machine). Use whatever address
   your phone can actually reach it at: a LAN IP on the same Wi-Fi, or your
   remote/Unraid box's address if you access it that way.

**Free-account limits to know about**: the app stops launching after **7
days** and needs re-running from Xcode to keep working (a paid $99/year
Apple Developer account removes this limit, entirely optional for personal
use); a free account can also only have a handful of self-signed apps
installed on a device at once, so remove old test apps if you hit that
ceiling.

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
