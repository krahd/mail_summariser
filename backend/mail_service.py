from __future__ import annotations

import imaplib
import smtplib
from copy import deepcopy
from email import message_from_bytes
from email.header import decode_header, make_header
from email.message import EmailMessage, Message
from email.utils import parsedate_to_datetime
from typing import Any

from schemas import SearchCriteria


class MailServiceError(RuntimeError):
    pass


DEFAULT_DUMMY_MESSAGES = [
    {
        "id": "msg-001",
        "subject": "Project update",
        "sender": "alice@example.com",
        "recipient": "you@example.com",
        "date": "2026-03-10T09:00:00",
        "body": "The project is on track. Key decisions are pending on budget and the deployment schedule.",
        "unread": True,
        "replied": False,
        "keywords": ["work"],
    },
    {
        "id": "msg-002",
        "subject": "Invoice question",
        "sender": "bob@example.com",
        "recipient": "you@example.com",
        "date": "2026-03-10T10:00:00",
        "body": "Can you confirm the invoice line items and whether travel costs are billable this month?",
        "unread": True,
        "replied": True,
        "keywords": ["finance"],
    },
    {
        "id": "msg-003",
        "subject": "Reading group",
        "sender": "carol@example.com",
        "recipient": "team@example.com",
        "date": "2026-03-09T17:30:00",
        "body": "Reminder that tomorrow's reading group starts at 4 pm. Please send your paper suggestions.",
        "unread": False,
        "replied": False,
        "keywords": ["academic"],
    },
]

_dummy_mailbox = deepcopy(DEFAULT_DUMMY_MESSAGES)
_dummy_outbox: list[dict[str, str]] = []


def reset_dummy_mailbox() -> None:
    global _dummy_mailbox
    _dummy_mailbox = deepcopy(DEFAULT_DUMMY_MESSAGES)
    _dummy_outbox.clear()


def get_dummy_outbox() -> list[dict[str, str]]:
    return deepcopy(_dummy_outbox)


def is_dummy_mode(settings: dict[str, Any] | None) -> bool:
    return bool((settings or {}).get("dummyMode", True))


def _normalized_keywords(message: dict[str, Any]) -> list[str]:
    raw = message.get("keywords", [])
    return [str(item) for item in raw if str(item).strip()]


def _matches_criteria(message: dict[str, Any], criteria: SearchCriteria) -> bool:
    checks: list[bool] = []
    subject = str(message.get("subject", ""))
    body = str(message.get("body", ""))
    sender = str(message.get("sender", ""))
    recipient = str(message.get("recipient", ""))
    keywords = [item.lower() for item in _normalized_keywords(message)]

    if criteria.keyword:
        haystack = f"{subject} {body}"
        checks.append(criteria.keyword.lower() in haystack.lower())
    if criteria.rawSearch:
        haystack = f"{subject} {body} {sender} {recipient} {' '.join(keywords)}"
        checks.append(criteria.rawSearch.lower() in haystack.lower())
    if criteria.sender:
        checks.append(criteria.sender.lower() in sender.lower())
    if criteria.recipient:
        checks.append(criteria.recipient.lower() in recipient.lower())
    if criteria.tag:
        checks.append(criteria.tag.lower() in keywords)
    if criteria.unreadOnly:
        checks.append(bool(message.get("unread")))
    if criteria.readOnly:
        checks.append(not bool(message.get("unread")))
    if criteria.replied is not None:
        checks.append(bool(message.get("replied")) is criteria.replied)

    if not checks:
        return True
    if criteria.useAnd:
        return all(checks)
    return any(checks)


def _decode_header_value(raw: str | None) -> str:
    if not raw:
        return ""
    try:
        return str(make_header(decode_header(raw)))
    except Exception:
        return raw


