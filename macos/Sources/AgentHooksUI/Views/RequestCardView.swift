import SwiftUI

/// One pending permission / AskUserQuestion card with its action affordances.
struct RequestCardView: View {
    let request: PermissionRequest
    let isActive: Bool
    @EnvironmentObject var store: AppStore

    /// Per-question selected option indices (AskUserQuestion only).
    @State private var selections: [Int: Set<Int>] = [:]
    /// Free-text correction / note typed by the user.
    @State private var correction: String = ""

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            header
            if !request.summary.isEmpty {
                ScrollView {
                    Text(request.summary)
                        .font(.system(.caption, design: .monospaced))
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .textSelection(.enabled)
                }
                .frame(maxHeight: 150)
            }
            Divider()
            actions
            if request.supportsFreeText {
                freeTextBar
            }
        }
        .padding(12)
        .frame(width: 340, alignment: .leading)
        .background(
            RoundedRectangle(cornerRadius: 10)
                .fill(Color(nsColor: .controlBackgroundColor))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 10)
                .stroke(isActive ? Color.accentColor : Color.gray.opacity(0.25),
                        lineWidth: isActive ? 2 : 1)
        )
    }

    private var header: some View {
        HStack(spacing: 6) {
            Text(request.toolName.isEmpty ? "Request" : request.toolName)
                .font(.subheadline)
                .bold()
            Spacer()
            Text(relativeAge(fromMs: request.createdAtMs))
                .font(.caption2)
                .foregroundStyle(.secondary)
        }
    }

    @ViewBuilder
    private var actions: some View {
        if request.kind == .askUserQuestion {
            questionForm
        } else {
            choiceButtons
        }
    }

    private var choiceButtons: some View {
        VStack(spacing: 6) {
            ForEach(request.choices) { choice in
                Button {
                    store.answer(request, choice: choice)
                } label: {
                    HStack {
                        if choice.suggestionIndex != nil {
                            Image(systemName: "lock.shield")
                        }
                        Text(choice.label)
                        Spacer()
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
                .buttonStyle(.bordered)
                .tint(tint(for: choice.button))
            }
            if !request.choices.contains(where: { $0.isDeny }) {
                Button {
                    store.deny(request)
                } label: {
                    Text("Deny").frame(maxWidth: .infinity, alignment: .leading)
                }
                .buttonStyle(.bordered)
                .tint(.red)
            }
        }
    }

    private var questionForm: some View {
        VStack(alignment: .leading, spacing: 10) {
            ForEach(request.questions) { question in
                VStack(alignment: .leading, spacing: 4) {
                    Text(question.header.isEmpty ? question.text : question.header)
                        .font(.caption)
                        .bold()
                    if !question.header.isEmpty && !question.text.isEmpty {
                        Text(question.text)
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                    ForEach(question.options) { option in
                        Button {
                            toggle(question, option)
                        } label: {
                            HStack(spacing: 6) {
                                Image(systemName: marker(question, option))
                                Text(option.label)
                                Spacer()
                            }
                            .frame(maxWidth: .infinity, alignment: .leading)
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
            HStack {
                Button { store.deny(request) } label: { Text("Cancel") }
                    .buttonStyle(.bordered)
                    .tint(.red)
                Spacer()
                Button { submit() } label: { Text("Submit") }
                    .buttonStyle(.borderedProminent)
                    .disabled(!allAnswered)
            }
        }
    }

    // MARK: - Free-text correction / note

    /// A text field plus a "Send instead" (deny + correction) action, and for AskUserQuestion an
    /// "Allow + note" (allow + extra context) action. Both feed the typed text back to the model.
    private var freeTextBar: some View {
        VStack(alignment: .leading, spacing: 6) {
            Divider()
            TextField("Correct or redirect the next step…", text: $correction, axis: .vertical)
                .textFieldStyle(.roundedBorder)
                .lineLimit(1...4)
                .font(.caption)
            HStack(spacing: 6) {
                Button {
                    store.sendCorrection(request, text: trimmedCorrection)
                } label: {
                    Label("Send instead", systemImage: "arrow.uturn.left")
                }
                .buttonStyle(.bordered)
                .tint(.orange)
                .disabled(trimmedCorrection.isEmpty)
                if request.supportsAllowNote {
                    Spacer()
                    Button {
                        store.allowWithNote(
                            request, answers: collectedAnswers(), text: trimmedCorrection
                        )
                    } label: {
                        Label("Allow + note", systemImage: "checkmark")
                    }
                    .buttonStyle(.bordered)
                    .tint(.green)
                    .disabled(trimmedCorrection.isEmpty || !allAnswered)
                }
            }
        }
    }

    private var trimmedCorrection: String {
        correction.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    // MARK: - AskUserQuestion helpers

    private func toggle(_ question: Question, _ option: QuestionOption) {
        var chosen = selections[question.index] ?? []
        if question.multiSelect {
            if chosen.contains(option.index) {
                chosen.remove(option.index)
            } else {
                chosen.insert(option.index)
            }
        } else {
            chosen = [option.index]
        }
        selections[question.index] = chosen
    }

    private func isSelected(_ question: Question, _ option: QuestionOption) -> Bool {
        (selections[question.index] ?? []).contains(option.index)
    }

    private func marker(_ question: Question, _ option: QuestionOption) -> String {
        let selected = isSelected(question, option)
        if question.multiSelect {
            return selected ? "checkmark.square.fill" : "square"
        }
        return selected ? "largecircle.fill.circle" : "circle"
    }

    private var allAnswered: Bool {
        request.questions.allSatisfy { !(selections[$0.index] ?? []).isEmpty }
    }

    /// Map the current per-question selections to answer text keyed by question.
    private func collectedAnswers() -> [String: String] {
        var answers: [String: String] = [:]
        for question in request.questions {
            let chosen = selections[question.index] ?? []
            let labels = question.options
                .filter { chosen.contains($0.index) }
                .map { $0.label }
            answers[question.text] = labels.joined(separator: ", ")
        }
        return answers
    }

    private func submit() {
        store.answerQuestions(request, answers: collectedAnswers())
    }

    private func tint(for button: String) -> Color {
        switch button {
        case "Deny": return .red
        case "Always Allow": return .green
        default: return .blue
        }
    }
}
