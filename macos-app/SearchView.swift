import SwiftUI

struct SearchView: View {
    @EnvironmentObject private var appState: AppState

    private struct MailboxDisplay {
        let name: String
        let address: String
    }

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

            VStack(alignment: .leading, spacing: 14) {
                summaryPanel
                messagesPanel
                    .frame(maxHeight: .infinity)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
        }
        .padding(4)
    }

    private var selectedMessageBinding: Binding<String?> {
        Binding(
            get: { appState.selectedMessageId },
            set: { newValue in
                Task { await appState.selectMessage(newValue) }
            }
        )
    }

    private var selectedMessageListItem: MessageItem? {
        guard let selectedMessageId = appState.selectedMessageId else {
            return nil
        }
        return appState.currentMessages.first(where: { $0.id == selectedMessageId })
    }

    private var hasSelectedMessage: Bool {
        appState.selectedMessageId != nil
    }

    private var senderMailboxDisplay: MailboxDisplay {
        guard hasSelectedMessage else {
            return MailboxDisplay(name: "", address: "")
        }

        return mailboxDisplay(
            from: appState.selectedMessageDetail?.sender ?? selectedMessageListItem?.sender,
            fallbackName: appState.isLoadingSelectedMessage ? "Loading sender" : "",
            fallbackAddress: appState.isLoadingSelectedMessage ? "Loading sender" : ""
        )
    }

    private var recipientMailboxDisplay: MailboxDisplay {
        guard hasSelectedMessage else {
            return MailboxDisplay(name: "", address: "")
        }

        return mailboxDisplay(
            from: appState.selectedMessageDetail?.recipient,
            fallbackName: appState.isLoadingSelectedMessage ? "Loading recipient" : "",
            fallbackAddress: appState.isLoadingSelectedMessage ? "Loading recipient" : ""
        )
    }

    private var messageDetailSubject: String {
        appState.selectedMessageDetail?.subject ?? selectedMessageListItem?.subject ?? "No mail selected"
    }

    private var messageDetailDate: String {
        appState.selectedMessageDetail?.date ?? selectedMessageListItem?.date ?? ""
    }

    private var messageDetailBody: String {
        guard hasSelectedMessage else {
            return ""
        }

        if let detail = appState.selectedMessageDetail {
            return detail.body.isEmpty ? "This message has no plain-text body." : detail.body
        }
        if appState.isLoadingSelectedMessage {
            return "Loading message body..."
        }
        if !appState.selectedMessageErrorText.isEmpty {
            return "Could not load this message: \(appState.selectedMessageErrorText)"
        }
        return ""
    }

    private var messageDetailBodyColor: Color {
        appState.selectedMessageErrorText.isEmpty ? BrandPalette.ink : BrandPalette.accentWarm
    }

    private func mailboxDisplay(from rawValue: String?, fallbackName: String, fallbackAddress: String) -> MailboxDisplay {
        let trimmed = rawValue?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        if trimmed.isEmpty {
            return MailboxDisplay(name: fallbackName, address: fallbackAddress)
        }

        if let start = trimmed.lastIndex(of: "<"), let end = trimmed.lastIndex(of: ">"), start < end {
            let name = trimmed[..<start]
                .trimmingCharacters(in: .whitespacesAndNewlines)
                .trimmingCharacters(in: CharacterSet(charactersIn: "\""))
            let address = trimmed[trimmed.index(after: start)..<end].trimmingCharacters(in: .whitespacesAndNewlines)
            if !address.isEmpty {
                return MailboxDisplay(
                    name: name.isEmpty ? fallbackMailboxName(from: address) : name,
                    address: address
                )
            }
        }

        if trimmed.contains("@") {
            return MailboxDisplay(name: fallbackMailboxName(from: trimmed), address: trimmed)
        }

        return MailboxDisplay(name: trimmed, address: trimmed)
    }

    private func fallbackMailboxName(from address: String) -> String {
        let localPart = address.split(separator: "@", maxSplits: 1).first.map(String.init) ?? address
        let separators = CharacterSet(charactersIn: "._+- ")
        let words = localPart
            .components(separatedBy: separators)
            .filter { !$0.isEmpty }
            .map { word in
                word.prefix(1).uppercased() + word.dropFirst().lowercased()
            }
        let candidate = words.joined(separator: " ")
        return candidate.isEmpty ? address : candidate
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
        VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .top, spacing: 12) {
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
                .font(.subheadline)
                .frame(minHeight: 290)
                .padding(8)
                .background(
                    RoundedRectangle(cornerRadius: 16, style: .continuous)
                        .fill(BrandPalette.panelMuted)
                )
                .overlay(
                    RoundedRectangle(cornerRadius: 16, style: .continuous)
                        .stroke(BrandPalette.line, lineWidth: 1)
                )

            HStack(spacing: 8) {
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
        .brandPanel(padding: 14, fill: BrandPalette.panelStrong)
    }

    private var messagesPanel: some View {
        VStack(alignment: .leading, spacing: 12) {
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
                HSplitView {
                    Table(appState.currentMessages, selection: selectedMessageBinding) {
                        TableColumn("Date", value: \.date)
                        TableColumn("Sender", value: \.sender)
                        TableColumn("Subject", value: \.subject)
                    }
                    .frame(minWidth: 340, idealWidth: 400, maxWidth: .infinity, maxHeight: .infinity)

                    messageDetailPanel
                        .frame(minWidth: 320, maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
                }
                .frame(minHeight: 250, maxHeight: .infinity)
            }
        }
        .brandPanel(fill: BrandPalette.panelStrong)
    }

    private var messageDetailPanel: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .top, spacing: 8) {
                VStack(alignment: .leading, spacing: 2) {
                    Text("Selected Mail")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(BrandPalette.muted)
                        .textCase(.uppercase)

                    Text(messageDetailSubject)
                        .font(.headline.weight(.semibold))
                        .foregroundStyle(BrandPalette.ink)
                        .lineLimit(3)
                }

                Spacer()

                if !messageDetailDate.isEmpty {
                    Text(messageDetailDate)
                        .font(.footnote)
                        .foregroundStyle(BrandPalette.muted)
                        .multilineTextAlignment(.trailing)
                }
            }

            if hasSelectedMessage {
                HStack(spacing: 6) {
                    messageMetaCard(title: "From", mailbox: senderMailboxDisplay)
                    messageMetaCard(title: "To", mailbox: recipientMailboxDisplay)
                }

                ScrollView {
                    Text(messageDetailBody)
                        .font(.subheadline)
                        .foregroundStyle(messageDetailBodyColor)
                        .frame(maxWidth: .infinity, alignment: .topLeading)
                        .textSelection(.enabled)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
                .padding(8)
                .background(
                    RoundedRectangle(cornerRadius: 16, style: .continuous)
                        .fill(BrandPalette.panelMuted)
                )
                .overlay(
                    RoundedRectangle(cornerRadius: 16, style: .continuous)
                        .stroke(BrandPalette.line, lineWidth: 1)
                )
            } else {
                Spacer(minLength: 0)
            }
        }
        .padding(10)
        .background(
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .fill(BrandPalette.panelMuted)
        )
        .overlay(
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .stroke(BrandPalette.line, lineWidth: 1)
        )
    }

    private func messageMetaCard(title: String, mailbox: MailboxDisplay) -> some View {
        VStack(alignment: .leading, spacing: 1) {
            Text(title)
                .font(.caption2.weight(.semibold))
                .foregroundStyle(BrandPalette.muted)
                .textCase(.uppercase)

            Text(mailbox.name)
                .font(.subheadline)
                .foregroundStyle(BrandPalette.ink)
                .frame(maxWidth: .infinity, alignment: .leading)

            Text(mailbox.address)
                .font(.subheadline)
                .foregroundStyle(BrandPalette.ink)
                .lineLimit(2)
                .frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 5)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .fill(.white.opacity(0.7))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .stroke(BrandPalette.line, lineWidth: 1)
        )
    }

    private func getSummary() async {
        do {
            let request = SummaryRequest(criteria: appState.criteria, summaryLength: max(1, appState.summaryLength))
            let response: SummaryResponse = try await appState.bridge.postJSON(path: "summaries", body: request)
            appState.currentSummary = response.summary
            appState.currentMessages = response.messages
            appState.selectedJobId = response.jobId
            appState.statusText = "Created summary for \(response.messages.count) messages"
            await appState.selectMessage(response.messages.first?.id)
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
