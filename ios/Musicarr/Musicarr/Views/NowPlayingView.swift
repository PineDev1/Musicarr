import SwiftUI

struct NowPlayingView: View {
    @EnvironmentObject var playback: PlaybackEngine
    @Environment(\.dismiss) private var dismiss
    @State private var isScrubbing = false
    @State private var scrubTime: Double = 0

    var body: some View {
        ZStack {
            Theme.background.ignoresSafeArea()
            VStack(spacing: 24) {
                Capsule()
                    .fill(Theme.border)
                    .frame(width: 40, height: 5)
                    .padding(.top, 8)

                if let track = playback.currentTrack {
                    Text(playback.sourceLabel.isEmpty ? "Now Playing" : playback.sourceLabel)
                        .font(.caption.smallCaps())
                        .foregroundStyle(Theme.muted)

                    RemoteArt(path: track.coverUrl, cornerRadius: 16)
                        .frame(width: 280, height: 280)
                        .shadow(color: .black.opacity(0.4), radius: 20, y: 10)

                    VStack(spacing: 4) {
                        Text(track.title)
                            .font(.title2.bold())
                            .foregroundStyle(Theme.text)
                            .multilineTextAlignment(.center)
                        Text(track.artistName)
                            .font(.body)
                            .foregroundStyle(Theme.muted)
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

                    HStack(spacing: 44) {
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
                    }
                    .foregroundStyle(Theme.text)
                } else {
                    Spacer()
                    Text("Nothing playing").foregroundStyle(Theme.muted)
                    Spacer()
                }

                Spacer()
            }
            .padding(.bottom, 20)
        }
    }

    private func formatTime(_ seconds: Double) -> String {
        guard seconds.isFinite, seconds >= 0 else { return "0:00" }
        let s = Int(seconds)
        return String(format: "%d:%02d", s / 60, s % 60)
    }
}
