import importlib


def test_tokenizer_count_basic():
    # Ensure the tokenizer wrapper is importable and returns an int
    tok = importlib.import_module("modelito.tokenizer")
    cnt = tok.count_tokens("Hello world! This is a small test.")
    assert isinstance(cnt, int)
    assert cnt > 0
