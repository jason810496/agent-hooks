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
