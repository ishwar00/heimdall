import AppKit
import SwiftUI

final class IslandState: ObservableObject {
    @Published var expanded = false
    @Published var view = 0  // 0 threads, 1 pages; a horizontal swipe switches
}

struct IslandView: View {
    @ObservedObject var store: Store
    @ObservedObject var state: IslandState
    let notch: CGSize, collapsed: CGSize, full: CGSize
    let onPick: (Row) -> Void
    let onOpen: (Page) -> Void
    @FocusState private var naming: Bool

    @AppStorage("appearance") var appearance = "System"
    @Environment(\.colorScheme) var scheme
    // the panel follows the theme; the strip at the notch stays black (with the dark colors) to merge with it
    var design: Design {
        appearance == "Light" || appearance == "System" && scheme == .light ? .instrumentLight : .instrument
    }
    @State private var dragKey: String?
    @State private var chipDrag: String?
    @State private var chipOrder: [String]?
    @State private var chipFrames: [String: CGRect] = [:]
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
            if state.expanded {
                VStack(spacing: 0) {
                    switcher
                    if state.view == 0 {
                        VStack(spacing: 0) { chips; list }
                            .transition(.move(edge: .leading).combined(with: .opacity))
                    } else {
                        pagesList.transition(.move(edge: .trailing).combined(with: .opacity))
                    }
                }
                .transition(.opacity)
            }
        }
        .frame(width: size.width, height: size.height, alignment: .top)
        .background(VStack(spacing: 0) { Color.black.frame(height: notch.height); design.background })
        .clipShape(UnevenRoundedRectangle(bottomLeadingRadius: radius, bottomTrailingRadius: radius))
        .contextMenu { islandMenu }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
    }

    @ViewBuilder var islandMenu: some View {
        Picker("Appearance", selection: $appearance) {
            ForEach(["System", "Light", "Dark"], id: \.self) { Text($0).tag($0) }
        }
        Button("Quit Heimdall") { NSApp.terminate(nil) }
    }

    var switcher: some View {
        HStack(spacing: 16) {
            ForEach(Array(["Threads", "Pages"].enumerated()), id: \.offset) { i, name in
                Text(name).font(design.header)
                    .foregroundStyle(state.view == i ? design.text : design.detail.opacity(0.7))
                    .contentShape(Rectangle())
                    .onTapGesture { withAnimation(.spring(response: 0.3, dampingFraction: 0.9)) { state.view = i } }
            }
            Spacer()
        }
        .padding(.horizontal, 20).padding(.top, 6).padding(.bottom, 4)
        // the name editor lives in Pages; leaving it (tap or swipe) drops the draft, so nothing hidden keeps
        // the island open
        .onChange(of: state.view) { _, view in if view != 1 { store.cancelDraft() } }
    }

    // saved pages as chips on the threads view: one click from opening the island. They wrap onto more lines
    // rather than scroll, since a sideways swipe switches views; drag one onto another's place to reorder.
    var chips: some View {
        Wrap(spacing: 6, lineSpacing: 6) {
            ForEach(chipPages, id: \.key) { page in
                PageChip(page: page, design: design, dragging: chipDrag == page.key, open: { onOpen(page) })
                    .background(GeometryReader { g in
                        Color.clear.preference(key: ChipFrames.self, value: [page.key: g.frame(in: .named("chips"))])
                    })
                    .gesture(DragGesture(minimumDistance: 4, coordinateSpace: .named("chips"))
                        .onChanged { dragChip(page.key, to: $0.location) }
                        .onEnded { _ in dropChip() })
            }
            Image(systemName: "plus").font(.system(size: 10, weight: .semibold)).foregroundStyle(design.detail)
                .frame(width: 24, height: 24).background(Circle().fill(design.text.opacity(0.06)))
                .contentShape(Circle())
                .onTapGesture { addPage() }
                .help("Save where you are as a page")
        }
        .coordinateSpace(.named("chips"))
        .onPreferenceChange(ChipFrames.self) { chipFrames = $0 }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.horizontal, 16).padding(.bottom, 6)
    }

    var chipPages: [Page] {
        guard let chipOrder else { return store.pages }
        let rank = Dictionary(uniqueKeysWithValues: chipOrder.enumerated().map { ($1, $0) })
        return store.pages.sorted { (rank[$0.key] ?? .max) < (rank[$1.key] ?? .max) }
    }

    func dragChip(_ key: String, to point: CGPoint) {
        if chipDrag == nil {
            chipDrag = key
            chipOrder = store.pages.map(\.key)
        }
        guard var order = chipOrder, let from = order.firstIndex(of: key),
              let over = chipFrames.first(where: { $0.key != key && $0.value.contains(point) })?.key,
              let to = order.firstIndex(of: over) else { return }
        order.move(fromOffsets: IndexSet(integer: from), toOffset: to > from ? to + 1 : to)
        withAnimation(.spring(response: 0.25, dampingFraction: 0.85)) { chipOrder = order }
    }

    func dropChip() {
        if let chipOrder, chipOrder != store.pages.map(\.key) {
            store.reorderPages(chipOrder)
        }
        chipDrag = nil
        chipOrder = nil
    }

    func addPage() {
        store.capturePage()
        withAnimation(.spring(response: 0.3, dampingFraction: 0.9)) { state.view = 1 }
    }

    var pagesList: some View {
        ScrollView {
            VStack(spacing: 0) {
                ForEach(store.pages, id: \.key) { page in
                    PageRow(page: page, design: design, action: "xmark", help: "Remove",
                            act: { store.removePage(page) })
                        .onTapGesture { onOpen(page) }
                        .contextMenu { Button("Remove Page") { store.removePage(page) } }
                }
                if let draft = store.draft {
                    HStack(spacing: 12) {
                        pageIcon(draft, size: 24)
                        VStack(alignment: .leading, spacing: 4) {
                            TextField("Name", text: Binding(get: { store.draft?.name ?? "" }, set: { store.draft?.name = $0 }))
                                .textFieldStyle(.plain).font(design.title).foregroundStyle(design.text)
                                .focused($naming).onSubmit { store.saveDraft() }
                                .onExitCommand { store.cancelDraft() }
                            Text(draft.detail ?? draft.app ?? "").font(design.small).foregroundStyle(design.detail).lineLimit(1)
                        }
                        Text("Save").font(design.small.weight(.semibold)).foregroundStyle(design.text)
                            .onTapGesture { store.saveDraft() }
                        Text("Cancel").font(design.small).foregroundStyle(design.detail)
                            .onTapGesture { store.cancelDraft() }
                    }
                    .padding(.horizontal, 12).padding(.vertical, 8)
                    .background(RoundedRectangle(cornerRadius: 10).fill(design.text.opacity(0.08)))
                    .onAppear { naming = true }
                } else {
                    HStack(spacing: 12) {
                        Image(systemName: "plus").font(.system(size: 12, weight: .semibold)).frame(width: 24, height: 24)
                        Text("Save where you are").font(design.title)
                        Spacer()
                    }
                    .foregroundStyle(design.detail)
                    .padding(.horizontal, 12).padding(.vertical, 8)
                    .contentShape(Rectangle())
                    .onTapGesture { addPage() }
                }
                if !store.recent.isEmpty {
                    Text("Recently removed").font(design.header).foregroundStyle(design.detail)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(.horizontal, 12).padding(.top, 16).padding(.bottom, 4)
                    ForEach(store.recent, id: \.key) { page in
                        PageRow(page: page, design: design, action: "pin", help: "Pin back",
                                act: { store.restorePage(page) }, dim: true)
                            .onTapGesture { onOpen(page) }
                            .contextMenu { Button("Pin Back") { store.restorePage(page) } }
                    }
                }
                if store.pages.isEmpty && store.draft == nil {
                    Text("Go to a tab or app you keep coming back to, open the island, and save it here.")
                        .font(design.small).foregroundStyle(design.detail).padding(.horizontal, 12).padding(.top, 8)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
            }
            .padding(.horizontal, 8).padding(.bottom, 8)
        }
    }

    @ViewBuilder var badgeWings: some View {
        HStack(spacing: 6) {
            if !store.errors.isEmpty {
                Image(systemName: "exclamationmark.triangle.fill").font(.system(size: 9)).foregroundStyle(Design.instrument.failed)
            }
            badge(store.needsYou, Design.instrument.needsYou)
        }
        .frame(maxWidth: .infinity)
        Spacer().frame(width: notch.width)
        badge(store.working, Design.instrument.working).frame(maxWidth: .infinity)
    }

    func badge(_ n: Int, _ color: Color) -> some View {
        HStack(spacing: 4) {
            if n > 0 {
                Circle().fill(color).frame(width: 7, height: 7)
                Text("\(n)").font(design.small.weight(.semibold)).monospacedDigit().foregroundStyle(Design.instrument.text)
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
