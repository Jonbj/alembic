"""#111: single-model reads must be labeled 'single:<model>' and gated like a
fallback (fallback_used=True), never mislabeled as a full ensemble."""
from src.workers.sentiment import _label_from_model_count


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
