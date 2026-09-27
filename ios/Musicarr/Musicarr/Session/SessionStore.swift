import Foundation

enum SessionState {
    case loading
    case loggedOut
    case loggedIn(AuthStatus)
}

@MainActor
final class SessionStore: ObservableObject {
    @Published var state: SessionState = .loading
    @Published var serverURLText: String = UserDefaults.standard.string(forKey: "musicarr.serverURL") ?? ""
    @Published var loginError: String?

    func refreshStatus() async {
        guard APIClient.shared.baseURL != nil else {
            state = .loggedOut
            return
        }
        do {
            let status = try await PlayerAPI.status()
            state = status.authenticated ? .loggedIn(status) : .loggedOut
        } catch {
            state = .loggedOut
        }
    }

    func saveServerURL() {
        var text = serverURLText.trimmingCharacters(in: .whitespacesAndNewlines)
        if !text.hasPrefix("http://") && !text.hasPrefix("https://") {
            text = "http://" + text
        }
        // Strip a trailing slash so path-joining in APIClient never
        // produces a double slash.
        while text.hasSuffix("/") { text.removeLast() }
        APIClient.shared.baseURL = URL(string: text)
    }

    func login(username: String, password: String) async {
        loginError = nil
        saveServerURL()
        guard APIClient.shared.baseURL != nil else {
            loginError = "Enter your Musicarr server address first."
            return
        }
        do {
            let status = try await PlayerAPI.login(username: username, password: password)
            if status.authenticated {
                state = .loggedIn(status)
            } else {
                loginError = "Incorrect username or password."
            }
        } catch {
            loginError = error.localizedDescription
        }
    }

    func logout() async {
        _ = try? await PlayerAPI.logout()
        state = .loggedOut
    }
}
