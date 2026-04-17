from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from itertools import count

_next_port = count(41000)
REGISTRY: dict[tuple[str, int], 'FakeMailEnvironment'] = {}


@dataclass
class _StubServer:
    host: str
    port: int

    @property
    def server_address(self) -> tuple[str, int]:
        return (self.host, self.port)


class FakeMailEnvironment:
    def __init__(self) -> None:
        self.host = '127.0.0.1'
        self.imap_server = _StubServer(self.host, next(_next_port))
        self.smtp_server = _StubServer(self.host, next(_next_port))
        self.username = 'fake-user@example.com'
        self.password = 'fake-password'
        self.recipient_email = 'recipient@example.com'
        self.messages = {
            '101': {
                'id': '101', 'subject': 'Project deployment schedule', 'sender': 'pm@example.com', 'recipient': self.username,
                'date': '2026-04-01T09:00:00Z', 'body': 'The deployment schedule changed. Review milestones and confirm by Friday.',
                'flags': set(),
            },
            '102': {
                'id': '102', 'subject': 'Invoice due this week', 'sender': 'billing@example.com', 'recipient': self.username,
                'date': '2026-04-02T12:00:00Z', 'body': 'Invoice 2048 is due on Thursday. Please review the attached invoice totals.',
                'flags': set(),
            },
        }
        self.sent_messages: list[dict[str, str]] = []
        self.settings_payload = {
            'dummyMode': False,
            'imapHost': self.host,
            'imapPort': self.imap_server.port,
            'imapUseSSL': False,
            'imapPassword': self.password,
            'smtpHost': self.host,
            'smtpPort': self.smtp_server.port,
            'smtpUseSSL': False,
            'smtpPassword': self.password,
            'username': self.username,
            'recipientEmail': self.recipient_email,
            'summarisedTag': 'summarised',
            'llmProvider': 'ollama',
            'openaiApiKey': '',
            'anthropicApiKey': '',
            'ollamaHost': 'http://127.0.0.1:11434',
            'ollamaAutoStart': False,
            'ollamaStartOnStartup': False,
            'ollamaStopOnExit': False,
            'ollamaSystemMessage': 'You create compact, practical email digests that focus on priorities, deadlines, and follow-up actions.',
            'openaiSystemMessage': 'You are an assistant that creates compact, practical email digests.',
            'anthropicSystemMessage': 'You create practical, concise email summaries with action cues.',
            'modelName': 'llama3.2:latest',
            'backendBaseURL': 'http://127.0.0.1:8766',
        }

    def start(self):
        REGISTRY[(self.host, self.imap_server.port)] = self
        REGISTRY[(self.host, self.smtp_server.port)] = self
        return self

    def stop(self) -> None:
        REGISTRY.pop((self.host, self.imap_server.port), None)
        REGISTRY.pop((self.host, self.smtp_server.port), None)

    def __enter__(self):
        return self.start()

    def __exit__(self, exc_type, exc, tb):
        self.stop()
        return False

    def flags_for(self, message_id: str) -> set[str]:
        return set(self.messages[message_id]['flags'])

    def list_messages(self) -> list[dict]:
        return [deepcopy(v) for v in self.messages.values()]
