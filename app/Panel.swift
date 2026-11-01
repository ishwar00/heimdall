import AppKit
import Combine
import SwiftUI

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
    var onSwipe: (Int) -> Void = { _ in }  // +1: to the next view, -1: back
    private var swipe: CGFloat = 0, swiped = false
    private var axis: Character = "?"  // per gesture: "x" sideways (ours), "y" a scroll (the list's)
    override var canBecomeKey: Bool { true }
    override func sendEvent(_ event: NSEvent) {
        if event.type == .leftMouseDown && !isKeyWindow { makeKey() }
        // a two-finger horizontal swipe anywhere switches views; only the fingers count, not the momentum after
        if event.type == .scrollWheel && event.hasPreciseScrollingDeltas && event.momentumPhase == [] {
            if event.phase == .began { swipe = 0; swiped = false; axis = "?" }
            let dx = event.scrollingDeltaX, dy = event.scrollingDeltaY
            if axis == "?" && abs(dx) + abs(dy) > 3 { axis = abs(dx) > abs(dy) ? "x" : "y" }
            if axis == "x" {
                // follow the fingers whatever the natural-scrolling setting: fingers to the left, next view
                swipe += event.isDirectionInvertedFromDevice ? dx : -dx
                if !swiped && abs(swipe) > 30 {
                    swiped = true
                    onSwipe(swipe < 0 ? 1 : -1)
                }
                return
            }
        }
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
    var draftWatch: AnyCancellable?
    var jumping = false
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
        // saved or cancelled a page name with the cursor elsewhere: close now, as leaving would have
        draftWatch = store.$draft.dropFirst().filter { $0 == nil }.receive(on: RunLoop.main).sink { [weak self] _ in
            guard let self, self.expanded, !self.onIsland() else { return }
            self.setExpanded(false)
        }
        panel.onSwipe = { [weak self] step in
            guard let self, self.expanded else { return }
            withAnimation(.spring(response: 0.3, dampingFraction: 0.9)) { self.state.view = max(0, min(1, self.state.view + step)) }
        }
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
        IslandView(store: store, state: state, notch: notch, collapsed: collapsed, full: expandedSize,
                   onPick: { [weak self] row in
                       self?.jumping = true
                       self?.store.jump(row)
                       self?.setExpanded(false)
                   },
                   onOpen: { [weak self] page in
                       self?.jumping = true
                       self?.store.open(page)
                       self?.setExpanded(false)
                   })
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
        if !value && store.draft != nil && !onIsland() { return }  // naming a page: stay open until saved or cancelled
        expanded = value
        // The window jumps to full size and SwiftUI springs the shape inside it;
        // on collapse the window shrinks only after the spring settles.
        if value { store.refresh(); layout() }
        withAnimation(spring) { state.expanded = value }
        if !value {
            state.view = 0
            store.cancelDraft()
            // a click made the panel key; give the keyboard back to the app you were in, unless a jump is
            // already taking you elsewhere (activating it here would race that jump)
            if panel.isKeyWindow && !jumping { NSWorkspace.shared.frontmostApplication?.activate() }
            jumping = false
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.6) { [weak self] in
                guard let self, !self.expanded else { return }
                self.layout()
                // the cursor may already rest on the pill; shrinking under it sends no mouse-entered
                if self.onPill() { self.hovered(true) }
            }
        }
    }

    func onIsland() -> Bool { panel.frame.contains(NSEvent.mouseLocation) }

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
