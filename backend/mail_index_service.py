from __future__ import annotations

from datetime import datetime
from email.parser import BytesParser
from email.policy import default
from email.utils import getaddresses
from typing import Any
import imaplib

from backend import db
from backend.fake_mail_server import REGISTRY as FAKE_MAIL_REGISTRY
from backend.mail_service import (
    MailServiceError,
    _imap_connection,
    _redact_error_message,
    discover_mailboxes_for_account,
    search_messages,
)
from backend.schemas import SearchCriteria


def _now_iso() -> str:
    return datetime.now().isoformat(timespec='seconds')


def _limit_value(limit: int | str | None) -> int:
    try:
        value = int(limit if limit is not None else 500)
    except (TypeError, ValueError):
        value = 500
    return max(1, min(value, 500))


def _trimmed_preview(text: Any, limit: int = 280) -> str:
    value = str(text or '').strip()
    if not value:
        return ''
    return ' '.join(value.split())[:limit]


def _decode_text(value: Any) -> str:
    if isinstance(value, (bytes, bytearray)):
        return bytes(value).decode('utf-8', errors='ignore')
    return str(value or '')


def _string_list(value: Any) -> list[str]:
    if value in (None, ''):
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, (list, tuple, set)):
        results: list[str] = []
        seen: set[str] = set()
        for item in value:
            text = str(item or '').strip()
            if not text or text in seen:
                continue
            seen.add(text)
            results.append(text)
        return results
    text = str(value).strip()
    return [text] if text else []


def _compose_message_id(account_id: str, mailbox_path: str, uid: str) -> str:
    return f'{account_id}|{mailbox_path}|{uid}'


def _is_fake_environment(account: dict[str, Any]) -> bool:
    host = str(account.get('imapHost') or '').strip()
    if not host:
        return False
    port = int(account.get('imapPort') or 993)
    return (host, port) in FAKE_MAIL_REGISTRY


def _fake_or_dummy_messages(account: dict[str, Any], mailbox_path: str, limit: int) -> list[dict[str, Any]]:
    dummy_mode = bool(account.get('dummyMode', False))
    settings: dict[str, Any] = {'dummyMode': dummy_mode} if dummy_mode else dict(account)
    settings['dummyMode'] = dummy_mode
    criteria = SearchCriteria(limit=limit, mailboxes=[mailbox_path] if not dummy_mode else [])
    messages = search_messages(criteria, settings)
    indexed: list[dict[str, Any]] = []
    account_id = str(account.get('id') or 'sample').strip() or 'sample'
    now = _now_iso()
    for message in messages[:limit]:
        recipient = str(message.get('recipient') or message.get('sender') or '').strip()
        keywords = _string_list(message.get('keywords'))
        flags: list[str] = []
        if not bool(message.get('unread', True)):
            flags.append('\\Seen')
        if bool(message.get('flagged')):
            flags.append('\\Flagged')
        if bool(message.get('replied')):
            flags.append('\\Answered')
        flags.extend(keywords)
        indexed.append({
            'id': _compose_message_id(account_id, mailbox_path, str(message.get('id') or '')),
            'accountId': account_id,
            'mailboxPath': mailbox_path,
            'uid': str(message.get('id') or ''),
            'messageIdHeader': '',
            'subject': str(message.get('subject') or ''),
            'sender': str(message.get('sender') or ''),
            'recipients': [recipient] if recipient else [],
            'date': str(message.get('date') or ''),
            'flags': flags,
            'keywords': keywords,
            'listId': '',
            'bodyPreview': _trimmed_preview(message.get('body', '')),
            'bodyCached': False,
            'bodyText': '',
            'lastSeenAt': now,
        })
    return indexed


def _extract_fetch_bytes(fdata: Any) -> bytes | None:
    if isinstance(fdata, list):
        for item in fdata:
            payload = _extract_fetch_bytes(item)
            if payload is not None:
                return payload
        return None
    if isinstance(fdata, tuple):
        if len(fdata) >= 2 and isinstance(fdata[1], (bytes, bytearray)):
            return bytes(fdata[1])
        for item in fdata:
            payload = _extract_fetch_bytes(item)
            if payload is not None:
                return payload
        return None
    if isinstance(fdata, (bytes, bytearray)):
        return bytes(fdata)
    return None


def _fetch_imap_part(imap: Any, uid: str, item: str) -> bytes | None:
    try:
        typ, data = imap.uid('fetch', uid, item)
    except (imaplib.IMAP4.error, OSError):
        return None
    if str(typ).upper() != 'OK' or not data:
        return None
    return _extract_fetch_bytes(data)


def _parse_header_message(raw_headers: bytes | None) -> Any | None:
    if not raw_headers:
        return None
    try:
        parser = BytesParser(policy=default)
        return parser.parsebytes(raw_headers)
    except (TypeError, ValueError, UnicodeDecodeError):
        return None


