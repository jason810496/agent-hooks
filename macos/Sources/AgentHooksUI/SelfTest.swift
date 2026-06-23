import Foundation

/// Headless health check exercised via `agent-hooks-ui --selftest`. Round-trips a request,
/// response, settings read, and the orphan janitor against a throwaway database so the SQLite
/// layer can be validated without a desktop session.
enum SelfTest {
    static func run() -> Bool {
        let path = (NSTemporaryDirectory() as NSString)
            .appendingPathComponent("agent-hooks-selftest-\(UUID().uuidString).db")
        defer { try? FileManager.default.removeItem(atPath: path) }

        var ok = true
        func check(_ condition: Bool, _ label: String) {
            print((condition ? "PASS" : "FAIL") + ": " + label)
            if !condition { ok = false }
        }

        do {
            let db = try Database(path: path)
            try db.bootstrap()
            db.ensureSettingsDefaults(Settings.defaults)

            let options = """
            {"default_index":0,"choices":[\
            {"label":"Allow once","button":"Allow Once","suggestion_index":null},\
            {"label":"Bash(git *)","button":"Always Allow","suggestion_index":0}]}
            """
            db.diagnosticsInsertRequest(
                uid: "t1", kind: "permission_choice", queue: "/tmp/repo",
                optionsJSON: options,
                ownerPid: ProcessInfo.processInfo.processIdentifier, heartbeatAtMs: nowMs()
            )

            let pending = db.fetchPendingRequests()
            check(pending.count == 1, "one pending request")
            if let raw = pending.first {
                let request = PermissionRequest.parse(raw)
                check(request.kind == .permissionChoice, "kind parsed")
                check(request.choices.count == 2, "two choices parsed")
                check(request.choices.last?.suggestionIndex == 0, "suggestion index parsed")
                check(request.choices.last?.label == "Bash(git *)", "exact rule label parsed")
            }

            db.insertResponse(requestUID: "t1", selectedIndex: 1, answersJSON: nil, cancelled: false)
            check(db.fetchPendingRequests().isEmpty, "answered request leaves the queue")
            check(db.settingValue(Settings.keyThreshold) == "5", "settings default present")

            db.diagnosticsInsertRequest(
                uid: "dead", kind: "permission", queue: "/tmp/repo",
                optionsJSON: "{\"buttons\":[\"Deny\",\"Allow Once\"]}",
                ownerPid: 2_000_000, heartbeatAtMs: nowMs() - 60_000
            )
            let dead = deadRequestUIDs(
                db.pendingOwners(), now: nowMs(), host: ProcessInfo.processInfo.hostName
            )
            check(dead.contains("dead"), "dead-owner request detected")
            db.markAbandoned(dead)
            check(
                !db.fetchPendingRequests().contains { $0.uid == "dead" },
                "abandoned request removed from queue"
            )
        } catch {
            check(false, "open/bootstrap: \(error)")
        }

        print(ok ? "selftest: OK" : "selftest: FAILURES")
        return ok
    }
}
