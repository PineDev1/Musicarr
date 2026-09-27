import SwiftUI

struct MiniPlayerBar: View {
    @EnvironmentObject var playback: PlaybackEngine
    @State private var showFullPlayer = false

    var body: some View {
        if let track = playback.currentTrack {
            Button {
                showFullPlayer = true
            } label: {
                HStack(spacing: 12) {
                    RemoteArt(path: track.coverUrl, cornerRadius: 6)
                        .frame(width: 40, height: 40)
                    VStack(alignment: .leading, spacing: 1) {
                        Text(track.title)
                            .font(.subheadline.weight(.medium))
                            .foregroundStyle(Theme.text)
                            .lineLimit(1)
                        Text(track.artistName)
                            .font(.caption2)
                            .foregroundStyle(Theme.muted)
                            .lineLimit(1)
                    }
                    Spacer()
                    Button {
                        playback.togglePlayPause()
                    } label: {
                        Image(systemName: playback.isPlaying ? "pause.fill" : "play.fill")
                            .font(.title3)
                            .foregroundStyle(Theme.text)
                    }
                    Button {
                        playback.next()
                    } label: {
                        Image(systemName: "forward.fill")
                            .font(.title3)
                            .foregroundStyle(Theme.text)
                    }
                }
                .padding(.horizontal, 12)
                .padding(.vertical, 8)
            }
            .buttonStyle(.plain)
            .background(.ultraThinMaterial)
            .overlay(alignment: .top) {
                ProgressBarSliver(progress: playback.duration > 0 ? playback.currentTime / playback.duration : 0)
            }
            .sheet(isPresented: $showFullPlayer) {
                NowPlayingView()
            }
        }
    }
}

private struct ProgressBarSliver: View {
    let progress: Double
    var body: some View {
        GeometryReader { geo in
            Rectangle()
                .fill(Theme.accent)
                .frame(width: geo.size.width * min(max(progress, 0), 1), height: 2)
        }
        .frame(height: 2)
    }
}
