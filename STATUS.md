# mail_summariser - Project Status

Last updated: 2026-05-09 14:14

## Purpose

mail_summariser is a local-first email workflow with:

- a FastAPI backend
- a browser client
- a macOS SwiftUI client

It supports a resettable sample mailbox for onboarding and testing, live IMAP/SMTP workflows, provider-backed summaries, and deterministic fallback summaries when providers are unavailable or return invalid output.

## Current state

The repository currently contains three active runtime surfaces and one documentation surface:

- `backend/` for API, storage, mail integration, summary orchestration, and model-runtime control
- `webapp/` for the browser UI
- `macos-app/` for the desktop client
- `docs/` for the GitHub Pages project website served from `main:/docs`

Key implemented backend areas:

- app entrypoint and router mounting in `backend/app.py`
- route decomposition across:
  - `backend/routers_runtime_models.py`
  - `backend/routers_settings.py`
  - `backend/routers_actions.py`
  - `backend/routers_summaries.py`
  - `backend/routers_devtools.py`
- shared app-module resolution in `backend/router_context.py`
- SQLite persistence in `backend/db.py`
- provider abstraction in `backend/llm_provider_clients.py`
- summary orchestration and fallback handling in `backend/summary_service.py`
- runtime/provider operations in `backend/model_provider_service.py`

## Active focus

Current focus is stability, safety, and product clarity of the local-first workflow:

- preserving secret masking semantics
- keeping fake-mail dev tooling strictly gated
- maintaining alignment between backend, browser client, and macOS client
- continuing malformed-input hardening and endpoint-level fuzz coverage
- keeping end-user surfaces focused on the sample mailbox and live mailbox concepts rather than internal dummy-mode naming
- keeping the browser first-run path grounded in real sample messages and explicit empty-result handling

## Architecture

The backend is the system of record for settings, mailbox integration, summaries, actions, logs, and runtime/model controls. Both clients call backend HTTP APIs.

### Architecture diagram

<svg xmlns="http://www.w3.org/2000/svg" width="1040" height="470" viewBox="0 0 1040 470" role="img" aria-labelledby="mail-arch-title mail-arch-desc">
  <title id="mail-arch-title">mail_summariser architecture</title>
  <desc id="mail-arch-desc">Browser and macOS clients call FastAPI routes backed by mail services, SQLite persistence, summary providers, and runtime model control.</desc>
  <defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto"><path d="M0 0 L10 5 L0 10 z" /></marker></defs>
  <rect x="40" y="80" width="180" height="70" rx="10" fill="none" stroke="black" /><text x="130" y="110" text-anchor="middle" font-size="14">webapp/</text><text x="130" y="130" text-anchor="middle" font-size="12">browser client</text>
  <rect x="40" y="230" width="180" height="70" rx="10" fill="none" stroke="black" /><text x="130" y="260" text-anchor="middle" font-size="14">macos-app/</text><text x="130" y="280" text-anchor="middle" font-size="12">SwiftUI client</text>
  <rect x="300" y="145" width="210" height="90" rx="10" fill="none" stroke="black" /><text x="405" y="180" text-anchor="middle" font-size="14">backend/app.py</text><text x="405" y="202" text-anchor="middle" font-size="12">FastAPI app and</text><text x="405" y="220" text-anchor="middle" font-size="12">router mounting</text>
  <rect x="590" y="40" width="190" height="70" rx="10" fill="none" stroke="black" /><text x="685" y="70" text-anchor="middle" font-size="14">mail services</text><text x="685" y="90" text-anchor="middle" font-size="12">sample, IMAP, SMTP</text>
  <rect x="590" y="145" width="190" height="70" rx="10" fill="none" stroke="black" /><text x="685" y="174" text-anchor="middle" font-size="14">summary service</text><text x="685" y="194" text-anchor="middle" font-size="12">provider fallback</text>
  <rect x="590" y="250" width="190" height="70" rx="10" fill="none" stroke="black" /><text x="685" y="280" text-anchor="middle" font-size="14">SQLite database</text><text x="685" y="300" text-anchor="middle" font-size="12">settings and state</text>
  <rect x="820" y="145" width="180" height="80" rx="10" fill="none" stroke="black" /><text x="910" y="176" text-anchor="middle" font-size="14">model providers</text><text x="910" y="198" text-anchor="middle" font-size="12">Ollama, OpenAI,</text><text x="910" y="216" text-anchor="middle" font-size="12">Anthropic, fallback</text>
  <rect x="590" y="360" width="190" height="70" rx="10" fill="none" stroke="black" /><text x="685" y="390" text-anchor="middle" font-size="14">tests/scripts</text><text x="685" y="410" text-anchor="middle" font-size="12">validation and hygiene</text>
  <line x1="220" y1="115" x2="300" y2="175" stroke="black" marker-end="url(#arrow)" /><line x1="220" y1="265" x2="300" y2="205" stroke="black" marker-end="url(#arrow)" /><line x1="510" y1="170" x2="590" y2="75" stroke="black" marker-end="url(#arrow)" /><line x1="510" y1="190" x2="590" y2="180" stroke="black" marker-end="url(#arrow)" /><line x1="510" y1="215" x2="590" y2="285" stroke="black" marker-end="url(#arrow)" /><line x1="780" y1="180" x2="820" y2="185" stroke="black" marker-end="url(#arrow)" /><line x1="685" y1="320" x2="685" y2="360" stroke="black" marker-end="url(#arrow)" />
