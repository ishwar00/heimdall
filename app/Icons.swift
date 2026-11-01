import AppKit
import SwiftUI

// Real app icons, so the source is readable at a glance on the left edge
let codexIcon = NSImage(contentsOfFile: "/Applications/ChatGPT.app/Contents/Resources/icon-codex-dark-color.png")
    ?? NSWorkspace.shared.icon(forFile: "/Applications/ChatGPT.app")
let claudeIcon = NSWorkspace.shared.icon(forFile: "/Applications/Claude.app")

var appIcons: [String: NSImage] = [:]
func pageIcon(_ page: Page, size: CGFloat) -> some View {
    let favicon = page.icon.flatMap { path in
        appIcons[path] ?? NSImage(contentsOfFile: path).map { appIcons[path] = $0; return $0 }
    }
    // app icons carry their own margin; a favicon fills its square, so it's drawn smaller to match
    if let favicon {
        return AnyView(Image(nsImage: favicon).resizable().interpolation(.high).aspectRatio(contentMode: .fit)
            .frame(width: size * 0.78, height: size * 0.78).frame(width: size, height: size))
    }
    let icon = appIcons[page.bundle] ?? {
        let url = NSWorkspace.shared.urlForApplication(withBundleIdentifier: page.bundle)
        let image = url.map { NSWorkspace.shared.icon(forFile: $0.path) } ?? NSImage(systemSymbolName: "macwindow", accessibilityDescription: nil)!
        appIcons[page.bundle] = image
        return image
    }()
    return AnyView(Image(nsImage: icon).resizable().interpolation(.high).frame(width: size, height: size))
}

func appIcon(_ row: Row, size: CGFloat) -> some View {
    Image(nsImage: row.src.hasPrefix("codex") ? codexIcon : claudeIcon)
        .resizable().interpolation(.high).frame(width: size, height: size)
}

// GitHub's pull-request icon (Octicons git-pull-request / git-pull-request-draft), drawn on a 16-unit grid
struct PRIcon: Shape {
    var draft = false
    func path(in rect: CGRect) -> Path {
        let k = rect.width / 16
        func p(_ x: CGFloat, _ y: CGFloat) -> CGPoint { CGPoint(x: rect.minX + x * k, y: rect.minY + y * k) }
        var path = Path()
        for (x, y) in [(3.5, 3.0), (3.5, 13.0), (12.5, 13.0)] {
            path.addEllipse(in: CGRect(x: rect.minX + (x - 1.75) * k, y: rect.minY + (y - 1.75) * k, width: 3.5 * k, height: 3.5 * k))
        }
        path.move(to: p(3.5, 4.75)); path.addLine(to: p(3.5, 11.25))
        if draft {  // a broken line and no arrow: not ready to merge
            for y in [3.5, 7.5] {  // round caps turn these into dots
                path.move(to: p(12.5, y)); path.addLine(to: p(12.5, y + 0.01))
            }
        } else {
            path.move(to: p(12.5, 11.25)); path.addLine(to: p(12.5, 6.0))
            path.addQuadCurve(to: p(10.5, 4.0), control: p(12.5, 4.0))
            path.addLine(to: p(7.5, 4.0))
            path.move(to: p(9.25, 2.25)); path.addLine(to: p(7.5, 4.0)); path.addLine(to: p(9.25, 5.75))
        }
        return path
    }
}
