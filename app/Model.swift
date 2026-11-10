import AppKit
import SwiftUI

let threadsScript = NSString(string: "~/.local/bin/heimdall").expandingTildeInPath

struct Row: Codable, Identifiable {
    let key: String, ts: Double, src: String, state: String, title: String, detail: String?
    let action: String, arg: String, cwd: String, age: String, section: String
    let pr: String?  // the thread's open PR, e.g. "#2236 in review"
    var id: String { key }
}

// A place you saved: an Arc tab (tab, url, space) or an app
struct Page: Codable, Equatable {
    var id: String?
    let bundle: String
    let app: String?
    var name: String
    let tab: String?, url: String?, space: String?, detail: String?
    var icon: String? = nil  // the site's favicon, fetched when saved
    var key: String { id ?? "draft" }
}

struct Payload: Decodable {
    let rows: [Row]
    let errors: [String]
    let pages: [Page]?
    let recent: [Page]?  // removed pages, newest first, to pin back
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