</svg>

## UI and UX audit

Current browser UI state:

- The browser client is a static HTML/CSS/JavaScript app with Main, Log, Settings, and Help surfaces.
- The Main surface uses a three-column desktop layout: quick filters and advanced query, digest and message review, and scoped job actions.
- The Log surface is a timeline-style view with text, status, and undoable filters.
- Settings are split into a basic screen and an advanced screen; advanced controls include provider prompts, provider keys, Ollama lifecycle, model tools, backend targeting, fake-mail tools, database reset, and backend shutdown.
- The previous temporary approval-stage mockups have been removed because the key web UI decisions were either implemented in production or superseded.

Implemented UI/UX changes:

- The first screen is now task-first. The previous overview band was removed, so the first viewport moves directly from header and tabs into quick filters, digest status, message review, and job actions.
- User-facing copy now presents the internal `dummyMode` capability as "Sample Mailbox" in the browser and macOS settings UI.
- The sample-mailbox switch moved out of the global top navigation and into Settings. The health strip shows `Mailbox: Sample` or `Mailbox: Live`.
- Quick filters were renamed to practical task labels: `Unread Mail`, `Needs Reply`, `Finance`, and `All Messages`.
- The default `Unread Mail` quick filter no longer injects a `today` keyword, so the resettable sample mailbox returns messages on first run.
- Empty searches now create an explicit no-message job with the summary text "No messages matched this search..." and log `summary_provider` as `status=empty`, `provider=none`, `model=none`.
- The browser disables job actions for empty jobs and shows a clearer no-message detail state.
- Disabled browser action buttons now use a muted inactive treatment rather than a faded active-colour treatment.
- Message dates are formatted for scanning, with stable table widths for date and sender columns.
- The rendered message table now uses fixed columns, wrapping, and a wider review split to prevent horizontal table scroll in the desktop review pane.
- Browser settings loading now preserves a manually selected backend URL instead of overwriting it with the backend's stored `backendBaseURL`.
- Developer fake-mail tooling remains gated by `MAIL_SUMMARISER_ENABLE_DEV_TOOLS` and is still separate from the end-user sample mailbox.

Rendered validation:

- `scripts/validate_rendered_ui.py` starts isolated backend and static-web instances, then drives Chromium through first load, sample digest generation, empty-result handling, the settings/live-mode toggle, and a mobile settings viewport.
- The rendered validator checks page identity, console warnings/errors, page overflow, message-table overflow, Sample Mailbox copy, enabled/disabled action states, and screenshot capture.
- CI installs Chromium and required browser dependencies, then runs the rendered UI regression on the Ubuntu Python 3.11 test job.

Remaining UI ideas:

- Continue refining dense desktop and mobile layouts as real usage patterns emerge.

## Sample mailbox assessment

