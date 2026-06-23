import Foundation

/// Owner identity for one pending request, used to detect abandoned cards.
struct PendingOwner {
    let uid: String
    let pid: Int32
    let host: String
    let heartbeatAtMs: Int64
}

/// Grace after the last heartbeat before a dead-pid owner is reaped. Covers the brief window
/// between a hook being killed and its parent reaping the zombie (during which `kill(pid, 0)`
/// still reports the pid alive), plus any insert/check race.
let reapGraceMs: Int64 = 2_000

/// Catch-all: a pending request whose heartbeat is this stale is abandoned regardless of pid
/// state. A live hook heartbeats every poll (default 0.2s), so this only fires for owners that
/// are truly gone (e.g. an unreaped zombie, or a process on another host). Keep it well above
/// any realistic `AGENT_HOOK_SQLITE_POLL_INTERVAL`.
let staleHeartbeatMs: Int64 = 20_000

/// Return the request ids whose owning hook is no longer waiting and should be abandoned.
///
/// A live, blocking hook refreshes `heartbeat_at_ms` on every poll, so a stale heartbeat is the
/// authoritative "not waiting anymore" signal. We confirm with pid liveness on the same host to
/// reap promptly, and fall back to a pure staleness cutoff for zombies / other hosts.
func deadRequestUIDs(
    _ owners: [PendingOwner],
    now: Int64,
    host: String
) -> [String] {
    owners.compactMap { owner in
        let age = now - owner.heartbeatAtMs
        let sameHost = owner.host == host || owner.host.isEmpty
        if sameHost && age > reapGraceMs && !processIsAlive(owner.pid) {
            return owner.uid
        }
        if age > staleHeartbeatMs {
            return owner.uid
        }
        return nil
    }
}
