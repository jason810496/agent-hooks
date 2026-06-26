import Foundation

/// Rich, live detail for one session, reconstructed by tailing its transcript JSONL. None of
/// this is in the hook stream between events, so the long-running app re-reads it each tick.
struct TranscriptTail {
    var toolName: String?
    var toolSummary: String = ""
    /// True when the latest `tool_use` has no matching `tool_result` yet (the tool is running).
    var toolInFlight: Bool = false
    /// Last few lines of the completed tool's output (the `⎿` block).
    var outputTail: String = ""
    /// Last assistant text, used as a one-line message preview.
    var lastMessage: String = ""
    /// Timestamp (ms) of the in-flight `tool_use` entry, for a per-tool elapsed timer.
    var toolStartedMs: Int64?
}

/// Tails a Claude Code / Codex transcript file (JSONL). Reads only the last chunk of the file so
/// it stays cheap on the 400ms poll; the caller caches results by file mtime.
enum TranscriptReader {
    private static let tailBytes: UInt64 = 128 * 1024
    private static let maxSummary = 140
    private static let maxOutputLines = 6
    private static let maxOutputChars = 600

    /// Modification time in epoch ms, or nil when the file is missing/unreadable.
    static func mtimeMs(path: String) -> Int64? {
        guard !path.isEmpty,
            let attrs = try? FileManager.default.attributesOfItem(atPath: path),
            let date = attrs[.modificationDate] as? Date
        else { return nil }
        return Int64(date.timeIntervalSince1970 * 1000)
    }

    /// Parse the transcript tail, returning the reconstructed detail and the file mtime, or nil
    /// when the file cannot be read.
    static func read(path: String) -> (tail: TranscriptTail, mtimeMs: Int64)? {
        guard !path.isEmpty, let mtime = mtimeMs(path: path),
            let handle = FileHandle(forReadingAtPath: path)
        else { return nil }
        defer { try? handle.close() }

        let size = (try? handle.seekToEnd()) ?? 0
        let start = size > tailBytes ? size - tailBytes : 0
        try? handle.seek(toOffset: start)
        let data = (try? handle.readToEnd()) ?? Data()
        guard !data.isEmpty else { return (TranscriptTail(), mtime) }

        var lines = String(decoding: data, as: UTF8.self)
            .split(separator: "\n", omittingEmptySubsequences: true).map(String.init)
        if start > 0, !lines.isEmpty { lines.removeFirst() }  // drop the partial leading line

        var lastToolUse: (id: String, name: String, summary: String, ts: Int64?)?
        var completed: Set<String> = []
        var outputs: [String: String] = [:]
        var lastMessage = ""

        for line in lines {
            guard let object = parseObject(line),
                let type = object["type"] as? String, type == "assistant" || type == "user",
                let message = object["message"] as? [String: Any],
                let content = message["content"] as? [[String: Any]]
            else { continue }
            let timestamp = millis(from: object["timestamp"] as? String)
            for item in content {
                switch item["type"] as? String {
                case "tool_use":
                    lastToolUse = (
                        id: item["id"] as? String ?? "",
                        name: item["name"] as? String ?? "",
                        summary: summarize(item["input"] as? [String: Any] ?? [:]),
                        ts: timestamp
                    )
                case "tool_result":
                    if let id = item["tool_use_id"] as? String {
                        completed.insert(id)
                        outputs[id] = outputTail(of: item["content"])
                    }
                case "text":
                    if type == "assistant", let text = item["text"] as? String, !text.isEmpty {
                        lastMessage = text
                    }
                default:
                    break
                }
            }
        }

        var tail = TranscriptTail()
        tail.lastMessage = oneLine(lastMessage, limit: 200)
        if let toolUse = lastToolUse {
            tail.toolName = toolUse.name
            tail.toolSummary = toolUse.summary
            tail.toolInFlight = !completed.contains(toolUse.id)
            tail.toolStartedMs = toolUse.ts
            if !tail.toolInFlight { tail.outputTail = outputs[toolUse.id] ?? "" }
        }
        return (tail, mtime)
    }

    // MARK: - Helpers

    private static func parseObject(_ line: String) -> [String: Any]? {
        guard let data = line.data(using: .utf8),
            let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        else { return nil }
        return object
    }

    private static let isoFractional: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return formatter
    }()
    private static let isoPlain = ISO8601DateFormatter()

    private static func millis(from iso: String?) -> Int64? {
        guard let iso, !iso.isEmpty else { return nil }
        guard let date = isoFractional.date(from: iso) ?? isoPlain.date(from: iso) else {
            return nil
        }
        return Int64(date.timeIntervalSince1970 * 1000)
    }

    private static func summarize(_ input: [String: Any]) -> String {
        for key in ["command", "file_path", "description", "pattern", "url", "query", "prompt"] {
            if let value = input[key] as? String,
                !value.trimmingCharacters(in: .whitespaces).isEmpty {
                return oneLine(value, limit: maxSummary)
            }
        }
        for value in input.values {
            if let string = value as? String, !string.isEmpty {
                return oneLine(string, limit: maxSummary)
            }
        }
        return ""
    }

    private static func outputTail(of content: Any?) -> String {
        var combined = ""
        if let string = content as? String {
            combined = string
        } else if let array = content as? [Any] {
            combined = array.compactMap { element -> String? in
                if let dict = element as? [String: Any] { return dict["text"] as? String }
                return element as? String
            }.joined(separator: "\n")
        }
        var lines = combined.split(separator: "\n", omittingEmptySubsequences: false).map(String.init)
        if lines.count > maxOutputLines { lines = Array(lines.suffix(maxOutputLines)) }
        var result = lines.joined(separator: "\n")
        if result.count > maxOutputChars { result = "…" + String(result.suffix(maxOutputChars)) }
        return result
    }

    private static func oneLine(_ string: String, limit: Int) -> String {
        let collapsed = string.replacingOccurrences(of: "\n", with: " ")
            .trimmingCharacters(in: .whitespacesAndNewlines)
        if collapsed.count > limit { return String(collapsed.prefix(limit)) + "…" }
        return collapsed
    }
}
