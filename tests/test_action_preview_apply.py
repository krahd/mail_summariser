"""Preview / apply action API: dry-run, safe-mode, and undo behaviour."""

from __future__ import annotations

import importlib
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from datetime import datetime
from unittest import mock

from fastapi.testclient import TestClient

mail_service: Any = None
dummy_state: Any = None
db: Any = None
backend_app: Any = None

SUMMARY_PAYLOAD = {
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
}


class ActionPreviewApplyTests(unittest.TestCase):
    def setUp(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        backend_dir = repo_root / "backend"
        if str(backend_dir) not in sys.path:
            sys.path.insert(0, str(backend_dir))
        globals()["mail_service"] = importlib.import_module("mail_service")
        globals()["dummy_state"] = importlib.import_module("dummy_state")
        globals()["db"] = importlib.import_module("db")
        globals()["backend_app"] = importlib.import_module("app")

        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_db_path = db.DB_PATH
        db.DB_PATH = Path(self.temp_dir.name) / "mail_summariser.sqlite3"
        backend_app.DEFAULT_SETTINGS["ollamaAutoStart"] = False
        backend_app._reset_dummy_sandbox()

    def tearDown(self) -> None:
        backend_app._reset_dummy_sandbox()
        db.DB_PATH = self.original_db_path
        self.temp_dir.cleanup()

    def _client(self) -> TestClient:
        return TestClient(backend_app.app)

    def _make_job(self, client: TestClient) -> str:
        summary = client.post(
            "/summaries",
            json={**SUMMARY_PAYLOAD, "criteria": {**SUMMARY_PAYLOAD["criteria"], "keyword": "project"}},
        )
        self.assertEqual(summary.status_code, 200)
        return summary.json()["jobId"]

    def _set_safe_mode(self, client: TestClient, value: bool) -> None:
        settings = client.get("/settings").json()
        settings["safeMode"] = value
        self.assertEqual(client.post("/settings", json=settings).status_code, 200)

    def test_preview_reports_planned_changes(self) -> None:
        with self._client() as client:
            job_id = self._make_job(client)
            response = client.post(f"/actions/jobs/{job_id}/preview", json={"action": "mark_read"})
            self.assertEqual(response.status_code, 200)
            plan = response.json()
            self.assertEqual(plan["action"], "mark_read")
            self.assertGreaterEqual(plan["changeCount"], 1)
            self.assertEqual(plan["changeCount"] + plan["skipCount"], plan["totalMessages"])
            self.assertTrue(plan["safeMode"])

    def test_safe_mode_defaults_to_on(self) -> None:
        with self._client() as client:
            settings = client.get("/settings").json()
            self.assertTrue(settings["safeMode"])

    def test_invalid_action_is_rejected(self) -> None:
        with self._client() as client:
            job_id = self._make_job(client)
            response = client.post(f"/actions/jobs/{job_id}/apply", json={"action": "delete"})
            self.assertEqual(response.status_code, 400)

    def test_apply_mutates_and_is_undoable(self) -> None:
        with self._client() as client:
            self._set_safe_mode(client, False)
            job_id = self._make_job(client)
            response = client.post(f"/actions/jobs/{job_id}/apply", json={"action": "mark_read"})
            self.assertEqual(response.status_code, 200)
            body = response.json()
            self.assertTrue(body["applied"])
            self.assertGreaterEqual(len(body["changedIds"]), 1)

            logs = client.get("/logs").json()
            mark_log = next(item for item in logs if item["action"] == "mark_read")
            self.assertTrue(mark_log["undoable"])

    def test_safe_mode_does_not_mutate_and_pushes_no_undo(self) -> None:
        with self._client() as client:
            job_id = self._make_job(client)
            self._set_safe_mode(client, True)

            response = client.post(f"/actions/jobs/{job_id}/apply", json={"action": "mark_read"})
            self.assertEqual(response.status_code, 200)
            body = response.json()
            self.assertFalse(body["applied"])
            self.assertTrue(body["safeMode"])
            self.assertEqual(body["logId"], "")

            logs = client.get("/logs").json()
            mark_log = next(item for item in logs if item["action"] == "mark_read")
            self.assertEqual(mark_log["status"], "dry_run")
            self.assertFalse(mark_log["undoable"])

            # Messages remain unread, so a real apply still finds them to change.
            self._set_safe_mode(client, False)
            real = client.post(f"/actions/jobs/{job_id}/apply", json={"action": "mark_read"})
            self.assertEqual(real.status_code, 200)
            self.assertGreaterEqual(len(real.json()["changedIds"]), 1)

    def test_archive_action_is_undoable_in_sample_mailbox(self) -> None:
        with self._client() as client:
            self._set_safe_mode(client, False)
            job_id = self._make_job(client)
            preview = client.post(f"/actions/jobs/{job_id}/preview", json={"action": "archive"})
            self.assertEqual(preview.status_code, 200)
            self.assertEqual(preview.json()["targetMailbox"], "Archive")
            self.assertGreaterEqual(preview.json()["changeCount"], 1)

            apply_response = client.post(f"/actions/jobs/{job_id}/apply", json={"action": "archive"})
            self.assertEqual(apply_response.status_code, 200)
            self.assertTrue(apply_response.json()["applied"])
            self.assertGreaterEqual(len(apply_response.json()["changedIds"]), 1)

            logs = client.get("/logs").json()
            archive_log = next(item for item in logs if item["action"] == "archive")
            self.assertTrue(archive_log["undoable"])

            undo = client.post(f"/actions/undo/logs/{archive_log['id']}")
            self.assertEqual(undo.status_code, 200)

    def test_dry_run_flag_does_not_mutate(self) -> None:
        with self._client() as client:
            self._set_safe_mode(client, False)
            job_id = self._make_job(client)
            response = client.post(
                f"/actions/jobs/{job_id}/apply", json={"action": "mark_read", "dryRun": True})
            self.assertEqual(response.status_code, 200)
            body = response.json()
            self.assertFalse(body["applied"])

            real = client.post(f"/actions/jobs/{job_id}/apply", json={"action": "mark_read"})
            self.assertGreaterEqual(len(real.json()["changedIds"]), 1)

    def test_apply_uses_preview_changed_items_only(self) -> None:
        with self._client() as client:
            settings = client.get("/settings").json()
            settings["dummyMode"] = False
            settings["safeMode"] = False
            settings["mailAccounts"] = [{
                "id": "acct",
                "displayName": "Account",
                "enabled": True,
                "imapHost": "imap.example.com",
                "imapPort": 993,
                "imapUseSSL": True,
                "username": "user",
                "imapPassword": "pw",
                "archiveMailbox": "Archive",
                "indexMailboxes": ["INBOX"],
            }]
            self.assertEqual(client.post("/settings", json=settings).status_code, 200)
            messages = [
                {"id": "acct|INBOX|1", "subject": "Unread", "sender": "a@example.com", "date": "now"},
                {"id": "acct|INBOX|2", "subject": "Read", "sender": "b@example.com", "date": "now"},
            ]
            db.insert_job("job-scope", datetime.now().isoformat(timespec="seconds"), {},
                          5, "summary", messages)
            db.upsert_index_message({
                "id": "acct|INBOX|1",
                "accountId": "acct",
                "mailboxPath": "INBOX",
                "uid": "1",
                "subject": "Unread",
                "sender": "a@example.com",
                "recipients": [],
                "date": "now",
                "flags": [],
                "keywords": [],
            })
            db.upsert_index_message({
                "id": "acct|INBOX|2",
                "accountId": "acct",
                "mailboxPath": "INBOX",
                "uid": "2",
                "subject": "Read",
                "sender": "b@example.com",
                "recipients": [],
                "date": "now",
                "flags": ["\\Seen"],
                "keywords": [],
            })

            with mock.patch("backend.routers_actions.mark_messages_read",
                            return_value={"restore_unread_ids": ["acct|INBOX|1"],
                                          "failed_message_ids": []}) as patched:
                response = client.post("/actions/jobs/job-scope/apply", json={"action": "mark_read"})

            self.assertEqual(response.status_code, 200)
            patched.assert_called_once()
            self.assertEqual(patched.call_args.args[0], ["acct|INBOX|1"])
            body = response.json()
            self.assertEqual(body["changedIds"], ["acct|INBOX|1"])
            self.assertIn("acct|INBOX|2", body["skippedIds"])
            self.assertIn("\\Seen", db.get_index_message("acct|INBOX|1")["flags"])


if __name__ == "__main__":
    unittest.main()
