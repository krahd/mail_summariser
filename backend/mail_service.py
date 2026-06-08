from __future__ import annotations

from copy import deepcopy
from typing import Any, TYPE_CHECKING
import imaplib
import smtplib
from contextlib import contextmanager
from email.parser import BytesParser
from email.policy import default
from email.message import EmailMessage

from backend.schemas import SearchCriteria

if TYPE_CHECKING:
    # Types imported here are only for static analysis (Pylance/pyright).
    # The fake mail environment is runtime-injected in tests so importing
    # it unconditionally can confuse test-time patches.
    from backend.fake_mail_server import FakeMailEnvironment


class MailServiceError(RuntimeError):
    pass


def _response_text(message: Any) -> str:
    if message is None:
        return ''
    if isinstance(message, bytes):
        return message.decode('utf-8', errors='replace')
    if isinstance(message, bytearray):
        return bytes(message).decode('utf-8', errors='replace')
    if isinstance(message, (list, tuple)):
        parts = [_response_text(item) for item in message if item is not None]
        return ' '.join(part for part in parts if part).strip()
    return str(message)


def _redact_error_message(message: Any, password: str | None = None) -> str:
    """Redact passwords and other sensitive values from error messages."""
    if not message:
        return ''
    redacted = _response_text(message)
    # Redact any obvious password patterns or actual password value if provided
    if password and len(password) > 0:
        redacted = redacted.replace(password, '***')
    # Redact IMAP4 standard error patterns that might contain credentials
    if 'LOGIN' in redacted and 'failed' in redacted.lower():
        # Keep the error but redact any credentials-like parts
        redacted = 'IMAP authentication failed'
    return redacted


DEFAULT_DUMMY_MESSAGES = [
    {
        'id': 'msg-001',
        'subject': 'Project update',
        'sender': 'alice@example.com',
        'recipient': 'you@example.com',
        'date': '2026-03-10T09:00:00',
        'body': 'The project is on track. Key decisions are pending on budget and the deployment schedule.',
        'unread': True,
        'replied': False,
        'keywords': ['work'],
    },
    {
        'id': 'msg-002',
        'subject': 'Invoice question',
        'sender': 'bob@example.com',
        'recipient': 'you@example.com',
        'date': '2026-03-10T10:00:00',
        'body': 'Can you confirm the invoice line items and whether travel costs are billable this month?',
        'unread': True,
        'replied': True,
        'keywords': ['finance'],
    },
]

_dummy_mailbox = deepcopy(DEFAULT_DUMMY_MESSAGES)
_dummy_outbox: list[dict[str, str]] = []


def reset_dummy_mailbox() -> None:
    global _dummy_mailbox  # pylint: disable=global-statement
    _dummy_mailbox = deepcopy(DEFAULT_DUMMY_MESSAGES)
    _dummy_outbox.clear()


def get_dummy_outbox() -> list[dict[str, str]]:
    return deepcopy(_dummy_outbox)


def is_dummy_mode(settings: dict[str, Any] | None) -> bool:
    return bool((settings or {}).get('dummyMode', True))


def _normalized_keywords(message: dict[str, Any]) -> list[str]:
    return [str(item) for item in message.get('keywords', []) if str(item).strip()]


def _matches_criteria(message: dict[str, Any], criteria: SearchCriteria) -> bool:
    checks: list[bool] = []
    subject = str(message.get('subject', ''))
    body = str(message.get('body', ''))
    sender = str(message.get('sender', ''))
    recipient = str(message.get('recipient', ''))
    keywords = [item.lower() for item in _normalized_keywords(message)]

    if criteria.keyword:
        checks.append(criteria.keyword.lower() in f'{subject} {body}'.lower())
    if criteria.rawSearch:
        hay = f"{subject} {body} {sender} {recipient} {' '.join(keywords)}".lower()
        checks.append(criteria.rawSearch.lower() in hay)
    if criteria.sender:
        checks.append(criteria.sender.lower() in sender.lower())
    if criteria.recipient:
        checks.append(criteria.recipient.lower() in recipient.lower())
    if criteria.tag:
        checks.append(criteria.tag.lower() in keywords)
    if criteria.unreadOnly:
        checks.append(bool(message.get('unread')))
    if criteria.readOnly:
        checks.append(not bool(message.get('unread')))
    if criteria.replied is not None:
        checks.append(bool(message.get('replied')) is criteria.replied)

    if not checks:
        return True
    return all(checks) if criteria.useAnd else any(checks)