The internal `dummyMode` setting is still required for tests, onboarding, documentation examples, and safe local verification. It stays in the backend and test suite for API compatibility and validation.

Product recommendation:

- Implemented: end-user clients present the capability as "Sample Mailbox".
- Implemented: the browser mode switch now lives in Settings rather than the global top navigation.
- Implemented: fake-mail dev tools remain developer-only integration tooling and are not merged conceptually with the end-user sample mailbox.
- Implemented: the default sample-mail quick filter returns built-in sample messages.
- Implemented: sample jobs, logs, and undo entries continue to use in-memory stores and reset when switching to live mode or resetting the database.

Current implementation notes:

- `dummyMode` is persisted as a setting.
- Dummy jobs, logs, and undo entries use the in-memory `backend/dummy_state.py` store rather than the SQLite job/log tables.
- Switching from dummy mode to live mode resets dummy session state, which prevents old dummy jobs from being acted on after the mode change.
- Database reset restores default settings and resets dummy state.
- Sample mailbox mode exercises the same summary/action endpoints as live mode, which is valuable for tests.

## Main request flow

<svg xmlns="http://www.w3.org/2000/svg" width="1040" height="350" viewBox="0 0 1040 350" role="img" aria-labelledby="mail-flow-title mail-flow-desc">
  <title id="mail-flow-title">mail_summariser summary flow</title>
  <desc id="mail-flow-desc">A client requests a summary, backend loads mail and settings, summary service calls provider or fallback, and returns persisted results.</desc>
  <defs><marker id="flowarrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto"><path d="M0 0 L10 5 L0 10 z" /></marker></defs>
  <rect x="30" y="140" width="135" height="65" rx="10" fill="none" stroke="black" /><text x="97" y="168" text-anchor="middle" font-size="12">Client requests</text><text x="97" y="186" text-anchor="middle" font-size="12">summary</text>
  <rect x="210" y="140" width="135" height="65" rx="10" fill="none" stroke="black" /><text x="277" y="168" text-anchor="middle" font-size="12">Load mail</text><text x="277" y="186" text-anchor="middle" font-size="12">and settings</text>
  <rect x="390" y="140" width="135" height="65" rx="10" fill="none" stroke="black" /><text x="457" y="168" text-anchor="middle" font-size="12">Build summary</text><text x="457" y="186" text-anchor="middle" font-size="12">request</text>
  <rect x="570" y="140" width="135" height="65" rx="10" fill="none" stroke="black" /><text x="637" y="168" text-anchor="middle" font-size="12">Call provider</text><text x="637" y="186" text-anchor="middle" font-size="12">or fallback</text>
  <rect x="750" y="140" width="135" height="65" rx="10" fill="none" stroke="black" /><text x="817" y="168" text-anchor="middle" font-size="12">Persist result</text><text x="817" y="186" text-anchor="middle" font-size="12">in SQLite</text>
  <rect x="930" y="140" width="90" height="65" rx="10" fill="none" stroke="black" /><text x="975" y="168" text-anchor="middle" font-size="12">Return</text><text x="975" y="186" text-anchor="middle" font-size="12">JSON</text>
  <line x1="165" y1="172" x2="210" y2="172" stroke="black" marker-end="url(#flowarrow)" /><line x1="345" y1="172" x2="390" y2="172" stroke="black" marker-end="url(#flowarrow)" /><line x1="525" y1="172" x2="570" y2="172" stroke="black" marker-end="url(#flowarrow)" /><line x1="705" y1="172" x2="750" y2="172" stroke="black" marker-end="url(#flowarrow)" /><line x1="885" y1="172" x2="930" y2="172" stroke="black" marker-end="url(#flowarrow)" />
</svg>

## Setup and run

Backend:

```bash
./start_backend.sh
```

Web app:

```bash
python -m http.server 8000 --directory webapp
```

Validation commands:

```bash
pytest -q
./scripts/validate_full_stack.sh
python scripts/validate_full_stack.py
python -m playwright install chromium
python scripts/validate_rendered_ui.py
./scripts/check_repo_hygiene.sh
```

## Configuration

