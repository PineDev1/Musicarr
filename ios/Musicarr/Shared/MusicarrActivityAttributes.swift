import ActivityKit
import Foundation

/// Drives the Dynamic Island / lock-screen Live Activity. `ContentState` is
/// what changes per update (every track change, play/pause, or periodic
/// progress refresh); the attributes themselves are fixed for the
/// Activity's lifetime.
struct MusicarrActivityAttributes: ActivityAttributes {
    public struct ContentState: Codable, Hashable {
        var title: String
        var artistName: String
        var isPlaying: Bool
        var currentTime: Double
        var duration: Double
        var referenceDate: Date
        var hasArtwork: Bool

        var estimatedCurrentTime: Double {
            guard isPlaying else { return currentTime }
            let elapsed = Date().timeIntervalSince(referenceDate)
            return min(currentTime + elapsed, duration)
        }
    }
}