def _find_dummy_messages(message_ids: list[str]) -> list[dict[str, Any]]:
    wanted = set(message_ids)
    return [message for message in _dummy_mailbox if message['id'] in wanted]


def _get_fake_env_for_host_port(host: str | None, port: int) -> Any | None:
    if host is None:
        return None
    try:
        from backend.fake_mail_server import REGISTRY as _REG  # pylint: disable=import-outside-toplevel
        return _REG.get((host, port))
    except (ImportError, AttributeError):
        return None


def _env_messages_from_env(env: Any) -> list[dict[str, Any]]:
    env_messages: list[dict[str, Any]] = []
    for msg in env.list_messages():
        flags = env.flags_for(msg['id'])
        env_messages.append({
            'id': str(msg.get('id', '')),
            'subject': msg.get('subject', ''),
            'sender': msg.get('sender', ''),
            'recipient': msg.get('recipient', ''),
            'date': msg.get('date', ''),
            'body': msg.get('body', ''),
            'unread': '\\Seen' not in flags,
            'replied': '\\Answered' in flags,
            'keywords': [f for f in flags if not f.startswith('\\')],
        })
    return env_messages


def _find_dummy_message(message_id: str) -> dict[str, Any] | None:
    for message in _dummy_mailbox:
        if str(message.get('id', '')) == str(message_id):
            return message
    return None


def _find_env_message(env: Any, message_id: str) -> dict[str, Any] | None:
    for message in env.messages.values():
        if str(message.get('id', '')) == str(message_id):
            return message
    return None


def _select_inbox_or_raise(imap: Any, password: str | None) -> None:
    try:
        typ, data = imap.select('INBOX')
    except imaplib.IMAP4.error as exc:
        raise MailServiceError(
            _redact_error_message(f'Could not select mailbox INBOX: {exc}', password)
        ) from exc
    if str(typ).upper() != 'OK':
        reason = _response_text(data)
        message = 'Could not select mailbox INBOX'
        if reason:
            message = f'{message}: {_redact_error_message(reason, password)}'
        raise MailServiceError(message)


def _store_message_flags(
    imap: Any,
    message_ids: list[str],
    command: str,
    flag: str,
) -> tuple[list[str], list[str]]:
    changed_ids: list[str] = []
    failed_ids: list[str] = []
    for uid in message_ids:
        try:
            typ, _ = imap.uid('STORE', str(uid), command, flag)
            if str(typ).upper() == 'OK':
                changed_ids.append(str(uid))
            else:
                failed_ids.append(str(uid))
        except (imaplib.IMAP4.error, OSError):
            failed_ids.append(str(uid))
    return changed_ids, failed_ids


def _mark_dummy_messages_read(message_ids: list[str]) -> tuple[list[str], list[str]]:
    changed_ids: list[str] = []
    failed_ids: list[str] = []
    for uid in message_ids:
        message = _find_dummy_message(uid)
        if message is None:
            failed_ids.append(str(uid))
            continue
        if message.get('unread'):
            message['unread'] = False
            changed_ids.append(str(message.get('id', uid)))
    return changed_ids, failed_ids


def _restore_dummy_messages_unread(message_ids: list[str]) -> tuple[list[str], list[str]]:
    changed_ids: list[str] = []
    failed_ids: list[str] = []
    for uid in message_ids:
        message = _find_dummy_message(uid)
        if message is None:
            failed_ids.append(str(uid))
            continue
        if not message.get('unread'):
            message['unread'] = True
            changed_ids.append(str(message.get('id', uid)))
    return changed_ids, failed_ids


