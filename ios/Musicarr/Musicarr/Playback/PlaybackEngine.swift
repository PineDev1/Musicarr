import AVFoundation
import Combine
import MediaPlayer
import UIKit
import WidgetKit

enum RepeatMode {
    case off, all, one
}

@MainActor
final class PlaybackEngine: NSObject, ObservableObject {
    @Published private(set) var queue: [Track] = []
    @Published private(set) var currentIndex: Int?
    @Published private(set) var isPlaying = false
    @Published private(set) var currentTime: Double = 0
    @Published private(set) var duration: Double = 0
    @Published var sourceLabel: String = ""
    @Published private(set) var shuffleEnabled = false
    @Published private(set) var playbackSpeed: Double = {
        let v = UserDefaults.standard.double(forKey: "musicarr.playbackSpeed")
        return v >= 0.5 && v <= 2 ? v : 1.0
    }()
    @Published var repeatMode: RepeatMode = .off
    @Published var sleepDeadline: Date?

    private var originalQueue: [Track] = []
    private var sleepTimer: Timer?

    var currentTrack: Track? {
        guard let currentIndex, queue.indices.contains(currentIndex) else { return nil }
        return queue[currentIndex]
    }

    private var player: AVPlayer?
    private var timeObserver: Any?
    private var endObserver: NSObjectProtocol?
    private var artworkCache: [Int: MPMediaItemArtwork] = [:]
    private var artworkDataCache: [Int: Data] = [:]
    private var lastReportedSecond: Int = -1
    private let liveActivity = LiveActivityManager()

    override init() {
        super.init()
        configureAudioSession()
        configureRemoteCommands()
        configureSignalObservers()
    }

    // MARK: - Widget / Live Activity signal bridge

    private func configureSignalObservers() {
        let center = CFNotificationCenterGetDarwinNotifyCenter()
        let observer = Unmanaged.passUnretained(self).toOpaque()

        // A CFNotificationCallback must be a plain (non-capturing) C
        // function, so the fired notification's own `name` — the callback's
        // third parameter — is how this tells the three signals apart,
        // rather than three separate capturing closures (which Swift can't
        // convert to a C function pointer at all).
        let callback: CFNotificationCallback = { _, observer, name, _, _ in
            guard let observer, let name else { return }
            let engine = Unmanaged<PlaybackEngine>.fromOpaque(observer).takeUnretainedValue()
            Task { @MainActor in engine.handleSignal(name.rawValue as String) }
        }
        CFNotificationCenterAddObserver(center, observer, callback, PlaybackSignal.playPause as CFString, nil, .deliverImmediately)
        CFNotificationCenterAddObserver(center, observer, callback, PlaybackSignal.next as CFString, nil, .deliverImmediately)
        CFNotificationCenterAddObserver(center, observer, callback, PlaybackSignal.previous as CFString, nil, .deliverImmediately)
    }

    private func handleSignal(_ name: String) {
        switch name {
        case PlaybackSignal.playPause: togglePlayPause()
        case PlaybackSignal.next: next()
        case PlaybackSignal.previous: previous()
        default: break
        }
    }

    // MARK: - Shared snapshot (widget + Live Activity)

    private func publishSharedState() {
        guard let track = currentTrack else {
            NowPlayingSnapshot.clear()
            WidgetCenter.shared.reloadTimelines(ofKind: "NowPlayingWidget")
            liveActivity.end()
            return
        }
        let hasArtwork = artworkDataCache[track.id] != nil
        if let data = artworkDataCache[track.id], let url = AppGroup.artworkURL {
            try? data.write(to: url)
        }
        NowPlayingSnapshot(
            trackID: track.id,
            title: track.title,
            artistName: track.artistName,
            albumTitle: track.albumTitle,
            isPlaying: isPlaying,
            currentTime: currentTime,
            duration: duration,
            referenceDate: Date(),
            hasArtwork: hasArtwork
        ).save()
        WidgetCenter.shared.reloadTimelines(ofKind: "NowPlayingWidget")
        liveActivity.update(
            title: track.title,
            artistName: track.artistName,
            isPlaying: isPlaying,
            currentTime: currentTime,
            duration: duration,
            hasArtwork: hasArtwork
        )
    }

    private func configureAudioSession() {
        let session = AVAudioSession.sharedInstance()
        try? session.setCategory(.playback, mode: .default, options: [])
        try? session.setActive(true)
    }

    // MARK: - Queue control

    func play(tracks: [Track], startIndex: Int = 0, sourceLabel: String = "") {
        guard tracks.indices.contains(startIndex) else { return }
        self.queue = tracks
        self.sourceLabel = sourceLabel
        self.shuffleEnabled = false
        self.originalQueue = []
        loadAndPlay(index: startIndex)
    }

    func playNext(_ track: Track) {
        guard let currentIndex else {
            queue = [track]
            loadAndPlay(index: 0)
            return
        }
        queue.insert(track, at: currentIndex + 1)
    }

