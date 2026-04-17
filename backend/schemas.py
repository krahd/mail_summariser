from __future__ import annotations

from pydantic import BaseModel, Field


class SearchCriteria(BaseModel):
    keyword: str = ''
    rawSearch: str = ''
    sender: str = ''
    recipient: str = ''
    tag: str = ''
    unreadOnly: bool = False
    readOnly: bool = False
    replied: bool | None = None
    useAnd: bool = True


class SummaryRequest(BaseModel):
    criteria: SearchCriteria = Field(default_factory=SearchCriteria)
    summaryLength: int = 5


class MessageItem(BaseModel):
    id: str
    subject: str
    sender: str
    date: str


class MessageDetail(BaseModel):
    id: str
    subject: str
    sender: str
    recipient: str
    date: str
    body: str


class SummaryResponse(BaseModel):
    jobId: str
    messages: list[MessageItem]
    summary: str


class DatabaseResetRequest(BaseModel):
    confirmation: str


class DatabaseResetResponse(BaseModel):
    status: str
    message: str
    removed: dict[str, int]
    settings: 'AppSettings'


class SystemMessageDefaultsResponse(BaseModel):
    ollamaSystemMessage: str
    openaiSystemMessage: str
    anthropicSystemMessage: str


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
    openaiApiKey: str = ''
    anthropicApiKey: str = ''
    ollamaHost: str
    ollamaAutoStart: bool
    ollamaStartOnStartup: bool
    ollamaStopOnExit: bool
    ollamaSystemMessage: str
    openaiSystemMessage: str
    anthropicSystemMessage: str
    modelName: str
    backendBaseURL: str


class DummyModeUpdate(BaseModel):
    dummyMode: bool
