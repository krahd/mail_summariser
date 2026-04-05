import SwiftUI

enum BrandPalette {
    static let backgroundTop = Color(red: 0.94, green: 0.91, blue: 0.85)
    static let backgroundBottom = Color(red: 0.99, green: 0.98, blue: 0.95)
    static let ink = Color(red: 0.07, green: 0.21, blue: 0.18)
    static let muted = Color(red: 0.36, green: 0.43, blue: 0.40)
    static let accent = Color(red: 0.05, green: 0.54, blue: 0.46)
    static let accentWarm = Color(red: 0.84, green: 0.42, blue: 0.19)
    static let panel = Color.white.opacity(0.72)
    static let panelStrong = Color.white.opacity(0.86)
    static let line = Color(red: 0.07, green: 0.21, blue: 0.18).opacity(0.12)
}

struct BrandBackdrop: View {
    var body: some View {
        ZStack {
            LinearGradient(
                colors: [BrandPalette.backgroundTop, BrandPalette.backgroundBottom],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )
            Circle()
                .fill(BrandPalette.accentWarm.opacity(0.22))
                .frame(width: 360, height: 360)
                .blur(radius: 80)
                .offset(x: -280, y: 240)
            Circle()
                .fill(BrandPalette.accent.opacity(0.18))
                .frame(width: 320, height: 320)
                .blur(radius: 90)
                .offset(x: 300, y: -220)
        }
        .ignoresSafeArea()
    }
}

struct BrandPanelModifier: ViewModifier {
    func body(content: Content) -> some View {
        content
            .padding(20)
            .background(
                RoundedRectangle(cornerRadius: 24, style: .continuous)
                    .fill(BrandPalette.panel)
            )
            .overlay(
                RoundedRectangle(cornerRadius: 24, style: .continuous)
                    .stroke(BrandPalette.line, lineWidth: 1)
            )
            .shadow(color: Color.black.opacity(0.08), radius: 22, x: 0, y: 16)
    }
}

extension View {
    func brandPanel() -> some View {
        modifier(BrandPanelModifier())
    }
}

struct BrandStatusPill: View {
    let text: String

    var body: some View {
        Text(text)
            .font(.caption.weight(.semibold))
            .foregroundStyle(BrandPalette.ink)
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            .background(
                Capsule(style: .continuous)
                    .fill(BrandPalette.panelStrong)
            )
            .overlay(
                Capsule(style: .continuous)
                    .stroke(BrandPalette.line, lineWidth: 1)
            )
    }
}

struct ContentView: View {
    @Environment(\.openURL) private var openURL
    @EnvironmentObject private var appState: AppState
    @State private var showStartupPrompt = false

    var body: some View {
        ZStack {
            BrandBackdrop()

            VStack(alignment: .leading, spacing: 18) {
                HStack(alignment: .top, spacing: 14) {
                    VStack(alignment: .leading, spacing: 6) {
                        HStack(spacing: 10) {
                            Circle()
                                .fill(
                                    LinearGradient(
                                        colors: [BrandPalette.accent, BrandPalette.accentWarm],
                                        startPoint: .topLeading,
                                        endPoint: .bottomTrailing
                                    )
                                )
                                .frame(width: 14, height: 14)
                            Text("Mail Summariser")
                                .font(.system(size: 30, weight: .bold, design: .rounded))
                                .foregroundStyle(BrandPalette.ink)
                        }
                        Text("Local-first mail workflow with a calmer, more intentional workspace.")
                            .font(.headline)
                            .foregroundStyle(BrandPalette.muted)
                    }

                    Spacer()
                    BrandStatusPill(text: appState.statusText)
                }

                TabView {
                    SearchView()
                        .tabItem { Text("Main") }
                    LogView()
                        .tabItem { Text("Log") }
                }
                .padding(12)
                .background(
                    RoundedRectangle(cornerRadius: 30, style: .continuous)
                        .fill(BrandPalette.panelStrong)
                )
                .overlay(
                    RoundedRectangle(cornerRadius: 30, style: .continuous)
                        .stroke(BrandPalette.line, lineWidth: 1)
                )
                .shadow(color: Color.black.opacity(0.08), radius: 28, x: 0, y: 16)
            }
            .padding(26)
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
