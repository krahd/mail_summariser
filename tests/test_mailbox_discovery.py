"""Tests for phase 03 — IMAP mailbox discovery.

Covers:
- Successful mailbox discovery via fake mail environment.
- \\Noselect mailbox is marked selectable=False.
- Unknown account returns 404.
- Bad credentials return a redacted error.
- dummyMode returns deterministic sample mailbox list.
- Existing settings and summary routes are unaffected.
- _parse_list_response handles various LIST response formats.
"""

from __future__ import annotations

import imaplib
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from backend.app import app
from backend import db as backend_db
from backend.fake_mail_server import FakeMailEnvironment
from backend.mail_service import (
    MailServiceError,
    _parse_list_response,
    discover_mailboxes_for_account,
)


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(backend_db, 'DB_PATH', tmp_path / 'test.sqlite3')


# ---------------------------------------------------------------------------
# _parse_list_response unit tests
# ---------------------------------------------------------------------------

def test_parse_list_response_basic():
    flags, delim, path = _parse_list_response(b'(\\HasNoChildren) "/" "INBOX"')
    assert path == 'INBOX'
    assert delim == '/'
    assert '\\HasNoChildren' in flags


def test_parse_list_response_noselect():
    flags, delim, path = _parse_list_response(b'(\\Noselect \\HasChildren) "/" "[Gmail]"')
    assert path == '[Gmail]'
    assert any(f.lower() == '\\noselect' for f in flags)


def test_parse_list_response_unquoted_path():
    flags, delim, path = _parse_list_response(b'() "/" INBOX')
    assert path == 'INBOX'
    assert delim == '/'
    assert flags == []


def test_parse_list_response_nil_delimiter():
    flags, delim, path = _parse_list_response(b'(\\Noselect) NIL ""')
    assert delim is None


def test_parse_list_response_empty():
    flags, delim, path = _parse_list_response(b'')
    assert flags == []
    assert path is None


def test_parse_list_response_string_input():
    flags, delim, path = _parse_list_response('(\\HasNoChildren) "/" Archive')
    assert path == 'Archive'


def test_parse_list_response_unescapes_quoted_text():
    flags, delim, path = _parse_list_response(b'(\\HasNoChildren) "/" "Foo\\"Bar"')
    assert path == 'Foo"Bar'
    assert delim == '/'
    assert flags == ['\\HasNoChildren']


# ---------------------------------------------------------------------------
# discover_mailboxes_for_account — fake environment
# ---------------------------------------------------------------------------

def test_discover_mailboxes_fake_env():
    with FakeMailEnvironment() as env:
        account = {
            'imapHost': env.host,
            'imapPort': env.imap_server.port,
            'imapUseSSL': False,
            'username': env.username,
            'imapPassword': env.password,
        }
        mailboxes = discover_mailboxes_for_account(account)
    paths = [m['path'] for m in mailboxes]
    assert 'INBOX' in paths
    assert 'Archive' in paths
    assert 'Lists/Fing' in paths


def test_discover_mailboxes_noselect_flag():
    with FakeMailEnvironment() as env:
        env.mailboxes.append({
            'path': 'NoSelectFolder',
            'delimiter': '/',
            'flags': ['\\Noselect', '\\HasChildren'],
            'selectable': True,
        })
        account = {
            'imapHost': env.host,
            'imapPort': env.imap_server.port,
            'imapUseSSL': False,
            'username': env.username,
            'imapPassword': env.password,
        }
        mailboxes = discover_mailboxes_for_account(account)
    noselect = [m for m in mailboxes if m['path'] == 'NoSelectFolder']
    assert len(noselect) == 1
    assert noselect[0]['selectable'] is False


def test_discover_mailboxes_non_ok_list_response_raises():
    with mock.patch('imaplib.IMAP4_SSL') as mock_imap:
        mock_conn = mock.MagicMock()
        mock_imap.return_value = mock_conn
        mock_conn.login.return_value = ('OK', [])
        mock_conn.list.return_value = ('NO', [b'Mailbox list failed'])

        with pytest.raises(MailServiceError, match='mailbox'):
            discover_mailboxes_for_account({
                'imapHost': 'imap.example.com',
                'imapPort': 993,
                'imapUseSSL': True,
                'username': 'user@example.com',
                'imapPassword': 'secret',
            })


def test_discover_mailboxes_missing_host():
    with pytest.raises(MailServiceError, match='host'):
        discover_mailboxes_for_account({'imapHost': '', 'imapPort': 993})


# ---------------------------------------------------------------------------
# API: GET /mail/accounts/{account_id}/mailboxes
# ---------------------------------------------------------------------------

