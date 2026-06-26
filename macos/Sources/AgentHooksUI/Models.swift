import Foundation

enum RequestKind: String {
    case permission
    case permissionChoice = "permission_choice"
    case askUserQuestion = "ask_user_question"
    case unknown
}

/// One actionable button on a permission card. `selectedIndex` is the value written back to
/// ``responses.selected_index``; it indexes the transport's in-memory option list.
struct ChoiceOption: Identifiable {
    let index: Int
    let label: String
    let button: String  // "Deny" | "Allow Once" | "Always Allow"
    let suggestionIndex: Int?
    var id: Int { index }

    var isDeny: Bool { button == "Deny" }
}

struct QuestionOption: Identifiable {
    let index: Int
    let label: String
    let detail: String
    var id: Int { index }
}

struct Question: Identifiable {
    let index: Int
    let text: String
    let header: String
    let multiSelect: Bool
    let options: [QuestionOption]
    var id: Int { index }
}

/// A pending permission/question card decoded from a `requests` row.
struct PermissionRequest: Identifiable {
    let uid: String
    let kind: RequestKind
    let queue: String
    let title: String
    let summary: String
    let toolName: String
    let createdAtMs: Int64
    let choices: [ChoiceOption]
    let questions: [Question]

    var id: String { uid }

    static func parse(_ raw: RawRequest) -> PermissionRequest {
        let kind = RequestKind(rawValue: raw.kind) ?? .unknown
        let options = decodeObject(raw.optionsJSON)
        var choices: [ChoiceOption] = []
        var questions: [Question] = []

        switch kind {
        case .permissionChoice:
            choices = parseChoices(options["choices"] as? [[String: Any]] ?? [])
        case .permission:
            let buttons = options["buttons"] as? [String] ?? []
            choices = buttons.enumerated().map { index, label in
                ChoiceOption(index: index, label: label, button: label, suggestionIndex: nil)
            }
        case .askUserQuestion:
            questions = parseQuestions(options["questions"] as? [[String: Any]] ?? [])
        case .unknown:
            break
        }

        return PermissionRequest(
            uid: raw.uid,
            kind: kind,
            queue: raw.queue,
            title: raw.title,
            summary: raw.summary,
            toolName: raw.toolName,
            createdAtMs: raw.createdAtMs,
            choices: choices,
            questions: questions
        )
    }

    private static func parseChoices(_ raw: [[String: Any]]) -> [ChoiceOption] {
        raw.enumerated().map { index, entry in
            ChoiceOption(
                index: index,
                label: entry["label"] as? String ?? "",
                button: entry["button"] as? String ?? "Allow Once",
                suggestionIndex: entry["suggestion_index"] as? Int
            )
        }
    }

    private static func parseQuestions(_ raw: [[String: Any]]) -> [Question] {
        raw.enumerated().map { index, entry in
            let optionEntries = entry["options"] as? [[String: Any]] ?? []
            let options = optionEntries.enumerated().map { optionIndex, option in
                QuestionOption(
                    index: optionIndex,
                    label: option["label"] as? String ?? "",
                    detail: option["description"] as? String ?? ""
                )
            }
            return Question(
                index: index,
                text: entry["question"] as? String ?? "",
                header: entry["header"] as? String ?? "",
                multiSelect: entry["multi_select"] as? Bool ?? false,
                options: options
            )
        }
    }
}

struct AppNotification: Identifiable {
    let id: Int64
    let queue: String
    let kind: String
    let title: String
    let subtitle: String
    let message: String
    let createdAtMs: Int64

    static func from(_ raw: RawNotification) -> AppNotification {
        AppNotification(
            id: raw.id,
            queue: raw.queue,
            kind: raw.kind,
            title: raw.title,
            subtitle: raw.subtitle,
            message: raw.message,
            createdAtMs: raw.createdAtMs
        )
    }
}

/// One repo/worktree lane of pending cards.
struct QueueGroup: Identifiable {
    let queue: String
    let requests: [PermissionRequest]
    var id: String { queue }
    var displayName: String {
        let name = (queue as NSString).lastPathComponent
        return name.isEmpty ? queue : name
    }
}

