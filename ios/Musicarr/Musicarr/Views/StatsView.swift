import SwiftUI

struct StatsView: View {
    private enum Period: Hashable {
        case days(Int)
        case year(Int)

        var title: String {
            switch self {
            case .days(let d): return "\(d) days"
            case .year(let y): return String(y)
            }
        }
    }

    private let thisYear = Calendar.current.component(.year, from: Date())
    @State private var period: Period = .days(30)
    @State private var stats: ListeningStats?
    @State private var failed = false

    private var choices: [Period] {
        [.days(7), .days(30), .days(90), .year(thisYear), .year(thisYear - 1)]
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                Picker("Period", selection: $period) {
                    ForEach(choices, id: \.self) { Text($0.title).tag($0) }
                }
                .pickerStyle(.segmented)

                if let stats {
                    header(stats)
                    if !stats.topArtists.isEmpty {
                        section("Top artists") {
                            ForEach(Array(stats.topArtists.prefix(10).enumerated()), id: \.element.id) { i, a in
                                row("\(i + 1). \(a.name)", "\(a.plays) plays · \(minutes(a.seconds))")
                            }
                        }
                    }
                    if !stats.topTracks.isEmpty {
                        section("Top tracks") {
                            ForEach(Array(stats.topTracks.prefix(10).enumerated()), id: \.element.id) { i, t in
                                row("\(i + 1). \(t.title)", "\(t.artistName) · \(t.plays) plays")
                            }
                        }
                    }
                    if !stats.topAlbums.isEmpty {
                        section("Top albums") {
                            ForEach(Array(stats.topAlbums.prefix(10).enumerated()), id: \.element.id) { i, a in
                                row("\(i + 1). \(a.title)", "\(a.artistName) · \(a.plays) plays")
                            }
                        }
                    }
                    if !stats.topGenres.isEmpty {
                        section("Top genres") {
                            ForEach(stats.topGenres.prefix(10)) { g in
                                row(g.genre, "\(g.plays) plays · \(minutes(g.seconds))")
                            }
                        }
                    }
                    section("When you listen") { hourBars(stats.playsByHour) }
                } else if failed {
                    Text("Couldn't load stats.").foregroundStyle(Theme.muted)
                } else {
                    ProgressView().frame(maxWidth: .infinity).padding(.top, 40)
                }
            }
            .padding()
        }
        .background(Theme.background.ignoresSafeArea())
        .navigationTitle(titleText)
        .task(id: period) { await load() }
    }

    private var titleText: String {
        if case .year(let y) = period { return "Your \(y) in music" }
        return "Listening stats"
    }

    private func load() async {
        stats = nil
        failed = false
        do {
            switch period {
            case .days(let d): stats = try await PlayerAPI.stats(rangeDays: d)
            case .year(let y): stats = try await PlayerAPI.stats(year: y)
            }
        } catch {
            failed = true
        }
    }

    private func header(_ s: ListeningStats) -> some View {
        let columns = [GridItem(.flexible()), GridItem(.flexible()), GridItem(.flexible())]
        return LazyVGrid(columns: columns, alignment: .leading, spacing: 14) {
            stat("Plays", "\(s.playEvents)")
            stat("Tracks", "\(s.uniqueTracks)")
            stat("Artists", "\(s.uniqueArtists)")
            stat("Time", minutes(s.totalSeconds))
            stat("Active days", "\(s.activeDays)")
            stat("Streak", "\(s.currentStreakDays)d (best \(s.longestStreakDays)d)")
        }
    }

    private func stat(_ label: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label).font(.caption).foregroundStyle(Theme.muted)
            Text(value).font(.headline).foregroundStyle(Theme.text)
        }
    }

    private func section<Content: View>(_ title: String, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title).font(.title3.bold()).foregroundStyle(Theme.text)
            content()
        }
    }

    private func row(_ title: String, _ subtitle: String) -> some View {
        VStack(alignment: .leading, spacing: 1) {
            Text(title).foregroundStyle(Theme.text)
            Text(subtitle).font(.caption).foregroundStyle(Theme.muted)
        }
    }

    private func hourBars(_ hours: [Int]) -> some View {
        let peak = max(1, hours.max() ?? 1)
        return HStack(alignment: .bottom, spacing: 3) {
            ForEach(Array(hours.enumerated()), id: \.offset) { hour, count in
                VStack(spacing: 2) {
                    RoundedRectangle(cornerRadius: 2)
                        .fill(Theme.accent.opacity(count == 0 ? 0.25 : 1))
                        .frame(height: max(2, CGFloat(count) / CGFloat(peak) * 70))
                    Text(hour % 6 == 0 ? "\(hour)" : "").font(.system(size: 9)).foregroundStyle(Theme.muted)
                }
            }
        }
        .frame(height: 90, alignment: .bottom)
    }

    private func minutes(_ seconds: Int) -> String {
        let m = Int((Double(seconds) / 60).rounded())
        if m < 60 { return "\(m) min" }
        return m % 60 == 0 ? "\(m / 60)h" : "\(m / 60)h \(m % 60)m"
    }
}
