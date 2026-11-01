// ThreadIsland: a notch panel listing Codex + Claude Code threads. Hover to expand, click to jump.
// All data and jumps come from ~/.local/bin/threads; this file is only the UI.
import AppKit
import SwiftUI

let threadsScript = NSString(string: "~/.local/bin/threads").expandingTildeInPath

struct Row: Codable, Identifiable {
    let key: String, ts: Double, src: String, state: String, title: String, detail: String?
    let action: String, arg: String, cwd: String, age: String, section: String
    let pr: String?  // the thread's open PR, e.g. "#2236 in review"
    var id: String { key }
}

struct Payload: Decodable {
    let rows: [Row]
    let errors: [String]
}

struct JumpResult: Decodable {
    let error: String?
}

func runThreads(_ args: [String], input: Data? = nil) -> Data {
    let p = Process()
    p.executableURL = URL(fileURLWithPath: "/usr/bin/python3")
    p.arguments = [threadsScript] + args
    p.environment = ["PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "HOME": NSHomeDirectory()]
    let out = Pipe(), inp = Pipe()
    p.standardOutput = out
    p.standardError = FileHandle.nullDevice
    p.standardInput = inp
    do { try p.run() } catch { return Data() }
    if let input { inp.fileHandleForWriting.write(input) }
    try? inp.fileHandleForWriting.close()
    let data = out.fileHandleForReading.readDataToEndOfFile()
    p.waitUntilExit()
    return data
}

final class Store: ObservableObject {
    @Published var rows: [Row] = []
    @Published var sourceErrors: [String] = []
    // kept until a jump succeeds, so a refresh doesn't hide why the last click did nothing
    @Published var jumpError: String?
    var errors: [String] { sourceErrors + (jumpError.map { ["Jump: \($0)"] } ?? []) }
    private var loading = false

    func refresh() {
        guard !loading else { return }
        loading = true
        DispatchQueue.global(qos: .userInitiated).async {
            let data = runThreads([])
            let payload = try? JSONDecoder().decode(Payload.self, from: data)
            DispatchQueue.main.async {
                self.loading = false
                guard let payload else {
                    self.sourceErrors = ["threads script: no readable output (\(data.count) bytes)"]
                    return
                }
                self.rows = payload.rows
                self.sourceErrors = payload.errors
            }
        }
    }

    func jump(_ row: Row) {
        guard let payload = try? JSONEncoder().encode(row) else { return }
        DispatchQueue.global(qos: .userInitiated).async {
            let data = runThreads(["--jump"], input: payload)
            let result = try? JSONDecoder().decode(JumpResult.self, from: data)
            DispatchQueue.main.async {
                self.jumpError = result == nil ? "threads script: no readable output (\(data.count) bytes)" : result?.error
            }
        }
    }

    // Priority as you left it after a drag: shown right away, then saved so refreshes keep it
    func saveOrder(_ keys: [String]) {
        let rank = Dictionary(uniqueKeysWithValues: keys.enumerated().map { ($1, $0) })
        let priority = rows.filter { $0.section == "Priority" }.sorted { (rank[$0.key] ?? .max) < (rank[$1.key] ?? .max) }
        rows = priority + rows.filter { $0.section != "Priority" }
        guard let payload = try? JSONSerialization.data(withJSONObject: ["keys": keys]) else { return }
        DispatchQueue.global(qos: .userInitiated).async {
            _ = runThreads(["--edit"], input: payload)
            DispatchQueue.main.async { self.refresh() }
        }
    }

    var needsYou: Int { rows.filter { $0.state == "needs you" }.count }
    var working: Int { rows.filter { $0.state == "working" }.count }
}

extension Color {
    init(hex: UInt32) {
        self.init(red: Double(hex >> 16 & 0xFF) / 255, green: Double(hex >> 8 & 0xFF) / 255, blue: Double(hex & 0xFF) / 255)
    }
}

// A design system: every color and type style a view may use. Color means state, nothing else.
struct Design {
    enum Marker { case lamp, margin, halo }  // where a row shows its state: one signature per design
    let name: String
    let text, detail, needsYou, working, failed: Color
    let title, small, header, age: Font
    let marker: Marker

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
        name: "Instrument", text: Color(hex: 0xECEAE4), detail: Color(hex: 0x8E8C86),
        needsYou: Color(hex: 0xFF6A13), working: Color(hex: 0x86B35E), failed: Color(hex: 0xE5484D),
        title: .system(size: 13, weight: .medium), small: .system(size: 11),
        header: .system(size: 11, weight: .semibold), age: .system(size: 11).monospacedDigit(), marker: .lamp)
    // Ink: threads as correspondence; serif titles, the age in the margin like a letter's date
    static let ink = Design(
        name: "Ink", text: Color(hex: 0xEDE8DF), detail: Color(hex: 0x8A857C),
        needsYou: Color(hex: 0xC8423B), working: Color(hex: 0x6E9E8A), failed: Color(hex: 0xC8423B),
        title: .system(size: 14, design: .serif), small: .system(size: 11),
        header: .system(size: 12, weight: .semibold, design: .serif), age: .system(size: 11, design: .serif).italic(),
        marker: .margin)
    // Tide: sea glass on black water; rounded type, state as a still ring around the app icon
    static let tide = Design(
        name: "Tide", text: Color(hex: 0xE6F0F0), detail: Color(hex: 0x7E9298),
        needsYou: Color(hex: 0xF2C879), working: Color(hex: 0x7FD1C1), failed: Color(hex: 0xF08A7E),
        title: .system(size: 13, weight: .semibold, design: .rounded), small: .system(size: 11, design: .rounded),
        header: .system(size: 11, weight: .semibold, design: .rounded), age: .system(size: 11, design: .rounded).monospacedDigit(),
        marker: .halo)

    static let all = [instrument, ink, tide]
    static func named(_ name: String) -> Design { all.first { $0.name == name } ?? instrument }
}

