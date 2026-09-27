import Foundation

struct AuthStatus: Codable {
    var enabled: Bool
    var authenticated: Bool
    var username: String?
    var userId: Int?
    var displayName: String?
    var avatarUrl: String?

    enum CodingKeys: String, CodingKey {
        case enabled, authenticated, username
        case userId = "user_id"
        case displayName = "display_name"
        case avatarUrl = "avatar_url"
    }
}

struct Track: Codable, Identifiable, Equatable, Hashable {
    var id: Int
    var title: String
    var trackNo: Int
    var discNo: Int
    var duration: Int
    var albumId: Int
    var albumTitle: String
    var artistId: Int
    var artistName: String
    var coverUrl: String?
    var quality: String
    var format: String
    var genre: String?

    enum CodingKeys: String, CodingKey {
        case id, title, duration, quality, format, genre
        case trackNo = "track_no"
        case discNo = "disc_no"
        case albumId = "album_id"
        case albumTitle = "album_title"
        case artistId = "artist_id"
        case artistName = "artist_name"
        case coverUrl = "cover_url"
    }

    static func == (lhs: Track, rhs: Track) -> Bool { lhs.id == rhs.id }
    func hash(into hasher: inout Hasher) { hasher.combine(id) }
}

struct Album: Codable, Identifiable, Hashable {
    var id: Int
    var title: String
    var artistId: Int
    var artistName: String
    var coverUrl: String?
    var releaseDate: String?
    var trackCount: Int
    var quality: String
    var tracks: [Track]

    enum CodingKeys: String, CodingKey {
        case id, title, quality, tracks
        case artistId = "artist_id"
        case artistName = "artist_name"
        case coverUrl = "cover_url"
        case releaseDate = "release_date"
        case trackCount = "track_count"
    }

    static func == (lhs: Album, rhs: Album) -> Bool { lhs.id == rhs.id }
    func hash(into hasher: inout Hasher) { hasher.combine(id) }
}

struct Artist: Codable, Identifiable, Hashable {
    var id: Int
    var name: String
    var imageUrl: String?
    var albumCount: Int

    enum CodingKeys: String, CodingKey {
        case id, name
        case imageUrl = "image_url"
        case albumCount = "album_count"
    }
}

struct ArtistDetail: Codable, Identifiable {
    var id: Int
    var name: String
    var imageUrl: String?
    var albums: [Album]

    enum CodingKeys: String, CodingKey {
        case id, name, albums
        case imageUrl = "image_url"
    }
}

struct Playlist: Codable, Identifiable, Hashable {
    var id: PlaylistID
    var name: String
    var trackCount: Int
    var tracks: [Track]
    var isSmart: Bool
    var builtin: Bool
    var kind: String?

    enum CodingKeys: String, CodingKey {
        case id, name, tracks, kind
        case trackCount = "track_count"
        case isSmart = "is_smart"
        case builtin
    }

    static func == (lhs: Playlist, rhs: Playlist) -> Bool { lhs.id == rhs.id }
    func hash(into hasher: inout Hasher) { hasher.combine(id) }
}

/// Playlist ids are an int for user playlists, a string kind for builtins
/// ("liked", "recently-added", ...) — mirrors the web client's `number |
/// string` union.
enum PlaylistID: Codable, Hashable {
    case number(Int)
    case string(String)

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if let intValue = try? container.decode(Int.self) {
            self = .number(intValue)
        } else {
            self = .string(try container.decode(String.self))
        }
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        switch self {
        case .number(let value): try container.encode(value)
        case .string(let value): try container.encode(value)
        }
    }

    var pathComponent: String {
        switch self {
        case .number(let value): return String(value)
        case .string(let value): return value
        }
    }
}

struct SearchResults: Codable {
    var top: Track?
    var songs: [Track]
    var albums: [Album]
    var artists: [Artist]
}

struct ContinueListening: Codable {
    var album: Album?
    var track: Track?
    var position: Double
    var sourceLabel: String?

    enum CodingKeys: String, CodingKey {
        case album, track, position
        case sourceLabel = "source_label"
    }
}

struct Lyrics: Codable {
    var plain: String?
    var synced: String?
}

struct ShareLinkInfo: Codable {
    var token: String
    var url: String
    var trackTitle: String
    var artistName: String
    var coverUrl: String?

    enum CodingKeys: String, CodingKey {
        case token, url
        case trackTitle = "track_title"
        case artistName = "artist_name"
        case coverUrl = "cover_url"
    }
}

struct LastfmStatus: Codable {
    var connected: Bool
    var username: String?
}

struct LastfmAuthURL: Codable {
    var authURL: String
    enum CodingKeys: String, CodingKey { case authURL = "auth_url" }
}

struct LastfmCallbackResult: Codable {
    var ok: Bool
    var username: String?
}

struct APIErrorBody: Codable {
    var detail: String?
}

struct APIError: Error, LocalizedError {
    let message: String
    var errorDescription: String? { message }
}
