# mail_summariser – Project Status

Last updated: 2026-05-06 17:37

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
  - Ollama install/running checks and full admin behavior (install/start/stop/serve/list pullable/pull/delete) in `backend/model_provider_service.py`
  - all Ollama admin lifecycle operations now delegated through `modelito==1.2.2` APIs
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
6. Route decomposition (settings/actions/summaries/dev-tools): implemented via
  - `backend/routers_settings.py`
  - `backend/routers_actions.py`
  - `backend/routers_summaries.py`
  - `backend/routers_devtools.py`
  - shared module resolver in `backend/router_context.py`
7. Startup validation matrix: implemented in `.github/workflows/ci.yml` as
  `startup-validation-matrix` on `ubuntu-latest`, `macos-latest`, and
  `windows-latest` using cross-platform `scripts/validate_full_stack.py`.
8. Router decomposition regression guards: implemented via
  - `tests/test_router_decomposition.py` (route registration contract)
  - `tests/test_router_context.py` (top-level vs package app-module resolution)
9. Router error-path behavior coverage: implemented via
  - `tests/test_router_error_paths.py` for settings, summaries, actions, and
    dev-tools failure/404 paths.
10. Property-based parser/validation fuzzing: implemented via
  - `tests/test_fuzz_summary_payloads.py` using Hypothesis to stress malformed
    `/summaries` payload shapes and assert handled outcomes (`200`, `400`, `422`)
    without server crashes.
11. Cross-endpoint payload fuzzing hardening: implemented via
  - `tests/test_fuzz_settings_actions_payloads.py` using Hypothesis to fuzz
    malformed payload contracts for `/settings`, `/settings/test-connection`,
    `/settings/dummy-mode`, `/actions/mark-read`, `/actions/tag-summarised`,
    and `/actions/email-summary` with assertions that responses remain handled
    (`200`, `400`, `404`, `422`) and do not surface server crashes.
12. Targeted remaining-route fuzzing hardening: implemented via
  - `tests/test_fuzz_settings_actions_payloads.py` coverage for
    `/actions/undo`, `/actions/undo/logs/{log_id}`, `/logs` query shapes, and
    `/admin/database/reset` confirmation edge cases and malformed payloads.
13. Runtime/model malformed-contract fuzzing hardening: implemented via
  - `tests/test_fuzz_runtime_models_payloads.py` for `/runtime/status`,
    `/runtime/ollama/start`, `/runtime/shutdown`, `/models/options`, and
    `/models/catalog` query/body shape stress coverage.

## Remaining opportunities

1. Add property-based fuzzing for dev fake-mail endpoint payload/query contracts
  (`/dev/fake-mail/status`, `/dev/fake-mail/start`, `/dev/fake-mail/stop`) to
  complete malformed input hardening across all backend mutable/control routes.
