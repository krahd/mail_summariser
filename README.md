# mail_summariser

mail_summariser is a local-first email workflow with a FastAPI backend, a browser client, and a macOS SwiftUI client.

It supports:

- a resettable sample mailbox for local onboarding and fast validation
- live IMAP/SMTP mode for real inbox workflows
- provider-backed summaries via Ollama, OpenAI, or Anthropic
- deterministic fallback summaries when providers are unavailable or return invalid output

## Project layout

- `backend/`: FastAPI app, mail services, provider integration, SQLite persistence
- `webapp/`: static browser UI (`index.html`, `app.js`, `api.js`)
- `macos-app/`: SwiftUI desktop client
- `tests/`: pytest suite for backend behavior and integration boundaries
- `scripts/`: build, release packaging, hygiene checks, and full-stack validation

## Quick start

### Backend

```bash
./start_backend.sh
```

Backend defaults to `http://127.0.0.1:8766`.

### Web app

Serve the `webapp/` folder with any static server, for example:

```bash
python -m http.server 8000 --directory webapp
```

### Tests

```bash
pytest -q
```

### Full-stack validation

```bash
./scripts/validate_full_stack.sh
```

Cross-platform equivalent:

```bash
python scripts/validate_full_stack.py
```

CI runs startup validation in a matrix on Linux, macOS, and Windows.

### Rendered UI regression

Install the Playwright browser once, then run the rendered browser smoke test:

```bash
python -m playwright install chromium
python scripts/validate_rendered_ui.py
```

This starts isolated backend and static-web instances, verifies the sample mailbox first-run flow, empty-result handling, settings/live-mode toggle, and a mobile layout check. Screenshots are written under the system temp directory.

### Repository hygiene guard

```bash
./scripts/check_repo_hygiene.sh
```

## Configuration notes

- Runtime settings are persisted in SQLite (`backend/data/mail_summariser.sqlite3` by default).
- The backend setting is still named `dummyMode` for API compatibility, but user-facing clients present it as the sample mailbox.
- Secrets are masked on reads from `/settings`.
- Writing masked sentinel values (`__MASKED__`) does not overwrite stored secrets.

## Dependency note

The project depends on the external `modelito` package for LLM helper utilities.
