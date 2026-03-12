import Foundation

struct SearchCriteria: Codable {
    var keyword: String = ""
    var rawSearch: String = ""
    var sender: String = ""
    var recipient: String = ""
    var unreadOnly: Bool = true
    var readOnly: Bool = false
    var replied: Bool? = nil
    var tag: String = ""
    var useAnd: Bool = true
}

struct SummaryRequest: Codable {
    var criteria: SearchCriteria
    var summaryLength: Int
}

struct MessageItem: Codable, Identifiable {
    var id: String
    var subject: String
    var sender: String
    var date: String
}

struct SummaryResponse: Codable {
    var jobId: String
    var messages: [MessageItem]
    var summary: String
}

struct ActionLogItem: Codable, Identifiable {
    var id: String
    var timestamp: String
    var action: String
    var status: String
    var details: String
    var job_id: String?
}

struct AppSettings: Codable {
    var imapHost: String = ""
    var imapPort: Int = 993
    var smtpHost: String = ""
    var smtpPort: Int = 465
    var username: String = ""
    var recipientEmail: String = ""
    var summarisedTag: String = "summarised"
    var modelName: String = "gpt-5"
    var backendBaseURL: String = "http://127.0.0.1:8766"
}

struct EmptyResponse: Codable {
    let status: String?
}
