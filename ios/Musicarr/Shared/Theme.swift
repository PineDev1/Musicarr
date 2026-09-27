import SwiftUI

/// Matches the web player's dark theme + green accent (index.css / the
/// player's default wave_color) so the iOS app reads as the same product,
/// not a reskin.
enum Theme {
    static let background = Color(hex: 0x0f1412)
    static let backgroundElevated = Color(hex: 0x1a221e)
    static let backgroundSoft = Color(hex: 0x24302a)
    static let border = Color(hex: 0x2f3f37)
    static let text = Color(hex: 0xe8efe9)
    static let muted = Color(hex: 0x8fa399)
    static let accent = Color(hex: 0x3dba7a)
    static let accentDim = Color(hex: 0x2a8f5c)
    static let danger = Color(hex: 0xe0605a)
}

extension Color {
    init(hex: UInt32, alpha: Double = 1.0) {
        let r = Double((hex >> 16) & 0xFF) / 255.0
        let g = Double((hex >> 8) & 0xFF) / 255.0
        let b = Double(hex & 0xFF) / 255.0
        self.init(.sRGB, red: r, green: g, blue: b, opacity: alpha)
    }
}
