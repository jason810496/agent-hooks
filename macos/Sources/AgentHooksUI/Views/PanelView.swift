import AppKit
import SwiftUI

/// Root panel shown from the menu-bar popover. Switches between the Answers queue, the live
/// Sessions dashboard, and Settings; the active panel is owned by ``AppStore``.
struct PanelView: View {
    @EnvironmentObject var store: AppStore

    var body: some View {
        Group {
            switch store.activePanel {
            case .settings:
                SettingsView(onClose: { store.closeSettings() })
            case .sessions:
                chrome(title: "Sessions", subtitle: sessionsSubtitle) { SessionsView() }
            case .answers:
                chrome(title: "Agent Hooks", subtitle: answersSubtitle) { answersContent }
            }
        }
        .frame(width: 760, height: 520)
        .dynamicTypeSize(TextSizeOption.from(level: store.settings.textSizeLevel).dynamicTypeSize)
    }

    // MARK: - Shared chrome

    private func chrome<Content: View>(
        title: String, subtitle: String?, @ViewBuilder content: () -> Content
    ) -> some View {
        VStack(spacing: 0) {
            header(title: title, subtitle: subtitle)
            Divider()
            content()
        }
    }

    private func header(title: String, subtitle: String?) -> some View {
        HStack(spacing: 8) {
            Image(nsImage: BrandIcon.image(size: 20, template: false))
            Text(title).font(.headline)
            if let subtitle {
                Text(subtitle).font(.caption).foregroundStyle(.secondary)
            }
            Spacer()
            menu
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 10)
    }

    private var menu: some View {
        Menu {
            Button("Answers") { store.showPanel(.answers) }
            Button("Sessions") { store.showPanel(.sessions) }
            Divider()
            Button("Settings") { store.showPanel(.settings) }
            Divider()
            Button("Quit Agent Hooks") { NSApp.terminate(nil) }
                .keyboardShortcut("q")
        } label: {
            Image(systemName: "ellipsis.circle")
        }
        .menuStyle(.borderlessButton)
        .menuIndicator(.hidden)
        .fixedSize()
        .help("Menu")
    }

    private var answersSubtitle: String? {
        store.pendingCount > 0 ? "\(store.pendingCount) pending" : nil
    }

    private var sessionsSubtitle: String? {
        store.sessions.isEmpty ? nil : "\(store.sessions.count) shown"
    }

    // MARK: - Answers content

    private var answersContent: some View {
        Group {
            if store.queues.isEmpty {
                emptyState
            } else {
                ScrollView {
                    VStack(alignment: .leading, spacing: 18) {
                        ForEach(store.queues) { group in
                            QueueLaneView(group: group)
                        }
                    }
                    .padding(14)
                }
            }
        }
    }

    private var emptyState: some View {
        VStack(spacing: 8) {
            Image(systemName: "checkmark.circle")
                .font(.system(size: 32))
                .foregroundStyle(.secondary)
            Text("All caught up")
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}
