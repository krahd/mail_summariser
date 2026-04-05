from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import app as backend_app
import db
import summary_service
from config import DEFAULT_SYSTEM_MESSAGES


class SystemMessageSettingsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        db.DB_PATH = Path(self.temp_dir.name) / "mail_summariser.sqlite3"
        self.original_defaults = backend_app.DEFAULT_SETTINGS.copy()
        backend_app._reset_dummy_sandbox()

    def tearDown(self) -> None:
        backend_app.DEFAULT_SETTINGS.clear()
        backend_app.DEFAULT_SETTINGS.update(self.original_defaults)
        backend_app._reset_dummy_sandbox()
        self.temp_dir.cleanup()

    def _client(self) -> TestClient:
        return TestClient(backend_app.app)

    def test_system_message_defaults_endpoint_returns_backend_defaults(self) -> None:
        with self._client() as client:
            response = client.get("/settings/system-message-defaults")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), DEFAULT_SYSTEM_MESSAGES)

    def test_settings_round_trip_includes_provider_system_messages(self) -> None:
        with self._client() as client:
            settings = client.get("/settings").json()
            settings["ollamaSystemMessage"] = "Local digest prompt"
            settings["openaiSystemMessage"] = "OpenAI digest prompt"
            settings["anthropicSystemMessage"] = "Anthropic digest prompt"

            save_response = client.post("/settings", json=settings)
            self.assertEqual(save_response.status_code, 200)

            refreshed = client.get("/settings").json()

        self.assertEqual(refreshed["ollamaSystemMessage"], "Local digest prompt")
        self.assertEqual(refreshed["openaiSystemMessage"], "OpenAI digest prompt")
        self.assertEqual(refreshed["anthropicSystemMessage"], "Anthropic digest prompt")

    def test_summary_service_uses_provider_specific_system_messages(self) -> None:
        messages = [
            {
                "id": "1",
                "subject": "Budget",
                "sender": "finance@example.com",
                "date": "2026-04-04",
                "body": "Please review the updated figures and confirm the follow-up plan.",
            }
        ]

        with mock.patch.object(summary_service, "_post_json", return_value={"choices": [{"message": {"content": "MAIL_SUMMARISER_VALID_V1\nDone"}}]}) as mocked_post:
            summary_service.summarize_messages(
                messages,
                5,
                settings={
                    "llmProvider": "openai",
                    "modelName": "gpt-4.1-mini",
                    "openaiApiKey": "key",
                    "openaiSystemMessage": "OpenAI custom system message",
                },
            )
        openai_payload = mocked_post.call_args.args[1]
        self.assertEqual(openai_payload["messages"][0]["content"], "OpenAI custom system message")

        with mock.patch.object(summary_service, "_post_json", return_value={"content": [{"type": "text", "text": "MAIL_SUMMARISER_VALID_V1\nDone"}]}) as mocked_post:
            summary_service.summarize_messages(
                messages,
                5,
                settings={
                    "llmProvider": "anthropic",
                    "modelName": "claude-3-5-haiku-latest",
                    "anthropicApiKey": "key",
                    "anthropicSystemMessage": "Anthropic custom system message",
                },
            )
        anthropic_payload = mocked_post.call_args.args[1]
        self.assertEqual(anthropic_payload["system"], "Anthropic custom system message")

        with (
            mock.patch.object(summary_service, "ensure_ollama_running", return_value=(True, "ok")),
            mock.patch.object(summary_service, "_post_json", return_value={"response": "MAIL_SUMMARISER_VALID_V1\nDone"}) as mocked_post,
        ):
            summary_service.summarize_messages(
                messages,
                5,
                settings={
                    "llmProvider": "ollama",
                    "modelName": "llama3.2:latest",
                    "ollamaHost": "http://127.0.0.1:11434",
                    "ollamaAutoStart": False,
                    "ollamaSystemMessage": "Ollama custom system message",
                },
            )
        ollama_payload = mocked_post.call_args.args[1]
        self.assertEqual(ollama_payload["system"], "Ollama custom system message")

    def test_summary_length_above_ten_is_accepted_and_more_detailed(self) -> None:
        messages = [
            {
                "id": "1",
                "subject": "Launch plan",
                "sender": "pm@example.com",
                "date": "2026-04-04",
                "body": "Need alignment on launch sequencing, pricing review, comms timing, and support coverage.",
            }
        ]

        summary_ten, meta_ten = summary_service.summarize_messages(
            messages,
            10,
            settings={"llmProvider": "openai", "openaiApiKey": ""},
        )
        summary_fifteen, meta_fifteen = summary_service.summarize_messages(
            messages,
            15,
            settings={"llmProvider": "openai", "openaiApiKey": ""},
        )

        self.assertEqual(meta_ten["status"], "fallback")
        self.assertEqual(meta_fifteen["status"], "fallback")
        self.assertGreater(len(summary_fifteen.splitlines()), len(summary_ten.splitlines()))

        with self._client() as client:
            response = client.post(
                "/summaries",
                json={
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
                    "summaryLength": 15,
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn("jobId", response.json())


if __name__ == "__main__":
    unittest.main()
