"""Reversal force-sell must ignore FinBERT fallback signals (low reliability)."""
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

from src.workers.portfolio_scheduler import _sentiment_reversal_sells


def _pos(symbol):
    return SimpleNamespace(symbol=symbol)


def _redis_with(payloads: dict):
    r = MagicMock()
    r.get.side_effect = lambda key: next(
        (json.dumps(p) for sym, p in payloads.items() if key == f"signal:{sym}:sentiment"),
        None,
    )
    return r


def test_reversal_ignores_fallback_signal():
    """Same bearish score: ensemble → force-sold; FinBERT fallback → NOT sold."""
    redis = _redis_with({
        "ENS": {"score": -0.5, "fallback_used": False, "signal_id": 1},
        "FB": {"score": -0.5, "fallback_used": True, "signal_id": 2},
    })
    result = _sentiment_reversal_sells([_pos("ENS"), _pos("FB")], redis, threshold=-0.1)
    assert "ENS" in result
    assert "FB" not in result


def test_reversal_still_sells_on_ensemble():
    redis = _redis_with({"X": {"score": -0.6, "fallback_used": False, "signal_id": 9}})
    result = _sentiment_reversal_sells([_pos("X")], redis, threshold=-0.1)
    assert result["X"]["score"] == -0.6
