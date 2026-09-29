import SwiftUI

struct RootTabView: View {
    @EnvironmentObject var playback: PlaybackEngine

    var body: some View {
        TabView {
            NavigationStack {
                HomeView()
                    .withCommonDestinations()
            }
            .modifier(MiniPlayerInsetModifier())
            .tabItem { Label("Home", systemImage: "house.fill") }

            NavigationStack {
                SearchView()
                    .withCommonDestinations()
            }
            .modifier(MiniPlayerInsetModifier())
            .tabItem { Label("Search", systemImage: "magnifyingglass") }

            NavigationStack {
                LibraryView()
                    .withCommonDestinations()
            }
            .modifier(MiniPlayerInsetModifier())
            .tabItem { Label("Library", systemImage: "square.stack.fill") }
        }
        .tint(Theme.accent)
    }
}

/// Anchored inside each tab (not on the TabView) so it sits above the tab bar
/// instead of covering it — on iOS 26 the floating tab bar ignores a
/// TabView-level bottom inset and ends up hidden behind the mini player.
private struct MiniPlayerInsetModifier: ViewModifier {
    @EnvironmentObject var playback: PlaybackEngine

    func body(content: Content) -> some View {
        content.safeAreaInset(edge: .bottom, spacing: 0) {
            if playback.currentTrack != nil {
                MiniPlayerBar()
            }
        }
    }
}

private struct CommonDestinationsModifier: ViewModifier {
    func body(content: Content) -> some View {
        content
            .navigationDestination(for: Album.self) { album in
                AlbumDetailView(albumID: album.id)
            }
            .navigationDestination(for: Artist.self) { artist in
                ArtistDetailView(artistID: artist.id)
            }
            .navigationDestination(for: Playlist.self) { playlist in
                PlaylistDetailView(playlistID: playlist.id, initialName: playlist.name)
            }
    }
}

extension View {
    func withCommonDestinations() -> some View {
        modifier(CommonDestinationsModifier())
    }
}
