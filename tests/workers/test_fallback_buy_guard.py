"""#110/#108 regression lock: a FinBERT-fallback signal must never survive into
BUY ranking. Combined with the #68 reversal cooldown (blocks re-buy during the
window) and S4-only sentiment ranking, this prevents re-buying a reversal-sold
name on a weaker contradicting fallback signal (WDC, 2026-07-21). Behavior is
locked by test; do not weaken _filter_fallback_signals without updating this."""
from types import SimpleNamespace

from src.workers.portfolio_scheduler import _filter_fallback_signals


def _sig(symbol, fallback_used):
    return SimpleNamespace(symbol=symbol, fallback_used=fallback_used)


def test_fallback_signal_is_dropped_from_buy_ranking():
    ensemble = _sig("WDC", fallback_used=False)
    fallback = _sig("WDC", fallback_used=True)
    non_fallback, dropped = _filter_fallback_signals([ensemble, fallback])
    assert ensemble in non_fallback
    assert fallback not in non_fallback
    assert dropped == [fallback]


def test_all_ensemble_signals_pass_through():
    a = _sig("AAA", fallback_used=False)
    b = _sig("BBB", fallback_used=False)
    non_fallback, dropped = _filter_fallback_signals([a, b])
    assert non_fallback == [a, b]
    assert dropped == []


def test_missing_attribute_treated_as_non_fallback():
    # Defensive: a signal object without the attribute must not be dropped.
    s = SimpleNamespace(symbol="XYZ")
    non_fallback, dropped = _filter_fallback_signals([s])
    assert non_fallback == [s]
    assert dropped == []
