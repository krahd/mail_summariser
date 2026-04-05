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
        self.assertIn("Start Ollama automatically on startup", html)
        self.assertIn("Stop Ollama automatically on exit", html)
        self.assertIn("Stop Mail Summariser", html)
        self.assertIn("Reset Local Database", html)
        self.assertIn("Fake Mail Server", html)
        self.assertIn("Advanced Settings", html)
        self.assertIn("System Message", html)
        self.assertIn('id="reset-local-database"', html)
        self.assertIn('id="start-fake-mail"', html)
        self.assertIn('id="stop-fake-mail"', html)
        self.assertIn('id="use-fake-mail-settings"', html)
        self.assertIn('id="settings-basic-screen"', html)
        self.assertIn('id="settings-advanced-screen"', html)
        self.assertIn('id="open-advanced-settings"', html)
        self.assertIn('id="back-to-basic-settings"', html)
        self.assertIn('id="provider-system-message"', html)
        self.assertIn('id="reset-system-message"', html)

    def test_log_ui_uses_final_and_not_no_undo(self) -> None:
        app_js = (REPO_ROOT / "webapp" / "app.js").read_text(encoding="utf-8")
        self.assertIn("Final", app_js)
        self.assertNotIn("No undo", app_js)
        self.assertIn("shutdownRuntime", app_js)
        self.assertIn("resetDatabase", app_js)
        self.assertIn("startFakeMailServer", app_js)
        self.assertIn("stopFakeMailServer", app_js)
        self.assertIn("getSystemMessageDefaults", app_js)
        self.assertIn("showSettingsScreen", app_js)
        self.assertIn("providerSystemMessageFieldName", app_js)
        self.assertIn("runtime-startup-banner", (REPO_ROOT / "webapp" / "index.html").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
