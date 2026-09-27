import ActivityKit
import SwiftUI
import WidgetKit

private func artworkImage() -> Image? {
    guard let url = AppGroup.artworkURL, let data = try? Data(contentsOf: url), let ui = UIImage(data: data) else {
        return nil
    }
    return Image(uiImage: ui)
}

@ViewBuilder
private func artworkView(hasArtwork: Bool, size: CGFloat, corner: CGFloat) -> some View {
    if hasArtwork, let image = artworkImage() {
        image.resizable().aspectRatio(contentMode: .fill)
            .frame(width: size, height: size)
            .clipShape(RoundedRectangle(cornerRadius: corner))
    } else {
        RoundedRectangle(cornerRadius: corner)
            .fill(Theme.backgroundSoft)
            .frame(width: size, height: size)
            .overlay(Image(systemName: "music.note").foregroundStyle(Theme.muted))
    }
}

struct MusicarrLiveActivity: Widget {
    var body: some WidgetConfiguration {
        ActivityConfiguration(for: MusicarrActivityAttributes.self) { context in
            // Lock screen / banner presentation.
            HStack(spacing: 14) {
                artworkView(hasArtwork: context.state.hasArtwork, size: 54, corner: 10)
                VStack(alignment: .leading, spacing: 4) {
                    Text(context.state.title).font(.subheadline.bold()).foregroundStyle(Theme.text).lineLimit(1)
                    Text(context.state.artistName).font(.caption).foregroundStyle(Theme.muted).lineLimit(1)
                    ProgressView(value: context.state.estimatedCurrentTime, total: max(context.state.duration, 1))
                        .tint(Theme.accent)
                }
                Spacer()
                HStack(spacing: 18) {
                    Button(intent: PreviousTrackIntent()) {
                        Image(systemName: "backward.fill")
                    }
                    Button(intent: PlayPauseIntent()) {
                        Image(systemName: context.state.isPlaying ? "pause.fill" : "play.fill")
                    }
                    Button(intent: NextTrackIntent()) {
                        Image(systemName: "forward.fill")
                    }
                }
                .buttonStyle(.plain)
                .foregroundStyle(Theme.text)
                .font(.title3)
            }
            .padding(16)
            .activityBackgroundTint(Theme.background)
            .activitySystemActionForegroundColor(Theme.text)

        } dynamicIsland: { context in
            DynamicIsland {
                DynamicIslandExpandedRegion(.leading) {
                    artworkView(hasArtwork: context.state.hasArtwork, size: 44, corner: 8)
                }
                DynamicIslandExpandedRegion(.trailing) {
                    HStack(spacing: 16) {
                        Button(intent: PreviousTrackIntent()) { Image(systemName: "backward.fill") }
                        Button(intent: PlayPauseIntent()) {
                            Image(systemName: context.state.isPlaying ? "pause.fill" : "play.fill")
                        }
                        Button(intent: NextTrackIntent()) { Image(systemName: "forward.fill") }
                    }
                    .buttonStyle(.plain)
                    .foregroundStyle(Theme.text)
                }
                DynamicIslandExpandedRegion(.bottom) {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(context.state.title).font(.subheadline.bold()).foregroundStyle(Theme.text).lineLimit(1)
                        Text(context.state.artistName).font(.caption).foregroundStyle(Theme.muted).lineLimit(1)
                        ProgressView(value: context.state.estimatedCurrentTime, total: max(context.state.duration, 1))
                            .tint(Theme.accent)
                    }
                }
            } compactLeading: {
                artworkView(hasArtwork: context.state.hasArtwork, size: 20, corner: 4)
            } compactTrailing: {
                Image(systemName: context.state.isPlaying ? "waveform" : "pause.fill")
                    .foregroundStyle(Theme.accent)
            } minimal: {
                Image(systemName: context.state.isPlaying ? "waveform" : "pause.fill")
                    .foregroundStyle(Theme.accent)
            }
            .keylineTint(Theme.accent)
        }
    }
}
