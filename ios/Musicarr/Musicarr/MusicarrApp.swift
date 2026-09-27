import SwiftUI

@main
struct MusicarrApp: App {
    @StateObject private var session = SessionStore()
    @StateObject private var playback = PlaybackEngine()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(session)
                .environmentObject(playback)
                .preferredColorScheme(.dark)
                .tint(Theme.accent)
        }
    }
}

struct RootView: View {
    @EnvironmentObject var session: SessionStore

    var body: some View {
        Group {
            switch session.state {
            case .loading:
                Color(Theme.background).ignoresSafeArea()
            case .loggedOut:
                LoginView()
            case .loggedIn:
                RootTabView()
            }
        }
        .task { await session.refreshStatus() }
    }
}
