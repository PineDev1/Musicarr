import SwiftUI

struct SettingsView: View {
    @EnvironmentObject var session: SessionStore
    @Environment(\.dismiss) private var dismiss
    @State private var lastfm: LastfmStatus?
    @State private var isConnectingLastfm = false
    @State private var lastfmError: String?
    private let connector = LastfmConnector()

    var body: some View {
        NavigationStack {
            List {
                Section("Server") {
                    if case .loggedIn(let status) = session.state {
                        HStack {
                            RemoteArt(path: status.avatarUrl, isCircle: true)
                                .frame(width: 44, height: 44)
                            VStack(alignment: .leading) {
                                Text(status.displayName ?? status.username ?? "")
                                    .font(.body)
                                Text(session.serverURLText)
                                    .font(.caption)
                                    .foregroundStyle(Theme.muted)
                            }
                        }
                    }
                }

                Section("Last.fm") {
                    if let lastfm, lastfm.connected {
                        LabeledContent("Connected as", value: lastfm.username ?? "")
                        Button("Disconnect", role: .destructive) {
                            Task {
                                try? await PlayerAPI.lastfmDisconnect()
                                self.lastfm = try? await PlayerAPI.lastfmStatus()
                            }
                        }
                    } else {
                        Button {
                            Task { await connectLastfm() }
                        } label: {
                            if isConnectingLastfm {
                                ProgressView()
                            } else {
                                Text("Connect Last.fm")
                            }
                        }
                        .disabled(isConnectingLastfm)
                        if let lastfmError {
                            Text(lastfmError).font(.caption).foregroundStyle(Theme.danger)
                        }
                    }
                }

                Section {
                    Button("Sign out", role: .destructive) {
                        Task {
                            await session.logout()
                            dismiss()
                        }
                    }
                }
            }
            .navigationTitle("Settings")
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Done") { dismiss() }
                }
            }
        }
        .task {
            lastfm = try? await PlayerAPI.lastfmStatus()
        }
    }

    private func connectLastfm() async {
        isConnectingLastfm = true
        lastfmError = nil
        defer { isConnectingLastfm = false }
        do {
            let result = try await connector.connect()
            lastfm = LastfmStatus(connected: result.ok, username: result.username)
        } catch {
            lastfmError = error.localizedDescription
        }
    }
}
