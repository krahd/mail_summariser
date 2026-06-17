"""Preview / apply action API: dry-run, safe-mode, and undo behaviour."""

from __future__ import annotations

import importlib
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

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

    def test_invalid_action_is_rejected(self) -> None:
        with self._client() as client:
            job_id = self._make_job(client)
            response = client.post(f"/actions/jobs/{job_id}/apply", json={"action": "delete"})
            self.assertEqual(response.status_code, 400)

    def test_apply_mutates_and_is_undoable(self) -> None:
        with self._client() as client:
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

    def test_dry_run_flag_does_not_mutate(self) -> None:
        with self._client() as client:
            job_id = self._make_job(client)
            response = client.post(
                f"/actions/jobs/{job_id}/apply", json={"action": "mark_read", "dryRun": True})
            self.assertEqual(response.status_code, 200)
            body = response.json()
            self.assertFalse(body["applied"])

            real = client.post(f"/actions/jobs/{job_id}/apply", json={"action": "mark_read"})
            self.assertGreaterEqual(len(real.json()["changedIds"]), 1)


if __name__ == "__main__":
    unittest.main()
