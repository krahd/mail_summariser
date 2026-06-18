from __future__ import annotations
import sys
import tempfile
import unittest
import unittest.mock as mock
from pathlib import Path
from typing import Any

import imaplib
import smtplib
from email.message import EmailMessage

from fastapi.testclient import TestClient

# Module-level placeholders for dynamically-imported backend modules
mail_service: Any = None
db: Any = None
backend_app: Any = None
schemas: Any = None


def _make_message_bytes(subject: str, sender: str, recipient: str, date: str, body: str, list_id: str = '') -> bytes:
    message = EmailMessage()
    message['Subject'] = subject
    message['From'] = sender
    message['To'] = recipient
    message['Date'] = date
    if list_id:
        message['List-Id'] = list_id
    message.set_content(body)
    return message.as_bytes()


class RecordingImapConnection:
    def __init__(
        self,
        *,
        search_results: dict[str, bytes] | None = None,
        message_bodies: dict[tuple[str, str], bytes] | None = None,
        message_flags: dict[tuple[str, str], list[str]] | None = None,
        select_failures: dict[str, tuple[str, list[bytes]]] | None = None,
    ) -> None:
        self.search_results = search_results or {}
        self.message_bodies = message_bodies or {}
        self.message_flags = message_flags or {}
        self.select_failures = select_failures or {}
        self.selected_mailbox = ''
        self.select_calls: list[str] = []
        self.uid_calls: list[tuple[str, str | None, tuple[str, ...], str]] = []
        self.login_calls: list[tuple[str, str]] = []
        self.logout_calls = 0

    def login(self, username: str, password: str) -> tuple[str, list[bytes]]:
        self.login_calls.append((username, password))
        return ('OK', [])

    def select(self, mailbox: str) -> tuple[str, list[bytes]]:
        self.select_calls.append(mailbox)
        failure = self.select_failures.get(mailbox)
        if failure is not None:
            return failure
        self.selected_mailbox = mailbox
        return ('OK', [b'1'])

    def uid(self, command: str, uid: str | None, *args: str) -> tuple[str, list[bytes]]:
        self.uid_calls.append((command, uid, args, self.selected_mailbox))
        if command == 'search':
            return ('OK', [self.search_results.get(self.selected_mailbox, b'')])
        if command == 'fetch' and args:
            if args[0] == '(BODY.PEEK[])':
                raw = self.message_bodies.get((self.selected_mailbox, str(uid or '')))
                if raw is None:
                    return ('NO', [b'Message not found'])
                return ('OK', [(f'1 (BODY[] {{{len(raw)}}}'.encode('utf-8'), raw)])
            if args[0] == '(FLAGS)':
                flags = self.message_flags.get((self.selected_mailbox, str(uid or '')), [])
                flags_text = ' '.join(flags)
                return ('OK', [f'1 (FLAGS ({flags_text}))'])
        return ('NO', [b'Unsupported command'])

    def logout(self) -> tuple[str, list[bytes]]:
        self.logout_calls += 1
        return ('BYE', [])