def _post_fake_account_settings(client: TestClient, env: FakeMailEnvironment) -> dict:
    """POST settings with a single fake IMAP account, non-dummy mode."""
    from backend.config import DEFAULT_SETTINGS
    payload = dict(DEFAULT_SETTINGS) | {
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
        'mailAccounts': [
            {
                'id': 'fake-account',
                'displayName': 'Fake',
                'enabled': True,
                'imapHost': env.host,
                'imapPort': env.imap_server.port,
                'imapUseSSL': False,
                'username': env.username,
                'imapPassword': env.password,
                'smtpHost': env.host,
                'smtpPort': env.smtp_server.port,
                'smtpUseSSL': False,
                'smtpPassword': env.password,
                'recipientEmail': env.recipient_email,
            }
        ],
    }
    r = client.post('/settings', json=payload)
    assert r.status_code == 200
    return payload


def test_api_mailboxes_dummy_mode_returns_sample():
    with TestClient(app) as client:
        response = client.get('/mail/accounts/any-id/mailboxes')
        assert response.status_code == 200
        data = response.json()
        paths = [m['path'] for m in data]
        assert 'INBOX' in paths
        assert all(m['accountId'] == 'sample' for m in data)


def test_api_mailboxes_all_dummy_mode_returns_sample():
    with TestClient(app) as client:
        response = client.get('/mail/mailboxes')
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert any(m['path'] == 'INBOX' for m in data)


def test_api_mailboxes_unknown_account_returns_404():
    with FakeMailEnvironment() as env:
        with TestClient(app) as client:
            _post_fake_account_settings(client, env)
            response = client.get('/mail/accounts/no-such-account/mailboxes')
    assert response.status_code == 404


def test_api_mailboxes_known_account_returns_list():
    with FakeMailEnvironment() as env:
        with TestClient(app) as client:
            _post_fake_account_settings(client, env)
            response = client.get('/mail/accounts/fake-account/mailboxes')
    assert response.status_code == 200
    data = response.json()
    paths = [m['path'] for m in data]
    assert 'INBOX' in paths
    assert 'Archive' in paths


def test_api_mailboxes_legacy_account_resolves_default_settings():
    with FakeMailEnvironment() as env:
        with TestClient(app) as client:
            from backend.config import DEFAULT_SETTINGS
            payload = dict(DEFAULT_SETTINGS) | {
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
            }
            response = client.post('/settings', json=payload)
            assert response.status_code == 200
            discovery = client.get('/mail/accounts/default/mailboxes')

    assert discovery.status_code == 200
    data = discovery.json()
    assert any(m['path'] == 'INBOX' for m in data)
    assert any(m['path'] == 'Archive' for m in data)


def test_api_mailboxes_all_accounts():
    with FakeMailEnvironment() as env:
        with TestClient(app) as client:
            _post_fake_account_settings(client, env)
            response = client.get('/mail/mailboxes')
    assert response.status_code == 200
    data = response.json()
    assert any(m['accountId'] == 'fake-account' for m in data)
    assert any(m['path'] == 'INBOX' for m in data)


def test_api_mailboxes_bad_credentials_returns_400():
    """Account with bad password should return 400 with a redacted message."""
    with mock.patch('imaplib.IMAP4_SSL') as mock_imap:
        mock_conn = mock.MagicMock()
        mock_imap.return_value = mock_conn
        mock_conn.login.side_effect = imaplib.IMAP4.error('Invalid credentials')

        with TestClient(app) as client:
            from backend.config import DEFAULT_SETTINGS
            payload = dict(DEFAULT_SETTINGS) | {
                'dummyMode': False,
                'mailAccounts': [
                    {
                        'id': 'bad-creds-account',
                        'displayName': 'Bad',
                        'enabled': True,
                        'imapHost': 'imap.example.com',
                        'imapPort': 993,
                        'imapUseSSL': True,
                        'username': 'user@example.com',
                        'imapPassword': 'wrong-password',
                        'smtpHost': '',
                        'smtpPort': 465,
                        'smtpUseSSL': False,
                        'smtpPassword': '',
                        'recipientEmail': '',
                    }
                ],
            }
            client.post('/settings', json=payload)
            response = client.get('/mail/accounts/bad-creds-account/mailboxes')

    assert response.status_code == 400
    detail = response.json().get('detail', '')
    assert 'authentication' in detail.lower()
    assert 'wrong-password' not in detail


# ---------------------------------------------------------------------------
# Regression: existing settings and summary routes still work
# ---------------------------------------------------------------------------

def test_settings_endpoint_still_works():
    with TestClient(app) as client:
        response = client.get('/settings')
        assert response.status_code == 200
        payload = response.json()
        assert 'dummyMode' in payload


def test_summaries_endpoint_still_works():
    with TestClient(app) as client:
        response = client.post('/summaries', json={
            'criteria': {'keyword': '', 'rawSearch': '', 'sender': '', 'recipient': '',
                         'unreadOnly': False, 'readOnly': False, 'replied': None,
                         'tag': '', 'useAnd': True},
            'summaryLength': 3,
        })
        assert response.status_code == 200
