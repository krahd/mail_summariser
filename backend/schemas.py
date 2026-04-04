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
    modelName: str
    backendBaseURL: str


class DummyModeUpdate(BaseModel):
    dummyMode: bool
