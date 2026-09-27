import SwiftUI

struct NowPlayingView: View {
    @EnvironmentObject var playback: PlaybackEngine
    @EnvironmentObject var favorites: FavoritesStore
    @Environment(\.dismiss) private var dismiss
    @State private var isScrubbing = false
    @State private var scrubTime: Double = 0
    @State private var showLyrics = false
    @State private var showQueue = false
    @State private var showSleepTimer = false
    @State private var showAddToPlaylist = false
    @State private var shareURL: IdentifiableShareURL?

    var body: some View {
        ZStack {
            Theme.background.ignoresSafeArea()
            VStack(spacing: 24) {
                Capsule()
                    .fill(Theme.border)
                    .frame(width: 40, height: 5)
                    .padding(.top, 8)

                if let track = playback.currentTrack {
                    HStack {
                        AirPlayButton()
                            .frame(width: 32, height: 32)
                        Spacer()
                        Text(playback.sourceLabel.isEmpty ? "Now Playing" : playback.sourceLabel)
                            .font(.caption.smallCaps())
                            .foregroundStyle(Theme.muted)
                        Spacer()
                        Menu {
                            Button {
                                showAddToPlaylist = true
                            } label: {
                                Label("Add to Playlist…", systemImage: "plus.circle")
                            }
                            Button {
                                Task { await createShare(for: track) }
                            } label: {
                                Label("Share Song", systemImage: "square.and.arrow.up")
                            }
                        } label: {
                            Image(systemName: "ellipsis.circle")
                                .foregroundStyle(Theme.text)
                                .frame(width: 32, height: 32)
                        }
                    }
                    .padding(.horizontal, 24)

                    Group {
                        if showLyrics {
                            LyricsView(trackID: track.id, currentTime: playback.currentTime)
                                .frame(height: 280)
                        } else {
                            RemoteArt(path: track.coverUrl, cornerRadius: 16)
                                .frame(width: 280, height: 280)
                                .shadow(color: .black.opacity(0.4), radius: 20, y: 10)
                        }
                    }
                    // Swipe up on the artwork/lyrics area to reveal or hide
                    // lyrics, in addition to the explicit LYRICS button below
                    // — mirrors the gesture from the reference design.
                    .gesture(
                        DragGesture(minimumDistance: 20)
                            .onEnded { value in
                                if value.translation.height < -30 {
                                    withAnimation { showLyrics = true }
                                } else if value.translation.height > 30 {
                                    withAnimation { showLyrics = false }
                                }
                            }
                    )

                    VStack(spacing: 4) {
                        Text(track.title)
                            .font(.title2.bold())
                            .foregroundStyle(Theme.text)
                            .multilineTextAlignment(.center)
                        HStack(spacing: 8) {
                            Text(track.artistName)
                                .font(.body)
                                .foregroundStyle(Theme.muted)
                            Button {
                                withAnimation { showLyrics.toggle() }
                            } label: {
                                Text("LYRICS")
                                    .font(.caption2.bold())
                                    .foregroundStyle(showLyrics ? Theme.accent : Theme.muted)
                                    .padding(.horizontal, 8)
                                    .padding(.vertical, 3)
                                    .background(Theme.backgroundSoft)
                                    .clipShape(Capsule())
                            }
                        }
                    }
                    .padding(.horizontal, 32)

                    VStack(spacing: 6) {
                        Slider(
                            value: Binding(
                                get: { isScrubbing ? scrubTime : playback.currentTime },
                                set: { scrubTime = $0 }
                            ),
                            in: 0...max(playback.duration, 1),
                            onEditingChanged: { editing in
                                isScrubbing = editing
                                if !editing { playback.seek(to: scrubTime) }
                            }
                        )
                        .tint(Theme.accent)

                        HStack {
                            Text(formatTime(isScrubbing ? scrubTime : playback.currentTime))
                            Spacer()
                            Text(formatTime(playback.duration))
                        }
                        .font(.caption.monospacedDigit())
                        .foregroundStyle(Theme.muted)
                    }
                    .padding(.horizontal, 24)

                    HStack(spacing: 30) {
                        Button { playback.toggleShuffle() } label: {
                            Image(systemName: "shuffle")
                                .foregroundStyle(playback.shuffleEnabled ? Theme.accent : Theme.muted)
                        }
                        Button { playback.previous() } label: {
                            Image(systemName: "backward.fill").font(.title)
                        }
                        Button { playback.togglePlayPause() } label: {
                            Image(systemName: playback.isPlaying ? "pause.circle.fill" : "play.circle.fill")
                                .font(.system(size: 64))
                        }
                        Button { playback.next() } label: {
                            Image(systemName: "forward.fill").font(.title)
                        }
                        Button { playback.cycleRepeatMode() } label: {
                            Image(systemName: playback.repeatMode == .one ? "repeat.1" : "repeat")
                                .foregroundStyle(playback.repeatMode == .off ? Theme.muted : Theme.accent)
                        }
                    }
                    .foregroundStyle(Theme.text)

                    HStack(spacing: 16) {
                        Button {
                            favorites.toggle(track)
                        } label: {
                            Label(favorites.isFavorite(track.id) ? "Loved" : "Love", systemImage: favorites.isFavorite(track.id) ? "heart.fill" : "heart")
                        }
                        .foregroundStyle(favorites.isFavorite(track.id) ? Theme.accent : Theme.muted)

                        Spacer()

                        Button {
                            showSleepTimer = true
                        } label: {
                            Label(sleepLabel, systemImage: "moon.fill")
                        }
                        .foregroundStyle(playback.sleepDeadline != nil ? Theme.accent : Theme.muted)

                        Button {
                            showQueue = true
                        } label: {
                            Label("Queue", systemImage: "list.bullet")
                        }
                        .foregroundStyle(Theme.muted)
                    }
                    .font(.footnote)
                    .padding(.horizontal, 24)
                } else {
                    Spacer()
                    Text("Nothing playing").foregroundStyle(Theme.muted)
                    Spacer()
                }

                Spacer()
            }
            .padding(.bottom, 20)
        }
        .sheet(isPresented: $showQueue) { QueueView() }
        .sheet(isPresented: $showSleepTimer) { sleepTimerSheet }
        .sheet(isPresented: $showAddToPlaylist) {
            if let track = playback.currentTrack {
                AddToPlaylistSheet(track: track)
            }
        }
        .sheet(item: $shareURL) { wrapped in
            ActivityShareSheet(items: [wrapped.url])
        }
    }