// Real app icons, so the source is readable at a glance on the left edge
let codexIcon = NSImage(contentsOfFile: "/Applications/ChatGPT.app/Contents/Resources/icon-codex-dark-color.png")
    ?? NSWorkspace.shared.icon(forFile: "/Applications/ChatGPT.app")
let claudeIcon = NSWorkspace.shared.icon(forFile: "/Applications/Claude.app")

func appIcon(_ row: Row, size: CGFloat) -> some View {
    Image(nsImage: row.src.hasPrefix("codex") ? codexIcon : claudeIcon)
        .resizable().interpolation(.high).frame(width: size, height: size)
}

final class IslandState: ObservableObject {
    @Published var expanded = false
}

struct IslandView: View {
    @ObservedObject var store: Store
    @ObservedObject var state: IslandState
    @AppStorage("design") var designName = Design.instrument.name
    let notch: CGSize, collapsed: CGSize, full: CGSize
    let onPick: (Row) -> Void

    var design: Design { Design.named(designName) }
    @State private var dragKey: String?
    @State private var dragOrder: [String]?
    @State private var dragShift: CGFloat = 0
    @State private var dragMoved: CGFloat = 0
    @State private var rowHeight: CGFloat = 0

    var body: some View {
        let size = state.expanded ? full : collapsed
        let radius: CGFloat = state.expanded ? 20 : 12  // rows: 10 radius + 10 inset, so corners nest
        VStack(spacing: 0) {
            HStack(spacing: 0) {
                badgeWings
            }
            .frame(height: notch.height)
            if state.expanded { list.transition(.opacity) }
        }
        .frame(width: size.width, height: size.height, alignment: .top)
        .background(.black)
        .clipShape(UnevenRoundedRectangle(bottomLeadingRadius: radius, bottomTrailingRadius: radius))
        .contextMenu { islandMenu }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
    }

