from __future__ import annotations

from unittest import mock

import pytest
from fastapi.testclient import TestClient

from backend import app as backend_app
from backend import db as backend_db
from backend import routers_saved_scopes


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


def _seed_index_rows() -> None:
    backend_db.upsert_index_account({
        'id': 'acct-1',
        'displayName': 'Account One',
        'username': 'user@example.com',
        'imapHost': 'imap.example.com',
        'enabled': True,
    })
    for mailbox in ('INBOX', 'Junk', 'Deleted Messages'):
        backend_db.upsert_index_mailbox('acct-1', {
            'path': mailbox,
            'delimiter': '/',
            'selectable': True,
            'flags': [],
        })


def _message_payload(
    *,
    message_id: str,
    mailbox: str,
    uid: str,
    subject: str,
    sender: str,
    body_preview: str = '',
    body_text: str = '',
    flags: list[str] | None = None,
    keywords: list[str] | None = None,
    list_id: str = '',
) -> dict[str, object]:
    return {
        'id': message_id,
        'accountId': 'acct-1',
        'mailboxPath': mailbox,
        'uid': uid,
        'messageIdHeader': f'<{message_id}@example.com>',
        'subject': subject,
        'sender': sender,
        'recipients': ['user@example.com'],
        'date': '2026-06-08T09:00:00Z',
        'flags': flags or [],
        'keywords': keywords or [],
        'listId': list_id,
        'bodyPreview': body_preview,
        'bodyCached': bool(body_text),
        'bodyText': body_text,
        'lastSeenAt': '2026-06-08T09:00:00',
    }


def _scope_ids(scopes: list[dict[str, object]]) -> list[str]:
    return [str(scope['id']) for scope in scopes]


def test_default_scopes_are_created() -> None:
    with TestClient(backend_app.app) as client:
        response = client.get('/mail/scopes')

    assert response.status_code == 200
    assert _scope_ids(response.json()) == [
        'unread_or_flagged_all',
        'flagged_all',
        'unread_all',
        'lists_fing',
        'finance',
    ]


def test_database_reset_restores_default_scopes() -> None:
    with TestClient(backend_app.app) as client:
        create_response = client.post('/mail/scopes', json={
            'id': 'custom_scope',
            'name': 'Custom Scope',
            'description': 'Temporary scope',
            'query': {'accounts': ['*'], 'subjectContains': 'temporary'},
            'sortOrder': 60,
        })
        assert create_response.status_code == 201
        assert 'custom_scope' in _scope_ids(client.get('/mail/scopes').json())

        reset_response = client.post('/admin/database/reset', json={'confirmation': 'RESET DATABASE'})

    assert reset_response.status_code == 200
    assert reset_response.json()['removed']['saved_scopes'] >= 1

    with TestClient(backend_app.app) as client:
        scope_ids = _scope_ids(client.get('/mail/scopes').json())

    assert scope_ids == [
        'unread_or_flagged_all',
        'flagged_all',
        'unread_all',
        'lists_fing',
        'finance',
    ]
    assert 'custom_scope' not in scope_ids


def test_saved_scope_crud_round_trip() -> None:
    with TestClient(backend_app.app) as client:
        create_response = client.post('/mail/scopes', json={
            'id': 'custom_scope',
            'name': 'Custom Scope',
            'description': 'Initial description',
            'query': {'accounts': ['*'], 'subjectContains': 'budget'},
            'sortOrder': 60,
        })
        assert create_response.status_code == 201
        assert create_response.json()['name'] == 'Custom Scope'

        scopes = client.get('/mail/scopes').json()
        assert any(scope['id'] == 'custom_scope' for scope in scopes)

        update_response = client.put('/mail/scopes/custom_scope', json={
            'name': 'Updated Scope',
            'description': 'Updated description',
            'query': {'accounts': ['*'], 'flagged': True},
            'sortOrder': 61,
        })
        assert update_response.status_code == 200
        assert update_response.json()['name'] == 'Updated Scope'
        assert update_response.json()['query']['flagged'] is True

        delete_response = client.delete('/mail/scopes/custom_scope')
        assert delete_response.status_code == 200
        assert delete_response.json()['status'] == 'ok'

        remaining_ids = _scope_ids(client.get('/mail/scopes').json())
        assert 'custom_scope' not in remaining_ids


def test_scope_evaluator_returns_unread_or_flagged_messages() -> None:
    _seed_index_rows()
    backend_db.upsert_index_message(_message_payload(
        message_id='acct-1|INBOX|1',
        mailbox='INBOX',
        uid='1',
        subject='Unread message',
        sender='alice@example.com',
        body_preview='Unread body',
        body_text='Unread body',
    ))
    backend_db.upsert_index_message(_message_payload(
        message_id='acct-1|INBOX|2',
        mailbox='INBOX',
        uid='2',
        subject='Flagged message',
        sender='bob@example.com',
        flags=['\\Flagged'],
        body_preview='Flagged body',
        body_text='Flagged body',
    ))
    backend_db.upsert_index_message(_message_payload(
        message_id='acct-1|INBOX|3',
        mailbox='INBOX',
        uid='3',
        subject='Read message',
        sender='carol@example.com',
        flags=['\\Seen'],
        body_preview='Read body',
        body_text='Read body',
    ))

    with TestClient(backend_app.app) as client:
        response = client.get('/mail/scopes/unread_or_flagged_all/messages', params={'limit': 10})

    assert response.status_code == 200
    assert {message['id'] for message in response.json()} == {
        'acct-1|INBOX|1',
        'acct-1|INBOX|2',
    }


