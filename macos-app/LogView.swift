import SwiftUI

struct LogView: View {
    @EnvironmentObject private var appState: AppState
    @State private var logs: [ActionLogItem] = []

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack {
                Text("Action Log")
                    .font(.title2)
                Spacer()
                Button("Refresh") {
                    Task { await loadLogs() }
                }
            }

            if logs.isEmpty {
                ContentUnavailableView("No log entries", systemImage: "list.bullet.rectangle")
            } else {
                Table(logs) {
                    TableColumn("Time", value: \.timestamp)
                    TableColumn("Action", value: \.action)
                    TableColumn("Status", value: \.status)
                    TableColumn("Details") { item in
                        Text(item.details)
                    }
                }
            }
        }
        .padding()
        .task {
            await loadLogs()
        }
    }

    private func loadLogs() async {
        do {
            logs = try await appState.bridge.get(path: "logs")
            appState.statusText = "Loaded \(logs.count) log entries"
        } catch {
            appState.statusText = "Failed to load logs: \(error.localizedDescription)"
        }
    }
}
