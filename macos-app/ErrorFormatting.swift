import Foundation

import Foundation

extension Error {
    var userFriendlyMessage: String {
        userFriendlyMessage(self)
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