    private var sleepLabel: String {
        guard let deadline = playback.sleepDeadline else { return "Sleep" }
        if deadline == .distantFuture { return "End of song" }
        let minutes = max(0, Int(deadline.timeIntervalSinceNow / 60))
        return "\(minutes)m"
    }

    private var sleepTimerSheet: some View {
        NavigationStack {
            List {
                ForEach([15.0, 30.0, 60.0], id: \.self) { minutes in
                    Button("\(Int(minutes)) min") {
                        playback.startSleepTimer(minutes: minutes)
                        showSleepTimer = false
                    }
                }
                Button("End of song") {
                    playback.sleepAtEndOfSong()
                    showSleepTimer = false
                }
                if playback.sleepDeadline != nil {
                    Button("Cancel sleep timer", role: .destructive) {
                        playback.cancelSleepTimer()
                        showSleepTimer = false
                    }
                }
            }
            .navigationTitle("Sleep Timer")
            .navigationBarTitleDisplayMode(.inline)
        }
        .presentationDetents([.medium])
    }

    private func createShare(for track: Track) async {
        if let info = try? await PlayerAPI.createShare(trackID: track.id), let url = URL(string: info.url) {
            shareURL = IdentifiableShareURL(url: url)
        }
    }

    private func formatTime(_ seconds: Double) -> String {
        guard seconds.isFinite, seconds >= 0 else { return "0:00" }
        let s = Int(seconds)
        return String(format: "%d:%02d", s / 60, s % 60)
    }
}

struct IdentifiableShareURL: Identifiable {
    let url: URL
    var id: String { url.absoluteString }
}