def _extract_text_body(message: Message) -> str:
    if message.is_multipart():
        parts: list[str] = []
        for part in message.walk():
            disposition = (part.get_content_disposition() or "").lower()
            if disposition == "attachment":
                continue
            if part.get_content_type() != "text/plain":
                continue
            payload = part.get_payload(decode=True)
            if payload is None:
                continue
            charset = part.get_content_charset() or "utf-8"
            try:
                parts.append(payload.decode(charset, errors="replace"))
            except LookupError:
                parts.append(payload.decode("utf-8", errors="replace"))
        return "\n".join(part.strip() for part in parts if part.strip()).strip()

    payload = message.get_payload(decode=True)
    if payload is None:
        raw_payload = message.get_payload()
        return raw_payload if isinstance(raw_payload, str) else ""
    charset = message.get_content_charset() or "utf-8"
    try:
        return payload.decode(charset, errors="replace").strip()
    except LookupError:
        return payload.decode("utf-8", errors="replace").strip()


def _format_date(raw_date: str | None) -> str:
    if not raw_date:
        return ""
    try:
        return parsedate_to_datetime(raw_date).isoformat()
    except (TypeError, ValueError, IndexError, OverflowError):
        return raw_date


def _parse_flags(metadata: bytes | str) -> set[str]:
    text = metadata.decode("utf-8", errors="replace") if isinstance(metadata, bytes) else str(metadata)
    start = text.find("FLAGS (")
    if start < 0:
        return set()
    start += len("FLAGS (")
    end = text.find(")", start)
    if end < 0:
        return set()
    return {flag for flag in text[start:end].split() if flag}


def _imap_message_from_bytes(uid: str, raw_message: bytes, flags: set[str]) -> dict[str, Any]:
    message = message_from_bytes(raw_message)
    keywords = [flag for flag in flags if not flag.startswith("\\")]
    return {
        "id": uid,
        "subject": _decode_header_value(message.get("Subject")),
        "sender": _decode_header_value(message.get("From")),
        "recipient": _decode_header_value(message.get("To")),
        "date": _format_date(message.get("Date")),
        "body": _extract_text_body(message),
        "unread": "\\Seen" not in flags,
        "replied": "\\Answered" in flags,
        "keywords": keywords,
    }


def _setting_str(settings: dict[str, Any], key: str) -> str:
    return str(settings.get(key, "")).strip()


def _setting_bool(settings: dict[str, Any], key: str, default: bool = False) -> bool:
    value = settings.get(key, default)
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _require_setting(settings: dict[str, Any], key: str, label: str) -> str:
    value = _setting_str(settings, key)
    if not value:
        raise MailServiceError(f"{label} is required when dummy mode is off")
    return value


def _smtp_password(settings: dict[str, Any]) -> str:
    return _setting_str(settings, "smtpPassword") or _setting_str(settings, "imapPassword")


def _login_imap(client: imaplib.IMAP4, settings: dict[str, Any]) -> None:
    username = _require_setting(settings, "username", "Username")
    password = _require_setting(settings, "imapPassword", "IMAP password")
    status, data = client.login(username, password)
    if status != "OK":
        raise MailServiceError(f"IMAP login failed: {data}")


def _open_imap_client(settings: dict[str, Any], readonly: bool) -> imaplib.IMAP4:
    host = _require_setting(settings, "imapHost", "IMAP host")
    port = int(settings.get("imapPort", 993))
    use_ssl = _setting_bool(settings, "imapUseSSL", True)

    try:
        client = imaplib.IMAP4_SSL(host, port) if use_ssl else imaplib.IMAP4(host, port)
        _login_imap(client, settings)
        status, data = client.select("INBOX", readonly=readonly)
        if status != "OK":
            raise MailServiceError(f"Failed to select INBOX: {data}")
        return client
    except MailServiceError:
        raise
    except Exception as exc:
        raise MailServiceError(f"IMAP connection failed: {exc}") from exc


def _close_imap_client(client: imaplib.IMAP4 | None) -> None:
    if client is None:
        return
    try:
        client.logout()
    except Exception:
        pass


def _open_smtp_client(settings: dict[str, Any]) -> smtplib.SMTP:
    host = _require_setting(settings, "smtpHost", "SMTP host")
    port = int(settings.get("smtpPort", 465))
    use_ssl = _setting_bool(settings, "smtpUseSSL", True)
    username = _require_setting(settings, "username", "Username")
    password = _smtp_password(settings)

    try:
        client: smtplib.SMTP = smtplib.SMTP_SSL(host, port, timeout=10) if use_ssl else smtplib.SMTP(host, port, timeout=10)
        client.ehlo()
        if username and password:
            client.login(username, password)
        return client
    except Exception as exc:
        raise MailServiceError(f"SMTP connection failed: {exc}") from exc


