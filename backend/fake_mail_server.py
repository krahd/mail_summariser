from __future__ import annotations

import base64
import socketserver
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.message import EmailMessage
from email.parser import BytesParser
from email.policy import default
from email.utils import format_datetime
from typing import Any

from config import DEFAULT_SYSTEM_MESSAGES
from uuid import uuid4


def _generated_identity() -> tuple[str, str, str]:
    suffix = uuid4().hex[:8]
    return (
        f"tester+{suffix}@example.com",
        f"fake-{uuid4().hex[:16]}",
        f"digest+{suffix}@example.com",
    )


@dataclass
class FakeMessage:
    uid: str
    subject: str
    sender: str
    recipient: str
    body: str
    date: datetime
    flags: set[str] = field(default_factory=set)

    def as_bytes(self) -> bytes:
        message = EmailMessage()
        message["Subject"] = self.subject
        message["From"] = self.sender
        message["To"] = self.recipient
        message["Date"] = format_datetime(self.date)
        message.set_content(self.body)
        return message.as_bytes()


class FakeMailState:
    def __init__(self, username: str, password: str, messages: list[FakeMessage]):
        self.username = username
        self.password = password
        self.messages = messages
        self.sent_messages: list[dict[str, Any]] = []
        self.lock = threading.Lock()

    def list_uids(self) -> list[str]:
        with self.lock:
            return [message.uid for message in self.messages]

    def get_message(self, uid: str) -> tuple[int, FakeMessage]:
        with self.lock:
            for index, message in enumerate(self.messages, start=1):
                if message.uid == uid:
                    return index, message
        raise KeyError(uid)

    def update_flags(self, uid: str, operation: str, flags: list[str]) -> None:
        _, message = self.get_message(uid)
        with self.lock:
            if operation.startswith("+FLAGS"):
                message.flags.update(flags)
            elif operation.startswith("-FLAGS"):
                message.flags.difference_update(flags)

    def message_flags(self, uid: str) -> set[str]:
        _, message = self.get_message(uid)
        with self.lock:
            return set(message.flags)

    def append_sent_message(self, raw_data: bytes) -> None:
        parsed = BytesParser(policy=default).parsebytes(raw_data)
        with self.lock:
            self.sent_messages.append(
                {
                    "subject": parsed.get("Subject", ""),
                    "from": parsed.get("From", ""),
                    "to": parsed.get("To", ""),
                    "body": parsed.get_body(preferencelist=("plain",)).get_content() if parsed.is_multipart() else parsed.get_content(),
                }
            )


class _ThreadedServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


