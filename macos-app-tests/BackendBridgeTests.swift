import XCTest
@testable import mail_summariser

@MainActor
final class BackendBridgeTests: XCTestCase {
    private func makeBridge(baseURLString: String = "http://127.0.0.1:8766") -> BackendBridge {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [MockURLProtocol.self]
        let session = URLSession(configuration: configuration)
        return BackendBridge(baseURLString: baseURLString, session: session)
    }

    override func tearDown() {
        MockURLProtocol.requestHandler = nil
        super.tearDown()
    }

    func testGetRuntimeStatusDecodesPayloadFromConfiguredBaseURL() async throws {
        MockURLProtocol.requestHandler = { request in
            XCTAssertEqual(request.url?.absoluteString, "http://127.0.0.1:8766/runtime/status")
            XCTAssertEqual(request.httpMethod, "GET")
            let payload = """
            {
              "backend": { "running": true, "canShutdown": true },
              "ollama": {
                "installed": true,
                "running": false,
                "startedByApp": false,
                "host": "http://127.0.0.1:11434",
                "modelName": "llama3.2:latest",
                "startupAction": "start",
                "message": "Ollama is installed but not running.",
                "installUrl": "https://ollama.com/download"
              }
            }
            """.data(using: .utf8)!
            let response = HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: ["Content-Type": "application/json"])!
            return (response, payload)
        }

        let bridge = makeBridge()
        let runtime: RuntimeStatusResponse = try await bridge.get(path: "runtime/status")

        XCTAssertTrue(runtime.backend.running)
        XCTAssertEqual(runtime.ollama.startupAction, "start")
        XCTAssertEqual(runtime.ollama.modelName, "llama3.2:latest")
    }

    func testPostJSONIncludesBodyAndSurfacesBackendErrors() async {
        MockURLProtocol.requestHandler = { request in
            XCTAssertEqual(request.url?.absoluteString, "http://127.0.0.1:8766/runtime/shutdown")
            XCTAssertEqual(request.httpMethod, "POST")
            XCTAssertEqual(request.value(forHTTPHeaderField: "Content-Type"), "application/json")
            let response = HTTPURLResponse(url: request.url!, statusCode: 400, httpVersion: nil, headerFields: ["Content-Type": "text/plain"])!
            return (response, Data("Shutdown not allowed".utf8))
        }

        let bridge = makeBridge()

        do {
            let _: EmptyResponse = try await bridge.postJSON(path: "runtime/shutdown", body: EmptyPayload())
            XCTFail("Expected request to throw")
        } catch {
            XCTAssertTrue(error.localizedDescription.contains("Shutdown not allowed"))
        }
    }

    func testRequestsIncludeBackendAPIKeyWhenConfigured() async throws {
        MockURLProtocol.requestHandler = { request in
            XCTAssertEqual(request.value(forHTTPHeaderField: "X-API-Key"), "secret-key")
            let payload = """
            {
              "ollamaSystemMessage": "Local prompt",
              "openaiSystemMessage": "OpenAI prompt",
              "anthropicSystemMessage": "Anthropic prompt"
            }
            """.data(using: .utf8)!
            let response = HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: ["Content-Type": "application/json"])!
            return (response, payload)
        }

        let bridge = makeBridge()
        bridge.configure(baseURLString: "http://127.0.0.1:8766", apiKey: "secret-key")
        let defaults: SystemMessageDefaultsResponse = try await bridge.get(path: "settings/system-message-defaults")

        XCTAssertEqual(defaults.openaiSystemMessage, "OpenAI prompt")
    }

    func testGetMessageDetailDecodesPayloadFromEncodedPath() async throws {
        MockURLProtocol.requestHandler = { request in
                        XCTAssertEqual(request.url?.absoluteString, "http://127.0.0.1:8766/jobs/job%20123/messages/msg%201")
            XCTAssertEqual(request.httpMethod, "GET")
            let payload = """
            {
                            "id": "msg 1",
              "subject": "Project update",
              "sender": "sender@example.com",
              "recipient": "recipient@example.com",
              "date": "2026-04-05T10:00:00",
              "body": "Here is the full message body."
            }
            """.data(using: .utf8)!
            let response = HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: ["Content-Type": "application/json"])!
            return (response, payload)
        }

        let bridge = makeBridge()
        let detail = try await bridge.getMessageDetail(jobId: "job 123", messageId: "msg 1")

        XCTAssertEqual(detail.id, "msg 1")
        XCTAssertEqual(detail.subject, "Project update")
        XCTAssertEqual(detail.body, "Here is the full message body.")
    }
}
