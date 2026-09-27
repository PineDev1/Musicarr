import SwiftUI

struct RootTabView: View {
    @EnvironmentObject var playback: PlaybackEngine

    var body: some View {
        TabView {
            NavigationStack {
                HomeView()
            }
            .withCommonDestinations()
            .tabItem { Label("Home", systemImage: "house.fill") }

            NavigationStack {
                SearchView()
            }
            .withCommonDestinations()
            .tabItem { Label("Search", systemImage: "magnifyingglass") }

            NavigationStack {
                LibraryView()
            }
            .withCommonDestinations()
            .tabItem { Label("Library", systemImage: "square.stack.fill") }
        }
        .tint(Theme.accent)
        .safeAreaInset(edge: .bottom) {
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
