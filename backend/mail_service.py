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
        'flagged': False,
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
        'flagged': False,
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


def _safe_search_limit(criteria: SearchCriteria) -> int:
    try:
        value = int(getattr(criteria, 'limit', 100) or 100)
    except (TypeError, ValueError):
        return 100
    return max(1, min(value, 500))


def _unique_non_empty_values(values: list[Any]) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or '').strip()
        if not text or text in seen:
            continue
        seen.add(text)
        unique.append(text)
    return unique


def _combine_or_terms(terms: list[list[str]]) -> list[str]:
    if not terms:
        return ['ALL']
    combined = list(terms[0])
    for term in terms[1:]:
        combined = ['OR', *combined, *term]
    return combined


def _build_imap_search_terms(criteria: SearchCriteria) -> list[str]:
    atoms: list[list[str]] = []
    keyword = str(criteria.keyword or '').strip()
    raw_search = str(criteria.rawSearch or '').strip()
    sender = str(criteria.sender or '').strip()
    recipient = str(criteria.recipient or '').strip()
    tag = str(criteria.tag or '').strip()
    since = str(criteria.since or '').strip()
    before = str(criteria.before or '').strip()
    list_id = str(criteria.listId or '').strip()

    if criteria.unreadOnly:
        atoms.append(['UNSEEN'])
    if criteria.readOnly:
        atoms.append(['SEEN'])
    if criteria.flagged is True:
        atoms.append(['FLAGGED'])
    elif criteria.flagged is False:
        atoms.append(['UNFLAGGED'])
    if criteria.replied is True:
        atoms.append(['ANSWERED'])
    elif criteria.replied is False:
        atoms.append(['UNANSWERED'])
    if keyword:
        # TEXT is the broadest conservative server-side search for the existing
        # subject/body keyword field, and it is only used when the caller asks for it.
        atoms.append(['TEXT', keyword])
    if raw_search:
        atoms.append(['TEXT', raw_search])
    if sender:
        atoms.append(['FROM', sender])
    if recipient:
        atoms.append(['TO', recipient])
    if tag:
        atoms.append(['KEYWORD', tag])
    if since:
        atoms.append(['SINCE', since])
    if before:
        atoms.append(['BEFORE', before])
    if list_id:
        atoms.append(['HEADER', 'List-Id', list_id])

    if not atoms:
        return ['ALL']
    if criteria.useAnd:
        terms: list[str] = []
        for atom in atoms:
            terms.extend(atom)
        return terms
    return _combine_or_terms(atoms)


def _legacy_search_account(settings: dict[str, Any]) -> dict[str, Any] | None:
    host = str(settings.get('imapHost', '') or '').strip()
    if not host:
        return None
    return {
        'id': 'default',
        'imapHost': settings.get('imapHost', ''),
        'imapPort': int(settings.get('imapPort') or 993),
        'imapUseSSL': bool(settings.get('imapUseSSL', True)),
        'username': settings.get('username', ''),
        'imapPassword': settings.get('imapPassword', ''),
    }


def _explicit_search_accounts(settings: dict[str, Any]) -> list[dict[str, Any]]:
    raw_accounts = settings.get('mailAccounts') or []
    if not isinstance(raw_accounts, list):
        return []
    return [account for account in raw_accounts if isinstance(account, dict)]


def _resolve_search_accounts(settings: dict[str, Any], criteria: SearchCriteria) -> list[dict[str, Any]]:
    legacy_account = _legacy_search_account(settings)
    explicit_accounts = _explicit_search_accounts(settings)
    requested_ids = _unique_non_empty_values(list(getattr(criteria, 'accountIds', []) or []))

    if explicit_accounts and requested_ids:
        requested = set(requested_ids)
        selected: list[dict[str, Any]] = []
        for account in explicit_accounts:
            account_id = str(account.get('id', '') or '').strip()
            if account_id and account_id in requested and bool(account.get('enabled', True)):
                selected.append(account)
        return selected

    if legacy_account is not None:
        return [legacy_account]
    return []


