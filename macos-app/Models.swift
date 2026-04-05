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

struct MessageDetail: Codable, Identifiable {
    var id: String
    var subject: String
    var sender: String
    var recipient: String
    var date: String
    var body: String
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
    var undoable: Bool?
    var undo_status: String?
}

struct AppSettings: Codable {
    var dummyMode: Bool = true
    var imapHost: String = ""
    var imapPort: Int = 993
    var imapUseSSL: Bool = true
    var imapPassword: String = ""
    var smtpHost: String = ""
    var smtpPort: Int = 465
    var smtpUseSSL: Bool = true
    var smtpPassword: String = ""
    var username: String = ""
    var recipientEmail: String = ""
    var summarisedTag: String = "summarised"
    var llmProvider: String = "ollama"
    var openaiApiKey: String = ""
    var anthropicApiKey: String = ""
    var ollamaHost: String = "http://127.0.0.1:11434"
    var ollamaAutoStart: Bool = true
    var ollamaStartOnStartup: Bool = false
    var ollamaStopOnExit: Bool = false
    var ollamaSystemMessage: String = "You create compact, practical email digests that focus on priorities, deadlines, and follow-up actions."
    var openaiSystemMessage: String = "You are an assistant that creates compact, practical email digests."
    var anthropicSystemMessage: String = "You create practical, concise email summaries with action cues."
    var modelName: String = "llama3.2:latest"
    var backendBaseURL: String = "http://127.0.0.1:8766"
}

struct SystemMessageDefaultsResponse: Codable {
    var ollamaSystemMessage: String = "You create compact, practical email digests that focus on priorities, deadlines, and follow-up actions."
    var openaiSystemMessage: String = "You are an assistant that creates compact, practical email digests."
    var anthropicSystemMessage: String = "You create practical, concise email summaries with action cues."
}

struct EmptyResponse: Codable {
    let status: String?
    let message: String?
}

struct EmptyPayload: Codable {}

struct ConnectionComponent: Codable {
    let status: String
    let message: String
}

struct ConnectionTestResponse: Codable {
    let status: String
    let mode: String
    let imap: ConnectionComponent
    let smtp: ConnectionComponent
}

struct BackendRuntimeStatus: Codable {
    var running: Bool = true
    var canShutdown: Bool = true
}

struct OllamaRuntimeStatus: Codable {
    var installed: Bool = false
    var running: Bool = false
    var startedByApp: Bool = false
    var host: String = "http://127.0.0.1:11434"
    var modelName: String = "llama3.2:latest"
    var startupAction: String = "none"
    var message: String = "Runtime status not loaded yet."
    var installUrl: String = "https://ollama.com/download"
}

struct RuntimeStatusResponse: Codable {
    var backend = BackendRuntimeStatus()
    var ollama = OllamaRuntimeStatus()
}

struct RuntimeActionResponse: Codable {
    let status: String
    let message: String
    let runtime: RuntimeStatusResponse
}

struct DatabaseResetCounts: Codable {
    var settings: Int
    var logs: Int
    var jobs: Int
    var undo: Int
}

struct DatabaseResetResponse: Codable {
    var status: String
    var message: String
    var removed: DatabaseResetCounts
    var settings: AppSettings
}

struct FakeMailStatusResponse: Codable {
    var enabled: Bool = false
    var running: Bool = false
    var message: String = "Developer fake mail server is disabled."
    var imapHost: String = "127.0.0.1"
    var imapPort: Int = 0
    var smtpHost: String = "127.0.0.1"
    var smtpPort: Int = 0
    var username: String = ""
    var password: String = ""
    var recipientEmail: String = ""
    var suggestedSettings: AppSettings? = nil
}

struct ConfirmationPayload: Codable {
    let confirmation: String
}
