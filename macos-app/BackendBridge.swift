import Foundation

enum BackendError: LocalizedError {
    case invalidBaseURL(String)
    case badServerResponse
    case httpError(statusCode: Int, message: String)
    case decodingError(underlying: Error)

    var errorDescription: String? {
        switch self {
        case .invalidBaseURL(let s): return "Invalid base URL: \(s)"
        case .badServerResponse: return "Bad server response"
        case .httpError(_, let message): return message
        case .decodingError(let underlying): return underlying.localizedDescription
        }
    }
}

func userFriendlyMessage(_ error: Error) -> String {
    if let be = error as? BackendError {
        switch be {
        case .invalidBaseURL(let s):
            return "Invalid backend URL: \(s)"
        case .badServerResponse:
            return "Bad server response"
        case .httpError(let status, let message):
            return "Server error \(status): \(message)"
        case .decodingError(let underlying):
            return "Response decode error: \(underlying.localizedDescription)"
        }
    }

    if let urlErr = error as? URLError {
        return urlErr.localizedDescription
    }

    return error.localizedDescription
}

@MainActor
final class BackendBridge: ObservableObject {
    @Published var baseURLString: String
    @Published var apiKey: String
    private let session: URLSession
    private let sleepProvider: (UInt64) async throws -> Void
    private let jitterFactor: Double
    private let jitterProvider: (() -> Double)?

    init(
        baseURLString: String = "http://127.0.0.1:8766",
        apiKey: String = "",
        session: URLSession = .shared,
        sleepProvider: ((UInt64) async throws -> Void)? = nil,
        jitterFactor: Double = 0.0,
        jitterProvider: (() -> Double)? = nil
    ) {
        self.baseURLString = baseURLString
        self.apiKey = apiKey
        self.session = session
        self.sleepProvider = sleepProvider ?? { nanos in try await Task.sleep(nanoseconds: nanos) }
        self.jitterFactor = jitterFactor
        self.jitterProvider = jitterProvider
    }

    func configure(baseURLString: String, apiKey: String? = nil) {
        self.baseURLString = baseURLString
        if let apiKey {
            self.apiKey = apiKey
        }
    }

    private func makeURL(path: String) throws -> URL {
        guard let base = URL(string: baseURLString) else {
            throw BackendError.invalidBaseURL(baseURLString)
        }

        // Prefer URL(relativeTo:) so path slashes are preserved for paths like "runtime/status".
        if let relative = URL(string: path, relativeTo: base) {
            return relative.absoluteURL
        }

        return base.appendingPathComponent(path)
    }

    private func isRetryable(_ error: Error) -> Bool {
        if let be = error as? BackendError {
            switch be {
            case .httpError(let status, _):
                return (500...599).contains(status)
            default:
                return false
            }
        }

        if let urlErr = error as? URLError {
            switch urlErr.code {
            case .timedOut, .networkConnectionLost, .cannotFindHost, .cannotConnectToHost, .dnsLookupFailed, .notConnectedToInternet:
                return true
            default:
                return false
            }
        }

        return false
    }

    private func parseErrorMessage(from data: Data, statusCode: Int) -> String {
        let raw = String(data: data, encoding: .utf8) ?? HTTPURLResponse.localizedString(forStatusCode: statusCode)
        do {
            let obj = try JSONSerialization.jsonObject(with: data, options: [])
            if let dict = obj as? [String: Any] {
                if let m = dict["error"] as? String { return m }
                if let m = dict["message"] as? String { return m }
                if let msgObj = dict["message"] as? [String: Any], let detail = msgObj["detail"] as? String { return detail }
                if let detail = dict["detail"] as? String { return detail }
                if let errors = dict["errors"] as? [[String: Any]], let first = errors.first {
                    if let m = first["message"] as? String { return m }
                    if let d = first["detail"] as? String { return d }
                }
                if let errorsArr = dict["errors"] as? [String], let first = errorsArr.first { return first }
                if let errorObj = dict["error"] as? [String: Any], let msg = errorObj["message"] as? String { return msg }
                if let pretty = try? JSONSerialization.data(withJSONObject: dict, options: [.prettyPrinted]), let s = String(data: pretty, encoding: .utf8) {
                    return s
                }
            } else if let arr = obj as? [Any] {
                if let first = arr.first as? String { return first }
                if let pretty = try? JSONSerialization.data(withJSONObject: arr, options: [.prettyPrinted]), let s = String(data: pretty, encoding: .utf8) {
                    return s
                }
            }
        } catch {
            // fall back to raw
        }
        return raw
    }