def _close_smtp_client(client: smtplib.SMTP | None) -> None:
    if client is None:
        return
    try:
        client.quit()
    except Exception:
        pass


def _fetch_uid_message(client: imaplib.IMAP4, uid: str) -> dict[str, Any] | None:
    status, data = client.uid("fetch", uid, "(UID FLAGS BODY.PEEK[])")
    if status != "OK":
        raise MailServiceError(f"Failed to fetch message {uid}: {data}")

    raw_message = b""
    metadata = b""
    for item in data:
        if isinstance(item, tuple):
            metadata = item[0] if isinstance(item[0], bytes) else metadata
            if isinstance(item[1], bytes):
                raw_message = item[1]

    if not raw_message:
        return None
    return _imap_message_from_bytes(uid, raw_message, _parse_flags(metadata))


def _fetch_uid_flags(client: imaplib.IMAP4, uid: str) -> set[str]:
    status, data = client.uid("fetch", uid, "(FLAGS)")
    if status != "OK":
        raise MailServiceError(f"Failed to fetch flags for message {uid}: {data}")

    for item in data:
        if isinstance(item, tuple):
            return _parse_flags(item[0])
    return set()


def _store_uid_flags(client: imaplib.IMAP4, uid: str, operation: str, flags: list[str]) -> None:
    flag_list = " ".join(flags)
    status, data = client.uid("store", uid, f"{operation}.SILENT", f"({flag_list})")
    if status != "OK":
        raise MailServiceError(f"Failed to update flags for message {uid}: {data}")


def _search_imap(criteria: SearchCriteria, settings: dict[str, Any]) -> list[dict[str, Any]]:
    client: imaplib.IMAP4 | None = None
    try:
        client = _open_imap_client(settings, readonly=True)
        status, data = client.uid("search", None, "ALL")
        if status != "OK":
            raise MailServiceError(f"IMAP search failed: {data}")

        uid_bytes = data[0].split() if data and data[0] else []
        results: list[dict[str, Any]] = []
        for uid_bytes_item in reversed(uid_bytes[-200:]):
            uid = uid_bytes_item.decode("utf-8", errors="replace")
            message = _fetch_uid_message(client, uid)
            if message and _matches_criteria(message, criteria):
                results.append(message)
        return results
    finally:
        _close_imap_client(client)


def _find_dummy_messages(message_ids: list[str]) -> list[dict[str, Any]]:
    wanted = set(message_ids)
    return [message for message in _dummy_mailbox if message["id"] in wanted]


def _search_dummy(criteria: SearchCriteria) -> list[dict[str, Any]]:
    return [
        deepcopy(message)
        for message in _dummy_mailbox
        if _matches_criteria(message, criteria)
    ]


def search_messages(criteria: SearchCriteria, settings: dict[str, Any]) -> list[dict[str, Any]]:
    if is_dummy_mode(settings):
        return _search_dummy(criteria)
    return _search_imap(criteria, settings)


def mark_messages_read(message_ids: list[str], settings: dict[str, Any]) -> dict[str, Any]:
    if is_dummy_mode(settings):
        changed_ids: list[str] = []
        for message in _find_dummy_messages(message_ids):
            if message.get("unread"):
                message["unread"] = False
                changed_ids.append(message["id"])
        return {"restore_unread_ids": changed_ids}

    client: imaplib.IMAP4 | None = None
    try:
        client = _open_imap_client(settings, readonly=False)
        changed_ids: list[str] = []
        for uid in message_ids:
            flags = _fetch_uid_flags(client, uid)
            if "\\Seen" not in flags:
                _store_uid_flags(client, uid, "+FLAGS", ["\\Seen"])
                changed_ids.append(uid)
        return {"restore_unread_ids": changed_ids}
    finally:
        _close_imap_client(client)