def _resolve_search_mailboxes(criteria: SearchCriteria) -> list[str]:
    raw_mailboxes = list(getattr(criteria, 'mailboxes', []) or [])
    if raw_mailboxes:
        requested_mailboxes: list[str] = []
        seen: set[str] = set()
        for value in raw_mailboxes:
            mailbox = str(value or '').strip()
            if not mailbox:
                raise MailServiceError('Mailbox path must not be empty')
            if mailbox in seen:
                continue
            seen.add(mailbox)
            requested_mailboxes.append(mailbox)
        return requested_mailboxes
    return ['INBOX']


def _account_connection_details(account: dict[str, Any], settings: dict[str, Any]) -> tuple[str | None, int, bool, str | None, str | None]:
    host = str(account.get('imapHost') or settings.get('imapHost') or '').strip() or None
    port = int(account.get('imapPort') or settings.get('imapPort') or 993)
    use_ssl = bool(account.get('imapUseSSL') if 'imapUseSSL' in account else settings.get('imapUseSSL', True))
    username = str(account.get('username') or settings.get('username') or '').strip() or None
    password = str(account.get('imapPassword') or settings.get('imapPassword') or '')
    return host, port, use_ssl, username, password


def _compose_message_id(account_id: str, mailbox_path: str, uid: str) -> str:
    return f'{account_id}|{mailbox_path}|{uid}'


def _split_composite_id(message_id: str) -> tuple[str, str, str] | None:
    """Split a canonical ``account|mailbox|uid`` id.

    The account is the first segment and the uid is the last; any inner
    segments form the mailbox path, so mailbox names containing ``|`` survive
    a round trip. Returns ``None`` for non-composite (legacy/sample) ids.
    """
    text = str(message_id or '')
    if text.count('|') < 2:
        return None
    parts = text.split('|')
    account_id = parts[0]
    uid = parts[-1]
    mailbox_path = '|'.join(parts[1:-1])
    if not account_id or not mailbox_path or not uid:
        return None
    return account_id, mailbox_path, uid


def _plan_action_groups(
    message_ids: list[str],
) -> tuple[dict[tuple[str, str], list[tuple[str, str]]], list[tuple[str, str]]]:
    """Group message ids for per-account/mailbox action routing.

    Returns ``(composite_groups, legacy_units)`` where each unit is a
    ``(uid, external_id)`` pair. ``external_id`` is what callers passed in, so
    aggregated results echo composite ids for composite inputs and the original
    (unwrapped) id for legacy/sample inputs.
    """
    composite_groups: dict[tuple[str, str], list[tuple[str, str]]] = {}
    legacy_units: list[tuple[str, str]] = []
    for raw in message_ids:
        external_id = str(raw)
        split = _split_composite_id(external_id)
        if split is None:
            legacy_units.append((external_id, external_id))
            continue
        account_id, mailbox_path, uid = split
        composite_groups.setdefault((account_id, mailbox_path), []).append((uid, external_id))
    return composite_groups, legacy_units


def _matches_criteria(message: dict[str, Any], criteria: SearchCriteria) -> bool:
    checks: list[bool] = []
    subject = str(message.get('subject', ''))
    body = str(message.get('body', ''))
    sender = str(message.get('sender', ''))
    recipient = str(message.get('recipient', ''))
    keywords = [item.lower() for item in _normalized_keywords(message)]
    account_id = str(message.get('accountId', '') or '').strip()
    mailbox_path = str(message.get('mailboxPath', '') or '').strip()
    list_id = str(message.get('listId', '') or '').strip()

    if criteria.keyword:
        checks.append(criteria.keyword.lower() in f'{subject} {body}'.lower())
    if criteria.rawSearch:
        hay = f"{subject} {body} {sender} {recipient} {' '.join(keywords)}".lower()
        checks.append(criteria.rawSearch.lower() in hay)
    if criteria.accountIds and account_id:
        requested_accounts = {str(item).strip() for item in criteria.accountIds if str(item).strip()}
        checks.append(account_id in requested_accounts)
    if criteria.mailboxes and mailbox_path:
        requested_mailboxes = {str(item).strip() for item in criteria.mailboxes if str(item).strip()}
        checks.append(mailbox_path in requested_mailboxes)
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
    if criteria.flagged is not None:
        checks.append(bool(message.get('flagged')) is criteria.flagged)
    if criteria.replied is not None:
        checks.append(bool(message.get('replied')) is criteria.replied)
    if criteria.listId and list_id:
        checks.append(criteria.listId.lower() in list_id.lower())

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
            'flagged': '\\Flagged' in flags,
            'keywords': [f for f in flags if not f.startswith('\\')],
        })
    return env_messages


