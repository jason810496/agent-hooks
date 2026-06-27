import Combine
import Foundation

/// Observable view-model: polls the shared database, groups pending cards by queue, exposes
/// the notification buffer, and writes responses back. All access is main-thread only.
/// The three top-level panels reachable from the menu-bar popover.
enum Panel {
    case answers
    case sessions
    case settings
}

/// A dead session lingers as a gray row this long after its last event, then is pruned/hidden.
private let recentDeadWindowMs: Int64 = 5 * 60 * 1000

final class AppStore: ObservableObject {
    @Published private(set) var queues: [QueueGroup] = []
    @Published private(set) var notifications: [AppNotification] = []
    @Published private(set) var sessions: [Session] = []
    @Published private(set) var settings: Settings
    /// Which panel the popover is showing. Owned here so the AppKit shell can pick the default
    /// when the popover opens and the header menu can switch between panels.
    @Published var activePanel: Panel = .answers

    let database: Database
    /// Invoked after every refresh so the AppKit shell can update the badge and auto-surface.
    var onRefresh: (() -> Void)?

    /// Panel to restore when leaving Settings.
    private var panelBeforeSettings: Panel = .answers
    /// Transcript tails cached by path; re-read only when the file mtime changes.
    private var transcriptCache: [String: (mtime: Int64, tail: TranscriptTail)] = [:]
    /// Resolved terminal host per session (keyed by ``focusKey``); absent until probed once.
    private var terminalKindCache: [String: TerminalKind] = [:]
    /// Keys currently being probed off-main, to avoid duplicate resolution.
    private var resolvingFocus: Set<String> = []
    /// Keys of sessions whose terminal can be focused; drives the row's click affordance.
    @Published private(set) var focusableKeys: Set<String> = []

    init(database: Database) {
        self.database = database
        self.settings = Settings.load(from: database)
    }

    // MARK: - Navigation

    func showPanel(_ panel: Panel) {
        if panel == .settings, activePanel != .settings { panelBeforeSettings = activePanel }
        activePanel = panel
    }

    func closeSettings() { activePanel = panelBeforeSettings }

    /// Pick the default panel right before the popover opens: Answers when something is pending,
    /// otherwise the live Sessions dashboard.
    func prepareForOpen() {
        if activePanel == .settings { return }
        activePanel = pendingCount > 0 ? .answers : .sessions
    }

    var pendingCount: Int { queues.reduce(0) { $0 + $1.requests.count } }
    var unseenNotificationCount: Int { notifications.count }

    /// Seconds since the most recent pending request arrived; `.infinity` when there are none.
    func newestRequestAgeSeconds() -> Double {
        var newest: Int64 = 0
        for group in queues {
            for request in group.requests { newest = max(newest, request.createdAtMs) }
        }
        return newest > 0 ? Double(nowMs() - newest) / 1000.0 : .infinity
    }

    /// Seconds since the most recent unseen notification arrived; `.infinity` when there are none.
    func newestNotificationAgeSeconds() -> Double {
        let newest = notifications.map(\.createdAtMs).max() ?? 0
        return newest > 0 ? Double(nowMs() - newest) / 1000.0 : .infinity
    }

    func refresh() {
        var order: [String] = []
        var byQueue: [String: [PermissionRequest]] = [:]
        for raw in database.fetchPendingRequests() {
            let request = PermissionRequest.parse(raw)
            if byQueue[request.queue] == nil {
                order.append(request.queue)
                byQueue[request.queue] = []
            }
            byQueue[request.queue]?.append(request)
        }
        queues = order.map { QueueGroup(queue: $0, requests: byQueue[$0] ?? []) }
        notifications = database.fetchUnseenNotifications(limit: 100).map(AppNotification.from)
        refreshSessions()
        onRefresh?()
    }

    /// Load session rows, enrich each with its transcript tail, then keep only live sessions
    /// (plus recently-dead ones), ordered green → yellow → gray and capped to the user's limit.
    private func refreshSessions() {
        let now = nowMs()
        let localHost = ProcessInfo.processInfo.hostName
        var loaded = database.fetchSessions().map(Session.parse)
        for index in loaded.indices { enrichTranscript(&loaded[index]) }

        let visible = loaded.filter { session in
            let band = session.band(now: now, localHost: localHost)
            return band != .dead || now - session.updatedAtMs <= recentDeadWindowMs
        }
        let ordered = visible.sorted { lhs, rhs in
            let lband = lhs.band(now: now, localHost: localHost).rawValue
            let rband = rhs.band(now: now, localHost: localHost).rawValue
            if lband != rband { return lband < rband }
            return lhs.updatedAtMs > rhs.updatedAtMs
        }
        sessions = Array(ordered.prefix(settings.maxSessionsShown))
        for session in sessions where session.band(now: now, localHost: localHost) != .dead {
            resolveFocusIfNeeded(session, localHost: localHost)
        }
    }

