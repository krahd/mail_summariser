import SwiftUI

struct ContentView: View {
    @Environment(\.openURL) private var openURL
    @EnvironmentObject private var appState: AppState
    @State private var showStartupPrompt = false

    var body: some View {
        TabView {
            SearchView()
                .tabItem { Text("Main") }
            LogView()
                .tabItem { Text("Log") }
        }
        .frame(minWidth: 980, minHeight: 700)
        .task {
            await bootstrap()
        }
        .alert("Ollama Setup", isPresented: $showStartupPrompt) {
            if appState.runtimeStatus.ollama.startupAction == "install" {
                Button("Install Ollama") {
                    if let url = URL(string: appState.runtimeStatus.ollama.installUrl) {
                        openURL(url)
                    }
                }
            } else if appState.runtimeStatus.ollama.startupAction == "start" {
                Button("Start Ollama") {
                    Task { await startOllamaFromPrompt() }
                }
            }
            Button("Later", role: .cancel) {}
        } message: {
            Text(appState.runtimeStatus.ollama.message)
        }
    }

    private func bootstrap() async {
        do {
            try await appState.loadSettings()
            try await appState.loadRuntimeStatus()
            showStartupPrompt = shouldPromptForOllama
        } catch {
            appState.statusText = "Failed to load settings: \(error.localizedDescription)"
        }
    }

    private var shouldPromptForOllama: Bool {
        let provider = appState.settings.llmProvider.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        let action = appState.runtimeStatus.ollama.startupAction
        return provider == "ollama" && (action == "install" || action == "start")
    }

    private func startOllamaFromPrompt() async {
        do {
            let response = try await appState.startManagedOllama()
            appState.statusText = response.message
            showStartupPrompt = shouldPromptForOllama
        } catch {
            appState.statusText = "Failed to start Ollama: \(error.localizedDescription)"
        }
    }
}
