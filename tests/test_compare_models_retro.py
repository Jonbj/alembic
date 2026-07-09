import sys
import os
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.compare_models_retro import _direction, _score_one


def test_direction_positive():
    assert _direction(0.5) == "positive"


def test_direction_negative():
    assert _direction(-0.3) == "negative"


def test_direction_neutral_inside_deadzone():
    assert _direction(0.05) == "neutral"
    assert _direction(-0.05) == "neutral"
    assert _direction(0.0) == "neutral"


def test_score_one_success():
    raw = '{"polarity": 0.4, "confidence": 0.7, "reasoning": "x"}'
    with patch("scripts.compare_models_retro._call", return_value=(raw, 1234)):
        result = _score_one("kimi-k2.6:cloud", "irrelevant prompt")
    assert result == {
        "polarity": 0.4,
        "confidence": 0.7,
        "parse_error": False,
        "latency_ms": 1234,
        "output_chars": len(raw),
    }


def test_score_one_retries_once_then_succeeds():
    raw = '{"polarity": -0.2, "confidence": 0.5, "reasoning": "x"}'
    calls = [RuntimeError("boom"), (raw, 500)]

    def fake_call(model, prompt):
        result = calls.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    with patch("scripts.compare_models_retro._call", side_effect=fake_call), \
         patch("scripts.compare_models_retro.time.sleep"):
        result = _score_one("glm-5.2:cloud", "irrelevant prompt")
    assert result == {
        "polarity": -0.2,
        "confidence": 0.5,
        "parse_error": False,
        "latency_ms": 500,
        "output_chars": len(raw),
    }


def test_score_one_fails_both_attempts():
    with patch("scripts.compare_models_retro._call", side_effect=RuntimeError("boom")), \
         patch("scripts.compare_models_retro.time.sleep"):
        result = _score_one("qwen3.5:cloud", "irrelevant prompt")
    assert result == {
        "polarity": 0.0,
        "confidence": 0.0,
        "parse_error": True,
        "latency_ms": 0,
        "output_chars": 0,
    }
