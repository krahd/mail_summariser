# Testing Strategy (Pre-IMAP)

This strategy is designed to prove the application behavior before connecting to a real IMAP account.

## Goals

- Verify summary generation and action workflows are stable.
- Verify API contracts and persistence behavior are deterministic.
- Verify provider fallback behavior is safe when dependencies are unavailable.
- Verify build artifacts start correctly on each release platform.

## Test Pyramid

1. Unit tests
- Focus: pure logic and service behavior.
- Scope: `backend/summary_service.py`, `backend/mail_service.py` filtering, `backend/model_provider_service.py` parsing and fallback, `backend/db.py` CRUD helpers.
- Requirement: no network calls.

2. Integration tests
- Focus: FastAPI endpoint behavior with an isolated SQLite database.
- Scope: `/health`, `/summaries`, `/settings`, `/logs`, `/actions/*`, model endpoints.
- Requirement: run with deterministic fixtures and stubbed provider calls.

3. Contract and compatibility checks
- Focus: request/response schema stability for frontend and macOS client compatibility.
- Scope: Pydantic models and representative payload snapshots.
- Requirement: explicit assertions for required fields and error responses.

4. Smoke tests
- Focus: startup and critical path behavior from built artifacts.
- Scope: start binary, call `/health`, create summary, verify fallback resilience.
- Requirement: same smoke flow in local validation and release CI.

## Readiness Gates Before Real IMAP

All gates must pass before introducing a real IMAP account.

1. Unit test gate
- Target: stable pass rate for all service-level tests.
- Required checks: provider fallback logic, summary construction, settings masking, undo stack behavior.

2. Integration test gate
- Target: all API endpoints covered for successful and failure responses.
- Required checks: auth header enforcement, invalid payload handling, settings persistence, job persistence.

3. Smoke gate
- Target: packaged binaries run and answer `/health` on macOS, Linux, and Windows.
- Required checks: startup, request handling, process shutdown.

4. Release gate
- Target: tag build must fail if test jobs fail.
- Required checks: matrix build + smoke verification across all target OS runners.

## Deterministic Test Data

- Use fixture message sets with stable IDs and timestamps.
- Use mocked provider responses for Ollama, OpenAI, and Anthropic paths.
- Use temporary SQLite files or in-memory DB for test runs.
- Avoid reliance on external APIs, local Ollama daemon, or real mailbox state.

## IMAP Onboarding Checklist

After all gates pass, enable IMAP in a staged rollout:

1. Use a non-production test mailbox.
2. Enable read-only validation mode first.
3. Validate message search and summary output correctness.
4. Enable action endpoints only after read validations pass.
5. Keep rollback path available via fallback summarizer and undo operations.
