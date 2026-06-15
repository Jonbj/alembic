"""Test per-model LLM timeout configuration."""
from unittest.mock import patch


def test_kimi_client_reads_timeout_from_config():
    """OllamaKimiClient deve usare OLLAMA_KIMI_TIMEOUT_SECONDS da config."""
    with patch.dict("os.environ", {"OLLAMA_KIMI_TIMEOUT_SECONDS": "30"}):
        import importlib
        import src.config as cfg_mod
        importlib.reload(cfg_mod)
        import src.llm.client as client_mod
        importlib.reload(client_mod)
        client = client_mod.OllamaKimiClient()
        assert client._OLLAMA_TIMEOUT == 30


def test_qwen_client_reads_timeout_from_config():
    """OllamaQwen35Client deve usare OLLAMA_QWEN_TIMEOUT_SECONDS da config."""
    with patch.dict("os.environ", {"OLLAMA_QWEN_TIMEOUT_SECONDS": "45"}):
        import importlib
        import src.config as cfg_mod
        importlib.reload(cfg_mod)
        import src.llm.client as client_mod
        importlib.reload(client_mod)
        client = client_mod.OllamaQwen35Client()
        assert client._OLLAMA_TIMEOUT == 45


def test_default_timeout_is_90():
    """Senza env var, il default deve essere 90s."""
    with patch.dict("os.environ", {}, clear=False):
        import importlib
        import src.config as cfg_mod
        importlib.reload(cfg_mod)
        import src.llm.client as client_mod
        importlib.reload(client_mod)
        client = client_mod.OllamaKimiClient()
        assert client._OLLAMA_TIMEOUT == 90


def test_deepseek_client_reads_timeout_from_config():
    """OllamaDeepseekClient deve usare OLLAMA_DEEPSEEK_TIMEOUT_SECONDS da config."""
    with patch.dict("os.environ", {"OLLAMA_DEEPSEEK_TIMEOUT_SECONDS": "60"}):
        import importlib
        import src.config as cfg_mod
        importlib.reload(cfg_mod)
        import src.llm.client as client_mod
        importlib.reload(client_mod)
        client = client_mod.OllamaDeepseekClient()
        assert client._OLLAMA_TIMEOUT == 60


def test_glm_client_reads_timeout_from_config():
    """OllamaGlmClient deve usare OLLAMA_GLM_TIMEOUT_SECONDS da config."""
    with patch.dict("os.environ", {"OLLAMA_GLM_TIMEOUT_SECONDS": "120"}):
        import importlib
        import src.config as cfg_mod
        importlib.reload(cfg_mod)
        import src.llm.client as client_mod
        importlib.reload(client_mod)
        client = client_mod.OllamaGlmClient()
        assert client._OLLAMA_TIMEOUT == 120
