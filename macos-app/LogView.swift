import SwiftUI
import AppKit

struct LogView: View {
    @EnvironmentObject private var appState: AppState
    @State private var logs: [ActionLogItem] = []
    @State private var errorDetailText: String? = nil
    @State private var showErrorDetail: Bool = false
    @State private var errorViewMode: ErrorViewMode = .pretty

    private enum ErrorViewMode: String, CaseIterable, Identifiable {
        case pretty = "Pretty"
        case raw = "Raw"
        var id: String { rawValue }
    }

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

            if let detail = errorDetailText {
                VStack(alignment: .leading, spacing: 8) {
                    Divider()
                    HStack {
                        Text("Error details")
                            .font(.headline)
                        Spacer()
                        Button(showErrorDetail ? "Hide details" : "Show details") {
                            withAnimation { showErrorDetail.toggle() }
                        }
                        .buttonStyle(.bordered)
                        .controlSize(.small)
                    }

                        if showErrorDetail {
                            // Controls: pretty/raw view + copy/save actions
                            HStack {
                                Picker("", selection: $errorViewMode) {
                                    ForEach(ErrorViewMode.allCases) { mode in
                                        Text(mode.rawValue).tag(mode)
                                    }
                                }
                                .pickerStyle(.segmented)
                                .frame(width: 220)

                                Spacer()

                                HStack(spacing: 8) {
                                    Button(action: {
                                        copyToPasteboard(formattedErrorText(detail))
                                    }) {
                                        Label("Copy", systemImage: "doc.on.doc")
                                    }
                                    .buttonStyle(.bordered)

                                    Button(action: {
                                        copyWithTimestamp(detail)
                                    }) {
                                        Label("Copy+Time", systemImage: "clock")
                                    }
                                    .buttonStyle(.bordered)

                                    Button(action: {
                                        copyWithMetadata(detail)
                                    }) {
                                        Label("Copy+Meta", systemImage: "doc.on.clipboard")
                                    }
                                    .buttonStyle(.bordered)

                                    Button(action: {
                                        exportErrorAsJSON(detail)
                                    }) {
                                        Label("Export JSON", systemImage: "square.and.arrow.up")
                                    }
                                    .buttonStyle(.bordered)

                                    Button(action: {
                                        saveErrorViaSavePanel(formattedErrorText(detail))
                                    }) {
                                        Label("Save As…", systemImage: "square.and.arrow.down")
                                    }
                                    .buttonStyle(.bordered)

                                    Button(action: {
                                        saveErrorToDownloads(formattedErrorText(detail))
                                    }) {
                                        Label("Save", systemImage: "square.and.arrow.down.on.square")
                                    }
                                    .buttonStyle(.bordered)
                                }
                            }

                            ScrollView {
                                Text(formattedErrorText(detail))
                                    .font(.system(.body, design: .monospaced))
                                    .textSelection(.enabled)
                                    .padding(6)
                                    .frame(maxWidth: .infinity, alignment: .leading)
                            }
                            .frame(maxHeight: 220)
                        }
                }
                .padding(.top, 8)
                .brandPanel(fill: BrandPalette.panelMuted)
            }
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
            errorDetailText = nil
        } catch {
            appState.statusText = "Failed to load logs: \(userFriendlyMessage(error))"
            errorDetailText = String(describing: error)
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
            errorDetailText = nil
        } catch {
            appState.statusText = "Undo failed: \(userFriendlyMessage(error))"
            errorDetailText = String(describing: error)
        }
    }

    private func formattedErrorText(_ raw: String) -> String {
        if errorViewMode == .raw { return raw }
        guard let data = raw.data(using: .utf8) else { return raw }
        do {
            let obj = try JSONSerialization.jsonObject(with: data, options: [])
            let pretty = try JSONSerialization.data(withJSONObject: obj, options: [.prettyPrinted])
            if let s = String(data: pretty, encoding: .utf8) {
                return s
            }
        } catch {
            // Not JSON or failed to pretty print; fall through
        }
        return raw
    }

    private func copyToPasteboard(_ text: String) {
        let pb = NSPasteboard.general
        pb.clearContents()
        pb.setString(text, forType: .string)
        appState.statusText = "Copied error details to clipboard"
    }

    private func saveErrorToDownloads(_ text: String) {
        do {
            let fm = FileManager.default
            let downloads = try fm.url(for: .downloadsDirectory, in: .userDomainMask, appropriateFor: nil, create: false)
            let formatter = ISO8601DateFormatter()
            let stamp = formatter.string(from: Date()).replacingOccurrences(of: ":", with: "-")
            let filename = "mail_summariser_error_\(stamp).txt"
            let url = downloads.appendingPathComponent(filename)
            try text.write(to: url, atomically: true, encoding: .utf8)
            appState.statusText = "Saved error to \(filename)"
        } catch {
            appState.statusText = "Failed to save error: \(error.localizedDescription)"
        }
    }

    private func metadataForError(_ raw: String) -> [String: Any] {
        let formatter = ISO8601DateFormatter()
        return [
            "timestamp": formatter.string(from: Date()),
            "baseURL": appState.bridge.baseURLString,
            "statusText": appState.statusText,
            "logsCount": logs.count,
            "error": raw
        ]
    }

    private func errorJSONWithMetadata(_ raw: String) -> String {
        let dict = metadataForError(raw)
        if JSONSerialization.isValidJSONObject(dict), let data = try? JSONSerialization.data(withJSONObject: dict, options: [.prettyPrinted]), let s = String(data: data, encoding: .utf8) {
            return s
        }
        return raw
    }

    private func copyWithMetadata(_ raw: String) {
        let json = errorJSONWithMetadata(raw)
        copyToPasteboard(json)
        appState.statusText = "Copied error + metadata to clipboard"
    }

    private func saveErrorViaSavePanel(_ text: String) {
        let panel = NSSavePanel()
        panel.canCreateDirectories = true
        if #available(macOS 12.0, *) {
            panel.allowedContentTypes = [.json, .plainText]
        } else {
            panel.allowedFileTypes = ["json", "txt"]
        }
        // Default filename and directory: prefer Downloads and include timestamp
        let fm = FileManager.default
        let formatter = ISO8601DateFormatter()
        let stamp = formatter.string(from: Date()).replacingOccurrences(of: ":", with: "-")
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        let isJSON = trimmed.first == "{" || trimmed.first == "["
        panel.nameFieldStringValue = isJSON ? "mail_summariser_error_\(stamp).json" : "mail_summariser_error_\(stamp).txt"
        if let downloads = try? fm.url(for: .downloadsDirectory, in: .userDomainMask, appropriateFor: nil, create: false) {
            panel.directoryURL = downloads
        }
        if panel.runModal() == .OK, let url = panel.url {
            do {
                try text.write(to: url, atomically: true, encoding: .utf8)
                appState.statusText = "Saved error to \(url.lastPathComponent)"
            } catch {
                appState.statusText = "Failed to save error: \(error.localizedDescription)"
            }
        }
    }

    private func copyWithTimestamp(_ raw: String) {
        let formatter = ISO8601DateFormatter()
        let stamp = formatter.string(from: Date())
        let text = "Timestamp: \(stamp)\n\n\(raw)"
        copyToPasteboard(text)
        appState.statusText = "Copied error with timestamp"
    }

    private func exportErrorAsJSON(_ raw: String) {
        let json = errorJSONWithMetadata(raw)
        saveErrorViaSavePanel(json)
    }
}
