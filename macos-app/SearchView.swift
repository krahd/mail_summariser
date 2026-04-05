import SwiftUI

struct SearchView: View {
    @EnvironmentObject private var appState: AppState

    var body: some View {
        HSplitView {
            ScrollView {
                criteriaPanel
                    .frame(maxWidth: .infinity, alignment: .topLeading)
                    .padding(.vertical, 4)
                    .padding(.trailing, 10)
            }
            .frame(minWidth: 300, idealWidth: 320, maxWidth: 360)
            .scrollContentBackground(.hidden)

            VStack(alignment: .leading, spacing: 16) {
                summaryPanel
                messagesPanel
                    .frame(maxHeight: .infinity)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
        }
        .padding(4)
    }

    private var criteriaPanel: some View {
        VStack(alignment: .leading, spacing: 18) {
            BrandSectionTitle(
                eyebrow: "Search",
                title: "Search Criteria",
                subtitle: "Define the message slice before you create a digest."
            )

            VStack(spacing: 12) {
                TextField("Keyword", text: $appState.criteria.keyword)
                TextField("Raw search", text: $appState.criteria.rawSearch)
                TextField("Sender", text: $appState.criteria.sender)
                TextField("Recipient", text: $appState.criteria.recipient)
                TextField("Tag", text: $appState.criteria.tag)
            }
            .textFieldStyle(.roundedBorder)

            Divider()

            VStack(alignment: .leading, spacing: 10) {
                Toggle("Unread only", isOn: $appState.criteria.unreadOnly)
                Toggle("Read only", isOn: $appState.criteria.readOnly)
                Toggle("Combine conditions with AND", isOn: $appState.criteria.useAnd)
            }

            Divider()

            VStack(alignment: .leading, spacing: 10) {
                Text("Summary length")
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(BrandPalette.ink)

                HStack(spacing: 10) {
                    TextField(
                        "Length",
                        value: Binding(
                            get: { appState.summaryLength },
                            set: { appState.summaryLength = max(1, $0) }
                        ),
                        format: .number
                    )
                    .frame(width: 88)
                    .textFieldStyle(.roundedBorder)

                    Stepper("", value: Binding(
                        get: { appState.summaryLength },
                        set: { appState.summaryLength = max(1, $0) }
                    ), in: 1...Int.max)
                    .labelsHidden()

                    Spacer()

                    Text("\(appState.summaryLength)")
                        .font(.system(.body, design: .monospaced))
                        .foregroundStyle(BrandPalette.muted)
                }
            }

            Button("Create Summary") {
                Task { await getSummary() }
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.large)
            .keyboardShortcut(.return)
        }
        .brandPanel(fill: BrandPalette.panelStrong)
    }

    private var summaryPanel: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack(alignment: .top, spacing: 16) {
                BrandSectionTitle(
                    eyebrow: "Digest",
                    title: "Summary",
                    subtitle: appState.selectedJobId.isEmpty
                        ? "Run a summary to populate the digest and action toolbar."
                        : "Current job: \(appState.selectedJobId)"
                )

                Spacer()
                BrandStatusPill(text: appState.statusText)
            }

            TextEditor(text: $appState.currentSummary)
                .font(.system(.body, design: .monospaced))
                .frame(minHeight: 290)
                .padding(10)
                .background(
                    RoundedRectangle(cornerRadius: 16, style: .continuous)
                        .fill(BrandPalette.panelMuted)
                )
                .overlay(
                    RoundedRectangle(cornerRadius: 16, style: .continuous)
                        .stroke(BrandPalette.line, lineWidth: 1)
                )

            HStack(spacing: 10) {
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
        .brandPanel(fill: BrandPalette.panelStrong)
    }

    private var messagesPanel: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(alignment: .top) {
                BrandSectionTitle(
                    eyebrow: "Review",
                    title: "Messages",
                    subtitle: appState.currentMessages.isEmpty
                        ? "The current result set appears here after each summary run."
                        : "\(appState.currentMessages.count) messages in the current job."
                )
                Spacer()
            }

            if appState.currentMessages.isEmpty {
                ContentUnavailableView(
                    "No messages yet",
                    systemImage: "tray",
                    description: Text("Create a summary to populate the message list.")
                )
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                Table(appState.currentMessages) {
                    TableColumn("Date", value: \.date)
                    TableColumn("Sender", value: \.sender)
                    TableColumn("Subject", value: \.subject)
                }
                .frame(minHeight: 250, maxHeight: .infinity)
            }
        }
        .brandPanel(fill: BrandPalette.panelStrong)
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
