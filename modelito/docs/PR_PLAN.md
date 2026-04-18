# PR plan to migrate BatLLM / mail_summariser to use `modelito`

1. Create a feature branch: `modelito/extract-ollama`
2. Add `modelito` as a git submodule or dependency in the BatLLM repo (or add as a package install).
3. Replace direct `ollama_service` imports with `from modelito import ollama_service`.
4. Update LLM connectors to use `modelito.connector.OllamaConnector` and provider registry.
5. Run BatLLM tests, add integration tests that assert the `modelito` provider lifecycle functions behave as expected.
6. Submit PR with changelog and migration notes; request reviewers from platform team.

## Considerations

- Keep backward-compatible shims for any config keys changed (e.g., `modelName` vs `model`).
- Add conditional integration tests that run only when `ollama` binary is available.
