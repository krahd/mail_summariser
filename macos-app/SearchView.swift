import SwiftUI

struct SearchView: View {
    @EnvironmentObject private var appState: AppState

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                HStack(alignment: .top, spacing: 20) {
                    criteriaPanel
                        .frame(maxWidth: 360, alignment: .top)
                    summaryPanel
                }

                messagesPanel
            }
            .padding(12)
        }
        .scrollContentBackground(.hidden)
    }

    private var criteriaPanel: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("Search Criteria")
                .font(.system(size: 22, weight: .bold, design: .rounded))
                .foregroundStyle(BrandPalette.ink)

            VStack(spacing: 12) {
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
                        .foregroundStyle(BrandPalette.muted)
                    Spacer()
                    TextField(
                        "Length",
                        value: Binding(
                            get: { appState.summaryLength },
                            set: { appState.summaryLength = max(1, $0) }
                        ),
                        format: .number
                    )
                    .frame(width: 90)
                    .textFieldStyle(.roundedBorder)
                    Button("-") {
                        appState.summaryLength = max(1, appState.summaryLength - 1)
                    }
                    .buttonStyle(.bordered)
                    Button("+") {
                        appState.summaryLength += 1
                    }
                    .buttonStyle(.borderedProminent)
                    Text("\(appState.summaryLength)")
                        .font(.body.monospacedDigit())
                        .frame(minWidth: 32, alignment: .trailing)
                }
            }

            Button("Create Summary") {
                Task { await getSummary() }
            }
            .buttonStyle(.borderedProminent)
            .tint(BrandPalette.accent)
            .keyboardShortcut(.return)
        }
        .brandPanel()
    }

    private var summaryPanel: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 6) {
                    Text("Summary")
                        .font(.system(size: 22, weight: .bold, design: .rounded))
                        .foregroundStyle(BrandPalette.ink)
                    Text(appState.selectedJobId.isEmpty ? "No job yet" : "Current job: \(appState.selectedJobId)")
                        .font(.caption)
                        .foregroundStyle(BrandPalette.muted)
                }
                Spacer()
                BrandStatusPill(text: appState.statusText)
            }

            TextEditor(text: $appState.currentSummary)
                .font(.system(.body, design: .monospaced))
                .frame(minHeight: 260)
                .padding(12)
                .background(
                    RoundedRectangle(cornerRadius: 18, style: .continuous)
                        .fill(Color.white.opacity(0.82))
                )
                .overlay(
                    RoundedRectangle(cornerRadius: 18, style: .continuous)
                        .stroke(BrandPalette.line, lineWidth: 1)
                )

            HStack {
                Button("Mark Read") {
                    Task { await performJobAction(path: "actions/mark-read") }
                }
                .disabled(appState.selectedJobId.isEmpty)
                .buttonStyle(.bordered)

                Button("Tag Summarised") {
                    Task { await performJobAction(path: "actions/tag-summarised") }
                }
                .disabled(appState.selectedJobId.isEmpty)
                .buttonStyle(.bordered)

                Button("Email Summary") {
                    Task { await performJobAction(path: "actions/email-summary") }
                }
                .disabled(appState.selectedJobId.isEmpty)
                .buttonStyle(.bordered)

                Spacer()

                Button("Undo Last Action") {
                    Task { await undoLastAction() }
                }
                .buttonStyle(.borderedProminent)
                .tint(BrandPalette.accentWarm)
            }
        }
        .brandPanel()
    }

    private var messagesPanel: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("Messages")
                .font(.system(size: 22, weight: .bold, design: .rounded))
                .foregroundStyle(BrandPalette.ink)

            if appState.currentMessages.isEmpty {
                ContentUnavailableView(
                    "No messages yet",
                    systemImage: "tray",
                    description: Text("Create a summary to populate the message list.")
                )
            } else {
                Table(appState.currentMessages) {
                    TableColumn("Date", value: \.date)
                    TableColumn("Sender", value: \.sender)
                    TableColumn("Subject", value: \.subject)
                }
                .frame(minHeight: 240)
            }
        }
        .brandPanel()
    }

    private func getSummary() async {
        do {
            let request = SummaryRequest(criteria: appState.criteria, summaryLength: max(1, appState.summaryLength))
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
