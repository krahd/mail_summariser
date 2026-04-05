from __future__ import annotations

import sqlite3
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
import dummy_state


class DatabaseResetTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_defaults = backend_app.DEFAULT_SETTINGS.copy()
        self.original_dev_tools_enabled = backend_app.ENABLE_DEV_TOOLS
        db.DB_PATH = Path(self.temp_dir.name) / "mail_summariser.sqlite3"
        backend_app.ENABLE_DEV_TOOLS = False
        backend_app._backend_shutdown_requested = False
        backend_app._fake_mail_manager.shutdown()
        backend_app._reset_dummy_sandbox()

    def tearDown(self) -> None:
        backend_app.DEFAULT_SETTINGS.clear()
        backend_app.DEFAULT_SETTINGS.update(self.original_defaults)
        backend_app.ENABLE_DEV_TOOLS = self.original_dev_tools_enabled
        backend_app._backend_shutdown_requested = False
        backend_app._fake_mail_manager.shutdown()
        backend_app._reset_dummy_sandbox()
        self.temp_dir.cleanup()

    def _client(self) -> TestClient:
        return TestClient(backend_app.app)

    def _table_count(self, table_name: str) -> int:
        with sqlite3.connect(db.DB_PATH) as conn:
            row = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()
        return int(row[0]) if row is not None else 0

    def test_admin_database_reset_wipes_rows_and_reseeds_defaults(self) -> None:
        with self._client() as client:
            self.assertEqual(client.get("/settings").status_code, 200)

        db.set_setting("llmApiKey", "legacy-shared-key")
        db.insert_log("log-reset", "2026-04-04T12:00:00", "manual", "ok", "Seeded reset test")
        db.insert_job(
            "job-reset",
            "2026-04-04T12:00:01",
            {"mailContext": {"dummyMode": False}},
            5,
            "Seed summary",
            [{"id": "m-1", "subject": "Seed", "sender": "seed@example.com", "date": "2026-04-04T12:00:00"}],
        )
        db.push_undo({"type": "mark_read", "log_id": "log-reset"}, "2026-04-04T12:00:02")
        dummy_state.insert_job(
            "dummy-job",
            "2026-04-04T12:01:00",
            {"mailContext": {"dummyMode": True}},
            5,
            "Dummy summary",
            [{"id": "msg-001", "subject": "Project update", "sender": "alice@example.com", "date": "2026-03-10T09:00:00"}],
        )
        dummy_state.insert_log("dummy-log", "2026-04-04T12:01:01", "create_summary", "ok", "Dummy log", "dummy-job")
        dummy_state.push_undo({"type": "mark_read", "log_id": "dummy-log"}, "2026-04-04T12:01:02")

        with self._client() as client:
            response = client.post("/admin/database/reset", json={"confirmation": "RESET DATABASE"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["removed"]["logs"], 1)
        self.assertEqual(payload["removed"]["jobs"], 1)
        self.assertEqual(payload["removed"]["undo"], 1)
        self.assertNotIn("llmApiKey", db.list_settings())
        self.assertEqual(db.list_settings(), backend_app.DEFAULT_SETTINGS)
        self.assertEqual(self._table_count("logs"), 0)
        self.assertEqual(self._table_count("jobs"), 0)
        self.assertEqual(self._table_count("undo_stack"), 0)
        self.assertEqual(dummy_state.dummy_store_counts()["jobs"], 0)
        self.assertEqual(dummy_state.dummy_store_counts()["logs"], 0)
        self.assertEqual(dummy_state.dummy_store_counts()["undo"], 0)
        self.assertEqual(payload["settings"]["dummyMode"], backend_app.DEFAULT_SETTINGS["dummyMode"])

    def test_admin_database_reset_requires_confirmation_phrase(self) -> None:
        with self._client() as client:
            response = client.post("/admin/database/reset", json={"confirmation": "reset"})

        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
