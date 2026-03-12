import SwiftUI

struct ContentView: View {
    @StateObject private var appState = AppState()

    var body: some View {
        TabView {
            SearchView()
                .tabItem { Text("Search") }
            SummaryView()
                .tabItem { Text("Summary") }
            LogView()
                .tabItem { Text("Log") }
        }
        .environmentObject(appState)
        .frame(minWidth: 980, minHeight: 700)
        .task {
            await loadSettings()
        }
    }

    private func loadSettings() async {
        do {
            let settings: AppSettings = try await appState.bridge.get(path: "settings")
            appState.settings = settings
            appState.applySettingsToBridge()
        } catch {
            appState.statusText = "Failed to load settings: \(error.localizedDescription)"
        }
    }
}