class _IMAPHandler(socketserver.StreamRequestHandler):
    server: "_IMAPServer"

    def handle(self) -> None:
        self.authed = False
        self._write_line("* OK FakeMail IMAP ready")
        while True:
            raw = self.rfile.readline()
            if not raw:
                return
            line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
            if not line:
                continue

            parts = line.split(" ", 2)
            if len(parts) < 2:
                continue
            tag = parts[0]
            command = parts[1].upper()
            rest = parts[2] if len(parts) > 2 else ""

            if command == "CAPABILITY":
                self._write_line("* CAPABILITY IMAP4rev1 UIDPLUS")
                self._write_line(f"{tag} OK CAPABILITY completed")
                continue

            if command == "LOGIN":
                username, password = self._parse_login_args(rest)
                if username == self.server.state.username and password == self.server.state.password:
                    self.authed = True
                    self._write_line(f"{tag} OK LOGIN completed")
                else:
                    self._write_line(f"{tag} NO LOGIN failed")
                continue

            if command in {"SELECT", "EXAMINE"}:
                count = len(self.server.state.list_uids())
                self._write_line(f"* {count} EXISTS")
                mode = "READ-ONLY" if command == "EXAMINE" else "READ-WRITE"
                self._write_line(f"{tag} OK [{mode}] {command} completed")
                continue

            if command == "NOOP":
                self._write_line(f"{tag} OK NOOP completed")
                continue

            if command == "LOGOUT":
                self._write_line("* BYE FakeMail IMAP signing off")
                self._write_line(f"{tag} OK LOGOUT completed")
                return

            if command == "UID":
                self._handle_uid_command(tag, rest)
                continue

            self._write_line(f"{tag} BAD unsupported command")

    def _handle_uid_command(self, tag: str, rest: str) -> None:
        parts = rest.split(" ", 2)
        if len(parts) < 2:
            self._write_line(f"{tag} BAD malformed UID command")
            return
        subcommand = parts[0].upper()
        target = parts[1]
        tail = parts[2] if len(parts) > 2 else ""

        if subcommand == "SEARCH":
            uids = " ".join(self.server.state.list_uids())
            self._write_line(f"* SEARCH {uids}".rstrip())
            self._write_line(f"{tag} OK SEARCH completed")
            return

        if subcommand == "FETCH":
            sequence, message = self.server.state.get_message(target)
            flags = " ".join(sorted(message.flags))
            if "BODY.PEEK[]" in tail or "BODY[]" in tail:
                raw = message.as_bytes()
                header = f"* {sequence} FETCH (UID {message.uid} FLAGS ({flags}) BODY[] {{{len(raw)}}}"
                self.wfile.write(header.encode("utf-8") + b"\r\n")
                self.wfile.write(raw)
                self.wfile.write(b")\r\n")
            else:
                self._write_line(f"* {sequence} FETCH (UID {message.uid} FLAGS ({flags}))")
            self._write_line(f"{tag} OK FETCH completed")
            return

        if subcommand == "STORE":
            operation = tail.split(" ", 1)[0]
            flag_text = tail.split(" ", 1)[1] if " " in tail else ""
            flags = [item for item in flag_text.strip().strip("()").split() if item]
            self.server.state.update_flags(target, operation, flags)
            self._write_line(f"{tag} OK STORE completed")
            return

        self._write_line(f"{tag} BAD unsupported UID command")

    def _parse_login_args(self, rest: str) -> tuple[str, str]:
        parts = [item.strip().strip('"') for item in rest.split(" ", 1)]
        if len(parts) != 2:
            return "", ""
        return parts[0], parts[1]

    def _write_line(self, text: str) -> None:
        self.wfile.write(text.encode("utf-8") + b"\r\n")


class _SMTPHandler(socketserver.StreamRequestHandler):
    server: "_SMTPServer"

    def handle(self) -> None:
        self._write_line("220 FakeMail SMTP ready")

        while True:
            raw = self.rfile.readline()
            if not raw:
                return
            line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
            upper = line.upper()

            if upper.startswith("EHLO") or upper.startswith("HELO"):
                self._write_line("250-fakemail.local")
                self._write_line("250 AUTH PLAIN LOGIN")
                continue

            if upper.startswith("AUTH PLAIN"):
                encoded = line.split(" ", 2)[2] if len(line.split(" ", 2)) == 3 else ""
                username, password = self._decode_auth_plain(encoded)
                if username == self.server.state.username and password == self.server.state.password:
                    self._write_line("235 Authentication successful")
                else:
                    self._write_line("535 Authentication failed")
                continue

            if upper == "AUTH LOGIN":
                self._write_line("334 VXNlcm5hbWU6")
                username = base64.b64decode(self.rfile.readline().strip()).decode("utf-8", errors="replace")
                self._write_line("334 UGFzc3dvcmQ6")
                password = base64.b64decode(self.rfile.readline().strip()).decode("utf-8", errors="replace")
                if username == self.server.state.username and password == self.server.state.password:
                    self._write_line("235 Authentication successful")
                else:
                    self._write_line("535 Authentication failed")
                continue

            if upper.startswith("MAIL FROM:"):
                self._write_line("250 Sender OK")
                continue

            if upper.startswith("RCPT TO:"):
                self._write_line("250 Recipient OK")
                continue

            if upper == "DATA":
                self._write_line("354 End data with <CR><LF>.<CR><LF>")
                data_lines: list[bytes] = []
                while True:
                    data_line = self.rfile.readline()
                    if data_line in {b".\r\n", b".\n", b"."}:
                        break
                    data_lines.append(data_line)
                self.server.state.append_sent_message(b"".join(data_lines))
                self._write_line("250 Message accepted for delivery")
                continue

            if upper == "NOOP":
                self._write_line("250 NOOP OK")
                continue

            if upper == "RSET":
                self._write_line("250 Reset OK")
                continue

            if upper == "QUIT":
                self._write_line("221 Bye")
                return

            self._write_line("250 OK")

    def _decode_auth_plain(self, encoded: str) -> tuple[str, str]:
        if not encoded:
            return "", ""
        raw = base64.b64decode(encoded).decode("utf-8", errors="replace")
        _, username, password = raw.split("\x00", 2)
        return username, password

    def _write_line(self, text: str) -> None:
        self.wfile.write(text.encode("utf-8") + b"\r\n")


