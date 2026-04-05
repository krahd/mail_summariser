from typing import Optional

from pydantic import BaseModel, Field


class SearchCriteria(BaseModel):
    keyword: str = ""
    rawSearch: str = ""
    sender: str = ""
    recipient: str = ""
    unreadOnly: bool = True
    readOnly: bool = False
    replied: Optional[bool] = None
    tag: str = ""
    useAnd: bool = True


class SummaryRequest(BaseModel):
    criteria: SearchCriteria
    summaryLength: int = Field(default=5, ge=1, le=10)


class MessageItem(BaseModel):
    id: str
    subject: str
    sender: str
    date: str


class SummaryResponse(BaseModel):
    jobId: str
    messages: list[MessageItem]
    summary: str


class JobAction(BaseModel):
    jobId: str


class ModelDownloadRequest(BaseModel):
    name: str


class ActionLogItem(BaseModel):
    id: str
    timestamp: str
    action: str
    status: str
    details: str
    job_id: str | None = None
    undoable: bool | None = None
    undo_status: str | None = None


class AppSettings(BaseModel):
    dummyMode: bool
    imapHost: str
    imapPort: int
    imapUseSSL: bool
    imapPassword: str
    smtpHost: str
    smtpPort: int
    smtpUseSSL: bool
    smtpPassword: str
    username: str
    recipientEmail: str
    summarisedTag: str
    llmProvider: str
    openaiApiKey: str
    anthropicApiKey: str
    ollamaHost: str
    ollamaAutoStart: bool
    ollamaStartOnStartup: bool
    ollamaStopOnExit: bool
    modelName: str
    backendBaseURL: str


class DummyModeUpdate(BaseModel):
    dummyMode: bool


class BackendRuntimeStatus(BaseModel):
    running: bool
    canShutdown: bool


class OllamaRuntimeStatus(BaseModel):
    installed: bool
    running: bool
    startedByApp: bool
    host: str
    modelName: str
    startupAction: str
    message: str
    installUrl: str


class RuntimeStatusResponse(BaseModel):
    backend: BackendRuntimeStatus
    ollama: OllamaRuntimeStatus


class RuntimeActionResponse(BaseModel):
    status: str
    message: str
    runtime: RuntimeStatusResponse


class DatabaseResetRequest(BaseModel):
    confirmation: str


class DatabaseResetCounts(BaseModel):
    settings: int
    logs: int
    jobs: int
    undo: int


class DatabaseResetResponse(BaseModel):
    status: str
    message: str
    removed: DatabaseResetCounts
    settings: AppSettings


class FakeMailStatusResponse(BaseModel):
    enabled: bool = False
    running: bool = False
    message: str = "Developer fake mail server is disabled."
    imapHost: str = "127.0.0.1"
    imapPort: int = 0
    smtpHost: str = "127.0.0.1"
    smtpPort: int = 0
    username: str = ""
    password: str = ""
    recipientEmail: str = ""
    suggestedSettings: AppSettings | None = None
