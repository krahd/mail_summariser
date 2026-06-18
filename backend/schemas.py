from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator


class MailboxInfo(BaseModel):
    accountId: str
    path: str
    delimiter: str | None = None
    selectable: bool = True
    flags: list[str] = Field(default_factory=list)
    displayName: str = ''


class MailAccountSettings(BaseModel):
    id: str = ''
    displayName: str = ''
    enabled: bool = True
    imapHost: str = ''
    imapPort: int = 993
    imapUseSSL: bool = True
    username: str = ''
    imapPassword: str = ''
    smtpHost: str = ''
    smtpPort: int = 465
    smtpUseSSL: bool = True
    smtpPassword: str = ''
    recipientEmail: str = ''
    archiveMailbox: str = 'Archive'
    indexMailboxes: list[str] = Field(default_factory=list)


class SearchCriteria(BaseModel):
    accountIds: list[str] = Field(default_factory=list)
    mailboxes: list[str] = Field(default_factory=list)
    keyword: str = ''
    rawSearch: str = ''
    sender: str = ''
    recipient: str = ''
    tag: str = ''
    unreadOnly: bool = False
    readOnly: bool = False
    flagged: bool | None = None
    since: str = ''
    before: str = ''
    listId: str = ''
    replied: bool | None = None
    useAnd: bool = True
    limit: int = 100

    @field_validator('limit', mode='before')
    @classmethod
    def _clamp_limit(cls, value: object) -> int:
        if value in (None, ''):
            return 100
        try:
            numeric = int(value)
        except (TypeError, ValueError):
            return value  # type: ignore[return-value]
        return max(1, min(numeric, 500))


class SummaryRequest(BaseModel):
    criteria: SearchCriteria = Field(default_factory=SearchCriteria)
    summaryLength: int = 5


class MailIndexSyncRequest(BaseModel):
    accountId: str = ''
    mailbox: str = 'INBOX'
    limit: int = 500

    @field_validator('limit', mode='before')
    @classmethod
    def _clamp_limit(cls, value: object) -> int:
        if value in (None, ''):
            return 500
        try:
            numeric = int(value)
        except (TypeError, ValueError):
            return value  # type: ignore[return-value]
        return max(1, min(numeric, 500))


class MailIndexSyncResponse(BaseModel):
    accountId: str
    mailbox: str
    scanned: int
    indexed: int
    errors: int


class MailIndexMessageSummary(BaseModel):
    id: str
    accountId: str
    mailboxPath: str
    uid: str
    messageIdHeader: str = ''
    subject: str
    sender: str
    recipients: list[str] = Field(default_factory=list)
    date: str
    flags: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    listId: str = ''
    bodyPreview: str = ''
    bodyCached: bool = False
    lastSeenAt: str


class MailIndexMessageDetail(MailIndexMessageSummary):
    bodyText: str = ''


class TriageBucketMessage(MailIndexMessageSummary):
    reasons: list[str] = Field(default_factory=list)


class TriageBucket(BaseModel):
    id: str
    label: str
    description: str
    count: int
    thresholdDays: int | None = None
    messages: list[TriageBucketMessage] = Field(default_factory=list)


class TriageDashboardTotals(BaseModel):
    messages: int
    unread: int
    flagged: int


class TriageDashboardResponse(BaseModel):
    scopeId: str
    generatedAt: str
    totals: TriageDashboardTotals
    buckets: list[TriageBucket] = Field(default_factory=list)


class TriageBucketSummaryRequest(BaseModel):
    scopeId: str = ''
    summaryLength: int = 5
    limitPerBucket: int = 5
    staleDays: int = 14

    @field_validator('summaryLength', mode='before')
    @classmethod
    def _clamp_summary_length(cls, value: object) -> int:
        if value in (None, ''):
            return 5
        try:
            numeric = int(value)
        except (TypeError, ValueError):
            return value  # type: ignore[return-value]
        return max(1, min(numeric, 24))

    @field_validator('limitPerBucket', mode='before')
    @classmethod
    def _clamp_limit_per_bucket(cls, value: object) -> int:
        if value in (None, ''):
            return 5
        try:
            numeric = int(value)
        except (TypeError, ValueError):
            return value  # type: ignore[return-value]
        return max(1, min(numeric, 100))

    @field_validator('staleDays', mode='before')
    @classmethod
    def _clamp_stale_days(cls, value: object) -> int:
        if value in (None, ''):
            return 14
        try:
            numeric = int(value)
        except (TypeError, ValueError):
            return value  # type: ignore[return-value]
        return max(1, min(numeric, 365))


class SavedScope(BaseModel):
    id: str
    name: str
    description: str = ''
    query: dict[str, Any] = Field(default_factory=dict)
    sortOrder: int = 0


class SavedScopeCreateRequest(BaseModel):
    id: str | None = None
    name: str
    description: str = ''
    query: dict[str, Any] = Field(default_factory=dict)
    sortOrder: int = 0


class SavedScopeSummaryRequest(BaseModel):
    summaryLength: int = 5
    limit: int = 200

    @field_validator('summaryLength', mode='before')
    @classmethod
    def _clamp_summary_length(cls, value: object) -> int:
        if value in (None, ''):
            return 5
        try:
            numeric = int(value)
        except (TypeError, ValueError):
            return value  # type: ignore[return-value]
        return max(1, min(numeric, 24))

    @field_validator('limit', mode='before')
    @classmethod
    def _clamp_limit(cls, value: object) -> int:
        if value in (None, ''):
            return 200
        try:
            numeric = int(value)
        except (TypeError, ValueError):
            return value  # type: ignore[return-value]
        return max(1, min(numeric, 200))


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
    archiveMailbox: str = 'Archive'
    safeMode: bool = True
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
    mailAccounts: list[MailAccountSettings] = Field(default_factory=list)


class DummyModeUpdate(BaseModel):
    dummyMode: bool


class ActionPreviewItem(BaseModel):
    id: str
    accountId: str = ''
    mailboxPath: str = ''
    uid: str = ''
    subject: str = ''
    sender: str = ''
    currentState: str = ''
    plannedState: str = ''
    willChange: bool = True
    reason: str = ''


class ActionPreviewGroup(BaseModel):
    accountId: str
    mailboxPath: str
    changeCount: int = 0
    skipCount: int = 0


class ActionPreview(BaseModel):
    jobId: str
    action: str
    tag: str = ''
    targetMailbox: str = ''
    totalMessages: int = 0
    changeCount: int = 0
    skipCount: int = 0
    items: list[ActionPreviewItem] = Field(default_factory=list)
    skipped: list[ActionPreviewItem] = Field(default_factory=list)
    groups: list[ActionPreviewGroup] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    safeMode: bool = True


class ActionApplyResult(BaseModel):
    status: str = 'ok'
    jobId: str
    action: str
    applied: bool
    safeMode: bool = True
    changedIds: list[str] = Field(default_factory=list)
    failedIds: list[str] = Field(default_factory=list)
    skippedIds: list[str] = Field(default_factory=list)
    logId: str = ''
    preview: ActionPreview