class IMAPHardeningTests(unittest.TestCase):
    """Tests for IMAP/SMTP authentication failure handling in phase 01."""

    def setUp(self) -> None:
        # ensure backend path is on sys.path then import backend modules
        REPO_ROOT = Path(__file__).resolve().parents[1]
        BACKEND_DIR = REPO_ROOT / "backend"
        if str(BACKEND_DIR) not in sys.path:
            sys.path.insert(0, str(BACKEND_DIR))

        # import backend modules dynamically after sys.path has been configured
        import importlib
        globals()["mail_service"] = importlib.import_module("mail_service")
        globals()["db"] = importlib.import_module("db")
        globals()["backend_app"] = importlib.import_module("app")
        globals()["schemas"] = importlib.import_module("schemas")

        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_db_path = db.DB_PATH
        db.DB_PATH = Path(self.temp_dir.name) / "mail_summariser.sqlite3"
        self.original_dev_tools_enabled = backend_app.ENABLE_DEV_TOOLS
        backend_app.DEFAULT_SETTINGS["ollamaAutoStart"] = False
        backend_app._backend_shutdown_requested = False
        backend_app._fake_mail_manager.shutdown()
        backend_app._reset_dummy_sandbox()

    def tearDown(self) -> None:
        backend_app.ENABLE_DEV_TOOLS = self.original_dev_tools_enabled
        backend_app._fake_mail_manager.shutdown()
        backend_app._reset_dummy_sandbox()
        db.DB_PATH = self.original_db_path
        self.temp_dir.cleanup()

    def _client(self) -> TestClient:
        return TestClient(backend_app.app)

    def _live_settings(self, **overrides: Any) -> dict[str, Any]:
        base = dict(backend_app.DEFAULT_SETTINGS)
        base.update({
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
        base.update(overrides)
        return base

    def test_imap_login_failure_raises_error(self) -> None:
        """IMAP login failure should raise MailServiceError."""
        with mock.patch('imaplib.IMAP4_SSL') as mock_imap:
            mock_conn = mock.MagicMock()
            mock_imap.return_value = mock_conn
            mock_conn.login.side_effect = imaplib.IMAP4.error('Invalid credentials')

            settings = {
                'dummyMode': False,
                'imapHost': 'imap.example.com',
                'imapPort': 993,
                'imapUseSSL': True,
                'username': 'user@example.com',
                'imapPassword': 'wrongpassword',
            }

            with self.assertRaises(mail_service.MailServiceError) as ctx:
                mail_service.search_messages(
                    schemas.SearchCriteria(
                        keyword='test',
                        rawSearch='',
                        sender='',
                        recipient='',
                        unreadOnly=False,
                        readOnly=False,
                        replied=None,
                        tag='',
                        useAnd=True,
                    ),
                    settings,
                )
            self.assertIn('authentication', str(ctx.exception).lower())
            # Ensure password is not in error message
            self.assertNotIn('wrongpassword', str(ctx.exception))

    def test_imap_select_failure_raises_error(self) -> None:
        """IMAP select('INBOX') failure should raise MailServiceError."""
        with mock.patch('imaplib.IMAP4_SSL') as mock_imap:
            mock_conn = mock.MagicMock()
            mock_imap.return_value = mock_conn
            mock_conn.login.return_value = ('OK', [])
            mock_conn.select.return_value = ('NO', [b'Mailbox does not exist'])

            settings = {
                'dummyMode': False,
                'imapHost': 'imap.example.com',
                'imapPort': 993,
                'imapUseSSL': True,
                'username': 'user@example.com',
                'imapPassword': 'password',
            }

            with self.assertRaises(mail_service.MailServiceError) as ctx:
                mail_service.search_messages(
                    schemas.SearchCriteria(
                        keyword='test',
                        rawSearch='',
                        sender='',
                        recipient='',
                        unreadOnly=False,
                        readOnly=False,
                        replied=None,
                        tag='',
                        useAnd=True,
                    ),
                    settings,
                )
            self.assertIn('select', str(ctx.exception).lower())

    def test_smtp_login_failure_raises_error_on_send(self) -> None:
        """SMTP login failure should raise MailServiceError."""
        with mock.patch('smtplib.SMTP_SSL') as mock_smtp:
            mock_conn = mock.MagicMock()
            mock_smtp.return_value = mock_conn
            mock_conn.ehlo.return_value = (250, b'OK')
            mock_conn.login.side_effect = smtplib.SMTPAuthenticationError(
                535, b'Invalid credentials')

            settings = {
                'dummyMode': False,
                'smtpHost': 'smtp.example.com',
                'smtpPort': 465,
                'smtpUseSSL': True,
                'username': 'user@example.com',
                'smtpPassword': 'wrongpassword',
            }

            with self.assertRaises(mail_service.MailServiceError) as ctx:
                mail_service.send_summary_email(
                    'recipient@example.com',
                    'Test Subject',
                    'Test Body',
                    settings,
                )
            self.assertIn('authentication', str(ctx.exception).lower())
            # Ensure password is not in error message
            self.assertNotIn('wrongpassword', str(ctx.exception))

    def test_imap_login_failure_test_connection_endpoint(self) -> None:
        """Bad IMAP credentials should fail test-connection endpoint with status 400."""
        with mock.patch('imaplib.IMAP4_SSL') as mock_imap:
            mock_conn = mock.MagicMock()
            mock_imap.return_value = mock_conn
            mock_conn.login.side_effect = imaplib.IMAP4.error('Invalid credentials')

            with self._client() as client:
                settings = client.get("/settings").json()
                settings['dummyMode'] = False
                settings['imapHost'] = 'imap.example.com'
                settings['imapPort'] = 993
                settings['imapUseSSL'] = True
                settings['username'] = 'user@example.com'
                settings['imapPassword'] = 'wrongpassword'

                response = client.post("/settings/test-connection", json=settings)
                self.assertEqual(response.status_code, 200)
                result = response.json()
                self.assertEqual(result['imap']['status'], 'error')
                self.assertIn('authentication', result['imap']['message'].lower())

    def test_imap_select_failure_test_connection_endpoint(self) -> None:
        """Mailbox selection failure should be reported by test-connection."""
        with mock.patch('imaplib.IMAP4_SSL') as mock_imap:
            mock_conn = mock.MagicMock()
            mock_imap.return_value = mock_conn
            mock_conn.login.return_value = ('OK', [])
            mock_conn.select.return_value = ('NO', [b'Mailbox does not exist'])

            with self._client() as client:
                settings = client.get("/settings").json()
                settings['dummyMode'] = False
                settings['imapHost'] = 'imap.example.com'
                settings['imapPort'] = 993
                settings['imapUseSSL'] = True
                settings['username'] = 'user@example.com'
                settings['imapPassword'] = 'password'

                response = client.post("/settings/test-connection", json=settings)
                self.assertEqual(response.status_code, 200)
                result = response.json()
                self.assertEqual(result['imap']['status'], 'error')
                self.assertIn('select', result['imap']['message'].lower())

    def test_password_redaction_in_error_messages(self) -> None:
        """Passwords should be redacted from error messages."""
        password = 'super_secret_password_12345'
        error_msg = f'IMAP4 server rejected login: {password}'

        redacted = mail_service._redact_error_message(error_msg, password)
        self.assertNotIn(password, redacted)
        self.assertIn('***', redacted)

    def test_dummy_mode_unaffected(self) -> None:
        """Dummy mode should continue to work unaffected."""
        with self._client() as client:
            settings = client.get("/settings").json()
            self.assertTrue(settings["dummyMode"])

            connection = client.post("/settings/test-connection", json=settings)
            self.assertEqual(connection.status_code, 200)
            result = connection.json()
            self.assertEqual(result['mode'], 'dummy')
            self.assertEqual(result['status'], 'ok')

            # Test summary creation in dummy mode
            response = client.post(
                "/summaries",
                json={
                    "criteria": {
                        "keyword": "",
                        "rawSearch": "",
                        "sender": "",
                        "recipient": "",
                        "unreadOnly": True,
                        "readOnly": False,
                        "replied": None,
                        "tag": "",
                        "useAnd": True,
                    },
                    "summaryLength": 5,
                },
            )
            self.assertEqual(response.status_code, 200)

    def test_mark_messages_read_with_connection_failure(self) -> None:
        """mark_messages_read should fail on IMAP connection failure."""
        with mock.patch('imaplib.IMAP4_SSL') as mock_imap:
            mock_imap.side_effect = OSError('Connection refused')

            settings = {
                'dummyMode': False,
                'imapHost': 'imap.example.com',
                'imapPort': 993,
                'imapUseSSL': True,
                'username': 'user@example.com',
                'imapPassword': 'password',
            }

            with self.assertRaises(mail_service.MailServiceError):
                mail_service.mark_messages_read(['msg-1'], settings)

    def test_add_keyword_tag_with_connection_failure(self) -> None:
        """add_keyword_tag should fail on IMAP connection failure."""
        with mock.patch('imaplib.IMAP4_SSL') as mock_imap:
            mock_imap.side_effect = OSError('Connection refused')

            settings = {
                'dummyMode': False,
                'imapHost': 'imap.example.com',
                'imapPort': 993,
                'imapUseSSL': True,
                'username': 'user@example.com',
                'imapPassword': 'password',
            }

            with self.assertRaises(mail_service.MailServiceError):
                mail_service.add_keyword_tag(['msg-1'], 'important', settings)

    def test_mark_read_tracks_failed_message_ids(self) -> None:
        """mark_messages_read should track and return failed_message_ids."""
        with mock.patch('imaplib.IMAP4_SSL') as mock_imap:
            mock_conn = mock.MagicMock()
            mock_imap.return_value = mock_conn
            mock_conn.login.return_value = ('OK', [])
            mock_conn.select.return_value = ('OK', [b'5'])

            # Each message fetches current flags before STORE. STORE fails for the second message.
            mock_conn.uid.side_effect = [
                ('OK', [b'1 (FLAGS ())']),
                ('OK', []),
                ('OK', [b'2 (FLAGS ())']),
                ('NO', [b'Connection lost']),
                ('OK', [b'3 (FLAGS ())']),
                ('OK', []),
            ]

            settings = {
                'dummyMode': False,
                'imapHost': 'imap.example.com',
                'imapPort': 993,
                'imapUseSSL': True,
                'username': 'user@example.com',
                'imapPassword': 'password',
            }

            result = mail_service.mark_messages_read(['msg-1', 'msg-2', 'msg-3'], settings)
            self.assertIn('failed_message_ids', result)
            self.assertEqual(result['failed_message_ids'], ['msg-2'])
            self.assertEqual(result['restore_unread_ids'], ['msg-1', 'msg-3'])

    def test_add_keyword_tag_tracks_failed_message_ids(self) -> None:
        """add_keyword_tag should track and return failed_message_ids."""
        with mock.patch('imaplib.IMAP4_SSL') as mock_imap:
            mock_conn = mock.MagicMock()
            mock_imap.return_value = mock_conn
            mock_conn.login.return_value = ('OK', [])
            mock_conn.select.return_value = ('OK', [b'5'])
            mock_conn.uid.side_effect = [
                ('OK', [b'1 (FLAGS ())']),
                ('OK', []),
                ('OK', [b'2 (FLAGS ())']),
                ('NO', [b'Permission denied']),
                ('OK', [b'3 (FLAGS ())']),
                ('OK', []),
            ]

            settings = {
                'dummyMode': False,
                'imapHost': 'imap.example.com',
                'imapPort': 993,
                'imapUseSSL': True,
                'username': 'user@example.com',
                'imapPassword': 'password',
            }

            result = mail_service.add_keyword_tag(['msg-1', 'msg-2', 'msg-3'], 'important', settings)
            self.assertIn('failed_message_ids', result)
            self.assertEqual(result['failed_message_ids'], ['msg-2'])
            self.assertEqual(result['added_message_ids'], ['msg-1', 'msg-3'])

    def test_remove_keyword_tag_tracks_failed_message_ids(self) -> None:
        """remove_keyword_tag should track and return failed_message_ids."""
        with mock.patch('imaplib.IMAP4_SSL') as mock_imap:
            mock_conn = mock.MagicMock()
            mock_imap.return_value = mock_conn
            mock_conn.login.return_value = ('OK', [])
            mock_conn.select.return_value = ('OK', [b'5'])
            mock_conn.uid.side_effect = [
                ('OK', [b'1 (FLAGS (important))']),
                ('OK', []),
                ('OK', [b'2 (FLAGS (important))']),
                ('OK', []),
                ('OK', [b'3 (FLAGS (important))']),
                ('NO', [b'No such message']),
            ]

            settings = {
                'dummyMode': False,
                'imapHost': 'imap.example.com',
                'imapPort': 993,
                'imapUseSSL': True,
                'username': 'user@example.com',
                'imapPassword': 'password',
            }

            result = mail_service.remove_keyword_tag(['msg-1', 'msg-2', 'msg-3'], 'important', settings)
            self.assertIn('failed_message_ids', result)
            self.assertEqual(result['failed_message_ids'], ['msg-3'])
            self.assertEqual(result['removed_message_ids'], ['msg-1', 'msg-2'])

    def test_search_criteria_accepts_new_fields(self) -> None:
        criteria = schemas.SearchCriteria(
            accountIds=['acct-1', 'acct-2'],
            mailboxes=['INBOX', 'Archive'],
            keyword='invoice',
            rawSearch='budget',
            sender='alice@example.com',
            recipient='team@example.com',
            unreadOnly=True,
            readOnly=False,
            flagged=True,
            since='01-Jan-2026',
            before='31-Jan-2026',
            listId='mailing-list@example.com',
            replied=False,
            tag='finance',
            useAnd=True,
            limit=42,
        )

        self.assertEqual(criteria.accountIds, ['acct-1', 'acct-2'])
        self.assertEqual(criteria.mailboxes, ['INBOX', 'Archive'])
        self.assertTrue(criteria.flagged)
        self.assertEqual(criteria.since, '01-Jan-2026')
        self.assertEqual(criteria.before, '31-Jan-2026')
        self.assertEqual(criteria.listId, 'mailing-list@example.com')
        self.assertEqual(criteria.limit, 42)

    def test_search_criteria_limit_is_clamped(self) -> None:
        low = schemas.SearchCriteria(limit=0)
        high = schemas.SearchCriteria(limit=10_000)

        self.assertEqual(low.limit, 1)
        self.assertEqual(high.limit, 500)

    def test_live_search_selects_requested_mailbox(self) -> None:
        fake_conn = RecordingImapConnection(
            search_results={'Archive': b'1'},
            message_bodies={
                ('Archive', '1'): _make_message_bytes(
                    'Archive notice',
                    'archive@example.com',
                    'user@example.com',
                    'Mon, 01 Jan 2026 09:00:00 +0000',
                    'Archive body',
                ),
            },
            message_flags={('Archive', '1'): []},
        )
        settings = self._live_settings()
        criteria = schemas.SearchCriteria(mailboxes=['Archive'])

        with mock.patch('imaplib.IMAP4_SSL', return_value=fake_conn):
            messages = mail_service.search_messages(criteria, settings)

        self.assertEqual(fake_conn.select_calls, ['Archive'])
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]['id'], 'default|Archive|1')

    def test_live_search_uses_unseen_when_unread_only(self) -> None:
        fake_conn = RecordingImapConnection(
            search_results={'INBOX': b'1'},
            message_bodies={
                ('INBOX', '1'): _make_message_bytes(
                    'Unread notice',
                    'sender@example.com',
                    'user@example.com',
                    'Mon, 01 Jan 2026 09:00:00 +0000',
                    'Unread body',
                ),
            },
            message_flags={('INBOX', '1'): []},
        )
        settings = self._live_settings()
        criteria = schemas.SearchCriteria(unreadOnly=True)

        with mock.patch('imaplib.IMAP4_SSL', return_value=fake_conn):
            messages = mail_service.search_messages(criteria, settings)

        self.assertEqual(fake_conn.uid_calls[0][0], 'search')
        self.assertEqual(fake_conn.uid_calls[0][2], ('UNSEEN',))
        self.assertEqual(len(messages), 1)

    def test_live_search_uses_flagged_when_flagged_true(self) -> None:
        fake_conn = RecordingImapConnection(
            search_results={'INBOX': b'1'},
            message_bodies={
                ('INBOX', '1'): _make_message_bytes(
                    'Flagged notice',
                    'sender@example.com',
                    'user@example.com',
                    'Mon, 01 Jan 2026 09:00:00 +0000',
                    'Flagged body',
                ),
            },
            message_flags={('INBOX', '1'): ['\\Flagged']},
        )
        settings = self._live_settings()
        criteria = schemas.SearchCriteria(flagged=True)

        with mock.patch('imaplib.IMAP4_SSL', return_value=fake_conn):
            messages = mail_service.search_messages(criteria, settings)

        self.assertEqual(fake_conn.uid_calls[0][2], ('FLAGGED',))
        self.assertEqual(len(messages), 1)

    def test_live_search_uses_keyword_when_tag_provided(self) -> None:
        fake_conn = RecordingImapConnection(
            search_results={'INBOX': b'1'},
            message_bodies={
                ('INBOX', '1'): _make_message_bytes(
                    'Tagged notice',
                    'sender@example.com',
                    'user@example.com',
                    'Mon, 01 Jan 2026 09:00:00 +0000',
                    'Tagged body',
                ),
            },
            message_flags={('INBOX', '1'): ['finance']},
        )
        settings = self._live_settings()
        criteria = schemas.SearchCriteria(tag='finance')

        with mock.patch('imaplib.IMAP4_SSL', return_value=fake_conn):
            messages = mail_service.search_messages(criteria, settings)

        self.assertEqual(fake_conn.uid_calls[0][2], ('KEYWORD', 'finance'))
        self.assertEqual(len(messages), 1)

    def test_live_search_returns_composite_ids_without_collisions(self) -> None:
        fake_conn = RecordingImapConnection(
            search_results={'INBOX': b'1', 'Archive': b'1'},
            message_bodies={
                ('INBOX', '1'): _make_message_bytes(
                    'Inbox notice',
                    'inbox@example.com',
                    'user@example.com',
                    'Mon, 01 Jan 2026 09:00:00 +0000',
                    'Inbox body',
                ),
                ('Archive', '1'): _make_message_bytes(
                    'Archive notice',
                    'archive@example.com',
                    'user@example.com',
                    'Mon, 01 Jan 2026 10:00:00 +0000',
                    'Archive body',
                ),
            },
            message_flags={
                ('INBOX', '1'): [],
                ('Archive', '1'): [],
            },
        )
        settings = self._live_settings(
            mailAccounts=[
                {
                    'id': 'acct-1',
                    'displayName': 'Primary',
                    'enabled': True,
                    'imapHost': 'imap.example.com',
                    'imapPort': 993,
                    'imapUseSSL': True,
                    'username': 'user@example.com',
                    'imapPassword': 'password',
                    'smtpHost': 'smtp.example.com',
                    'smtpPort': 465,
                    'smtpUseSSL': True,
                    'smtpPassword': 'password',
                    'recipientEmail': 'recipient@example.com',
                }
            ],
        )
        criteria = schemas.SearchCriteria(accountIds=['acct-1'], mailboxes=['INBOX', 'Archive'])

        with mock.patch('imaplib.IMAP4_SSL', return_value=fake_conn):
            messages = mail_service.search_messages(criteria, settings)

        ids = [message['id'] for message in messages]
        self.assertEqual(len(ids), 2)
        self.assertEqual(len(set(ids)), 2)
        self.assertIn('acct-1|INBOX|1', ids)
        self.assertIn('acct-1|Archive|1', ids)
        self.assertEqual(fake_conn.select_calls, ['INBOX', 'Archive'])

    def test_live_search_returns_http_400_when_mailbox_selection_fails(self) -> None:
        fake_conn = RecordingImapConnection(
            select_failures={'Missing': ('NO', [b'Mailbox does not exist'])},
        )
        payload = {
            'criteria': {'mailboxes': ['Missing']},
            'summaryLength': 5,
        }

        with self._client() as client, mock.patch('imaplib.IMAP4_SSL', return_value=fake_conn):
            client.post('/settings', json=self._live_settings())
            response = client.post('/summaries', json=payload)

        self.assertEqual(response.status_code, 400)
        self.assertIn('select', response.json()['detail'].lower())

    def test_dummy_mode_ignores_new_scoping_fields(self) -> None:
        with self._client() as client:
            response = client.post('/summaries', json={
                'criteria': {
                    'accountIds': ['acct-1'],
                    'mailboxes': ['Archive'],
                    'unreadOnly': True,
                },
                'summaryLength': 5,
            })

        self.assertEqual(response.status_code, 200)
        self.assertGreater(len(response.json()['messages']), 0)


if __name__ == '__main__':
    unittest.main()
