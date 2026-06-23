import AppKit
import SwiftUI

/// Root panel shown from the menu-bar popover.
struct PanelView: View {
    @EnvironmentObject var store: AppStore
    @State private var showSettings = false

    var body: some View {
        Group {
            if showSettings {
                SettingsView(onClose: { showSettings = false })
            } else {
                main
            }
        }
        .frame(width: 760, height: 520)
        .dynamicTypeSize(TextSizeOption.from(level: store.settings.textSizeLevel).dynamicTypeSize)
    }

    private var main: some View {
        VStack(spacing: 0) {
            header
            Divider()
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

    private var header: some View {
        HStack(spacing: 8) {
            Image(nsImage: BrandIcon.image(size: 20, template: false))
            Text("Agent Hooks").font(.headline)
            if store.pendingCount > 0 {
                Text("\(store.pendingCount) pending")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Spacer()
            Menu {
                Button("Settings") { showSettings = true }
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
        .padding(.horizontal, 14)
        .padding(.vertical, 10)
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
