import ActivityKit
import Foundation
import os

@MainActor
final class LiveActivityManager {
    private let log = Logger(subsystem: "com.musicarr.player", category: "LiveActivity")
    private var activity: Activity<MusicarrActivityAttributes>?

    func update(title: String, artistName: String, isPlaying: Bool, currentTime: Double, duration: Double, hasArtwork: Bool) {
        let state = MusicarrActivityAttributes.ContentState(
            title: title,
            artistName: artistName,
            isPlaying: isPlaying,
            currentTime: currentTime,
            duration: duration,
            referenceDate: Date(),
            hasArtwork: hasArtwork
        )

        if let activity {
            Task { await activity.update(ActivityContent(state: state, staleDate: nil)) }
            return
        }

        guard ActivityAuthorizationInfo().areActivitiesEnabled else {
            log.error("Live Activities not enabled (areActivitiesEnabled == false)")
            return
        }
        do {
            activity = try Activity.request(
                attributes: MusicarrActivityAttributes(),
                content: ActivityContent(state: state, staleDate: nil)
            )
            log.notice("Live Activity started \(self.activity?.id ?? "?", privacy: .public)")
        } catch {
            // Live Activities aren't essential to playback — a failure here
            // (e.g. the user disabled them in Settings) shouldn't affect
            // anything else.
            log.error("Live Activity request failed: \(String(describing: error), privacy: .public)")
        }
    }

    func end() {
        guard let activity else { return }
        Task { await activity.end(nil, dismissalPolicy: .immediate) }
        self.activity = nil
    }
}
