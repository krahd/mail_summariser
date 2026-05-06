from __future__ import annotations

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class WebContractTests(unittest.TestCase):
    def test_main_log_and_dummy_mode_copy_exist(self) -> None:
        html = (REPO_ROOT / "webapp" / "index.html").read_text(encoding="utf-8")
        self.assertIn(">Main<", html)
        self.assertIn(">Log<", html)
        self.assertIn('id="status-line"', html)
        self.assertIn('id="help-button"', html)
        self.assertIn('class="help-btn-glyph"', html)
        self.assertIn('id="dummy-mode-toggle"', html)
        self.assertIn('id="test-connection"', html)
        self.assertIn("Start Ollama automatically on startup", html)
        self.assertIn("Stop Ollama automatically on exit", html)
        self.assertIn("Stop mail_summariser", html)
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
        self.assertIn('class="review-split"', html)
        self.assertIn('id="message-detail-shell"', html)
        self.assertIn('id="message-detail-body"', html)
        self.assertIn('id="messages-summary"', html)
        self.assertIn('id="quick-filters"', html)
        self.assertIn('id="apply-scope-actions"', html)
        self.assertIn('id="scope-action-mark-read"', html)
        self.assertIn('id="scope-action-tag"', html)
        self.assertIn('id="scope-action-email"', html)
        self.assertIn('id="workspace-health-strip"', html)
        self.assertIn('id="health-mode"', html)
        self.assertIn('id="health-provider"', html)
        self.assertIn('id="health-runtime"', html)
        self.assertIn('id="health-sync"', html)
        self.assertIn('id="digest-metric-messages"', html)
        self.assertIn('id="digest-metric-selected"', html)
        self.assertIn('id="digest-metric-filter"', html)
        self.assertIn('id="log-search"', html)
        self.assertIn('id="log-status-filter"', html)
        self.assertIn('id="log-undo-only"', html)
        self.assertIn('id="logs-count"', html)
        self.assertIn('id="diag-provider-state"', html)
        self.assertIn('id="diag-runtime-state"', html)
        self.assertIn('id="diag-fakemail-state"', html)
        self.assertNotIn("Narrow the mailbox slice before you create a digest.", html)

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
        self.assertIn("updateHealthStrip", app_js)
        self.assertIn("updateDiagnosticsSummary", app_js)
        self.assertIn("filteredLogs", app_js)
        self.assertIn("refreshLogTimeline", app_js)
        self.assertIn("applyQuickFilter", app_js)
        self.assertIn("updateActionScopePreview", app_js)
        self.assertIn("updateDigestMetrics", app_js)
        self.assertIn("getMessageDetail", (REPO_ROOT / "webapp" /
                      "api.js").read_text(encoding="utf-8"))
        self.assertIn("Loading message body...", app_js)
        self.assertIn("message-detail-shell", (REPO_ROOT / "webapp" /
                      "index.html").read_text(encoding="utf-8"))
        self.assertIn("runtime-startup-banner", (REPO_ROOT / "webapp" /
                      "index.html").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
