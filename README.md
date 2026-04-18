# mail_summariser

This branch extracts provider-specific LLM access behind a small client layer and hardens the backend mail flow around three modes:

- dummy mode for local/demo use
- real IMAP/SMTP mode
- developer fake-mail mode for end-to-end tests

## What changed

- cleaned up provider abstractions for OpenAI, Anthropic, and Ollama
- made summary generation validate responses with a sentinel and fall back safely
- fixed connection testing so it exercises the actual configured mail path
- fixed tagging/undo behaviour to use the saved `summarisedTag` setting rather than a hard-coded default
- simplified app startup and state handling so tests can isolate their own database file cleanly
- documented the backend flow and test strategy

## Development

Create a virtual environment and install the project with dev dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
```

Run tests:

```bash
pytest
```

Run the API locally:

```bash
uvicorn backend.app:app --reload --port 8766
```

## Notes on provider credentials

The API masks stored secrets on reads. When saving settings, masked values are ignored so existing secrets remain stored.

## External LLM helper: modelito

This project now consumes the external `modelito` package (v0.1.1+) for lightweight LLM helpers — token counting, small Ollama HTTP helpers, and timeout/catalog utilities.

Install the published package (preferred) or use the dev environment which pulls it in automatically:

```bash
# Preferred: install the released package
pip install modelito==0.1.1 --extra-index-url https://test.pypi.org/simple || true

# Or install the project in development mode (pulls modelito as a dependency)
pip install -e '.[dev]'
```

See the `modelito` release notes for details and compatibility shims: https://github.com/krahd/modelito/releases

## Test coverage

The test suite covers:

- provider-library integration and fallbacks
- provider-specific system messages
- dummy-mode mail flow, undo, and job isolation
- live IMAP/SMTP flow against a controllable fake local server
- developer fake-mail endpoints
