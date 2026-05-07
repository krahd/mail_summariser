# mail_summariser - Project Status

Last updated: 2026-05-07 15:57

## Purpose

mail_summariser is a local-first email workflow with:

- a FastAPI backend
- a browser client
- a macOS SwiftUI client

It supports a resettable sample mailbox for onboarding and testing, live IMAP/SMTP workflows, provider-backed summaries, and deterministic fallback summaries when providers are unavailable or return invalid output.

## Current state

The repository currently contains three active runtime surfaces:

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
- The temporary mockups in `mockups/temporary/` are non-functional concept artefacts and remain separate from production UI.

Implemented UI/UX changes:

- The first screen is now task-first. The previous overview band was removed, so the first viewport moves directly from header and tabs into quick filters, digest status, message review, and job actions.
- User-facing copy now presents the internal `dummyMode` capability as "Sample Mailbox" in the browser and macOS settings UI.
- The sample-mailbox switch moved out of the global top navigation and into Settings. The health strip shows `Mailbox: Sample` or `Mailbox: Live`.
- Quick filters were renamed to practical task labels: `Unread Mail`, `Needs Reply`, `Finance`, and `All Messages`.
- The default `Unread Mail` quick filter no longer injects a `today` keyword, so the resettable sample mailbox returns messages on first run.
- Empty searches now create an explicit no-message job with the summary text "No messages matched this search..." and log `summary_provider` as `status=empty`, `provider=none`, `model=none`.
- The browser disables job actions for empty jobs and shows a clearer no-message detail state.
- Message dates are formatted for scanning, with stable table widths for date and sender columns.
- Browser settings loading now preserves a manually selected backend URL instead of overwriting it with the backend's stored `backendBaseURL`.
- Developer fake-mail tooling remains gated by `MAIL_SUMMARISER_ENABLE_DEV_TOOLS` and is still separate from the end-user sample mailbox.

Rendered validation:

- A Safari-rendered screenshot of `http://127.0.0.1:5173` confirmed the task-first first viewport, sample mailbox health chip, renamed quick filters, and removal of the global mode toggle and overview band.
- Safari WebDriver could not execute page JavaScript because Safari's "Allow JavaScript from Apple Events" setting is disabled on this machine, so browser flow verification used the rendered screenshot plus backend/API and full-stack validation.
- The sample quick-filter API payload returned two built-in sample messages on `127.0.0.1:8766`.
- An empty-search API payload returned an explicit empty summary and did not route to an LLM provider.

Remaining UI ideas:

- Add a dedicated rendered regression harness for first-run, empty-result, settings, live-mode, and mobile workflows.
- Consider stronger disabled-button styling for action controls, especially while no job is active.
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
- Runtime/model routes now read merged persisted settings for Ollama host and model name.
- `tag_summarised` actions and undo now honour the saved `summarisedTag` by storing the actual tag in undo payloads.
- Browser backend target initialisation now preserves the browser-selected backend URL during settings loads.
- Dependency declarations and CI install steps now use the project runtime dependency set instead of the stale TestPyPI `modelito==0.1.1` workaround.
- Repository hygiene now ignores/removes local `.env` state and flags tracked exact `.env` and backend SQLite files.
- Browser rendered validation used Safari screenshot and API checks because Safari WebDriver JavaScript execution is disabled locally.

## Verification status

Latest verification:

- `backend/.venv/bin/python -m pytest -q tests/test_web_contract.py`: passed with 3 passed.
- `backend/.venv/bin/python -m pytest -q tests/test_summary_service_provider_library.py tests/test_fuzz_summary_payloads.py::test_summary_endpoint_skips_provider_when_search_returns_no_messages`: passed with 8 passed.
- `backend/.venv/bin/python -m pytest -q tests/test_fuzz_summary_payloads.py`: passed with 4 passed.
- `backend/.venv/bin/python -m pytest -q tests/test_backend_mail_flow.py tests/test_runtime_model_endpoints.py tests/test_runtime_controls.py tests/test_fuzz_summary_payloads.py tests/test_summary_service_provider_library.py tests/test_web_contract.py`: passed with 32 passed.
- `backend/.venv/bin/python -m pytest -q`: passed with 71 passed, 1 skipped.
- `./scripts/check_repo_hygiene.sh`: passed.
- `./scripts/validate_full_stack.sh`: passed when run with local port binding allowed. A first sandboxed run failed because local binding to `127.0.0.1:8766` was not permitted.
- Rendered Safari screenshot on `http://127.0.0.1:5173` with backend `http://127.0.0.1:8766`: loaded the updated task-first browser UI.
- Rendered Playwright screenshot on `http://127.0.0.1:8040`: loaded the updated `docs/` project website with `mail_summariser` hero, Sample Mailbox copy, download section, and architecture diagrams.
- API smoke on `POST /summaries` with the default unread sample-mail criteria returned two built-in sample messages.
- API smoke on `POST /summaries` with a no-match keyword returned an explicit empty summary and corresponding `summary_provider` log metadata.

Validation implications:

- Provider-key tests now clear or set controlled environment variables and redaction prevents provider errors from exposing API keys in fallback responses.
- Rendered JavaScript automation still needs a Playwright or enabled-Safari-WebDriver path for repeatable UI assertions.

## Risks and limitations

- Real IMAP/SMTP workflows involve real credentials and mailbox data; handling must remain conservative.
- Secret masking and masked-write semantics must not regress.
- Dev fake-mail endpoints must remain disabled unless explicitly enabled.
- Behaviour changes across backend/client boundaries require contract discipline.
- The rendered UI still lacks an automated browser regression suite; current verification used a screenshot plus API/full-stack checks.
- Dependency alignment is updated locally and should be confirmed in CI on the next push.
- Sample mailbox naming is implemented in clients, but backend route and schema names intentionally retain `dummyMode` for compatibility.
- Browser and macOS clients should continue to be reviewed together when backend response contracts change.

## Pending tasks

- Continue broad malformed-input fuzzing for any remaining lightly covered route shapes.
- Keep browser and macOS client expectations aligned with backend response contracts.
- Keep hygiene checks current as packaging and release scripts evolve.
- Add repeatable rendered UI regression checks for first-run, empty-result, settings, live-mode, and mobile flows.
- Confirm dependency and hygiene changes in CI after pushing.

## Next steps

1. Push and review CI for the dependency, hygiene, and full-stack validation changes.
2. Add automated rendered UI coverage using Playwright or an enabled WebDriver path.
3. Continue broadening malformed-input fuzzing around lightly covered route combinations.
4. Keep documentation, website, and client copy aligned around "Sample Mailbox" while preserving backend API compatibility.

## Longer-term steps

1. Keep local-first onboarding reliable through a safe sample mailbox and deterministic fallback behaviour.
2. Strengthen cross-platform validation for backend and clients.
3. Preserve safe handling for live mailbox operations and provider integrations.
4. Convert any remaining useful temporary UX mockup decisions into production UI work or remove obsolete mockups after decisions are made.
5. Add and maintain rendered UI regression checks for first-run, empty-result, live-mode settings, and mobile workflows.

## Decisions

- The internal dummy-mode capability remains required for tests and safe local development, but end users see it as "Sample Mailbox".
- Provider failures should degrade gracefully to deterministic fallback summaries.
- Dev-only tooling remains explicit and gated.
- Empty message sets should not be sent to LLM providers.

---

Last updated: 2026-05-07 15:57