def _derive_flags(raw_flags: list[str]) -> tuple[list[str], list[str]]:
    flags = [str(flag) for flag in raw_flags if str(flag).strip()]
    keywords = [flag for flag in flags if not flag.startswith('\\')]
    return flags, keywords


def _build_index_message_from_imap(account_id: str, mailbox_path: str, uid: str, imap: Any) -> tuple[dict[str, Any] | None, bool]:
    headers = _fetch_imap_part(imap, uid, '(BODY.PEEK[HEADER])')
    if not headers:
        return None, True
    message = _parse_header_message(headers)
    if message is None:
        return None, True

    preview_bytes = _fetch_imap_part(imap, uid, '(BODY.PEEK[TEXT]<0.1024>)')
    flags_failed = False
    flags_data: list[str] = []
    try:
        flags_typ, raw_flags = imap.uid('fetch', uid, '(FLAGS)')
        if str(flags_typ).upper() == 'OK' and raw_flags:
            fetched_flags = _extract_fetch_bytes(raw_flags)
            if fetched_flags is not None:
                flags_text = fetched_flags.decode('utf-8', errors='ignore')
                start = flags_text.find('FLAGS (')
                if start != -1:
                    start += len('FLAGS (')
                    end = flags_text.find(')', start)
                    flags_data = [item.strip() for item in flags_text[start:end].split() if item.strip()]
            else:
                flags_failed = True
        else:
            flags_failed = True
    except (imaplib.IMAP4.error, OSError):
        flags_failed = True

    flags, keywords = _derive_flags(flags_data)
    recipient_header = str(message.get('To', '') or '')
    recipients = [addr or name for name, addr in getaddresses([recipient_header]) if addr or name]
    list_id_parts = [
        str(message.get('List-Id', '') or '').strip(),
        str(message.get('List-Unsubscribe', '') or '').strip(),
    ]
    list_id = ' | '.join(part for part in list_id_parts if part)

    indexed_message = {
        'id': _compose_message_id(account_id, mailbox_path, uid),
        'accountId': account_id,
        'mailboxPath': mailbox_path,
        'uid': uid,
        'messageIdHeader': str(message.get('Message-ID', '') or '').strip(),
        'subject': str(message.get('Subject', '') or ''),
        'sender': str(message.get('From', '') or ''),
        'recipients': recipients,
        'date': str(message.get('Date', '') or ''),
        'flags': flags,
        'keywords': keywords,
        'listId': list_id,
        'bodyPreview': _trimmed_preview(preview_bytes.decode('utf-8', errors='replace') if preview_bytes else ''),
        'bodyCached': False,
        'bodyText': '',
        'lastSeenAt': _now_iso(),
    }
    return indexed_message, preview_bytes is None or flags_failed


def _resolve_account(settings: dict[str, Any], account_id: str) -> dict[str, Any]:
    resolved_account_id = str(account_id or '').strip()

    if bool(settings.get('dummyMode', False)):
        return {
            'id': resolved_account_id or 'sample',
            'displayName': 'Sample Mailbox',
            'enabled': True,
            'imapHost': '',
            'imapPort': 0,
            'imapUseSSL': False,
            'username': '',
            'imapPassword': '',
            'dummyMode': True,
        }

    raw_accounts = settings.get('mailAccounts') or []
    explicit_accounts = [account for account in raw_accounts if isinstance(account, dict)]
    if explicit_accounts:
        if resolved_account_id:
            for account in explicit_accounts:
                if str(account.get('id', '')).strip() == resolved_account_id:
                    if not bool(account.get('enabled', True)):
                        raise MailServiceError(f'Account {resolved_account_id!r} is disabled')
                    return dict(account)
            raise MailServiceError(f'Account {resolved_account_id!r} not found')
        enabled_accounts = [account for account in explicit_accounts if bool(account.get('enabled', True))]
        if len(enabled_accounts) == 1:
            return dict(enabled_accounts[0])
        if not enabled_accounts:
            raise MailServiceError('No enabled mail accounts configured')
        raise MailServiceError('accountId is required when multiple mail accounts are configured')

    host = str(settings.get('imapHost') or '').strip()
    if not host:
        raise MailServiceError('No mail account configured')
    legacy_account = {
        'id': 'default',
        'displayName': str(settings.get('username') or host or 'Default Account'),
        'enabled': True,
        'imapHost': settings.get('imapHost', ''),
        'imapPort': int(settings.get('imapPort') or 993),
        'imapUseSSL': bool(settings.get('imapUseSSL', True)),
        'username': settings.get('username', ''),
        'imapPassword': settings.get('imapPassword', ''),
        'smtpHost': settings.get('smtpHost', ''),
        'smtpPort': int(settings.get('smtpPort') or 465),
        'smtpUseSSL': bool(settings.get('smtpUseSSL', True)),
        'smtpPassword': settings.get('smtpPassword', ''),
        'recipientEmail': settings.get('recipientEmail', ''),
    }
    if resolved_account_id and resolved_account_id != 'default':
        raise MailServiceError(f'Account {resolved_account_id!r} not found')
    return legacy_account


