import SwiftUI

/// One repo/worktree lane: a horizontal strip of cards, leftmost = next to answer.
struct QueueLaneView: View {
    let group: QueueGroup

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 6) {
                Image(systemName: "folder")
                    .foregroundStyle(.secondary)
                Text(group.displayName)
                    .font(.subheadline)
                    .bold()
                Text("\(group.requests.count)")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(alignment: .top, spacing: 12) {
                    ForEach(Array(group.requests.enumerated()), id: \.element.id) { index, request in
                        RequestCardView(request: request, isActive: index == 0)
                    }
                }
                .padding(.bottom, 4)
            }
        }
    }
}
