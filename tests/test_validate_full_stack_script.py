from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from scripts import validate_full_stack


class FakeSocket:
    def __init__(self) -> None:
        self.bound_address: tuple[str, int] | None = None

    def __enter__(self) -> "FakeSocket":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def bind(self, address: tuple[str, int]) -> None:
        self.bound_address = address

    def getsockname(self) -> tuple[str, int]:
        return ("127.0.0.1", 54321)


class FakeProcess:
    def __init__(self, returncode: int | None) -> None:
        self.returncode = returncode

    def poll(self) -> int | None:
        return self.returncode


class ValidateFullStackScriptTests(unittest.TestCase):
    def test_find_free_port_asks_os_for_loopback_port(self) -> None:
        fake_socket = FakeSocket()

        with patch.object(validate_full_stack.socket, "socket", return_value=fake_socket):
            port = validate_full_stack.find_free_port("127.0.0.1")

        self.assertEqual(port, 54321)
        self.assertEqual(fake_socket.bound_address, ("127.0.0.1", 0))

    def test_read_log_tail_limits_lines(self) -> None:
        with TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "service.log"
            log_path.write_text("one\ntwo\nthree\n", encoding="utf-8")

            self.assertEqual(validate_full_stack.read_log_tail(log_path, max_lines=2), "two\nthree")

    def test_wait_for_url_reports_exited_process_and_log_tail(self) -> None:
        with TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "web.log"
            log_path.write_text("first line\nlast line\n", encoding="utf-8")

            with self.assertRaises(RuntimeError) as context:
                validate_full_stack.wait_for_url(
                    "http://127.0.0.1:8000",
                    attempts=1,
                    delay_seconds=0,
                    process=FakeProcess(returncode=48),  # type: ignore[arg-type]
                    log_path=log_path,
                )

            message = str(context.exception)
            self.assertIn("Timed out waiting for http://127.0.0.1:8000", message)
            self.assertIn("Process exited with code 48.", message)
            self.assertIn("last line", message)


if __name__ == "__main__":
    unittest.main()
