import SwiftUI

struct TrackRow: View {
    let track: Track
    let queue: [Track]
    let sourceLabel: String
    var number: Int?
    var showAlbum: Bool = false

    @EnvironmentObject var playback: PlaybackEngine
    @EnvironmentObject var favorites: FavoritesStore

    private var isCurrent: Bool { playback.currentTrack?.id == track.id }

    var body: some View {
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
                Text((showAlbum ? "\(track.artistName) — \(track.albumTitle)" : track.artistName) + (track.addedByName.map { " · added by \($0)" } ?? ""))
                    .font(.caption)
                    .foregroundStyle(Theme.muted)
                    .lineLimit(1)
            }
            .contentShape(Rectangle())
            .onTapGesture {
                playback.play(tracks: queue, startIndex: queue.firstIndex(of: track) ?? 0, sourceLabel: sourceLabel)
            }

            Spacer()

            if isCurrent && playback.isPlaying {
                Image(systemName: "speaker.wave.2.fill")
                    .foregroundStyle(Theme.accent)
                    .font(.caption)
            }

            Button {
                favorites.toggle(track)
            } label: {
                Image(systemName: favorites.isFavorite(track.id) ? "heart.fill" : "heart")
                    .foregroundStyle(favorites.isFavorite(track.id) ? Theme.accent : Theme.muted)
                    .font(.footnote)
                    .frame(width: 32, height: 32)
            }
            .buttonStyle(.plain)
        }
        .contentShape(Rectangle())
        .onTapGesture {
            playback.play(tracks: queue, startIndex: queue.firstIndex(of: track) ?? 0, sourceLabel: sourceLabel)
        }
        .trackActions(track: track)
        .padding(.vertical, 6)
    }
}
