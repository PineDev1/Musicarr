import SwiftUI

struct PeopleView: View {
    @State private var people: [Person] = []
    @State private var isLoading = true

    var body: some View {
        List {
            if !isLoading && people.isEmpty {
                Text("No other accounts yet.").foregroundStyle(Theme.muted)
            }
            ForEach(people) { person in
                NavigationLink {
                    ProfileView(userID: person.id)
                } label: {
                    HStack(spacing: 12) {
                        RemoteArt(path: person.avatarUrl, isCircle: true).frame(width: 44, height: 44)
                        VStack(alignment: .leading) {
                            Text(person.shownName)
                            Text("@\(person.username)\(person.followsYou ? " · follows you" : "")")
                                .font(.caption).foregroundStyle(Theme.muted)
                        }
                        Spacer()
                        if person.isFollowing {
                            Text("Following").font(.caption).foregroundStyle(Theme.accent)
                        }
                    }
                }
            }
        }
        .scrollContentBackground(.hidden)
        .background(Theme.background.ignoresSafeArea())
        .navigationTitle("People")
        .overlay { if isLoading { ProgressView() } }
        .task { await load() }
        .refreshable { await load() }
    }

    private func load() async {
        people = (try? await PlayerAPI.people()) ?? people
        isLoading = false
    }
}

struct ProfileView: View {
    let userID: Int
    @State private var profile: Profile?
    @State private var error: String?
    @State private var isBusy = false

    var body: some View {
        ScrollView {
            if let profile {
                VStack(alignment: .leading, spacing: 16) {
                    HStack(spacing: 16) {
                        RemoteArt(path: profile.avatarUrl, isCircle: true).frame(width: 84, height: 84)
                        VStack(alignment: .leading) {
                            Text(profile.shownName).font(.title2.bold()).foregroundStyle(Theme.text)
                            Text("@\(profile.username)\(profile.followsYou ? " · follows you" : "")")
                                .font(.caption).foregroundStyle(Theme.muted)
                        }
                    }
                    if !profile.isSelf {
                        Button {
                            Task { await toggleFollow(profile) }
                        } label: {
                            Text(profile.isFollowing ? "Following" : "Follow")
                                .frame(maxWidth: .infinity)
                        }
                        .buttonStyle(.borderedProminent)
                        .tint(profile.isFollowing ? .gray : Theme.accent)
                        .disabled(isBusy)
                    }
                    HStack(spacing: 24) {
                        stat("Followers", profile.followers)
                        stat("Following", profile.following)
                        if profile.activityShared {
                            stat("Favorites", profile.favorites)
                            stat("Plays (30d)", profile.plays30d)
                        }
                    }
                    if !profile.activityShared {
                        Text("This person isn't sharing their listening activity.")
                            .font(.footnote).foregroundStyle(Theme.muted)
                    }
                    if !profile.recent.isEmpty {
                        Text("Recently played").font(.headline).foregroundStyle(Theme.text)
                        ForEach(Array(profile.recent.enumerated()), id: \.offset) { index, track in
                            TrackRow(track: track, queue: profile.recent, sourceLabel: "Recently played", number: index + 1, showAlbum: true)
                        }
                    }
                    if let error { Text(error).font(.footnote).foregroundStyle(.red) }
                }
                .padding()
            } else {
                ProgressView().padding(.top, 60).frame(maxWidth: .infinity)
            }
        }
        .background(Theme.background.ignoresSafeArea())
        .navigationBarTitleDisplayMode(.inline)
        .task { profile = try? await PlayerAPI.profile(id: userID) }
    }

    private func stat(_ label: String, _ value: Int) -> some View {
        VStack(alignment: .leading) {
            Text(label).font(.caption).foregroundStyle(Theme.muted)
            Text("\(value)").font(.title3.bold()).foregroundStyle(Theme.text)
        }
    }

    private func toggleFollow(_ p: Profile) async {
        isBusy = true
        defer { isBusy = false }
        do {
            if p.isFollowing { try await PlayerAPI.unfollow(id: p.id) } else { try await PlayerAPI.follow(id: p.id) }
            profile = try await PlayerAPI.profile(id: userID)
        } catch {
            self.error = error.localizedDescription
        }
    }
}
