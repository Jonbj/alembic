"""QS-07: backtest/live parity — backtest replay applies the live signal freshness window."""
from datetime import datetime, timedelta, timezone

import pandas as pd

from src.strategies.s4.config import S4Config
from src.strategies.s4.strategy import NewsDrivenTactical

_TS = datetime(2026, 6, 30, 18, 0, tzinfo=timezone.utc)


def _df(rows):
    return pd.DataFrame(rows)


def test_signals_as_of_drops_stale_beyond_max_age():
    """Signals older than max_signal_age_hours at the tick are dropped (like live)."""
    df = _df([
        {"symbol": "AAPL", "score": 0.5, "confidence": 0.8, "generated_at": _TS - timedelta(hours=1)},   # fresh
        {"symbol": "MSFT", "score": 0.5, "confidence": 0.8, "generated_at": _TS - timedelta(hours=10)},  # stale > 4h
        {"symbol": "NVDA", "score": 0.5, "confidence": 0.8, "generated_at": _TS + timedelta(hours=1)},   # future
    ])
    strat = NewsDrivenTactical(config=S4Config(max_signal_age_hours=4), signals=df)
    symbols = {r.symbol for r in strat._signals_as_of(_TS)}
    assert symbols == {"AAPL"}


def test_signals_as_of_keeps_within_window():
    df = _df([
        {"symbol": "AAPL", "score": 0.5, "confidence": 0.8, "generated_at": _TS - timedelta(hours=3, minutes=59)},
        {"symbol": "MSFT", "score": 0.5, "confidence": 0.8, "generated_at": _TS - timedelta(hours=4, minutes=1)},
    ])
    strat = NewsDrivenTactical(config=S4Config(max_signal_age_hours=4), signals=df)
    symbols = {r.symbol for r in strat._signals_as_of(_TS)}
    assert symbols == {"AAPL"}  # MSFT is just over the 4h window


def test_age_window_disabled_when_zero():
    df = _df([
        {"symbol": "AAPL", "score": 0.5, "confidence": 0.8, "generated_at": _TS - timedelta(hours=1)},
        {"symbol": "MSFT", "score": 0.5, "confidence": 0.8, "generated_at": _TS - timedelta(hours=50)},
    ])
    strat = NewsDrivenTactical(config=S4Config(max_signal_age_hours=0), signals=df)
    symbols = {r.symbol for r in strat._signals_as_of(_TS)}
    assert symbols == {"AAPL", "MSFT"}  # no age filter → both (only the <= ts rule applies)
