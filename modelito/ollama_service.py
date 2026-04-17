"""
modelito.ollama_service

Lightweight Ollama lifecycle and HTTP helper utilities.

Provides: resolve_ollama_command, run_ollama_command, start_detached_ollama_serve,
wait_until_ready, preload_model, start_service, stop_service, server_is_up,
and small HTTP helpers. This implementation aims to be a compact, dependency-
minimal subset of BatLLM's Ollama helpers so `modelito` can manage local
Ollama instances when available.
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
import time
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

try:
    import psutil
except Exception:  # pragma: no cover - optional
    psutil = None


ROOT = Path(__file__).resolve().parents[1]


def endpoint_url(url: str, port: int, path: str) -> str:
    return f"{url.rstrip('/')}:{port}{path}"


def json_get(url: str, timeout: float = 5.0) -> Dict[str, Any]:
    with urlopen(url, timeout=timeout) as response:
        body = response.read().decode("utf-8")
    return json.loads(body) if body else {}


def json_post(url: str, payload: Dict[str, Any], timeout: float = 60.0) -> Dict[str, Any]:
    request = Request(url, data=json.dumps(payload).encode("utf-8"),
                      headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(request, timeout=timeout) as response:
        body = response.read().decode("utf-8")
    return json.loads(body) if body else {}


def server_is_up(url: str, port: int) -> bool:
    try:
        json_get(endpoint_url(url, port, "/api/version"), timeout=2.0)
        return True
    except (URLError, HTTPError, ValueError):
        return False


def resolve_ollama_command() -> str:
    discovered = shutil.which("ollama")
    if discovered:
        return str(Path(discovered))

    candidates: List[Path] = []
    if os.name == "nt":
        local_appdata = os.environ.get("LOCALAPPDATA")
        if local_appdata:
            candidates.append(Path(local_appdata) / "Programs" / "Ollama" / "ollama.exe")
        candidates.append(Path.home() / "AppData" / "Local" / "Programs" / "Ollama" / "ollama.exe")
    elif sys.platform == "darwin":
        candidates.extend([
            Path("/Applications/Ollama.app/Contents/Resources/ollama"),
            Path("/Applications/Ollama.app/Contents/MacOS/Ollama"),
            Path("/usr/local/bin/ollama"),
            Path("/opt/homebrew/bin/ollama"),
        ])
    else:
        candidates.extend([Path("/usr/local/bin/ollama"),
                          Path("/usr/bin/ollama"), Path("/bin/ollama")])

    for c in candidates:
        if c.exists():
            return str(c)
    raise FileNotFoundError("ollama")


def ollama_installed() -> bool:
    try:
        resolve_ollama_command()
    except FileNotFoundError:
        return False
    return True


def run_ollama_command(*args: str, host: Optional[str] = None, cwd: Optional[Path] = None, timeout: Optional[float] = None) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    if host:
        env["OLLAMA_HOST"] = host
    command = resolve_ollama_command()
    return subprocess.run([command, *args], cwd=str(cwd) if cwd is not None else None, text=True, capture_output=True, check=False, env=env, timeout=timeout)


def start_detached_ollama_serve(host: str, cwd: Optional[Path] = None) -> subprocess.Popen:
    command = resolve_ollama_command()
    env = {**os.environ, "OLLAMA_HOST": host}
    kwargs: Dict[str, Any] = {
        "cwd": str(cwd) if cwd is not None else str(ROOT),
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "stdin": subprocess.DEVNULL,
        "env": env,
        "text": True,
    }
    if os.name == "nt":
        kwargs["creationflags"] = (subprocess.DETACHED_PROCESS |
                                   subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW)
    else:
        kwargs["start_new_session"] = True

    return subprocess.Popen([command, "serve"], **kwargs)


def wait_until_ready(url: str, port: int, timeout_seconds: float = 60.0) -> None:
    deadline = time.monotonic() + float(timeout_seconds)
    while time.monotonic() < deadline:
        if server_is_up(url, port):
            return
        time.sleep(1)
    raise RuntimeError(f"ollama serve did not become ready at {url}:{port}/api/version")


def preload_model(url: str, port: int, model: str, timeout: float = 120.0) -> None:
    json_post(endpoint_url(url, port, "/api/generate"),
              {"model": model, "keep_alive": "30m"}, timeout=timeout)


def running_model_names(host: str) -> List[str]:
    proc = None
    try:
        proc = run_ollama_command("ps", host=host)
    except FileNotFoundError:
        return []
    if proc is None or proc.returncode != 0:
        return []
    names: List[str] = []
    for line in (proc.stdout or "").splitlines()[1:]:
        line = line.strip()
        if not line:
            continue
        names.append(line.split()[0])
    return names


def _listener_pids_from_connections(connections, port: int) -> List[int]:
    pids: set[int] = set()
    for conn in connections:
        if conn.status != psutil.CONN_LISTEN or not getattr(conn, "laddr", None):
            continue
        if getattr(conn.laddr, "port", None) != port or conn.pid is None:
            continue
        pids.add(conn.pid)
    return sorted(pids)


def find_ollama_listener_pids(port: int) -> List[int]:
    if psutil is None:
        return []
    try:
        return _listener_pids_from_connections(psutil.net_connections(kind="inet"), port)
    except psutil.AccessDenied:
        pass

    pids: set[int] = set()
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            name = str((proc.info or {}).get("name") or proc.name()).lower()
        except psutil.Error:
            continue
        if "ollama" not in name:
            continue
        try:
            connections = proc.net_connections(kind="inet")
        except psutil.Error:
            continue
        for conn in connections:
            if conn.status != psutil.CONN_LISTEN or not getattr(conn, "laddr", None):
                continue
            if getattr(conn.laddr, "port", None) != port:
                continue
            pids.add(getattr(conn, "pid", None) or proc.pid)
    return sorted(pids)


def start_service(url: str, port: int, model: str, preload_timeout: float = 120.0) -> Tuple[int, str]:
    host = f"{url.rstrip(':/')}:{port}"
    if not model:
        return 1, "No model specified"
    try:
        version_proc = run_ollama_command("--version", host=url + f":{port}")
    except FileNotFoundError:
        return 1, "ollama: command not found"

    started = False
    if server_is_up(url, port):
        msg = f"Ollama already serving at {host}"
    else:
        try:
            start_detached_ollama_serve(host=url + f":{port}")
            wait_until_ready(url, port)
            started = True
            msg = f"Started ollama serve at {host}"
        except Exception as exc:
            return 1, f"Failed to start ollama: {exc}"

    pull_proc = run_ollama_command("pull", model, host=url + f":{port}")
    if pull_proc.returncode != 0:
        details = (pull_proc.stdout or "") + (pull_proc.stderr or "")
        return pull_proc.returncode, details

    try:
        preload_model(url, port, model, timeout=preload_timeout)
    except Exception:
        # Preload failures are non-fatal for startup
        pass

    if started:
        return 0, f"Started ollama at {host}, pulled and warmed model '{model}'."
    return 0, f"Ollama already running at {host}; pulled and warmed model '{model}'."


def stop_service(url: str, port: int, verbose: bool = False) -> int:
    try:
        run_ollama_command("--version", host=f"{url}:{port}")
        models = running_model_names(f"{url}:{port}")
        if models and verbose:
            print(f"Stopping running models: {' '.join(models)}")
        for model in models:
            run_ollama_command("stop", model, host=f"{url}:{port}")
    except FileNotFoundError:
        if verbose:
            print("ollama CLI not found; skipping model stop.")

    pids = find_ollama_listener_pids(port)
    if not pids:
        if verbose:
            print(f"No process is listening on port {port} (already stopped?).")
        return 0

    killed = False
    for pid in pids:
        try:
            proc = psutil.Process(pid) if psutil is not None else None
        except Exception:
            proc = None
        if proc is None:
            continue
        name = proc.name().lower()
        if "ollama" not in name:
            continue
        if verbose:
            print(f"Stopping ollama serve PID {pid} (port {port})")
        try:
            proc.terminate()
            killed = True
        except Exception:
            continue

    if psutil is not None:
        try:
            _gone, alive = psutil.wait_procs([psutil.Process(pid)
                                             for pid in pids if psutil.pid_exists(pid)], timeout=3.0)
            for p in alive:
                try:
                    p.kill()
                except Exception:
                    pass
        except Exception:
            pass

    if verbose:
        if killed:
            print(f"Ollama server on {url}:{port} stopped.")
        else:
            print(f"No ollama serve process found on {url}:{port}.")
    return 0


if __name__ == "__main__":
    # Minimal CLI wrapper for convenience
    import argparse

    parser = argparse.ArgumentParser(description="Ollama helper for modelito")
    parser.add_argument("action", choices=("start", "stop", "status", "install"))
    parser.add_argument("--url", default=os.environ.get("MODELITO_OLLAMA_URL", "http://localhost"))
    parser.add_argument("--port", type=int,
                        default=int(os.environ.get("MODELITO_OLLAMA_PORT", "11434")))
    parser.add_argument("--model", default=os.environ.get("MODELITO_OLLAMA_MODEL", ""))
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    if args.action == "start":
        code, message = start_service(args.url, args.port, args.model or "", preload_timeout=120.0)
        print(message)
        raise SystemExit(code)
    if args.action == "stop":
        raise SystemExit(stop_service(args.url, args.port, verbose=args.verbose))
    if args.action == "status":
        print(json.dumps({
            "installed": ollama_installed(),
            "running": server_is_up(args.url, args.port),
        }))
        raise SystemExit(0)
    if args.action == "install":
        # Best-effort: delegate to official installer script by opening a shell
        if sys.platform.startswith("win"):
            cmd = ["powershell.exe", "-NoExit", "-ExecutionPolicy", "Bypass",
                   "-Command", "irm https://ollama.com/install.ps1 | iex"]
            subprocess.Popen(cmd)
            print("Launched Windows installer (PowerShell).")
            raise SystemExit(0)
        else:
            install_cmd = "curl -fsSL https://ollama.com/install.sh | sh"
            subprocess.run(["/bin/sh", "-lc", install_cmd], check=False)
            print("Attempted to run installer script.")
            raise SystemExit(0)
