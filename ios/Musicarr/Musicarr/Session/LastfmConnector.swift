import AuthenticationServices
import Foundation
import UIKit

/// Drives Last.fm's own web auth page in a system browser sheet (no app
/// login of ours is exposed to it) with a `musicarr://lastfm-callback`
/// return URL — same shape as the web player's own flow, which appends its
/// own origin as `cb` and reads the token back off the redirect.
@MainActor
final class LastfmConnector: NSObject, ASWebAuthenticationPresentationContextProviding {
    func presentationAnchor(for session: ASWebAuthenticationSession) -> ASPresentationAnchor {
        UIApplication.shared.connectedScenes
            .compactMap { $0 as? UIWindowScene }
            .flatMap { $0.windows }
            .first { $0.isKeyWindow } ?? ASPresentationAnchor()
    }

    func connect() async throws -> LastfmCallbackResult {
        let start = try await PlayerAPI.lastfmStart()
        let callbackScheme = "musicarr"
        guard var components = URLComponents(string: start.authURL) else {
            throw APIError(message: "Last.fm returned an invalid auth URL")
        }
        var items = components.queryItems ?? []
        items.append(URLQueryItem(name: "cb", value: "\(callbackScheme)://lastfm-callback"))
        components.queryItems = items
        guard let url = components.url else {
            throw APIError(message: "Could not build the Last.fm auth URL")
        }

        let callbackURL: URL = try await withCheckedThrowingContinuation { continuation in
            let session = ASWebAuthenticationSession(url: url, callbackURLScheme: callbackScheme) { url, error in
                if let url {
                    continuation.resume(returning: url)
                } else {
                    continuation.resume(throwing: error ?? APIError(message: "Last.fm sign-in was cancelled"))
                }
            }
            session.presentationContextProvider = self
            session.start()
        }

        guard let token = URLComponents(url: callbackURL, resolvingAgainstBaseURL: false)?
            .queryItems?.first(where: { $0.name == "token" })?.value
        else {
            throw APIError(message: "Last.fm did not return an auth token")
        }
        return try await PlayerAPI.lastfmCallback(token: token)
    }
}
