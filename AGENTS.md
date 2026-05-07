# AGENTS.md

Repository instructions for AI coding agents working in this project.

This file is the durable source of truth for GitHub Copilot, OpenAI Codex, Claude Code, and compatible coding agents. Read it before making changes.

## 1: Non-negotiable rules

- Keep `STATUS.md` accurate at all times.
- `STATUS.md` must exist in the repository root.
- Do not finish a task that changes the project without reviewing and, when needed, updating `STATUS.md`.
- Do not invent project facts. Inspect the repository and record uncertainty explicitly.
- Do not overwrite user work or unrelated changes.
- Do not commit secrets, credentials, tokens, private keys, local environment files, mail data, generated artefacts, or local SQLite databases.
- Prefer small, focused changes over broad rewrites.
- Verify meaningful changes with the narrowest reliable command available.
- Do not claim tests passed unless they were actually run.

## 2: Communication style

Use terse, factual, technical communication. Do not use playful, whimsical, cute, decorative, or filler progress phrases such as "combobulating", "cooking", "thinking...", "working on it", "let me dive in", "I'll get started", or "working my magic".

Allowed status-update style: "Reading files." "Found the issue." "Applying patch." "Tests passed." "Tests failed: <reason>."

No jokes, metaphors, fake enthusiasm, anthropomorphising, or decorative progress messages. Prefer concise present-tense technical updates. Use British English for prose documentation unless the repository consistently uses another variant.

## 3: Standard work loop

1. Read this file and `STATUS.md` before editing.
2. Inspect relevant files, docs, tests, scripts, and CI workflows.
3. Identify the smallest safe change.
4. Search call sites before changing API routes, schemas, settings, database behaviour, provider contracts, or client assumptions.
5. Make focused edits.
6. Run relevant verification when possible.
7. Update documentation when behaviour, setup, architecture, commands, or public APIs change.
8. Update `STATUS.md` if project state changed.
9. Report changed files, verification, and remaining issues.

## 4: Project-specific map

### 4.1: Project shape

- Purpose: local-first email workflow with provider-backed summaries.
- Runtime surfaces: FastAPI backend, browser client, macOS SwiftUI client, scripts, CI validation.
- Main modes: dummy mailbox, live IMAP/SMTP mailbox, gated dev fake-mail tools.
- LLM providers: Ollama, OpenAI, Anthropic, deterministic fallback, and modelito helper utilities.

### 4.2: Important paths

- `README.md`: human-facing overview.
- `STATUS.md`: complete current project status report; mandatory upkeep.
- `backend/app.py`: FastAPI entrypoint and route mounting.
- `backend/db.py`: SQLite persistence.
- `backend/summary_service.py`: summary orchestration and fallback handling.
- `backend/llm_provider_clients.py`: provider abstraction.
- `backend/model_provider_service.py`: model provider and Ollama runtime checks.
- `backend/routers_*.py`: decomposed API route modules.
- `backend/router_context.py`: shared app-module resolution.
- `webapp/`: static browser UI.
- `macos-app/`: SwiftUI desktop client.
- `tests/`: pytest coverage.
- `scripts/validate_full_stack.py` and `.sh`: full-stack validation.
- `scripts/check_repo_hygiene.sh`: generated artefact guard.

### 4.3: Safety invariants

- Do not expose or log real mailbox secrets or message contents unnecessarily.
- Preserve masking semantics for secrets returned from settings routes.
- Writing masked sentinel values such as `__MASKED__` must not overwrite stored secrets.
- Dev fake-mail endpoints must remain gated by `MAIL_SUMMARISER_ENABLE_DEV_TOOLS`.
- Dummy mode must remain safe for onboarding and tests.
- Live IMAP/SMTP behaviour must avoid destructive mailbox operations unless explicitly designed and documented.

## 5: STATUS.md maintenance

`STATUS.md` is mandatory project state, not optional documentation.

Required timestamp line near the top:

```text
Last updated: YYYY-MM-DD HH:MM
```

Use 24-hour local time. If no other timezone is specified, use `America/Montevideo`. Duplicate the exact same line as the final line at the bottom of `STATUS.md`. Update both lines together.

`STATUS.md` must be a complete current snapshot, not a changelog. Include relevant sections for purpose, current state, active focus, architecture, setup/run instructions, configuration, important files, recent changes, tests, risks, pending tasks, next steps, longer-term steps, and decisions.

## 6: Diagrams in STATUS.md

Include useful inline SVG architecture and flow diagrams when the structure is meaningful enough. Keep text inside boxes and canvas bounds. Keep arrows out of unrelated boxes and labels. Prefer generous spacing and simple SVG primitives.

## 7: Validation

Typical validation commands:

```bash
pytest -q
./scripts/validate_full_stack.sh
python scripts/validate_full_stack.py
./scripts/check_repo_hygiene.sh
```

Run the narrowest relevant checks first. Record tests not run when relevant.

## 8: Final response requirements

When finishing a task, report concisely: what changed, files changed, verification commands and results, whether `STATUS.md` was updated, and remaining issues or follow-up work.
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
