import AppKit
import SwiftUI

final class Store: ObservableObject {
    @Published var rows: [Row] = []
    @Published var pages: [Page] = []
    @Published var recent: [Page] = []
    @Published var draft: Page?  // captured, waiting for its name
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
                self.pages = payload.pages ?? []
                self.recent = payload.recent ?? []
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

    // Save where you are: the script reads the app in front, which is still yours (the island never takes it)
    private var capturing = false  // cleared on collapse, so a capture that returns after it is dropped
    func capturePage() {
        capturing = true
        DispatchQueue.global(qos: .userInitiated).async {
            let data = runThreads(["--page-capture"])
            let page = try? JSONDecoder().decode(Page.self, from: data)
            let error = (try? JSONDecoder().decode(JumpResult.self, from: data))?.error
            DispatchQueue.main.async {
                guard self.capturing else { return }
                self.capturing = false
                if let page { self.draft = page } else { self.jumpError = error ?? "couldn't read the app in front" }
            }
        }
    }

    func cancelDraft() {
        capturing = false
        draft = nil
    }

    func saveDraft() {
        guard var page = draft else { return }
        page.id = UUID().uuidString
        page.name = page.name.trimmingCharacters(in: .whitespaces)
        if page.name.isEmpty { page.name = page.app ?? page.bundle }
        draft = nil
        pages.append(page)
        editPages(["op": "add", "page": (try? JSONSerialization.jsonObject(with: JSONEncoder().encode(page))) ?? [:]])
    }

    func removePage(_ page: Page) {
        pages.removeAll { $0.id == page.id }
        recent.insert(page, at: 0)
        editPages(["op": "remove", "id": page.id ?? ""])
    }

    func restorePage(_ page: Page) {
        recent.removeAll { $0.id == page.id }
        pages.append(page)
        editPages(["op": "restore", "id": page.id ?? ""])
    }

    func reorderPages(_ keys: [String]) {
        let rank = Dictionary(uniqueKeysWithValues: keys.enumerated().map { ($1, $0) })
        pages.sort { (rank[$0.key] ?? .max) < (rank[$1.key] ?? .max) }
        editPages(["op": "order", "ids": keys])
    }

    private func editPages(_ edit: [String: Any]) {
        guard let payload = try? JSONSerialization.data(withJSONObject: edit) else { return }
        DispatchQueue.global(qos: .userInitiated).async {
            _ = runThreads(["--page-edit"], input: payload)
            DispatchQueue.main.async { self.refresh() }
        }
    }

    func open(_ page: Page) {
        guard let payload = try? JSONEncoder().encode(page) else { return }
        DispatchQueue.global(qos: .userInitiated).async {
            let data = runThreads(["--page-open"], input: payload)
            let result = try? JSONDecoder().decode(JumpResult.self, from: data)
            DispatchQueue.main.async {
                self.jumpError = result == nil ? "threads script: no readable output (\(data.count) bytes)" : result?.error
            }
        }
    }

    var needsYou: Int { rows.filter { $0.state == "needs you" }.count }
    var working: Int { rows.filter { $0.state == "working" }.count }
}
