import SwiftUI

struct LibraryView: View {
    var body: some View {
        List {
            NavigationLink("Artists") { ArtistsListView() }
            NavigationLink("Albums") { AlbumsListView() }
            NavigationLink("Songs") { SongsListView() }
            NavigationLink("Playlists") { PlaylistsListView() }
            NavigationLink("People") { PeopleView() }
            NavigationLink("Stats") { StatsView() }
        }
        .scrollContentBackground(.hidden)
        .background(Theme.background.ignoresSafeArea())
        .navigationTitle("Library")
    }
}

struct ArtistsListView: View {
    @State private var artists: [Artist] = []
    @State private var isLoading = true

    var body: some View {
        List(artists) { artist in
            NavigationLink(value: artist) {
                HStack {
                    RemoteArt(path: artist.imageUrl, isCircle: true).frame(width: 40, height: 40)
                    Text(artist.name)
                }
            }
        }
        .scrollContentBackground(.hidden)
        .background(Theme.background.ignoresSafeArea())
        .navigationTitle("Artists")
        .overlay { if isLoading { ProgressView() } }
        .task {
            artists = (try? await PlayerAPI.artists()) ?? []
            isLoading = false
        }
    }
}

struct AlbumsListView: View {
    @State private var albums: [Album] = []
    @State private var isLoading = true
    private let columns = [GridItem(.adaptive(minimum: 140), spacing: 14)]

    var body: some View {
        ScrollView {
            LazyVGrid(columns: columns, spacing: 18) {
                ForEach(albums) { album in
                    AlbumCard(album: album)
                }
            }
            .padding()
        }
        .background(Theme.background.ignoresSafeArea())
        .navigationTitle("Albums")
        .overlay { if isLoading { ProgressView() } }
        .task {
            albums = (try? await PlayerAPI.libraryAlbums(sort: "name")) ?? []
            isLoading = false
        }
    }
}

struct SongsListView: View {
    @State private var songs: [Track] = []
    @State private var isLoading = true

    var body: some View {
        List(songs) { track in
            TrackRow(track: track, queue: songs, sourceLabel: "Songs", showAlbum: true)
                .listRowBackground(Theme.background)
        }
        .listStyle(.plain)
        .scrollContentBackground(.hidden)
        .background(Theme.background.ignoresSafeArea())
        .navigationTitle("Songs")
        .overlay { if isLoading { ProgressView() } }
        .task {
            let page = try? await PlayerAPI.songs(limit: 200)
            songs = page?.items ?? []
            isLoading = false
        }
    }
}

struct PlaylistsListView: View {
    @State private var playlists: [Playlist] = []
    @State private var isLoading = true
    @State private var showCreate = false
    @State private var newName = ""

    var body: some View {
        List(playlists) { playlist in
            NavigationLink(value: playlist) {
                HStack {
                    Image(systemName: playlist.builtin ? "music.note.list" : "text.badge.star")
                        .foregroundStyle(Theme.accent)
                    VStack(alignment: .leading) {
                        Text(playlist.name)
                        Text("\(playlist.trackCount) songs").font(.caption).foregroundStyle(Theme.muted)
                    }
                }
            }
        }
        .scrollContentBackground(.hidden)
        .background(Theme.background.ignoresSafeArea())
        .navigationTitle("Playlists")
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button {
                    showCreate = true
                } label: {
                    Image(systemName: "plus")
                }
            }
        }
        .alert("New Playlist", isPresented: $showCreate) {
            TextField("Name", text: $newName)
            Button("Cancel", role: .cancel) { newName = "" }
            Button("Create") {
                Task { await create() }
            }
        }
        .overlay { if isLoading { ProgressView() } }
        .task { await load() }
    }

    private func load() async {
        async let builtins = try? PlayerAPI.builtins()
        async let mine = try? PlayerAPI.playlists()
        playlists = (await builtins ?? []) + (await mine ?? [])
        isLoading = false
    }

    private func create() async {
        let name = newName.trimmingCharacters(in: .whitespaces)
        newName = ""
        guard !name.isEmpty else { return }
        _ = try? await PlayerAPI.createPlaylist(name: name)
        await load()
    }
}
