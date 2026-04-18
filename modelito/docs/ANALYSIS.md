# Analysis: mapping BatLLM -> modelito and repo change recommendations

## Summary

This document summarizes the feature mapping between BatLLM and the extracted
`modelito` package, lists remaining gaps, and recommends concrete changes in
BatLLM and `mail_summariser` to best use the improved `modelito`.

## What `modelito` now provides (high level)

- Ollama lifecycle helpers: `ollama_service` (start/stop/pull/warm/check)
- Timeout catalog and estimator: `timeout.estimate_remote_timeout()`
- Provider: `OllamaProvider` updated to use service helpers and dynamic timeouts
- Connector: `OllamaConnector` with token-aware trimming, system-message support
- Config helpers and small packaging skeleton + basic tests and CI

## Gaps remaining vs BatLLM

- Ollama installer helper (BatLLM's installer detection/interactive flows) — `modelito` has a best-effort `install` CLI wrapper but not a full installer flow.
- Advanced timeout/catalog tuning: `modelito` has a compact estimator; BatLLM uses a richer catalog and keyword heuristics.
- Ollama model preload caching and model lifecycle policies (per-model warmers) — limited in `modelito`.
- psutil-based deep process analysis is implemented but may require platform-specific handling.

## Recommended changes in BatLLM

1. Switch local Ollama lifecycle calls to use `modelito.ollama_service` (small API differences: prefer `start_service/stop_service` and `start_detached_ollama_serve`).
2. Replace local timeout heuristics with `modelito.timeout.estimate_remote_timeout()` where appropriate; extend the catalog file if you need fine-grained tuning.
3. Use `modelito.connector.OllamaConnector` for conversation/history logic; migrate system-instruction file paths to connector config.
4. Add an integration test harness that runs `modelito` integration tests as part of BatLLM's CI when `ollama` is available.

## Recommended changes in mail_summariser repo

1. Replace inline Ollama helpers with `modelito` calls (already exercised in this branch).
2. Adopt the connector API for mailbox-specific conversation flows; use `max_history_tokens` to control prompt sizes for mobile/desktop clients.
3. Add `RUN_OLLAMA_INTEGRATION=1` optional workflow and document how to run integration tests locally.

## Next steps for full parity

- Expand the timeout catalog (`modelito/data/ollama_remote_timeout_catalog.json`) using BatLLM's catalog as a source of truth.
- Add optional `tiktoken` integration and improve token counting accuracy in the connector.
- Create a publishable package release for `modelito` and update downstream repos to depend on it as a versioned package.
