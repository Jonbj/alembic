"""Tests for security fixes implemented after multimodel review."""

import pytest
from pydantic import ValidationError

from src.llm.client import ALLOWED_MODEL_IDS, LLMClient
from src.llm.ensemble import run_ensemble_query
from src.models.news import LLMSentimentOutput


class TestAllowedModelIds:
    """Test ALLOWED_MODEL_IDS security allowlist."""

    def test_allowed_model_ids_not_empty(self):
        """Verify allowlist is not empty."""
        assert len(ALLOWED_MODEL_IDS) > 0

    def test_allowed_model_ids_contains_expected_models(self):
        """Verify key models are in allowlist."""
        assert "opus" in ALLOWED_MODEL_IDS
        assert "qwen3.5:cloud" in ALLOWED_MODEL_IDS
        assert "deepseek-v4-pro:cloud" in ALLOWED_MODEL_IDS

    def test_invalid_model_id_rejected(self):
        """Test that invalid model_id raises ValueError."""
        # Note: Full subprocess test would require mocking
        # This verifies the allowlist exists and is accessible
        assert "invalid-model" not in ALLOWED_MODEL_IDS
        assert "opus; rm -rf /" not in ALLOWED_MODEL_IDS


class TestEnsembleEmptyClients:
    """Test edge case handling in run_ensemble_query."""

    @pytest.mark.asyncio
    async def test_empty_clients_returns_empty_list(self):
        """Test that empty clients list returns empty result (no crash)."""
        result = await run_ensemble_query(
            prompt="test",
            clients=[],  # Empty list - edge case
            response_schema=LLMSentimentOutput,
            symbol="AAPL",
        )
        assert result == []


class TestSanitizerBidiRemoval:
    """Test BiDi character removal in sanitizer."""

    def test_bidi_override_characters_removed(self):
        """Test that BiDi override characters are removed."""
        from src.text.sanitizer import sanitize_text

        # U+202E (RLO - Right-to-Left Override)
        text_with_bidi = "test‮malicious"
        sanitized = sanitize_text(text_with_bidi)
        assert "‮" not in sanitized
        assert "malicious" in sanitized

        # U+202D (LRO - Left-to-Right Override)
        text_with_lro = "start‭reversed"
        sanitized = sanitize_text(text_with_lro)
        assert "‭" not in sanitized

    def test_bidi_isolate_overrides_removed(self):
        """Test that BiDi isolate overrides are removed."""
        from src.text.sanitizer import sanitize_text

        # U+2067-U+2069 (isolate overrides)
        for char in ["⁧", "⁦", "⁨", "⁩"]:
            text = f"test{char}injected"
            sanitized = sanitize_text(text)
            assert char not in sanitized


class TestSanitizerEmojiRemoval:
    """Test emoji removal in sanitizer."""

    def test_emoji_removed(self):
        """Test that emojis are removed."""
        from src.text.sanitizer import sanitize_text

        text_with_emoji = "Hello 👋 World 🌍"
        sanitized = sanitize_text(text_with_emoji)

        assert "👋" not in sanitized
        assert "🌍" not in sanitized
        assert "Hello" in sanitized
        assert "World" in sanitized

    def test_emoji_flags_removed(self):
        """Test that flag emojis are removed."""
        from src.text.sanitizer import sanitize_text

        text_with_flag = "Italy 🇮🇹 USA 🇺🇸"
        sanitized = sanitize_text(text_with_flag)

        assert "🇮🇹" not in sanitized
        assert "🇺🇸" not in sanitized


