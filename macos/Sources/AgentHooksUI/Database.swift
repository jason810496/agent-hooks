import Foundation
import SQLite3

/// SQLite is copied (not referenced) when binding text, so values survive the call.
private let SQLITE_TRANSIENT = unsafeBitCast(-1, to: sqlite3_destructor_type.self)

enum DatabaseError: Error {
    case open(String)
    case message(String)
}

/// Raw request row as stored by the Python hook process.
struct RawRequest {
    let uid: String
    let kind: String
    let queue: String
    let cwd: String
    let sessionId: String
    let provider: String
    let toolName: String
    let title: String
    let summary: String
    let toolInputJSON: String
    let optionsJSON: String
    let suggestionsJSON: String
    let createdAtMs: Int64
    let ownerPid: Int32
    let heartbeatAtMs: Int64
}

/// Raw notification row from the non-blocking buffer.
struct RawNotification {
    let id: Int64
    let queue: String
    let kind: String
    let title: String
    let subtitle: String
    let message: String
    let createdAtMs: Int64
}

/// Thin wrapper over the shared SQLite database. All calls run on the main thread; the
/// connection is serialized and uses WAL so it coexists with the concurrent Python writers.
final class Database {
    private var handle: OpaquePointer?

    init(path: String) throws {
        let directory = (path as NSString).deletingLastPathComponent
        try? FileManager.default.createDirectory(
            atPath: directory, withIntermediateDirectories: true
        )
        let flags = SQLITE_OPEN_READWRITE | SQLITE_OPEN_CREATE | SQLITE_OPEN_FULLMUTEX
        if sqlite3_open_v2(path, &handle, flags, nil) != SQLITE_OK {
            throw DatabaseError.open(lastErrorMessage())
        }
        sqlite3_busy_timeout(handle, 5000)
        try exec("PRAGMA journal_mode=WAL;")
        try exec("PRAGMA foreign_keys=ON;")
    }

    deinit {
        if handle != nil { sqlite3_close_v2(handle) }
    }

    // MARK: - Bootstrap

    func bootstrap() throws {
        if currentUserVersion() < Schema.userVersion {
            try exec(Schema.sql)
        }
    }

    private func currentUserVersion() -> Int32 {
        var statement: OpaquePointer?
        guard sqlite3_prepare_v2(handle, "PRAGMA user_version", -1, &statement, nil) == SQLITE_OK
        else { return 0 }
        defer { sqlite3_finalize(statement) }
        guard sqlite3_step(statement) == SQLITE_ROW else { return 0 }
        return Int32(sqlite3_column_int64(statement, 0))
    }

    // MARK: - Reads

    func fetchPendingRequests() -> [RawRequest] {
        let sql = """
        SELECT request_uid, kind, queue, cwd, session_id, provider, tool_name, title, summary,
               tool_input_json, options_json, suggestions_json, created_at_ms, owner_pid,
               heartbeat_at_ms
        FROM requests r
        WHERE r.status = 'pending'
          AND NOT EXISTS (SELECT 1 FROM responses x WHERE x.request_uid = r.request_uid)
        ORDER BY r.created_at_ms ASC
        """
        var rows: [RawRequest] = []
        query(sql) { stmt in
            rows.append(
                RawRequest(
                    uid: text(stmt, 0),
                    kind: text(stmt, 1),
                    queue: text(stmt, 2),
                    cwd: text(stmt, 3),
                    sessionId: text(stmt, 4),
                    provider: text(stmt, 5),
                    toolName: text(stmt, 6),
                    title: text(stmt, 7),
                    summary: text(stmt, 8),
                    toolInputJSON: text(stmt, 9),
                    optionsJSON: text(stmt, 10),
                    suggestionsJSON: text(stmt, 11),
                    createdAtMs: sqlite3_column_int64(stmt, 12),
                    ownerPid: Int32(sqlite3_column_int64(stmt, 13)),
                    heartbeatAtMs: sqlite3_column_int64(stmt, 14)
                )
            )
        }
        return rows
    }

