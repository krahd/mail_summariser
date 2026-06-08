from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import re
from typing import Any

from backend.saved_scope_service import list_all_messages_for_scope


DEFAULT_TRIAGE_SCOPE_ID = 'unread_or_flagged_all'
DEFAULT_STALE_DAYS = 14
DEFAULT_RECENT_DAYS = 7

_REPLY_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ('could you', re.compile(r'\bcould you\b', re.IGNORECASE)),
    ('can you', re.compile(r'\bcan you\b', re.IGNORECASE)),
    ('would you', re.compile(r'\bwould you\b', re.IGNORECASE)),
    ('please', re.compile(r'\bplease\b', re.IGNORECASE)),
    ('confirm', re.compile(r'\bconfirm\b', re.IGNORECASE)),
    ('let me know', re.compile(r'\blet me know\b', re.IGNORECASE)),
)
_DEADLINE_WORDS = ('deadline', 'due', 'vence', 'vencimiento', 'submit', 'cierre', 'closes')
_DEADLINE_CONTEXT_PATTERN = re.compile(
    r'\b(?:by|before|until|due|deadline|submit|closes|cierre|vence|vencimiento)\b',
    re.IGNORECASE,
)
_DATE_PATTERN = re.compile(
    r'\b(?:'
    r'\d{4}-\d{1,2}-\d{1,2}'
    r'|\d{1,2}/\d{1,2}(?:/\d{2,4})?'
    r'|(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*\s+\d{1,2}'
    r'|(?:mon|tue|wed|thu|fri|sat|sun)\w*'
    r')\b',
    re.IGNORECASE,
)
_LIST_KEYWORD_PATTERN = re.compile(r'^(?:list[_-].+|list_fing)$', re.IGNORECASE)


@dataclass
class _BucketAccumulator:
    id: str
    label: str
    description: str
    threshold_days: int | None = None
    count: int = 0
    messages: list[dict[str, Any]] = field(default_factory=list)

    def add_message(self, message: dict[str, Any], reasons: list[str], limit: int,
                    include_body_text: bool) -> None:
        self.count += 1
        if len(self.messages) >= limit:
            return
        projected = _project_message(message, reasons, include_body_text=include_body_text)
        self.messages.append(projected)

    def to_payload(self) -> dict[str, Any]:
        return {
            'id': self.id,
            'label': self.label,
            'description': self.description,
            'count': self.count,
            'thresholdDays': self.threshold_days,
            'messages': self.messages,
        }


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _normalise_text(value: Any) -> str:
    return str(value or '').strip()


def _normalise_text_list(value: Any) -> list[str]:
    if value in (None, ''):
        return []
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, (list, tuple, set)):
        values = list(value)
    else:
        values = [value]

    results: list[str] = []
    seen: set[str] = set()
    for item in values:
        text = _normalise_text(item)
        if not text:
            continue
        lowered = text.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        results.append(text)
    return results


def _message_text(message: dict[str, Any]) -> str:
    recipients = message.get('recipients') or []
    if not isinstance(recipients, list):
        recipients = [recipients]
    keywords = message.get('keywords') or []
    if not isinstance(keywords, list):
        keywords = [keywords]
    parts = [
        message.get('subject', ''),
        message.get('sender', ''),
        ' '.join(str(item) for item in recipients),
        message.get('listId', ''),
        message.get('bodyPreview', ''),
        message.get('bodyText', ''),
        ' '.join(str(item) for item in keywords),
    ]
    return ' '.join(str(part) for part in parts if str(part).strip()).lower()


def _message_flags(message: dict[str, Any]) -> set[str]:
    flags = message.get('flags') or []
    if not isinstance(flags, list):
        flags = [flags]
    return {str(flag).strip().lower() for flag in flags if str(flag).strip()}


