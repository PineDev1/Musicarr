import AVFoundation
import Combine
import MediaPlayer
import UIKit

@MainActor
final class PlaybackEngine: NSObject, ObservableObject {
    @Published private(set) var queue: [Track] = []
    @Published private(set) var currentIndex: Int?
    @Published private(set) var isPlaying = false
    @Published private(set) var currentTime: Double = 0
    @Published private(set) var duration: Double = 0
    @Published var sourceLabel: String = ""

    var currentTrack: Track? {
        guard let currentIndex, queue.indices.contains(currentIndex) else { return nil }
        return queue[currentIndex]
    }

    private var player: AVPlayer?
    private var timeObserver: Any?
    private var endObserver: NSObjectProtocol?
    private var artworkCache: [Int: MPMediaItemArtwork] = [:]
    private var lastReportedSecond: Int = -1

    override init() {
        super.init()
        configureAudioSession()
        configureRemoteCommands()
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
        newPlayer.play()
        isPlaying = true
        currentTime = 0
        duration = Double(track.duration)
        updateNowPlayingInfo()
        loadArtworkIfNeeded(for: track)
        Task { try? await PlayerAPI.reportPlaying(trackID: track.id, position: 0, playing: true, title: track.title, artistName: track.artistName, coverURL: track.coverUrl) }
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
    }

    func next() {
        guard let currentIndex, queue.indices.contains(currentIndex + 1) else { return }
        loadAndPlay(index: currentIndex + 1)
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
            }
        }
        endObserver = NotificationCenter.default.addObserver(
            forName: .AVPlayerItemDidPlayToEndTime, object: item, queue: .main
        ) { [weak self] _ in
            Task { @MainActor in self?.next() }
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
            MPNowPlayingInfoPropertyPlaybackRate: isPlaying ? 1.0 : 0.0,
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
            let artwork = MPMediaItemArtwork(boundsSize: image.size) { _ in image }
            await MainActor.run {
                self.artworkCache[track.id] = artwork
                if self.currentTrack?.id == track.id {
                    self.updateNowPlayingInfo()
                }
            }
        }
    }
}