    func addToEnd(_ track: Track) {
        queue.append(track)
    }

    func removeFromQueue(at index: Int) {
        guard queue.indices.contains(index), index != currentIndex else { return }
        queue.remove(at: index)
        if let currentIndex, index < currentIndex {
            self.currentIndex = currentIndex - 1
        }
    }

    func moveInQueue(from source: IndexSet, to destination: Int) {
        guard let current = currentTrack else {
            queue.move(fromOffsets: source, toOffset: destination)
            return
        }
        queue.move(fromOffsets: source, toOffset: destination)
        currentIndex = queue.firstIndex(of: current)
    }

    func toggleShuffle() {
        guard let current = currentTrack else {
            shuffleEnabled.toggle()
            return
        }
        if shuffleEnabled {
            // Turning off: restore original order, keeping playback on the
            // same track rather than jumping the user's place in the queue.
            queue = originalQueue
            currentIndex = queue.firstIndex(of: current)
            shuffleEnabled = false
        } else {
            originalQueue = queue
            var rest = queue
            rest.removeAll { $0.id == current.id }
            rest.shuffle()
            queue = [current] + rest
            currentIndex = 0
            shuffleEnabled = true
        }
    }

    func cycleRepeatMode() {
        switch repeatMode {
        case .off: repeatMode = .all
        case .all: repeatMode = .one
        case .one: repeatMode = .off
        }
    }

    // MARK: - Sleep timer

    func startSleepTimer(minutes: Double) {
        sleepTimer?.invalidate()
        let deadline = Date().addingTimeInterval(minutes * 60)
        sleepDeadline = deadline
        sleepTimer = Timer.scheduledTimer(withTimeInterval: minutes * 60, repeats: false) { [weak self] _ in
            Task { @MainActor in self?.fireSleepTimer() }
        }
    }

    /// "End of song" — no fixed deadline, just pause when the current track
    /// finishes; handled directly in the end-of-track observer.
    func sleepAtEndOfSong() {
        sleepTimer?.invalidate()
        sleepTimer = nil
        sleepDeadline = .distantFuture
    }

    func cancelSleepTimer() {
        sleepTimer?.invalidate()
        sleepTimer = nil
        sleepDeadline = nil
    }

    private func fireSleepTimer() {
        if isPlaying { togglePlayPause() }
        sleepDeadline = nil
        sleepTimer = nil
    }

    private func loadAndPlay(index: Int) {
        guard queue.indices.contains(index) else { return }
        currentIndex = index
        let track = queue[index]
        guard let url = APIClient.shared.streamURL(trackID: track.id) else { return }

        removeObservers()
        let item = AVPlayerItem(url: url)
        let newPlayer = AVPlayer(playerItem: item)
        player = newPlayer
        addObservers(item: item)
        newPlayer.defaultRate = Float(playbackSpeed)
        newPlayer.play()
        isPlaying = true
        currentTime = 0
        duration = Double(track.duration)
        updateNowPlayingInfo()
        loadArtworkIfNeeded(for: track)
        publishSharedState()
        Task { try? await PlayerAPI.reportPlaying(trackID: track.id, position: 0, playing: true, title: track.title, artistName: track.artistName, coverURL: track.coverUrl) }
    }

    func setPlaybackSpeed(_ speed: Double) {
        playbackSpeed = speed
        UserDefaults.standard.set(speed, forKey: "musicarr.playbackSpeed")
        player?.defaultRate = Float(speed)
        if isPlaying { player?.rate = Float(speed) }
        updateNowPlayingInfo()
    }

    func togglePlayPause() {
        guard let player else { return }
        if isPlaying {
            player.pause()
            isPlaying = false
        } else {
            player.play()
            isPlaying = true
        }
        updateNowPlayingInfo()
        reportCurrentState()
        publishSharedState()
    }

    func next() {
        guard let currentIndex else { return }
        if queue.indices.contains(currentIndex + 1) {
            loadAndPlay(index: currentIndex + 1)
        } else if repeatMode == .all, !queue.isEmpty {
            loadAndPlay(index: 0)
        }
    }

    /// Distinct from `next()`: called when a track finishes on its own,
    /// where repeat-one and the "end of song" sleep timer both apply —
    /// neither should affect a manual tap on the skip button.
    private func handleTrackFinished() {
        if sleepDeadline == .distantFuture {
            sleepDeadline = nil
            isPlaying = false
            player?.pause()
            updateNowPlayingInfo()
            publishSharedState()
            return
        }
        if repeatMode == .one, let currentIndex {
            loadAndPlay(index: currentIndex)
            return
        }
        next()
    }

    func previous() {
        guard let currentIndex else { return }
        if currentTime > 3 {
            seek(to: 0)
            return
        }
        guard queue.indices.contains(currentIndex - 1) else {
            seek(to: 0)
            return
        }
        loadAndPlay(index: currentIndex - 1)
    }

