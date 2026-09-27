import SwiftUI

struct LyricLine {
    let time: Double
    let text: String
}

/// Parses the same [mm:ss.xx] LRC format the web player's
/// ExpandedNowPlaying.tsx parses (parseLrc), so both clients treat the same
/// lyrics text identically.
func parseLRC(_ raw: String) -> [LyricLine] {
    var lines: [LyricLine] = []
    let pattern = #"^\[(\d+):(\d+(?:\.\d+)?)\](.*)$"#
    guard let regex = try? NSRegularExpression(pattern: pattern) else { return [] }
    for rawLine in raw.split(separator: "\n", omittingEmptySubsequences: false) {
        let line = rawLine.trimmingCharacters(in: .whitespaces)
        let range = NSRange(line.startIndex..<line.endIndex, in: line)
        guard let match = regex.firstMatch(in: line, range: range),
              let minutesRange = Range(match.range(at: 1), in: line),
              let secondsRange = Range(match.range(at: 2), in: line),
              let textRange = Range(match.range(at: 3), in: line),
              let minutes = Double(line[minutesRange]),
              let seconds = Double(line[secondsRange])
        else { continue }
        let text = line[textRange].trimmingCharacters(in: .whitespaces)
        lines.append(LyricLine(time: minutes * 60 + seconds, text: text))
    }
    return lines.sorted { $0.time < $1.time }
}

struct LyricsView: View {
    let trackID: Int
    let currentTime: Double
    @State private var lyrics: Lyrics?
    @State private var loadedForTrack: Int?

    private var syncedLines: [LyricLine] {
        guard let synced = lyrics?.synced, !synced.isEmpty else { return [] }
        return parseLRC(synced)
    }

    private var activeIndex: Int? {
        let lines = syncedLines
        guard !lines.isEmpty else { return nil }
        var result: Int? = nil
        for (i, line) in lines.enumerated() where line.time <= currentTime {
            result = i
        }
        return result
    }

    var body: some View {
        ScrollViewReader { proxy in
            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    if lyrics == nil {
                        ProgressView().frame(maxWidth: .infinity).padding(.top, 30)
                    } else if !syncedLines.isEmpty {
                        ForEach(Array(syncedLines.enumerated()), id: \.offset) { index, line in
                            Text(line.text.isEmpty ? "…" : line.text)
                                .font(index == activeIndex ? .title3.bold() : .title3)
                                .foregroundStyle(index == activeIndex ? Theme.text : Theme.muted)
                                .id(index)
                                .padding(.vertical, 2)
                        }
                    } else if let plain = lyrics?.plain, !plain.isEmpty {
                        Text(plain)
                            .font(.body)
                            .foregroundStyle(Theme.text)
                    } else {
                        Text("No lyrics found").foregroundStyle(Theme.muted).padding(.top, 30)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding()
            }
            .onChange(of: activeIndex) { _, newValue in
                guard let newValue else { return }
                withAnimation(.easeInOut) {
                    proxy.scrollTo(newValue, anchor: .center)
                }
            }
        }
        .task(id: trackID) {
            guard loadedForTrack != trackID else { return }
            lyrics = nil
            lyrics = try? await PlayerAPI.lyrics(trackID: trackID)
            loadedForTrack = trackID
        }
    }
}
