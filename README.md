# Mail Summariser

Mail Summariser is a local-first email assistant with a FastAPI backend, a SwiftUI macOS client, and a browser client. It searches messages, generates concise summaries, and supports post-summary actions while keeping settings and job history in SQLite.

## Project status

- Current release target: `v0.0.3`
- Mail source: demo dataset only (real IMAP integration is planned, not enabled yet)
- Cross-platform release artifacts: backend binaries for macOS, Linux, and Windows
- Desktop client release artifact: macOS `.app`

## Architecture

1. Frontend clients (web or macOS) send search criteria to the backend.
2. Backend retrieves message candidates from demo data.
3. Backend builds summarization input and calls selected provider.
4. If provider output is unavailable or invalid, backend falls back to deterministic built-in summarization.
5. Backend stores settings, logs, jobs, and undo events in SQLite for traceability.

## Repository structure

- `backend/`: FastAPI service, summary logic, provider integration, persistence
- `webapp/`: static browser UI served at `/web`
- `macos-app/`: SwiftUI macOS application source
- `scripts/`: smoke tests and build scripts
- `.vscode/tasks.json`: local tasks for backend startup and artifact creation

## Prerequisites

- Python 3.10+
- macOS + Xcode (for macOS app build)
- Optional: Ollama for local model inference

## Quick start

From repository root:

```bash
./start_backend.sh
```

Open:

- `http://127.0.0.1:8766/docs`
- `http://127.0.0.1:8766/web`

### macOS app

Open `MailSummariser.xcodeproj` in Xcode and run scheme `MailSummariser`.

## Configuration

Core environment variables:

- `ALLOWED_ORIGINS`: comma-separated CORS origins
- `API_KEY`: optional backend API key
- `API_KEY_HEADER`: auth header name (default `X-API-Key`)
- `LLM_PROVIDER`: `ollama`, `openai`, or `anthropic`
- `OPENAI_API_KEY`: OpenAI key
- `ANTHROPIC_API_KEY`: Anthropic key
- `OLLAMA_HOST`: Ollama endpoint (default `http://127.0.0.1:11434`)
- `OLLAMA_AUTO_START`: auto-start Ollama when possible
- `MODEL_NAME`: selected provider model
- `MAIL_SUMMARISER_DATA_DIR`: optional override for SQLite/log storage location

## Testing

### Smoke test

Run the backend smoke checks against a running instance:

```bash
./scripts/smoke_test_backend.sh
```

With API key enabled:

```bash
API_KEY=your-key ./scripts/smoke_test_backend.sh
```

### Pre-IMAP confidence strategy

The full testing strategy is documented in [docs/TESTING_STRATEGY.md](docs/TESTING_STRATEGY.md) and is designed to prove functional correctness before connecting a real IMAP account.

Release gate summary:

1. Unit and integration checks must pass.
2. Platform binary startup smoke checks must pass on macOS, Linux, and Windows.
3. Release workflow publishes only when matrix jobs succeed.

## Binary builds

VS Code task labels:

- `Build Backend Binary (macOS)`
- `Build Backend Binary (Linux)`
- `Build Backend Binary (Windows)`
- `Build macOS App Archive`

Direct script usage:

```bash
python3 scripts/build_backend_binary.py --platform macos --arch arm64
python3 scripts/build_backend_binary.py --platform linux --arch x64
python3 scripts/build_backend_binary.py --platform windows --arch x64
./scripts/build_macos_app.sh
```

Note: backend binaries must be built on matching host OS (or CI matrix runners).

## Release process

Tag convention: `v<semver>` (example: `v0.0.3`).

On tag push, GitHub Actions builds and publishes release assets for:

- `mail-summariser-backend-macos-*`
- `mail-summariser-backend-linux-*`
- `mail-summariser-backend-windows-*.exe`
- macOS app archive artifact

Packaged backend downloads are also published for easier installation:

- macOS: `mail-summariser-backend-macos-arm64.tar.gz`
- Linux: `mail-summariser-backend-linux-x64.tar.gz`
- Windows: `mail-summariser-backend-windows-x64.zip`

## Known limitations

- IMAP integration is not yet enabled.
- Windows/Linux desktop native apps are not included in `v0.0.3`.
- Provider-dependent quality varies by selected model and availability.
