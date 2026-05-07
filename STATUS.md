# mail_summariser - Project Status

Last updated: 2026-05-07 00:56

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

Current focus is stability and safety of the local-first workflow:

- preserving secret masking semantics
- keeping fake-mail dev tooling strictly gated
- maintaining alignment between backend, browser client, and macOS client
- continuing malformed-input hardening and endpoint-level fuzz coverage

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

### Main request flow

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

## Recent implementation status

- Route decomposition remains in place across runtime/models, settings, actions, summaries, and dev-tools modules.
- Router parity safeguards exist via router-context and route-decomposition tests.
- Fuzz tests exist for summary, settings/actions, and runtime/model malformed payload contracts.
- Full-stack validation scripts remain available in both shell and Python variants.

## Verification status

Previously available project-level validation includes:

- pytest suite under `tests/`
- route decomposition and router-context tests
- endpoint-focused fuzz tests for multiple route groups
- full-stack startup validation scripts
- repository hygiene checks

No commands were run as part of this STATUS.md normalisation beyond repository inspection.

## Risks and limitations

- Real IMAP/SMTP workflows involve real credentials and mailbox data; handling must remain conservative.
- Secret masking and masked-write semantics must not regress.
- Dev fake-mail endpoints must remain disabled unless explicitly enabled.
- Behaviour changes across backend/client boundaries require contract discipline.

## Pending tasks

- Continue broad malformed-input fuzzing for any remaining lightly covered route shapes.
- Keep browser and macOS client expectations aligned with backend response contracts.
- Keep hygiene checks current as packaging and release scripts evolve.

## Next steps

1. Extend endpoint fuzzing where payload/query contracts are still shallow.
2. Re-run full-stack validation after significant backend or client integration changes.
3. Continue keeping route tests aligned with any future route movement.

## Longer-term steps

1. Keep local-first onboarding reliable through dummy mode and deterministic fallback behaviour.
2. Strengthen cross-platform validation for backend and clients.
3. Preserve safe handling for live mailbox operations and provider integrations.

## Decisions

- Dummy mode remains the safe default for onboarding and local development.
- Provider failures should degrade gracefully to deterministic fallback summaries.
- Dev-only tooling remains explicit and gated.

---

Last updated: 2026-05-07 00:56
