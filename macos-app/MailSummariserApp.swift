import SwiftUI

@main
struct MailSummariserApp: App {
    @StateObject private var appState = AppState()

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(appState)
        }
        Settings {
            SettingsView()
                .environmentObject(appState)
        }
    }
}
