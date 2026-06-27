import AppKit
import SwiftUI

let appVersion = "0.3.0"

private let heartbeatInterval: TimeInterval = 5
private let janitorInterval: TimeInterval = 2
private let retentionMs: Int64 = 24 * 60 * 60 * 1000
/// A dead session may be pruned once it has been silent this long (matches the gray-row window
/// in ``AppStore``). Live sessions are kept regardless of age.
private let sessionStaleMs: Int64 = 5 * 60 * 1000

final class AppDelegate: NSObject, NSApplicationDelegate {
    private var statusItem: NSStatusItem!
    private var popover: NSPopover!
    private var store: AppStore!
    private let toastPresenter = ToastPresenter()

    private var pollTimer: Timer?
    private var heartbeatTimer: Timer?
    private var janitorTimer: Timer?

    /// True once the panel has auto-surfaced for the current batch; reset when it empties so a
    /// dismissed panel does not immediately pop back up.
    private var autoSurfaced = false

    func applicationDidFinishLaunching(_ notification: Notification) {
        let path =
            ProcessInfo.processInfo.environment["AGENT_HOOK_DB_PATH"] ?? Self.defaultDatabasePath()
        do {
            let database = try Database(path: path)
            try database.bootstrap()
            database.ensureSettingsDefaults(Settings.defaults)
            store = AppStore(database: database)
        } catch {
            NSLog("agent-hooks-ui: cannot open database at \(path): \(error)")
            NSApp.terminate(nil)
            return
        }

        setupStatusItem()
        setupPopover()
        store.onRefresh = { [weak self] in self?.handleRefresh() }

        writeHeartbeat()
        runJanitor()
        store.refresh()
        startTimers()
    }

    func applicationWillTerminate(_ notification: Notification) {
        pollTimer?.invalidate()
        heartbeatTimer?.invalidate()
        janitorTimer?.invalidate()
    }

    // MARK: - Setup

    private func setupStatusItem() {
        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        if let button = statusItem.button {
            let icon = BrandIcon.image(size: 18, template: true, inset: 1)
            icon.accessibilityDescription = "Agent Hooks"
            button.image = icon
            button.imagePosition = .imageLeading
            button.action = #selector(statusButtonClicked)
            button.target = self
            button.sendAction(on: [.leftMouseUp, .rightMouseUp])
        }
    }

    private func setupPopover() {
        popover = NSPopover()
        popover.behavior = .transient
        popover.contentSize = NSSize(width: 760, height: 520)
        popover.contentViewController = NSHostingController(
            rootView: PanelView().environmentObject(store)
        )
    }

    private func startTimers() {
        let pollSeconds = Double(store.settings.pollIntervalMs) / 1000.0
        pollTimer = Timer.scheduledTimer(withTimeInterval: pollSeconds, repeats: true) {
            [weak self] _ in self?.store.refresh()
        }
        heartbeatTimer = Timer.scheduledTimer(withTimeInterval: heartbeatInterval, repeats: true) {
            [weak self] _ in self?.writeHeartbeat()
        }
        janitorTimer = Timer.scheduledTimer(withTimeInterval: janitorInterval, repeats: true) {
            [weak self] _ in self?.runJanitor()
        }
    }

    // MARK: - Refresh / badge / auto-surface

    private func handleRefresh() {
        updateBadge(pending: store.pendingCount)
        surfacePanelForRequests()
        toastNotifications()
    }

    /// Auto-surface the panel for pending permission requests using the batching thresholds.
    private func surfacePanelForRequests() {
        let pending = store.pendingCount
        if pending == 0 {
            autoSurfaced = false
            return
        }
        guard !popover.isShown, !autoSurfaced else { return }

        let reachedCount = pending >= store.settings.surfaceThresholdCount
        let quietElapsed =
            store.newestRequestAgeSeconds() >= Double(store.settings.surfaceQuietSeconds)
        if reachedCount || quietElapsed {
            showPopover()
            autoSurfaced = true
        }
    }

    /// Surface unseen notifications as top-right toast banners (never the panel), batching by
    /// the same count / quiet thresholds, then mark them seen so they are not shown twice.
    private func toastNotifications() {
        let unseen = store.notifications
        guard !unseen.isEmpty else { return }

        let reachedCount = unseen.count >= store.settings.surfaceThresholdCount
        let quietElapsed =
            store.newestNotificationAgeSeconds() >= Double(store.settings.surfaceQuietSeconds)
        guard reachedCount || quietElapsed else { return }

        toastPresenter.present(store.consumeNotificationsForToast())
    }

    private func updateBadge(pending: Int) {
        statusItem.button?.title = pending > 0 ? " \(pending)" : ""
    }

    // MARK: - Heartbeat / janitor

    private func writeHeartbeat() {
        store.database.upsertDaemonHeartbeat(
            pid: ProcessInfo.processInfo.processIdentifier,
            host: ProcessInfo.processInfo.hostName,
            version: appVersion
        )
    }

    private func runJanitor() {
        let dead = deadRequestUIDs(
            store.database.pendingOwners(),
            now: nowMs(),
            host: ProcessInfo.processInfo.hostName
        )
        store.database.markAbandoned(dead)

        // Clear cards the user answered in the agent's own TUI: writing a cancelled response
        // unblocks the (possibly still-waiting) hook and drops the card from the queue.
        let superseded = store.database.supersededRequestUIDs()
        for uid in superseded {
            store.database.insertResponse(
                requestUID: uid, selectedIndex: nil, answersJSON: nil,
                cancelled: true, responder: "self"
            )
        }

        store.database.prune(
            terminalOlderThanMs: nowMs() - retentionMs,
            notificationsOlderThanMs: nowMs() - retentionMs
        )
        store.database.pruneSessions(
            staleCutoffMs: nowMs() - sessionStaleMs,
            hardCutoffMs: nowMs() - retentionMs,
            localHost: ProcessInfo.processInfo.hostName
        )
        if !dead.isEmpty || !superseded.isEmpty { store.refresh() }
    }

    // MARK: - Popover control

    @objc private func statusButtonClicked() {
        let event = NSApp.currentEvent
        let isSecondaryClick =
            event?.type == .rightMouseUp || (event?.modifierFlags.contains(.control) ?? false)
        if isSecondaryClick {
            showStatusMenu()
        } else {
            togglePopover()
        }
    }

    /// Right-click / control-click menu on the menu-bar icon, offering Quit.
    private func showStatusMenu() {
        let menu = NSMenu()
        menu.addItem(
            withTitle: "Quit Agent Hooks",
            action: #selector(NSApplication.terminate(_:)),
            keyEquivalent: "q"
        )
        // Attach the menu only for this click, then detach so a left-click still toggles the
        // popover instead of opening the menu.
        statusItem.menu = menu
        statusItem.button?.performClick(nil)
        statusItem.menu = nil
    }

    private func togglePopover() {
        if popover.isShown {
            popover.performClose(nil)
        } else {
            showPopover()
        }
    }

    private func showPopover() {
        guard let button = statusItem.button else { return }
        store.prepareForOpen()
        popover.show(relativeTo: button.bounds, of: button, preferredEdge: .minY)
        NSApp.activate(ignoringOtherApps: true)
    }

    // MARK: - Paths

    private static func defaultDatabasePath() -> String {
        let home = FileManager.default.homeDirectoryForCurrentUser
        return
            home
            .appendingPathComponent("Library/Application Support/agent-hooks/queue.db")
            .path
    }
}
