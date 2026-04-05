import SwiftUI

struct LogView: View {
    @EnvironmentObject private var appState: AppState
    @State private var logs: [ActionLogItem] = []

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack(alignment: .top, spacing: 16) {
                BrandSectionTitle(
                    eyebrow: "History",
                    title: "Action Log",
                    subtitle: "Review action history and unwind reversible steps without leaving the workspace."
                )

                Spacer()

                HStack(spacing: 10) {
                    BrandStatusPill(text: logs.isEmpty ? "No entries" : "\(logs.count) entries")

                    Button("Refresh") {
                        Task { await loadLogs() }
                    }
                    .buttonStyle(.borderedProminent)
                }
            }

            VStack(alignment: .leading, spacing: 14) {
                if logs.isEmpty {
                    ContentUnavailableView("No log entries", systemImage: "list.bullet.rectangle")
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                } else {
                    Table(logs) {
                        TableColumn("Time", value: \.timestamp)
                        TableColumn("Action", value: \.action)
                        TableColumn("Status", value: \.status)
                        TableColumn("Details") { item in
                            Text(item.details)
                        }
                        TableColumn("Undo") { item in
                            if item.undoable == true {
                                Button("Undo") {
                                    Task { await undoLog(item) }
                                }
                                .buttonStyle(.bordered)
                                .controlSize(.small)
                            } else {
                                Text("Final")
                                    .foregroundStyle(.secondary)
                            }
                        }
                    }
                    .frame(minHeight: 420, maxHeight: .infinity)
                }
            }
            .brandPanel(fill: BrandPalette.panelStrong)
        }
        .padding(4)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
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

    private func undoLog(_ item: ActionLogItem) async {
        do {
            let response: EmptyResponse = try await appState.bridge.postJSON(
                path: "actions/undo/logs/\(item.id)",
                body: [String: String]()
            )
            appState.statusText = response.status ?? "Undo complete"
            await loadLogs()
        } catch {
            appState.statusText = "Undo failed: \(error.localizedDescription)"
        }
    }
}
