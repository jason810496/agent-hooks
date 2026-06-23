import AppKit
import SwiftUI

/// Presents notifications as top-right toast banners, independent of the menu-bar panel.
/// Banners stack downward from the top-right corner and auto-dismiss. Main-thread only.
final class ToastPresenter {
    private var windows: [NSWindow] = []
    private let width: CGFloat = 320
    private let margin: CGFloat = 14
    private let spacing: CGFloat = 8
    private let maxVisible = 4
    private let displaySeconds: TimeInterval = 6

    private enum Content {
        case single(AppNotification)
        case summary(Int)
    }

    func present(_ notifications: [AppNotification]) {
        guard !notifications.isEmpty else { return }
        let shown = notifications.prefix(maxVisible)
        for notification in shown { show(.single(notification)) }
        let overflow = notifications.count - shown.count
        if overflow > 0 { show(.summary(overflow)) }
    }

    private func show(_ content: Content) {
        let window = makeWindow()
        let close: () -> Void = { [weak self, weak window] in self?.dismiss(window) }
        let root: AnyView
        switch content {
        case .single(let notification):
            root = AnyView(ToastView(notification: notification, onClose: close))
        case .summary(let count):
            root = AnyView(ToastSummaryView(extra: count, onClose: close))
        }

        let hosting = NSHostingView(rootView: root)
        hosting.frame = NSRect(x: 0, y: 0, width: width, height: 1)
        hosting.layoutSubtreeIfNeeded()
        let height = max(56, hosting.fittingSize.height)
        window.setContentSize(NSSize(width: width, height: height))
        window.contentView = hosting

        windows.append(window)
        layout()
        window.orderFrontRegardless()

        Timer.scheduledTimer(withTimeInterval: displaySeconds, repeats: false) {
            [weak self, weak window] _ in
            self?.dismiss(window)
        }
    }

    private func dismiss(_ window: NSWindow?) {
        guard let window, let index = windows.firstIndex(of: window) else { return }
        windows.remove(at: index)
        window.orderOut(nil)
        layout()
    }

    private func layout() {
        guard let screen = NSScreen.main else { return }
        let frame = screen.visibleFrame
        var top = frame.maxY - margin
        for window in windows {
            let size = window.frame.size
            window.setFrameOrigin(NSPoint(x: frame.maxX - size.width - margin, y: top - size.height))
            top -= size.height + spacing
        }
    }

    private func makeWindow() -> NSWindow {
        let window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: width, height: 56),
            styleMask: [.borderless], backing: .buffered, defer: false
        )
        window.isReleasedWhenClosed = false
        window.isOpaque = false
        window.backgroundColor = .clear
        window.hasShadow = true
        window.level = .statusBar
        window.ignoresMouseEvents = false
        window.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .stationary]
        return window
    }
}

private struct ToastView: View {
    let notification: AppNotification
    let onClose: () -> Void

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: icon)
                .foregroundStyle(tint)
                .font(.title3)
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(.subheadline).bold().lineLimit(1)
                if !notification.message.isEmpty {
                    Text(notification.message)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(3)
                }
                if !repoName.isEmpty {
                    Text(repoName).font(.caption2).foregroundStyle(.tertiary)
                }
            }
            Spacer(minLength: 0)
            Button(action: onClose) {
                Image(systemName: "xmark").font(.caption2)
            }
            .buttonStyle(.plain)
            .foregroundStyle(.secondary)
        }
        .padding(12)
        .frame(width: 320, alignment: .leading)
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 12))
        .overlay(RoundedRectangle(cornerRadius: 12).stroke(Color.gray.opacity(0.2)))
        .contentShape(Rectangle())
        .onTapGesture(perform: onClose)
    }

    private var title: String { notification.title.isEmpty ? defaultTitle : notification.title }
    private var defaultTitle: String {
        switch notification.kind {
        case "stop": return "Finished"
        case "stop_failure": return "Error"
        default: return "Notification"
        }
    }
    private var repoName: String { (notification.queue as NSString).lastPathComponent }
    private var icon: String {
        switch notification.kind {
        case "stop": return "checkmark.circle.fill"
        case "stop_failure": return "exclamationmark.triangle.fill"
        default: return "bell.fill"
        }
    }
    private var tint: Color {
        switch notification.kind {
        case "stop": return .green
        case "stop_failure": return .red
        default: return .blue
        }
    }
}

private struct ToastSummaryView: View {
    let extra: Int
    let onClose: () -> Void

    var body: some View {
        HStack(spacing: 10) {
            Image(systemName: "bell.badge.fill").foregroundStyle(.blue)
            Text("+\(extra) more message\(extra == 1 ? "" : "s")").font(.subheadline)
            Spacer(minLength: 0)
            Button(action: onClose) {
                Image(systemName: "xmark").font(.caption2)
            }
            .buttonStyle(.plain)
            .foregroundStyle(.secondary)
        }
        .padding(12)
        .frame(width: 320, alignment: .leading)
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 12))
        .overlay(RoundedRectangle(cornerRadius: 12).stroke(Color.gray.opacity(0.2)))
        .contentShape(Rectangle())
        .onTapGesture(perform: onClose)
    }
}
