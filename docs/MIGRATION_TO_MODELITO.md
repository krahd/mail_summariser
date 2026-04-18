Migration to `modelito` as external library
==========================================

This document outlines steps to migrate `mail_summariser` (or BatLLM)
to consume `modelito` as a published dependency rather than an in-repo copy.

1. Publish `modelito` to your package index (TestPyPI for RC, PyPI for release).
2. Update `mail_summariser/pyproject.toml` to depend on `modelito = "^0.1.0"`.
3. Remove the local `modelito/` package directory from the repo.
4. Replace imports that reference internal utilities with `from modelito import ...`.
   - `ensure_ollama_running` is now available as `modelito.ensure_ollama_running`
   - `OllamaConnector`, `OllamaProvider` and `timeout.estimate_remote_timeout` are exported
5. Run the test suite and fix any minor API differences (mostly naming/kwargs).
6. Optionally, pin a release candidate for downstream testing before final release.

Notes:
- Keep the calibration script in CI if you want environment-specific timeouts.
- Consider adding a small compatibility shim in the downstream repo if you need
  to maintain old helper names during incremental migration.
