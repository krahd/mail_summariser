import XCTest
@testable import MailSummariser

@MainActor
final class AppStateTests: XCTestCase {
    private func makeState() -> AppState {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [MockURLProtocol.self]
        let session = URLSession(configuration: configuration)
        let bridge = BackendBridge(session: session)
        return AppState(bridge: bridge)
    }

    override func tearDown() {
        MockURLProtocol.requestHandler = nil
        super.tearDown()
    }

    func testLoadSettingsUpdatesSettingsAndBridgeBaseURL() async throws {
        MockURLProtocol.requestHandler = { request in
            XCTAssertEqual(request.url?.absoluteString, "http://127.0.0.1:8766/settings")
            let payload = """
            {
              "dummyMode": true,
              "imapHost": "",
              "imapPort": 993,
              "imapUseSSL": true,
              "imapPassword": "",
              "smtpHost": "",
              "smtpPort": 465,
              "smtpUseSSL": true,
              "smtpPassword": "",
              "username": "",
              "recipientEmail": "",
              "summarisedTag": "summarised",
              "llmProvider": "ollama",
              "openaiApiKey": "",
              "anthropicApiKey": "",
              "ollamaHost": "http://127.0.0.1:11434",
              "ollamaAutoStart": true,
              "ollamaStartOnStartup": true,
              "ollamaStopOnExit": false,
              "modelName": "llama3.2:latest",
              "backendBaseURL": "http://127.0.0.1:9999"
            }
            """.data(using: .utf8)!
            let response = HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: ["Content-Type": "application/json"])!
            return (response, payload)
        }

        let appState = makeState()
        try await appState.loadSettings()

