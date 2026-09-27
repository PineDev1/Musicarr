import SwiftUI
import UIKit

/// UIActivityViewController wrapper — SwiftUI's `ShareLink` needs its item
/// up front, but a share link has to be created on the server first
/// (POST /shares), so this presents after that async call finishes instead.
struct ActivityShareSheet: UIViewControllerRepresentable {
    let items: [Any]

    func makeUIViewController(context: Context) -> UIActivityViewController {
        UIActivityViewController(activityItems: items, applicationActivities: nil)
    }

    func updateUIViewController(_ uiViewController: UIActivityViewController, context: Context) {}
}

struct TrackActionsModifier: ViewModifier {
    let track: Track
    var hideNavigation: Bool = false

    @EnvironmentObject var playback: PlaybackEngine
    @State private var showAddToPlaylist = false
    @State private var shareURL: URL?
    @State private var isCreatingShare = false

    func body(content: Content) -> some View {
        content
            .contextMenu {
                Button {
                    playback.playNext(track)
                } label: {
                    Label("Play Next", systemImage: "text.line.first.and.arrowtriangle.forward")
                }
                Button {
                    playback.addToEnd(track)
                } label: {
                    Label("Add to Queue", systemImage: "text.badge.plus")
                }
                Button {
                    showAddToPlaylist = true
                } label: {
                    Label("Add to Playlist…", systemImage: "plus.circle")
                }
                Button {
                    Task { await createShare() }
                } label: {
                    Label("Share Song", systemImage: "square.and.arrow.up")
                }
                if !hideNavigation {
                    if track.albumId != 0 {
                        NavigationLink(value: Album(id: track.albumId, title: track.albumTitle, artistId: track.artistId, artistName: track.artistName, coverUrl: track.coverUrl, releaseDate: nil, trackCount: 0, quality: "", tracks: [])) {
                            Label("Go to Album", systemImage: "square.stack")
                        }
                    }
                    if track.artistId != 0 {
                        NavigationLink(value: Artist(id: track.artistId, name: track.artistName, imageUrl: nil, albumCount: 0)) {
                            Label("Go to Artist", systemImage: "person")
                        }
                    }
                }
            }
            .sheet(isPresented: $showAddToPlaylist) {
                AddToPlaylistSheet(track: track)
            }
            .sheet(item: Binding(
                get: { shareURL.map { IdentifiableURL(url: $0) } },
                set: { shareURL = $0?.url }
            )) { wrapped in
                ActivityShareSheet(items: [wrapped.url])
            }
    }

    private func createShare() async {
        guard !isCreatingShare else { return }
        isCreatingShare = true
        defer { isCreatingShare = false }
        if let info = try? await PlayerAPI.createShare(trackID: track.id), let url = URL(string: info.url) {
            shareURL = url
        }
    }
}

private struct IdentifiableURL: Identifiable {
    let url: URL
    var id: String { url.absoluteString }
}

extension View {
    func trackActions(track: Track, hideNavigation: Bool = false) -> some View {
        modifier(TrackActionsModifier(track: track, hideNavigation: hideNavigation))
    }
}