- Settings persist in SQLite (`backend/data/mail_summariser.sqlite3` by default).
- The persisted API setting remains named `dummyMode`, but user-facing clients present it as "Sample Mailbox".
- Secrets returned from settings routes are masked.
- Writing masked sentinel values (for example `__MASKED__`) does not overwrite persisted secrets.
- Provider error messages are redacted before fallback text or metadata is returned.
- Dev fake-mail routes are gated by `MAIL_SUMMARISER_ENABLE_DEV_TOOLS`.
- `pyproject.toml` and `backend/requirements.txt` are aligned on runtime dependencies, including `modelito==1.2.2`, FastAPI, Pydantic, Uvicorn, OpenAI, and Anthropic.
- Local `.env` files are ignored. The previously tracked `.env` file has been removed from the working tree, and the hygiene guard flags exact tracked `.env` files and tracked backend SQLite databases.

## Important files

- `README.md`: project overview
- `backend/app.py`: FastAPI entrypoint and router mounting
- `backend/router_context.py`: runtime/test app-module parity
- `backend/db.py`: persistence
- `backend/summary_service.py`: summary orchestration and fallback handling
- `backend/model_provider_service.py`: provider runtime controls
- `backend/llm_provider_clients.py`: provider abstraction
- `webapp/api.js`: browser API contract surface
- `docs/index.html`, `docs/site.css`, `docs/site.js`: GitHub Pages website source
- `docs/assets/`: website diagrams and product screenshot
- `tests/`: backend/API and robustness test suite
- `scripts/validate_full_stack.py` and `scripts/validate_full_stack.sh`: startup validation
- `scripts/validate_rendered_ui.py`: Playwright rendered UI regression
- `scripts/check_repo_hygiene.sh`: repository hygiene guard

## Recent audit status

