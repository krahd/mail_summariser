modelito
=======

Lightweight LLM provider abstractions and connectors.

This small package provides:

- Provider interfaces (`LLMProvider`, `AsyncLLMProvider`)
- `OllamaProvider`, `OpenAIProvider`, `AnthropicProvider`
- `ollama_service` lifecycle helpers
- timeout estimation utilities
- a small `OllamaConnector` for conversation history & system messages

Install (editable during development):

```bash
pip install -e .
```

Note: This README is a minimal scaffold for packaging; expand docs as needed.