def sync_mailbox(account: dict[str, Any], mailbox_path: str, limit: int = 500) -> dict[str, Any]:
    limit_value = _limit_value(limit)
    resolved_account = dict(account)
    account_id = str(resolved_account.get('id') or resolved_account.get('accountId') or '').strip() or 'default'
    mailbox_path_value = str(mailbox_path or 'INBOX').strip() or 'INBOX'
    account_record = dict(resolved_account)
    account_record['id'] = account_id

    db.upsert_index_account(account_record, updated_at=_now_iso())

    if bool(resolved_account.get('dummyMode', False)):
        db.upsert_index_mailbox(account_id, {
            'path': mailbox_path_value,
            'delimiter': '/',
            'selectable': True,
            'flags': [],
        }, updated_at=_now_iso())
        messages = _fake_or_dummy_messages(account_record | {'dummyMode': True}, mailbox_path_value, limit_value)
        indexed = 0
        for message in messages:
            db.upsert_index_message(message, last_seen_at=message.get('lastSeenAt'))
            indexed += 1
        db.update_sync_state(account_id, mailbox_path_value, last_sync_at=_now_iso())
        return {'accountId': account_id, 'mailbox': mailbox_path_value, 'scanned': len(messages), 'indexed': indexed, 'errors': 0}

    host = str(resolved_account.get('imapHost') or '').strip()
    port = int(resolved_account.get('imapPort') or 993)
    use_ssl = bool(resolved_account.get('imapUseSSL', True))
    username = str(resolved_account.get('username') or '').strip() or None
    password = str(resolved_account.get('imapPassword') or '')

    if _is_fake_environment(resolved_account):
        mailbox_info = None
        try:
            mailboxes = discover_mailboxes_for_account(resolved_account)
        except MailServiceError:
            raise
        for candidate in mailboxes:
            if str(candidate.get('path', '')) == mailbox_path_value:
                mailbox_info = candidate
                break
        if mailbox_info is None:
            raise MailServiceError(f'Could not select mailbox {mailbox_path_value}')
        if not bool(mailbox_info.get('selectable', True)):
            raise MailServiceError(f'Could not select mailbox {mailbox_path_value}')
        db.upsert_index_mailbox(account_id, mailbox_info, updated_at=_now_iso())
        messages = _fake_or_dummy_messages(account_record, mailbox_path_value, limit_value)
        indexed = 0
        for message in messages:
            db.upsert_index_message(message, last_seen_at=message.get('lastSeenAt'))
            indexed += 1
        db.update_sync_state(account_id, mailbox_path_value, last_sync_at=_now_iso())
        return {'accountId': account_id, 'mailbox': mailbox_path_value, 'scanned': len(messages), 'indexed': indexed, 'errors': 0}

    try:
        mailbox_info = None
        for candidate in discover_mailboxes_for_account(resolved_account):
            if str(candidate.get('path', '')) == mailbox_path_value:
                mailbox_info = candidate
                break
        if mailbox_info is None:
            raise MailServiceError(f'Could not select mailbox {mailbox_path_value}')
        if not bool(mailbox_info.get('selectable', True)):
            raise MailServiceError(f'Could not select mailbox {mailbox_path_value}')
        db.upsert_index_mailbox(account_id, mailbox_info, updated_at=_now_iso())

        with _imap_connection(host, port, use_ssl, username, password, mailbox_path_value) as imap:
            typ, data = imap.uid('search', None, 'ALL')
            if str(typ).upper() != 'OK':
                raise MailServiceError(f'Could not search mailbox {mailbox_path_value}')
            raw_uids = []
            if data and data[0]:
                raw_search = _decode_text(data[0])
                raw_uids = [item for item in raw_search.split() if item.strip()]
            selected_uids = raw_uids[-limit_value:]
            indexed = 0
            errors = 0
            for uid in selected_uids:
                indexed_message, preview_failed = _build_index_message_from_imap(account_id, mailbox_path_value, uid, imap)
                if indexed_message is None:
                    errors += 1
                    continue
                if preview_failed:
                    errors += 1
                db.upsert_index_message(indexed_message, last_seen_at=indexed_message.get('lastSeenAt'))
                indexed += 1
            db.update_sync_state(account_id, mailbox_path_value, last_sync_at=_now_iso())
            return {'accountId': account_id, 'mailbox': mailbox_path_value, 'scanned': len(selected_uids), 'indexed': indexed, 'errors': errors}
    except MailServiceError:
        raise
    except (imaplib.IMAP4.error, OSError) as exc:
        raise MailServiceError(_redact_error_message(str(exc), password)) from exc
