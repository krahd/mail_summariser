from __future__ import annotations

from copy import deepcopy
from typing import Any
import imaplib
from email.parser import BytesParser
from email.policy import default
import smtplib
from email.message import EmailMessage

from backend.schemas import SearchCriteria


class MailServiceError(RuntimeError):
    pass


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
    global _dummy_mailbox
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
    try:
        imap = imaplib.IMAP4_SSL(host, port) if use_ssl else imaplib.IMAP4(host, port)
    except Exception as exc:
        raise MailServiceError(str(exc)) from exc

    try:
        if username:
            try:
                imap.login(username, password or '')
            except Exception:
                pass

        imap.select('INBOX')
        typ, data = imap.uid('search', None, 'ALL')
        if typ != 'OK' or not data or not data[0]:
            try:
                imap.logout()
            except Exception:
                pass
            return []

        raw_uids = data[0].split()
        for raw_uid in raw_uids:
            uid = raw_uid.decode('utf-8') if isinstance(raw_uid, bytes) else str(raw_uid)
            try:
                ftyp, fdata = imap.uid('fetch', uid, '(BODY.PEEK[])')
            except Exception:
                continue
            if ftyp != 'OK' or not fdata:
                continue

            raw = None
            if isinstance(fdata[0], tuple) and fdata[0][1] is not None:
                raw = fdata[0][1]
            elif len(fdata) > 1 and isinstance(fdata[1], (bytes, bytearray)):
                raw = fdata[1]
            if not raw:
                continue

            try:
                parser = BytesParser(policy=default)
                msg = parser.parsebytes(raw)
            except Exception:
                continue

            body = msg.get_body(preferencelist=('plain',))
            body_text = body.get_content() if body is not None else (msg.get_payload(decode=True) or '')

            flags: list[str] = []
            try:
                rtyp, rdata = imap.uid('fetch', uid, '(FLAGS)')
                if rtyp == 'OK' and rdata and rdata[0]:
                    flags_text = str(rdata[0])
                    if 'FLAGS (' in flags_text:
                        start = flags_text.find('FLAGS (') + len('FLAGS (')
                        end = flags_text.find(')', start)
                        flags = [f.strip() for f in flags_text[start:end].split() if f.strip()]
            except Exception:
                flags = []

            messages.append({
                'id': uid,
                'subject': msg.get('Subject', ''),
                'sender': msg.get('From', ''),
                'recipient': msg.get('To', ''),
                'date': msg.get('Date', ''),
                'body': str(body_text),
                'unread': '\\Seen' not in flags,
                'replied': '\\Answered' in flags,
                'keywords': [f for f in flags if not f.startswith('\\')],
            })

    finally:
        try:
            imap.logout()
        except Exception:
            pass

    return [deepcopy(message) for message in messages if _matches_criteria(message, criteria)]


def mark_messages_read(message_ids: list[str], settings: dict[str, Any]) -> dict[str, Any]:
    if is_dummy_mode(settings):
        changed_ids: list[str] = []
        for message in _find_dummy_messages(message_ids):
            if message.get('unread'):
                message['unread'] = False
                changed_ids.append(message['id'])
        return {'restore_unread_ids': changed_ids}

    host = settings.get('imapHost')
    port = int(settings.get('imapPort') or 993)
    use_ssl = bool(settings.get('imapUseSSL'))
    username = settings.get('username')
    password = settings.get('imapPassword')
    try:
        imap = imaplib.IMAP4_SSL(host, port) if use_ssl else imaplib.IMAP4(host, port)
        if username:
            try:
                imap.login(username, password or '')
            except Exception:
                pass
        imap.select('INBOX')
        for uid in message_ids:
            try:
                imap.uid('STORE', str(uid), '+FLAGS', '(\\Seen)')
            except Exception:
                pass
        try:
            imap.logout()
        except Exception:
            pass
    except Exception as exc:
        raise MailServiceError(str(exc)) from exc
    return {'restore_unread_ids': []}


def restore_messages_unread(message_ids: list[str], settings: dict[str, Any]) -> None:
    if is_dummy_mode(settings):
        for message in _find_dummy_messages(message_ids):
            message['unread'] = True
        return

    host = settings.get('imapHost')
    port = int(settings.get('imapPort') or 993)
    use_ssl = bool(settings.get('imapUseSSL'))
    username = settings.get('username')
    password = settings.get('imapPassword')
    try:
        imap = imaplib.IMAP4_SSL(host, port) if use_ssl else imaplib.IMAP4(host, port)
        if username:
            try:
                imap.login(username, password or '')
            except Exception:
                pass
        imap.select('INBOX')
        for uid in message_ids:
            try:
                imap.uid('STORE', str(uid), '-FLAGS', '(\\Seen)')
            except Exception:
                pass
        try:
            imap.logout()
        except Exception:
            pass
    except Exception as exc:
        raise MailServiceError(str(exc)) from exc