- Route decomposition remains in place across runtime/models, settings, actions, summaries, and dev-tools modules.
- Router parity safeguards exist via router-context and route-decomposition tests.
- Fuzz tests exist for summary, settings/actions, and runtime/model malformed payload contracts.
- Full-stack validation scripts remain available in both shell and Python variants.
- Empty-message summary creation now skips provider calls and records explicit empty-provider metadata.
- Summary length is clamped before provider calls and persistence so malformed or extremely large payload values cannot overflow SQLite.
- Browser and macOS user-facing copy now uses "Sample Mailbox" while preserving the `dummyMode` API field.
- The GitHub Pages website source has been restored in `docs/` with current Sample Mailbox positioning, download links, architecture diagrams, and a rendered product screenshot.
- The Python full-stack validator now selects a free static-web port by default, binds the static server to `127.0.0.1`, watches startup subprocess exits, and includes service log tails in readiness failures. This addresses the macOS CI startup-validation timeout observed against fixed port `8000`.
- The Playwright rendered UI validator is available locally and wired into CI for first-run, empty-result, settings/live-mode, and mobile checks.
- CI run `25518723986` passed after adding the rendered UI regression, Playwright dependency, and expanded fuzz coverage.
- Runtime/model routes now read merged persisted settings for Ollama host and model name.
- Runtime/model fuzz coverage now includes install/stop runtime routes, model serve/download payloads, download-status query strings, and local-model delete query strings.
- Dev fake-mail route fuzz coverage now includes `/dev/fake-mail/status`, `/dev/fake-mail/start`, and `/dev/fake-mail/stop` malformed query/payload shapes with safe disabled-mode mocking.
- Read-endpoint fuzz coverage now includes `/settings`, `/settings/system-message-defaults`, `/health`, and `/jobs/{job_id}/messages/{message_id}` malformed query/path shapes.
- Browser API requests now normalise backend URLs (including missing schemes) and convert low-level fetch network failures into explicit backend-connectivity errors.
- Backend URL settings input now explicitly accepts host:port values and shows examples for both full URLs and host:port format.
- Backend CORS now accepts localhost/127.0.0.1 dev origins on arbitrary ports via `ALLOWED_ORIGIN_REGEX`, preventing runtime/model preflight `OPTIONS` failures on the default webapp port (`8000`).
- Desktop studio layout now uses a narrower actions column to reduce overlap pressure against the central review column on wider main-screen sessions.
- Desktop actions panel spacing is slightly denser (reduced internal padding and action-button gap) to keep controls compact without reducing text readability.
- Main-screen actions checkboxes now align correctly with labels, and the scope-status helper text is italicised for clearer emphasis.
- Advanced settings now groups Ollama controls into Runtime, Local Models, and Discover/Download panels and relies on the existing bottom status bar for runtime/model/catalog feedback.
- Refresh Available Models and Discover Models now disable while running and report explicit success/failure outcomes in the global status line so button activity is visible.
- Local model selection in advanced settings is now a true dropdown populated from available model options.
- Ollama catalog discovery now surfaces backend/provider errors instead of silently reporting a successful zero-model refresh.
- Remote catalog parsing now accepts dict/object payload shapes so Discover Models returns actual names when provider data is available.
- Remote catalog parsing now also accepts plain string payload entries and normalises CLI-style rows that include trailing metadata columns.
- Discover Models now falls back to parsing the Ollama public library page when the CLI remote listing is unavailable, then uses a curated default list only as a final offline fallback.
- Serve/Delete model actions now normalise model identifiers and strip CLI metadata suffixes, avoiding false serve failures when a selected model row includes digest/size/date columns.
- Serving a model now reports a clear "still downloading" state when a pull is in progress, instead of a generic serve failure.
- Discover Models now reports failure when the backend returns an empty catalogue and no longer reports a successful zero-model completion.
- Default provider system messages now give clearer guidance about deadlines, blockers, reply-needed items, grouping related threads, and avoiding invented details.
- Backend prompt construction now explicitly asks for grouped, factual, action-oriented output with short next-step cues when useful.
- Targeted backend tests now lock the updated default system-message copy and `_build_prompt()` guardrails so prompt regressions are caught without relying only on rendered UI coverage.
- Browser advanced settings now includes a prompt checklist beside the editable provider system message.
- The browser UI now includes a bottom status bar that keeps the current status text, mailbox mode, provider, job id, and message count visible.
- Rendered UI validation now asserts the bottom status bar on initial load, after a populated summary, and after an empty-result search so provider, job, status text, and message-count updates stay covered.
- macOS Settings now uses clearer Sample Mailbox wording and includes the same prompt checklist guidance as the browser advanced settings screen.
- The macOS shell now includes a persistent footer strip that mirrors the browser's status visibility with current status text, mailbox mode, provider, runtime health, fake-mail health, job id, and message count.
- The obsolete approval-stage files under `mockups/temporary/` have been removed after their useful web UI decisions were implemented or overtaken by the shipped interface.
- `tag_summarised` actions and undo now honour the saved `summarisedTag` by storing the actual tag in undo payloads.
- Browser backend target initialisation now preserves the browser-selected backend URL during settings loads.
- Dependency declarations and CI install steps now use the project runtime dependency set instead of the stale TestPyPI `modelito==0.1.1` workaround.
- Repository hygiene now ignores/removes local `.env` state and flags tracked exact `.env` and backend SQLite files.
- Browser rendered validation used Safari screenshot and API checks because Safari WebDriver JavaScript execution is disabled locally.

## Verification status

Recent verification:

