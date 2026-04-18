from modelito import OllamaConnector
from modelito.ollama import OllamaProvider


def test_token_trimming_behavior():
    prov = OllamaProvider()
    # small token budget to force trimming
    conn = OllamaConnector(prov, max_history_messages=50, max_history_tokens=20)
    conv = "convA"
    conn.set_system_message("You are a helpful assistant.")
    # add a few small messages
    conn.add_to_history(conv, "user", "Hello")
    conn.add_to_history(conv, "assistant", "Hi")
    conn.add_to_history(
        conv, "user", "This is a longer user message that should count against tokens")
    hist = conn.get_history(conv)
    # total tokens should be <= configured max_history_tokens
    total_tokens = conn._total_tokens(hist)
    assert conn.max_history_tokens is not None and total_tokens <= conn.max_history_tokens