def _parse_message_datetime(value: Any) -> datetime | None:
    text = _normalise_text(value)
    if not text:
        return None

    try:
        parsed = datetime.fromisoformat(text.replace('Z', '+00:00'))
    except ValueError:
        try:
            parsed = parsedate_to_datetime(text)
        except (TypeError, ValueError):
            return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _message_age_days(message: dict[str, Any], reference_time: datetime | None = None) -> int | None:
    parsed = _parse_message_datetime(message.get('date', ''))
    if parsed is None:
        return None
    reference = reference_time or _now_utc()
    delta = reference - parsed
    if delta.total_seconds() <= 0:
        return 0
    return int(delta.total_seconds() // 86400)


def _reply_needed_reasons(message: dict[str, Any]) -> list[str]:
    text = _message_text(message)
    reasons: list[str] = []
    if '?' in text:
        reasons.append('contains a question mark')
    for label, pattern in _REPLY_PATTERNS:
        if pattern.search(text):
            reasons.append(f'contains "{label}"')
    return reasons


def _deadline_reasons(message: dict[str, Any]) -> list[str]:
    text = _message_text(message)
    reasons: list[str] = []
    for word in _DEADLINE_WORDS:
        if re.search(rf'\b{re.escape(word)}\b', text):
            reasons.append(f'contains "{word}"')
    if reasons:
        return reasons
    if _DATE_PATTERN.search(text) and _DEADLINE_CONTEXT_PATTERN.search(text):
        return ['contains deadline-like date wording']
    return []


def _mailing_list_reasons(message: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    list_id = _normalise_text(message.get('listId', ''))
    if list_id:
        reasons.append('List-Id header present')

    keywords = _normalise_text_list(message.get('keywords'))
    list_keywords = [keyword for keyword in keywords if _LIST_KEYWORD_PATTERN.match(keyword)]
    if list_keywords:
        if any(keyword.lower() == 'list_fing' for keyword in list_keywords):
            reasons.append('keyword List_Fing')
        else:
            reasons.append('list keyword present')
    return reasons


def _bucket_definitions(stale_days: int, recent_days: int) -> list[dict[str, Any]]:
    return [
        {
            'id': 'reply_needed_candidates',
            'label': 'Reply-needed candidates',
            'description': 'Heuristic candidates from question marks and request phrases; not a certainty.',
            'threshold_days': None,
        },
        {
            'id': 'flagged',
            'label': 'Flagged',
            'description': 'Messages with the IMAP \\Flagged flag set.',
            'threshold_days': None,
        },
        {
            'id': 'deadlines',
            'label': 'Deadlines',
            'description': 'Messages with deadline words or deadline-like date wording in the subject or body.',
            'threshold_days': None,
        },
        {
            'id': 'mailing_lists',
            'label': 'Mailing lists',
            'description': 'Messages with a List-Id header or list tags such as List_Fing.',
            'threshold_days': None,
        },
        {
            'id': 'stale_unread',
            'label': 'Stale unread',
            'description': f'Unread messages older than {stale_days} days.',
            'threshold_days': stale_days,
        },
        {
            'id': 'bulk_archive_candidates',
            'label': 'Bulk archive candidates',
            'description': f'Read messages or unread messages older than {stale_days} days, excluding flagged mail.',
            'threshold_days': stale_days,
        },
        {
            'id': 'recent_unread',
            'label': 'Recent unread',
            'description': f'Unread messages from the last {recent_days} days.',
            'threshold_days': recent_days,
        },
    ]


def _project_message(message: dict[str, Any], reasons: list[str], *,
                     include_body_text: bool) -> dict[str, Any]:
    recipients = message.get('recipients') or []
    if not isinstance(recipients, list):
        recipients = [recipients]
    flags = _normalise_text_list(message.get('flags'))
    keywords = _normalise_text_list(message.get('keywords'))
    projected = {
        'id': _normalise_text(message.get('id')),
        'accountId': _normalise_text(message.get('accountId')),
        'mailboxPath': _normalise_text(message.get('mailboxPath')),
        'uid': _normalise_text(message.get('uid')),
        'messageIdHeader': _normalise_text(message.get('messageIdHeader')),
        'subject': _normalise_text(message.get('subject')),
        'sender': _normalise_text(message.get('sender')),
        'recipients': [str(item) for item in recipients if _normalise_text(item)],
        'date': _normalise_text(message.get('date')),
        'flags': flags,
        'keywords': keywords,
        'listId': _normalise_text(message.get('listId')),
        'bodyPreview': _normalise_text(message.get('bodyPreview')),
        'bodyCached': bool(message.get('bodyCached', False)),
        'lastSeenAt': _normalise_text(message.get('lastSeenAt')),
        'reasons': reasons,
    }
    if include_body_text:
        projected['bodyText'] = _normalise_text(message.get('bodyText'))
    return projected


def _classify_message(message: dict[str, Any], *, stale_days: int, recent_days: int,
                      reference_time: datetime) -> dict[str, list[str]]:
    flags = _message_flags(message)
    is_unread = '\\seen' not in flags
    is_flagged = '\\flagged' in flags
    age_days = _message_age_days(message, reference_time)

    matches: dict[str, list[str]] = {}

    reply_reasons = _reply_needed_reasons(message)
    if reply_reasons:
        matches['reply_needed_candidates'] = reply_reasons

    if is_flagged:
        matches['flagged'] = ['\\Flagged flag set']

    deadline_reasons = _deadline_reasons(message)
    if deadline_reasons:
        matches['deadlines'] = deadline_reasons

    mailing_list_reasons = _mailing_list_reasons(message)
    if mailing_list_reasons:
        matches['mailing_lists'] = mailing_list_reasons

    if is_unread and age_days is not None and age_days >= stale_days:
        matches['stale_unread'] = [f'unread for about {age_days} days (threshold {stale_days} days)']

    if is_unread and age_days is not None and age_days <= recent_days:
        matches['recent_unread'] = [f'unread for about {age_days} days (threshold {recent_days} days)']

    if not is_flagged and (
        (not is_unread) or (is_unread and age_days is not None and age_days >= stale_days)
    ):
        reasons: list[str] = []
        if not is_unread:
            reasons.append('already read')
        if is_unread and age_days is not None and age_days >= stale_days:
            reasons.append(f'unread older than {stale_days} days')
        if reasons:
            matches['bulk_archive_candidates'] = reasons

    return matches


def _resolve_scope_id(scope_id: str | None) -> str:
    resolved = _normalise_text(scope_id)
    return resolved or DEFAULT_TRIAGE_SCOPE_ID


def _clamp_limit(limit_per_bucket: int | str | None) -> int:
    try:
        value = int(limit_per_bucket if limit_per_bucket is not None else 5)
    except (TypeError, ValueError):
        value = 5
    return max(1, min(value, 100))


def _clamp_stale_days(stale_days: int | str | None) -> int:
    try:
        value = int(stale_days if stale_days is not None else DEFAULT_STALE_DAYS)
    except (TypeError, ValueError):
        value = DEFAULT_STALE_DAYS
    return max(1, min(value, 365))


def build_triage_dashboard(scope_id: str | None = None, limit_per_bucket: int | str | None = 5,
                           stale_days: int | str | None = DEFAULT_STALE_DAYS,
                           include_body_text: bool = False) -> dict[str, Any]:
    resolved_scope_id = _resolve_scope_id(scope_id)
    safe_limit = _clamp_limit(limit_per_bucket)
    safe_stale_days = _clamp_stale_days(stale_days)
    recent_days = max(1, min(DEFAULT_RECENT_DAYS, safe_stale_days))
    reference_time = _now_utc()

    scoped_messages = list_all_messages_for_scope(
        resolved_scope_id,
        include_body_text=include_body_text,
    )
    buckets = [
        _BucketAccumulator(**bucket_definition)
        for bucket_definition in _bucket_definitions(safe_stale_days, recent_days)
    ]
    bucket_lookup = {bucket.id: bucket for bucket in buckets}

    unread_count = 0
    flagged_count = 0
    for message in scoped_messages:
        flags = _message_flags(message)
        is_unread = '\\seen' not in flags
        is_flagged = '\\flagged' in flags
        if is_unread:
            unread_count += 1
        if is_flagged:
            flagged_count += 1

        matches = _classify_message(
            message,
            stale_days=safe_stale_days,
            recent_days=recent_days,
            reference_time=reference_time,
        )
        for bucket_id, reasons in matches.items():
            bucket_lookup[bucket_id].add_message(message, reasons, safe_limit, include_body_text)

    return {
        'scopeId': resolved_scope_id,
        'generatedAt': reference_time.isoformat(timespec='seconds'),
        'totals': {
            'messages': len(scoped_messages),
            'unread': unread_count,
            'flagged': flagged_count,
        },
        'buckets': [bucket.to_payload() for bucket in buckets],
    }


def build_triage_bucket_summary_data(scope_id: str | None, bucket_id: str,
                                     limit_per_bucket: int | str | None,
                                     stale_days: int | str | None) -> tuple[dict[str, Any], dict[str, Any]]:
    dashboard = build_triage_dashboard(
        scope_id=scope_id,
        limit_per_bucket=limit_per_bucket,
        stale_days=stale_days,
        include_body_text=True,
    )
    bucket = next((item for item in dashboard['buckets'] if item['id'] == bucket_id), None)
    if bucket is None:
        raise LookupError(f'Triage bucket {bucket_id!r} not found')
    return dashboard, bucket


def project_message_for_summary(message: dict[str, Any]) -> dict[str, Any]:
    recipients = message.get('recipients') or []
    if not isinstance(recipients, list):
        recipients = [recipients]
    keywords = message.get('keywords') or []
    if not isinstance(keywords, list):
        keywords = [keywords]
    flags = [str(flag) for flag in _normalise_text_list(message.get('flags')) if str(flag).strip()]
    recipient = _normalise_text(recipients[0]) if recipients else ''
    body_text = _normalise_text(message.get('bodyText', ''))
    body = body_text or _normalise_text(message.get('bodyPreview', ''))
    return {
        'id': _normalise_text(message.get('id')),
        'subject': _normalise_text(message.get('subject')),
        'sender': _normalise_text(message.get('sender')),
        'recipient': recipient,
        'date': _normalise_text(message.get('date')),
        'body': body,
        'unread': '\\seen' not in {flag.lower() for flag in flags},
        'replied': '\\answered' in {flag.lower() for flag in flags},
        'flagged': '\\flagged' in {flag.lower() for flag in flags},
        'keywords': [str(keyword) for keyword in _normalise_text_list(keywords)],
        'listId': _normalise_text(message.get('listId')),
    }
