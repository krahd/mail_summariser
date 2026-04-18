# Migration checklist to integrate `modelito` into BatLLM and other projects

1. Replace local Ollama lifecycle calls with `modelito.ollama_service` helpers.
2. Use `modelito.timeout.estimate_remote_timeout()` when making remote calls.
3. Swap direct provider instantiation to registry via `modelito.get_provider()`.
4. Add adapter shims in BatLLM for any config differences (system instruction paths, model name keys).
5. Add integration tests that run only when Ollama binary is present; skip otherwise.
