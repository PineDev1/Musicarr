import SwiftUI
import WidgetKit

struct NowPlayingEntry: TimelineEntry {
    let date: Date
    let snapshot: NowPlayingSnapshot?
}

struct NowPlayingProvider: TimelineProvider {
    func placeholder(in context: Context) -> NowPlayingEntry {
        NowPlayingEntry(date: Date(), snapshot: nil)
    }

    func getSnapshot(in context: Context, completion: @escaping (NowPlayingEntry) -> Void) {
        completion(NowPlayingEntry(date: Date(), snapshot: NowPlayingSnapshot.load()))
    }

    func getTimeline(in context: Context, completion: @escaping (Timeline<NowPlayingEntry>) -> Void) {
        // The app reloads this widget's timeline itself (WidgetCenter)
        // whenever playback state actually changes, so a single entry with
        // no automatic refresh policy is correct — there's nothing new to
        // show until the app says so.
        let entry = NowPlayingEntry(date: Date(), snapshot: NowPlayingSnapshot.load())
        completion(Timeline(entries: [entry], policy: .never))
    }
}

private func artworkImage() -> Image? {
    guard let url = AppGroup.artworkURL, let data = try? Data(contentsOf: url), let ui = UIImage(data: data) else {
        return nil
    }
    return Image(uiImage: ui)
}

struct NowPlayingWidgetView: View {
    @Environment(\.widgetFamily) var family
    let entry: NowPlayingEntry

    var body: some View {
        if let snapshot = entry.snapshot {
            content(for: snapshot)
        } else {
            emptyState
        }
    }

    private var emptyState: some View {
        VStack(spacing: 8) {
            Image(systemName: "waveform")
                .font(.title)
                .foregroundStyle(Theme.accent)
            Text("Not playing")
                .font(.caption)
                .foregroundStyle(Theme.muted)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .containerBackground(Theme.background, for: .widget)
    }

    @ViewBuilder
    private func content(for snapshot: NowPlayingSnapshot) -> some View {
        switch family {
        case .systemSmall:
            VStack(alignment: .leading, spacing: 8) {
                art(snapshot).frame(width: 52, height: 52)
                Text(snapshot.title).font(.caption.bold()).foregroundStyle(Theme.text).lineLimit(1)
                Text(snapshot.artistName).font(.caption2).foregroundStyle(Theme.muted).lineLimit(1)
                Spacer()
                HStack {
                    Spacer()
                    Button(intent: PlayPauseIntent()) {
                        Image(systemName: snapshot.isPlaying ? "pause.fill" : "play.fill")
                            .foregroundStyle(Theme.text)
                    }
                    .buttonStyle(.plain)
                    Spacer()
                }
            }
            .padding(12)
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .leading)
            .containerBackground(Theme.background, for: .widget)

        default:
            HStack(spacing: 12) {
                art(snapshot).frame(width: 64, height: 64)
                VStack(alignment: .leading, spacing: 4) {
                    Text(snapshot.title).font(.subheadline.bold()).foregroundStyle(Theme.text).lineLimit(1)
                    Text(snapshot.artistName).font(.caption).foregroundStyle(Theme.muted).lineLimit(1)
                    HStack(spacing: 20) {
                        Button(intent: PreviousTrackIntent()) {
                            Image(systemName: "backward.fill").foregroundStyle(Theme.text)
                        }
                        Button(intent: PlayPauseIntent()) {
                            Image(systemName: snapshot.isPlaying ? "pause.fill" : "play.fill")
                                .foregroundStyle(Theme.text)
                        }
                        Button(intent: NextTrackIntent()) {
                            Image(systemName: "forward.fill").foregroundStyle(Theme.text)
                        }
                    }
                    .buttonStyle(.plain)
                    .padding(.top, 4)
                }
                Spacer()
            }
            .padding(14)
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .leading)
            .containerBackground(Theme.background, for: .widget)
        }
    }

    @ViewBuilder
    private func art(_ snapshot: NowPlayingSnapshot) -> some View {
        if snapshot.hasArtwork, let image = artworkImage() {
            image.resizable().aspectRatio(contentMode: .fill).clipShape(RoundedRectangle(cornerRadius: 10))
        } else {
            RoundedRectangle(cornerRadius: 10).fill(Theme.backgroundSoft)
                .overlay(Image(systemName: "music.note").foregroundStyle(Theme.muted))
        }
    }
}

struct NowPlayingWidget: Widget {
    let kind = "NowPlayingWidget"

    var body: some WidgetConfiguration {
        StaticConfiguration(kind: kind, provider: NowPlayingProvider()) { entry in
            NowPlayingWidgetView(entry: entry)
        }
        .configurationDisplayName("Now Playing")
        .description("Shows what's currently playing in Musicarr.")
        .supportedFamilies([.systemSmall, .systemMedium])
    }
}
