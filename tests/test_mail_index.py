from __future__ import annotations

import sqlite3
from email.message import EmailMessage
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from backend import app as backend_app
from backend import db as backend_db
from backend.fake_mail_server import FakeMailEnvironment


@pytest.fixture(autouse=True)
def isolated_runtime(tmp_path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(backend_db, 'DB_PATH', tmp_path / 'mail_summariser.sqlite3')
    monkeypatch.setattr(backend_app, 'ENABLE_DEV_TOOLS', False)
    monkeypatch.setitem(backend_app.DEFAULT_SETTINGS, 'ollamaAutoStart', False)
    backend_app._fake_mail_manager.shutdown()
    backend_app._reset_dummy_sandbox()
    backend_db.init_db()
    yield
    backend_app._fake_mail_manager.shutdown()
    backend_app._reset_dummy_sandbox()


def _table_count(table_name: str) -> int:
    with sqlite3.connect(backend_db.DB_PATH) as conn:
        row = conn.execute(f'SELECT COUNT(*) FROM {table_name}').fetchone()
    return int(row[0]) if row is not None else 0


def _make_message_bytes(
    subject: str,
    sender: str,
    recipient: str,
    date: str,
    body: str,
    message_id: str,
    *,
    list_id: str = '',
    list_unsubscribe: str = '',
) -> bytes:
    message = EmailMessage()
    message['Subject'] = subject
    message['From'] = sender
    message['To'] = recipient
    message['Date'] = date
    message['Message-ID'] = message_id
    if list_id:
        message['List-Id'] = list_id
    if list_unsubscribe:
        message['List-Unsubscribe'] = list_unsubscribe
    message.set_content(body)
    return message.as_bytes()


class SyncRecordingImapConnection:
    def __init__(
        self,
        *,
        search_results: dict[str, bytes] | None = None,
        headers: dict[tuple[str, str], bytes] | None = None,
        previews: dict[tuple[str, str], bytes] | None = None,
        flags: dict[tuple[str, str], list[str]] | None = None,
        mailbox_list: list[bytes] | None = None,
    ) -> None:
        self.search_results = search_results or {}
        self.headers = headers or {}
        self.previews = previews or {}
        self.flags = flags or {}
        self.mailbox_list = mailbox_list or [b'(\\HasNoChildren) "/" "INBOX"']
        self.selected_mailbox = ''
        self.login_calls: list[tuple[str, str]] = []
        self.select_calls: list[str] = []
        self.uid_calls: list[tuple[str, str | None, tuple[str, ...], str]] = []
        self.logout_calls = 0

    def login(self, username: str, password: str) -> tuple[str, list[bytes]]:
        self.login_calls.append((username, password))
        return ('OK', [])

    def list(self, reference: str = '', mailbox: str = '*') -> tuple[str, list[bytes]]:
        return ('OK', self.mailbox_list)

    def select(self, mailbox: str) -> tuple[str, list[bytes]]:
        self.select_calls.append(mailbox)
        self.selected_mailbox = mailbox
        return ('OK', [b'1'])

    def uid(self, command: str, uid: str | None, *args: str) -> tuple[str, list[bytes]]:
        self.uid_calls.append((command, uid, args, self.selected_mailbox))
        if command == 'search':
            return ('OK', [self.search_results.get(self.selected_mailbox, b'')])
        if command == 'fetch' and args:
            item = args[0]
            key = (self.selected_mailbox, str(uid or ''))
            if item == '(BODY.PEEK[HEADER])':
                raw = self.headers.get(key)
                if raw is None:
                    return ('NO', [b'header missing'])
                return ('OK', [(f'1 (BODY[HEADER] {{{len(raw)}}}'.encode('utf-8'), raw)])
            if item == '(BODY.PEEK[TEXT]<0.1024>)':
                raw = self.previews.get(key)
                if raw is None:
                    return ('NO', [b'preview missing'])
                return ('OK', [(f'1 (BODY[TEXT] {{{len(raw)}}}'.encode('utf-8'), raw)])
            if item == '(FLAGS)':
                flags = self.flags.get(key, [])
                return ('OK', [f'1 (FLAGS ({" ".join(flags)}))'.encode('utf-8')])
        return ('NO', [b'unsupported'])

    def logout(self) -> tuple[str, list[bytes]]:
        self.logout_calls += 1
        return ('BYE', [])


def test_dummy_mode_sync_indexes_sample_mailbox() -> None:
    with TestClient(backend_app.app) as client:
        response = client.post('/mail/index/sync', json={})
        assert response.status_code == 200

        payload = response.json()
        assert payload['accountId'] == 'sample'
        assert payload['mailbox'] == 'INBOX'
        assert payload['indexed'] == 2
        assert payload['errors'] == 0

        messages = client.get('/mail/index/messages', params={'accountId': 'sample', 'mailbox': 'INBOX'}).json()
        assert len(messages) == 2

        assert _table_count('sync_state') == 1



def test_sync_from_fake_environment_populates_filters() -> None:
    with FakeMailEnvironment() as env:
        env.messages['101']['flags'].add('\\Seen')
        env.messages['102']['flags'].add('\\Flagged')

        payload = dict(backend_app.DEFAULT_SETTINGS)
        payload.update({
            'dummyMode': False,
            'imapHost': env.host,
            'imapPort': env.imap_server.port,
            'imapUseSSL': False,
            'imapPassword': env.password,
            'smtpHost': env.host,
            'smtpPort': env.smtp_server.port,
            'smtpUseSSL': False,
            'smtpPassword': env.password,
            'username': env.username,
            'recipientEmail': env.recipient_email,
        })

        with TestClient(backend_app.app) as client:
            save = client.post('/settings', json=payload)
            assert save.status_code == 200

            response = client.post('/mail/index/sync', json={'accountId': 'default', 'mailbox': 'INBOX', 'limit': 10})
            assert response.status_code == 200
            result = response.json()
            assert result == {
                'accountId': 'default',
                'mailbox': 'INBOX',
                'scanned': 2,
                'indexed': 2,
                'errors': 0,
            }

            unread = client.get('/mail/index/messages', params={
                'accountId': 'default',
                'mailbox': 'INBOX',
                'unread': 'true',
            }).json()
            flagged = client.get('/mail/index/messages', params={
                'accountId': 'default',
                'mailbox': 'INBOX',
                'flagged': 'true',
            }).json()
            read = client.get('/mail/index/messages', params={
                'accountId': 'default',
                'mailbox': 'INBOX',
                'unread': 'false',
            }).json()

            assert _table_count('sync_state') == 1

    assert {message['uid'] for message in unread} == {'102'}
    assert {message['uid'] for message in flagged} == {'102'}
    assert {message['uid'] for message in read} == {'101'}


def test_sync_clamps_limit_and_extracts_list_id() -> None:
    headers: dict[tuple[str, str], bytes] = {}
    previews: dict[tuple[str, str], bytes] = {}
    flags: dict[tuple[str, str], list[str]] = {}
    uids = [str(uid) for uid in range(1, 502)]
    search_bytes = ' '.join(uids).encode('utf-8')

    for uid in uids:
        list_id = '<list.example.com>' if uid == '501' else ''
        list_unsubscribe = '<mailto:unsubscribe@example.com>' if uid == '501' else ''
        headers[('INBOX', uid)] = _make_message_bytes(
            f'Subject {uid}',
            'sender@example.com',
            'user@example.com',
            'Mon, 01 Jan 2026 09:00:00 +0000',
            f'Body {uid}',
            f'<msg-{uid}@example.com>',
            list_id=list_id,
            list_unsubscribe=list_unsubscribe,
        )
        previews[('INBOX', uid)] = f'Body {uid}'.encode('utf-8')
        flags[('INBOX', uid)] = []

    fake_conn = SyncRecordingImapConnection(
        search_results={'INBOX': search_bytes},
        headers=headers,
        previews=previews,
        flags=flags,
    )

    payload = dict(backend_app.DEFAULT_SETTINGS)
    payload.update({
        'dummyMode': False,
        'imapHost': 'imap.example.com',
        'imapPort': 993,
        'imapUseSSL': True,
        'imapPassword': 'password',
        'smtpHost': 'smtp.example.com',
        'smtpPort': 465,
        'smtpUseSSL': True,
        'smtpPassword': 'password',
        'username': 'user@example.com',
        'recipientEmail': 'recipient@example.com',
    })

    with mock.patch('imaplib.IMAP4_SSL', return_value=fake_conn), TestClient(backend_app.app) as client:
        save = client.post('/settings', json=payload)
        assert save.status_code == 200

        response = client.post('/mail/index/sync', json={'accountId': 'default', 'mailbox': 'INBOX', 'limit': 1000})
        assert response.status_code == 200
        result = response.json()
        assert result['scanned'] == 500
        assert result['indexed'] == 500
        assert result['errors'] == 0

        messages = client.get('/mail/index/messages', params={'listId': 'list.example.com', 'limit': 10}).json()
        assert len(messages) == 1
        assert messages[0]['uid'] == '501'

        detail = client.get(f"/mail/index/messages/{messages[0]['id']}").json()
        assert detail['bodyText'] == ''
        assert 'list.example.com' in detail['listId']


def test_upsert_index_message_updates_existing_row_and_sync_state() -> None:
    backend_db.upsert_index_account({
        'id': 'acct-1',
        'displayName': 'Account One',
        'username': 'user@example.com',
        'imapHost': 'imap.example.com',
        'enabled': True,
    })
    backend_db.upsert_index_mailbox('acct-1', {
        'path': 'INBOX',
        'delimiter': '/',
        'selectable': True,
        'flags': ['\\HasNoChildren'],
    })
    backend_db.upsert_index_message({
        'id': 'acct-1|INBOX|101',
        'accountId': 'acct-1',
        'mailboxPath': 'INBOX',
        'uid': '101',
        'messageIdHeader': '<msg-101@example.com>',
        'subject': 'Original subject',
        'sender': 'sender@example.com',
        'recipients': ['you@example.com'],
        'date': '2026-05-01T12:00:00Z',
        'flags': ['\\Seen'],
        'keywords': ['finance'],
        'listId': '<list.example.com>',
        'bodyPreview': '',
        'bodyCached': True,
        'bodyText': 'Full body',
        'lastSeenAt': '2026-05-01T12:00:00',
    })
    backend_db.upsert_index_message({
        'id': 'acct-1|INBOX|101',
        'accountId': 'acct-1',
        'mailboxPath': 'INBOX',
        'uid': '101',
        'messageIdHeader': '<msg-101@example.com>',
        'subject': 'Updated subject',
        'sender': 'sender@example.com',
        'recipients': ['you@example.com'],
        'date': '2026-05-01T12:00:00Z',
        'flags': ['\\Seen'],
        'keywords': ['finance'],
        'listId': '<list.example.com>',
        'bodyPreview': '',
        'bodyCached': False,
        'bodyText': '',
        'lastSeenAt': '2026-05-01T12:05:00',
    })
    backend_db.update_sync_state('acct-1', 'INBOX', uidvalidity='123', uidnext='456',
                                 last_sync_at='2026-05-01T12:05:00')

    with sqlite3.connect(backend_db.DB_PATH) as conn:
        assert int(conn.execute('SELECT COUNT(*) FROM mail_accounts_index').fetchone()[0]) == 1
        assert int(conn.execute('SELECT COUNT(*) FROM mailboxes_index').fetchone()[0]) == 1
        assert int(conn.execute('SELECT COUNT(*) FROM messages_index').fetchone()[0]) == 1
        sync_row = conn.execute(
            'SELECT uidvalidity, uidnext FROM sync_state WHERE account_id = ? AND mailbox_path = ?',
            ('acct-1', 'INBOX'),
        ).fetchone()

    stored = backend_db.get_index_message('acct-1|INBOX|101')
    assert stored is not None
    assert stored['subject'] == 'Updated subject'
    assert stored['bodyText'] == 'Full body'
    assert stored['bodyCached'] is True
    assert stored['recipients'] == ['you@example.com']
    assert stored['listId'] == '<list.example.com>'
    assert sync_row == ('123', '456')
    assert backend_db.list_index_messages({'accountId': 'acct-1'})[0]['bodyCached'] is True