    @ViewBuilder var islandMenu: some View {
        Picker("Design", selection: $designName) {
            ForEach(Design.all, id: \.name) { Text($0.name).tag($0.name) }
        }
        Button("Quit ThreadIsland") { NSApp.terminate(nil) }
    }

    @ViewBuilder var badgeWings: some View {
        HStack(spacing: 6) {
            if !store.errors.isEmpty {
                Image(systemName: "exclamationmark.triangle.fill").font(.system(size: 9)).foregroundStyle(design.failed)
            }
            badge(store.needsYou, design.needsYou)
        }
        .frame(maxWidth: .infinity)
        Spacer().frame(width: notch.width)
        badge(store.working, design.working).frame(maxWidth: .infinity)
    }

    func badge(_ n: Int, _ color: Color) -> some View {
        HStack(spacing: 4) {
            if n > 0 {
                Circle().fill(color).frame(width: 7, height: 7)
                Text("\(n)").font(design.small.weight(.semibold)).monospacedDigit().foregroundStyle(design.text)
            }
        }
    }

    var list: some View {
        ScrollView {
            LazyVStack(spacing: 0) {
                ForEach(store.errors, id: \.self) { error in
                    Label(error, systemImage: "exclamationmark.triangle.fill")
                        .font(design.small).foregroundStyle(design.failed).lineLimit(2)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(.horizontal, 12).padding(.vertical, 8)
                        .background(RoundedRectangle(cornerRadius: 10).fill(design.failed.opacity(0.12)))
                }
                if store.rows.isEmpty && store.errors.isEmpty {
                    Text("All quiet.").font(design.small).foregroundStyle(design.detail).padding(16)
                }
                let rows = shownRows
                ForEach(Array(rows.enumerated()), id: \.element.id) { i, row in
                    if i == 0 || rows[i - 1].section != row.section {
                        Text(row.section).font(design.header)
                            .foregroundStyle(row.section == "Priority" ? design.text : design.detail)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(.horizontal, 12).padding(.top, i == 0 ? 4 : 16).padding(.bottom, 4)
                    }
                    let dragging = dragKey == row.key
                    RowView(row: row, design: design, dragging: dragging,
                            reorder: row.section == "Priority" ? DragGesture(minimumDistance: 1, coordinateSpace: .named("list"))
                                .onChanged { drag(row.key, $0.translation.height) }
                                .onEnded { _ in drop() } : nil)
                        .onTapGesture { onPick(row) }
                        .offset(y: dragging ? dragShift : 0)
                        .zIndex(dragging ? 1 : 0)
                        .onGeometryChange(for: CGFloat.self) { $0.size.height } action: { rowHeight = $0 }
                }
            }
            .padding(.horizontal, 8)
            .padding(.bottom, 8)
            .coordinateSpace(.named("list"))
        }
    }

    // Dragging a Priority row by its grip: the others slide aside as it passes their midpoint
    var shownRows: [Row] {
        guard let dragOrder else { return store.rows }
        let rank = Dictionary(uniqueKeysWithValues: dragOrder.enumerated().map { ($1, $0) })
        let priority = store.rows.filter { $0.section == "Priority" }.sorted { (rank[$0.key] ?? .max) < (rank[$1.key] ?? .max) }
        return priority + store.rows.filter { $0.section != "Priority" }
    }

    func drag(_ key: String, _ dy: CGFloat) {
        if dragKey == nil {
            dragKey = key
            dragOrder = store.rows.filter { $0.section == "Priority" }.map(\.key)
            dragMoved = 0
        }
        guard var order = dragOrder, var at = order.firstIndex(of: key), rowHeight > 0 else { return }
        var shift = dy - dragMoved
        while shift > rowHeight / 2 && at < order.count - 1 {
            order.swapAt(at, at + 1); at += 1; dragMoved += rowHeight; shift -= rowHeight
        }
        while shift < -rowHeight / 2 && at > 0 {
            order.swapAt(at, at - 1); at -= 1; dragMoved -= rowHeight; shift += rowHeight
        }
        if order != dragOrder { withAnimation(.spring(response: 0.25, dampingFraction: 0.85)) { dragOrder = order } }
        dragShift = shift
    }

