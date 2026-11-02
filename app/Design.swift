import AppKit
import SwiftUI

extension Color {
    init(hex: UInt32) {
        self.init(red: Double(hex >> 16 & 0xFF) / 255, green: Double(hex >> 8 & 0xFF) / 255, blue: Double(hex & 0xFF) / 255)
    }
}

// The design system: every color and type style a view may use. Color means state, nothing else.
struct Design {
    let background, text, detail, needsYou, working, failed: Color
    let title, small, header, age: Font

    func color(_ state: String) -> Color? {
        switch state {
        case "needs you": return needsYou
        case "working": return working
        case "failed": return failed
        default: return nil
        }
    }

    // Instrument: a calm, single-purpose instrument panel; state lamps in one column at the left edge
    static let instrument = Design(
        background: .black, text: Color(hex: 0xECEAE4), detail: Color(hex: 0x8E8C86),
        needsYou: Color(hex: 0xFF6A13), working: Color(hex: 0x86B35E), failed: Color(hex: 0xE5484D),
        title: .system(size: 13, weight: .medium), small: .system(size: 11),
        header: .system(size: 11, weight: .semibold), age: .system(size: 11).monospacedDigit())
    // the same on a light panel: state colors darkened to keep their contrast on white
    static let instrumentLight = Design(
        background: Color(hex: 0xF5F5F7), text: Color(hex: 0x1C1C1E), detail: Color(hex: 0x6B6B70),
        needsYou: Color(hex: 0xC2410C), working: Color(hex: 0x3F7D20), failed: Color(hex: 0xC81E1E),
        title: instrument.title, small: instrument.small, header: instrument.header, age: instrument.age)
}