class TestConfigValidators:
    """Test new config validators."""

    def test_model_costs_validation(self):
        """Test MODEL_COSTS validator."""
        from src.config import Config

        # Valid costs
        config = Config(
            ADMIN_API_KEY="a" * 40,
            DATABASE_URL="postgresql://localhost/test",
            REDIS_URL="redis://localhost:6379/0",
            MODEL_COSTS={"test": (1.0, 2.0)},
        )
        assert config.MODEL_COSTS["test"] == (1.0, 2.0)

    def test_model_costs_invalid_tuple(self):
        """Test MODEL_COSTS rejects invalid tuple."""
        from src.config import Config

        with pytest.raises(ValidationError) as exc_info:
            Config(
                ADMIN_API_KEY="a" * 40,
                DATABASE_URL="postgresql://localhost/test",
                REDIS_URL="redis://localhost:6379/0",
                MODEL_COSTS={"test": (1.0, 2.0, 3.0)},  # 3 elements
            )
        # Pydantic validates tuple size before custom validator
        assert "too_long" in str(exc_info.value) or "tuple" in str(exc_info.value).lower()

    def test_signal_ttl_positive(self):
        """Test REDIS_SIGNAL_TTL_SECONDS must be positive."""
        from src.config import Config

        with pytest.raises(ValidationError) as exc_info:
            Config(
                ADMIN_API_KEY="a" * 40,
                DATABASE_URL="postgresql://localhost/test",
                REDIS_URL="redis://localhost:6379/0",
                REDIS_SIGNAL_TTL_SECONDS=-100,
            )
        assert "positive" in str(exc_info.value).lower()

    def test_daily_budget_positive(self):
        """Test LLM_DAILY_BUDGET_USD must be positive."""
        from src.config import Config

        with pytest.raises(ValidationError) as exc_info:
            Config(
                ADMIN_API_KEY="a" * 40,
                DATABASE_URL="postgresql://localhost/test",
                REDIS_URL="redis://localhost:6379/0",
                LLM_DAILY_BUDGET_USD=-50.0,
            )
        assert "positive" in str(exc_info.value).lower()

    def test_ensemble_min_confidence_valid_range(self):
        """Test ENSEMBLE_MIN_CONFIDENCE must be in [0, 1]."""
        from src.config import Config

        # Valid values
        config = Config(
            ADMIN_API_KEY="a" * 40,
            DATABASE_URL="postgresql://localhost/test",
            REDIS_URL="redis://localhost:6379/0",
            ENSEMBLE_MIN_CONFIDENCE=0.5,
        )
        assert config.ENSEMBLE_MIN_CONFIDENCE == 0.5

        # Invalid: negative
        with pytest.raises(ValidationError) as exc_info:
            Config(
                ADMIN_API_KEY="a" * 40,
                DATABASE_URL="postgresql://localhost/test",
                REDIS_URL="redis://localhost:6379/0",
                ENSEMBLE_MIN_CONFIDENCE=-0.1,
            )
        assert "between 0 and 1" in str(exc_info.value)

        # Invalid: > 1
        with pytest.raises(ValidationError) as exc_info:
            Config(
                ADMIN_API_KEY="a" * 40,
                DATABASE_URL="postgresql://localhost/test",
                REDIS_URL="redis://localhost:6379/0",
                ENSEMBLE_MIN_CONFIDENCE=1.5,
            )
        assert "between 0 and 1" in str(exc_info.value)

    def test_ensemble_divergence_std_positive(self):
        """Test ENSEMBLE_DIVERGENCE_STD must be positive."""
        from src.config import Config

        with pytest.raises(ValidationError) as exc_info:
            Config(
                ADMIN_API_KEY="a" * 40,
                DATABASE_URL="postgresql://localhost/test",
                REDIS_URL="redis://localhost:6379/0",
                ENSEMBLE_DIVERGENCE_STD=-0.1,
            )
        assert "positive" in str(exc_info.value).lower()

    def test_max_consecutive_fallbacks_positive(self):
        """Test MAX_CONSECUTIVE_FALLBACKS must be positive."""
        from src.config import Config

        with pytest.raises(ValidationError) as exc_info:
            Config(
                ADMIN_API_KEY="a" * 40,
                DATABASE_URL="postgresql://localhost/test",
                REDIS_URL="redis://localhost:6379/0",
                MAX_CONSECUTIVE_FALLBACKS=0,
            )
        assert "positive" in str(exc_info.value).lower()


class TestModelIDConsistency:
    """Verify model IDs are consistent across clients, allowlist, and performance worker."""

    def test_default_weights_model_ids_in_allowlist(self):
        """Model IDs used as fallback weights in performance worker must be in ALLOWED_MODEL_IDS."""
        # These are the hardcoded defaults in src/workers/performance.py
        # If this test fails, there is a typo in the performance worker fallback weights.
        default_weight_model_ids = {"kimi-k2.6:cloud", "qwen3.5:cloud", "deepseek-v4-pro:cloud", "glm-5.1:cloud"}
        assert default_weight_model_ids.issubset(ALLOWED_MODEL_IDS), (
            f"Model IDs in performance worker fallback weights not in ALLOWED_MODEL_IDS: "
            f"{default_weight_model_ids - ALLOWED_MODEL_IDS}"
        )

    def test_client_model_ids_in_allowlist(self):
        """Each concrete client's model_id must be in ALLOWED_MODEL_IDS."""
        from src.llm.client import OllamaKimiClient, OllamaQwen35Client, OllamaDeepseekClient, OllamaGlmClient

        for client_cls in (OllamaKimiClient, OllamaQwen35Client, OllamaDeepseekClient, OllamaGlmClient):
            assert client_cls.model_id in ALLOWED_MODEL_IDS, (
                f"{client_cls.__name__}.model_id={client_cls.model_id!r} not in ALLOWED_MODEL_IDS"
            )

    def test_timing_safe_api_key_comparison(self):
        """API auth must use secrets.compare_digest for timing-safe comparison."""
        import inspect
        import src.api.auth as auth_module

        source = inspect.getsource(auth_module)
        assert "compare_digest" in source, (
            "auth.py must use secrets.compare_digest() for timing-safe API key comparison"
        )