    // MARK: - Terminal focus

    private func focusKey(_ session: Session) -> String {
        "\(session.provider):\(session.sessionId):\(session.pid)"
    }

    func canFocus(_ session: Session) -> Bool { focusableKeys.contains(focusKey(session)) }

    /// Probe a live, same-host session's terminal host once (off-main) and cache the result so the
    /// row's click affordance and the focus action are both ready without re-walking `ps`.
    private func resolveFocusIfNeeded(_ session: Session, localHost: String) {
        let key = focusKey(session)
        guard isSameHost(session.host, localHost) else { return }
        if terminalKindCache[key] != nil || resolvingFocus.contains(key) { return }
        resolvingFocus.insert(key)
        let pid = session.pid
        let cwd = session.cwd
        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            let target = TerminalFocus.resolve(sessionPid: pid, cwd: cwd)
            DispatchQueue.main.async {
                guard let self else { return }
                self.resolvingFocus.remove(key)
                guard let target else { return }
                self.terminalKindCache[key] = target.kind
                self.focusableKeys.insert(key)
            }
        }
    }

    /// Bring the session's terminal to the front (selecting the exact tab when possible). Resolves
    /// fresh on the click so the tty reflects the current process tree.
    func focusSession(_ session: Session) {
        let pid = session.pid
        let cwd = session.cwd
        DispatchQueue.global(qos: .userInitiated).async {
            if let target = TerminalFocus.resolve(sessionPid: pid, cwd: cwd) {
                TerminalFocus.focus(target)
            }
        }
    }

    private func enrichTranscript(_ session: inout Session) {
        let path = session.transcriptPath
        guard !path.isEmpty, let mtime = TranscriptReader.mtimeMs(path: path) else { return }
        session.transcriptMtimeMs = mtime
        if let cached = transcriptCache[path], cached.mtime == mtime {
            session.tail = cached.tail
            return
        }
        if let result = TranscriptReader.read(path: path) {
            transcriptCache[path] = (result.mtimeMs, result.tail)
            session.tail = result.tail
            session.transcriptMtimeMs = result.mtimeMs
        }
    }

    // MARK: - Actions

    func answer(_ request: PermissionRequest, choice: ChoiceOption) {
        database.insertResponse(
            requestUID: request.uid, selectedIndex: choice.index, answersJSON: nil, cancelled: false
        )
        refresh()
    }

    func deny(_ request: PermissionRequest) {
        database.insertResponse(
            requestUID: request.uid, selectedIndex: nil, answersJSON: nil, cancelled: true
        )
        refresh()
    }

    func answerQuestions(_ request: PermissionRequest, answers: [String: String]) {
        let json = encodeJSON(answers)
        database.insertResponse(
            requestUID: request.uid, selectedIndex: nil, answersJSON: json, cancelled: false
        )
        refresh()
    }

    /// "Send instead": deny the suggested step and feed the user's typed text back to the model
    /// as a correction.
    func sendCorrection(_ request: PermissionRequest, text: String) {
        database.insertResponse(
            requestUID: request.uid, selectedIndex: nil, answersJSON: nil, cancelled: false,
            action: FreeTextAction.denyCorrect, freetext: text
        )
        refresh()
    }

    /// "Allow + note": allow the AskUserQuestion answers and attach the user's typed text as
    /// extra context for the model.
    func allowWithNote(_ request: PermissionRequest, answers: [String: String], text: String) {
        database.insertResponse(
            requestUID: request.uid, selectedIndex: nil, answersJSON: encodeJSON(answers),
            cancelled: false, action: FreeTextAction.allowNote, freetext: text
        )
        refresh()
    }

    /// Mark the current unseen notifications seen and return them for toast display. Updates the
    /// published list directly (no full refresh) to avoid re-entering the refresh callback.
    func consumeNotificationsForToast() -> [AppNotification] {
        let current = notifications
        guard !current.isEmpty else { return [] }
        database.markNotificationsSeen(current.map { $0.id })
        notifications = []
        return current
    }

    // MARK: - Settings

    func updateSettings(_ change: (inout Settings) -> Void) {
        var updated = settings
        change(&updated)
        database.setSetting(Settings.keyThreshold, String(updated.surfaceThresholdCount))
        database.setSetting(Settings.keyQuiet, String(updated.surfaceQuietSeconds))
        database.setSetting(Settings.keyPoll, String(updated.pollIntervalMs))
        database.setSetting(Settings.keyTextSize, String(updated.textSizeLevel))
        database.setSetting(Settings.keyMaxSessions, String(updated.maxSessionsShown))
        settings = Settings.load(from: database)
    }
}

private func encodeJSON(_ value: [String: String]) -> String? {
    guard let data = try? JSONSerialization.data(withJSONObject: value) else { return nil }
    return String(data: data, encoding: .utf8)
}
