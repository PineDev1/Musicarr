import SwiftUI

struct TrackRow: View {
    let track: Track
    let queue: [Track]
    let sourceLabel: String
    var number: Int?
    var showAlbum: Bool = false

    @EnvironmentObject var playback: PlaybackEngine

    private var isCurrent: Bool { playback.currentTrack?.id == track.id }

    var body: some View {
        Button {
            playback.play(tracks: queue, startIndex: queue.firstIndex(of: track) ?? 0, sourceLabel: sourceLabel)
        } label: {
            HStack(spacing: 12) {
                if let number {
                    Text("\(number)")
                        .font(.subheadline.monospacedDigit())
                        .foregroundStyle(isCurrent ? Theme.accent : Theme.muted)
                        .frame(width: 22, alignment: .trailing)
                } else {
                    RemoteArt(path: track.coverUrl)
                        .frame(width: 44, height: 44)
                }

                VStack(alignment: .leading, spacing: 2) {
                    Text(track.title)
                        .font(.body)
                        .foregroundStyle(isCurrent ? Theme.accent : Theme.text)
                        .lineLimit(1)
                    Text(showAlbum ? "\(track.artistName) — \(track.albumTitle)" : track.artistName)
                        .font(.caption)
                        .foregroundStyle(Theme.muted)
                        .lineLimit(1)
                }

                Spacer()

                if isCurrent && playback.isPlaying {
                    Image(systemName: "speaker.wave.2.fill")
                        .foregroundStyle(Theme.accent)
                        .font(.caption)
                }
            }
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .padding(.vertical, 6)
    }
}
