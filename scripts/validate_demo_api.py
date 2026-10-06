"""Synthetic-only acceptance tests in a fresh demo process (no network needed)."""
from __future__ import annotations
import os
from pathlib import Path
import sys
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

os.environ['MAIL_SUMMARISER_DEMO'] = 'true'
# Deliberately conflicting synthetic settings must never escape into the demo.
os.environ.update(DUMMY_MODE='false', SAFE_MODE='false', LLM_PROVIDER='openai',
                  OPENAI_API_KEY='synthetic-not-a-key', IMAP_HOST='invalid.example',
                  SMTP_HOST='invalid.example', OLLAMA_START_ON_STARTUP='true')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from backend import demo, db, mail_service, summary_service
from backend.app import app, _merged_settings
from backend.config import DATA_DIR
from backend import routers_actions


class IsolatedDemoTests(unittest.TestCase):
    def setUp(self):
        self.client_context = TestClient(app)
        self.client = self.client_context.__enter__()
        # A single accidental transport/provider call fails the acceptance test.
        self.patches = [patch('socket.socket.connect', side_effect=AssertionError('Network blocked in demo')),
                        patch('socket.create_connection', side_effect=AssertionError('Network blocked in demo')),
                        patch.object(summary_service, '_summarize_with_provider', side_effect=AssertionError('Provider called')),
                        patch.object(routers_actions, 'send_summary_email', side_effect=AssertionError('SMTP called'))]
        for guard in self.patches: guard.start()

    def tearDown(self):
        for guard in reversed(self.patches): guard.stop()
        self.client_context.__exit__(None, None, None)

    def job(self, **criteria):
        r = self.client.post('/summaries', json={'criteria': criteria})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIn('local excerpts, no AI provider', r.json()['summary'])
        return r.json()['jobId']

    def preview(self, job, action='mark_read'):
        r = self.client.post(f'/actions/jobs/{job}/preview', json={'action': action})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def apply(self, job, plan, **extra):
        return self.client.post(f'/actions/jobs/{job}/apply', json={'action': plan['action'], 'previewToken': plan['previewToken'], **extra})

    def enable_changes(self):
        self.assertEqual(self.client.post('/demo/safe-mode', json={'safeMode': False}).status_code, 200)

    def test_onboarding_is_indexed_and_explicit(self):
        html = self.client.get('/')
        self.assertIn('data-isolated-demo="true"', html.text)
        self.assertIn("connect-src 'self'", html.headers['content-security-policy'])
        self.assertEqual(self.client.get('/mail/scopes').status_code, 200)
        self.assertGreater(len(self.client.get('/mail/scopes').json()), 0)
        self.assertEqual(len(self.client.get('/mail/index/messages').json()), 8)
        self.assertEqual(self.client.get('/mail/triage/dashboard').json()['totals']['unread'], 6)
        self.assertTrue(self.client.get('/settings').json()['safeMode'])
        self.assertTrue(DATA_DIR.name.startswith('mail-summariser-demo-'))
        self.assertNotIn('synthetic-not-a-key', self.client.get('/settings').text)

    def test_live_provider_send_and_admin_paths_default_deny(self):
        for method, path, data in [('POST', '/settings', {'dummyMode': False}),
            ('POST', '/settings/dummy-mode', {'dummyMode': False}),
            ('POST', '/settings/test-connection', {'imapHost': 'invalid.example'}),
            ('POST', '/actions/email-summary', {}), ('POST', '/runtime/ollama/start', {}),
            ('GET', '/runtime/status', None), ('GET', '/models/catalog', None),
            ('POST', '/models/download', {'name':'example'}), ('POST', '/admin/database/reset', {}),
            ('GET', '/openapi.json', None), ('POST', '/dev/fake-mail/start', {}),
            ('POST', '/actions/email-summary/', {}), ('POST', '/actions%2femail-summary', {})]:
            with self.subTest(path=path):
                self.assertEqual(self.client.request(method, path, json=data).status_code, 403)
        self.job()
        self.assertEqual(mail_service.get_dummy_outbox(), [])

    def test_origin_and_host_guard(self):
        self.assertEqual(self.client.get('/settings', headers={'Origin': 'https://untrusted.example'}).status_code, 403)
        self.assertEqual(self.client.get('/settings', headers={'Host': 'untrusted.example'}).status_code, 403)
        self.assertEqual(self.client.get('/settings', headers={'Origin': 'http://testserver'}).status_code, 200)

    def test_settings_poisoning_cannot_enable_transport(self):
        db.set_setting('dummyMode', False)
        db.set_setting('imapHost', 'invalid.example')
        db.set_setting('ollamaStartOnStartup', True)
        self.assertTrue(_merged_settings()['dummyMode'])
        self.assertFalse(_merged_settings()['ollamaStartOnStartup'])
        self.assertEqual(_merged_settings()['imapHost'], '')
        self.job()
        db.set_setting('dummyMode', True)

    def test_preview_is_mandatory_even_in_safe_mode(self):
        job = self.job()
        self.assertEqual(self.client.post(f'/actions/jobs/{job}/apply', json={'action': 'mark_read'}).status_code, 409)

    def test_dry_run_does_not_mutate_and_token_is_one_use(self):
        job = self.job(unreadOnly=True)
        plan = self.preview(job)
        result = self.apply(job, plan)
        self.assertFalse(result.json()['applied'])
        self.assertEqual(self.client.get('/mail/triage/dashboard').json()['totals']['unread'], 6)
        self.assertEqual(self.apply(job, plan).status_code, 409)

    def test_mark_read_and_undo_refresh_index(self):
        self.enable_changes()
        job = self.job(unreadOnly=True)
        result = self.apply(job, self.preview(job)).json()
        self.assertEqual(len(result['changedIds']), 6)
        self.assertEqual(self.client.get('/mail/triage/dashboard').json()['totals']['unread'], 0)
        self.assertEqual(self.preview(job)['changeCount'], 0)
        self.assertEqual(self.client.post('/actions/undo/logs/'+result['logId']).status_code, 200)
        self.assertEqual(self.client.get('/mail/triage/dashboard').json()['totals']['unread'], 6)
        self.assertEqual(self.client.post('/actions/undo/logs/'+result['logId']).status_code, 404)

    def test_archive_resync_and_undo_keep_exactly_eight_messages(self):
        self.enable_changes()
        job = self.job(keyword='Project')
        result = self.apply(job, self.preview(job, 'archive')).json()
        self.assertEqual(len(result['changedIds']), 1)
        for _ in range(3):
            self.assertEqual(self.client.post('/mail/index/sync', json={}).json()['indexed'], 8)
            self.assertEqual(len(self.client.get('/mail/index/messages?mailbox=Archive').json()), 2)
        self.assertEqual(self.preview(job, 'archive')['changeCount'], 0)
        self.client.post('/actions/undo/logs/'+result['logId'])
        self.assertEqual(len(self.client.get('/mail/index/messages?mailbox=Archive').json()), 1)

    def test_safety_toggle_and_changed_message_invalidate_preview(self):
        job = self.job()
        plan = self.preview(job)
        self.enable_changes()
        self.assertEqual(self.apply(job, plan).status_code, 409)
        old = self.preview(job)
        self.apply(job, self.preview(job))
        self.assertEqual(self.apply(job, old).status_code, 409)

    def test_expired_token_rejected(self):
        job = self.job()
        plan = self.preview(job)
        with patch.object(demo, 'monotonic', return_value=10**15):
            self.assertEqual(self.apply(job, plan).status_code, 409)

    def test_token_is_bound_to_job_and_action(self):
        one, two = self.job(), self.job(keyword='Project')
        self.assertEqual(self.apply(two, self.preview(one)).status_code, 409)
        plan = self.preview(one)
        self.assertEqual(self.apply(one, plan, action='archive').status_code, 409)

    def test_repeated_concurrent_apply_changes_once(self):
        self.enable_changes()
        job = self.job()
        plan = self.preview(job)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: self.apply(job, plan).status_code, range(2)))
        self.assertEqual(sorted(results), [200, 409])

    def test_reset_invalidates_jobs_and_restores_safe_mode(self):
        self.enable_changes()
        job = self.job()
        plan = self.preview(job)
        self.assertEqual(self.client.post('/demo/reset').status_code, 200)
        self.assertEqual(self.apply(job, plan).status_code, 404)
        self.assertTrue(self.client.get('/settings').json()['safeMode'])
        self.assertEqual(self.client.get('/logs').json(), [])

    def test_failed_undo_preserves_recovery(self):
        self.enable_changes()
        job = self.job()
        result = self.apply(job, self.preview(job)).json()
        with patch.object(routers_actions, 'restore_messages_unread', side_effect=RuntimeError('Synthetic failure')):
            self.assertEqual(self.client.post('/actions/undo/logs/'+result['logId']).status_code, 400)
        self.assertEqual(self.client.post('/actions/undo/logs/'+result['logId']).status_code, 200)

    def test_index_failure_keeps_prior_index_and_action_recovery(self):
        self.enable_changes()
        job = self.job()
        plan = self.preview(job)
        with patch('backend.mail_index_service.sync_mailbox', side_effect=RuntimeError('Synthetic index failure')):
            self.assertEqual(self.apply(job, plan).status_code, 503)
        self.assertEqual(len(self.client.get('/mail/index/messages').json()), 8)
        logs = self.client.get('/logs').json()
        self.assertTrue(any(log['undoable'] for log in logs))
        self.assertEqual(self.client.post('/actions/undo').status_code, 200)
        self.assertEqual(self.client.get('/mail/triage/dashboard').json()['totals']['unread'], 6)

    def test_partial_undo_failure_preserves_recovery(self):
        self.enable_changes()
        job = self.job()
        result = self.apply(job, self.preview(job)).json()
        with patch.object(routers_actions, 'restore_messages_unread', return_value={'failed_message_ids':['demo-001']}):
            self.assertEqual(self.client.post('/actions/undo/logs/'+result['logId']).status_code, 409)
        self.assertEqual(self.client.post('/actions/undo/logs/'+result['logId']).status_code, 200)

    def test_invalid_demo_controls_and_unknown_mailboxes_fail_closed(self):
        self.assertEqual(self.client.post('/demo/safe-mode', json={'safeMode':'false'}).status_code, 422)
        self.assertEqual(self.client.post('/mail/index/sync', json={'accountId':'live'}).status_code, 400)
        self.assertEqual(self.client.post('/mail/index/sync', json={'mailbox':'Other'}).status_code, 400)


if __name__ == '__main__':
    unittest.main(verbosity=2)
