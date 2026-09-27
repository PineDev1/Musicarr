import SwiftUI

struct AlbumDetailView: View {
    let albumID: Int
    @State private var album: Album?
    @EnvironmentObject var playback: PlaybackEngine

    var body: some View {
        ScrollView {
            if let album {
                VStack(alignment: .leading, spacing: 16) {
                    VStack(spacing: 10) {
                        RemoteArt(path: album.coverUrl, cornerRadius: 14)
                            .frame(width: 200, height: 200)
                        Text(album.title).font(.title2.bold()).foregroundStyle(Theme.text).multilineTextAlignment(.center)
                        Text(album.artistName).font(.subheadline).foregroundStyle(Theme.muted)
                        if let date = album.releaseDate {
                            Text(date.prefix(4)).font(.caption).foregroundStyle(Theme.muted)
                        }
                        Button {
                            playback.play(tracks: album.tracks, sourceLabel: album.title)
                        } label: {
                            Label("Play", systemImage: "play.fill")
                                .frame(maxWidth: .infinity)
                                .padding(.vertical, 12)
                        }
                        .background(Theme.accent)
                        .foregroundStyle(.black)
                        .clipShape(RoundedRectangle(cornerRadius: 10))
                        .padding(.horizontal, 40)
                        .padding(.top, 6)
                    }
                    .frame(maxWidth: .infinity)

                    VStack(spacing: 0) {
                        ForEach(Array(album.tracks.enumerated()), id: \.element.id) { index, track in
                            TrackRow(track: track, queue: album.tracks, sourceLabel: album.title, number: index + 1)
                        }
                    }
                }
                .padding()
            } else {
                ProgressView().padding(.top, 80)
            }
        }
        .background(Theme.background.ignoresSafeArea())
        .navigationBarTitleDisplayMode(.inline)
        .task {
            album = try? await PlayerAPI.album(id: albumID)
        }
    }
}
