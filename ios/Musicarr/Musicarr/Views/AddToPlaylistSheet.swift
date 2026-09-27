import SwiftUI

struct AddToPlaylistSheet: View {
    let track: Track
    @Environment(\.dismiss) private var dismiss
    @State private var playlists: [Playlist] = []
    @State private var isLoading = true
    @State private var newName = ""
    @State private var message: String?

    var body: some View {
        NavigationStack {
            List {
                Section {
                    HStack {
                        TextField("New playlist name", text: $newName)
                        Button("Create") {
                            Task { await createAndAdd() }
                        }
                        .disabled(newName.trimmingCharacters(in: .whitespaces).isEmpty)
                    }
                }
                Section("Add to existing") {
                    if isLoading {
                        ProgressView()
                    } else if playlists.isEmpty {
                        Text("No playlists yet").foregroundStyle(Theme.muted)
                    } else {
                        ForEach(playlists.filter { !$0.builtin }) { playlist in
                            Button {
                                Task { await add(to: playlist) }
                            } label: {
                                Text(playlist.name)
                            }
                        }
                    }
                }
                if let message {
                    Text(message).foregroundStyle(Theme.accent)
                }
            }
            .scrollContentBackground(.hidden)
            .background(Theme.background.ignoresSafeArea())
            .navigationTitle("Add to Playlist")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Done") { dismiss() }
                }
            }
        }
        .task {
            playlists = (try? await PlayerAPI.playlists()) ?? []
            isLoading = false
        }
    }

    private func add(to playlist: Playlist) async {
        guard case .number(let id) = playlist.id else { return }
        do {
            _ = try await PlayerAPI.addToPlaylist(id: id, trackIDs: [track.id])
            message = "Added to \(playlist.name)"
        } catch {
            message = error.localizedDescription
        }
    }

    private func createAndAdd() async {
        let name = newName.trimmingCharacters(in: .whitespaces)
        guard !name.isEmpty else { return }
        do {
            let created = try await PlayerAPI.createPlaylist(name: name)
            guard case .number(let id) = created.id else { return }
            _ = try await PlayerAPI.addToPlaylist(id: id, trackIDs: [track.id])
            message = "Created \(name) and added the song"
            newName = ""
            playlists = (try? await PlayerAPI.playlists()) ?? playlists
        } catch {
            message = error.localizedDescription
        }
    }
}
