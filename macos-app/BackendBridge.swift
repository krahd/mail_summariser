import Foundation

@MainActor
final class BackendBridge: ObservableObject {
    @Published var baseURLString: String
    private let session: URLSession

    init(baseURLString: String = "http://127.0.0.1:8766", session: URLSession = .shared) {
        self.baseURLString = baseURLString
        self.session = session
    }

    private var baseURL: URL {
        URL(string: baseURLString)!
    }

    func configure(baseURLString: String) {
        self.baseURLString = baseURLString
    }

    func postJSON<T: Encodable, R: Decodable>(path: String, body: T) async throws -> R {
        let url = baseURL.appendingPathComponent(path)
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONEncoder().encode(body)

        let (data, response) = try await session.data(for: request)
        guard let http = response as? HTTPURLResponse else {
            throw URLError(.badServerResponse)
        }
        guard (200..<300).contains(http.statusCode) else {
            let message = String(data: data, encoding: .utf8) ?? "Unknown error"
            throw NSError(domain: "BackendError", code: http.statusCode, userInfo: [NSLocalizedDescriptionKey: message])
        }
        return try JSONDecoder().decode(R.self, from: data)
    }

    func get<R: Decodable>(path: String) async throws -> R {
        let url = baseURL.appendingPathComponent(path)
        let (data, response) = try await session.data(from: url)
        guard let http = response as? HTTPURLResponse else {
            throw URLError(.badServerResponse)
        }
        guard (200..<300).contains(http.statusCode) else {
            let message = String(data: data, encoding: .utf8) ?? "Unknown error"
            throw NSError(domain: "BackendError", code: http.statusCode, userInfo: [NSLocalizedDescriptionKey: message])
        }
        return try JSONDecoder().decode(R.self, from: data)
    }
}
