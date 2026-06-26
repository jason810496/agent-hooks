import Darwin

/// Return whether a process id is still alive on this host.
///
/// `kill(pid, 0)` performs no signal delivery but reports reachability: success means alive,
/// `EPERM` means alive but owned by another user, and `ESRCH` means the process is gone.
func processIsAlive(_ pid: Int32) -> Bool {
    guard pid > 0 else { return false }
    if kill(pid, 0) == 0 { return true }
    return errno == EPERM
}

/// Whether a recorded host matches this machine. Compared case-insensitively because Python
/// (`socket.gethostname()`) and Swift (`ProcessInfo.hostName`) can disagree on case
/// (e.g. `Jasons-MacBook-Pro.local` vs `jasons-macbook-pro.local`). An empty recorded host is
/// treated as a match so liveness still resolves.
func isSameHost(_ recorded: String, _ local: String) -> Bool {
    recorded.isEmpty || recorded.caseInsensitiveCompare(local) == .orderedSame
}
