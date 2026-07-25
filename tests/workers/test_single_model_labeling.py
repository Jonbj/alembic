"""#111: single-model reads must be labeled 'single:<model>' and gated like a
fallback (fallback_used=True), never mislabeled as a full ensemble."""
from src.models.signals import SentimentResult
from src.workers.sentiment import _is_full_fallback, _label_from_model_count


def _result(model_id: str, fallback_used: bool) -> SentimentResult:
    return SentimentResult(
        symbol="AAPL", score=0.1, confidence=0.5, reasoning="x",
        model_id=model_id, fallback_used=fallback_used,
    )


def test_two_models_is_ensemble():
    mid, fb, reasoning = _label_from_model_count(
        ["glm-5.2:cloud", "gpt-oss:20b-cloud"], "bull case"
    )
    assert mid == "ensemble:glm-5.2:cloud+gpt-oss:20b-cloud"
    assert fb is False
    assert reasoning == "bull case"


def test_single_model_labeled_and_gated():
    mid, fb, reasoning = _label_from_model_count(["gpt-oss:20b-cloud"], "bull case")
    assert mid == "single:gpt-oss:20b-cloud"
    assert fb is True
    assert reasoning == "[single-model:gpt-oss:20b-cloud] bull case"


def test_empty_model_ids_defensive():
    mid, fb, reasoning = _label_from_model_count([], "x")
    assert mid == "single:unknown"
    assert fb is True


# #128: the sizing circuit breaker must count only FULL (FinBERT) fallbacks.

def test_full_fallback_finbert_counts():
    assert _is_full_fallback(_result("finbert", fallback_used=True)) is True


def test_single_model_is_not_full_fallback():
    # Gated for trading (fallback_used=True) but must NOT trip the breaker.
    assert _is_full_fallback(_result("single:gpt-oss:20b-cloud", fallback_used=True)) is False


def test_ensemble_is_not_full_fallback():
    assert _is_full_fallback(_result("ensemble:a+b", fallback_used=False)) is False
