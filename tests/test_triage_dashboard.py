from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from backend import app as backend_app
from backend import db as backend_db
from backend import routers_triage


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


def _iso_days_ago(days: int) -> str:
    value = datetime.now(timezone.utc) - timedelta(days=days)
    return value.isoformat().replace('+00:00', 'Z')


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
    date: str | None = None,
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
        'date': date or _iso_days_ago(0),
        'flags': flags or [],
        'keywords': keywords or [],
        'listId': list_id,
        'bodyPreview': body_preview,
        'bodyCached': bool(body_text),
        'bodyText': body_text,
        'lastSeenAt': _iso_days_ago(0),
    }


def _bucket_by_id(buckets: list[dict[str, object]], bucket_id: str) -> dict[str, object]:
    return next(bucket for bucket in buckets if str(bucket['id']) == bucket_id)


def test_dashboard_endpoint_returns_totals() -> None:
    _seed_index_rows()
    backend_db.upsert_index_message(_message_payload(
        message_id='acct-1|INBOX|1',
        mailbox='INBOX',
        uid='1',
        subject='Could you confirm the schedule?',
        sender='alice@example.com',
        body_preview='Could you confirm the schedule?',
        body_text='Could you confirm the schedule?',
    ))
    backend_db.upsert_index_message(_message_payload(
        message_id='acct-1|INBOX|2',
        mailbox='INBOX',
        uid='2',
        subject='Read follow-up',
        sender='bob@example.com',
        flags=['\\Seen'],
        body_preview='This is read.',
        body_text='This is read.',
    ))
    backend_db.upsert_index_message(_message_payload(
        message_id='acct-1|Junk|3',
        mailbox='Junk',
        uid='3',
        subject='Ignored junk',
        sender='junk@example.com',
        body_preview='Please ignore this.',
        body_text='Please ignore this.',
    ))

    with TestClient(backend_app.app) as client:
        response = client.get('/mail/triage/dashboard')

    assert response.status_code == 200
    payload = response.json()
    assert payload['scopeId'] == 'unread_or_flagged_all'
    assert payload['totals'] == {
        'messages': 1,
        'unread': 1,
        'flagged': 0,
    }
    reply_bucket = _bucket_by_id(payload['buckets'], 'reply_needed_candidates')
    assert reply_bucket['count'] == 1
    assert reply_bucket['messages'][0]['id'] == 'acct-1|INBOX|1'


def test_flagged_bucket_detects_flagged_messages() -> None:
    _seed_index_rows()
    backend_db.upsert_index_message(_message_payload(
        message_id='acct-1|INBOX|1',
        mailbox='INBOX',
        uid='1',
        subject='Flagged follow-up',
        sender='alice@example.com',
        flags=['\\Flagged'],
        body_preview='Flagged body',
        body_text='Flagged body',
    ))
    backend_db.upsert_index_message(_message_payload(
        message_id='acct-1|INBOX|2',
        mailbox='INBOX',
        uid='2',
        subject='Regular message',
        sender='bob@example.com',
        body_preview='Regular body',
        body_text='Regular body',
    ))

    with TestClient(backend_app.app) as client:
        response = client.get('/mail/triage/dashboard')

    assert response.status_code == 200
    flagged_bucket = _bucket_by_id(response.json()['buckets'], 'flagged')
    assert flagged_bucket['count'] == 1
    assert [message['id'] for message in flagged_bucket['messages']] == ['acct-1|INBOX|1']


def test_mailing_list_bucket_detects_list_id_and_list_fing() -> None:
    _seed_index_rows()
    backend_db.upsert_index_message(_message_payload(
        message_id='acct-1|INBOX|1',
        mailbox='INBOX',
        uid='1',
        subject='List announcement',
        sender='list@example.com',
        list_id='list.example.com',
        body_preview='List-Id header present',
        body_text='List-Id header present',
    ))
    backend_db.upsert_index_message(_message_payload(
        message_id='acct-1|INBOX|2',
        mailbox='INBOX',
        uid='2',
        subject='Fing list message',
        sender='list@example.com',
        keywords=['List_Fing'],
        body_preview='List tag present',
        body_text='List tag present',
    ))

    with TestClient(backend_app.app) as client:
        response = client.get('/mail/triage/dashboard')

    assert response.status_code == 200
    mailing_bucket = _bucket_by_id(response.json()['buckets'], 'mailing_lists')
    assert mailing_bucket['count'] == 2
    assert {message['id'] for message in mailing_bucket['messages']} == {
        'acct-1|INBOX|1',
        'acct-1|INBOX|2',
    }


