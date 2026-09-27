import Foundation

/// Everything the main app and the widget/Live Activity extension share.
/// Deliberately minimal: the extension never calls the backend or holds the
/// session cookie — it only reads a snapshot the app writes, and sends
/// playback commands back via Darwin notifications the app (kept alive by
/// its own background-audio session) is always listening for. This avoids
/// giving the extension process any of the app's auth state.
enum AppGroup {
    static let id = "group.com.musicarr.player"

    static var defaults: UserDefaults? {
        UserDefaults(suiteName: id)
    }

    static var containerURL: URL? {
        FileManager.default.containerURL(forSecurityApplicationGroupIdentifier: id)
    }

    static var artworkURL: URL? {
        containerURL?.appendingPathComponent("now-playing-artwork.jpg")
    }
}

/// Darwin notification names the widget/Live Activity's AppIntents post and
/// the main app's PlaybackEngine listens for. Darwin notifications cross
/// process boundaries with no payload — just a wakeup signal — which is all
/// a play/pause/skip command needs.
enum PlaybackSignal {
    static let playPause = "com.musicarr.player.signal.playPause"
    static let next = "com.musicarr.player.signal.next"
    static let previous = "com.musicarr.player.signal.previous"
}

struct NowPlayingSnapshot: Codable {
    var trackID: Int
    var title: String
    var artistName: String
    var albumTitle: String
    var isPlaying: Bool
    var currentTime: Double
    var duration: Double
    /// The wall-clock time `currentTime` was accurate as of — lets a widget
    /// or Live Activity interpolate elapsed time between app-driven updates
    /// without polling, using SwiftUI's `Text(timerInterval:)`/manual math.
    var referenceDate: Date
    var hasArtwork: Bool

    private static let key = "nowPlayingSnapshot"

    static func load() -> NowPlayingSnapshot? {
        guard let data = AppGroup.defaults?.data(forKey: key) else { return nil }
        return try? JSONDecoder().decode(NowPlayingSnapshot.self, from: data)
    }

    func save() {
        guard let data = try? JSONEncoder().encode(self) else { return }
        AppGroup.defaults?.set(data, forKey: Self.key)
    }

    static func clear() {
        AppGroup.defaults?.removeObject(forKey: key)
    }

    /// Elapsed playback position right now, accounting for time passed
    /// since `referenceDate` while actively playing.
    var estimatedCurrentTime: Double {
        guard isPlaying else { return currentTime }
        let elapsed = Date().timeIntervalSince(referenceDate)
        return min(currentTime + elapsed, duration)
    }
}
