import AppKit
import SwiftUI

struct SettingsView: View {
    @Environment(\.openURL) private var openURL
    @EnvironmentObject private var appState: AppState
    @State private var localSettings = AppSettings()
    @State private var saveStatus = ""
    @State private var imapPasswordVisible = false
    @State private var smtpPasswordVisible = false
    @State private var showStopConfirmation = false
    @State private var showResetSheet = false
    @State private var resetConfirmationText = ""

    var body: some View {
        Form {
            Section {
                Toggle("Dummy Mode", isOn: $localSettings.dummyMode)
                Text(localSettings.dummyMode ? "Using the built-in test mailbox and outbox." : "Using the configured IMAP and SMTP servers.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            Section("Local Ollama") {
                TextField("Ollama Host", text: $localSettings.ollamaHost)
                TextField("Model", text: $localSettings.modelName)
                Toggle("Auto-start Ollama when needed", isOn: $localSettings.ollamaAutoStart)
                Toggle("Start Ollama automatically on startup", isOn: $localSettings.ollamaStartOnStartup)
                Toggle("Stop Ollama automatically on exit", isOn: $localSettings.ollamaStopOnExit)
                Text(appState.runtimeStatus.ollama.message)
                    .font(.caption)
                    .foregroundStyle(runtimeNeedsAttention ? .orange : .secondary)

                HStack {
                    if let runtimeActionTitle {
                        Button(runtimeActionTitle) {
                            Task { await handleRuntimeAction() }
                        }
                    }
                    Button("Refresh Runtime Status") {
                        Task { await loadRuntimeStatus() }
                    }
                }
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
            }

            Section("Application") {
                Button("Reset Local Database", role: .destructive) {
                    resetConfirmationText = ""
                    showResetSheet = true
                }
                Text("This removes every stored setting, job, log, and undo entry from the backend database and restores defaults.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Button("Stop Mail Summariser", role: .destructive) {
                    showStopConfirmation = true
                }
                Text("This shuts down the connected backend. If shutdown succeeds, the macOS app also closes.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            if appState.fakeMailStatus.enabled {
                Section("Fake Mail Server") {
                    Text(appState.fakeMailStatus.message)
                        .font(.caption)
                        .foregroundStyle(appState.fakeMailStatus.running ? Color.secondary : Color.orange)
                    if appState.fakeMailStatus.running {
                        Text(
                            "IMAP \(appState.fakeMailStatus.imapHost):\(appState.fakeMailStatus.imapPort) | " +
                            "SMTP \(appState.fakeMailStatus.smtpHost):\(appState.fakeMailStatus.smtpPort) | " +
                            "Username \(appState.fakeMailStatus.username) | Password \(appState.fakeMailStatus.password)"
                        )
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    }

                    HStack {
                        Button("Start Fake Mail Server") {
                            Task { await startFakeMailServer() }
                        }
                        .disabled(appState.fakeMailStatus.running)
                        Button("Stop Fake Mail Server") {
                            Task { await stopFakeMailServer() }
                        }
                        .disabled(!appState.fakeMailStatus.running)
                        Button("Use Fake Mail Settings") {
                            applyFakeMailSettings()
                        }
                        .disabled(!appState.fakeMailStatus.running || appState.fakeMailStatus.suggestedSettings == nil)
                    }
                }
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
            if appState.runtimeStatus.ollama.message == "Runtime status not loaded yet." {
                await loadRuntimeStatus()
            }
            if !appState.fakeMailStatus.enabled {
                await loadFakeMailStatus()
            }
        }
        .alert("Stop Mail Summariser?", isPresented: $showStopConfirmation) {
            Button("Stop", role: .destructive) {
                Task { await stopMailSummariser() }
            }
            Button("Cancel", role: .cancel) {}
        } message: {
            Text("This will stop the connected backend and close the macOS app.")
        }
        .sheet(isPresented: $showResetSheet) {
            VStack(alignment: .leading, spacing: 16) {
                Text("Reset Local Database")
                    .font(.headline)
                Text("Type RESET DATABASE to delete all stored backend data and restore defaults.")
                    .foregroundStyle(.secondary)
                TextField("RESET DATABASE", text: $resetConfirmationText)
                    .textFieldStyle(.roundedBorder)
                HStack {
                    Spacer()
                    Button("Cancel") {
                        showResetSheet = false
                    }
                    Button("Reset", role: .destructive) {
                        Task { await resetDatabase() }
                    }
                    .disabled(resetConfirmationText != "RESET DATABASE")
                }
            }
            .padding(24)
            .frame(width: 440)
        }
    }

    private func loadSettings() async {
        do {
            try await appState.loadSettings()
            localSettings = appState.settings
            try await appState.loadRuntimeStatus()
            try await appState.loadFakeMailStatus()
            saveStatus = "Loaded"
        } catch {
            saveStatus = "Load failed: \(error.localizedDescription)"
        }
    }

    private func saveSettings() async {
        do {
            let previousDummyMode = appState.settings.dummyMode
            try await appState.saveSettings(localSettings)
            try await appState.loadRuntimeStatus()
            try await appState.loadFakeMailStatus()
            if previousDummyMode != localSettings.dummyMode {
                appState.resetWorkspaceState()
            }
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

    private var runtimeActionTitle: String? {
        switch appState.runtimeStatus.ollama.startupAction {
        case "install":
            return "Install Ollama"
        case "start":
            return "Start Ollama"
        default:
            return nil
        }
    }

    private var runtimeNeedsAttention: Bool {
        let action = appState.runtimeStatus.ollama.startupAction
        if action == "install" || action == "start" {
            return true
        }
        return appState.runtimeStatus.ollama.message.localizedCaseInsensitiveContains("not installed")
            || appState.runtimeStatus.ollama.message.localizedCaseInsensitiveContains("failed")
    }

    private func loadRuntimeStatus() async {
        do {
            try await appState.loadRuntimeStatus()
        } catch {
            saveStatus = "Runtime status failed: \(error.localizedDescription)"
        }
    }

    private func loadFakeMailStatus() async {
        do {
            try await appState.loadFakeMailStatus()
        } catch {
            saveStatus = "Fake mail status failed: \(error.localizedDescription)"
        }
    }

    private func handleRuntimeAction() async {
        if appState.runtimeStatus.ollama.startupAction == "install" {
            if let url = URL(string: appState.runtimeStatus.ollama.installUrl) {
                openURL(url)
            }
            saveStatus = "Opened the Ollama download page."
            return
        }

        do {
            let response = try await appState.startManagedOllama()
            saveStatus = response.message
        } catch {
            saveStatus = "Ollama start failed: \(error.localizedDescription)"
        }
    }

    private func stopMailSummariser() async {
        do {
            let response = try await appState.requestShutdown()
            saveStatus = response.message ?? response.status ?? "Stopping"
            NSApplication.shared.terminate(nil)
        } catch {
            saveStatus = "Stop failed: \(error.localizedDescription)"
        }
    }

    private func startFakeMailServer() async {
        do {
            let status = try await appState.startFakeMailServer()
            saveStatus = status.message
        } catch {
            saveStatus = "Fake mail start failed: \(error.localizedDescription)"
        }
    }

    private func stopFakeMailServer() async {
        do {
            let status = try await appState.stopFakeMailServer()
            saveStatus = status.message
        } catch {
            saveStatus = "Fake mail stop failed: \(error.localizedDescription)"
        }
    }

    private func applyFakeMailSettings() {
        guard let suggested = appState.fakeMailStatus.suggestedSettings else {
            saveStatus = "Start the fake mail server before applying its settings."
            return
        }
        localSettings = suggested
        saveStatus = "Fake mail settings loaded. Save to use them."
    }

    private func resetDatabase() async {
        do {
            let response = try await appState.resetDatabase()
            localSettings = response.settings
            try await appState.loadRuntimeStatus()
            try await appState.loadFakeMailStatus()
            saveStatus = response.message
            showResetSheet = false
        } catch {
            saveStatus = "Reset failed: \(error.localizedDescription)"
        }
    }
}