def restore_messages_unread(message_ids: list[str], settings: dict[str, Any]) -> None:
    if is_dummy_mode(settings):
        for message in _find_dummy_messages(message_ids):
            message["unread"] = True
        return

    client: imaplib.IMAP4 | None = None
    try:
        client = _open_imap_client(settings, readonly=False)
        for uid in message_ids:
            _store_uid_flags(client, uid, "-FLAGS", ["\\Seen"])
    finally:
        _close_imap_client(client)


def add_keyword_tag(message_ids: list[str], tag: str, settings: dict[str, Any]) -> dict[str, Any]:
    normalized_tag = tag.strip()
    if not normalized_tag:
        return {"added_message_ids": []}

    if is_dummy_mode(settings):
        added_message_ids: list[str] = []
        for message in _find_dummy_messages(message_ids):
            current = _normalized_keywords(message)
            if normalized_tag.lower() not in [item.lower() for item in current]:
                current.append(normalized_tag)
                message["keywords"] = current
                added_message_ids.append(message["id"])
        return {"added_message_ids": added_message_ids}

    client: imaplib.IMAP4 | None = None
    try:
        client = _open_imap_client(settings, readonly=False)
        added_message_ids: list[str] = []
        for uid in message_ids:
            flags = _fetch_uid_flags(client, uid)
            if normalized_tag.lower() not in [flag.lower() for flag in flags]:
                _store_uid_flags(client, uid, "+FLAGS", [normalized_tag])
                added_message_ids.append(uid)
        return {"added_message_ids": added_message_ids}
    finally:
        _close_imap_client(client)


def remove_keyword_tag(message_ids: list[str], tag: str, settings: dict[str, Any]) -> None:
    normalized_tag = tag.strip()
    if not normalized_tag:
        return

    if is_dummy_mode(settings):
        for message in _find_dummy_messages(message_ids):
            message["keywords"] = [
                keyword
                for keyword in _normalized_keywords(message)
                if keyword.lower() != normalized_tag.lower()
            ]
        return

    client: imaplib.IMAP4 | None = None
    try:
        client = _open_imap_client(settings, readonly=False)
        for uid in message_ids:
            _store_uid_flags(client, uid, "-FLAGS", [normalized_tag])
    finally:
        _close_imap_client(client)


def send_summary_email(recipient: str, subject: str, body: str, settings: dict[str, Any]) -> None:
    if is_dummy_mode(settings):
        _dummy_outbox.append(
            {
                "recipient": recipient,
                "subject": subject,
                "body": body,
            }
        )
        return

    username = _require_setting(settings, "username", "Username")
    smtp_client: smtplib.SMTP | None = None
    try:
        smtp_client = _open_smtp_client(settings)
        message = EmailMessage()
        message["From"] = username
        message["To"] = recipient
        message["Subject"] = subject
        message.set_content(body)
        smtp_client.send_message(message)
    finally:
        _close_smtp_client(smtp_client)


def test_mail_connection(settings: dict[str, Any]) -> dict[str, Any]:
    if is_dummy_mode(settings):
        return {
            "status": "ok",
            "mode": "dummy",
            "imap": {"status": "ok", "message": "Dummy mode uses the built-in test mailbox"},
            "smtp": {"status": "ok", "message": "Dummy mode uses the in-memory outbox"},
            "details": {"messageCount": len(_dummy_mailbox)},
        }

    imap_client: imaplib.IMAP4 | None = None
    smtp_client: smtplib.SMTP | None = None
    try:
        imap_client = _open_imap_client(settings, readonly=True)
        status, data = imap_client.select("INBOX", readonly=True)
        if status != "OK":
            raise MailServiceError(f"Failed to inspect INBOX: {data}")
        message_count = int((data[0] or b"0").decode("utf-8", errors="replace") or "0")

        smtp_client = _open_smtp_client(settings)
        smtp_code, smtp_message = smtp_client.noop()
        return {
            "status": "ok",
            "mode": "imap",
            "imap": {"status": "ok", "message": f"Connected to INBOX with {message_count} messages"},
            "smtp": {
                "status": "ok",
                "message": f"SMTP NOOP returned {smtp_code} {smtp_message.decode('utf-8', errors='replace') if isinstance(smtp_message, bytes) else smtp_message}",
            },
            "details": {"messageCount": message_count},
        }
    finally:
        _close_imap_client(imap_client)
        _close_smtp_client(smtp_client)
