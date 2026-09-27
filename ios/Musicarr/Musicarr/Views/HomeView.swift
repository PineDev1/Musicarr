import SwiftUI

struct HomeView: View {
    @EnvironmentObject var session: SessionStore
    @EnvironmentObject var playback: PlaybackEngine

    @State private var continueListening: ContinueListening?
    @State private var recommended: [Track] = []
    @State private var recentAlbums: [Album] = []
    @State private var artists: [Artist] = []
    @State private var isLoading = true
    @State private var showSettings = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 28) {
                if isLoading {
                    ProgressView().padding(.top, 60).frame(maxWidth: .infinity)
                } else {
                    if let cont = continueListening, let track = cont.track {
                        continueCard(track: track, cont: cont)
                    }
                    if !recommended.isEmpty {
                        HorizontalShelf(title: "Recommended for you", subtitle: "Based on what you've been playing") {
                            ForEach(recommended.prefix(12)) { track in
                                Button {
                                    playback.play(tracks: recommended, startIndex: recommended.firstIndex(of: track) ?? 0, sourceLabel: "Recommended for you")
                                } label: {
                                    VStack(alignment: .leading, spacing: 6) {
                                        RemoteArt(path: track.coverUrl, cornerRadius: 10)
                                            .frame(width: 140, height: 140)
                                        Text(track.title).font(.subheadline.weight(.medium)).foregroundStyle(Theme.text).lineLimit(1)
                                        Text(track.artistName).font(.caption).foregroundStyle(Theme.muted).lineLimit(1)
                                    }
                                    .frame(width: 140)
                                }
                                .buttonStyle(.plain)
                            }
                        }
                    }
                    if !recentAlbums.isEmpty {
                        HorizontalShelf(title: "Recently added") {
                            ForEach(recentAlbums.prefix(12)) { album in
                                AlbumCard(album: album)
                            }
                        }
                    }
                    if !artists.isEmpty {
                        HorizontalShelf(title: "Artists") {
                            ForEach(artists.prefix(12)) { artist in
                                ArtistCard(artist: artist)
                            }
                        }
                    }
                    if continueListening?.track == nil && recommended.isEmpty && recentAlbums.isEmpty && artists.isEmpty {
                        Text("No playable tracks yet. Download albums in Musicarr first.")
                            .foregroundStyle(Theme.muted)
                            .padding(.top, 60)
                            .frame(maxWidth: .infinity)
                    }
                }
            }
            .padding()
        }
        .background(Theme.background.ignoresSafeArea())
        .navigationTitle("Listen Now")
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button { showSettings = true } label: {
                    Image(systemName: "gearshape.fill")
                }
            }
        }
        .sheet(isPresented: $showSettings) { SettingsView() }
        .task { await load() }
        .refreshable { await load() }
    }

    @ViewBuilder
    private func continueCard(track: Track, cont: ContinueListening) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Continue listening").font(.title3.bold()).foregroundStyle(Theme.text)
            Button {
                let queue = cont.album?.tracks.isEmpty == false ? cont.album!.tracks : [track]
                playback.play(tracks: queue, startIndex: queue.firstIndex(of: track) ?? 0, sourceLabel: cont.album?.title ?? cont.sourceLabel ?? "")
                playback.seek(to: cont.position)
            } label: {
                HStack(spacing: 14) {
                    RemoteArt(path: track.coverUrl, cornerRadius: 10)
                        .frame(width: 64, height: 64)
                    VStack(alignment: .leading, spacing: 2) {
                        Text(track.title).font(.headline).foregroundStyle(Theme.text)
                        Text(track.artistName).font(.subheadline).foregroundStyle(Theme.muted)
                    }
                    Spacer()
                    Image(systemName: "play.circle.fill").font(.title).foregroundStyle(Theme.accent)
                }
                .padding(12)
                .background(Theme.backgroundElevated)
                .clipShape(RoundedRectangle(cornerRadius: 12))
            }
            .buttonStyle(.plain)
        }
    }

    private func load() async {
        isLoading = continueListening == nil
        async let cont = try? PlayerAPI.continueListening()
        async let rec = try? PlayerAPI.recommended()
        async let albums = try? PlayerAPI.libraryAlbums()
        async let art = try? PlayerAPI.artists()
        continueListening = await cont
        recommended = await rec ?? []
        recentAlbums = Array((await albums ?? []).prefix(20))
        artists = await art ?? []
        isLoading = false
    }
}
