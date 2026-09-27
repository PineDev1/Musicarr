import SwiftUI

struct AlbumCard: View {
    let album: Album

    var body: some View {
        NavigationLink(value: album) {
            VStack(alignment: .leading, spacing: 6) {
                RemoteArt(path: album.coverUrl, cornerRadius: 10)
                    .aspectRatio(1, contentMode: .fit)
                Text(album.title)
                    .font(.subheadline.weight(.medium))
                    .foregroundStyle(Theme.text)
                    .lineLimit(1)
                Text(album.artistName)
                    .font(.caption)
                    .foregroundStyle(Theme.muted)
                    .lineLimit(1)
            }
        }
        .buttonStyle(.plain)
        .frame(width: 140)
    }
}

struct ArtistCard: View {
    let artist: Artist

    var body: some View {
        NavigationLink(value: artist) {
            VStack(spacing: 6) {
                RemoteArt(path: artist.imageUrl, isCircle: true)
                    .aspectRatio(1, contentMode: .fit)
                Text(artist.name)
                    .font(.subheadline.weight(.medium))
                    .foregroundStyle(Theme.text)
                    .lineLimit(1)
            }
        }
        .buttonStyle(.plain)
        .frame(width: 120)
    }
}

struct HorizontalShelf<Content: View>: View {
    let title: String
    var subtitle: String? = nil
    @ViewBuilder var content: Content

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(.title3.bold()).foregroundStyle(Theme.text)
                if let subtitle {
                    Text(subtitle).font(.caption).foregroundStyle(Theme.muted)
                }
            }
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(alignment: .top, spacing: 14) {
                    content
                }
                .padding(.horizontal, 1)
            }
        }
    }
}