def _mark_env_messages_read(env: Any, message_ids: list[str]) -> tuple[list[str], list[str]]:
    changed_ids: list[str] = []
    failed_ids: list[str] = []
    for uid in message_ids:
        message = _find_env_message(env, uid)
        if message is None:
            failed_ids.append(str(uid))
            continue
        if '\\Seen' not in message['flags']:
            message['flags'].add('\\Seen')
            changed_ids.append(str(message.get('id', uid)))
    return changed_ids, failed_ids


def _restore_env_messages_unread(env: Any, message_ids: list[str]) -> tuple[list[str], list[str]]:
    changed_ids: list[str] = []
    failed_ids: list[str] = []
    for uid in message_ids:
        message = _find_env_message(env, uid)
        if message is None:
            failed_ids.append(str(uid))
            continue
        if '\\Seen' in message['flags']:
            message['flags'].discard('\\Seen')
            changed_ids.append(str(message.get('id', uid)))
    return changed_ids, failed_ids


def _add_dummy_tag(message_ids: list[str], normalized_tag: str) -> tuple[list[str], list[str]]:
    added_ids: list[str] = []
    failed_ids: list[str] = []
    for uid in message_ids:
        message = _find_dummy_message(uid)
        if message is None:
            failed_ids.append(str(uid))
            continue
        current = _normalized_keywords(message)
        if normalized_tag.lower() not in [item.lower() for item in current]:
            current.append(normalized_tag)
            message['keywords'] = current
            added_ids.append(str(message.get('id', uid)))
    return added_ids, failed_ids


def _remove_dummy_tag(message_ids: list[str], normalized_tag: str) -> tuple[list[str], list[str]]:
    removed_ids: list[str] = []
    failed_ids: list[str] = []
    for uid in message_ids:
        message = _find_dummy_message(uid)
        if message is None:
            failed_ids.append(str(uid))
            continue
        before = _normalized_keywords(message)
        after = [kw for kw in before if kw.lower() != normalized_tag.lower()]
        if after != before:
            message['keywords'] = after
            removed_ids.append(str(message.get('id', uid)))
    return removed_ids, failed_ids


def _add_env_tag(env: Any, normalized_tag: str, message_ids: list[str]) -> tuple[list[str], list[str]]:
    added: list[str] = []
    failed: list[str] = []
    for uid in message_ids:
        message = _find_env_message(env, uid)
        if message is None:
            failed.append(str(uid))
            continue
        current = [kw for kw in message['flags'] if not kw.startswith('\\')]
        if normalized_tag.lower() not in [item.lower() for item in current]:
            message['flags'].add(normalized_tag)
            added.append(str(message.get('id', uid)))
    return added, failed


def _remove_env_tag(env: Any, normalized_tag: str, message_ids: list[str]) -> tuple[list[str], list[str]]:
    removed: list[str] = []
    failed: list[str] = []
    for uid in message_ids:
        message = _find_env_message(env, uid)
        if message is None:
            failed.append(str(uid))
            continue
        to_remove = [kw for kw in list(message['flags']) if not kw.startswith(
            '\\') and kw.lower() == normalized_tag.lower()]
        if to_remove:
            for kw in to_remove:
                message['flags'].discard(kw)
            removed.append(str(message.get('id', uid)))
    return removed, failed


@contextmanager
def _imap_connection(host: str, port: int, use_ssl: bool, username: str | None, password: str | None) -> Any:
    imap = _open_imap(host, port, use_ssl)
    try:
        if username:
            try:
                imap.login(username, password or '')
            except imaplib.IMAP4.error as exc:
                raise MailServiceError(_redact_error_message(
                    'IMAP authentication failed', password)) from exc
        _select_inbox_or_raise(imap, password)
        yield imap
    finally:
        try:
            imap.logout()
        except (imaplib.IMAP4.error, OSError):
            pass


