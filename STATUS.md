# mail_summariser - Project Status

Last updated: 2026-05-07 01:13

## Purpose

mail_summariser is a local-first email workflow with:

- a FastAPI backend
- a browser client
- a macOS SwiftUI client

It supports dummy-mode onboarding, live IMAP/SMTP workflows, provider-backed summaries, and deterministic fallback summaries when providers are unavailable or return invalid output.

## Current state

The repository currently contains three active runtime surfaces:

- `backend/` for API, storage, mail integration, summary orchestration, and model-runtime control
- `webapp/` for the browser UI
- `macos-app/` for the desktop client

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
- reducing end-user exposure to test/development concepts that are still required for validation
- tightening the browser workflow so the first run produces grounded, inspectable results

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
  <rect x="590" y="40" width="190" height="70" rx="10" fill="none" stroke="black" /><text x="685" y="70" text-anchor="middle" font-size="14">mail services</text><text x="685" y="90" text-anchor="middle" font-size="12">dummy, IMAP, SMTP</text>
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

Rendered audit findings:

- The app rendered without console errors on the default backend path (`webapp` on `127.0.0.1:5173`, backend on `127.0.0.1:8766`).
- Desktop and mobile layouts avoid horizontal overflow in the checked viewports.
- The mobile first viewport is top-heavy: header, status, tabs, dummy toggle, and overview consume the screen before the user reaches the actual digest workflow.
- The desktop main workflow is usable but dense. In the message review area, date values wrap awkwardly and the table/detail split can make subjects hard to scan.
- The hero/overview band explains internal architecture rather than helping the user complete the next email task. It should probably be shortened or removed from the operational app surface.
- The default `Today Unread` quick filter does not match the built-in dummy mailbox because it sets `keyword=today`, while dummy messages do not contain that word. A first-run digest can therefore create a zero-message job.
- If a provider is running, a zero-message summary request can still return provider-generated content unrelated to any email. Empty result sets need an explicit backend and UI empty state, not a provider call.
- The browser can switch to a non-default backend URL from local storage, but the initial `/settings` response can overwrite `backendBaseURL` back to the backend's stored value during load. This caused subsequent requests to fall back to `127.0.0.1:8766` in a non-default-port rendered test.

UI improvement ideas:

- Make the first screen task-first: search controls, digest status, and message review should outrank product/architecture copy.
- Replace the permanent overview band with a compact connection/workspace strip, or move explanatory content to Help.
- Convert quick filters into predictable presets backed by real dummy and live-mail semantics. For dummy mode, default to a preset that returns messages.
- Add an explicit empty-result state: "No messages matched this search", with actions to clear filters, change quick filter, or open Settings.
- Do not call LLM providers for empty message sets.
- Rename user-facing "Dummy Mode" to "Demo mailbox" or "Sample mailbox" and place the mode switch in onboarding/settings rather than as a permanent global top-nav control.
- Keep developer fake-mail tooling hidden behind `MAIL_SUMMARISER_ENABLE_DEV_TOOLS`; it should remain separate from the end-user demo mailbox.
- Improve scan density in the message table with date formatting, stable column widths, and a clearer selected-message detail panel.
- Treat destructive and operational controls as advanced/admin actions with stronger separation from ordinary account setup.
- Prefer icons or compact controls for repeated toolbar actions only after the workflow labels are stable.

## Dummy mode assessment

Dummy mode is still required for tests, onboarding, documentation examples, and safe local verification. It should stay in the backend and test suite.

Product recommendation:

- Keep the capability, but reposition it as a "Demo mailbox" or "Sample mailbox" for end users.
- Make it a first-run/onboarding affordance and a Settings option, not a persistent global mode toggle.
- Keep fake-mail dev tools as developer-only integration tooling; do not merge them conceptually with the end-user sample mailbox.
- Ensure sample data covers the default quick filters so a new user gets a meaningful summary immediately.
- Ensure actions in sample mode are clearly non-destructive and resettable.

Current implementation notes:

- `dummyMode` is persisted as a setting.
- Dummy jobs, logs, and undo entries use the in-memory `backend/dummy_state.py` store rather than the SQLite job/log tables.
- Switching from dummy mode to live mode resets dummy session state, which prevents old dummy jobs from being acted on after the mode change.
- Database reset restores default settings and resets dummy state.
- Dummy mode exercises the same summary/action endpoints as live mode, which is valuable for tests.

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
- Secrets returned from settings routes are masked.
- Writing masked sentinel values (for example `__MASKED__`) does not overwrite persisted secrets.
- Dev fake-mail routes are gated by `MAIL_SUMMARISER_ENABLE_DEV_TOOLS`.
- `pyproject.toml` pins `modelito==1.2.2`.
- `backend/requirements.txt` is not aligned with `pyproject.toml`; it does not declare the pinned `modelito` dependency used by backend imports.
- A tracked `.env` file exists. Its content is not repeated here, but tracked local environment files conflict with the repository safety rules and should be removed or explicitly justified.

## Important files

- `README.md`: project overview
- `backend/app.py`: FastAPI entrypoint and router mounting
- `backend/router_context.py`: runtime/test app-module parity
- `backend/db.py`: persistence
- `backend/summary_service.py`: summary orchestration and fallback handling
- `backend/model_provider_service.py`: provider runtime controls
- `backend/llm_provider_clients.py`: provider abstraction
- `webapp/api.js`: browser API contract surface
- `tests/`: backend/API and robustness test suite
- `scripts/validate_full_stack.py` and `scripts/validate_full_stack.sh`: startup validation
- `scripts/check_repo_hygiene.sh`: repository hygiene guard