def _find_dummy_message(message_id: str) -> dict[str, Any] | None:
    target = str(message_id)
    for message in _dummy_mailbox:
        if str(message.get('id', '')) == target:
            return message
    split = _split_composite_id(target)
    if split is not None:
        _, _, uid = split
        for message in _dummy_mailbox:
            if str(message.get('id', '')) == uid:
                return message
    return None


def _find_env_message(env: Any, message_id: str) -> dict[str, Any] | None:
    for message in env.messages.values():
        if str(message.get('id', '')) == str(message_id):
            return message
    return None


def _select_mailbox_or_raise(imap: Any, mailbox_path: str, password: str | None) -> None:
    mailbox = str(mailbox_path or '').strip()
    if not mailbox:
        raise MailServiceError('Mailbox path must not be empty')
    try:
        typ, data = imap.select(mailbox)
    except imaplib.IMAP4.error as exc:
        raise MailServiceError(
            _redact_error_message(f'Could not select mailbox {mailbox}: {exc}', password)
        ) from exc
    if str(typ).upper() != 'OK':
        reason = _response_text(data)
        message = f'Could not select mailbox {mailbox}'
        if reason:
            message = f'{message}: {_redact_error_message(reason, password)}'
        raise MailServiceError(message)


def _select_inbox_or_raise(imap: Any, password: str | None) -> None:
    _select_mailbox_or_raise(imap, 'INBOX', password)


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
def _imap_connection(host: str, port: int, use_ssl: bool, username: str | None, password: str | None, mailbox_path: str = 'INBOX') -> Any:
    imap = _open_imap(host, port, use_ssl)
    try:
        if username:
            try:
                imap.login(username, password or '')
            except imaplib.IMAP4.error as exc:
                raise MailServiceError(_redact_error_message(
                    'IMAP authentication failed', password)) from exc
        _select_mailbox_or_raise(imap, mailbox_path, password)
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
        'listId': msg.get('List-Id', ''),
        'body': str(body_text),
        'unread': '\\Seen' not in flags,
        'replied': '\\Answered' in flags,
        'flagged': '\\Flagged' in flags,
        'keywords': [f for f in flags if not f.startswith('\\')],
    }


