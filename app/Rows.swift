import AppKit
import SwiftUI

// a saved page; on hover, one button at the right edge: remove it, or pin a removed one back
struct PageRow: View {
    let page: Page
    let design: Design
    let action: String, help: String
    let act: () -> Void
    var dim = false
    @State private var hover = false

    var body: some View {
        HStack(spacing: 12) {
            pageIcon(page, size: 24).opacity(dim ? 0.6 : 1)
            VStack(alignment: .leading, spacing: 4) {
                Text(page.name).font(design.title).foregroundStyle(dim ? design.detail : design.text).lineLimit(1)
                Text(page.detail ?? page.app ?? "").font(design.small).foregroundStyle(design.detail).lineLimit(1)
            }
            Spacer(minLength: 0)
            Image(systemName: action).font(.system(size: 11, weight: .semibold)).foregroundStyle(design.detail)
                .frame(width: 26, height: 26).background(Circle().fill(design.text.opacity(0.08)))
                .contentShape(Circle())
                .opacity(hover ? 1 : 0)
                .onTapGesture { act() }
                .help(help)
        }
        .padding(.horizontal, 12).padding(.vertical, 8)
        .background(RoundedRectangle(cornerRadius: 10).fill(design.text.opacity(hover ? 0.08 : 0)))
        .contentShape(Rectangle())
        .onHover { hover = $0 }
    }
}

struct PageChip: View {
    let page: Page
    let design: Design
    let dragging: Bool
    let open: () -> Void
    @State private var hover = false

    var body: some View {
        HStack(spacing: 5) {
            pageIcon(page, size: 14)
            Text(page.name).font(design.small.weight(.medium)).foregroundStyle(design.text).lineLimit(1)
                .frame(maxWidth: 110, alignment: .leading).fixedSize()
        }
        .padding(.horizontal, 8).padding(.vertical, 5)
        .background(Capsule().fill(design.text.opacity(dragging ? 0.2 : hover ? 0.14 : 0.08)))
        .contentShape(Capsule())
        .onTapGesture { open() }
        .onHover { hover = $0 }
    }
}

struct RowView: View {
    let row: Row
    let design: Design
    var dragging = false
    var reorder: _EndedGesture<_ChangedGesture<DragGesture>>?  // Priority rows: drag the grip to move
    @State private var hover = false

    var inTerminal: Bool { row.src.hasSuffix("-cli") || row.src == "claude-bg" }
    var stateLabel: String? {
        switch row.state {
        case "needs you": return "Needs you"
        case "working": return "Working"
        case "failed": return "Failed"
        default: return nil
        }
    }

    // The terminal marker sits on the icon, not in the text line, so every row's text lines up in columns
    var icon: some View {
        appIcon(row, size: 24).overlay(alignment: .bottomTrailing) {
            if inTerminal {
                Image(systemName: "terminal.fill").font(.system(size: 7, weight: .bold)).foregroundStyle(design.text)
                    .padding(2).background(Circle().fill(design.background)).offset(x: 4, y: 4)
            }
        }
    }

    var body: some View {
        let tint = design.color(row.state)
        HStack(spacing: 12) {
            // indicator lamp: lit in the state color, a dim ring when idle
            Circle().fill(tint ?? .clear).frame(width: 8, height: 8)
                .overlay(Circle().stroke(tint ?? design.detail.opacity(0.4), lineWidth: 1))
            icon
            VStack(alignment: .leading, spacing: 4) {
                Text(row.title).font(design.title).foregroundStyle(design.text).lineLimit(1)
                HStack(spacing: 8) {
                    // fixed column: "now", "53m" and "1d" all take the same width
                    Text(row.age).font(design.age).foregroundStyle(design.detail).frame(width: 28, alignment: .leading)
                    if let stateLabel, let tint {
                        Text(stateLabel).font(design.small.weight(.medium)).foregroundStyle(tint)
                    }
                    if let pr = row.pr {
                        let draft = pr.contains("draft")
                        HStack(spacing: 4) {
                            PRIcon(draft: draft)
                                .stroke(style: StrokeStyle(lineWidth: 1.4, lineCap: .round, lineJoin: .round))
                                .foregroundStyle(draft ? Color(hex: 0x8B949E) : Color(hex: 0x3FB950))  // GitHub's open / draft
                                .frame(width: 11, height: 11)
                            Text(pr).font(design.small.weight(.medium)).lineLimit(1).fixedSize()
                                .foregroundStyle(pr.contains("checks failing") ? design.failed : design.text.opacity(0.85))
                        }
                    }
                    if let detail = row.detail, !detail.isEmpty {
                        Text(detail).font(design.small).foregroundStyle(design.detail.opacity(0.8)).lineLimit(1)
                    }
                }
            }
            Spacer(minLength: 0)
            if let reorder {  // six-dot grip, shown on hover only, so the list stays still
                Grid(horizontalSpacing: 2, verticalSpacing: 2) {
                    ForEach(0..<3, id: \.self) { _ in
                        GridRow { Circle().frame(width: 2, height: 2); Circle().frame(width: 2, height: 2) }
                    }
                }
                .foregroundStyle(design.detail)
                .frame(width: 20, height: 32).contentShape(Rectangle())
                .opacity(hover || dragging ? 1 : 0)
                .gesture(reorder)
                .onTapGesture {}  // a click on the grip isn't a click on the thread
            }
        }
        .padding(.horizontal, 12).padding(.vertical, 8)
        .background(RoundedRectangle(cornerRadius: 10).fill(design.text.opacity(dragging ? 0.14 : hover ? 0.08 : 0)))
        .background(RoundedRectangle(cornerRadius: 10).fill(dragging ? design.background : .clear))  // covers rows it passes
        .contentShape(Rectangle())
        .onHover { hover = $0 }
    }
}

struct ChipFrames: PreferenceKey {
    static var defaultValue: [String: CGRect] = [:]
    static func reduce(value: inout [String: CGRect], nextValue: () -> [String: CGRect]) {
        value.merge(nextValue()) { $1 }
    }
}

// Lays its views out left to right, starting a new line when the next one doesn't fit
struct Wrap: Layout {
    var spacing: CGFloat, lineSpacing: CGFloat

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let width = proposal.width ?? .infinity
        let rows = lines(subviews, width)
        let height = rows.map { $0.height }.reduce(0, +) + lineSpacing * CGFloat(max(rows.count - 1, 0))
        return CGSize(width: proposal.width ?? rows.map { $0.width }.max() ?? 0, height: height)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        var y = bounds.minY
        for line in lines(subviews, bounds.width) {
            var x = bounds.minX
            for i in line.items {
                let size = subviews[i].sizeThatFits(.unspecified)
                subviews[i].place(at: CGPoint(x: x, y: y + (line.height - size.height) / 2), proposal: .unspecified)
                x += size.width + spacing
            }
            y += line.height + lineSpacing
        }
    }

    private func lines(_ subviews: Subviews, _ width: CGFloat) -> [(items: [Int], width: CGFloat, height: CGFloat)] {
        var out: [(items: [Int], width: CGFloat, height: CGFloat)] = []
        for (i, view) in subviews.enumerated() {
            let size = view.sizeThatFits(.unspecified)
            if let last = out.last, last.width + spacing + size.width <= width {
                out[out.count - 1] = (last.items + [i], last.width + spacing + size.width, max(last.height, size.height))
            } else {
                out.append(([i], size.width, size.height))
            }
        }
        return out
    }
}