def _imap_message_from_uid(imap, uid: str) -> dict[str, Any] | None:
    try:
        ftyp, fdata = imap.uid('fetch', uid, '(BODY.PEEK[])')
    except (imaplib.IMAP4.error, OSError):
        return None
    if ftyp != 'OK' or not fdata:
        return None
    parsed = _parse_fetched_message(fdata)
    if parsed is None:
        return None
    msg, body_text = parsed
    flags = _fetch_flags(imap, uid)
    return {
        'id': uid,
        'subject': msg.get('Subject', ''),
        'sender': msg.get('From', ''),
        'recipient': msg.get('To', ''),
        'date': msg.get('Date', ''),
        'body': str(body_text),
        'unread': '\\Seen' not in flags,
        'replied': '\\Answered' in flags,
        'keywords': [f for f in flags if not f.startswith('\\')],
    }


def _collect_imap_messages(host: str | None, port: int, use_ssl: bool, username: str | None, password: str | None) -> list[dict[str, Any]]:
    msgs: list[dict[str, Any]] = []
    if host is None:
        return msgs
    with _imap_connection(host, port, use_ssl, username, password) as imap:
        typ, data = imap.uid('search', None, 'ALL')
        if typ != 'OK' or not data or not data[0]:
            return []
        raw_uids = data[0].split()
        for raw_uid in raw_uids:
            uid = raw_uid.decode('utf-8') if isinstance(raw_uid, bytes) else str(raw_uid)
            m = _imap_message_from_uid(imap, uid)
            if m is not None:
                msgs.append(m)
    return msgs


def _check_imap_connection(host: str | None, port: int, use_ssl: bool, username: str | None, password: str | None) -> tuple[bool, str]:
    if host is None:
        return False, 'No IMAP host configured'
    try:
        _env = _get_fake_env_for_host_port(host, port)
        if _env is not None:
            return True, 'IMAP OK'
        try:
            imap = _open_imap(host, port, use_ssl)
            try:
                if username:
                    try:
                        imap.login(username, password or '')
                    except imaplib.IMAP4.error:
                        return False, _redact_error_message('IMAP authentication failed', password)
                _select_inbox_or_raise(imap, password)
                return True, 'IMAP OK'
            finally:
                try:
                    imap.logout()
                except Exception:
                    pass
        except MailServiceError as exc:
            return False, str(exc)
        except (imaplib.IMAP4.error, OSError) as exc:
            return False, _redact_error_message(str(exc), password)
    except (imaplib.IMAP4.error, OSError) as exc:
        return False, _redact_error_message(str(exc), password)


def _check_smtp_connection(host: str | None, port: int, use_ssl: bool, username: str | None = None, password: str | None = None) -> tuple[bool, str]:
    if host is None:
        return False, 'No SMTP host configured'
    try:
        _env = _get_fake_env_for_host_port(host, port)
        if _env is not None:
            return True, 'SMTP OK'
        if use_ssl:
            smtp = smtplib.SMTP_SSL(host, port)
        else:
            smtp = smtplib.SMTP(host, port)
        try:
            smtp.ehlo()
            if username and password:
                try:
                    smtp.login(username, password)
                except smtplib.SMTPException:
                    return False, _redact_error_message('SMTP authentication failed', password)
            return True, 'SMTP OK'
        finally:
            try:
                smtp.quit()
            except Exception:
                pass
    except (smtplib.SMTPException, OSError) as exc:
        return False, _redact_error_message(str(exc), password)


def _add_tag_to_env(env: Any, normalized_tag: str, message_ids: list[str]) -> list[str]:
    added, _failed = _add_env_tag(env, normalized_tag, message_ids)
    return added


def _remove_tag_from_env(env: Any, normalized_tag: str, message_ids: list[str]) -> None:
    _remove_env_tag(env, normalized_tag, message_ids)


