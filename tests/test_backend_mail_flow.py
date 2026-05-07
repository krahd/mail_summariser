from __future__ import annotations
import sys
import tempfile
import unittest
import sqlite3
from pathlib import Path
from typing import Any, cast

from fastapi.testclient import TestClient

# backend modules are imported dynamically in setUp after sys.path is configured
try:
    from tests.support.fake_mail_server import FakeMailEnvironment
except Exception:
    from backend.fake_mail_server import FakeMailEnvironment


# Module-level placeholders for dynamically-imported backend modules
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


class BackendMailFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        # ensure backend path is on sys.path then import backend modules
        REPO_ROOT = Path(__file__).resolve().parents[1]
        BACKEND_DIR = REPO_ROOT / "backend"
        if str(BACKEND_DIR) not in sys.path:
            sys.path.insert(0, str(BACKEND_DIR))

        # import backend modules dynamically after sys.path has been configured
        import importlib
        globals()["mail_service"] = importlib.import_module("mail_service")
        globals()["dummy_state"] = importlib.import_module("dummy_state")
        globals()["db"] = importlib.import_module("db")
        globals()["backend_app"] = importlib.import_module("app")

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

    def _create_summary_and_get_job(self, client: TestClient, keyword: str) -> tuple[str, dict]:
        summary = client.post(
            "/summaries",
            json={**SUMMARY_PAYLOAD, "criteria": {**
                                                  SUMMARY_PAYLOAD["criteria"], "keyword": keyword}},
        )
        self.assertEqual(summary.status_code, 200)
        payload = summary.json()
        job_id = payload["jobId"]
        return job_id, payload

    def _perform_undo_checks(self, client: TestClient, job_id: str, payload: dict) -> None:
        # mark as read and tag summarised, then verify undo behavior
        self.assertEqual(client.post("/actions/mark-read", json={"jobId": job_id}).status_code, 200)
        self.assertEqual(client.post("/actions/tag-summarised",
                         json={"jobId": job_id}).status_code, 200)

        logs = client.get("/logs").json()
        job_logs = [item for item in logs if item.get("job_id") == job_id]
        mark_log = next(item for item in job_logs if item["action"] == "mark_read")
        tag_log = next(item for item in job_logs if item["action"] == "tag_summarised")
        self.assertTrue(mark_log["undoable"])
        self.assertTrue(tag_log["undoable"])

        undo_response = client.post(f"/actions/undo/logs/{tag_log['id']}")
        self.assertEqual(undo_response.status_code, 200)

        logs_after_tag_undo = client.get("/logs").json()
        job_logs_after_tag_undo = [
            item for item in logs_after_tag_undo if item.get("job_id") == job_id]
        mark_log_after = next(
            item for item in job_logs_after_tag_undo if item["id"] == mark_log["id"])
        tag_log_after = next(
            item for item in job_logs_after_tag_undo if item["id"] == tag_log["id"])
        self.assertTrue(mark_log_after["undoable"])
        self.assertEqual(tag_log_after["undo_status"], "final")

        undo_mark_response = client.post(f"/actions/undo/logs/{mark_log['id']}")
        self.assertEqual(undo_mark_response.status_code, 200)

        restored = mail_service.search_messages(
            backend_app.SummaryRequest(
                **{**SUMMARY_PAYLOAD, "criteria": {**SUMMARY_PAYLOAD["criteria"], "keyword": "project"}}
            ).criteria,
            {"dummyMode": True},
        )
        self.assertTrue(restored[0]["unread"])

    def _perform_imap_flow_checks(self, client: TestClient, environment: Any, job_id: str, payload: dict) -> None:
        self.assertEqual(len(payload["messages"]), 1)
        self.assertEqual(payload["messages"][0]["id"], "102")
        self.assertNotIn("body", payload["messages"][0])

        detail_response = client.get(f"/jobs/{job_id}/messages/{payload['messages'][0]['id']}")
        self.assertEqual(detail_response.status_code, 200)
        self.assertIn("invoice", detail_response.json()["body"].lower())

        self.assertEqual(client.post("/actions/mark-read", json={"jobId": job_id}).status_code, 200)
        self.assertIn("\\Seen", environment.flags_for("102"))

        self.assertEqual(client.post("/actions/tag-summarised",
                         json={"jobId": job_id}).status_code, 200)
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
        email_log = next(
            item for item in latest_logs if item["action"] == "email_summary" and item.get("job_id") == job_id
        )
        self.assertEqual(email_log["undo_status"], "final")
        self.assertFalse(email_log["undoable"])

    def _table_count(self, table_name: str) -> int:
        with sqlite3.connect(db.DB_PATH) as conn:
            row = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()
        return int(row[0]) if row is not None else 0

    def test_dummy_mode_connection_and_undo_flow(self) -> None:
        with self._client() as client:
            settings = client.get("/settings").json()
            self.assertTrue(settings["dummyMode"])

            connection = client.post("/settings/test-connection", json=settings)
            self.assertEqual(connection.status_code, 200)
            self.assertEqual(connection.json()["mode"], "dummy")
            job_id, payload = self._create_summary_and_get_job(client, "project")
            self.assertNotIn("body", payload["messages"][0])

            detail_response = client.get(f"/jobs/{job_id}/messages/{payload['messages'][0]['id']}")
            self.assertEqual(detail_response.status_code, 200)
            self.assertIn("deployment schedule", detail_response.json()["body"].lower())

            # perform mark/tag and undo checks in helper to reduce local variables
            self._perform_undo_checks(client, job_id, payload)

    def test_message_detail_endpoint_returns_404_for_unknown_job_or_message(self) -> None:
        with self._client() as client:
            summary = client.post(
                "/summaries", json={**SUMMARY_PAYLOAD, "criteria": {**SUMMARY_PAYLOAD["criteria"], "keyword": "project"}})
            self.assertEqual(summary.status_code, 200)
            payload = summary.json()
            job_id = payload["jobId"]

            missing_job = client.get(f"/jobs/missing-job/messages/{payload['messages'][0]['id']}")
            self.assertEqual(missing_job.status_code, 404)

            missing_message = client.get(f"/jobs/{job_id}/messages/missing-message")
            self.assertEqual(missing_message.status_code, 404)

        self.assertEqual(self._table_count("jobs"), 0)
        self.assertEqual(self._table_count("logs"), 0)
        self.assertEqual(self._table_count("undo_stack"), 0)

    def test_dummy_mode_jobs_are_invalidated_when_switching_to_live_mode(self) -> None:
        with self._client() as client:
            summary = client.post(
                "/summaries", json={**SUMMARY_PAYLOAD, "criteria": {**SUMMARY_PAYLOAD["criteria"], "keyword": "project"}})
            self.assertEqual(summary.status_code, 200)
            job_id = summary.json()["jobId"]

            toggle_response = client.post("/settings/dummy-mode", json={"dummyMode": False})
            self.assertEqual(toggle_response.status_code, 200)

            mark_response = client.post("/actions/mark-read", json={"jobId": job_id})
            self.assertEqual(mark_response.status_code, 404)

        self.assertEqual(dummy_state.dummy_store_counts()["jobs"], 0)

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

            job_id, payload = self._create_summary_and_get_job(client, "invoice")
            self._perform_imap_flow_checks(client, environment, job_id, payload)

    def test_tag_summarised_uses_saved_tag_in_live_mail(self) -> None:
        with FakeMailEnvironment() as environment, self._client() as client:
            save_response = client.post(
                "/settings",
                json={**environment.settings_payload, "summarisedTag": "reviewed"},
            )
            self.assertEqual(save_response.status_code, 200)

            job_id, payload = self._create_summary_and_get_job(client, "invoice")
            self.assertEqual(payload["messages"][0]["id"], "102")

            self.assertEqual(client.post("/actions/tag-summarised",
                             json={"jobId": job_id}).status_code, 200)
            self.assertIn("reviewed", environment.flags_for("102"))
            self.assertNotIn("summarised", environment.flags_for("102"))

            logs = client.get("/logs").json()
            job_logs = [item for item in logs if item.get("job_id") == job_id]
            tag_log = next(item for item in job_logs if item["action"] == "tag_summarised")

            self.assertEqual(client.post(f"/actions/undo/logs/{tag_log['id']}").status_code, 200)
            self.assertNotIn("reviewed", environment.flags_for("102"))

    def test_embedded_fake_mail_server_can_drive_live_mail_flow(self) -> None:
        backend_app.ENABLE_DEV_TOOLS = True
        with self._client() as client:
            start_response = client.post("/dev/fake-mail/start", json={})
            self.assertEqual(start_response.status_code, 200)
            status_payload = start_response.json()
            self.assertTrue(status_payload["running"])
            self.assertFalse(status_payload["suggestedSettings"]["dummyMode"])

            save_response = client.post("/settings", json=status_payload["suggestedSettings"])
            self.assertEqual(save_response.status_code, 200)

            connection = client.post("/settings/test-connection",
                                     json=status_payload["suggestedSettings"])
            self.assertEqual(connection.status_code, 200)
            self.assertEqual(connection.json()["mode"], "imap")

            summary = client.post(
                "/summaries",
                json={**SUMMARY_PAYLOAD, "criteria": {**
                                                      SUMMARY_PAYLOAD["criteria"], "keyword": "invoice"}},
            )
            self.assertEqual(summary.status_code, 200)
            job_id = summary.json()["jobId"]

            self.assertEqual(client.post("/actions/mark-read",
                             json={"jobId": job_id}).status_code, 200)
            self.assertEqual(client.post("/actions/tag-summarised",
                             json={"jobId": job_id}).status_code, 200)

            environment = cast(Any, backend_app._fake_mail_manager._environment)
            self.assertIsNotNone(environment)
            self.assertIn("\\Seen", environment.flags_for("102"))
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

            stop_response = client.post("/dev/fake-mail/stop", json={})
            self.assertEqual(stop_response.status_code, 200)
            self.assertFalse(stop_response.json()["running"])

    def test_dummy_mode_toggle_endpoint_updates_settings(self) -> None:
        with self._client() as client:
            toggle_response = client.post("/settings/dummy-mode", json={"dummyMode": False})
            self.assertEqual(toggle_response.status_code, 200)
            self.assertFalse(toggle_response.json()["dummyMode"])

            settings = client.get("/settings").json()
            self.assertFalse(settings["dummyMode"])


if __name__ == "__main__":
    unittest.main()
