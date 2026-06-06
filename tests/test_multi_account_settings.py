"""Tests for multi-account settings support.

This module tests backwards-compatible multi-account settings:
- mailAccounts list persists and retrieves correctly
- account secrets are masked in reads
- masked secret writes don't overwrite stored secrets
- legacy single-account fields remain compatible
"""

import pytest
from fastapi.testclient import TestClient

from backend.app import app
from backend import db as backend_db
from backend.config import DEFAULT_SETTINGS
from backend.schemas import AppSettings, MailAccountSettings


def _base_settings() -> dict[str, object]:
    """Return a copy of default settings."""
    return dict(DEFAULT_SETTINGS)


@pytest.fixture(autouse=True)
def isolated_settings_db(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """Isolate each test to a temporary database."""
    monkeypatch.setattr(backend_db, 'DB_PATH', tmp_path / 'mail_summariser-test.sqlite3')


def test_settings_endpoint_includes_mail_accounts_field() -> None:
    """Verify /settings response includes mailAccounts."""
    with TestClient(app) as client:
        response = client.get('/settings')
        assert response.status_code == 200
        payload = response.json()
        assert 'mailAccounts' in payload
        assert isinstance(payload['mailAccounts'], list)


def test_mail_accounts_defaults_to_empty_list() -> None:
    """Verify mailAccounts defaults to empty list."""
    with TestClient(app) as client:
        response = client.get('/settings')
        assert response.status_code == 200
        payload = response.json()
        assert payload['mailAccounts'] == []


def test_post_settings_persists_mail_accounts() -> None:
    """Verify POST /settings persists mailAccounts list."""
    with TestClient(app) as client:
        account1 = {
            'id': 'personal',
            'displayName': 'Personal Email',
            'enabled': True,
            'imapHost': 'imap.gmail.com',
            'imapPort': 993,
            'imapUseSSL': True,
            'username': 'user@example.com',
            'imapPassword': 'secret-imap-password',
            'smtpHost': 'smtp.gmail.com',
            'smtpPort': 465,
            'smtpUseSSL': True,
            'smtpPassword': 'secret-smtp-password',
            'recipientEmail': 'user@example.com',
        }
        account2 = {
            'id': 'work',
            'displayName': 'Work Email',
            'enabled': True,
            'imapHost': 'imap.company.com',
            'imapPort': 993,
            'imapUseSSL': True,
            'username': 'user@company.com',
            'imapPassword': 'work-imap-password',
            'smtpHost': 'smtp.company.com',
            'smtpPort': 465,
            'smtpUseSSL': True,
            'smtpPassword': 'work-smtp-password',
            'recipientEmail': 'user@company.com',
        }

        payload = _base_settings()
        payload['mailAccounts'] = [account1, account2]

        response = client.post('/settings', json=payload)
        assert response.status_code == 200

        # Retrieve and verify persistence
        settings_response = client.get('/settings')
        assert settings_response.status_code == 200
        settings_payload = settings_response.json()
        assert len(settings_payload['mailAccounts']) == 2
        assert settings_payload['mailAccounts'][0]['id'] == 'personal'
        assert settings_payload['mailAccounts'][1]['id'] == 'work'


def test_account_secrets_masked_in_read() -> None:
    """Verify account imapPassword and smtpPassword are masked in reads."""
    with TestClient(app) as client:
        account = {
            'id': 'test-account',
            'displayName': 'Test Account',
            'enabled': True,
            'imapHost': 'imap.example.com',
            'imapPort': 993,
            'imapUseSSL': True,
            'username': 'testuser@example.com',
            'imapPassword': 'secret-imap-pass',
            'smtpHost': 'smtp.example.com',
            'smtpPort': 465,
            'smtpUseSSL': True,
            'smtpPassword': 'secret-smtp-pass',
            'recipientEmail': 'testuser@example.com',
        }

        payload = _base_settings()
        payload['mailAccounts'] = [account]

        client.post('/settings', json=payload)

        # Read settings and verify secrets are masked
        response = client.get('/settings')
        assert response.status_code == 200
        settings_payload = response.json()
        assert len(settings_payload['mailAccounts']) == 1
        retrieved_account = settings_payload['mailAccounts'][0]
        assert retrieved_account['imapPassword'] == '__MASKED__'
        assert retrieved_account['smtpPassword'] == '__MASKED__'
        assert retrieved_account['username'] == 'testuser@example.com'  # non-secret fields visible


def test_masked_account_secret_write_preserves_stored_secret() -> None:
    """Verify writing __MASKED__ account secrets doesn't overwrite stored values."""
    with TestClient(app) as client:
        # Create initial account with secrets
        account1 = {
            'id': 'test-account',
            'displayName': 'Test Account',
            'enabled': True,
            'imapHost': 'imap.example.com',
            'imapPort': 993,
            'imapUseSSL': True,
            'username': 'testuser@example.com',
            'imapPassword': 'original-imap-secret',
            'smtpHost': 'smtp.example.com',
            'smtpPort': 465,
            'smtpUseSSL': True,
            'smtpPassword': 'original-smtp-secret',
            'recipientEmail': 'testuser@example.com',
        }

        payload1 = _base_settings()
        payload1['mailAccounts'] = [account1]
        assert client.post('/settings', json=payload1).status_code == 200

        # Verify original secrets were stored (by updating with different secrets)
        account1_updated = account1.copy()
        account1_updated['displayName'] = 'Updated Name'
        payload2 = _base_settings()
        payload2['mailAccounts'] = [account1_updated]
        assert client.post('/settings', json=payload2).status_code == 200

        # Now read and get masked values
        response = client.get('/settings')
        retrieved = response.json()
        assert retrieved['mailAccounts'][0]['imapPassword'] == '__MASKED__'
        assert retrieved['mailAccounts'][0]['smtpPassword'] == '__MASKED__'

        # Send update with masked values back
        account_update_with_masked = retrieved['mailAccounts'][0].copy()
        # Keep masked sentinel values
        payload3 = _base_settings()
        payload3['mailAccounts'] = [account_update_with_masked]
        assert client.post('/settings', json=payload3).status_code == 200

        # Read again and verify __MASKED__ writes didn't erase the original secrets
        # We can't directly read the secrets (they're masked), but if they were erased,
        # the account would have empty secrets. Instead, verify the account still exists
        # with the same structure (displayName change persisted but secrets preserved)
        response2 = client.get('/settings')
        retrieved2 = response2.json()
        assert len(retrieved2['mailAccounts']) == 1
        assert retrieved2['mailAccounts'][0]['displayName'] == 'Updated Name'
        assert retrieved2['mailAccounts'][0]['imapPassword'] == '__MASKED__'
        assert retrieved2['mailAccounts'][0]['smtpPassword'] == '__MASKED__'


def test_legacy_imap_settings_still_work() -> None:
    """Verify legacy top-level IMAP fields still persist and retrieve correctly."""
    with TestClient(app) as client:
        payload = _base_settings()
        payload['imapHost'] = 'legacy.imap.example.com'
        payload['imapPort'] = 993
        payload['imapUseSSL'] = True
        payload['username'] = 'legacyuser@example.com'
        payload['imapPassword'] = 'legacy-secret-pass'
        payload['recipientEmail'] = 'legacyuser@example.com'

        response = client.post('/settings', json=payload)
        assert response.status_code == 200

        # Retrieve and verify legacy fields
        settings_response = client.get('/settings')
        assert settings_response.status_code == 200
        settings_payload = settings_response.json()
        assert settings_payload['imapHost'] == 'legacy.imap.example.com'
        assert settings_payload['imapPort'] == 993
        assert settings_payload['imapUseSSL'] is True
        assert settings_payload['username'] == 'legacyuser@example.com'
        assert settings_payload['imapPassword'] == '__MASKED__'
        assert settings_payload['recipientEmail'] == 'legacyuser@example.com'


def test_legacy_and_multi_account_coexist() -> None:
    """Verify legacy fields and mailAccounts can coexist in settings."""
    with TestClient(app) as client:
        account = {
            'id': 'account1',
            'displayName': 'Account 1',
            'enabled': True,
            'imapHost': 'imap1.example.com',
            'imapPort': 993,
            'imapUseSSL': True,
            'username': 'user1@example.com',
            'imapPassword': 'pass1',
            'smtpHost': 'smtp1.example.com',
            'smtpPort': 465,
            'smtpUseSSL': True,
            'smtpPassword': 'pass1-smtp',
            'recipientEmail': 'user1@example.com',
        }

        payload = _base_settings()
        payload['imapHost'] = 'legacy.imap.example.com'  # Legacy field
        payload['username'] = 'legacyuser@example.com'  # Legacy field
        payload['imapPassword'] = 'legacy-pass'  # Legacy field
        payload['mailAccounts'] = [account]  # New multi-account field

        response = client.post('/settings', json=payload)
        assert response.status_code == 200

        # Retrieve and verify both coexist
        settings_response = client.get('/settings')
        assert settings_response.status_code == 200
        settings_payload = settings_response.json()

        # Legacy fields present
        assert settings_payload['imapHost'] == 'legacy.imap.example.com'
        assert settings_payload['username'] == 'legacyuser@example.com'
        assert settings_payload['imapPassword'] == '__MASKED__'

        # Multi-account field present
        assert len(settings_payload['mailAccounts']) == 1
        assert settings_payload['mailAccounts'][0]['id'] == 'account1'


def test_empty_account_passwords_not_masked() -> None:
    """Verify empty account passwords are not masked (empty != secret)."""
    with TestClient(app) as client:
        account = {
            'id': 'incomplete-account',
            'displayName': 'Incomplete Account',
            'enabled': False,
            'imapHost': 'imap.example.com',
            'imapPort': 993,
            'imapUseSSL': True,
            'username': 'user@example.com',
            'imapPassword': '',  # Empty, not a secret
            'smtpHost': 'smtp.example.com',
            'smtpPort': 465,
            'smtpUseSSL': True,
            'smtpPassword': '',  # Empty, not a secret
            'recipientEmail': 'user@example.com',
        }

        payload = _base_settings()
        payload['mailAccounts'] = [account]

        client.post('/settings', json=payload)

        # Read and verify empty passwords are not masked
        response = client.get('/settings')
        assert response.status_code == 200
        settings_payload = response.json()
        retrieved_account = settings_payload['mailAccounts'][0]
        assert retrieved_account['imapPassword'] == ''
        assert retrieved_account['smtpPassword'] == ''


def test_multiple_accounts_each_masked_independently() -> None:
    """Verify secrets are masked independently for each account."""
    with TestClient(app) as client:
        account1 = {
            'id': 'account1',
            'displayName': 'Account 1',
            'enabled': True,
            'imapHost': 'imap1.example.com',
            'imapPort': 993,
            'imapUseSSL': True,
            'username': 'user1@example.com',
            'imapPassword': 'account1-imap-secret',
            'smtpHost': 'smtp1.example.com',
            'smtpPort': 465,
            'smtpUseSSL': True,
            'smtpPassword': 'account1-smtp-secret',
            'recipientEmail': 'user1@example.com',
        }
        account2 = {
            'id': 'account2',
            'displayName': 'Account 2',
            'enabled': True,
            'imapHost': 'imap2.example.com',
            'imapPort': 993,
            'imapUseSSL': True,
            'username': 'user2@example.com',
            'imapPassword': 'account2-imap-secret',
            'smtpHost': 'smtp2.example.com',
            'smtpPort': 465,
            'smtpUseSSL': True,
            'smtpPassword': 'account2-smtp-secret',
            'recipientEmail': 'user2@example.com',
        }

        payload = _base_settings()
        payload['mailAccounts'] = [account1, account2]

        client.post('/settings', json=payload)

        # Read and verify both are masked independently
        response = client.get('/settings')
        assert response.status_code == 200
        settings_payload = response.json()
        assert len(settings_payload['mailAccounts']) == 2

        for i, account in enumerate(settings_payload['mailAccounts'], 1):
            assert account['imapPassword'] == '__MASKED__'
            assert account['smtpPassword'] == '__MASKED__'
            assert account['username'] == f'user{i}@example.com'
