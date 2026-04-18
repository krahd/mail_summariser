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

        func testRetryOnTransientNetworkError() async throws {
                var callCount = 0
                MockURLProtocol.requestHandler = { request in
                        callCount += 1
                        if callCount < 3 {
                                throw URLError(.timedOut)
                        }
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

                XCTAssertEqual(callCount, 3)
                XCTAssertTrue(runtime.backend.running)
        }

            func testInvalidBaseURLThrows() async throws {
                // Use an empty base URL string which should fail URL(string:)
                let bridge = makeBridge(baseURLString: "")

                do {
                    let _: RuntimeStatusResponse = try await bridge.get(path: "runtime/status")
                    XCTFail("Expected invalidBaseURL error")
                } catch {
                    if let be = error as? BackendError {
                        switch be {
                        case .invalidBaseURL(let s):
                            XCTAssertEqual(s, "")
                        default:
                            XCTFail("Expected invalidBaseURL, got \(be)")
                        }
                    } else {
                        XCTFail("Expected BackendError, got \(error)")
                    }
                }
            }

            func testRetryOnHTTP5xxSucceeds() async throws {
                var callCount = 0
                MockURLProtocol.requestHandler = { request in
                    callCount += 1
                    if callCount < 3 {
                        let response = HTTPURLResponse(url: request.url!, statusCode: 500, httpVersion: nil, headerFields: ["Content-Type": "text/plain"])!
                        return (response, Data("Server failure".utf8))
                    }
                    let payload = """
                    {
                      "backend": { "running": true, "canShutdown": true },
                      "ollama": { "installed": true, "running": false, "startedByApp": false, "host": "http://127.0.0.1:11434", "modelName": "llama3.2:latest", "startupAction": "start", "message": "OK", "installUrl": "https://ollama.com/download" }
                    }
                    """.data(using: .utf8)!
                    let response = HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: ["Content-Type": "application/json"])!
                    return (response, payload)
                }

                let bridge = makeBridge()
                let runtime: RuntimeStatusResponse = try await bridge.get(path: "runtime/status")

                XCTAssertEqual(callCount, 3)
                XCTAssertTrue(runtime.backend.running)
            }

            func testNoRetryOnHTTP4xx() async throws {
                var callCount = 0
                MockURLProtocol.requestHandler = { request in
                    callCount += 1
                    let response = HTTPURLResponse(url: request.url!, statusCode: 400, httpVersion: nil, headerFields: ["Content-Type": "text/plain"])!
                    return (response, Data("Bad request".utf8))
                }

                let bridge = makeBridge()

                do {
                    let _: RuntimeStatusResponse = try await bridge.get(path: "runtime/status")
                    XCTFail("Expected to throw for 4xx")
                } catch {
                    XCTAssertEqual(callCount, 1)
                    if let be = error as? BackendError {
                        switch be {
                        case .httpError(let status, let msg):
                            XCTAssertEqual(status, 400)
                            XCTAssertTrue(msg.contains("Bad request"))
                        default:
                            XCTFail("Expected httpError, got \(be)")
                        }
                    } else {
                        XCTFail("Expected BackendError, got \(error)")
                    }
                }

                func testBackoffDelaySequence() async throws {
                    var callCount = 0
                    var delays: [UInt64] = []

                    MockURLProtocol.requestHandler = { request in
                        callCount += 1
                        if callCount < 3 {
                            throw URLError(.timedOut)
                        }
                        let payload = """
                        {
                          "backend": { "running": true, "canShutdown": true },
                          "ollama": { "installed": true, "running": false, "startedByApp": false, "host": "http://127.0.0.1:11434", "modelName": "llama3.2:latest", "startupAction": "start", "message": "OK", "installUrl": "https://ollama.com/download" }
                        }
                        """.data(using: .utf8)!
                        let response = HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: ["Content-Type": "application/json"])!
                        return (response, payload)
                    }

                    let configuration = URLSessionConfiguration.ephemeral
                    configuration.protocolClasses = [MockURLProtocol.self]
                    let session = URLSession(configuration: configuration)

                    let bridge = BackendBridge(baseURLString: "http://127.0.0.1:8766", session: session, sleepProvider: { nanos in
                        delays.append(nanos)
                    }, jitterFactor: 0.0)

                    let runtime: RuntimeStatusResponse = try await bridge.get(path: "runtime/status")

                    XCTAssertEqual(callCount, 3)
                    XCTAssertEqual(delays.count, 2)
                    XCTAssertEqual(delays[0], 200_000_000)
                    XCTAssertEqual(delays[1], 400_000_000)
                    XCTAssertTrue(runtime.backend.running)
                }

                func testBackoffWithJitterProviderUsed() async throws {
                    var callCount = 0
                    var delays: [UInt64] = []
                    var jitterValues: [Double] = [-0.5, 0.25]

                    MockURLProtocol.requestHandler = { request in
                        callCount += 1
                        if callCount < 3 {
                            throw URLError(.timedOut)
                        }
                        let payload = """
                        {
                          "backend": { "running": true, "canShutdown": true },
                          "ollama": { "installed": true, "running": false }
                        }
                        """.data(using: .utf8)!
                        let response = HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: ["Content-Type": "application/json"])!
                        return (response, payload)
                    }

                    let configuration = URLSessionConfiguration.ephemeral
                    configuration.protocolClasses = [MockURLProtocol.self]
                    let session = URLSession(configuration: configuration)

                    let jitterProvider: () -> Double = {
                        return jitterValues.removeFirst()
                    }

                    let bridge = BackendBridge(baseURLString: "http://127.0.0.1:8766", session: session, sleepProvider: { nanos in
                        delays.append(nanos)
                    }, jitterFactor: 0.5, jitterProvider: jitterProvider)

                    let runtime: RuntimeStatusResponse = try await bridge.get(path: "runtime/status")

                    XCTAssertEqual(callCount, 3)
                    XCTAssertEqual(delays.count, 2)
                    // first delay = 200_000_000 * (1 - 0.5) = 100_000_000
                    XCTAssertEqual(delays[0], 100_000_000)
                    // second delay = 400_000_000 * (1 + 0.25) = 500_000_000
                    XCTAssertEqual(delays[1], 500_000_000)
                    XCTAssertTrue(runtime.backend.running)
                }

                func testServerErrorPayloadParsing() async throws {
                    MockURLProtocol.requestHandler = { request in
                        let payload = "{ \"error\": \"Bad token\", \"code\": 401 }".data(using: .utf8)!
                        let response = HTTPURLResponse(url: request.url!, statusCode: 401, httpVersion: nil, headerFields: ["Content-Type": "application/json"])!
                        return (response, payload)
                    }

                    let bridge = makeBridge()

                    do {
                        let _: RuntimeStatusResponse = try await bridge.get(path: "runtime/status")
                        XCTFail("Expected HTTP error to be thrown")
                    } catch {
                        if let be = error as? BackendError {
                            switch be {
                            case .httpError(let status, let msg):
                                XCTAssertEqual(status, 401)
                                XCTAssertEqual(msg, "Bad token")
                            default:
                                XCTFail("Expected httpError, got \(be)")
                            }
                        } else {
                            XCTFail("Expected BackendError, got \(error)")
                        }
                    }
                }
            }

            func testGetDecodingFailureReturnsDecodingError() async throws {
                MockURLProtocol.requestHandler = { request in
                    let payload = "not json".data(using: .utf8)!
                    let response = HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: ["Content-Type": "application/json"])!
                    return (response, payload)
                }

                let bridge = makeBridge()

                do {
                    let _: RuntimeStatusResponse = try await bridge.get(path: "runtime/status")
                    XCTFail("Expected decoding error")
                } catch {
                    if let be = error as? BackendError {
                        switch be {
                        case .decodingError(let underlying):
                            XCTAssert(underlying is DecodingError)
                        default:
                            XCTFail("Expected decodingError, got \(be)")
                        }
                    } else {
                        XCTFail("Expected BackendError, got \(error)")
                    }
                }
            }

    func testServerErrorFormats() async throws {
        // errors array -> first.message
        MockURLProtocol.requestHandler = { request in
            let payload = "{ \"errors\": [{ \"message\": \"Token expired\" }] }".data(using: .utf8)!
            let response = HTTPURLResponse(url: request.url!, statusCode: 401, httpVersion: nil, headerFields: ["Content-Type": "application/json"])!
            return (response, payload)
        }

        var bridge = makeBridge()
        do {
            let _: RuntimeStatusResponse = try await bridge.get(path: "runtime/status")
            XCTFail("Expected HTTP error")
        } catch {
            if let be = error as? BackendError {
                switch be {
                case .httpError(let status, let msg):
                    XCTAssertEqual(status, 401)
                    XCTAssertEqual(msg, "Token expired")
                default:
                    XCTFail("Expected httpError, got \(be)")
                }
            } else {
                XCTFail("Expected BackendError, got \(error)")
            }
        }

        // message object with nested detail
        MockURLProtocol.requestHandler = { request in
            let payload = "{ \"message\": { \"detail\": \"Invalid token detail\" } }".data(using: .utf8)!
            let response = HTTPURLResponse(url: request.url!, statusCode: 403, httpVersion: nil, headerFields: ["Content-Type": "application/json"])!
            return (response, payload)
        }

        do {
            let _: RuntimeStatusResponse = try await bridge.get(path: "runtime/status")
            XCTFail("Expected HTTP error")
        } catch {
            if let be = error as? BackendError {
                switch be {
                case .httpError(let status, let msg):
                    XCTAssertEqual(status, 403)
                    XCTAssertEqual(msg, "Invalid token detail")
                default:
                    XCTFail("Expected httpError, got \(be)")
                }
            } else {
                XCTFail("Expected BackendError, got \(error)")
            }
        }

        // top-level array error payload
        MockURLProtocol.requestHandler = { request in
            let payload = "[\"Array error message\"]".data(using: .utf8)!
            let response = HTTPURLResponse(url: request.url!, statusCode: 500, httpVersion: nil, headerFields: ["Content-Type": "application/json"])!
            return (response, payload)
        }

        do {
            let _: RuntimeStatusResponse = try await bridge.get(path: "runtime/status")
            XCTFail("Expected HTTP error")
        } catch {
            if let be = error as? BackendError {
                switch be {
                case .httpError(let status, let msg):
                    XCTAssertEqual(status, 500)
                    XCTAssertTrue(msg.contains("Array error message"))
                default:
                    XCTFail("Expected httpError, got \(be)")
                }
            } else {
                XCTFail("Expected BackendError, got \(error)")
            }
        }
    }

    func testRandomizedJitterBounds() async throws {
        var callCount = 0
        var delays: [UInt64] = []
        var jitterValues: [Double] = [-0.45, 0.12]

        MockURLProtocol.requestHandler = { request in
            callCount += 1
            if callCount < 3 {
                throw URLError(.timedOut)
            }
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

        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [MockURLProtocol.self]
        let session = URLSession(configuration: configuration)

        let jitterProvider: () -> Double = {
            return jitterValues.removeFirst()
        }

        let bridge = BackendBridge(baseURLString: "http://127.0.0.1:8766", session: session, sleepProvider: { nanos in
            delays.append(nanos)
        }, jitterFactor: 0.5, jitterProvider: jitterProvider)

        let runtime: RuntimeStatusResponse = try await bridge.get(path: "runtime/status")

        XCTAssertEqual(callCount, 3)
        XCTAssertEqual(delays.count, 2)
        let expected0 = UInt64(Double(200_000_000) * (1.0 + (-0.45)))
        let expected1 = UInt64(Double(400_000_000) * (1.0 + 0.12))
        XCTAssertEqual(delays[0], expected0)
        XCTAssertEqual(delays[1], expected1)
        XCTAssertTrue(runtime.backend.running)
    }
}
