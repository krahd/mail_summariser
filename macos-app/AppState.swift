import Foundation

@MainActor
final class AppState: ObservableObject {
    let bridge: BackendBridge

    @Published var criteria = SearchCriteria()
    @Published var summaryLength: Double = 5
    @Published var currentSummary: String = ""
    @Published var currentMessages: [MessageItem] = []
    @Published var selectedJobId: String = ""
    @Published var statusText: String = "Ready"
    @Published var settings = AppSettings()
    @Published var runtimeStatus = RuntimeStatusResponse()
    @Published var fakeMailStatus = FakeMailStatusResponse()

    init(bridge: BackendBridge? = nil) {
        self.bridge = bridge ?? BackendBridge()
    }

    func applySettingsToBridge() {
        bridge.configure(baseURLString: settings.backendBaseURL)
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
    }
}
