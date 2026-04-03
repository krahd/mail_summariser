# Mail Summariser (macOS + Web)

Mail Summariser is a local-first email workflow assistant. It helps you find messages, generate concise actionable summaries, and apply follow-up actions from one interface.

## What the project does

- Collects email search criteria (keyword, sender, recipient, tags, unread/read flags, and logical filters)
- Produces a short summary from matched messages using a selectable LLM provider
- Supports local and remote providers:
	- local Ollama models
	- OpenAI models
	- Anthropic models
- Lets you run post-summary actions such as mark-as-read, add/remove tags, email summary, and undo
- Persists app settings, logs, and summary jobs in SQLite so behaviour is reproducible between sessions

## How it works

1. The frontend (web or macOS) sends search criteria to the FastAPI backend.
2. The backend fetches message data (currently via demo data scaffolding, with IMAP integration planned).
3. The backend builds a provider-agnostic summarisation prompt and calls the selected model provider.
4. Provider responses are validated; if they are unavailable or invalid, the backend falls back to a deterministic built-in summariser.
5. The backend returns summary output plus message metadata, and records logs/jobs for traceability.

Starter project with a Python backend, a native macOS GUI, and a new browser-based web client.

## Structure

- `macos-app/`: SwiftUI source files for the native macOS app
- `backend/`: FastAPI backend with persisted settings, logs, jobs, and undo history
- `webapp/`: Static web client served by the backend at `/web`

## Backend quick start

```bash
cd backend
./start_backend
```

Then visit:
- `http://127.0.0.1:8766/docs`
- `http://127.0.0.1:8766/web`

Environment variables for browser client support:
- `ALLOWED_ORIGINS`: comma-separated origins for CORS. Defaults include local Vite and local backend URLs.
- `API_KEY`: optional API key. When set, all API routes except docs/health/web static require this key.
- `API_KEY_HEADER`: request header used for API key (default: `X-API-Key`).

LLM settings:
- `LLM_PROVIDER`: one of `ollama`, `openai`, `anthropic`.
- `OPENAI_API_KEY`: optional OpenAI key used for OpenAI provider.
- `ANTHROPIC_API_KEY`: optional Anthropic key used for Anthropic provider.
- `LLM_API_KEY`: legacy shared key fallback (kept for backward compatibility).
- `OLLAMA_HOST`: local Ollama endpoint (default `http://127.0.0.1:11434`).
- `OLLAMA_AUTO_START`: `true`/`false`; if true the backend will attempt to start Ollama automatically.
- `MODEL_NAME`: selected model name for the active provider.

## macOS app quick start

Open `MailSummariser.xcodeproj` in Xcode and run the `MailSummariser` scheme.

The app defaults to the backend at `http://127.0.0.1:8766`.

## Web app quick start

1. Start backend from project root:

```bash
./start_backend.sh
```

2. Open:

```text
http://127.0.0.1:8766/web
```

3. (Optional) If backend auth is enabled via `API_KEY`, open `Settings` and enter the **Backend API Key** field.

## Backend smoke test

Run an end-to-end API smoke test against a running backend:

```bash
./scripts/smoke_test_backend.sh
```

Optional custom base URL:

```bash
./scripts/smoke_test_backend.sh http://127.0.0.1:8766
```

If API key auth is enabled:

```bash
API_KEY=your-key ./scripts/smoke_test_backend.sh
```

## Model Provider UX

The settings screen supports both remote and local models:
- `Ollama (local)`: backend can auto-start Ollama and list locally available models.
- `OpenAI` / `Anthropic`: shows suggested model names and stores provider-specific keys in app settings.

There are now two different key types in the UI:
- `Backend API Key`: used only for backend route authentication (`X-API-Key` header). Stored in browser localStorage.
- `Provider API Keys` (OpenAI/Anthropic): used only for LLM inference. Stored in backend settings and returned masked.

For non-technical users, the recommended default is:
1. Keep provider on Ollama.
2. Keep auto-start enabled.
3. Click "Refresh Available Models" and select one.

The app now supports provider-based summarization:
- `ollama`: local inference via Ollama API.
- `openai`: remote inference via OpenAI Chat Completions.
- `anthropic`: remote inference via Anthropic Messages API.

If the selected provider fails (missing key, service unavailable, etc.), the backend falls back to the built-in demo summarizer and logs a warning so the user still gets a result.

### Downloading Ollama models from the app

In Settings:
1. Click `Discover Models` to fetch downloadable model names from the Ollama public catalog.
2. Pick a model from `Discover Downloadable Ollama Models`.
3. Click `Download Selected Model`.

The backend will ensure Ollama is running (if auto-start is enabled), then trigger `ollama pull` in the background.

## Notes

This is an MVP scaffold.

Current backend behavior:
- stores settings in SQLite
- stores summary jobs in SQLite
- stores logs in SQLite
- supports a basic undo stack
- uses **demo mail data** instead of real IMAP

Next step after this scaffold:
- implement real IMAP search in `backend/mail_service.py`
- implement real LLM summary generation in `backend/summary_service.py`
- wire MailMate-specific send/compose helpers if desired
