# Testing Strategy

This strategy covers both the built-in dummy mailbox and the controlled IMAP/SMTP workflow used before testing against an external provider.

## Goals

- Verify summary generation and action workflows are stable.
- Verify API contracts and persistence behaviour are deterministic.
- Verify dummy-mode activity remains isolated from persistent SQLite state.
- Verify provider fallback behaviour is safe when dependencies are unavailable.
- Verify build artefacts start correctly on each release platform.

## Test Pyramid

1. Unit tests
- Focus: pure logic and service behaviour.
- Scope: `backend/summary_service.py`, `backend/mail_service.py` filtering, `backend/model_provider_service.py` parsing and fallback, `backend/db.py` CRUD helpers.
- Requirement: no network calls.

2. Integration tests
- Focus: FastAPI endpoint behaviour with an isolated SQLite database and the in-memory dummy sandbox.
- Scope: `/health`, `/runtime/*`, `/summaries`, `/settings`, `/logs`, `/actions/*`, `/admin/database/reset`, `/dev/fake-mail/*`, model endpoints.
- Requirement: run with deterministic fixtures and stubbed provider calls.

3. Contract and compatibility checks
- Focus: request/response schema stability for frontend and macOS client compatibility.
- Scope: Pydantic models and representative payload snapshots.
- Requirement: explicit assertions for required fields and error responses.

4. Smoke tests
- Focus: startup and critical path behaviour from built artefacts.
- Scope: start binary, call `/health`, verify `/runtime/status`, `/dev/fake-mail/status`, create summary, verify reset flow, verify fallback resilience.
- Requirement: same smoke flow in local validation and release CI.

## Readiness Gates Before External IMAP

All gates must pass before introducing an external IMAP account.

1. Unit test gate
- Target: stable pass rate for all service-level tests.
- Required checks: provider fallback logic, summary construction, settings masking, undo stack behaviour.

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
- Use the shared fake IMAP/SMTP server for controlled live-mail integration tests.
- Avoid reliance on external APIs, local Ollama daemon, or real mailbox state.

## IMAP Onboarding Checklist

After all gates pass, enable IMAP in a staged rollout:

1. Use a non-production test mailbox.
2. Enable read-only validation mode first.
3. Validate message search and summary output correctness.
4. Enable action endpoints only after read validations pass.
5. Keep rollback path available via fallback summariser and undo operations.
