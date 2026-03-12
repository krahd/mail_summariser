import SwiftUI

struct SummaryView: View {
    @EnvironmentObject private var appState: AppState

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("Last Summary")
                .font(.title2)

            if appState.currentMessages.isEmpty {
                ContentUnavailableView("No summary yet", systemImage: "doc.text.magnifyingglass", description: Text("Create a summary in the Search tab."))
            } else {
                Text("Job ID: \(appState.selectedJobId)")
                    .font(.caption)
                    .foregroundStyle(.secondary)

                Table(appState.currentMessages) {
                    TableColumn("Date", value: \.date)
                    TableColumn("Sender", value: \.sender)
                    TableColumn("Subject", value: \.subject)
                }
                .frame(minHeight: 260)

                Text("Digest")
                    .font(.headline)

                ScrollView {
                    Text(appState.currentSummary)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .textSelection(.enabled)
                }
            }
        }
        .padding()
    }
}
