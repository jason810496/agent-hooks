import Foundation

/// The terminal host of a session, resolved by walking the agent process's ancestry. Only kinds
/// we can do something useful with are represented; an unknown host resolves to `nil` so the row
/// shows no click affordance.
enum TerminalKind {
    case terminalApp  // macOS Terminal.app — exact tab focus by tty
    case iterm        // iTerm2 — exact session focus by tty
    case vscode       // VS Code integrated terminal — activate app + focus the repo window
}

/// What to bring to the front for one session.
struct TerminalTarget {
    let kind: TerminalKind
    let tty: String  // "/dev/ttysNNN" or "" when it could not be determined
    let cwd: String
}

/// Resolve and activate the terminal hosting a Claude Code / Codex session.
///
/// The recorded `session_pid` is the agent process (`os.getppid()` of the hook). Walking up its
/// process ancestry finds the controlling terminal app; the tty (read from the agent process)
/// lets Terminal.app / iTerm2 select the exact tab. VS Code's integrated terminal exposes no
/// tab-selection API, so it is activated at the window level via `open`.
enum TerminalFocus {
    /// Maximum ancestry depth to walk before giving up (agent -> shell -> ... -> terminal app).
    private static let maxAncestry = 16

    /// Resolve the terminal target for a session's agent pid, or `nil` when the host terminal is
    /// not one we can focus (or the process is gone).
    static func resolve(sessionPid: Int32, cwd: String) -> TerminalTarget? {
        guard sessionPid > 0 else { return nil }
        let tty = ttyForPid(sessionPid)
        var pid = sessionPid
        for _ in 0..<maxAncestry {
            guard let (parent, comm) = parentAndComm(of: pid) else { return nil }
            if let kind = kind(forExecutable: comm) {
                return TerminalTarget(kind: kind, tty: tty, cwd: cwd)
            }
            if parent <= 1 { return nil }
            pid = parent
        }
        return nil
    }

    /// Bring the resolved terminal to the front, selecting the exact tab when possible.
    static func focus(_ target: TerminalTarget) {
        switch target.kind {
        case .terminalApp:
            runAppleScript(terminalAppScript(tty: target.tty))
        case .iterm:
            runAppleScript(itermScript(tty: target.tty))
        case .vscode:
            focusVSCode(cwd: target.cwd)
        }
    }

    // MARK: - Ancestry / tty probing

    private static func kind(forExecutable comm: String) -> TerminalKind? {
        if comm.contains("Visual Studio Code.app") || comm.contains("Code - Insiders.app")
            || comm.contains("Code Helper") {
            return .vscode
        }
        if comm.contains("iTerm.app") || comm.contains("iTerm2") { return .iterm }
        if comm.contains("/Terminal.app/") { return .terminalApp }
        return nil
    }

    private static func ttyForPid(_ pid: Int32) -> String {
        let raw = runProcess("/bin/ps", ["-o", "tty=", "-p", "\(pid)"])?
            .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        if raw.isEmpty || raw == "??" || raw == "?" { return "" }
        return raw.hasPrefix("/dev/") ? raw : "/dev/\(raw)"
    }

    /// Return one process's parent pid and executable path via `ps`.
    private static func parentAndComm(of pid: Int32) -> (Int32, String)? {
        guard
            let line = runProcess("/bin/ps", ["-o", "ppid=,comm=", "-p", "\(pid)"])?
                .trimmingCharacters(in: .whitespacesAndNewlines),
            !line.isEmpty
        else { return nil }
        let parts = line.split(separator: " ", maxSplits: 1, omittingEmptySubsequences: true)
        guard let parent = Int32(parts.first ?? "") else { return nil }
        let comm = parts.count > 1 ? String(parts[1]) : ""
        return (parent, comm)
    }

    // MARK: - AppleScript

    private static func terminalAppScript(tty: String) -> String {
        guard !tty.isEmpty else { return #"tell application "Terminal" to activate"# }
        return """
        tell application "Terminal"
          activate
          repeat with w in windows
            repeat with t in tabs of w
              if tty of t is "\(tty)" then
                set selected of t to true
                set frontmost of w to true
                return
              end if
            end repeat
          end repeat
        end tell
        """
    }

    private static func itermScript(tty: String) -> String {
        guard !tty.isEmpty else { return #"tell application "iTerm" to activate"# }
        return """
        tell application "iTerm"
          activate
          repeat with w in windows
            repeat with t in tabs of w
              repeat with s in sessions of t
                if tty of s is "\(tty)" then
                  select w
                  select t
                  select s
                  return
                end if
              end repeat
            end repeat
          end repeat
        end tell
        """
    }

    /// VS Code cannot focus a specific integrated-terminal tab from outside, so activate the app
    /// and focus the window for the repo folder (a no-op-safe `open` that reuses an open window).
    private static func focusVSCode(cwd: String) {
        if !cwd.isEmpty, FileManager.default.fileExists(atPath: cwd) {
            _ = runProcess("/usr/bin/open", ["-a", "Visual Studio Code", cwd])
        } else {
            _ = runProcess("/usr/bin/open", ["-a", "Visual Studio Code"])
        }
    }

    private static func runAppleScript(_ source: String) {
        _ = runProcess("/usr/bin/osascript", ["-e", source])
    }

    // MARK: - Subprocess

    /// Run a tool and return its stdout, or `nil` if it cannot be launched. Synchronous; callers
    /// run it off the main thread.
    @discardableResult
    private static func runProcess(_ launchPath: String, _ arguments: [String]) -> String? {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: launchPath)
        process.arguments = arguments
        let pipe = Pipe()
        process.standardOutput = pipe
        process.standardError = Pipe()
        do {
            try process.run()
        } catch {
            return nil
        }
        let data = pipe.fileHandleForReading.readDataToEndOfFile()
        process.waitUntilExit()
        return String(data: data, encoding: .utf8)
    }
}
