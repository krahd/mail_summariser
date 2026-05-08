from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.validate_full_stack import (
    find_free_port,
    read_log_tail,
    terminate_process,
    wait_for_url,
)


def _load_playwright():
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Playwright is not installed. Install dev dependencies, then run "
            "`python -m playwright install chromium`."
        ) from exc
    return sync_playwright, PlaywrightTimeoutError


def _start_backend(
    root_dir: Path,
    host: str,
    port: int,
    web_origin: str,
    data_dir: Path,
    log_path: Path,
) -> subprocess.Popen[bytes]:
    env = os.environ.copy()
    backend_url = f"http://{host}:{port}"
    env["PYTHONPATH"] = str(root_dir)
    env["MAIL_SUMMARISER_DATA_DIR"] = str(data_dir)
    env["ALLOWED_ORIGINS"] = web_origin
    env["BACKEND_BASE_URL"] = backend_url
    env["DUMMY_MODE"] = "true"
    env["LLM_PROVIDER"] = "openai"
    env.pop("OPENAI_API_KEY", None)
    env.pop("ANTHROPIC_API_KEY", None)

    with log_path.open("wb") as log_out:
        return subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "backend.app:app",
                "--host",
                host,
                "--port",
                str(port),
            ],
            cwd=root_dir,
            env=env,
            stdout=log_out,
            stderr=subprocess.STDOUT,
        )


def _start_web(root_dir: Path, host: str, port: int, log_path: Path) -> subprocess.Popen[bytes]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root_dir)

    with log_path.open("wb") as log_out:
        return subprocess.Popen(
            [
                sys.executable,
                "-m",
                "http.server",
                str(port),
                "--bind",
                host,
                "--directory",
                "webapp",
            ],
            cwd=root_dir,
            env=env,
            stdout=log_out,
            stderr=subprocess.STDOUT,
        )


def _attach_console_capture(page, messages: list[str]) -> None:
    page.on(
        "console",
        lambda msg: messages.append(f"{msg.type}: {msg.text}")
        if msg.type in {"error", "warning"}
        else None,
    )
    page.on("pageerror", lambda exc: messages.append(f"pageerror: {exc}"))


def _fail_on_console_messages(messages: list[str]) -> None:
    if messages:
        joined = "\n".join(messages)
        raise RuntimeError(f"Rendered UI emitted console warnings/errors:\n{joined}")


def _wait_for_initial_load(page) -> None:
    page.wait_for_selector("#workspace-health-strip", state="visible", timeout=15_000)
    page.wait_for_function(
        "() => document.querySelector('#status-line')?.textContent"
        ".includes('Connected and loaded initial data.')",
        timeout=30_000,
    )


def _assert_no_horizontal_overflow(page, label: str) -> None:
    metrics = page.evaluate(
        """() => ({
            innerWidth: window.innerWidth,
            scrollWidth: document.documentElement.scrollWidth,
            bodyScrollWidth: document.body.scrollWidth
        })"""
    )
    max_scroll_width = max(int(metrics["scrollWidth"]), int(metrics["bodyScrollWidth"]))
    if max_scroll_width > int(metrics["innerWidth"]) + 2:
        raise RuntimeError(f"{label} viewport has horizontal overflow: {metrics}")


def _assert_no_element_horizontal_scroll(page, selector: str, label: str) -> None:
    metrics = page.locator(selector).evaluate(
        """(element) => ({
            clientWidth: element.clientWidth,
            scrollWidth: element.scrollWidth
        })"""
    )
    if int(metrics["scrollWidth"]) > int(metrics["clientWidth"]) + 2:
        raise RuntimeError(f"{label} has horizontal scroll: {metrics}")


def _assert_text_absent(page, text: str) -> None:
    body_text = page.locator("body").inner_text(timeout=5_000)
    if text in body_text:
        raise RuntimeError(f"Unexpected rendered text found: {text}")


def _assert_message_explainer_modal_behaviour(page) -> None:
    modal = page.locator("#message-explainer-modal")
    title = page.locator("#message-explainer-title")
    body = page.locator("#message-explainer-body")
    close_button = page.locator("#message-explainer-close")

    expected_by_kind = {
        "runtime": ("Runtime Status Help", "Runtime status"),
        "models": ("Model Status Help", "Model status"),
        "catalog": ("Catalogue Status Help", "Catalogue status"),
    }

    for kind, expected_values in expected_by_kind.items():
        expected_title, expected_text = expected_values
        page.locator(f".message-help-btn[data-message-help='{kind}']").click()
        modal.wait_for(state="visible", timeout=5_000)
        title.wait_for(state="visible", timeout=5_000)
        if title.inner_text(timeout=5_000).strip() != expected_title:
            raise RuntimeError(f"Unexpected explainer title for {kind} status.")
        body_text = body.inner_text(timeout=5_000)
        if expected_text not in body_text:
            raise RuntimeError(
                f"Explainer body for {kind} status did not include expected text: {expected_text}"
            )

        close_button.click()
        page.wait_for_function(
            "() => document.querySelector('#message-explainer-modal')?.classList.contains('is-hidden')",
            timeout=5_000,
        )


