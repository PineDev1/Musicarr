import AVKit
import SwiftUI

/// Wraps AVRoutePickerView (the system AirPlay picker) — there is no
/// SwiftUI-native equivalent. Tapping it lets the system show every
/// AirPlay-capable output on the network, same as any other audio app.
struct AirPlayButton: UIViewRepresentable {
    var tintColor: UIColor = UIColor(Theme.text)

    func makeUIView(context: Context) -> AVRoutePickerView {
        let view = AVRoutePickerView()
        view.tintColor = tintColor
        view.activeTintColor = UIColor(Theme.accent)
        view.prioritizesVideoDevices = false
        return view
    }

    func updateUIView(_ uiView: AVRoutePickerView, context: Context) {
        uiView.tintColor = tintColor
    }
}