def test_scope_evaluator_excludes_deleted_and_junk_mailboxes() -> None:
    _seed_index_rows()
    backend_db.upsert_index_message(_message_payload(
        message_id='acct-1|INBOX|1',
        mailbox='INBOX',
        uid='1',
        subject='List mail in inbox',
        sender='list@example.com',
        keywords=['List_Fing'],
        body_preview='Inbox list message',
        body_text='Inbox list message',
    ))
    backend_db.upsert_index_message(_message_payload(
        message_id='acct-1|Junk|2',
        mailbox='Junk',
        uid='2',
        subject='List mail in junk',
        sender='list@example.com',
        keywords=['List_Fing'],
        body_preview='Junk list message',
        body_text='Junk list message',
    ))
    backend_db.upsert_index_message(_message_payload(
        message_id='acct-1|Deleted Messages|3',
        mailbox='Deleted Messages',
        uid='3',
        subject='List mail in deleted',
        sender='list@example.com',
        keywords=['List_Fing'],
        body_preview='Deleted list message',
        body_text='Deleted list message',
    ))

    with TestClient(backend_app.app) as client:
        response = client.get('/mail/scopes/lists_fing/messages', params={'limit': 10})

    assert response.status_code == 200
    assert {message['id'] for message in response.json()} == {'acct-1|INBOX|1'}


def test_lists_fing_scope_matches_keyword_list_fing() -> None:
    _seed_index_rows()
    backend_db.upsert_index_message(_message_payload(
        message_id='acct-1|INBOX|1',
        mailbox='INBOX',
        uid='1',
        subject='Fing list message',
        sender='list@example.com',
        keywords=['List_Fing'],
        body_preview='List body',
        body_text='List body',
    ))

    with TestClient(backend_app.app) as client:
        response = client.get('/mail/scopes/lists_fing/messages', params={'limit': 10})

    assert response.status_code == 200
    assert [message['id'] for message in response.json()] == ['acct-1|INBOX|1']


def test_scope_summary_creates_job_and_uses_cached_body() -> None:
    _seed_index_rows()
    backend_db.upsert_index_message(_message_payload(
        message_id='acct-1|INBOX|1',
        mailbox='INBOX',
        uid='1',
        subject='Quarterly budget',
        sender='finance@example.com',
        body_preview='Preview text',
        body_text='Cached body text',
    ))

    with TestClient(backend_app.app) as client:
        save_response = client.post('/settings', json={
            **backend_app.DEFAULT_SETTINGS,
            'dummyMode': False,
        })
        assert save_response.status_code == 200

        with mock.patch.object(
            routers_saved_scopes,
            'summarize_messages',
            return_value=('Scope summary', {'status': 'ok', 'provider': 'stub', 'model': 'stub'}),
        ) as summarize_mock, mock.patch.object(routers_saved_scopes, 'insert_job') as insert_job_mock:
            response = client.post('/mail/scopes/unread_or_flagged_all/summary', json={
                'summaryLength': 6,
                'limit': 10,
            })

    assert response.status_code == 200
    assert response.json()['summary'] == 'Scope summary'
    assert response.json()['messages'][0]['id'] == 'acct-1|INBOX|1'
    summarize_mock.assert_called_once()
    summary_messages = summarize_mock.call_args.args[0]
    assert summary_messages[0]['body'] == 'Cached body text'
    insert_job_mock.assert_called_once()
    assert insert_job_mock.call_args.args[2]['scopeId'] == 'unread_or_flagged_all'
    assert insert_job_mock.call_args.args[5][0]['body'] == 'Cached body text'


def test_scope_summary_handles_empty_result_without_provider_call() -> None:
    with TestClient(backend_app.app) as client:
        save_response = client.post('/settings', json={
            **backend_app.DEFAULT_SETTINGS,
            'dummyMode': False,
        })
        assert save_response.status_code == 200

        with mock.patch('backend.summary_service.get_provider_client') as provider_mock:
            with mock.patch.object(routers_saved_scopes, 'insert_job') as insert_job_mock:
                response = client.post('/mail/scopes/unread_or_flagged_all/summary', json={
                    'summaryLength': 5,
                    'limit': 10,
                })

    assert response.status_code == 200
    assert response.json()['messages'] == []
    assert response.json()['summary'].startswith('No messages matched')
    provider_mock.assert_not_called()
    insert_job_mock.assert_called_once()
    assert insert_job_mock.call_args.args[2]['scopeId'] == 'unread_or_flagged_all'
    assert insert_job_mock.call_args.args[5] == []