def _run_desktop_flow(browser, web_url: str, backend_url: str, screenshot_dir: Path) -> dict[str, str]:
    console_messages: list[str] = []
    context = browser.new_context(viewport={"width": 1440, "height": 960})
    context.add_init_script(
        f"window.localStorage.setItem('mail_summariser-base-url', {json.dumps(backend_url)});"
    )
    page = context.new_page()
    _attach_console_capture(page, console_messages)

    page.goto(web_url, wait_until="domcontentloaded")
    _wait_for_initial_load(page)
    if page.title() != "mail_summariser web":
        raise RuntimeError(f"Unexpected page title: {page.title()}")
    page.get_by_role("heading", name="mail_summariser").wait_for(timeout=5_000)
    page.locator("#health-mode").wait_for(state="visible", timeout=5_000)
    if "Mailbox: Sample" not in page.locator("#health-mode").inner_text():
        raise RuntimeError("Sample mailbox health chip was not rendered.")
    _assert_text_absent(page, "Dummy Mode")
    _assert_text_absent(page, "Dummy mode")
    _assert_no_horizontal_overflow(page, "desktop initial")

    page.wait_for_timeout(350)
    first_run_path = screenshot_dir / "rendered-ui-desktop-first-run.png"
    page.screenshot(path=str(first_run_path), full_page=False)

    page.locator("#search-form button[type='submit']").click()
    page.wait_for_function(
        "() => document.querySelector('#digest-metric-messages')?.textContent.trim() === '2'",
        timeout=30_000,
    )
    page.wait_for_function(
        "() => document.querySelector('#message-detail-shell')?.dataset.state === 'ready'",
        timeout=15_000,
    )
    summary_text = page.locator("#summary-text").inner_text(timeout=5_000)
    if "Messages summarized: 2" not in summary_text:
        raise RuntimeError("First-run sample summary did not include two messages.")
    if not page.locator("#apply-scope-actions").is_enabled():
        raise RuntimeError("Scoped action button was not enabled for a non-empty job.")
    _assert_no_element_horizontal_scroll(page, ".message-table-wrapper", "sample message table")

    page.wait_for_timeout(350)
    sample_summary_path = screenshot_dir / "rendered-ui-sample-summary.png"
    page.screenshot(path=str(sample_summary_path), full_page=False)

    page.locator("input[name='keyword']").fill("no-such-rendered-ui-message")
    page.locator("#search-form button[type='submit']").click()
    page.wait_for_function(
        "() => document.querySelector('#summary-card')?.dataset.state === 'empty-results'",
        timeout=15_000,
    )
    empty_text = page.locator("#summary-text").inner_text(timeout=5_000)
    if "No messages matched this search" not in empty_text:
        raise RuntimeError("Empty-result summary text was not rendered.")
    if page.locator("#apply-scope-actions").is_enabled():
        raise RuntimeError("Scoped action button stayed enabled for an empty job.")

    page.wait_for_timeout(350)
    empty_path = screenshot_dir / "rendered-ui-empty-result.png"
    page.screenshot(path=str(empty_path), full_page=False)

    page.locator(".tab[data-tab='settings']").click()
    page.locator("#dummy-mode-toggle").wait_for(state="visible", timeout=5_000)
    if "Sample Mailbox: On" not in page.locator("#dummy-mode-toggle").inner_text():
        raise RuntimeError("Sample Mailbox settings toggle was not on.")
    page.locator("#dummy-mode-toggle").click()
    page.wait_for_function(
        "() => document.querySelector('#dummy-mode-toggle')?.textContent.includes('Off')",
        timeout=10_000,
    )
    page.locator("#dummy-mode-toggle").click()
    page.wait_for_function(
        "() => document.querySelector('#dummy-mode-toggle')?.textContent.includes('On')",
        timeout=10_000,
    )
    page.locator("#open-advanced-settings").click()
    page.locator("#settings-advanced-screen:not(.is-hidden)").wait_for(timeout=5_000)
    if page.locator("#llm-provider").input_value() != "openai":
        raise RuntimeError("Rendered settings did not load the OpenAI fallback provider.")
    _assert_message_explainer_modal_behaviour(page)
    _assert_no_horizontal_overflow(page, "desktop settings")

    page.wait_for_timeout(350)
    settings_path = screenshot_dir / "rendered-ui-settings.png"
    page.screenshot(path=str(settings_path), full_page=False)
    _fail_on_console_messages(console_messages)
    context.close()

    return {
        "desktop_first_run": str(first_run_path),
        "sample_summary": str(sample_summary_path),
        "empty_result": str(empty_path),
        "settings": str(settings_path),
    }


