from __future__ import annotations
import sys
import tempfile
import unittest
import unittest.mock as mock
from pathlib import Path
from typing import Any

import imaplib
import smtplib

from fastapi.testclient import TestClient

# Module-level placeholders for dynamically-imported backend modules
mail_service: Any = None
db: Any = None
backend_app: Any = None
schemas: Any = None


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
        self.temp_dir.cleanup()

    def _client(self) -> TestClient:
        return TestClient(backend_app.app)

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
            mock_conn.select.side_effect = imaplib.IMAP4.error('Mailbox does not exist')

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

            # First call succeeds, second fails
            mock_conn.uid.side_effect = [
                ('OK', []),  # First message succeeds
                imaplib.IMAP4.error('Connection lost'),  # Second message fails
                ('OK', []),  # Third message succeeds
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


if __name__ == '__main__':
    unittest.main()