## Recent audit status

- Route decomposition remains in place across runtime/models, settings, actions, summaries, and dev-tools modules.
- Router parity safeguards exist via router-context and route-decomposition tests.
- Fuzz tests exist for summary, settings/actions, and runtime/model malformed payload contracts.
- Full-stack validation scripts remain available in both shell and Python variants.
- Browser rendered checks were run with Python Playwright because the Browser plugin was not available in this session. Screenshots were written outside the repository under `/tmp/mail-summariser-audit/`.
- The default rendered browser path loads and can create a dummy-mode summary when the backend runs on `127.0.0.1:8766`.
- Non-default backend targeting needs follow-up because loaded backend settings can overwrite the browser's selected backend URL during initialisation.

## Verification status

Latest verification:

- `./scripts/check_repo_hygiene.sh`: passed.
- `backend/.venv/bin/python -m pytest -q`: failed in `test_masked_provider_keys_do_not_count_as_real_credentials` because the local environment contained an OpenAI API key; the failing assertion exposed the key value in output, and the value is intentionally not repeated here.
- `env -u OPENAI_API_KEY -u ANTHROPIC_API_KEY backend/.venv/bin/python -m pytest -q`: passed with 65 passed, 1 skipped.
- Rendered browser check on `http://127.0.0.1:5173` with backend `http://127.0.0.1:8766`: loaded without console errors and exercised the dummy all-messages summary path.
- Ambient `python3 -m uvicorn backend.app:app ...` failed because the ambient Python environment has `modelito` 1.2.0, which does not provide a function imported by `backend/model_provider_service.py`. The project venv has `modelito` 1.2.2 and can run the backend.

Validation implications:

- Test runs should clear provider key environment variables or tests should monkeypatch them, so secret-bearing developer environments do not leak keys into failure output.
- Fresh install and release paths need dependency alignment checks against `pyproject.toml`.

## Risks and limitations

- Real IMAP/SMTP workflows involve real credentials and mailbox data; handling must remain conservative.
- Secret masking and masked-write semantics must not regress.
- Dev fake-mail endpoints must remain disabled unless explicitly enabled.
- Behaviour changes across backend/client boundaries require contract discipline.
- Provider-backed summaries are not currently guarded against empty message lists; a running provider can produce ungrounded content for zero-email jobs.
- The default browser quick filter can return no dummy messages, which weakens first-run confidence.
- Runtime/model endpoints currently read Ollama host/model from defaults in `backend/routers_runtime_models.py`, not from persisted settings, so Settings changes may not fully affect runtime/model controls.
- `tag_summarised` and undo currently use `DEFAULT_SETTINGS['summarisedTag']`, not the saved `summarisedTag`, so custom tag settings may not be honoured.
- The tracked `.env` file and environment-sensitive provider-key test are secret-handling risks.
- `backend/requirements.txt`, release workflow dependency installation, and `pyproject.toml` are not fully aligned.
- Browser non-default backend targeting is fragile during initial settings load.

## Pending tasks

- Continue broad malformed-input fuzzing for any remaining lightly covered route shapes.
- Keep browser and macOS client expectations aligned with backend response contracts.
- Keep hygiene checks current as packaging and release scripts evolve.
- Add an empty-message guard to summary creation and provider calls.
- Change the default dummy/demo quick filter so it returns built-in sample messages.
- Reposition dummy mode as end-user demo/sample mailbox mode while keeping the backend test capability.
- Fix runtime/model routes to use merged/persisted settings where appropriate.
- Fix tag actions and undo to honour the saved `summarisedTag`.
- Remove or justify the tracked `.env` file and extend hygiene checks to catch tracked local environment files.
- Make provider-key tests independent from real `OPENAI_API_KEY` and `ANTHROPIC_API_KEY` environment variables.
- Align `backend/requirements.txt`, release workflow dependencies, and `pyproject.toml`.
- Fix browser backend target initialisation so a manually selected backend is not overwritten unexpectedly.

## Next steps

1. Fix empty-message summary behaviour and the default dummy/demo quick filter.
2. Decide the end-user naming and placement for dummy mode; recommended wording is "Demo mailbox" or "Sample mailbox".
3. Fix saved-setting alignment issues for `summarisedTag`, Ollama host/model runtime routes, and browser backend targeting.
4. Remove tracked local environment state and harden tests against secret-bearing environments.
5. Align dependency files and run full-stack validation from a clean environment.

## Longer-term steps

1. Keep local-first onboarding reliable through a safe sample mailbox and deterministic fallback behaviour.
2. Strengthen cross-platform validation for backend and clients.
3. Preserve safe handling for live mailbox operations and provider integrations.
4. Convert temporary UX mockup decisions into production UI work or remove obsolete mockups after decisions are made.
5. Add rendered UI regression checks for first-run, empty-result, live-mode settings, and mobile workflows.

## Decisions

- Dummy mode remains required for tests and safe local development, but should be presented to end users as a demo/sample mailbox rather than a technical "dummy mode".
- Provider failures should degrade gracefully to deterministic fallback summaries.
- Dev-only tooling remains explicit and gated.
- Empty message sets should not be sent to LLM providers.

---

Last updated: 2026-05-07 01:13