def _imap_add_flag(host: str | None, port: int, use_ssl: bool, username: str | None, password: str | None, message_ids: list[str], normalized_tag: str) -> tuple[list[str], list[str]]:
    added: list[str] = []
    failed: list[str] = []
    if host is None:
        return added, failed
    with _imap_connection(host, port, use_ssl, username, password) as imap:
        added, failed = _store_message_flags(imap, message_ids, '+FLAGS', f'({normalized_tag})')
    return added, failed


def _imap_remove_flag(host: str | None, port: int, use_ssl: bool, username: str | None, password: str | None, message_ids: list[str], normalized_tag: str) -> tuple[list[str], list[str]]:
    if host is None:
        return [], []
    with _imap_connection(host, port, use_ssl, username, password) as imap:
        return _store_message_flags(imap, message_ids, '-FLAGS', f'({normalized_tag})')


def _open_imap(host: str, port: int, use_ssl: bool) -> imaplib.IMAP4 | imaplib.IMAP4_SSL:
    try:
        return imaplib.IMAP4_SSL(host, port) if use_ssl else imaplib.IMAP4(host, port)
    except (imaplib.IMAP4.error, OSError) as exc:
        raise MailServiceError(str(exc)) from exc


def _fetch_flags(imap, uid: str) -> list[str]:
    try:
        rtyp, rdata = imap.uid('fetch', uid, '(FLAGS)')
        if rtyp == 'OK' and rdata and rdata[0]:
            flags_text = str(rdata[0])
            if 'FLAGS (' in flags_text:
                start = flags_text.find('FLAGS (') + len('FLAGS (')
                end = flags_text.find(')', start)
                return [f.strip() for f in flags_text[start:end].split() if f.strip()]
    except (imaplib.IMAP4.error, OSError):
        pass
    return []


def _parse_fetched_message(fdata: Any) -> tuple[EmailMessage, str] | None:
    raw = None
    if isinstance(fdata[0], tuple) and fdata[0][1] is not None:
        raw = fdata[0][1]
    elif len(fdata) > 1 and isinstance(fdata[1], (bytes, bytearray)):
        raw = fdata[1]
    if not raw:
        return None
    try:
        parser = BytesParser(policy=default)
        msg = parser.parsebytes(raw)
    except (TypeError, ValueError, UnicodeDecodeError):
        return None
    body = msg.get_body(preferencelist=('plain',))
    body_text = body.get_content() if body is not None else (msg.get_payload(decode=True) or '')
    return msg, str(body_text)


def search_messages(criteria: SearchCriteria, settings: dict[str, Any]) -> list[dict[str, Any]]:
    if is_dummy_mode(settings):
        return [deepcopy(message) for message in _dummy_mailbox if _matches_criteria(message, criteria)]

    # Live IMAP mode: fetch messages from configured IMAP server and filter locally
    messages: list[dict[str, Any]] = []
    host = settings.get('imapHost')
    port = int(settings.get('imapPort') or 993)
    use_ssl = bool(settings.get('imapUseSSL'))
    username = settings.get('username')
    password = settings.get('imapPassword')

    # If a fake mail environment is registered for this host/port, use it instead of making network calls
    _env = _get_fake_env_for_host_port(host, port)
    if _env is not None:
        return [deepcopy(message) for message in _env_messages_from_env(_env) if _matches_criteria(message, criteria)]

    try:
        messages = _collect_imap_messages(host, port, use_ssl, username, password)
    except (imaplib.IMAP4.error, OSError) as exc:
        raise MailServiceError(str(exc)) from exc

    return [deepcopy(message) for message in messages if _matches_criteria(message, criteria)]