- `backend/.venv/bin/python -m pytest -q tests/test_validate_full_stack_script.py`: passed with 3 passed.
- `backend/.venv/bin/python -m pytest -q tests/test_web_contract.py tests/test_validate_full_stack_script.py`: passed with 6 passed.
- `backend/.venv/bin/python -m pytest -q tests/test_fuzz_runtime_models_payloads.py`: passed with 11 passed.
- `backend/.venv/bin/python -m pytest -q tests/test_web_contract.py`: passed with 3 passed.
- `backend/.venv/bin/python -m pytest -q tests/test_fuzz_devtools_payloads.py`: passed with 3 passed.
- `backend/.venv/bin/python -m pytest -q tests/test_fuzz_read_endpoints.py`: passed with 4 passed.
- `backend/.venv/bin/python -m pytest -q tests/test_cors_runtime_endpoints.py tests/test_fuzz_read_endpoints.py`: passed with 6 passed.
- `backend/.venv/bin/python -m pytest -q tests/test_cors_runtime_endpoints.py tests/test_runtime_controls.py tests/test_runtime_model_endpoints.py`: passed with 14 passed.
- `backend/.venv/bin/python -m pytest -q tests/test_fuzz_runtime_models_payloads.py tests/test_fuzz_settings_actions_payloads.py tests/test_fuzz_summary_payloads.py tests/test_fuzz_devtools_payloads.py`: passed with 29 passed.
- `backend/.venv/bin/python -m pytest -q tests/test_fuzz_runtime_models_payloads.py tests/test_fuzz_settings_actions_payloads.py tests/test_fuzz_summary_payloads.py tests/test_fuzz_devtools_payloads.py tests/test_fuzz_read_endpoints.py`: passed with 33 passed.
- `backend/.venv/bin/python -m pytest -q tests/test_summary_service_provider_library.py tests/test_fuzz_summary_payloads.py::test_summary_endpoint_skips_provider_when_search_returns_no_messages`: passed with 8 passed.
- `backend/.venv/bin/python -m pytest -q tests/test_fuzz_summary_payloads.py`: passed with 4 passed.
- `backend/.venv/bin/python -m pytest -q tests/test_backend_mail_flow.py tests/test_runtime_model_endpoints.py tests/test_runtime_controls.py tests/test_fuzz_summary_payloads.py tests/test_summary_service_provider_library.py tests/test_web_contract.py`: passed with 32 passed.
- `backend/.venv/bin/python -m pytest -q`: passed with 90 passed, 1 skipped.
- `./scripts/check_repo_hygiene.sh`: passed.
- `git diff --check`: passed.
- `backend/.venv/bin/python -m py_compile scripts/validate_rendered_ui.py scripts/validate_full_stack.py`: passed.
- `backend/.venv/bin/python -m py_compile backend/config.py backend/summary_service.py scripts/validate_rendered_ui.py`: passed.
- `backend/.venv/bin/python -m pytest -q tests/test_system_message_settings.py tests/test_summary_service_provider_library.py tests/test_web_contract.py`: passed.
- `backend/.venv/bin/python -m pytest -q tests/test_runtime_model_endpoints.py tests/test_web_contract.py`: passed with 7 passed.
- `backend/.venv/bin/python -m pytest -q tests/test_runtime_model_endpoints.py tests/test_web_contract.py`: passed with 9 passed.
- `backend/.venv/bin/python -m pytest -q tests/test_runtime_model_endpoints.py tests/test_web_contract.py`: passed with 10 passed.
- `backend/.venv/bin/python -m pytest -q tests/test_runtime_model_endpoints.py tests/test_web_contract.py`: passed with 11 passed.
- `backend/.venv/bin/python scripts/validate_rendered_ui.py`: passed with local port binding and Chromium launch allowed. Screenshots were written to `/var/folders/z_/872qmw6s5_d1qlyd3xdgsl5r0000gn/T/mail_summariser_rendered_ui/`.
- `backend/.venv/bin/python scripts/validate_rendered_ui.py`: passed after frontend API backend-URL/error-handling changes.
- `backend/.venv/bin/python scripts/validate_rendered_ui.py`: passed after backend URL settings input guidance and format updates.
- `backend/.venv/bin/python scripts/validate_rendered_ui.py`: passed after backend CORS localhost/loopback regex update.
- `backend/.venv/bin/python scripts/validate_rendered_ui.py`: passed after narrowing the desktop actions column in the main studio grid.
- `backend/.venv/bin/python scripts/validate_rendered_ui.py`: passed after tightening actions panel internal spacing.
- `backend/.venv/bin/python scripts/validate_rendered_ui.py`: passed after adding status-message `?` explainers and click-anywhere close behaviour.
- `backend/.venv/bin/python scripts/validate_rendered_ui.py`: passed after adding explicit rendered assertions for explainer modal open/close behaviour.
- `backend/.venv/bin/python scripts/validate_rendered_ui.py`: passed after centralising Ollama status/help into one panel, restoring click-anywhere explainer close behaviour, reducing help-button size, converting local-model input to dropdown, and strengthening refresh/discover button feedback.
- `backend/.venv/bin/python scripts/validate_rendered_ui.py`: passed after improving default prompt guidance, adding the bottom browser status bar, and aligning macOS/browser Sample Mailbox wording.
- `backend/.venv/bin/python scripts/validate_rendered_ui.py`: passed after extending bottom-status assertions beyond initial load and adding the macOS footer status strip.
- `backend/.venv/bin/python scripts/validate_rendered_ui.py`: passed after removing the dedicated Ollama status panel/modal and using bottom-status-only runtime/model/catalog feedback.
- `backend/.venv/bin/python -m pytest -q`: passed with 96 passed, 1 skipped.
- `backend/.venv/bin/python scripts/validate_full_stack.py --attempts 5 --delay 0.5`: passed with local port binding allowed. A first sandboxed run failed because selecting and binding a loopback port was not permitted.
- `./scripts/validate_full_stack.sh`: passed when run with local port binding allowed. A first sandboxed run failed because local binding to `127.0.0.1:8766` was not permitted.
- GitHub CI run `25518723986`: passed, including Ubuntu Python 3.11 rendered UI regression and the cross-platform startup validation matrix.
- Rendered Safari screenshot on `http://127.0.0.1:5173` with backend `http://127.0.0.1:8766`: loaded the updated task-first browser UI.
- Rendered Playwright screenshot on `http://127.0.0.1:8040`: loaded the updated `docs/` project website with `mail_summariser` hero, Sample Mailbox copy, download section, and architecture diagrams.
- API smoke on `POST /summaries` with the default unread sample-mail criteria returned two built-in sample messages.
- API smoke on `POST /summaries` with a no-match keyword returned an explicit empty summary and corresponding `summary_provider` log metadata.

