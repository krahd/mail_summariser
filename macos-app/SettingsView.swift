import SwiftUI

struct SettingsView: View {
    @EnvironmentObject private var appState: AppState
    @State private var localSettings = AppSettings()
    @State private var saveStatus = ""
    @State private var imapPasswordVisible = false
    @State private var smtpPasswordVisible = false

    var body: some View {
        Form {
            Section {
                Toggle("Dummy Mode", isOn: $localSettings.dummyMode)
                Text(localSettings.dummyMode ? "Using the built-in test mailbox and outbox." : "Using the configured IMAP and SMTP servers.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            Section("Connection Check") {
                Button("Test Connection") {
                    Task { await testConnection() }
                }
                Text(saveStatus)
                    .foregroundStyle(.secondary)
            }

            Section("Mail") {
                TextField("IMAP Host", text: $localSettings.imapHost)
                TextField("IMAP Port", value: $localSettings.imapPort, format: .number)
                Toggle("Use SSL for IMAP", isOn: $localSettings.imapUseSSL)
                if imapPasswordVisible {
                    TextField("IMAP Password", text: $localSettings.imapPassword)
                } else {
                    SecureField("IMAP Password", text: $localSettings.imapPassword)
                }
                Button(imapPasswordVisible ? "Hide IMAP Password" : "Show IMAP Password") {
                    imapPasswordVisible.toggle()
                }
                TextField("SMTP Host", text: $localSettings.smtpHost)
                TextField("SMTP Port", value: $localSettings.smtpPort, format: .number)
                Toggle("Use SSL for SMTP", isOn: $localSettings.smtpUseSSL)
                if smtpPasswordVisible {
                    TextField("SMTP Password", text: $localSettings.smtpPassword)
                } else {
                    SecureField("SMTP Password", text: $localSettings.smtpPassword)
                }
                Button(smtpPasswordVisible ? "Hide SMTP Password" : "Show SMTP Password") {
                    smtpPasswordVisible.toggle()
                }
                TextField("Username", text: $localSettings.username)
                TextField("Digest recipient", text: $localSettings.recipientEmail)
                TextField("Summarised tag", text: $localSettings.summarisedTag)
            }

            Section("Backend") {
                TextField("Provider", text: $localSettings.llmProvider)
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
            }
        }
        .padding()
        .frame(width: 560)
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

    private func testConnection() async {
        do {
            let response: ConnectionTestResponse = try await appState.bridge.postJSON(path: "settings/test-connection", body: localSettings)
            saveStatus = "\(response.imap.message) | \(response.smtp.message)"
        } catch {
            saveStatus = "Test failed: \(error.localizedDescription)"
        }
    }
}
