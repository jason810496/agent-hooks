import SwiftUI

/// One pending permission / AskUserQuestion card with its action affordances.
struct RequestCardView: View {
    let request: PermissionRequest
    let isActive: Bool
    @EnvironmentObject var store: AppStore

    /// Per-question selected option indices for native question cards.
    @State private var selections: [Int: Set<Int>] = [:]
    /// Codex questions may add a free-form "Other" answer alongside their choices.
    @State private var otherSelections: Set<Int> = []
    @State private var otherAnswers: [Int: String] = [:]
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
        if request.kind == .askUserQuestion || request.kind == .codexUserInput {
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
                            HStack(alignment: .top, spacing: 6) {
                                Image(systemName: marker(question, option))
                                VStack(alignment: .leading, spacing: 1) {
                                    Text(option.label)
                                    if !option.detail.isEmpty {
                                        Text(option.detail)
                                            .font(.caption2)
                                            .foregroundStyle(.secondary)
                                    }
                                }
                                Spacer(minLength: 0)
                            }
                            .frame(maxWidth: .infinity, alignment: .leading)
                        }
                        .buttonStyle(.plain)
                    }
                    if question.allowsOther {
                        otherAnswerField(question)
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
        otherSelections.remove(question.index)
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
        request.questions.allSatisfy { question in
            if !(selections[question.index] ?? []).isEmpty { return true }
            return otherSelections.contains(question.index)
                && !trimmedOtherAnswer(for: question).isEmpty
        }
    }

    /// Map the current per-question selections to answer text keyed by question.
    private func collectedAnswers() -> [String: String] {
        var answers: [String: String] = [:]
        for question in request.questions {
            let chosen = selections[question.index] ?? []
            let labels = question.options
                .filter { chosen.contains($0.index) }
                .map { $0.label }
            answers[question.answerKey] = labels.joined(separator: ", ")
        }
        return answers
    }

    private func submit() {
        guard let answersJSON = encodedAnswers() else { return }
        store.answerQuestions(request, answersJSON: answersJSON)
    }

    @ViewBuilder
    private func otherAnswerField(_ question: Question) -> some View {
        Button {
            selectOther(question)
        } label: {
            HStack(spacing: 6) {
                Image(
                    systemName: otherSelections.contains(question.index)
                        ? "largecircle.fill.circle" : "circle"
                )
                Text(question.options.isEmpty ? "Answer" : "Other")
                Spacer()
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .buttonStyle(.plain)

        if otherSelections.contains(question.index) {
            Group {
                if question.isSecret {
                    SecureField("Type your answer…", text: otherAnswerBinding(question))
                } else {
                    TextField(
                        "Type your answer…", text: otherAnswerBinding(question), axis: .vertical
                    )
                    .lineLimit(1...3)
                }
            }
            .textFieldStyle(.roundedBorder)
            .font(.caption)
        }
    }

    private func selectOther(_ question: Question) {
        selections[question.index] = []
        otherSelections.insert(question.index)
    }

    private func otherAnswerBinding(_ question: Question) -> Binding<String> {
        Binding(
            get: { otherAnswers[question.index] ?? "" },
            set: { value in
                otherAnswers[question.index] = value
                otherSelections.insert(question.index)
                selections[question.index] = []
            }
        )
    }

    private func trimmedOtherAnswer(for question: Question) -> String {
        (otherAnswers[question.index] ?? "")
            .trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private func answerValues(for question: Question) -> [String] {
        if otherSelections.contains(question.index) {
            let answer = trimmedOtherAnswer(for: question)
            return answer.isEmpty ? [] : [answer]
        }
        let chosen = selections[question.index] ?? []
        return question.options.filter { chosen.contains($0.index) }.map(\.label)
    }

    private func encodedAnswers() -> String? {
        if request.kind == .codexUserInput {
            var answers: [String: [String: [String]]] = [:]
            for question in request.questions {
                answers[question.answerKey] = ["answers": answerValues(for: question)]
            }
            return encodeJSON(answers)
        }
        return encodeJSON(collectedAnswers())
    }

    private func tint(for button: String) -> Color {
        switch button {
        case "Deny": return .red
        case "Always Allow": return .green
        default: return .blue
        }
    }
}
