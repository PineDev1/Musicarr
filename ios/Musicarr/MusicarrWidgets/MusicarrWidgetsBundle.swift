import SwiftUI
import WidgetKit

@main
struct MusicarrWidgetsBundle: WidgetBundle {
    var body: some Widget {
        NowPlayingWidget()
        MusicarrLiveActivity()
    }
}
