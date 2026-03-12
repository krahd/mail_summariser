import SwiftUI

struct SettingsView: View {
    @EnvironmentObject private var appState: AppState
    @State private var localSettings = AppSettings()
    @State private var saveStatus = ""

    var body: some View {
        Form {
            Section("Mail") {
                TextField("IMAP Host", text: $localSettings.imapHost)
                TextField("SMTP Host", text: $localSettings.smtpHost)
                TextField("Username", text: $localSettings.username)
                TextField("Digest recipient", text: $localSettings.recipientEmail)
                TextField("Summarised tag", text: $localSettings.summarisedTag)
            }

            Section("Backend") {
                TextField("Backend URL", text: $localSettings.backendBaseURL)
                TextField("Model", text: $localSettings.modelName)
            }

            HStack {
                Button("Load") {
                    Task { await loadSettings() }
                }
                Button("Save") {
                    Task { await saveSettings() }
                }
                Text(saveStatus)
                    .foregroundStyle(.secondary)
            }
        }
        .padding()
        .frame(width: 520)
        .task {
            localSettings = appState.settings
        }
    }

    private func loadSettings() async {
        do {
            let loaded: AppSettings = try await appState.bridge.get(path: "settings")
            localSettings = loaded
            appState.settings = loaded
            appState.applySettingsToBridge()
            saveStatus = "Loaded"
        } catch {
            saveStatus = "Load failed: \(error.localizedDescription)"
        }
    }

    private func saveSettings() async {
        do {
            let _: EmptyResponse = try await appState.bridge.postJSON(path: "settings", body: localSettings)
            appState.settings = localSettings
            appState.applySettingsToBridge()
            saveStatus = "Saved"
        } catch {
            saveStatus = "Save failed: \(error.localizedDescription)"
        }
    }
}
