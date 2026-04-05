import SwiftUI

enum BrandPalette {
    static let backgroundTop = Color(red: 0.93, green: 0.96, blue: 0.95)
    static let backgroundBottom = Color(red: 0.98, green: 0.99, blue: 0.99)
    static let backgroundAccent = Color(red: 0.05, green: 0.46, blue: 0.40).opacity(0.08)
    static let ink = Color(red: 0.12, green: 0.22, blue: 0.20)
    static let muted = Color(red: 0.40, green: 0.47, blue: 0.45)
    static let accent = Color(red: 0.05, green: 0.46, blue: 0.40)
    static let accentWarm = Color(red: 0.72, green: 0.40, blue: 0.25)
    static let panel = Color.white.opacity(0.9)
    static let panelStrong = Color.white.opacity(0.96)
    static let panelMuted = Color(red: 0.96, green: 0.97, blue: 0.97)
    static let line = Color(red: 0.12, green: 0.22, blue: 0.20).opacity(0.1)
}

struct BrandBackdrop: View {
    var body: some View {
        ZStack(alignment: .top) {
            LinearGradient(
                colors: [BrandPalette.backgroundTop, BrandPalette.backgroundBottom],
                startPoint: .top,
                endPoint: .bottom
            )

            LinearGradient(
                colors: [BrandPalette.backgroundAccent, .clear],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )
            .frame(height: 220)
        }
        .ignoresSafeArea()
    }
}

struct BrandPanelModifier: ViewModifier {
    let padding: CGFloat
    let fill: Color

    func body(content: Content) -> some View {
        content
            .padding(padding)
            .background(
                RoundedRectangle(cornerRadius: 20, style: .continuous)
                    .fill(fill)
            )
            .overlay(
                RoundedRectangle(cornerRadius: 20, style: .continuous)
                    .stroke(BrandPalette.line, lineWidth: 1)
            )
            .shadow(color: Color.black.opacity(0.05), radius: 14, x: 0, y: 6)
    }
}

extension View {
    func brandPanel(padding: CGFloat = 18, fill: Color = BrandPalette.panel) -> some View {
        modifier(BrandPanelModifier(padding: padding, fill: fill))
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
                    .fill(BrandPalette.panelMuted)
            )
            .overlay(
                Capsule(style: .continuous)
                    .stroke(BrandPalette.line, lineWidth: 1)
            )
    }
}

struct BrandSectionTitle: View {
    let eyebrow: String
    let title: String
    let subtitle: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 5) {
            Text(eyebrow.uppercased())
                .font(.caption.weight(.bold))
                .kerning(1.1)
                .foregroundStyle(BrandPalette.accent)

            Text(title)
                .font(.system(size: 23, weight: .bold))
                .foregroundStyle(BrandPalette.ink)

            if let subtitle, !subtitle.isEmpty {
                Text(subtitle)
                    .font(.subheadline)
                    .foregroundStyle(BrandPalette.muted)
            }
        }
    }
}

struct ContentView: View {
    @Environment(\.openURL) private var openURL
    @EnvironmentObject private var appState: AppState
    @State private var showStartupPrompt = false

    var body: some View {
        ZStack {
            BrandBackdrop()

            VStack(alignment: .leading, spacing: 16) {
                HStack(alignment: .top, spacing: 16) {
                    VStack(alignment: .leading, spacing: 8) {
                        HStack(spacing: 10) {
                            Circle()
                                .fill(BrandPalette.accent)
                                .frame(width: 10, height: 10)

                            Text("mail_summariser")
                                .font(.system(size: 27, weight: .bold))
                                .foregroundStyle(BrandPalette.ink)
                        }

                        Text("Summaries, actions, and logs in one local workspace.")
                            .font(.subheadline)
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
                .padding(10)
                .background(
                    RoundedRectangle(cornerRadius: 24, style: .continuous)
                        .fill(BrandPalette.panelStrong)
                )
                .overlay(
                    RoundedRectangle(cornerRadius: 24, style: .continuous)
                        .stroke(BrandPalette.line, lineWidth: 1)
                )
                .shadow(color: Color.black.opacity(0.05), radius: 16, x: 0, y: 8)
            }
            .padding(22)
        }
        .frame(minWidth: 1000, minHeight: 720)
        .tint(BrandPalette.accent)
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
