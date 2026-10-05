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
    var addedByName: String?

    enum CodingKeys: String, CodingKey {
        case id, title, duration, quality, format, genre
        case addedByName = "added_by_name"
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
    var ownerId: Int?
    var ownerName: String?
    var isOwner: Bool?
    var collaborators: [Collaborator]?

    enum CodingKeys: String, CodingKey {
        case id, name, tracks, kind, collaborators
        case ownerId = "owner_id"
        case ownerName = "owner_name"
        case isOwner = "is_owner"
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


struct Collaborator: Codable, Identifiable, Hashable {
    var userId: Int
    var username: String
    var displayName: String
    var avatarUrl: String?
    var id: Int { userId }

    enum CodingKeys: String, CodingKey {
        case username
        case userId = "user_id"
        case displayName = "display_name"
        case avatarUrl = "avatar_url"
    }
}

struct Person: Codable, Identifiable, Hashable {
    var id: Int
    var username: String
    var displayName: String
    var avatarUrl: String?
    var isFollowing: Bool
    var followsYou: Bool

    var shownName: String { displayName.isEmpty ? username : displayName }

    enum CodingKeys: String, CodingKey {
        case id, username
        case displayName = "display_name"
        case avatarUrl = "avatar_url"
        case isFollowing = "is_following"
        case followsYou = "follows_you"
    }
}

struct Profile: Codable {
    var id: Int
    var username: String
    var displayName: String
    var avatarUrl: String?
    var isFollowing: Bool
    var followsYou: Bool
    var followers: Int
    var following: Int
    var favorites: Int
    var plays30d: Int
    var isSelf: Bool
    var activityShared: Bool
    var recent: [Track]

    var shownName: String { displayName.isEmpty ? username : displayName }

    enum CodingKeys: String, CodingKey {
        case id, username, followers, following, favorites, recent
        case displayName = "display_name"
        case avatarUrl = "avatar_url"
        case isFollowing = "is_following"
        case followsYou = "follows_you"
        case plays30d = "plays_30d"
        case isSelf = "is_self"
        case activityShared = "activity_shared"
    }
}

struct ListeningStats: Codable {
    struct TopTrack: Codable, Identifiable {
        var trackId: Int
        var title: String
        var artistName: String
        var plays: Int
        var id: Int { trackId }
        enum CodingKeys: String, CodingKey {
            case title, plays
            case trackId = "track_id"
            case artistName = "artist_name"
        }
    }
    struct TopArtist: Codable, Identifiable {
        var artistId: Int
        var name: String
        var plays: Int
        var seconds: Int
        var id: Int { artistId }
        enum CodingKeys: String, CodingKey {
            case name, plays, seconds
            case artistId = "artist_id"
        }
    }
    struct TopAlbum: Codable, Identifiable {
        var albumId: Int
        var title: String
        var artistName: String
        var plays: Int
        var id: Int { albumId }
        enum CodingKeys: String, CodingKey {
            case title, plays
            case albumId = "album_id"
            case artistName = "artist_name"
        }
    }
    struct TopGenre: Codable, Identifiable {
        var genre: String
        var plays: Int
        var seconds: Int
        var id: String { genre }
    }

    var playEvents: Int
    var uniqueTracks: Int
    var uniqueArtists: Int
    var totalSeconds: Int
    var topTracks: [TopTrack]
    var topArtists: [TopArtist]
    var topAlbums: [TopAlbum]
    var topGenres: [TopGenre]
    var playsByHour: [Int]
    var activeDays: Int
    var longestStreakDays: Int
    var currentStreakDays: Int

    enum CodingKeys: String, CodingKey {
        case playEvents = "play_events"
        case uniqueTracks = "unique_tracks"
        case uniqueArtists = "unique_artists"
        case totalSeconds = "total_seconds"
        case topTracks = "top_tracks"
        case topArtists = "top_artists"
        case topAlbums = "top_albums"
        case topGenres = "top_genres"
        case playsByHour = "plays_by_hour"
        case activeDays = "active_days"
        case longestStreakDays = "longest_streak_days"
        case currentStreakDays = "current_streak_days"
    }
}
