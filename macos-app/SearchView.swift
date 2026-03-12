import SwiftUI

struct SearchView: View {
    @EnvironmentObject private var appState: AppState

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack {
                Text("Mail Summary Builder")
                    .font(.title2)
                Spacer()
                Text(appState.statusText)
                    .foregroundStyle(.secondary)
            }

            Form {
                TextField("Keyword", text: $appState.criteria.keyword)
                TextField("Raw search", text: $appState.criteria.rawSearch)
                TextField("Sender", text: $appState.criteria.sender)
                TextField("Recipient", text: $appState.criteria.recipient)
                TextField("Tag", text: $appState.criteria.tag)
                Toggle("Unread only", isOn: $appState.criteria.unreadOnly)
                Toggle("Read only", isOn: $appState.criteria.readOnly)
                Toggle("Combine conditions with AND", isOn: $appState.criteria.useAnd)

                HStack {
                    Text("Summary length")
                    Slider(value: $appState.summaryLength, in: 1...10, step: 1)
                    Text("\(Int(appState.summaryLength))")
                        .monospacedDigit()
                        .frame(width: 28)
                }
            }
            .formStyle(.grouped)

            HStack {
                Button("Get Summary") {
                    Task { await getSummary() }
                }
                .keyboardShortcut(.return)

                Button("Mark Summarised Emails as Read") {
                    Task { await performJobAction(path: "actions/mark-read") }
                }
                .disabled(appState.selectedJobId.isEmpty)

                Button("Add ‘summarised’ Tag") {
                    Task { await performJobAction(path: "actions/tag-summarised") }
                }
                .disabled(appState.selectedJobId.isEmpty)

                Button("Email Summary") {
                    Task { await performJobAction(path: "actions/email-summary") }
                }
                .disabled(appState.selectedJobId.isEmpty)

                Button("Undo Last Action") {
                    Task { await undoLastAction() }
                }
            }

            Text("Summary")
                .font(.headline)

            TextEditor(text: $appState.currentSummary)
                .font(.system(.body, design: .monospaced))
                .frame(minHeight: 260)
                .overlay {
                    RoundedRectangle(cornerRadius: 8)
                        .stroke(Color.gray.opacity(0.25), lineWidth: 1)
                }
        }
        .padding()
    }

    private func getSummary() async {
        do {
            let request = SummaryRequest(criteria: appState.criteria, summaryLength: Int(appState.summaryLength))
            let response: SummaryResponse = try await appState.bridge.postJSON(path: "summaries", body: request)
            appState.currentSummary = response.summary
            appState.currentMessages = response.messages
            appState.selectedJobId = response.jobId
            appState.statusText = "Created summary for \(response.messages.count) messages"
        } catch {
            appState.statusText = "Summary failed: \(error.localizedDescription)"
        }
    }

    private func performJobAction(path: String) async {
        guard !appState.selectedJobId.isEmpty else { return }
        do {
            let body = ["jobId": appState.selectedJobId]
            let response: EmptyResponse = try await appState.bridge.postJSON(path: path, body: body)
            appState.statusText = response.status ?? "OK"
        } catch {
            appState.statusText = "Action failed: \(error.localizedDescription)"
        }
    }

    private func undoLastAction() async {
        do {
            let response: EmptyResponse = try await appState.bridge.postJSON(path: "actions/undo", body: [String: String]())
            appState.statusText = response.status ?? "Undo complete"
        } catch {
            appState.statusText = "Undo failed: \(error.localizedDescription)"
        }
    }
}
