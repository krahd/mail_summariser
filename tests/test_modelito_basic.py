import importlib

from modelito import OllamaProvider


def test_timeout_estimator_basic():
    tmod = importlib.import_module('modelito.timeout')
    assert isinstance(tmod.estimate_remote_timeout('llama3.2:latest'), int)
    assert tmod.estimate_remote_timeout(
        'smollm_v1') <= tmod.estimate_remote_timeout('llama3.2:latest')


def test_ollama_provider_list_models_no_server():
    prov = OllamaProvider()
    models = prov.list_models()
    assert isinstance(models, list)


def test_connector_history():
    conn_mod = importlib.import_module('modelito.connector')
    prov = OllamaProvider()
    conn = conn_mod.OllamaConnector(prov, shared_history=False)
    conv = 'c1'
    conn.add_to_history(conv, 'user', 'hello')
    conn.add_to_history(conv, 'assistant', 'hi')
    hist = conn.get_history(conv)
    assert len(hist) == 2
