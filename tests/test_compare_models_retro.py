import csv
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


class _NoopTracker:
    """Fake LLMBudgetTracker — records calls without touching Postgres."""

    def __init__(self):
        self.recorded = []

    async def record_spending(self, model_id, input_tokens, output_tokens):
        self.recorded.append((model_id, input_tokens, output_tokens))
        return 0.0

    def close(self):
        pass


class _FakeConn:
    """Stand-in for the raw psycopg2 connection returned by _build_budget_tracker."""

    def close(self):
        pass


def test_main_skips_already_scored_pairs_and_records_spend(tmp_path, monkeypatch):
    import scripts.compare_models_retro as mod

    out_path = tmp_path / "stage1_retro.csv"
    # Pre-existing CSV: label 1 already scored for kimi-k2.6:cloud only.
    with open(out_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=mod._FIELDS)
        w.writeheader()
        w.writerow({
            "label_id": 1, "model": "kimi-k2.6:cloud", "polarity": 0.2,
            "confidence": 0.6, "gt_sentiment_dir": "positive",
            "predicted_dir": "positive", "correct": True,
            "parse_error": False, "latency_ms": 900,
        })
    monkeypatch.setattr(mod, "_OUT", str(out_path))
    monkeypatch.setattr(mod, "_MODELS", ["kimi-k2.6:cloud", "glm-5.2:cloud"])
    monkeypatch.setattr(
        mod, "_fetch_labeled_rows",
        lambda: [{
            "label_id": 1, "body_snippet": "Some news body",
            "gt_tickers": ["AAPL"], "extracted_tickers": [],
            "gt_sentiment_dir": "positive",
        }],
    )
    calls = []

    def fake_score_one(model, prompt):
        calls.append(model)
        return {
            "polarity": 0.3, "confidence": 0.5, "parse_error": False,
            "latency_ms": 100, "output_chars": 200,
        }

    monkeypatch.setattr(mod, "_score_one", fake_score_one)
    monkeypatch.setattr(mod.time, "sleep", lambda *_: None)
    tracker = _NoopTracker()
    monkeypatch.setattr(mod, "_build_budget_tracker", lambda: (tracker, _FakeConn()))

    mod.main()

    # label 1 / kimi already done -> must NOT be re-scored.
    assert calls == ["glm-5.2:cloud"]
    with open(out_path) as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 2  # the pre-existing row + the new glm-5.2 row
    # Spend recorded only for the one new (uncached) call.
    assert len(tracker.recorded) == 1
    model_id, input_tokens, output_tokens = tracker.recorded[0]
    assert model_id == "glm-5.2:cloud"
    assert input_tokens > 0
    assert output_tokens == 200 // 4