def _collect_imap_messages(criteria: SearchCriteria, settings: dict[str, Any]) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    search_terms = _build_imap_search_terms(criteria)
    requested_mailboxes = _resolve_search_mailboxes(criteria)
    limit = _safe_search_limit(criteria)

    candidate_accounts = _resolve_search_accounts(settings, criteria)
    if not candidate_accounts:
        legacy_account = _legacy_search_account(settings)
        candidate_accounts = [legacy_account] if legacy_account is not None else []

    fake_env = None
    for account in candidate_accounts:
        host, port, _use_ssl, _username, _password = _account_connection_details(account, settings)
        fake_env = _get_fake_env_for_host_port(host, port)
        if fake_env is not None:
            break

    if fake_env is not None:
        available_mailboxes = {
            str(mbox.get('path', '')).strip()
            for mbox in getattr(fake_env, 'mailboxes', [])
            if str(mbox.get('path', '')).strip()
        }
        for mailbox_path in requested_mailboxes:
            if mailbox_path not in available_mailboxes:
                raise MailServiceError(f'Could not select mailbox {mailbox_path}')
        return [
            deepcopy(message)
            for message in _env_messages_from_env(fake_env)
            if _matches_criteria(message, criteria)
        ][:limit]

    for account in _resolve_search_accounts(settings, criteria):
        account_id = str(account.get('id', '') or '').strip() or 'default'
        host, port, use_ssl, username, password = _account_connection_details(account, settings)
        if not host:
            continue

        for mailbox_path in requested_mailboxes:
            if len(messages) >= limit:
                return messages
            with _imap_connection(host, port, use_ssl, username, password, mailbox_path=mailbox_path) as imap:
                typ, data = imap.uid('search', None, *search_terms)
                if str(typ).upper() != 'OK' or not data or not data[0]:
                    continue
                raw_uids = data[0].split()
                remaining = limit - len(messages)
                for raw_uid in raw_uids[:remaining]:
                    uid = raw_uid.decode('utf-8') if isinstance(raw_uid, bytes) else str(raw_uid)
                    message = _imap_message_from_uid(imap, uid)
                    if message is None:
                        continue
                    message['accountId'] = account_id
                    message['mailboxPath'] = mailbox_path
                    message['uid'] = uid
                    message['id'] = _compose_message_id(account_id, mailbox_path, uid)
                    if _matches_criteria(message, criteria):
                        messages.append(message)
                        if len(messages) >= limit:
                            return messages
    return messages


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
    try:
        return _collect_imap_messages(criteria, settings)
    except (imaplib.IMAP4.error, OSError) as exc:
        raise MailServiceError(str(exc)) from exc


def _resolve_action_account(account_id: str, settings: dict[str, Any]) -> dict[str, Any] | None:
    """Resolve the enabled account for a composite id, or None if unroutable."""
    target = str(account_id or '').strip()
    for account in _explicit_search_accounts(settings):
        if str(account.get('id', '') or '').strip() == target:
            if not bool(account.get('enabled', True)):
                return None
            return account
    legacy = _legacy_search_account(settings)
    if legacy is not None and target in ('', 'default', 'sample'):
        return legacy
    return None


def _apply_grouped_message_action(
    message_ids: list[str],
    settings: dict[str, Any],
    *,
    imap_op: Any,
    env_op: Any,
) -> tuple[list[str], list[str]]:
    """Route an action over composite ids grouped by account and mailbox.

    ``imap_op(imap, uids)`` and ``env_op(env, uids)`` each return
    ``(changed_uids, failed_uids)``. Results are mapped back to the ids the
    caller passed in. Legacy (non-composite) ids route to the single legacy
    account against INBOX and are returned unwrapped.
    """
    composite_groups, legacy_units = _plan_action_groups(message_ids)
    changed: list[str] = []
    failed: list[str] = []

    def run_unit(account: dict[str, Any] | None, mailbox_path: str, units: list[tuple[str, str]]) -> None:
        external_by_uid = {uid: external for uid, external in units}
        uids = [uid for uid, _external in units]

        def externals(values: list[str]) -> list[str]:
            return [external_by_uid.get(str(value), str(value)) for value in values]

        if account is None:
            failed.extend(external for _uid, external in units)
            return
        host, port, use_ssl, username, password = _account_connection_details(account, settings)
        env = _get_fake_env_for_host_port(host, port)
        if env is not None:
            changed_uids, failed_uids = env_op(env, uids)
            changed.extend(externals(changed_uids))
            failed.extend(externals(failed_uids))
            return
        if host is None:
            raise MailServiceError('IMAP host not configured')
        try:
            with _imap_connection(host, port, use_ssl, username, password, mailbox_path) as imap:
                changed_uids, failed_uids = imap_op(imap, uids)
        except (imaplib.IMAP4.error, OSError) as exc:
            raise MailServiceError(_redact_error_message(str(exc), password)) from exc
        changed.extend(externals(changed_uids))
        failed.extend(externals(failed_uids))

    if legacy_units:
        legacy_account = _legacy_search_account(settings)
        if legacy_account is None:
            raise MailServiceError('IMAP host not configured')
        run_unit(legacy_account, 'INBOX', legacy_units)

    for (account_id, mailbox_path), units in composite_groups.items():
        run_unit(_resolve_action_account(account_id, settings), mailbox_path, units)

    return changed, failed


