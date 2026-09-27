import SwiftUI

struct ArtistDetailView: View {
    let artistID: Int
    @State private var detail: ArtistDetail?

    var body: some View {
        ScrollView {
            if let detail {
                VStack(alignment: .leading, spacing: 20) {
                    VStack(spacing: 8) {
                        RemoteArt(path: detail.imageUrl, isCircle: true)
                            .frame(width: 140, height: 140)
                        Text(detail.name).font(.title2.bold()).foregroundStyle(Theme.text)
                    }
                    .frame(maxWidth: .infinity)

                    if !detail.albums.isEmpty {
                        HorizontalShelf(title: "Albums") {
                            ForEach(detail.albums) { album in
                                AlbumCard(album: album)
                            }
                        }
                    }
                }
                .padding()
            } else {
                ProgressView().padding(.top, 80)
            }
        }
        .background(Theme.background.ignoresSafeArea())
        .navigationBarTitleDisplayMode(.inline)
        .task {
            detail = try? await PlayerAPI.artistDetail(id: artistID)
        }
    }
}
