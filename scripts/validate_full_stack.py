from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen


def find_free_port(host: str) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as test_socket:
        test_socket.bind((host, 0))
        return int(test_socket.getsockname()[1])


def read_log_tail(log_path: Path | None, max_lines: int = 80) -> str:
    if log_path is None:
        return ""
    if not log_path.exists():
        return f"{log_path} does not exist."

    content = log_path.read_text(encoding="utf-8", errors="replace")
    lines = content.splitlines()
    if not lines:
        return f"{log_path} is empty."
    return "\n".join(lines[-max_lines:])


def build_wait_failure_message(
    url: str,
    last_error: BaseException | None,
    process: subprocess.Popen[bytes] | None = None,
    log_path: Path | None = None,
) -> str:
    message = f"Timed out waiting for {url}: {last_error}"
    if process is not None and process.poll() is not None:
        message += f"\nProcess exited with code {process.returncode}."
    if log_path is not None:
        message += f"\nLog tail ({log_path}):\n{read_log_tail(log_path)}"
    return message


def wait_for_url(
    url: str,
    attempts: int,
    delay_seconds: float,
    process: subprocess.Popen[bytes] | None = None,
    log_path: Path | None = None,
) -> None:
    last_error: Exception | None = None
    for attempt in range(attempts):
        if process is not None and process.poll() is not None:
            raise RuntimeError(build_wait_failure_message(url, last_error, process, log_path))
        try:
            with urlopen(url, timeout=2.0) as response:  # nosec B310
                if 200 <= response.status < 500:
                    return
        except (OSError, TimeoutError, URLError) as exc:
            last_error = exc
        if attempt + 1 < attempts:
            time.sleep(delay_seconds)
    raise RuntimeError(build_wait_failure_message(url, last_error, process, log_path))


def fetch_or_raise(url: str) -> None:
    with urlopen(url, timeout=5.0) as response:  # nosec B310
        if response.status >= 400:
            raise RuntimeError(f"Request failed for {url} with status {response.status}")


def terminate_process(process: subprocess.Popen[bytes] | None) -> None:
    if process is None:
        return
    if process.poll() is not None:
        return

    process.terminate()
    try:
        process.wait(timeout=8)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def main() -> int:
    parser = argparse.ArgumentParser(description="Cross-platform full-stack startup validation")
    parser.add_argument("--backend-host", default="127.0.0.1")
    parser.add_argument("--backend-port", type=int, default=8766)
    parser.add_argument("--web-port", type=int, default=0, help="Static web port. Use 0 to select a free port.")
    parser.add_argument("--attempts", type=int, default=40)
    parser.add_argument("--delay", type=float, default=1.0)
    args = parser.parse_args()

    root_dir = Path(__file__).resolve().parents[1]
    backend_url = f"http://{args.backend_host}:{args.backend_port}"
    web_host = "127.0.0.1"
    web_port = args.web_port if args.web_port else find_free_port(web_host)
    web_url = f"http://{web_host}:{web_port}"

    temp_dir = Path(tempfile.gettempdir())
    backend_log = temp_dir / "mail_summariser_backend.log"
    web_log = temp_dir / "mail_summariser_web.log"

    env = os.environ.copy()
    env["PYTHONPATH"] = str(root_dir)

    backend_proc: subprocess.Popen[bytes] | None = None
    web_proc: subprocess.Popen[bytes] | None = None

    try:
        with backend_log.open("wb") as backend_out:
            backend_proc = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "backend.app:app",
                    "--host",
                    args.backend_host,
                    "--port",
                    str(args.backend_port),
                ],
                cwd=root_dir,
                env=env,
                stdout=backend_out,
                stderr=subprocess.STDOUT,
            )

            wait_for_url(
                f"{backend_url}/health",
                attempts=args.attempts,
                delay_seconds=args.delay,
                process=backend_proc,
                log_path=backend_log,
            )
            fetch_or_raise(f"{backend_url}/health")
            fetch_or_raise(f"{backend_url}/runtime/status")
            fetch_or_raise(f"{backend_url}/models/options?provider=openai")
            fetch_or_raise(f"{backend_url}/models/catalog?limit=5")

        with web_log.open("wb") as web_out:
            web_proc = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "http.server",
                    str(web_port),
                    "--bind",
                    web_host,
                    "--directory",
                    "webapp",
                ],
                cwd=root_dir,
                env=env,
                stdout=web_out,
                stderr=subprocess.STDOUT,
            )

            wait_for_url(
                web_url,
                attempts=args.attempts,
                delay_seconds=args.delay,
                process=web_proc,
                log_path=web_log,
            )
            fetch_or_raise(web_url)

        print("Full-stack validation passed.")
        return 0
    finally:
        terminate_process(web_proc)
        terminate_process(backend_proc)


if __name__ == "__main__":
    raise SystemExit(main())