def add_keyword_tag(message_ids: list[str], tag: str, settings: dict[str, Any]) -> dict[str, Any]:
    normalized_tag = tag.strip()
    if not normalized_tag:
        return {'added_message_ids': []}
    added_message_ids: list[str] = []
    if is_dummy_mode(settings):
        for message in _find_dummy_messages(message_ids):
            current = _normalized_keywords(message)
            if normalized_tag.lower() not in [item.lower() for item in current]:
                current.append(normalized_tag)
                message['keywords'] = current
                added_message_ids.append(message['id'])
        return {'added_message_ids': added_message_ids}
    # Live IMAP mode: use STORE to add flag
    host = settings.get('imapHost')
    port = int(settings.get('imapPort') or 993)
    use_ssl = bool(settings.get('imapUseSSL'))
    username = settings.get('username')
    password = settings.get('imapPassword')
    try:
        imap = imaplib.IMAP4_SSL(host, port) if use_ssl else imaplib.IMAP4(host, port)
        if username:
            try:
                imap.login(username, password or '')
            except Exception:
                pass
        imap.select('INBOX')
        for uid in message_ids:
            try:
                imap.uid('STORE', str(uid), '+FLAGS', f'({normalized_tag})')
                added_message_ids.append(str(uid))
            except Exception:
                pass
        imap.logout()
    except Exception as exc:
        raise MailServiceError(str(exc)) from exc
    return {'added_message_ids': added_message_ids}


def remove_keyword_tag(message_ids: list[str], tag: str, settings: dict[str, Any]) -> None:
    normalized_tag = tag.strip()
    if is_dummy_mode(settings):
        for message in _find_dummy_messages(message_ids):
            message['keywords'] = [kw for kw in _normalized_keywords(
                message) if kw.lower() != normalized_tag.lower()]
        return
    host = settings.get('imapHost')
    port = int(settings.get('imapPort') or 993)
    use_ssl = bool(settings.get('imapUseSSL'))
    username = settings.get('username')
    password = settings.get('imapPassword')
    try:
        imap = imaplib.IMAP4_SSL(host, port) if use_ssl else imaplib.IMAP4(host, port)
        if username:
            try:
                imap.login(username, password or '')
            except Exception:
                pass
        imap.select('INBOX')
        for uid in message_ids:
            try:
                imap.uid('STORE', str(uid), '-FLAGS', f'({normalized_tag})')
            except Exception:
                pass
        imap.logout()
    except Exception as exc:
        raise MailServiceError(str(exc)) from exc


def send_summary_email(recipient: str, subject: str, body: str, settings: dict[str, Any]) -> None:
    if is_dummy_mode(settings):
        _dummy_outbox.append({'recipient': recipient, 'subject': subject, 'body': body})
        return
    host = settings.get('smtpHost')
    port = int(settings.get('smtpPort') or 25)
    use_ssl = bool(settings.get('smtpUseSSL'))
    username = settings.get('username')
    password = settings.get('smtpPassword') or settings.get('imapPassword')
    msg = EmailMessage()
    msg['Subject'] = subject
    msg['From'] = username or ''
    msg['To'] = recipient
    msg.set_content(body or '')
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
                except Exception:
                    pass
            smtp.send_message(msg)
        finally:
            try:
                smtp.quit()
            except Exception:
                pass
    except Exception as exc:
        raise MailServiceError(str(exc)) from exc


def test_mail_connection(settings: dict[str, Any]) -> dict[str, Any]:
    if is_dummy_mode(settings):
        return {
            'status': 'ok',
            'mode': 'dummy',
            'imap': {'status': 'ok', 'message': 'Dummy mode uses the built-in test mailbox'},
            'smtp': {'status': 'ok', 'message': 'Dummy mode uses the in-memory outbox'},
            'details': {'messageCount': len(_dummy_mailbox)},
        }
    # Live IMAP/SMTP check
    host = settings.get('imapHost')
    port = int(settings.get('imapPort') or 993)
    use_ssl = bool(settings.get('imapUseSSL'))
    imap_ok = False
    imap_message = ''
    try:
        imap = imaplib.IMAP4_SSL(host, port) if use_ssl else imaplib.IMAP4(host, port)
        username = settings.get('username')
        password = settings.get('imapPassword')
        if username:
            try:
                imap.login(username, password or '')
            except Exception as exc:
                imap_message = str(exc)
            else:
                imap_ok = True
        else:
            imap_ok = True
        try:
            imap.logout()
        except Exception:
            pass
    except Exception as exc:
        imap_message = str(exc)
    smtp_ok = False
    smtp_message = ''
    try:
        smtp_host = settings.get('smtpHost')
        smtp_port = int(settings.get('smtpPort') or 25)
        use_ssl = bool(settings.get('smtpUseSSL'))
        if use_ssl:
            smtp = smtplib.SMTP_SSL(smtp_host, smtp_port)
        else:
            smtp = smtplib.SMTP(smtp_host, smtp_port)
        try:
            smtp.ehlo()
            smtp_ok = True
        finally:
            try:
                smtp.quit()
            except Exception:
                pass
    except Exception as exc:
        smtp_message = str(exc)
    return {
        'status': 'ok' if (imap_ok and smtp_ok) else 'warning',
        'mode': 'imap',
        'imap': {'status': 'ok' if imap_ok else 'error', 'message': imap_message or 'IMAP OK'},
        'smtp': {'status': 'ok' if smtp_ok else 'error', 'message': smtp_message or 'SMTP OK'},
        'details': {'messageCount': 0},
    }