    func fetchUnseenNotifications(limit: Int) -> [RawNotification] {
        let sql = """
        SELECT id, queue, kind, title, subtitle, message, created_at_ms
        FROM notifications
        WHERE seen_at_ms IS NULL
        ORDER BY created_at_ms DESC
        LIMIT \(limit)
        """
        var rows: [RawNotification] = []
        query(sql) { stmt in
            rows.append(
                RawNotification(
                    id: sqlite3_column_int64(stmt, 0),
                    queue: text(stmt, 1),
                    kind: text(stmt, 2),
                    title: text(stmt, 3),
                    subtitle: text(stmt, 4),
                    message: text(stmt, 5),
                    createdAtMs: sqlite3_column_int64(stmt, 6)
                )
            )
        }
        return rows
    }

    /// Owner identity for every pending request, for the orphan janitor.
    func pendingOwners() -> [PendingOwner] {
        let sql = """
        SELECT request_uid, owner_pid, owner_host, heartbeat_at_ms FROM requests
        WHERE status = 'pending'
        """
        var rows: [PendingOwner] = []
        query(sql) { stmt in
            rows.append(
                PendingOwner(
                    uid: text(stmt, 0),
                    pid: Int32(sqlite3_column_int64(stmt, 1)),
                    host: text(stmt, 2),
                    heartbeatAtMs: sqlite3_column_int64(stmt, 3)
                )
            )
        }
        return rows
    }

    // MARK: - Writes

    func insertResponse(
        requestUID: String,
        selectedIndex: Int?,
        answersJSON: String?,
        cancelled: Bool
    ) {
        let sql = """
        INSERT INTO responses
          (request_uid, selected_index, answers_json, cancelled, responder, created_at_ms)
        VALUES (?, ?, ?, ?, 'swift_ui', ?)
        """
        execute(sql) { stmt in
            bindText(stmt, 1, requestUID)
            if let index = selectedIndex {
                sqlite3_bind_int64(stmt, 2, Int64(index))
            } else {
                sqlite3_bind_null(stmt, 2)
            }
            if let answers = answersJSON {
                bindText(stmt, 3, answers)
            } else {
                sqlite3_bind_null(stmt, 3)
            }
            sqlite3_bind_int64(stmt, 4, cancelled ? 1 : 0)
            sqlite3_bind_int64(stmt, 5, nowMs())
        }
    }

    func markAbandoned(_ uids: [String]) {
        guard !uids.isEmpty else { return }
        for uid in uids {
            execute("UPDATE requests SET status = 'abandoned' WHERE request_uid = ? AND status = 'pending'") {
                stmt in
                bindText(stmt, 1, uid)
            }
        }
    }

    func markNotificationsSeen(_ ids: [Int64]) {
        guard !ids.isEmpty else { return }
        let now = nowMs()
        for id in ids {
            execute("UPDATE notifications SET seen_at_ms = ? WHERE id = ?") { stmt in
                sqlite3_bind_int64(stmt, 1, now)
                sqlite3_bind_int64(stmt, 2, id)
            }
        }
    }

    func upsertDaemonHeartbeat(pid: Int32, host: String, version: String) {
        let sql = """
        INSERT INTO daemon (id, pid, host, version, heartbeat_at_ms)
        VALUES (1, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
          pid = excluded.pid, host = excluded.host,
          version = excluded.version, heartbeat_at_ms = excluded.heartbeat_at_ms
        """
        execute(sql) { stmt in
            sqlite3_bind_int64(stmt, 1, Int64(pid))
            bindText(stmt, 2, host)
            bindText(stmt, 3, version)
            sqlite3_bind_int64(stmt, 4, nowMs())
        }
    }

    func prune(terminalOlderThanMs terminalCutoff: Int64, notificationsOlderThanMs notifCutoff: Int64) {
        execute(
            "DELETE FROM responses WHERE request_uid IN "
                + "(SELECT request_uid FROM requests WHERE status IN "
                + "('answered','cancelled','abandoned','expired') AND created_at_ms < ?)"
        ) { stmt in sqlite3_bind_int64(stmt, 1, terminalCutoff) }
        execute(
            "DELETE FROM requests WHERE status IN "
                + "('answered','cancelled','abandoned','expired') AND created_at_ms < ?"
        ) { stmt in sqlite3_bind_int64(stmt, 1, terminalCutoff) }
        execute("DELETE FROM notifications WHERE seen_at_ms IS NOT NULL AND created_at_ms < ?") {
            stmt in sqlite3_bind_int64(stmt, 1, notifCutoff)
        }
    }

