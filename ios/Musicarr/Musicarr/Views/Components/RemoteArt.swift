import SwiftUI

/// Album/artist artwork loaded from the server, with a themed placeholder —
/// used everywhere a cover shows up so every list looks consistent even
/// before images load or when there isn't one.
struct RemoteArt: View {
    var path: String?
    var cornerRadius: CGFloat = 8
    var isCircle: Bool = false

    var body: some View {
        Group {
            if let url = APIClient.shared.absoluteMediaURL(path) {
                AsyncImage(url: url) { phase in
                    switch phase {
                    case .success(let image):
                        image.resizable().aspectRatio(contentMode: .fill)
                    default:
                        placeholder
                    }
                }
            } else {
                placeholder
            }
        }
        .clipShape(isCircle ? AnyShape(Circle()) : AnyShape(RoundedRectangle(cornerRadius: cornerRadius)))
    }

    private var placeholder: some View {
        ZStack {
            Theme.backgroundSoft
            Image(systemName: isCircle ? "person.fill" : "music.note")
                .foregroundStyle(Theme.muted)
        }
    }
}
