import Foundation

@MainActor
final class AppState: ObservableObject {
    let bridge = BackendBridge()

    @Published var criteria = SearchCriteria()
    @Published var summaryLength: Double = 5
    @Published var currentSummary: String = ""
    @Published var currentMessages: [MessageItem] = []
    @Published var selectedJobId: String = ""
    @Published var statusText: String = "Ready"
    @Published var settings = AppSettings()

    func applySettingsToBridge() {
        bridge.configure(baseURLString: settings.backendBaseURL)
    }
}