class _IMAPServer(_ThreadedServer):
    def __init__(self, address: tuple[str, int], state: FakeMailState):
        super().__init__(address, _IMAPHandler)
        self.state = state


class _SMTPServer(_ThreadedServer):
    def __init__(self, address: tuple[str, int], state: FakeMailState):
        super().__init__(address, _SMTPHandler)
        self.state = state


class FakeMailEnvironment:
    def __init__(
        self,
        *,
        username: str | None = None,
        password: str | None = None,
        recipient_email: str | None = None,
        messages: list[FakeMessage] | None = None,
    ) -> None:
        generated_username, generated_password, generated_recipient = _generated_identity()
        self.username = username or generated_username
        self.password = password or generated_password
        self.recipient_email = recipient_email or generated_recipient
        self.state = FakeMailState(
            username=self.username,
            password=self.password,
            messages=messages
            or [
                FakeMessage(
                    uid="101",
                    subject="Quarterly project update",
                    sender="alice@example.com",
                    recipient=self.username,
                    body="Budget is approved. Please review the launch checklist by Friday.",
                    date=datetime(2026, 4, 1, 15, 0, tzinfo=timezone.utc),
                    flags=set(),
                ),
                FakeMessage(
                    uid="102",
                    subject="Invoice follow-up",
                    sender="finance@example.com",
                    recipient=self.username,
                    body="Can you confirm whether the April invoice is ready to send?",
                    date=datetime(2026, 4, 2, 9, 30, tzinfo=timezone.utc),
                    flags={"\\Answered"},
                ),
            ],
        )
        self.imap_server = _IMAPServer(("127.0.0.1", 0), self.state)
        self.smtp_server = _SMTPServer(("127.0.0.1", 0), self.state)
        self._threads: list[threading.Thread] = []
        self._running = False

    def start(self) -> "FakeMailEnvironment":
        if self._running:
            return self
        for server in (self.imap_server, self.smtp_server):
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            self._threads.append(thread)
        self._running = True
        return self

    def stop(self) -> None:
        if not self._running:
            return
        for server in (self.imap_server, self.smtp_server):
            server.shutdown()
            server.server_close()
        for thread in self._threads:
            thread.join(timeout=1)
        self._threads = []
        self._running = False

    def __enter__(self) -> "FakeMailEnvironment":
        return self.start()

    def __exit__(self, exc_type, exc, tb) -> None:
        self.stop()

    @property
    def settings_payload(self) -> dict[str, Any]:
        return {
            "dummyMode": False,
            "imapHost": "127.0.0.1",
            "imapPort": self.imap_server.server_address[1],
            "imapUseSSL": False,
            "imapPassword": self.password,
            "smtpHost": "127.0.0.1",
            "smtpPort": self.smtp_server.server_address[1],
            "smtpUseSSL": False,
            "smtpPassword": self.password,
            "username": self.username,
            "recipientEmail": self.recipient_email,
            "summarisedTag": "summarised",
            "llmProvider": "ollama",
            "openaiApiKey": "",
            "anthropicApiKey": "",
            "ollamaHost": "http://127.0.0.1:11434",
            "ollamaAutoStart": False,
            "ollamaStartOnStartup": False,
            "ollamaStopOnExit": False,
            "ollamaSystemMessage": DEFAULT_SYSTEM_MESSAGES["ollamaSystemMessage"],
            "openaiSystemMessage": DEFAULT_SYSTEM_MESSAGES["openaiSystemMessage"],
            "anthropicSystemMessage": DEFAULT_SYSTEM_MESSAGES["anthropicSystemMessage"],
            "modelName": "llama3.2:latest",
            "backendBaseURL": "http://127.0.0.1:8766",
        }

    def status_payload(self, backend_base_url: str = "http://127.0.0.1:8766") -> dict[str, Any]:
        if not self._running:
            return {
                "enabled": True,
                "running": False,
                "message": "Developer fake mail server is not running.",
                "imapHost": "127.0.0.1",
                "imapPort": 0,
                "smtpHost": "127.0.0.1",
                "smtpPort": 0,
                "username": "",
                "password": "",
                "recipientEmail": "",
                "suggestedSettings": None,
            }

        suggested = self.settings_payload | {"backendBaseURL": backend_base_url}
        return {
            "enabled": True,
            "running": True,
            "message": "Developer fake mail server is running on localhost.",
            "imapHost": "127.0.0.1",
            "imapPort": self.imap_server.server_address[1],
            "smtpHost": "127.0.0.1",
            "smtpPort": self.smtp_server.server_address[1],
            "username": self.username,
            "password": self.password,
            "recipientEmail": self.recipient_email,
            "suggestedSettings": suggested,
        }

    def flags_for(self, uid: str) -> set[str]:
        return self.state.message_flags(uid)

    @property
    def sent_messages(self) -> list[dict[str, Any]]:
        return list(self.state.sent_messages)


class FakeMailServerManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._environment: FakeMailEnvironment | None = None

    def status(self, enabled: bool, backend_base_url: str = "http://127.0.0.1:8766") -> dict[str, Any]:
        with self._lock:
            environment = self._environment
        if not enabled:
            return {
                "enabled": False,
                "running": False,
                "message": "Developer fake mail server is disabled.",
                "imapHost": "127.0.0.1",
                "imapPort": 0,
                "smtpHost": "127.0.0.1",
                "smtpPort": 0,
                "username": "",
                "password": "",
                "recipientEmail": "",
                "suggestedSettings": None,
            }
        if environment is None:
            return {
                "enabled": True,
                "running": False,
                "message": "Developer fake mail server is available but not running.",
                "imapHost": "127.0.0.1",
                "imapPort": 0,
                "smtpHost": "127.0.0.1",
                "smtpPort": 0,
                "username": "",
                "password": "",
                "recipientEmail": "",
                "suggestedSettings": None,
            }
        return environment.status_payload(backend_base_url)

    def start(self, enabled: bool, backend_base_url: str = "http://127.0.0.1:8766") -> dict[str, Any]:
        if not enabled:
            raise RuntimeError("Developer fake mail server is disabled.")
        with self._lock:
            if self._environment is None:
                self._environment = FakeMailEnvironment().start()
            return self._environment.status_payload(backend_base_url)

    def stop(self, enabled: bool, backend_base_url: str = "http://127.0.0.1:8766") -> dict[str, Any]:
        if not enabled:
            raise RuntimeError("Developer fake mail server is disabled.")
        with self._lock:
            environment = self._environment
            if environment is None:
                return {
                    "enabled": True,
                    "running": False,
                    "message": "Developer fake mail server is already stopped.",
                    "imapHost": "127.0.0.1",
                    "imapPort": 0,
                    "smtpHost": "127.0.0.1",
                    "smtpPort": 0,
                    "username": "",
                    "password": "",
                    "recipientEmail": "",
                    "suggestedSettings": None,
                }
            environment.stop()
            self._environment = None
        return {
            "enabled": True,
            "running": False,
            "message": "Developer fake mail server stopped.",
            "imapHost": "127.0.0.1",
            "imapPort": 0,
            "smtpHost": "127.0.0.1",
            "smtpPort": 0,
            "username": "",
            "password": "",
            "recipientEmail": "",
            "suggestedSettings": None,
        }

    def shutdown(self) -> None:
        with self._lock:
            environment = self._environment
            self._environment = None
        if environment is not None:
            environment.stop()