    func drop() {
        if let dragOrder, dragOrder != store.rows.filter({ $0.section == "Priority" }).map(\.key) {
            store.saveOrder(dragOrder)
        }
        withAnimation(.spring(response: 0.25, dampingFraction: 0.85)) {
            dragKey = nil; dragOrder = nil; dragShift = 0
        }
    }
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
                    .padding(2).background(Circle().fill(.black)).offset(x: 4, y: 4)
            }
        }
    }

    var body: some View {
        let tint = design.color(row.state)
        HStack(spacing: 12) {
            switch design.marker {
            case .lamp:  // indicator lamp: lit in the state color, a dim ring when idle
                Circle().fill(tint ?? .clear).frame(width: 8, height: 8)
                    .overlay(Circle().stroke(tint ?? design.detail.opacity(0.4), lineWidth: 1))
                icon
            case .margin:
                Text(row.age).font(design.age).foregroundStyle(design.detail).frame(width: 32, alignment: .leading)
                icon
            case .halo:
                icon.padding(4)
                    .overlay(Circle().stroke(tint ?? .clear, lineWidth: 2))
            }
            VStack(alignment: .leading, spacing: 4) {
                Text(row.title).font(design.title).foregroundStyle(design.text).lineLimit(1)
                HStack(spacing: 8) {
                    if design.marker != .margin {  // fixed column: "now", "53m" and "1d" all take the same width
                        Text(row.age).font(design.age).foregroundStyle(design.detail).frame(width: 28, alignment: .leading)
                    }
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
        .background(RoundedRectangle(cornerRadius: 10).fill(dragging ? Color.black : .clear))  // covers rows it passes
        .contentShape(Rectangle())
        .onHover { hover = $0 }
    }
}

// Non-key panel: take the first click, and track hover even when another app is active.
final class HoverHostingView<V: View>: NSHostingView<V> {
    var onHover: (Bool) -> Void = { _ in }
    private var area: NSTrackingArea?
    override func acceptsFirstMouse(for event: NSEvent?) -> Bool { true }
    override func updateTrackingAreas() {
        super.updateTrackingAreas()
        // remove only our own area: SwiftUI's per-row hover areas are on this view too
        if let area { removeTrackingArea(area) }
        let a = NSTrackingArea(rect: .zero, options: [.mouseEnteredAndExited, .activeAlways, .inVisibleRect], owner: self)
        addTrackingArea(a)
        area = a
    }
    override func mouseEntered(with event: NSEvent) { onHover(true) }
    override func mouseExited(with event: NSEvent) { onHover(false) }
}

// The list is a ScrollView, whose AppKit views don't take a click on a window that isn't key: the first click
// would only make the panel key. Becoming key on mouse-down lets that click through; non-activating, so the
// app you were in stays active.
final class IslandPanel: NSPanel {
    override var canBecomeKey: Bool { true }
    override func sendEvent(_ event: NSEvent) {
        if event.type == .leftMouseDown && !isKeyWindow { makeKey() }
        super.sendEvent(event)
    }
}

final class Island: NSObject {
    let store = Store()
    let state = IslandState()
    let panel = IslandPanel(contentRect: .zero, styleMask: [.borderless, .nonactivatingPanel], backing: .buffered, defer: false)
    var host: HoverHostingView<IslandView>!
    var expanded = false
    var notch = CGSize(width: 180, height: 32)
    var hoverWork: DispatchWorkItem?
    var ticks = 0
    var collapsed = CGSize.zero
    let wing: CGFloat = 44, expandedSize = CGSize(width: 520, height: 480)
    let pad: CGFloat = 16  // window margin so the spring's overshoot isn't clipped
    let spring = Animation.spring(response: 0.38, dampingFraction: 0.72)

    func start() {
        panel.isOpaque = false
        panel.backgroundColor = .clear
        panel.hasShadow = false
        panel.acceptsMouseMovedEvents = true  // row hover in a non-key panel
        panel.level = .statusBar
        panel.collectionBehavior = [.canJoinAllSpaces, .stationary, .fullScreenAuxiliary, .ignoresCycle]
        host = HoverHostingView(rootView: view())
        host.onHover = { [weak self] inside in self?.hovered(inside) }
        panel.contentView = host
        layout()
        panel.orderFrontRegardless()
        store.refresh()
        // ponytail: polls the script (~0.25 s CPU per run): every 4 s while open, every 32 s collapsed, where it
        // only keeps the two counts current (opening the island refreshes right away)
        Timer.scheduledTimer(withTimeInterval: 4, repeats: true) { [weak self] _ in
            guard let self else { return }
            self.ticks += 1
            if self.expanded || self.ticks % 8 == 0 { self.store.refresh() }
        }
        NotificationCenter.default.addObserver(forName: NSApplication.didChangeScreenParametersNotification,
                                               object: nil, queue: .main) { [weak self] _ in self?.layout() }
    }

    func view() -> IslandView {
        IslandView(store: store, state: state, notch: notch, collapsed: collapsed, full: expandedSize) { [weak self] row in
            self?.store.jump(row)
            self?.setExpanded(false)
        }
    }

    func hovered(_ inside: Bool) {
        hoverWork?.cancel()
        // expand only if the cursor rests on the notch, so passing through to the menu bar doesn't open it
        // and only from the pill: while collapsing, the window keeps its full size for the spring, and moving
        // back into that empty space mustn't reopen it
        let work = DispatchWorkItem { [weak self] in
            guard let self else { return }
            self.setExpanded(inside && (self.expanded || self.onPill()))
        }
        hoverWork = work
        DispatchQueue.main.asyncAfter(deadline: .now() + (inside ? 0.15 : 0.25), execute: work)
    }

    func setExpanded(_ value: Bool) {
        guard value != expanded else { return }
        expanded = value
        // The window jumps to full size and SwiftUI springs the shape inside it;
        // on collapse the window shrinks only after the spring settles.
        if value { store.refresh(); layout() }
        withAnimation(spring) { state.expanded = value }
        if !value {
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.6) { [weak self] in
                guard let self, !self.expanded else { return }
                self.layout()
                // the cursor may already rest on the pill; shrinking under it sends no mouse-entered
                if self.onPill() { self.hovered(true) }
            }
        }
    }

    func onPill() -> Bool {
        let f = panel.screen?.frame ?? NSScreen.main?.frame ?? .zero
        let pill = NSRect(x: f.midX - collapsed.width / 2, y: f.maxY - collapsed.height,
                          width: collapsed.width, height: collapsed.height)
        return pill.insetBy(dx: -2, dy: -2).contains(NSEvent.mouseLocation)  // the top edge itself counts
    }

    func layout() {
        let screen = NSScreen.screens.first { $0.safeAreaInsets.top > 0 } ?? NSScreen.main ?? NSScreen.screens[0]
        if let l = screen.auxiliaryTopLeftArea, let r = screen.auxiliaryTopRightArea {
            notch = CGSize(width: r.minX - l.maxX, height: screen.safeAreaInsets.top)
        } else {
            notch = CGSize(width: 180, height: NSStatusBar.system.thickness)
        }
        collapsed = CGSize(width: notch.width + 2 * wing, height: notch.height)
        let size = expanded ? CGSize(width: expandedSize.width + 2 * pad, height: expandedSize.height + pad) : collapsed
        let f = screen.frame
        let frame = NSRect(x: f.midX - size.width / 2, y: f.maxY - size.height, width: size.width, height: size.height)
        host.rootView = view()
        panel.setFrame(frame, display: true)
    }
}

let app = NSApplication.shared
app.setActivationPolicy(.accessory)
let island = Island()
island.start()
app.run()
