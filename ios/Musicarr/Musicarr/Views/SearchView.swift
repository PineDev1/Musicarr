import SwiftUI

struct SearchView: View {
    @State private var query = ""
    @State private var results: SearchResults?
    @State private var task: Task<Void, Never>?

    var body: some View {
        ScrollView {
            if let results {
                VStack(alignment: .leading, spacing: 20) {
                    if !results.songs.isEmpty {
                        VStack(alignment: .leading, spacing: 4) {
                            Text("Songs").font(.headline).foregroundStyle(Theme.text)
                            ForEach(results.songs) { track in
                                TrackRow(track: track, queue: results.songs, sourceLabel: "Search: \(query)")
                            }
                        }
                    }
                    if !results.artists.isEmpty {
                        HorizontalShelf(title: "Artists") {
                            ForEach(results.artists) { artist in
                                ArtistCard(artist: artist)
                            }
                        }
                    }
                    if !results.albums.isEmpty {
                        HorizontalShelf(title: "Albums") {
                            ForEach(results.albums) { album in
                                AlbumCard(album: album)
                            }
                        }
                    }
                    if results.songs.isEmpty && results.albums.isEmpty && results.artists.isEmpty {
                        Text("No results for \"\(query)\"").foregroundStyle(Theme.muted).padding(.top, 40)
                    }
                }
                .padding()
            } else if !query.isEmpty {
                ProgressView().padding(.top, 60)
            } else {
                Text("Search your library").foregroundStyle(Theme.muted).padding(.top, 60)
            }
        }
        .background(Theme.background.ignoresSafeArea())
        .navigationTitle("Search")
        .searchable(text: $query, placement: .navigationBarDrawer(displayMode: .always))
        .onChange(of: query) { _, newValue in
            task?.cancel()
            guard !newValue.trimmingCharacters(in: .whitespaces).isEmpty else {
                results = nil
                return
            }
            task = Task {
                try? await Task.sleep(nanoseconds: 300_000_000)
                guard !Task.isCancelled else { return }
                results = try? await PlayerAPI.search(newValue)
            }
        }
    }
}
