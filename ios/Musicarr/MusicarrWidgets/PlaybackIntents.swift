import AppIntents

/// Interactive widget/Live Activity buttons run these in the extension
/// process — they never touch playback directly. Each just posts a Darwin
/// notification; PlaybackEngine (running in the main app, kept alive by its
/// own background-audio session while anything is playing) is listening for
/// exactly these names and performs the real action. Same cross-process
/// pattern real audio apps use for Live Activity/widget controls, since a
/// widget extension has no access to the app's in-memory AVPlayer.
private func signal(_ name: String) {
    CFNotificationCenterPostNotification(
        CFNotificationCenterGetDarwinNotifyCenter(),
        CFNotificationName(name as CFString),
        nil, nil, true
    )
}

struct PlayPauseIntent: AppIntent {
    static var title: LocalizedStringResource = "Play or Pause"
    static var isDiscoverable: Bool = false

    func perform() async throws -> some IntentResult {
        signal(PlaybackSignal.playPause)
        return .result()
    }
}

struct NextTrackIntent: AppIntent {
    static var title: LocalizedStringResource = "Next Track"
    static var isDiscoverable: Bool = false

    func perform() async throws -> some IntentResult {
        signal(PlaybackSignal.next)
        return .result()
    }
}

struct PreviousTrackIntent: AppIntent {
    static var title: LocalizedStringResource = "Previous Track"
    static var isDiscoverable: Bool = false

    func perform() async throws -> some IntentResult {
        signal(PlaybackSignal.previous)
        return .result()
    }
}
