import SwiftUI

struct QueueView: View {
    @EnvironmentObject var playback: PlaybackEngine
    @Environment(\.dismiss) private var dismiss

    private var upcoming: [Track] {
        guard let currentIndex = playback.currentIndex else { return [] }
        return Array(playback.queue.enumerated().filter { $0.offset > currentIndex }.map { $0.element })
    }

    var body: some View {
        NavigationStack {
            List {
                if let current = playback.currentTrack {
                    Section("Now Playing") {
                        HStack(spacing: 12) {
                            RemoteArt(path: current.coverUrl).frame(width: 44, height: 44)
                            VStack(alignment: .leading, spacing: 2) {
                                Text(current.title).foregroundStyle(Theme.accent)
                                Text(current.artistName).font(.caption).foregroundStyle(Theme.muted)
                            }
                        }
                    }
                }

                if !upcoming.isEmpty {
                    Section("Next Up") {
                        ForEach(Array(upcoming.enumerated()), id: \.element.id) { _, track in
                            HStack(spacing: 12) {
                                RemoteArt(path: track.coverUrl).frame(width: 40, height: 40)
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(track.title).foregroundStyle(Theme.text)
                                    Text(track.artistName).font(.caption).foregroundStyle(Theme.muted)
                                }
                            }
                            .contentShape(Rectangle())
                            .onTapGesture {
                                if let idx = playback.queue.firstIndex(of: track) {
                                    playback.play(tracks: playback.queue, startIndex: idx, sourceLabel: playback.sourceLabel)
                                }
                            }
                        }
                        .onDelete { offsets in
                            let indices = offsets.compactMap { i in
                                playback.queue.firstIndex(of: upcoming[i])
                            }
                            for i in indices.sorted(by: >) {
                                playback.removeFromQueue(at: i)
                            }
                        }
                        .onMove { source, destination in
                            guard let currentIndex = playback.currentIndex else { return }
                            let shifted = IndexSet(source.map { $0 + currentIndex + 1 })
                            playback.moveInQueue(from: shifted, to: destination + currentIndex + 1)
                        }
                    }
                }

                if upcoming.isEmpty && playback.currentTrack == nil {
                    Text("Nothing queued").foregroundStyle(Theme.muted)
                }
            }
            .scrollContentBackground(.hidden)
            .background(Theme.background.ignoresSafeArea())
            .navigationTitle("Queue")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) { EditButton() }
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Done") { dismiss() }
                }
            }
        }
    }
}