def mark_messages_read(message_ids: list[str], settings: dict[str, Any]) -> dict[str, Any]:
    if is_dummy_mode(settings):
        changed_ids, failed_ids = _mark_dummy_messages_read(message_ids)
        return {'restore_unread_ids': changed_ids, 'failed_message_ids': failed_ids}
    host = settings.get('imapHost')
    port = int(settings.get('imapPort') or 993)
    use_ssl = bool(settings.get('imapUseSSL'))
    username = settings.get('username')
    password = settings.get('imapPassword')

    _env = _get_fake_env_for_host_port(host, port)
    if _env is not None:
        changed_ids, failed_ids = _mark_env_messages_read(_env, message_ids)
        return {'restore_unread_ids': changed_ids, 'failed_message_ids': failed_ids}

    if host is None:
        raise MailServiceError('IMAP host not configured')

    try:
        changed_ids: list[str] = []
        failed_ids: list[str] = []
        with _imap_connection(host, port, use_ssl, username, password) as imap:
            changed_ids, failed_ids = _store_message_flags(imap, message_ids, '+FLAGS', '(\\Seen)')
    except (imaplib.IMAP4.error, OSError) as exc:
        raise MailServiceError(_redact_error_message(str(exc), password)) from exc
    return {'restore_unread_ids': changed_ids, 'failed_message_ids': failed_ids}


def restore_messages_unread(message_ids: list[str], settings: dict[str, Any]) -> dict[str, Any]:
    if is_dummy_mode(settings):
        changed_ids, failed_ids = _restore_dummy_messages_unread(message_ids)
        return {'restore_unread_ids': changed_ids, 'failed_message_ids': failed_ids}
    host = settings.get('imapHost')
    port = int(settings.get('imapPort') or 993)
    use_ssl = bool(settings.get('imapUseSSL'))
    username = settings.get('username')
    password = settings.get('imapPassword')

    _env = _get_fake_env_for_host_port(host, port)
    if _env is not None:
        changed_ids, failed_ids = _restore_env_messages_unread(_env, message_ids)
        return {'restore_unread_ids': changed_ids, 'failed_message_ids': failed_ids}

    if host is None:
        raise MailServiceError('IMAP host not configured')

    try:
        with _imap_connection(host, port, use_ssl, username, password) as imap:
            changed_ids, failed_ids = _store_message_flags(imap, message_ids, '-FLAGS', '(\\Seen)')
    except (imaplib.IMAP4.error, OSError) as exc:
        raise MailServiceError(_redact_error_message(str(exc), password)) from exc
    return {'restore_unread_ids': changed_ids, 'failed_message_ids': failed_ids}


def add_keyword_tag(message_ids: list[str], tag: str, settings: dict[str, Any]) -> dict[str, Any]:
    normalized_tag = tag.strip()
    if not normalized_tag:
        return {'added_message_ids': [], 'failed_message_ids': []}
    added_message_ids: list[str] = []
    failed_message_ids: list[str] = []
    if is_dummy_mode(settings):
        added_message_ids, failed_message_ids = _add_dummy_tag(message_ids, normalized_tag)
        return {'added_message_ids': added_message_ids, 'failed_message_ids': failed_message_ids}
    # Live IMAP mode: use STORE to add flag
    host = settings.get('imapHost')
    port = int(settings.get('imapPort') or 993)
    use_ssl = bool(settings.get('imapUseSSL'))
    username = settings.get('username')
    password = settings.get('imapPassword')
    _env = _get_fake_env_for_host_port(host, port)
    if _env is not None:
        added_message_ids, failed_message_ids = _add_env_tag(_env, normalized_tag, message_ids)
        return {'added_message_ids': added_message_ids, 'failed_message_ids': failed_message_ids}

    try:
        added_message_ids, failed_message_ids = _imap_add_flag(
            host, port, use_ssl, username, password, message_ids, normalized_tag)
    except (imaplib.IMAP4.error, OSError) as exc:
        raise MailServiceError(_redact_error_message(str(exc), password)) from exc
    return {'added_message_ids': added_message_ids, 'failed_message_ids': failed_message_ids}