    private func retry<T>(attempts: Int = 3, initialDelayNanos: UInt64 = 200_000_000, operation: () async throws -> T) async throws -> T {
        var delay = initialDelayNanos
        for attempt in 0..<attempts {
            do {
                return try await operation()
            } catch {
                if attempt == attempts - 1 {
                    throw error
                }
                if !isRetryable(error) {
                    throw error
                }

                // Apply jitter (if configured) and sleep using the injected sleepProvider
                var toSleep = delay
                if jitterFactor > 0.0 {
                    let rand = jitterProvider?() ?? Double.random(in: -jitterFactor...jitterFactor)
                    let jittered = Double(delay) * (1.0 + rand)
                    toSleep = jittered <= 0 ? 0 : UInt64(jittered)
                }

                try await sleepProvider(toSleep)
                delay = delay &* 2
            }
        }
        // Fallback - should not reach here
        return try await operation()
    }

    func postJSON<T: Encodable, R: Decodable>(path: String, body: T) async throws -> R {
        return try await retry {
            let url = try makeURL(path: path)
            var request = URLRequest(url: url)
            request.httpMethod = "POST"
            request.timeoutInterval = 30
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.setValue("application/json", forHTTPHeaderField: "Accept")
            if !apiKey.isEmpty {
                request.setValue(apiKey, forHTTPHeaderField: "X-API-Key")
            }
            request.httpBody = try JSONEncoder().encode(body)

            let (data, response) = try await session.data(for: request)
            guard let http = response as? HTTPURLResponse else {
                throw BackendError.badServerResponse
            }
            guard (200..<300).contains(http.statusCode) else {
                let parsedMessage = parseErrorMessage(from: data, statusCode: http.statusCode)
                throw BackendError.httpError(statusCode: http.statusCode, message: parsedMessage)
            }
            do {
                return try JSONDecoder().decode(R.self, from: data)
            } catch {
                throw BackendError.decodingError(underlying: error)
            }
        }
    }

    func get<R: Decodable>(path: String) async throws -> R {
        return try await retry {
            let url = try makeURL(path: path)
            var request = URLRequest(url: url)
            request.timeoutInterval = 30
            request.setValue("application/json", forHTTPHeaderField: "Accept")
            if !apiKey.isEmpty {
                request.setValue(apiKey, forHTTPHeaderField: "X-API-Key")
            }
            let (data, response) = try await session.data(for: request)
            guard let http = response as? HTTPURLResponse else {
                throw BackendError.badServerResponse
            }
            guard (200..<300).contains(http.statusCode) else {
                let parsedMessage = parseErrorMessage(from: data, statusCode: http.statusCode)
                throw BackendError.httpError(statusCode: http.statusCode, message: parsedMessage)
            }
            do {
                return try JSONDecoder().decode(R.self, from: data)
            } catch {
                throw BackendError.decodingError(underlying: error)
            }
        }
    }

    func getMessageDetail(jobId: String, messageId: String) async throws -> MessageDetail {
        guard let base = URL(string: baseURLString) else {
            throw BackendError.invalidBaseURL(baseURLString)
        }

        let url = base
            .appendingPathComponent("jobs")
            .appendingPathComponent(jobId)
            .appendingPathComponent("messages")
            .appendingPathComponent(messageId)

        var request = URLRequest(url: url)
        request.timeoutInterval = 30
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        if !apiKey.isEmpty {
            request.setValue(apiKey, forHTTPHeaderField: "X-API-Key")
        }

        return try await retry {
            let (data, response) = try await session.data(for: request)
            guard let http = response as? HTTPURLResponse else {
                throw BackendError.badServerResponse
            }
            guard (200..<300).contains(http.statusCode) else {
                let parsedMessage = parseErrorMessage(from: data, statusCode: http.statusCode)
                throw BackendError.httpError(statusCode: http.statusCode, message: parsedMessage)
            }
            do {
                return try JSONDecoder().decode(MessageDetail.self, from: data)
            } catch {
                throw BackendError.decodingError(underlying: error)
            }
        }
    }
}