    /// Diagnostics only (``--selftest``): insert a synthetic pending request. The normal flow
    /// never inserts requests from Swift; the Python hook owns that table.
    func diagnosticsInsertRequest(
        uid: String,
        kind: String,
        queue: String,
        optionsJSON: String,
        ownerPid: Int32,
        heartbeatAtMs: Int64
    ) {
        execute(
            """
            INSERT INTO requests
              (request_uid, kind, status, queue, cwd, provider, tool_name, title, summary,
               tool_input_json, options_json, suggestions_json, owner_pid, created_at_ms,
               heartbeat_at_ms)
            VALUES (?, ?, 'pending', ?, ?, 'claude-code', 'Bash', 'Title', 'summary',
               '{}', ?, '[]', ?, ?, ?)
            """
        ) { stmt in
            bindText(stmt, 1, uid)
            bindText(stmt, 2, kind)
            bindText(stmt, 3, queue)
            bindText(stmt, 4, queue)
            bindText(stmt, 5, optionsJSON)
            sqlite3_bind_int64(stmt, 6, Int64(ownerPid))
            sqlite3_bind_int64(stmt, 7, nowMs())
            sqlite3_bind_int64(stmt, 8, heartbeatAtMs)
        }
    }

    // MARK: - Settings

    func ensureSettingsDefaults(_ defaults: [String: String]) {
        for (key, value) in defaults {
            execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)") { stmt in
                bindText(stmt, 1, key)
                bindText(stmt, 2, value)
            }
        }
    }

    func settingValue(_ key: String) -> String? {
        var result: String?
        query("SELECT value FROM settings WHERE key = ?", bind: { stmt in
            bindText(stmt, 1, key)
        }) { stmt in
            result = text(stmt, 0)
        }
        return result
    }

    func setSetting(_ key: String, _ value: String) {
        let sql = """
        INSERT INTO settings (key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """
        execute(sql) { stmt in
            bindText(stmt, 1, key)
            bindText(stmt, 2, value)
        }
    }

    // MARK: - Low-level helpers

    private func exec(_ sql: String) throws {
        var errorPointer: UnsafeMutablePointer<CChar>?
        if sqlite3_exec(handle, sql, nil, nil, &errorPointer) != SQLITE_OK {
            let message = errorPointer.map { String(cString: $0) } ?? "unknown error"
            sqlite3_free(errorPointer)
            throw DatabaseError.message(message)
        }
    }

    /// Run a read query, binding parameters then invoking `onRow` for each result row.
    private func query(
        _ sql: String,
        bind: (OpaquePointer) -> Void = { _ in },
        _ onRow: (OpaquePointer) -> Void
    ) {
        var statement: OpaquePointer?
        guard sqlite3_prepare_v2(handle, sql, -1, &statement, nil) == SQLITE_OK else { return }
        defer { sqlite3_finalize(statement) }
        bind(statement!)
        while sqlite3_step(statement) == SQLITE_ROW {
            onRow(statement!)
        }
    }

    /// Run a write statement; the trailing closure binds parameters before a single step.
    private func execute(_ sql: String, bind: (OpaquePointer) -> Void = { _ in }) {
        var statement: OpaquePointer?
        guard sqlite3_prepare_v2(handle, sql, -1, &statement, nil) == SQLITE_OK else { return }
        defer { sqlite3_finalize(statement) }
        bind(statement!)
        sqlite3_step(statement)
    }

    private func bindText(_ stmt: OpaquePointer, _ index: Int32, _ value: String) {
        sqlite3_bind_text(stmt, index, (value as NSString).utf8String, -1, SQLITE_TRANSIENT)
    }

    private func lastErrorMessage() -> String {
        if let message = sqlite3_errmsg(handle) { return String(cString: message) }
        return "unknown error"
    }
}

/// Read a TEXT column as a Swift string (empty when NULL).
private func text(_ stmt: OpaquePointer, _ index: Int32) -> String {
    guard let value = sqlite3_column_text(stmt, index) else { return "" }
    return String(cString: value)
}
