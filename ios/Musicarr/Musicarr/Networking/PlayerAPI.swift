import Foundation

struct LoginBody: Encodable {
    var username: String
    var password: String
}

/// Thin wrappers over APIClient.request for each endpoint the app uses —
/// mirrors frontend/src/player/playerApi.ts's shape/naming so the two
/// clients of the same backend stay easy to compare.
enum PlayerAPI {
    static func status() async throws -> AuthStatus {
        try await APIClient.shared.request("/status")
    }

    static func login(username: String, password: String) async throws -> AuthStatus {
        try await APIClient.shared.request("/login", method: "POST", body: LoginBody(username: username, password: password))
    }

    static func logout() async throws -> AuthStatus {
        try await APIClient.shared.request("/logout", method: "POST")
    }

    static func artists() async throws -> [Artist] {
        try await APIClient.shared.request("/artists")
    }

    static func artistDetail(id: Int) async throws -> ArtistDetail {
        try await APIClient.shared.request("/artists/\(id)")
    }

    static func album(id: Int) async throws -> Album {
        try await APIClient.shared.request("/albums/\(id)")
    }

    static func libraryAlbums(sort: String = "recent") async throws -> [Album] {
        try await APIClient.shared.request("/library/albums", query: ["sort": sort])
    }

    static func songs(query: String = "", offset: Int = 0, limit: Int = 50) async throws -> SongsPage {
        try await APIClient.shared.request(
            "/library/songs",
            query: ["q": query, "offset": String(offset), "limit": String(limit)]
        )
    }

    static func builtins() async throws -> [Playlist] {
        try await APIClient.shared.request("/library/builtins")
    }

    static func mixes() async throws -> [Playlist] {
        try await APIClient.shared.request("/library/mixes")
    }

    static func playlists() async throws -> [Playlist] {
        try await APIClient.shared.request("/playlists")
    }

    static func playlist(id: PlaylistID) async throws -> Playlist {
        switch id {
        case .number(let value):
            return try await APIClient.shared.request("/playlists/\(value)")
        case .string(let kind):
            return try await APIClient.shared.request("/library/builtins/\(kind)")
        }
    }

    static func continueListening() async throws -> ContinueListening {
        try await APIClient.shared.request("/library/continue")
    }

    static func recommended() async throws -> [Track] {
        try await APIClient.shared.request("/library/recommended")
    }

    static func search(_ q: String) async throws -> SearchResults {
        try await APIClient.shared.request("/search", query: ["q": q, "grouped": "1"])
    }

    static func favoriteIDs() async throws -> FavoriteIDs {
        try await APIClient.shared.request("/favorites/ids")
    }

    static func addFavorite(trackID: Int) async throws {
        let _: Track = try await APIClient.shared.request("/favorites/\(trackID)", method: "POST")
    }

    static func removeFavorite(trackID: Int) async throws {
        let _: EmptyResponse = try await APIClient.shared.request("/favorites/\(trackID)", method: "DELETE")
    }

    struct PlayingUpdateBody: Encodable {
        var track_id: Int?
        var position: Double
        var playing: Bool
        var title: String?
        var artist_name: String?
        var cover_url: String?
    }

    static func reportPlaying(trackID: Int?, position: Double, playing: Bool, title: String? = nil, artistName: String? = nil, coverURL: String? = nil) async throws {
        let body = PlayingUpdateBody(track_id: trackID, position: position, playing: playing, title: title, artist_name: artistName, cover_url: coverURL)
        let _: EmptyResponse = try await APIClient.shared.request("/me/playing", method: "POST", body: body)
    }
}

struct SongsPage: Codable {
    var items: [Track]
    var total: Int
    var offset: Int
    var limit: Int
}

struct FavoriteIDs: Codable {
    var ids: [Int]
}
