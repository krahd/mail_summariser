from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import app as backend_app
import db
import mail_service
from tests.support.fake_mail_server import FakeMailEnvironment


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


class BackendMailFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        db.DB_PATH = Path(self.temp_dir.name) / "mail_summariser.sqlite3"
        backend_app.DEFAULT_SETTINGS["ollamaAutoStart"] = False
        mail_service.reset_dummy_mailbox()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _client(self) -> TestClient:
        return TestClient(backend_app.app)

    def test_dummy_mode_connection_and_undo_flow(self) -> None:
        with self._client() as client:
            settings = client.get("/settings").json()
            self.assertTrue(settings["dummyMode"])

            connection = client.post("/settings/test-connection", json=settings)
            self.assertEqual(connection.status_code, 200)
            self.assertEqual(connection.json()["mode"], "dummy")

            summary = client.post("/summaries", json={**SUMMARY_PAYLOAD, "criteria": {**SUMMARY_PAYLOAD["criteria"], "keyword": "project"}})
            self.assertEqual(summary.status_code, 200)
            job_id = summary.json()["jobId"]

            self.assertEqual(client.post("/actions/mark-read", json={"jobId": job_id}).status_code, 200)
            self.assertEqual(client.post("/actions/tag-summarised", json={"jobId": job_id}).status_code, 200)

            logs = client.get("/logs").json()
            job_logs = [item for item in logs if item.get("job_id") == job_id]
            mark_log = next(item for item in job_logs if item["action"] == "mark_read")
            tag_log = next(item for item in job_logs if item["action"] == "tag_summarised")
            self.assertTrue(mark_log["undoable"])
            self.assertTrue(tag_log["undoable"])

            undo_response = client.post(f"/actions/undo/logs/{tag_log['id']}")
            self.assertEqual(undo_response.status_code, 200)

            logs_after_tag_undo = client.get("/logs").json()
            job_logs_after_tag_undo = [item for item in logs_after_tag_undo if item.get("job_id") == job_id]
            mark_log_after = next(item for item in job_logs_after_tag_undo if item["id"] == mark_log["id"])
            tag_log_after = next(item for item in job_logs_after_tag_undo if item["id"] == tag_log["id"])
            self.assertTrue(mark_log_after["undoable"])
            self.assertEqual(tag_log_after["undo_status"], "final")

            undo_mark_response = client.post(f"/actions/undo/logs/{mark_log['id']}")
            self.assertEqual(undo_mark_response.status_code, 200)

            restored = mail_service.search_messages(
                backend_app.SummaryRequest(**{**SUMMARY_PAYLOAD, "criteria": {**SUMMARY_PAYLOAD["criteria"], "keyword": "project"}}).criteria,
                {"dummyMode": True},
            )
            self.assertTrue(restored[0]["unread"])

    def test_real_imap_mode_end_to_end_with_fake_account(self) -> None:
        with FakeMailEnvironment() as environment, self._client() as client:
            save_response = client.post("/settings", json=environment.settings_payload)
            self.assertEqual(save_response.status_code, 200)

            masked_settings = client.get("/settings").json()
            self.assertEqual(masked_settings["imapPassword"], "__MASKED__")
            self.assertEqual(masked_settings["smtpPassword"], "__MASKED__")

            connection = client.post("/settings/test-connection", json=masked_settings)
            self.assertEqual(connection.status_code, 200)
            self.assertEqual(connection.json()["mode"], "imap")

            summary = client.post(
                "/summaries",
                json={**SUMMARY_PAYLOAD, "criteria": {**SUMMARY_PAYLOAD["criteria"], "keyword": "invoice"}},
            )
            self.assertEqual(summary.status_code, 200)
            payload = summary.json()
            self.assertEqual(len(payload["messages"]), 1)
            self.assertEqual(payload["messages"][0]["id"], "102")
            job_id = payload["jobId"]

            self.assertEqual(client.post("/actions/mark-read", json={"jobId": job_id}).status_code, 200)
            self.assertIn("\\Seen", environment.flags_for("102"))

            self.assertEqual(client.post("/actions/tag-summarised", json={"jobId": job_id}).status_code, 200)
            self.assertIn("summarised", environment.flags_for("102"))

            logs = client.get("/logs").json()
            job_logs = [item for item in logs if item.get("job_id") == job_id]
            mark_log = next(item for item in job_logs if item["action"] == "mark_read")
            tag_log = next(item for item in job_logs if item["action"] == "tag_summarised")

            self.assertEqual(client.post(f"/actions/undo/logs/{tag_log['id']}").status_code, 200)
            self.assertNotIn("summarised", environment.flags_for("102"))

            self.assertEqual(client.post(f"/actions/undo/logs/{mark_log['id']}").status_code, 200)
            self.assertNotIn("\\Seen", environment.flags_for("102"))

            email_response = client.post("/actions/email-summary", json={"jobId": job_id})
            self.assertEqual(email_response.status_code, 200)
            self.assertEqual(len(environment.sent_messages), 1)
            self.assertIn("Mail summary", environment.sent_messages[0]["subject"])

            latest_logs = client.get("/logs").json()
            email_log = next(item for item in latest_logs if item["action"] == "email_summary" and item.get("job_id") == job_id)
            self.assertEqual(email_log["undo_status"], "final")
            self.assertFalse(email_log["undoable"])

    def test_dummy_mode_toggle_endpoint_updates_settings(self) -> None:
        with self._client() as client:
            toggle_response = client.post("/settings/dummy-mode", json={"dummyMode": False})
            self.assertEqual(toggle_response.status_code, 200)
            self.assertFalse(toggle_response.json()["dummyMode"])

            settings = client.get("/settings").json()
            self.assertFalse(settings["dummyMode"])


if __name__ == "__main__":
    unittest.main()