def remove_keyword_tag(message_ids: list[str], tag: str, settings: dict[str, Any]) -> dict[str, Any]:
    normalized_tag = tag.strip()
    if not normalized_tag:
        return {'removed_message_ids': [], 'failed_message_ids': []}
    if is_dummy_mode(settings):
        removed_message_ids, failed_message_ids = _remove_dummy_tag(message_ids, normalized_tag)
        return {'removed_message_ids': removed_message_ids, 'failed_message_ids': failed_message_ids}
    host = settings.get('imapHost')
    port = int(settings.get('imapPort') or 993)
    use_ssl = bool(settings.get('imapUseSSL'))
    username = settings.get('username')
    password = settings.get('imapPassword')
    _env = _get_fake_env_for_host_port(host, port)
    if _env is not None:
        removed_message_ids, failed_message_ids = _remove_env_tag(_env, normalized_tag, message_ids)
        return {'removed_message_ids': removed_message_ids, 'failed_message_ids': failed_message_ids}

    try:
        removed_message_ids, failed_message_ids = _imap_remove_flag(
            host, port, use_ssl, username, password, message_ids, normalized_tag)
    except (imaplib.IMAP4.error, OSError) as exc:
        raise MailServiceError(_redact_error_message(str(exc), password)) from exc
    return {'removed_message_ids': removed_message_ids, 'failed_message_ids': failed_message_ids}


def send_summary_email(recipient: str, subject: str, body: str, settings: dict[str, Any]) -> None:
    if is_dummy_mode(settings):
        _dummy_outbox.append({'recipient': recipient, 'subject': subject, 'body': body})
        return
    host = settings.get('smtpHost')
    port = int(settings.get('smtpPort') or 25)
    use_ssl = bool(settings.get('smtpUseSSL'))
    username = settings.get('username')
    password = settings.get('smtpPassword') or settings.get('imapPassword')
    if host is None:
        raise MailServiceError('SMTP host not configured')
    msg = EmailMessage()
    msg['Subject'] = subject
    msg['From'] = username or ''
    msg['To'] = recipient
    msg.set_content(body or '')
    # Check for fake mail environment for SMTP
    _env = _get_fake_env_for_host_port(host, port)
    if _env is not None:
        _env.sent_messages.append({'recipient': recipient, 'subject': subject, 'body': body})
        return
    try:
        if use_ssl:
            smtp = smtplib.SMTP_SSL(host, port)
        else:
            smtp = smtplib.SMTP(host, port)
        try:
            smtp.ehlo()
            if username and password:
                try:
                    smtp.login(username, password)
                except smtplib.SMTPException as exc:
                    raise MailServiceError(_redact_error_message(
                        'SMTP authentication failed', password)) from exc
            smtp.send_message(msg)
        finally:
            try:
                smtp.quit()
            except (smtplib.SMTPException, OSError):
                pass
    except (smtplib.SMTPException, OSError) as exc:
        raise MailServiceError(_redact_error_message(str(exc), password)) from exc


def test_mail_connection(settings: dict[str, Any]) -> dict[str, Any]:
    if is_dummy_mode(settings):
        return {
            'status': 'ok',
            'mode': 'dummy',
            'imap': {'status': 'ok', 'message': 'Sample mailbox uses resettable sample mail'},
            'smtp': {'status': 'ok', 'message': 'Sample mailbox uses the local sample outbox'},
            'details': {'messageCount': len(_dummy_mailbox)},
        }
    # Live IMAP/SMTP check
    host = settings.get('imapHost')
    port = int(settings.get('imapPort') or 993)
    use_ssl = bool(settings.get('imapUseSSL'))
    imap_ok = False
    imap_message = ''
    imap_ok, imap_message = _check_imap_connection(
        host, port, use_ssl, settings.get('username'), settings.get('imapPassword'))
    smtp_ok = False
    smtp_message = ''
    smtp_ok, smtp_message = _check_smtp_connection(
        settings.get('smtpHost'),
        int(settings.get('smtpPort') or 25),
        bool(settings.get('smtpUseSSL')),
        settings.get('username'),
        settings.get('smtpPassword') or settings.get('imapPassword'))
    return {
        'status': 'ok' if (imap_ok and smtp_ok) else 'warning',
        'mode': 'imap',
        'imap': {'status': 'ok' if imap_ok else 'error', 'message': imap_message or 'IMAP OK'},
        'smtp': {'status': 'ok' if smtp_ok else 'error', 'message': smtp_message or 'SMTP OK'},
        'details': {'messageCount': 0},
    }


