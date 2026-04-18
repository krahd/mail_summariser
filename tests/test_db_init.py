from __future__ import annotations
import sys
import sqlite3
import tempfile
import unittest
from pathlib import Path
from typing import Any


# Module-level placeholder for dynamically-imported backend module
db: Any = None

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


class DatabaseInitTests(unittest.TestCase):
    def setUp(self) -> None:
        # import backend module dynamically after sys.path has been configured
        import importlib
        globals()["db"] = importlib.import_module("db")

        self.original_db_path = db.DB_PATH
        self.temp_dir = tempfile.TemporaryDirectory()

    def tearDown(self) -> None:
        db.DB_PATH = self.original_db_path
        self.temp_dir.cleanup()

    def test_init_db_creates_missing_parent_dir_and_database_file(self) -> None:
        db.DB_PATH = Path(self.temp_dir.name) / "nested" / "runtime" / "mail_summariser.sqlite3"

        self.assertFalse(db.DB_PATH.exists())
        self.assertFalse(db.DB_PATH.parent.exists())

        db.init_db()

        self.assertTrue(db.DB_PATH.parent.exists())
        self.assertTrue(db.DB_PATH.exists())

        with sqlite3.connect(db.DB_PATH) as conn:
            table_names = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }

        self.assertTrue({"settings", "logs", "jobs", "undo_stack"}.issubset(table_names))


if __name__ == "__main__":
    unittest.main()
