# Repository Report

Last updated: 2026-05-06

## Current state

The repository is currently organized around three actively used surfaces:

- FastAPI backend in `backend/`
- Browser client in `webapp/`
- macOS SwiftUI client in `macos-app/`

Key runtime characteristics:

- API entrypoint: `backend/app.py`
- Persistence: SQLite via `backend/db.py`
- Mail modes:
  - dummy in-memory mailbox
  - real IMAP/SMTP mailbox
  - dev fake-mail server endpoints (gated by `MAIL_SUMMARISER_ENABLE_DEV_TOOLS`)
- Summary generation:
  - provider abstraction in `backend/llm_provider_clients.py`
  - orchestration and fallback handling in `backend/summary_service.py`
- Runtime model control:
  - Ollama install/running checks and start/stop behavior in `backend/model_provider_service.py`
  - runtime/model route module in `backend/routers_runtime_models.py`

## Cleanup performed

Removed stale or generated remnants from version control:

- migration-era docs:
  - `docs/MIGRATION_PR.md`
  - `docs/MIGRATION_TO_MODELITO.md`
- generated metadata:
  - `mail_summariser.egg-info/`
- generated build outputs:
  - `dist/`
- stale release logs:
  - `release_artifacts/`
- stale calibration output:
  - `calibration_report.json`
- low-value docs and site assets:
  - `docs/CALIBRATION.md`
  - `docs/IMAP_TEST_PLAN.md`
  - `docs/TESTING_STRATEGY.md`
  - `docs/index.html`, `docs/site.css`, `docs/site.js`
  - legacy screenshot assets under `docs/assets/*.png`
- low-value utility scripts and isolated calibration test:
  - `scripts/calibrate_timeout_catalog.py`
  - `scripts/run_imap_test_plan.sh`
  - `scripts/run_with_local_modelito.sh`
  - `scripts/test_workflows.sh`
  - `tests/test_calibration_cli.py`

Local-only remnants removed from workspace:

- `temp.txt`
- `modelito/` (cache-only residue)
- local cache folders (`.pytest_cache/`, `__pycache__/`)

Ignore rules strengthened in `.gitignore` for these artifact classes.

## Architecture diagram (SVG)

![Architecture diagram](docs/assets/architecture.svg)

## Main request flow chart (SVG)

![Summary flow chart](docs/assets/flow-summary.svg)

## Suggested-next-steps status

1. Route decomposition: implemented for runtime/model routes (`backend/routers_runtime_models.py`) and mounted in `backend/app.py`.
2. CI artifact/migration guard: implemented via `scripts/check_repo_hygiene.sh` and enabled in `.github/workflows/ci.yml`.
3. Runtime/model smoke tests: implemented in `tests/test_runtime_model_endpoints.py`.
4. Single full-stack validation command: implemented in `scripts/validate_full_stack.sh`, CI-enabled, and exposed in `.vscode/tasks.json`.
5. Structured diagnostics logging: debug `print` calls replaced with logger-based messages in `backend/app.py`.

## Remaining opportunities

1. Continue route decomposition for settings, actions, summaries, and dev-tools endpoints.
2. Add startup validation on additional OS targets for release confidence (Linux/macOS matrix).