def _run_mobile_flow(browser, web_url: str, backend_url: str, screenshot_dir: Path) -> dict[str, str]:
    console_messages: list[str] = []
    context = browser.new_context(
        viewport={"width": 390, "height": 844},
        is_mobile=True,
    )
    context.add_init_script(
        f"window.localStorage.setItem('mail_summariser-base-url', {json.dumps(backend_url)});"
    )
    page = context.new_page()
    _attach_console_capture(page, console_messages)

    page.goto(web_url, wait_until="domcontentloaded")
    _wait_for_initial_load(page)
    page.get_by_role("heading", name="mail_summariser").wait_for(timeout=5_000)
    page.locator(".tab[data-tab='settings']").click()
    page.locator("#dummy-mode-toggle").wait_for(state="visible", timeout=5_000)
    _assert_no_horizontal_overflow(page, "mobile settings")

    page.wait_for_timeout(350)
    mobile_path = screenshot_dir / "rendered-ui-mobile-settings.png"
    page.screenshot(path=str(mobile_path), full_page=False)
    _fail_on_console_messages(console_messages)
    context.close()

    return {"mobile_settings": str(mobile_path)}


def _run_playwright_checks(web_url: str, backend_url: str, screenshot_dir: Path) -> dict[str, str]:
    sync_playwright, playwright_timeout_error = _load_playwright()
    screenshot_dir.mkdir(parents=True, exist_ok=True)

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                screenshots = _run_desktop_flow(browser, web_url, backend_url, screenshot_dir)
                screenshots.update(_run_mobile_flow(browser, web_url, backend_url, screenshot_dir))
                return screenshots
            finally:
                browser.close()
    except playwright_timeout_error as exc:
        raise RuntimeError(f"Rendered UI validation timed out: {exc}") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description="Run rendered browser UI regression checks")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--backend-port", type=int, default=0)
    parser.add_argument("--web-port", type=int, default=0)
    parser.add_argument("--attempts", type=int, default=40)
    parser.add_argument("--delay", type=float, default=1.0)
    parser.add_argument(
        "--screenshot-dir",
        type=Path,
        default=Path(tempfile.gettempdir()) / "mail_summariser_rendered_ui",
    )
    args = parser.parse_args()

    root_dir = Path(__file__).resolve().parents[1]
    host = args.host
    backend_port = args.backend_port or find_free_port(host)
    web_port = args.web_port or find_free_port(host)
    backend_url = f"http://{host}:{backend_port}"
    web_url = f"http://{host}:{web_port}"

    temp_dir = Path(tempfile.gettempdir())
    backend_log = temp_dir / "mail_summariser_rendered_ui_backend.log"
    web_log = temp_dir / "mail_summariser_rendered_ui_web.log"

    backend_proc: subprocess.Popen[bytes] | None = None
    web_proc: subprocess.Popen[bytes] | None = None

    with tempfile.TemporaryDirectory(prefix="mail-summariser-rendered-ui-") as data_dir_name:
        data_dir = Path(data_dir_name)
        try:
            web_proc = _start_web(root_dir, host, web_port, web_log)
            wait_for_url(web_url, args.attempts, args.delay, web_proc, web_log)

            backend_proc = _start_backend(root_dir, host, backend_port, web_url, data_dir, backend_log)
            wait_for_url(f"{backend_url}/health", args.attempts, args.delay, backend_proc, backend_log)

            screenshots = _run_playwright_checks(web_url, backend_url, args.screenshot_dir)
        except Exception as exc:
            print(f"Rendered UI validation failed: {exc}", file=sys.stderr)
            print(f"Backend log tail:\n{read_log_tail(backend_log)}", file=sys.stderr)
            print(f"Web log tail:\n{read_log_tail(web_log)}", file=sys.stderr)
            return 1
        finally:
            terminate_process(web_proc)
            terminate_process(backend_proc)

    print("Rendered UI validation passed.")
    print(json.dumps({"url": web_url, "backendUrl": backend_url, "screenshots": screenshots}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
