import SwiftUI

struct PlaylistDetailView: View {
    let playlistID: PlaylistID
    let initialName: String
    @State private var playlist: Playlist?
    @State private var newCollaborator = ""
    @State private var collabError: String?
    @Environment(\.dismiss) private var dismiss
    @EnvironmentObject var playback: PlaybackEngine

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                HStack {
                    VStack(alignment: .leading) {
                        Text(playlist?.name ?? initialName).font(.title2.bold()).foregroundStyle(Theme.text)
                        Text(subtitle).font(.caption).foregroundStyle(Theme.muted)
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

                if let playlist, case .number(let numericID) = playlist.id, !playlist.builtin, !playlist.isSmart {
                    collaboratorsSection(playlist, id: numericID)
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

    private var subtitle: String {
        var text = "\(playlist?.trackCount ?? 0) songs"
        if playlist?.isOwner == false {
            text += " · Shared by \(playlist?.ownerName ?? "someone")"
        } else if !(playlist?.collaborators ?? []).isEmpty {
            text += " · Shared"
        }
        return text
    }

    @ViewBuilder
    private func collaboratorsSection(_ playlist: Playlist, id: Int) -> some View {
        let isOwner = playlist.isOwner != false
        VStack(alignment: .leading, spacing: 8) {
            Text("Collaborators").font(.headline).foregroundStyle(Theme.text)
            Text("Collaborators can add and remove songs. Only the owner can rename or delete.")
                .font(.caption).foregroundStyle(Theme.muted)
            let people = playlist.collaborators ?? []
            if people.isEmpty {
                Text("Just you.").font(.caption).foregroundStyle(Theme.muted)
            }
            ForEach(people) { person in
                HStack {
                    RemoteArt(path: person.avatarUrl, isCircle: true).frame(width: 28, height: 28)
                    Text(person.displayName.isEmpty ? person.username : person.displayName)
                    Spacer()
                    if isOwner {
                        Button(role: .destructive) {
                            Task {
                                try? await PlayerAPI.removeCollaborator(playlistID: id, userID: person.userId)
                                await reload()
                            }
                        } label: { Image(systemName: "xmark.circle") }
                    }
                }
            }
            if isOwner {
                HStack {
                    TextField("Add by username", text: $newCollaborator)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                    Button("Add") {
                        Task { await addCollaborator(id: id) }
                    }
                    .disabled(newCollaborator.trimmingCharacters(in: .whitespaces).isEmpty)
                }
            } else {
                Button("Leave this playlist", role: .destructive) {
                    Task {
                        try? await PlayerAPI.leavePlaylist(id: id)
                        dismiss()
                    }
                }
            }
            if let collabError { Text(collabError).font(.caption).foregroundStyle(.red) }
        }
        .padding(12)
        .background(Theme.background.opacity(0.6), in: RoundedRectangle(cornerRadius: 10))
    }

    private func addCollaborator(id: Int) async {
        collabError = nil
        do {
            _ = try await PlayerAPI.addCollaborator(playlistID: id, username: newCollaborator.trimmingCharacters(in: .whitespaces))
            newCollaborator = ""
            await reload()
        } catch {
            collabError = error.localizedDescription
        }
    }

    private func reload() async {
        playlist = try? await PlayerAPI.playlist(id: playlistID)
    }
}