def test_stale_unread_bucket_respects_threshold() -> None:
    _seed_index_rows()
    backend_db.upsert_index_message(_message_payload(
        message_id='acct-1|INBOX|1',
        mailbox='INBOX',
        uid='1',
        subject='Old unread message',
        sender='alice@example.com',
        date=_iso_days_ago(15),
        body_preview='Old unread body',
        body_text='Old unread body',
    ))
    backend_db.upsert_index_message(_message_payload(
        message_id='acct-1|INBOX|2',
        mailbox='INBOX',
        uid='2',
        subject='Recent unread message',
        sender='bob@example.com',
        date=_iso_days_ago(6),
        body_preview='Recent unread body',
        body_text='Recent unread body',
    ))

    with TestClient(backend_app.app) as client:
        response = client.get('/mail/triage/dashboard', params={'staleDays': 7})

    assert response.status_code == 200
    buckets = response.json()['buckets']
    stale_bucket = _bucket_by_id(buckets, 'stale_unread')
    recent_bucket = _bucket_by_id(buckets, 'recent_unread')
    assert stale_bucket['count'] == 1
    assert [message['id'] for message in stale_bucket['messages']] == ['acct-1|INBOX|1']
    assert recent_bucket['count'] == 1
    assert [message['id'] for message in recent_bucket['messages']] == ['acct-1|INBOX|2']


def test_bucket_limits_are_clamped() -> None:
    _seed_index_rows()
    for idx in range(120):
        backend_db.upsert_index_message(_message_payload(
            message_id=f'acct-1|INBOX|{idx + 1}',
            mailbox='INBOX',
            uid=str(idx + 1),
            subject=f'Could you review {idx + 1}?',
            sender='review@example.com',
            body_preview=f'Could you review {idx + 1}?',
            body_text=f'Could you review {idx + 1}?',
        ))

    with TestClient(backend_app.app) as client:
        response = client.get('/mail/triage/dashboard', params={'limitPerBucket': 500})

    assert response.status_code == 200
    reply_bucket = _bucket_by_id(response.json()['buckets'], 'reply_needed_candidates')
    assert reply_bucket['count'] == 120
    assert len(reply_bucket['messages']) == 100


def test_bucket_summary_creates_job() -> None:
    _seed_index_rows()
    backend_db.upsert_index_message(_message_payload(
        message_id='acct-1|INBOX|1',
        mailbox='INBOX',
        uid='1',
        subject='Could you review the invoice?',
        sender='finance@example.com',
        body_preview='Could you review the invoice?',
        body_text='Could you review the invoice?',
    ))
    backend_db.upsert_index_message(_message_payload(
        message_id='acct-1|INBOX|2',
        mailbox='INBOX',
        uid='2',
        subject='Please confirm the deadline',
        sender='finance@example.com',
        body_preview='Please confirm the deadline',
        body_text='Please confirm the deadline',
    ))

    with TestClient(backend_app.app) as client:
        save_response = client.post('/settings', json={
            **backend_app.DEFAULT_SETTINGS,
            'dummyMode': False,
        })
        assert save_response.status_code == 200

        with mock.patch.object(
            routers_triage,
            'summarize_messages',
            return_value=('Bucket summary', {'status': 'ok', 'provider': 'stub', 'model': 'stub'}),
        ) as summarize_mock, mock.patch.object(routers_triage, 'insert_job') as insert_job_mock:
            response = client.post('/mail/triage/buckets/reply_needed_candidates/summary', json={
                'scopeId': 'unread_or_flagged_all',
                'summaryLength': 6,
                'limitPerBucket': 10,
                'staleDays': 14,
            })

    assert response.status_code == 200
    assert response.json()['summary'] == 'Bucket summary'
    summarize_mock.assert_called_once()
    assert insert_job_mock.call_args.args[2]['triageBucketId'] == 'reply_needed_candidates'
    assert insert_job_mock.call_args.args[2]['scopeId'] == 'unread_or_flagged_all'


def test_empty_bucket_summary_avoids_provider_call() -> None:
    with TestClient(backend_app.app) as client:
        save_response = client.post('/settings', json={
            **backend_app.DEFAULT_SETTINGS,
            'dummyMode': False,
        })
        assert save_response.status_code == 200

        with mock.patch('backend.summary_service.get_provider_client') as provider_mock:
            with mock.patch.object(routers_triage, 'insert_job') as insert_job_mock:
                response = client.post('/mail/triage/buckets/reply_needed_candidates/summary', json={
                    'scopeId': 'unread_or_flagged_all',
                    'summaryLength': 5,
                    'limitPerBucket': 10,
                    'staleDays': 14,
                })

    assert response.status_code == 200
    assert response.json()['messages'] == []
    assert response.json()['summary'].startswith('No messages matched')
    provider_mock.assert_not_called()
    assert insert_job_mock.call_args.args[2]['triageBucketId'] == 'reply_needed_candidates'