private func decodeObject(_ json: String) -> [String: Any] {
    guard let data = json.data(using: .utf8),
        let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
    else { return [:] }
    return object
}

/// Short relative age label, e.g. "just now", "3m", "2h".
func relativeAge(fromMs createdAtMs: Int64) -> String {
    let seconds = max(0, Int(nowMs() - createdAtMs) / 1000)
    if seconds < 5 { return "just now" }
    if seconds < 60 { return "\(seconds)s" }
    let minutes = seconds / 60
    if minutes < 60 { return "\(minutes)m" }
    let hours = minutes / 60
    if hours < 24 { return "\(hours)h" }
    return "\(hours / 24)d"
}

/// Format an elapsed duration like the TUI status line, e.g. "45s", "11m 59s", "1h 2m".
func formatDuration(ms: Int64) -> String {
    let total = max(0, Int(ms / 1000))
    let hours = total / 3600
    let minutes = (total % 3600) / 60
    let seconds = total % 60
    if hours > 0 { return "\(hours)h \(minutes)m" }
    if minutes > 0 { return "\(minutes)m \(seconds)s" }
    return "\(seconds)s"
}

// MARK: - Sessions

/// Round state persisted by the Python hook. Aliveness is *not* stored — it is derived from
/// process liveness + transcript mtime so it can never go stale.
enum SessionStatus: String {
    case working
    case idle
    case failed
    case unknown
}

/// Liveness band that drives both ordering and the dot color (green / yellow / gray). A failed
/// session keeps its band (so it sorts by liveness) but paints its dot red.
enum SessionBand: Int, Comparable {
    case working = 0  // green: alive and working
    case idle = 1     // yellow: alive but idle
    case dead = 2     // gray: process gone

    static func < (lhs: SessionBand, rhs: SessionBand) -> Bool { lhs.rawValue < rhs.rawValue }
}

/// A session whose transcript changed within this window is treated as alive even if its
/// recorded pid looks dead — covers the case where `getppid()` resolved to a transient shell.
let transcriptAliveWindowMs: Int64 = 10_000

/// One Claude Code / Codex session decoded from a `sessions` row, enriched with live transcript
/// detail by ``AppStore``.
struct Session: Identifiable {
    let sessionId: String
    let provider: String
    let queue: String
    let cwd: String
    let model: String
    let transcriptPath: String
    let pid: Int32
    let host: String
    let status: SessionStatus
    let lastEvent: String
    let toolName: String
    let roundStartedMs: Int64?
    let lastRoundMs: Int64?
    let errorText: String
    let updatedAtMs: Int64

    /// Live detail filled in by ``AppStore`` after reading the transcript tail.
    var tail: TranscriptTail?
    var transcriptMtimeMs: Int64?

    var id: String { "\(provider):\(sessionId)" }

    var displayName: String {
        let name = (queue as NSString).lastPathComponent
        return name.isEmpty ? queue : name
    }

    var failed: Bool { status == .failed }

    static func parse(_ raw: RawSession) -> Session {
        Session(
            sessionId: raw.sessionId,
            provider: raw.provider,
            queue: raw.queue,
            cwd: raw.cwd,
            model: raw.model,
            transcriptPath: raw.transcriptPath,
            pid: raw.pid,
            host: raw.host,
            status: SessionStatus(rawValue: raw.status) ?? .unknown,
            lastEvent: raw.lastEvent,
            toolName: raw.toolName,
            roundStartedMs: raw.roundStartedMs,
            lastRoundMs: raw.lastRoundMs,
            errorText: raw.errorText,
            updatedAtMs: raw.updatedAtMs,
            tail: nil,
            transcriptMtimeMs: nil
        )
    }

    func isAlive(now: Int64, localHost: String) -> Bool {
        if let mtime = transcriptMtimeMs, now - mtime <= transcriptAliveWindowMs { return true }
        return isSameHost(host, localHost) && processIsAlive(pid)
    }

    func band(now: Int64, localHost: String) -> SessionBand {
        guard isAlive(now: now, localHost: localHost) else { return .dead }
        if tail?.toolInFlight == true { return .working }
        return status == .working ? .working : .idle
    }
}