        XCTAssertEqual(appState.settings.backendBaseURL, "http://127.0.0.1:9999")
        XCTAssertTrue(appState.settings.ollamaStartOnStartup)
        XCTAssertEqual(appState.bridge.baseURLString, "http://127.0.0.1:9999")
    }

    func testLoadRuntimeStatusUpdatesPublishedRuntimeStatus() async throws {
        MockURLProtocol.requestHandler = { request in
            XCTAssertEqual(request.url?.absoluteString, "http://127.0.0.1:8766/runtime/status")
            let payload = """
            {
              "backend": { "running": true, "canShutdown": true },
              "ollama": {
                "installed": false,
                "running": false,
                "startedByApp": false,
                "host": "http://127.0.0.1:11434",
                "modelName": "llama3.2:latest",
                "startupAction": "install",
                "message": "Ollama CLI not found. Install Ollama to use local models.",
                "installUrl": "https://ollama.com/download"
              }
            }
            """.data(using: .utf8)!
            let response = HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: ["Content-Type": "application/json"])!
            return (response, payload)
        }

        let appState = makeState()
        try await appState.loadRuntimeStatus()

        XCTAssertEqual(appState.runtimeStatus.ollama.startupAction, "install")
        XCTAssertFalse(appState.runtimeStatus.ollama.installed)
    }

    func testStartManagedOllamaUpdatesRuntimeStatus() async throws {
        MockURLProtocol.requestHandler = { request in
            XCTAssertEqual(request.url?.absoluteString, "http://127.0.0.1:8766/runtime/ollama/start")
            XCTAssertEqual(request.httpMethod, "POST")
            let payload = """
            {
              "status": "warning",
              "message": "Ollama is running, but model 'llama3.2:latest' is not installed. Download it from Settings.",
              "runtime": {
                "backend": { "running": true, "canShutdown": true },
                "ollama": {
                  "installed": true,
                  "running": true,
                  "startedByApp": true,
                  "host": "http://127.0.0.1:11434",
                  "modelName": "llama3.2:latest",
                  "startupAction": "none",
                  "message": "Ollama is running, but model 'llama3.2:latest' is not installed. Download it from Settings.",
                  "installUrl": "https://ollama.com/download"
                }
              }
            }
            """.data(using: .utf8)!
            let response = HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: ["Content-Type": "application/json"])!
            return (response, payload)
        }

        let appState = makeState()
        let response = try await appState.startManagedOllama()

        XCTAssertEqual(response.status, "warning")
        XCTAssertTrue(appState.runtimeStatus.ollama.running)
        XCTAssertTrue(appState.runtimeStatus.ollama.startedByApp)
    }

    func testLoadFakeMailStatusUpdatesPublishedState() async throws {
        MockURLProtocol.requestHandler = { request in
            XCTAssertEqual(request.url?.absoluteString, "http://127.0.0.1:8766/dev/fake-mail/status")
            let payload = """
            {
              "enabled": true,
              "running": true,
              "message": "Developer fake mail server is running on localhost.",
              "imapHost": "127.0.0.1",
              "imapPort": 1143,
              "smtpHost": "127.0.0.1",
              "smtpPort": 1025,
              "username": "tester@example.com",
              "password": "test-secret",
              "recipientEmail": "digest@example.com",
              "suggestedSettings": {
                "dummyMode": false,
                "imapHost": "127.0.0.1",
                "imapPort": 1143,
                "imapUseSSL": false,
                "imapPassword": "test-secret",
                "smtpHost": "127.0.0.1",
                "smtpPort": 1025,
                "smtpUseSSL": false,
                "smtpPassword": "test-secret",
                "username": "tester@example.com",
                "recipientEmail": "digest@example.com",
                "summarisedTag": "summarised",
                "llmProvider": "ollama",
                "openaiApiKey": "",
                "anthropicApiKey": "",
                "ollamaHost": "http://127.0.0.1:11434",
                "ollamaAutoStart": false,
                "ollamaStartOnStartup": false,
                "ollamaStopOnExit": false,
                "modelName": "llama3.2:latest",
                "backendBaseURL": "http://127.0.0.1:8766"
              }
            }
            """.data(using: .utf8)!
            let response = HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: ["Content-Type": "application/json"])!
            return (response, payload)
        }

        let appState = makeState()
        try await appState.loadFakeMailStatus()

        XCTAssertTrue(appState.fakeMailStatus.enabled)
        XCTAssertTrue(appState.fakeMailStatus.running)
        XCTAssertEqual(appState.fakeMailStatus.imapPort, 1143)
        XCTAssertEqual(appState.fakeMailStatus.suggestedSettings?.username, "tester@example.com")
    }

    func testStartAndStopFakeMailServerUpdatePublishedState() async throws {
        var requests: [String] = []
        MockURLProtocol.requestHandler = { request in
            requests.append(request.url?.absoluteString ?? "")
            let payload: String
            if request.url?.absoluteString == "http://127.0.0.1:8766/dev/fake-mail/start" {
                payload = """
                {
                  "enabled": true,
                  "running": true,
                  "message": "Developer fake mail server is running on localhost.",
                  "imapHost": "127.0.0.1",
                  "imapPort": 1143,
                  "smtpHost": "127.0.0.1",
                  "smtpPort": 1025,
                  "username": "tester@example.com",
                  "password": "test-secret",
                  "recipientEmail": "digest@example.com",
                  "suggestedSettings": {
                    "dummyMode": false,
                    "imapHost": "127.0.0.1",
                    "imapPort": 1143,
                    "imapUseSSL": false,
                    "imapPassword": "test-secret",
                    "smtpHost": "127.0.0.1",
                    "smtpPort": 1025,
                    "smtpUseSSL": false,
                    "smtpPassword": "test-secret",
                    "username": "tester@example.com",
                    "recipientEmail": "digest@example.com",
                    "summarisedTag": "summarised",
                    "llmProvider": "ollama",
                    "openaiApiKey": "",
                    "anthropicApiKey": "",
                    "ollamaHost": "http://127.0.0.1:11434",
                    "ollamaAutoStart": false,
                    "ollamaStartOnStartup": false,
                    "ollamaStopOnExit": false,
                    "modelName": "llama3.2:latest",
                    "backendBaseURL": "http://127.0.0.1:8766"
                  }
                }
                """
            } else {
                payload = """
                {
                  "enabled": true,
                  "running": false,
                  "message": "Developer fake mail server stopped.",
                  "imapHost": "127.0.0.1",
                  "imapPort": 0,
                  "smtpHost": "127.0.0.1",
                  "smtpPort": 0,
                  "username": "",
                  "password": "",
                  "recipientEmail": "",
                  "suggestedSettings": null
                }
                """
            }
            let response = HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: ["Content-Type": "application/json"])!
            return (response, Data(payload.utf8))
        }

        let appState = makeState()
        let started = try await appState.startFakeMailServer()
        XCTAssertTrue(started.running)
        XCTAssertTrue(appState.fakeMailStatus.running)

        let stopped = try await appState.stopFakeMailServer()
        XCTAssertFalse(stopped.running)
        XCTAssertFalse(appState.fakeMailStatus.running)
        XCTAssertEqual(
            requests,
            [
                "http://127.0.0.1:8766/dev/fake-mail/start",
                "http://127.0.0.1:8766/dev/fake-mail/stop",
            ]
        )
    }

    func testRequestShutdownReturnsBackendStatus() async throws {
        MockURLProtocol.requestHandler = { request in
            XCTAssertEqual(request.url?.absoluteString, "http://127.0.0.1:8766/runtime/shutdown")
            XCTAssertEqual(request.httpMethod, "POST")
            let payload = """
            { "status": "ok", "message": "Mail Summariser is shutting down" }
            """.data(using: .utf8)!
            let response = HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: ["Content-Type": "application/json"])!
            return (response, payload)
        }

        let appState = makeState()
        let response = try await appState.requestShutdown()

        XCTAssertEqual(response.status, "ok")
    }

    func testResetDatabaseClearsWorkspaceAndUpdatesSettings() async throws {
        MockURLProtocol.requestHandler = { request in
            XCTAssertEqual(request.url?.absoluteString, "http://127.0.0.1:8766/admin/database/reset")
            XCTAssertEqual(request.httpMethod, "POST")
            let payload = """
            {
              "status": "ok",
              "message": "Local database reset to defaults.",
              "removed": {
                "settings": 20,
                "logs": 8,
                "jobs": 2,
                "undo": 2
              },
              "settings": {
                "dummyMode": true,
                "imapHost": "",
                "imapPort": 993,
                "imapUseSSL": true,
                "imapPassword": "",
                "smtpHost": "",
                "smtpPort": 465,
                "smtpUseSSL": true,
                "smtpPassword": "",
                "username": "",
                "recipientEmail": "",
                "summarisedTag": "summarised",
                "llmProvider": "ollama",
                "openaiApiKey": "",
                "anthropicApiKey": "",
                "ollamaHost": "http://127.0.0.1:11434",
                "ollamaAutoStart": true,
                "ollamaStartOnStartup": false,
                "ollamaStopOnExit": false,
                "modelName": "llama3.2:latest",
                "backendBaseURL": "http://127.0.0.1:8766"
              }
            }
            """.data(using: .utf8)!
            let response = HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: ["Content-Type": "application/json"])!
            return (response, payload)
        }

        let appState = makeState()
        appState.currentSummary = "Old summary"
        appState.currentMessages = [MessageItem(id: "1", subject: "Subject", sender: "sender@example.com", date: "2026-04-04T12:00:00")]
        appState.selectedJobId = "job-123"

        let response = try await appState.resetDatabase()

        XCTAssertEqual(response.status, "ok")
        XCTAssertTrue(appState.currentSummary.isEmpty)
        XCTAssertTrue(appState.currentMessages.isEmpty)
        XCTAssertTrue(appState.selectedJobId.isEmpty)
        XCTAssertTrue(appState.settings.dummyMode)
    }
}
