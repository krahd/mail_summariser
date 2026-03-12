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


class ActionLogItem(BaseModel):
    id: str
    timestamp: str
    action: str
    status: str
    details: str
    job_id: str | None = None


class AppSettings(BaseModel):
    imapHost: str = ""
    imapPort: int = 993
    smtpHost: str = ""
    smtpPort: int = 465
    username: str = ""
    recipientEmail: str = ""
    summarisedTag: str = "summarised"
    modelName: str = "gpt-5"
    backendBaseURL: str = "http://127.0.0.1:8765"
