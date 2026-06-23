import AppKit

// Headless health check: validate the SQLite layer without launching the GUI.
if CommandLine.arguments.contains("--selftest") {
    exit(SelfTest.run() ? 0 : 1)
}

// Build step: render the app icon to a `.iconset` directory for `iconutil` (see build_app.sh).
if let index = CommandLine.arguments.firstIndex(of: "--write-iconset"),
    index + 1 < CommandLine.arguments.count
{
    do {
        try BrandIcon.writeIconset(to: CommandLine.arguments[index + 1])
        exit(0)
    } catch {
        NSLog("agent-hooks-ui: failed to write iconset: \(error)")
        exit(1)
    }
}

// Menu-bar accessory app: no Dock icon, no main window. The status item owns the panel.
let delegate = AppDelegate()
let application = NSApplication.shared
application.delegate = delegate
application.setActivationPolicy(.accessory)
application.run()