    func seek(to seconds: Double) {
        let time = CMTime(seconds: seconds, preferredTimescale: 600)
        player?.seek(to: time)
        currentTime = seconds
        updateNowPlayingInfo()
        reportCurrentState()
    }

    private func reportCurrentState() {
        guard let track = currentTrack else { return }
        Task { try? await PlayerAPI.reportPlaying(trackID: track.id, position: currentTime, playing: isPlaying) }
    }

    // MARK: - Player observers

    private func addObservers(item: AVPlayerItem) {
        timeObserver = player?.addPeriodicTimeObserver(forInterval: CMTime(seconds: 1, preferredTimescale: 1), queue: .main) { [weak self] time in
            Task { @MainActor in
                guard let self else { return }
                self.currentTime = time.seconds.isFinite ? time.seconds : 0
                if let duration = item.duration.seconds.isFinite ? item.duration.seconds : nil, duration > 0 {
                    self.duration = duration
                }
                self.updateNowPlayingElapsed()
                let second = Int(self.currentTime)
                if second != self.lastReportedSecond, second % 15 == 0 {
                    self.lastReportedSecond = second
                    self.reportCurrentState()
                    self.publishSharedState()
                }
            }
        }
        endObserver = NotificationCenter.default.addObserver(
            forName: .AVPlayerItemDidPlayToEndTime, object: item, queue: .main
        ) { [weak self] _ in
            Task { @MainActor in self?.handleTrackFinished() }
        }
    }

    private func removeObservers() {
        if let timeObserver, let player {
            player.removeTimeObserver(timeObserver)
        }
        timeObserver = nil
        if let endObserver {
            NotificationCenter.default.removeObserver(endObserver)
        }
        endObserver = nil
    }

    // MARK: - Now Playing / Control Center / lock screen

    private func configureRemoteCommands() {
        let center = MPRemoteCommandCenter.shared()
        center.playCommand.addTarget { [weak self] _ in
            guard let self else { return .commandFailed }
            if !self.isPlaying { self.togglePlayPause() }
            return .success
        }
        center.pauseCommand.addTarget { [weak self] _ in
            guard let self else { return .commandFailed }
            if self.isPlaying { self.togglePlayPause() }
            return .success
        }
        center.nextTrackCommand.addTarget { [weak self] _ in
            self?.next()
            return .success
        }
        center.previousTrackCommand.addTarget { [weak self] _ in
            self?.previous()
            return .success
        }
        center.changePlaybackPositionCommand.addTarget { [weak self] event in
            guard let self, let event = event as? MPChangePlaybackPositionCommandEvent else { return .commandFailed }
            self.seek(to: event.positionTime)
            return .success
        }
    }

    private func updateNowPlayingInfo() {
        guard let track = currentTrack else {
            MPNowPlayingInfoCenter.default().nowPlayingInfo = nil
            return
        }
        var info: [String: Any] = [
            MPMediaItemPropertyTitle: track.title,
            MPMediaItemPropertyArtist: track.artistName,
            MPMediaItemPropertyAlbumTitle: track.albumTitle,
            MPMediaItemPropertyPlaybackDuration: duration,
            MPNowPlayingInfoPropertyElapsedPlaybackTime: currentTime,
            MPNowPlayingInfoPropertyPlaybackRate: isPlaying ? playbackSpeed : 0.0,
        ]
        if let artwork = artworkCache[track.id] {
            info[MPMediaItemPropertyArtwork] = artwork
        }
        MPNowPlayingInfoCenter.default().nowPlayingInfo = info
    }

    private func updateNowPlayingElapsed() {
        var info = MPNowPlayingInfoCenter.default().nowPlayingInfo ?? [:]
        info[MPNowPlayingInfoPropertyElapsedPlaybackTime] = currentTime
        info[MPMediaItemPropertyPlaybackDuration] = duration
        MPNowPlayingInfoCenter.default().nowPlayingInfo = info
    }

    private func loadArtworkIfNeeded(for track: Track) {
        guard artworkCache[track.id] == nil, let url = APIClient.shared.absoluteMediaURL(track.coverUrl) else { return }
        Task {
            guard let (data, _) = try? await URLSession.shared.data(from: url), let image = UIImage(data: data) else { return }
            // Re-encode as JPEG for the shared App Group file the widget and
            // Live Activity read — the original might be PNG/WebP and this
            // keeps the shared file small and universally decodable.
            let jpeg = image.jpegData(compressionQuality: 0.85)
            let artwork = MPMediaItemArtwork(boundsSize: image.size) { _ in image }
            await MainActor.run {
                self.artworkCache[track.id] = artwork
                if let jpeg { self.artworkDataCache[track.id] = jpeg }
                if self.currentTrack?.id == track.id {
                    self.updateNowPlayingInfo()
                    self.publishSharedState()
                }
            }
        }
    }
}
