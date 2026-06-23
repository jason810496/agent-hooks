import Combine
import Foundation

/// Observable view-model: polls the shared database, groups pending cards by queue, exposes
/// the notification buffer, and writes responses back. All access is main-thread only.
final class AppStore: ObservableObject {
    @Published private(set) var queues: [QueueGroup] = []
    @Published private(set) var notifications: [AppNotification] = []
    @Published private(set) var settings: Settings

    let database: Database
    /// Invoked after every refresh so the AppKit shell can update the badge and auto-surface.
    var onRefresh: (() -> Void)?

    init(database: Database) {
        self.database = database
        self.settings = Settings.load(from: database)
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
        onRefresh?()
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
        settings = Settings.load(from: database)
    }
}

private func encodeJSON(_ value: [String: String]) -> String? {
    guard let data = try? JSONSerialization.data(withJSONObject: value) else { return nil }
    return String(data: data, encoding: .utf8)
}
