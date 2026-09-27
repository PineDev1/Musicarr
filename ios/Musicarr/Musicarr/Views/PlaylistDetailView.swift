import SwiftUI

struct PlaylistDetailView: View {
    let playlistID: PlaylistID
    let initialName: String
    @State private var playlist: Playlist?
    @EnvironmentObject var playback: PlaybackEngine

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                HStack {
                    VStack(alignment: .leading) {
                        Text(playlist?.name ?? initialName).font(.title2.bold()).foregroundStyle(Theme.text)
                        Text("\(playlist?.trackCount ?? 0) songs").font(.caption).foregroundStyle(Theme.muted)
                    }
                    Spacer()
                    if let playlist, !playlist.tracks.isEmpty {
                        Button {
                            playback.play(tracks: playlist.tracks, sourceLabel: playlist.name)
                        } label: {
                            Image(systemName: "play.circle.fill").font(.system(size: 34)).foregroundStyle(Theme.accent)
                        }
                    }
                }

                if let playlist {
                    ForEach(Array(playlist.tracks.enumerated()), id: \.element.id) { index, track in
                        TrackRow(track: track, queue: playlist.tracks, sourceLabel: playlist.name, number: index + 1, showAlbum: true)
                    }
                } else {
                    ProgressView().padding(.top, 60).frame(maxWidth: .infinity)
                }
            }
            .padding()
        }
        .background(Theme.background.ignoresSafeArea())
        .navigationBarTitleDisplayMode(.inline)
        .task {
            playlist = try? await PlayerAPI.playlist(id: playlistID)
        }
    }
}