def unroutable_message_ids(message_ids: list[str], settings: dict[str, Any]) -> list[str]:
    """Return ids that cannot be routed to a configured, enabled account.

    Used by action previews to warn before applying. Sample/dummy mode treats
    everything as routable.
    """
    if is_dummy_mode(settings):
        return []
    composite_groups, legacy_units = _plan_action_groups(message_ids)
    unroutable: list[str] = []
    if legacy_units and _legacy_search_account(settings) is None:
        unroutable.extend(external for _uid, external in legacy_units)
    for (account_id, _mailbox), units in composite_groups.items():
        if _resolve_action_account(account_id, settings) is None:
            unroutable.extend(external for _uid, external in units)
    return unroutable


def mark_messages_read(message_ids: list[str], settings: dict[str, Any]) -> dict[str, Any]:
    if is_dummy_mode(settings):
        changed_ids, failed_ids = _mark_dummy_messages_read(message_ids)
        return {'restore_unread_ids': changed_ids, 'failed_message_ids': failed_ids}
    changed_ids, failed_ids = _apply_grouped_message_action(
        message_ids, settings,
        imap_op=lambda imap, uids: _store_message_flags(imap, uids, '+FLAGS', '(\\Seen)'),
        env_op=lambda env, uids: _mark_env_messages_read(env, uids),
    )
    return {'restore_unread_ids': changed_ids, 'failed_message_ids': failed_ids}


def restore_messages_unread(message_ids: list[str], settings: dict[str, Any]) -> dict[str, Any]:
    if is_dummy_mode(settings):
        changed_ids, failed_ids = _restore_dummy_messages_unread(message_ids)
        return {'restore_unread_ids': changed_ids, 'failed_message_ids': failed_ids}
    changed_ids, failed_ids = _apply_grouped_message_action(
        message_ids, settings,
        imap_op=lambda imap, uids: _store_message_flags(imap, uids, '-FLAGS', '(\\Seen)'),
        env_op=lambda env, uids: _restore_env_messages_unread(env, uids),
    )
    return {'restore_unread_ids': changed_ids, 'failed_message_ids': failed_ids}


def add_keyword_tag(message_ids: list[str], tag: str, settings: dict[str, Any]) -> dict[str, Any]:
    normalized_tag = tag.strip()
    if not normalized_tag:
        return {'added_message_ids': [], 'failed_message_ids': []}
    if is_dummy_mode(settings):
        added_message_ids, failed_message_ids = _add_dummy_tag(message_ids, normalized_tag)
        return {'added_message_ids': added_message_ids, 'failed_message_ids': failed_message_ids}
    added_message_ids, failed_message_ids = _apply_grouped_message_action(
        message_ids, settings,
        imap_op=lambda imap, uids: _store_message_flags(imap, uids, '+FLAGS', f'({normalized_tag})'),
        env_op=lambda env, uids: _add_env_tag(env, normalized_tag, uids),
    )
    return {'added_message_ids': added_message_ids, 'failed_message_ids': failed_message_ids}


def remove_keyword_tag(message_ids: list[str], tag: str, settings: dict[str, Any]) -> dict[str, Any]:
    normalized_tag = tag.strip()
    if not normalized_tag:
        return {'removed_message_ids': [], 'failed_message_ids': []}
    if is_dummy_mode(settings):
        removed_message_ids, failed_message_ids = _remove_dummy_tag(message_ids, normalized_tag)
        return {'removed_message_ids': removed_message_ids, 'failed_message_ids': failed_message_ids}
    removed_message_ids, failed_message_ids = _apply_grouped_message_action(
        message_ids, settings,
        imap_op=lambda imap, uids: _store_message_flags(imap, uids, '-FLAGS', f'({normalized_tag})'),
        env_op=lambda env, uids: _remove_env_tag(env, normalized_tag, uids),
    )
    return {'removed_message_ids': removed_message_ids, 'failed_message_ids': failed_message_ids}