Validation implications:

- Provider-key tests now clear or set controlled environment variables and redaction prevents provider errors from exposing API keys in fallback responses.
- Settings/defaults regression tests now force a temporary SQLite path so they validate startup defaults instead of inheriting a developer's persisted local settings.
- Rendered JavaScript automation now has a Playwright path. Safari WebDriver remains unavailable locally because Safari's "Allow JavaScript from Apple Events" setting is disabled on this machine.

## Risks and limitations

- Real IMAP/SMTP workflows involve real credentials and mailbox data; handling must remain conservative.
- Secret masking and masked-write semantics must not regress.
- Dev fake-mail endpoints must remain disabled unless explicitly enabled.
- Behaviour changes across backend/client boundaries require contract discipline.
- Playwright browser installation is now a CI dependency for the Ubuntu Python 3.11 test job; the first CI run passed, but CDN/browser-install availability remains an external dependency.
- Sample mailbox naming is implemented in clients, but backend route and schema names intentionally retain `dummyMode` for compatibility.
- Browser and macOS clients should continue to be reviewed together when backend response contracts change.

## Recurring tasks

- Continue broad malformed-input fuzzing for any remaining lightly covered route shapes.
- Keep browser and macOS client expectations aligned with backend response contracts.
- Keep hygiene checks current as packaging and release scripts evolve.
- Add more rendered UI assertions as new workflows land.
- Keep documentation, website, and client copy aligned around "Sample Mailbox" while preserving backend API compatibility.

## Pending tasks

- None currently.

## Next steps

None currently. The previous cycle was completed and verified with targeted coverage for in-progress pull handling, cross-surface browser/macOS copy mirroring, and a full test run of 101 passed and 1 skipped.

## Longer-term steps

1. Keep local-first onboarding reliable through a safe sample mailbox and deterministic fallback behaviour.
2. Strengthen cross-platform validation for backend and clients.
3. Preserve safe handling for live mailbox operations and provider integrations.
4. Expand rendered UI regression checks beyond first-run flows to cover help/explainer overlays, scoped actions, and denser desktop layouts.
5. Keep browser and macOS information architecture aligned as provider/runtime controls continue to evolve.

## Decisions

- The internal dummy-mode capability remains required for tests and safe local development, but end users see it as "Sample Mailbox".
- Provider failures should degrade gracefully to deterministic fallback summaries.
- Dev-only tooling remains explicit and gated.
- Empty message sets should not be sent to LLM providers.

---

Last updated: 2026-05-09 14:14
