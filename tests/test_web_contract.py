from __future__ import annotations

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class WebContractTests(unittest.TestCase):
    def test_main_log_and_dummy_mode_copy_exist(self) -> None:
        html = (REPO_ROOT / "webapp" / "index.html").read_text(encoding="utf-8")
        self.assertIn(">Main<", html)
        self.assertIn(">Log<", html)
        self.assertIn('id="dummy-mode-toggle"', html)
        self.assertIn('id="test-connection"', html)

    def test_log_ui_uses_final_and_not_no_undo(self) -> None:
        app_js = (REPO_ROOT / "webapp" / "app.js").read_text(encoding="utf-8")
        self.assertIn("Final", app_js)
        self.assertNotIn("No undo", app_js)


if __name__ == "__main__":
    unittest.main()