def _parse_copyuid(data: Any) -> str | None:
    """Best-effort parse of the UIDPLUS COPYUID destination uid from a response."""
    try:
        for part in data or []:
            text = part.decode() if isinstance(part, (bytes, bytearray)) else str(part)
            upper = text.upper()
            if 'COPYUID' not in upper:
                continue
            tail = upper.split('COPYUID', 1)[1].replace(']', '')
            tokens = tail.split()
            if len(tokens) >= 3:
                return tokens[2].split(':')[0]
    except (ValueError, AttributeError, IndexError):
        return None
    return None


def _imap_move_messages(imap: Any, message_ids: list[str], target_mailbox: str) -> tuple[dict[str, str], list[str]]:
    """Move uids in the selected mailbox to ``target_mailbox``.

    Prefers IMAP MOVE (RFC 6851); otherwise COPY then mark ``\\Deleted`` and
    EXPUNGE. Returns ``({source_uid: new_uid}, failed_uids)``.
    """
    moved: dict[str, str] = {}
    failed: list[str] = []
    capabilities = getattr(imap, 'capabilities', ()) or ()
    use_move = 'MOVE' in capabilities
    expunge_needed = False
    for uid in message_ids:
        try:
            command = 'MOVE' if use_move else 'COPY'
            typ, data = imap.uid(command, str(uid), target_mailbox)
            if str(typ).upper() != 'OK':
                failed.append(str(uid))
                continue
            new_uid = _parse_copyuid(data) or str(uid)
            if not use_move:
                imap.uid('STORE', str(uid), '+FLAGS', '(\\Deleted)')
                expunge_needed = True
            moved[str(uid)] = new_uid
        except (imaplib.IMAP4.error, OSError):
            failed.append(str(uid))
    if expunge_needed:
        try:
            imap.expunge()
        except (imaplib.IMAP4.error, OSError):
            pass
    return moved, failed


def _move_env_messages(env: Any, message_ids: list[str], dest_mailbox: str) -> tuple[dict[str, str], list[str]]:
    moved: dict[str, str] = {}
    failed: list[str] = []
    for uid in message_ids:
        message = _find_env_message(env, uid)
        if message is None:
            failed.append(str(uid))
            continue
        message['mailbox'] = dest_mailbox
        moved[str(uid)] = str(uid)
    return moved, failed


def _move_dummy_messages(message_ids: list[str], target_mailbox: str) -> tuple[list[dict[str, Any]], list[str]]:
    moved: list[dict[str, Any]] = []
    failed: list[str] = []
    for raw in message_ids:
        message = _find_dummy_message(raw)
        if message is None:
            failed.append(str(raw))
            continue
        source = str(message.get('mailbox', 'INBOX'))
        if source == target_mailbox:
            continue
        message['mailbox'] = target_mailbox
        uid = str(message.get('id', raw))
        moved.append({'id': str(raw), 'accountId': 'sample', 'sourceMailbox': source,
                      'targetMailbox': target_mailbox, 'newUid': uid, 'movedId': uid})
    return moved, failed


