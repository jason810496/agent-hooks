import SwiftUI

/// Maps the persisted `textSizeLevel` (0...3) to a SwiftUI `DynamicTypeSize`. Using semantic
/// sizes keeps every element's relative scale while bumping the whole panel up a step at a time.
enum TextSizeOption: Int, CaseIterable, Identifiable {
    case standard = 0
    case medium = 1
    case large = 2
    case extraLarge = 3

    var id: Int { rawValue }

    var label: String {
        switch self {
        case .standard: return "Standard"
        case .medium: return "Medium"
        case .large: return "Large"
        case .extraLarge: return "Extra Large"
        }
    }

    var dynamicTypeSize: DynamicTypeSize {
        switch self {
        case .standard: return .large
        case .medium: return .xLarge
        case .large: return .xxLarge
        case .extraLarge: return .xxxLarge
        }
    }

    static func from(level: Int) -> TextSizeOption {
        TextSizeOption(rawValue: level) ?? .medium
    }
}

/// App preferences, persisted immediately to the shared `settings` table. Laid out as a native
/// grouped form so it reads as a standard macOS settings pane.
struct SettingsView: View {
    @EnvironmentObject var store: AppStore
    let onClose: () -> Void

    var body: some View {
        VStack(spacing: 0) {
            header
            Divider()
            Form {
                Section {
                    Picker("Text size", selection: textSizeBinding) {
                        ForEach(TextSizeOption.allCases) { option in
                            Text(option.label).tag(option)
                        }
                    }
                    .pickerStyle(.segmented)
                } header: {
                    Text("Appearance")
                } footer: {
                    Text("Scales every label in the panel together. Each element keeps its relative size.")
                        .foregroundStyle(.secondary)
                }

                Section {
                    Stepper(value: thresholdBinding, in: 1...99) {
                        LabeledContent("Surface after") {
                            Text("\(store.settings.surfaceThresholdCount) pending")
                        }
                    }
                    Stepper(value: quietBinding, in: 1...600, step: 5) {
                        LabeledContent("…or after quiet for") {
                            Text("\(store.settings.surfaceQuietSeconds)s")
                        }
                    }
                } header: {
                    Text("Auto-surface")
                } footer: {
                    Text("The panel pops open on its own once either threshold is reached.")
                        .foregroundStyle(.secondary)
                }

                Section {
                    Stepper(value: pollBinding, in: 100...5000, step: 100) {
                        LabeledContent("Poll interval") {
                            Text("\(store.settings.pollIntervalMs) ms")
                        }
                    }
                } header: {
                    Text("Performance")
                } footer: {
                    Text("How often the queue is checked. Restart the app to apply a new interval.")
                        .foregroundStyle(.secondary)
                }
            }
            .formStyle(.grouped)
        }
    }

    private var header: some View {
        ZStack {
            Text("Settings").font(.headline)
            HStack {
                Button(action: onClose) {
                    HStack(spacing: 4) {
                        Image(systemName: "chevron.left")
                        Text("Back")
                    }
                }
                .buttonStyle(.link)
                Spacer()
            }
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 10)
    }

    // MARK: - Bindings

    private var textSizeBinding: Binding<TextSizeOption> {
        Binding(
            get: { TextSizeOption.from(level: store.settings.textSizeLevel) },
            set: { option in store.updateSettings { $0.textSizeLevel = option.rawValue } }
        )
    }

    private var thresholdBinding: Binding<Int> {
        Binding(
            get: { store.settings.surfaceThresholdCount },
            set: { value in store.updateSettings { $0.surfaceThresholdCount = value } }
        )
    }

    private var quietBinding: Binding<Int> {
        Binding(
            get: { store.settings.surfaceQuietSeconds },
            set: { value in store.updateSettings { $0.surfaceQuietSeconds = value } }
        )
    }

    private var pollBinding: Binding<Int> {
        Binding(
            get: { store.settings.pollIntervalMs },
            set: { value in store.updateSettings { $0.pollIntervalMs = value } }
        )
    }
}
