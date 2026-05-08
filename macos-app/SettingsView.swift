import AppKit
import SwiftUI

struct SettingsView: View {
    @Environment(\.openURL) private var openURL
    @EnvironmentObject private var appState: AppState
    @State private var localSettings = AppSettings()
    @State private var saveStatus = ""
    @State private var imapPasswordVisible = false
    @State private var smtpPasswordVisible = false
    @State private var openAIKeyVisible = false
    @State private var anthropicKeyVisible = false
    @State private var backendAPIKeyVisible = false
    @State private var showStopConfirmation = false
    @State private var showResetSheet = false
    @State private var resetConfirmationText = ""

    var body: some View {
        ZStack {
            BrandBackdrop()

            VStack(alignment: .leading, spacing: 16) {
                HStack(alignment: .top, spacing: 16) {
                    BrandSectionTitle(
                        eyebrow: "Configuration",
                        title: "Settings",
                        subtitle: "Mail, provider, runtime, and operator controls."
                    )

                    Spacer()
                    BrandStatusPill(text: saveStatus.isEmpty ? "Ready" : saveStatus)
                }

                NavigationStack {
                    Form {
                        Section {
                            Toggle("Sample Mailbox", isOn: $localSettings.dummyMode)
                            Text(localSettings.dummyMode ? "Using the Sample Mailbox with resettable sample messages and the local sample outbox." : "Using the configured live IMAP and SMTP servers.")
                                .font(.caption)
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

                        Section("Connection Check") {
                            Button("Test Connection") {
                                Task { await testConnection() }
                            }
                            Text(saveStatus.isEmpty ? "Connection not tested yet." : saveStatus)
                                .foregroundStyle(.secondary)
                        }

                        Section {
                            NavigationLink("Advanced Settings") {
                                advancedSettingsView
                            }
                        }

                        Section {
                            HStack {
                                Button("Load") {
                                    Task { await loadSettings() }
                                }
                                Button("Save") {
                                    Task { await saveSettings() }
                                }
                            }
                        }
                    }
                    .navigationTitle("Settings")
                    .formStyle(.grouped)
                    .scrollContentBackground(.hidden)
                    .background(Color.clear)
                }
                .padding(8)
                .background(
                    RoundedRectangle(cornerRadius: 22, style: .continuous)
                        .fill(BrandPalette.panelStrong)
                )
                .overlay(
                    RoundedRectangle(cornerRadius: 22, style: .continuous)
                        .stroke(BrandPalette.line, lineWidth: 1)
                )
            }
        }
        .padding(20)
        .frame(width: 700, height: 820)
        .tint(BrandPalette.accent)
        .task {
            localSettings = appState.settings
            if appState.runtimeStatus.ollama.message == "Runtime status not loaded yet." {
                await loadRuntimeStatus()
            }
            if !appState.fakeMailStatus.enabled {
                await loadFakeMailStatus()
            }
            await loadSystemMessageDefaults()
        }
        .alert("Stop mail_summariser?", isPresented: $showStopConfirmation) {
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

    private var advancedSettingsView: some View {
        Form {
            Section("Provider") {
                Picker("LLM Provider", selection: providerBinding) {
                    Text("Ollama").tag("ollama")
                    Text("OpenAI").tag("openai")
                    Text("Anthropic").tag("anthropic")
                }
                .pickerStyle(.menu)

                Text(providerKeyStatus)
                    .font(.caption)
                    .foregroundStyle(providerKeyStatusIsWarning ? .orange : .secondary)

                VStack(alignment: .leading, spacing: 8) {
                    Text("System Message for \(providerDisplayName)")
                        .font(.headline)
                    TextEditor(text: systemMessageBinding)
                        .font(.body)
                        .frame(minHeight: 180)
                        .padding(8)
                        .background(
                            RoundedRectangle(cornerRadius: 12, style: .continuous)
                                .fill(BrandPalette.panelMuted)
                        )
                        .overlay {
                            RoundedRectangle(cornerRadius: 12, style: .continuous)
                                .stroke(BrandPalette.line, lineWidth: 1)
                        }
                    Text("\(providerDisplayName) stores its own system message. Switching providers swaps the prompt shown here.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    Text("Prompt checklist: prioritise deadlines, approvals, blockers, and reply-needed items; group related threads; avoid filler; do not invent facts.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    Button("Reset to Default") {
                        resetCurrentSystemMessage()
                    }
                }

                if selectedProviderID == "openai" {
                    if openAIKeyVisible {
                        TextField("OpenAI API Key", text: $localSettings.openaiApiKey)
                    } else {
                        SecureField("OpenAI API Key", text: $localSettings.openaiApiKey)
                    }
                    Button(openAIKeyVisible ? "Hide OpenAI API Key" : "Show OpenAI API Key") {
                        openAIKeyVisible.toggle()
                    }
                }

                if selectedProviderID == "anthropic" {
                    if anthropicKeyVisible {
                        TextField("Anthropic API Key", text: $localSettings.anthropicApiKey)
                    } else {
                        SecureField("Anthropic API Key", text: $localSettings.anthropicApiKey)
                    }
                    Button(anthropicKeyVisible ? "Hide Anthropic API Key" : "Show Anthropic API Key") {
                        anthropicKeyVisible.toggle()
                    }
                }
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

            Section("Backend Client") {
                TextField(
                    "Backend URL",
                    text: Binding(
                        get: { localSettings.backendBaseURL },
                        set: { newValue in
                            localSettings.backendBaseURL = newValue
                            appState.bridge.configure(baseURLString: newValue, apiKey: appState.backendAPIKey)
                        }
                    )
                )
                if backendAPIKeyVisible {
                    TextField("Backend API Key", text: backendAPIKeyBinding)
                } else {
                    SecureField("Backend API Key", text: backendAPIKeyBinding)
                }
                Button(backendAPIKeyVisible ? "Hide Backend API Key" : "Show Backend API Key") {
                    backendAPIKeyVisible.toggle()
                }
                Text("Stored locally on this Mac and sent as X-API-Key with backend requests.")
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

            Section("Application") {
                Button("Reset Local Database", role: .destructive) {
                    resetConfirmationText = ""
                    showResetSheet = true
                }
                Text("This removes every stored setting, job, log, and undo entry from the backend database and restores defaults.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Button("Stop mail_summariser", role: .destructive) {
                    showStopConfirmation = true
                }
                Text("This shuts down the connected backend. If shutdown succeeds, the macOS app also closes.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            Section {
                HStack {
                    Button("Load") {
                        Task { await loadSettings() }
                    }
                    Button("Save") {
                        Task { await saveSettings() }
                    }
                }
            }
        }
        .navigationTitle("Advanced Settings")
        .formStyle(.grouped)
        .scrollContentBackground(.hidden)
        .background(Color.clear)
    }

    private var providerBinding: Binding<String> {
        Binding(
            get: { selectedProviderID },
            set: { localSettings.llmProvider = $0 }
        )
    }

    private var backendAPIKeyBinding: Binding<String> {
        Binding(
            get: { appState.backendAPIKey },
            set: { appState.updateBackendAPIKey($0) }
        )
    }

    private var systemMessageBinding: Binding<String> {
        Binding(
            get: {
                switch selectedProviderID {
                case "openai":
                    return localSettings.openaiSystemMessage
                case "anthropic":
                    return localSettings.anthropicSystemMessage
                default:
                    return localSettings.ollamaSystemMessage
                }
            },
            set: { newValue in
                switch selectedProviderID {
                case "openai":
                    localSettings.openaiSystemMessage = newValue
                case "anthropic":
                    localSettings.anthropicSystemMessage = newValue
                default:
                    localSettings.ollamaSystemMessage = newValue
                }
            }
        )
    }

    private var selectedProviderID: String {
        let provider = localSettings.llmProvider.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        switch provider {
        case "openai", "anthropic":
            return provider
        default:
            return "ollama"
        }
    }

    private var providerDisplayName: String {
        switch selectedProviderID {
        case "openai":
            return "OpenAI"
        case "anthropic":
            return "Anthropic"
        default:
            return "Ollama"
        }
    }

    private var providerKeyStatus: String {
        switch selectedProviderID {
        case "openai":
            return hasConfiguredKey(localSettings.openaiApiKey)
                ? "OpenAI selected. Key is configured."
                : "OpenAI selected but no OpenAI key is configured. Summaries may fall back."
        case "anthropic":
            return hasConfiguredKey(localSettings.anthropicApiKey)
                ? "Anthropic selected. Key is configured."
                : "Anthropic selected but no Anthropic key is configured. Summaries may fall back."
        default:
            return "Ollama selected. Remote provider keys are not required."
        }
    }

    private var providerKeyStatusIsWarning: Bool {
        (selectedProviderID == "openai" && !hasConfiguredKey(localSettings.openaiApiKey))
            || (selectedProviderID == "anthropic" && !hasConfiguredKey(localSettings.anthropicApiKey))
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

    private func hasConfiguredKey(_ value: String) -> Bool {
        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
        return !trimmed.isEmpty
    }

    private func resetCurrentSystemMessage() {
        switch selectedProviderID {
        case "openai":
            localSettings.openaiSystemMessage = appState.systemMessageDefaults.openaiSystemMessage
        case "anthropic":
            localSettings.anthropicSystemMessage = appState.systemMessageDefaults.anthropicSystemMessage
        default:
            localSettings.ollamaSystemMessage = appState.systemMessageDefaults.ollamaSystemMessage
        }
        saveStatus = "\(providerDisplayName) system message reset in the form. Save to keep it."
    }

    private func loadSettings() async {
        do {
            try await appState.loadSettings()
            localSettings = appState.settings
            try await appState.loadRuntimeStatus()
            try await appState.loadFakeMailStatus()
            try await appState.loadSystemMessageDefaults()
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
            try await appState.loadSystemMessageDefaults()
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

    private func loadSystemMessageDefaults() async {
        do {
            try await appState.loadSystemMessageDefaults()
        } catch {
            saveStatus = "System message defaults failed: \(error.localizedDescription)"
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
        appState.bridge.configure(baseURLString: suggested.backendBaseURL, apiKey: appState.backendAPIKey)
        saveStatus = "Fake mail settings loaded. Save to use them."
    }

    private func resetDatabase() async {
        do {
            let response = try await appState.resetDatabase()
            localSettings = response.settings
            try await appState.loadRuntimeStatus()
            try await appState.loadFakeMailStatus()
            try await appState.loadSystemMessageDefaults()
            saveStatus = response.message
            showResetSheet = false
        } catch {
            saveStatus = "Reset failed: \(error.localizedDescription)"
        }
    }
}