def _move_dummy_back(moved_entries: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
    restored: list[str] = []
    failed: list[str] = []
    for entry in moved_entries:
        lookup = str(entry.get('newUid') or entry.get('id') or '')
        message = _find_dummy_message(lookup)
        if message is None:
            failed.append(lookup)
            continue
        message['mailbox'] = str(entry.get('sourceMailbox', 'INBOX'))
        restored.append(str(message.get('id', lookup)))
    return restored, failed


def _move_one_group(account: dict[str, Any] | None, account_id: str, source_mailbox: str,
                    target_mailbox: str, units: list[tuple[str, str]], settings: dict[str, Any],
                    moved: list[dict[str, Any]], failed: list[str]) -> None:
    external_by_uid = {uid: external for uid, external in units}
    uids = [uid for uid, _external in units]
    if account is None:
        failed.extend(external for _uid, external in units)
        return
    if source_mailbox == target_mailbox:
        return
    host, port, use_ssl, username, password = _account_connection_details(account, settings)
    env = _get_fake_env_for_host_port(host, port)
    if env is not None:
        new_map, failed_uids = _move_env_messages(env, uids, target_mailbox)
    else:
        if host is None:
            raise MailServiceError('IMAP host not configured')
        try:
            with _imap_connection(host, port, use_ssl, username, password, source_mailbox) as imap:
                new_map, failed_uids = _imap_move_messages(imap, uids, target_mailbox)
        except (imaplib.IMAP4.error, OSError) as exc:
            raise MailServiceError(_redact_error_message(str(exc), password)) from exc
    for uid in uids:
        if uid in new_map:
            moved.append({'id': external_by_uid[uid], 'accountId': account_id,
                          'sourceMailbox': source_mailbox, 'targetMailbox': target_mailbox,
                          'newUid': new_map[uid],
                          'movedId': _compose_message_id(account_id, target_mailbox, new_map[uid])})
        else:
            failed.append(external_by_uid[uid])


def _move_groups(message_ids: list[str], target_mailbox: str,
                 settings: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    composite_groups, legacy_units = _plan_action_groups(message_ids)
    moved: list[dict[str, Any]] = []
    failed: list[str] = []
    if legacy_units:
        legacy_account = _legacy_search_account(settings)
        if legacy_account is None:
            raise MailServiceError('IMAP host not configured')
        _move_one_group(legacy_account, 'default', 'INBOX', target_mailbox, legacy_units,
                        settings, moved, failed)
    for (account_id, source_mailbox), units in composite_groups.items():
        _move_one_group(_resolve_action_account(account_id, settings), account_id, source_mailbox,
                        target_mailbox, units, settings, moved, failed)
    return moved, failed


def _move_back_groups(moved_entries: list[dict[str, Any]],
                      settings: dict[str, Any]) -> tuple[list[str], list[str]]:
    groups: dict[tuple[str, str, str], list[str]] = {}
    for entry in moved_entries:
        account_id = str(entry.get('accountId', '') or '')
        from_mailbox = str(entry.get('targetMailbox', '') or '')
        to_mailbox = str(entry.get('sourceMailbox', '') or 'INBOX')
        groups.setdefault((account_id, from_mailbox, to_mailbox), []).append(str(entry.get('newUid', '')))
    restored: list[str] = []
    failed: list[str] = []
    for (account_id, from_mailbox, to_mailbox), uids in groups.items():
        account = _resolve_action_account(account_id, settings)
        if account is None:
            failed.extend(uids)
            continue
        host, port, use_ssl, username, password = _account_connection_details(account, settings)
        env = _get_fake_env_for_host_port(host, port)
        if env is not None:
            new_map, failed_uids = _move_env_messages(env, uids, to_mailbox)
        else:
            if host is None:
                raise MailServiceError('IMAP host not configured')
            try:
                with _imap_connection(host, port, use_ssl, username, password, from_mailbox) as imap:
                    new_map, failed_uids = _imap_move_messages(imap, uids, to_mailbox)
            except (imaplib.IMAP4.error, OSError) as exc:
                raise MailServiceError(_redact_error_message(str(exc), password)) from exc
        restored.extend(new_map.keys())
        failed.extend(failed_uids)
    return restored, failed


def move_messages(message_ids: list[str], target_mailbox: str,
                  settings: dict[str, Any]) -> dict[str, Any]:
    target = str(target_mailbox or '').strip()
    if not target:
        raise MailServiceError('Target mailbox not configured')
    if is_dummy_mode(settings):
        moved, failed = _move_dummy_messages(message_ids, target)
        return {'moved': moved, 'failed_message_ids': failed}
    moved, failed = _move_groups(message_ids, target, settings)
    return {'moved': moved, 'failed_message_ids': failed}


def move_messages_back(moved_entries: list[dict[str, Any]],
                       settings: dict[str, Any]) -> dict[str, Any]:
    if is_dummy_mode(settings):
        restored, failed = _move_dummy_back(moved_entries)
        return {'restored_message_ids': restored, 'failed_message_ids': failed}
    restored, failed = _move_back_groups(moved_entries, settings)
    return {'restored_message_ids': restored, 'failed_message_ids': failed}


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


def _consume_imap_list_token(text: str, start: int = 0) -> tuple[bool, str | None, int]:
    idx = start
    length = len(text)
    while idx < length and text[idx].isspace():
        idx += 1
    if idx >= length:
        return False, None, idx

    if text[idx] == '"':
        idx += 1
        chars: list[str] = []
        escaped = False
        while idx < length:
            char = text[idx]
            if escaped:
                chars.append(char)
                escaped = False
            elif char == '\\':
                escaped = True
            elif char == '"':
                return True, ''.join(chars), idx + 1
            else:
                chars.append(char)
            idx += 1
        if escaped:
            chars.append('\\')
        return True, ''.join(chars), idx

    start_idx = idx
    while idx < length and not text[idx].isspace():
        idx += 1
    token = text[start_idx:idx]
    if not token:
        return False, None, idx
    if token.upper() == 'NIL':
        return True, None, idx
    return True, token, idx


def _mailbox_is_selectable(flags: list[str]) -> bool:
    return not any(flag.lower() == '\\noselect' for flag in flags)


def _parse_list_response(line: bytes | str) -> tuple[list[str], str | None, str | None]:
    """Parse a single IMAP LIST response line.

    Returns (flags_list, delimiter, mailbox_path). Returns empty values on
    unparseable lines. This is intentionally defensive: IMAP server LIST
    responses vary across implementations.
    """
    if isinstance(line, (list, tuple)):
        for item in line:
            if isinstance(item, (bytes, bytearray, str)):
                line = item
                break
        else:
            return [], None, None

    if isinstance(line, bytes):
        try:
            line = line.decode('utf-8', errors='replace')
        except (AttributeError, UnicodeDecodeError):
            line = str(line)
    elif not isinstance(line, str):
        line = str(line)

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

    has_delimiter, delimiter, position = _consume_imap_list_token(remainder, 0)
    if not has_delimiter:
        return flags, None, None

    has_path, path, _ = _consume_imap_list_token(remainder, position)
    if not has_path:
        return flags, delimiter, None

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
            raw_flags = mbox.get('flags', []) or []
            flags = [str(flag) for flag in raw_flags if str(flag).strip()]
            results.append({
                'path': str(mbox.get('path', '')),
                'delimiter': mbox.get('delimiter'),
                'flags': flags,
                'selectable': bool(mbox.get('selectable', True)) and _mailbox_is_selectable(flags),
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
            typ, data = imap.list('', '*')
        except imaplib.IMAP4.error as exc:
            raise MailServiceError(_redact_error_message(str(exc), password)) from exc

        if str(typ).upper() != 'OK':
            reason = _response_text(data)
            message = 'Could not list mailboxes'
            if reason:
                message = f'{message}: {_redact_error_message(reason, password)}'
            raise MailServiceError(message)

        if not data:
            return []

        results: list[dict[str, Any]] = []
        for item in data:
            if item is None:
                continue
            flags, delimiter, path = _parse_list_response(item)
            if path is None:
                continue
            results.append({
                'path': path,
                'delimiter': delimiter,
                'flags': flags,
                'selectable': _mailbox_is_selectable(flags),
            })
        return results
    finally:
        try:
            imap.logout()
        except (imaplib.IMAP4.error, OSError):
            pass
