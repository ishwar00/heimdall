// Heimdall: a notch panel listing Codex + Claude Code threads. Hover to expand, click to jump.
// All data and jumps come from ~/.local/bin/heimdall; app/ is only the UI, and this file starts it.
import AppKit

let app = NSApplication.shared
app.setActivationPolicy(.accessory)
let island = Island()
island.start()
app.run()
