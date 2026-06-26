import AppKit
import SwiftUI

/// Live dashboard of Claude Code / Codex sessions: one row each, ordered by liveness
/// (green → yellow → gray), with a TUI-style current/last tool line and a ticking timer.
struct SessionsView: View {
    @EnvironmentObject var store: AppStore

    var body: some View {
        if store.sessions.isEmpty {
            emptyState
        } else {
            ScrollView {
                VStack(alignment: .leading, spacing: 10) {
                    ForEach(store.sessions) { session in
                        SessionRowView(session: session)
                    }
                }
                .padding(14)
            }
        }
    }

    private var emptyState: some View {
        VStack(spacing: 8) {
            Image(systemName: "circle.dashed")
                .font(.system(size: 32))
                .foregroundStyle(.secondary)
            Text("No active sessions")
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

/// A single session row: status dot, repo + model, current tool call + output, and timer.
struct SessionRowView: View {
    let session: Session

    var body: some View {
        let band = session.band(now: nowMs(), localHost: ProcessInfo.processInfo.hostName)
        return VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 8) {
                Circle()
                    .fill(dotColor(band))
                    .frame(width: 10, height: 10)
                Text(session.displayName)
                    .font(.subheadline).bold()
                    .lineLimit(1)
                if !session.model.isEmpty {
                    Text(session.model)
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }
                Text("pid \(session.pid)")
                    .font(.caption2.monospacedDigit())
                    .foregroundStyle(.secondary)
                Spacer()
                timer(band)
            }
            statusBlock(band)
        }
        .padding(10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(RoundedRectangle(cornerRadius: 10).fill(Color.gray.opacity(0.08)))
        .overlay(
            RoundedRectangle(cornerRadius: 10).stroke(Color.gray.opacity(0.2), lineWidth: 1)
        )
    }

    @ViewBuilder
    private func statusBlock(_ band: SessionBand) -> some View {
        if session.failed, !session.errorText.isEmpty {
            Text(session.errorText)
                .font(.system(.caption, design: .monospaced))
                .foregroundStyle(.red)
                .lineLimit(3)
        }
        if let tool = session.tail?.toolName, !tool.isEmpty {
            let summary = session.tail?.toolSummary ?? ""
            Text("⏺ \(tool)\(summary.isEmpty ? "" : "(\(summary))")")
                .font(.system(.caption, design: .monospaced))
                .lineLimit(2)
            if let output = session.tail?.outputTail, !output.isEmpty,
                session.tail?.toolInFlight != true {
                Text("⎿ \(output)")
                    .font(.system(.caption2, design: .monospaced))
                    .foregroundStyle(.secondary)
                    .lineLimit(maxOutputLines)
            }
        } else if let message = session.tail?.lastMessage, !message.isEmpty {
            Text(message)
                .font(.caption)
                .foregroundStyle(.secondary)
                .lineLimit(2)
        }
    }

    private var maxOutputLines: Int { 6 }

    @ViewBuilder
    private func timer(_ band: SessionBand) -> some View {
        if band == .working, let started = roundStart {
            Label(formatDuration(ms: nowMs() - started), systemImage: "circle.fill")
                .labelStyle(.titleOnly)
                .font(.caption.monospacedDigit())
                .foregroundStyle(.secondary)
        } else if let last = session.lastRoundMs, last > 0 {
            Text("ran \(formatDuration(ms: last))")
                .font(.caption.monospacedDigit())
                .foregroundStyle(.secondary)
        }
    }

    /// Prefer the round start; fall back to the in-flight tool's start when no round is recorded.
    private var roundStart: Int64? {
        session.roundStartedMs ?? session.tail?.toolStartedMs
    }

    private func dotColor(_ band: SessionBand) -> Color {
        if session.failed { return .red }
        switch band {
        case .working: return .green
        case .idle: return .yellow
        case .dead: return .gray
        }
    }
}
