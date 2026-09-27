import Foundation

@MainActor
final class FavoritesStore: ObservableObject {
    @Published private(set) var ids: Set<Int> = []
    private var loaded = false

    func load() async {
        guard !loaded else { return }
        loaded = true
        if let result = try? await PlayerAPI.favoriteIDs() {
            ids = Set(result.ids)
        }
    }

    func isFavorite(_ trackID: Int) -> Bool { ids.contains(trackID) }

    func toggle(_ track: Track) {
        let wasFavorite = ids.contains(track.id)
        if wasFavorite {
            ids.remove(track.id)
        } else {
            ids.insert(track.id)
        }
        Task {
            do {
                if wasFavorite {
                    try await PlayerAPI.removeFavorite(trackID: track.id)
                } else {
                    try await PlayerAPI.addFavorite(trackID: track.id)
                }
            } catch {
                // Revert on failure so the UI doesn't lie about server state.
                if wasFavorite { ids.insert(track.id) } else { ids.remove(track.id) }
            }
        }
    }
}
