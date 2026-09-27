import Foundation

/// Talks to Musicarr's existing Player REST API (backend/app/api/player.py) —
/// no new backend endpoints, this app is just another client of the same
/// `/api/player/*` surface the web player already uses. Auth is the same
/// cookie session the web client relies on (`credentials: 'include'`);
/// `URLSession`'s default configuration already persists cookies to disk via
/// `HTTPCookieStorage.shared`, so login here survives app relaunches for
/// free with no extra code.
final class APIClient {
    static let shared = APIClient()

    private let session: URLSession

    private init() {
        let config = URLSessionConfiguration.default
        config.httpCookieStorage = HTTPCookieStorage.shared
        config.httpShouldSetCookies = true
        config.httpCookieAcceptPolicy = .always
        self.session = URLSession(configuration: config)
    }

    /// The server's base origin, e.g. "http://10.99.99.10:8787" — set once
    /// during login/server setup and persisted in UserDefaults.
    var baseURL: URL? {
        get {
            guard let raw = UserDefaults.standard.string(forKey: "musicarr.serverURL") else { return nil }
            return URL(string: raw)
        }
        set {
            UserDefaults.standard.set(newValue?.absoluteString, forKey: "musicarr.serverURL")
        }
    }

    func streamURL(trackID: Int) -> URL? {
        baseURL?.appendingPathComponent("api/player/stream/\(trackID)")
    }

    func absoluteMediaURL(_ path: String?) -> URL? {
        guard let path, !path.isEmpty else { return nil }
        if path.hasPrefix("http://") || path.hasPrefix("https://") { return URL(string: path) }
        guard let base = baseURL else { return nil }
        return URL(string: path, relativeTo: base)
    }

    @discardableResult
    func request<T: Decodable>(
        _ path: String,
        method: String = "GET",
        query: [String: String] = [:],
        body: Encodable? = nil
    ) async throws -> T {
        guard let base = baseURL else { throw APIError(message: "No server configured") }
        var components = URLComponents(url: base.appendingPathComponent("api/player\(path)"), resolvingAgainstBaseURL: false)
        if !query.isEmpty {
            components?.queryItems = query.map { URLQueryItem(name: $0.key, value: $0.value) }
        }
        guard let url = components?.url else { throw APIError(message: "Invalid request URL") }

        var req = URLRequest(url: url)
        req.httpMethod = method
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        if let body {
            req.httpBody = try JSONEncoder().encode(AnyEncodable(body))
        }

        let (data, response) = try await session.data(for: req)
        guard let http = response as? HTTPURLResponse else {
            throw APIError(message: "No response from server")
        }
        guard (200..<300).contains(http.statusCode) else {
            if let err = try? JSONDecoder().decode(APIErrorBody.self, from: data), let detail = err.detail {
                throw APIError(message: detail)
            }
            throw APIError(message: "Server returned \(http.statusCode)")
        }
        if data.isEmpty {
            // Callers only ever decode Void via EmptyResponse; guard against
            // trying to decode an empty body as anything else.
            if T.self == EmptyResponse.self {
                return EmptyResponse() as! T
            }
        }
        let decoder = JSONDecoder()
        do {
            return try decoder.decode(T.self, from: data)
        } catch {
            throw APIError(message: "Could not read server response: \(error.localizedDescription)")
        }
    }
}

struct EmptyResponse: Decodable {}

/// Type-erasing wrapper so `request(...)` can accept any Encodable body
/// without becoming generic over the body type too.
private struct AnyEncodable: Encodable {
    private let encodeFunc: (Encoder) throws -> Void
    init(_ wrapped: Encodable) {
        self.encodeFunc = wrapped.encode
    }
    func encode(to encoder: Encoder) throws {
        try encodeFunc(encoder)
    }
}
