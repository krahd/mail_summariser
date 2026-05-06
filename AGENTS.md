# AGENTS Guide

This file is a machine-oriented operating guide for AI coding agents (Codex, Claude, and similar).

## Purpose

Maintain and evolve this repository without reintroducing stale artifacts or migration-era leftovers.

## Repo map

- `backend/`: FastAPI backend and core domain logic
- `webapp/`: static browser client
- `macos-app/`: SwiftUI desktop client
- `tests/`: pytest suite
- `scripts/`: build/package and operational validation helpers
- `.github/workflows/`: CI and release automation

## Ground rules for agents

1. Keep generated artifacts out of git.
2. Prefer small, focused edits over broad rewrites.
3. Preserve API contracts unless explicitly asked to change them.
4. Update docs when behavior changes.
5. Run tests relevant to the touched area before finishing.
6. Keep `STATUS.md` up to date whenever implementation status, architecture status, or validation scope changes.
7. Ensure `STATUS.md` always has an accurate `Last updated` date and time reflecting the latest substantive change.

## Never commit these

- `dist/`
- `release_artifacts/`
- `*.egg-info/`
- `__pycache__/`, `.pytest_cache/`, `.DS_Store`
- temporary scratch files

## Backend architecture summary

- App entrypoint and router assembly: `backend/app.py`
- Router context resolver for test/runtime module parity: `backend/router_context.py`
- Runtime/model domain router: `backend/routers_runtime_models.py`
- Settings/admin routes: `backend/routers_settings.py`
- Summary/message routes: `backend/routers_summaries.py`
- Action/log/undo routes: `backend/routers_actions.py`
- Dev fake-mail routes: `backend/routers_devtools.py`
- Settings/defaults: `backend/config.py`
- Storage: `backend/db.py`
- Mail transport and search: `backend/mail_service.py`
- Summary orchestration/fallback: `backend/summary_service.py`
- Provider runtime controls: `backend/model_provider_service.py`
- Dev fake-mail harness: `backend/fake_mail_server.py`

## Safe edit workflow for agents

1. Read impacted modules and tests first.
1. Search for all call sites before changing function signatures.
1. Implement minimal code change.
1. Update/add tests.
1. Run:

```bash
pytest -q
```

1. If touching route wiring or app-module resolution, also run:

```bash
pytest -q tests/test_router_decomposition.py tests/test_router_context.py
```

1. If touching web client behavior, also validate the API contract used by `webapp/api.js`.

## Common commands

```bash
# Start backend
./start_backend.sh

# Start web client static host
python -m http.server 8000 --directory webapp

# Run full tests
pytest -q

# Repository hygiene guard
./scripts/check_repo_hygiene.sh

# Full-stack startup validation
./scripts/validate_full_stack.sh

# Cross-platform full-stack startup validation
python scripts/validate_full_stack.py

# Build backend binary (platform-specific)
python3 scripts/build_backend_binary.py --platform macos --arch arm64
```

## Review checklist for pull requests

1. No generated/build/cache artifacts added.
2. No references to old migration states unless intentionally reintroduced.
3. Tests pass for changed modules.
4. README and relevant docs reflect current behavior.
5. Public endpoints remain backward compatible, or breaking changes are explicit.

## Compatibility note

This document is plain Markdown, deterministic, and tool-agnostic so it can be consumed by Codex-style and Claude-style coding agents.