def _parse_list_response(line: bytes | str) -> tuple[list[str], str | None, str | None]:
    """Parse a single IMAP LIST response line.

    Returns (flags_list, delimiter, mailbox_path). Returns empty values on
    unparseable lines. This is intentionally defensive: IMAP server LIST
    responses vary across implementations.
    """
    if isinstance(line, bytes):
        try:
            line = line.decode('utf-8', errors='replace')
        except (AttributeError, UnicodeDecodeError):
            line = str(line)

    # Typical format: (\Flag \Flag2) "/" "INBOX" or (\Flag) "/" INBOX
    line = line.strip()
    if not line:
        return [], None, None

    flags: list[str] = []
    delimiter: str | None = None
    path: str | None = None

    # Extract flags: content between the first '(' and matching ')'
    flag_start = line.find('(')
    flag_end = line.find(')', flag_start)
    if flag_start != -1 and flag_end != -1:
        flags_str = line[flag_start + 1:flag_end].strip()
        flags = [f.strip() for f in flags_str.split() if f.strip()] if flags_str else []
        remainder = line[flag_end + 1:].strip()
    else:
        remainder = line

    # Extract delimiter and path from remainder.  Both may be quoted.
    parts = remainder.split(None, 1)
    if not parts:
        return flags, None, None

    raw_delim = parts[0]
    delimiter = raw_delim.strip('"') if raw_delim != 'NIL' else None

    if len(parts) < 2:
        return flags, delimiter, None

    raw_path = parts[1].strip()
    # Strip surrounding quotes
    if raw_path.startswith('"') and raw_path.endswith('"') and len(raw_path) >= 2:
        path = raw_path[1:-1]
    else:
        path = raw_path

    return flags, delimiter, path


def discover_mailboxes_for_account(account: dict[str, Any]) -> list[dict[str, Any]]:
    """Discover IMAP mailboxes for the given account configuration.

    Returns a list of mailbox dicts with keys: path, delimiter, flags, selectable.
    Raises MailServiceError on connection or authentication failure.
    """
    host: str | None = account.get('imapHost') or None
    if not host:
        raise MailServiceError('IMAP host not configured for account')

    port = int(account.get('imapPort') or 993)
    use_ssl = bool(account.get('imapUseSSL', True))
    username: str | None = account.get('username') or None
    password: str | None = account.get('imapPassword') or None

    # Check for fake mail environment
    _env = _get_fake_env_for_host_port(host, port)
    if _env is not None:
        results = []
        for mbox in getattr(_env, 'mailboxes', []):
            results.append({
                'path': mbox.get('path', ''),
                'delimiter': mbox.get('delimiter'),
                'flags': list(mbox.get('flags', [])),
                'selectable': mbox.get('selectable', True),
            })
        return results

    imap = _open_imap(host, port, use_ssl)
    try:
        if username:
            try:
                imap.login(username, password or '')
            except imaplib.IMAP4.error as exc:
                raise MailServiceError(_redact_error_message(
                    'IMAP authentication failed', password)) from exc

        try:
            typ, data = imap.list('""', '*')
        except imaplib.IMAP4.error as exc:
            raise MailServiceError(_redact_error_message(str(exc), password)) from exc

        if typ != 'OK' or not data:
            return []

        results: list[dict[str, Any]] = []
        for item in data:
            if item is None:
                continue
            flags, delimiter, path = _parse_list_response(item)
            if path is None:
                continue
            noselect = any(f.lower() == '\\noselect' for f in flags)
            results.append({
                'path': path,
                'delimiter': delimiter,
                'flags': flags,
                'selectable': not noselect,
            })
        return results
    finally:
        try:
            imap.logout()
        except (imaplib.IMAP4.error, OSError):
            pass
