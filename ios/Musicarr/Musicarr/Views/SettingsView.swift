import SwiftUI

struct SettingsView: View {
    @EnvironmentObject var session: SessionStore
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            List {
                Section("Server") {
                    if case .loggedIn(let status) = session.state {
                        LabeledContent("Signed in as", value: status.displayName ?? status.username ?? "")
                    }
                    LabeledContent("Address", value: session.serverURLText)
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
    }
}
