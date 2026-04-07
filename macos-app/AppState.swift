import Foundation

@MainActor
final class AppState: ObservableObject {
    private static let backendAPIKeyDefaultsKey = "mail_summariser-backend-api-key"
    private var messageDetailRequestToken = UUID()

    let bridge: BackendBridge

    @Published var criteria = SearchCriteria()
    @Published var summaryLength: Int = 5
    @Published var currentSummary: String = ""
    @Published var currentMessages: [MessageItem] = []
    @Published var selectedJobId: String = ""
    @Published var selectedMessageId: String? = nil
    @Published var selectedMessageDetail: MessageDetail? = nil
    @Published var isLoadingSelectedMessage = false
    @Published var selectedMessageErrorText: String = ""
    @Published var statusText: String = "Ready"
    @Published var settings = AppSettings()
    @Published var backendAPIKey: String
    @Published var runtimeStatus = RuntimeStatusResponse()
    @Published var fakeMailStatus = FakeMailStatusResponse()
    @Published var systemMessageDefaults = SystemMessageDefaultsResponse()

    init(bridge: BackendBridge? = nil) {
        let storedAPIKey = UserDefaults.standard.string(forKey: Self.backendAPIKeyDefaultsKey) ?? ""
        self.backendAPIKey = storedAPIKey
        self.bridge = bridge ?? BackendBridge(apiKey: storedAPIKey)
        self.bridge.configure(baseURLString: self.bridge.baseURLString, apiKey: storedAPIKey)
    }

    func applySettingsToBridge() {
        bridge.configure(baseURLString: settings.backendBaseURL, apiKey: backendAPIKey)
    }

    func updateBackendAPIKey(_ apiKey: String) {
        backendAPIKey = apiKey
        UserDefaults.standard.set(apiKey, forKey: Self.backendAPIKeyDefaultsKey)
        bridge.configure(baseURLString: settings.backendBaseURL, apiKey: apiKey)
    }

    func loadSettings() async throws {
        let loaded: AppSettings = try await bridge.get(path: "settings")
        settings = loaded
        applySettingsToBridge()
    }

    func loadRuntimeStatus() async throws {
        runtimeStatus = try await bridge.get(path: "runtime/status")
    }

    func loadFakeMailStatus() async throws {
        fakeMailStatus = try await bridge.get(path: "dev/fake-mail/status")
    }

    func loadSystemMessageDefaults() async throws {
        systemMessageDefaults = try await bridge.get(path: "settings/system-message-defaults")
    }

    func startManagedOllama() async throws -> RuntimeActionResponse {
        let response: RuntimeActionResponse = try await bridge.postJSON(path: "runtime/ollama/start", body: EmptyPayload())
        runtimeStatus = response.runtime
        return response
    }

    func startFakeMailServer() async throws -> FakeMailStatusResponse {
        let response: FakeMailStatusResponse = try await bridge.postJSON(path: "dev/fake-mail/start", body: EmptyPayload())
        fakeMailStatus = response
        return response
    }

    func stopFakeMailServer() async throws -> FakeMailStatusResponse {
        let response: FakeMailStatusResponse = try await bridge.postJSON(path: "dev/fake-mail/stop", body: EmptyPayload())
        fakeMailStatus = response
        return response
    }

    func requestShutdown() async throws -> EmptyResponse {
        try await bridge.postJSON(path: "runtime/shutdown", body: EmptyPayload())
    }

    func saveSettings(_ newSettings: AppSettings) async throws {
        let _: EmptyResponse = try await bridge.postJSON(path: "settings", body: newSettings)
        settings = newSettings
        applySettingsToBridge()
    }

    func resetDatabase() async throws -> DatabaseResetResponse {
        let response: DatabaseResetResponse = try await bridge.postJSON(
            path: "admin/database/reset",
            body: ConfirmationPayload(confirmation: "RESET DATABASE")
        )
        settings = response.settings
        applySettingsToBridge()
        resetWorkspaceState()
        return response
    }

    func resetWorkspaceState() {
        currentSummary = ""
        currentMessages = []
        selectedJobId = ""
        clearSelectedMessageState()
    }

    func selectMessage(_ messageId: String?) async {
        messageDetailRequestToken = UUID()
        selectedMessageId = messageId
        selectedMessageDetail = nil
        selectedMessageErrorText = ""

        guard let messageId, !messageId.isEmpty, !selectedJobId.isEmpty else {
            isLoadingSelectedMessage = false
            return
        }

        let requestToken = UUID()
        messageDetailRequestToken = requestToken
        isLoadingSelectedMessage = true

        do {
            let detail = try await bridge.getMessageDetail(jobId: selectedJobId, messageId: messageId)
            guard messageDetailRequestToken == requestToken, selectedMessageId == messageId else {
                return
            }

            selectedMessageDetail = detail
            isLoadingSelectedMessage = false
        } catch {
            guard messageDetailRequestToken == requestToken, selectedMessageId == messageId else {
                return
            }

            isLoadingSelectedMessage = false
            selectedMessageErrorText = error.localizedDescription
            statusText = "Message load failed: \(error.localizedDescription)"
        }
    }

    private func clearSelectedMessageState() {
        messageDetailRequestToken = UUID()
        selectedMessageId = nil
        selectedMessageDetail = nil
        isLoadingSelectedMessage = false
        selectedMessageErrorText = ""
    }
}
