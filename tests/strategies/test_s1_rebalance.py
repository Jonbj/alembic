"""Tests for S1 TimeSeriesMomentum public rebalance gate."""
from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from src.strategies.s1.strategy import S1Config, TimeSeriesMomentum
from src.backtest.engine.types import RebalanceFrequency


def _make_prices(n: int = 300) -> pd.DataFrame:
    dates = pd.date_range("2024-01-01", periods=n, freq="B")
    return pd.DataFrame({"SPY": np.ones(n) * 100.0}, index=dates)


def test_s1_should_rebalance_returns_true_on_first_call():
    prices = _make_prices()
    cfg = S1Config(rebalance_frequency=RebalanceFrequency.MONTHLY)
    s1 = TimeSeriesMomentum(prices, cfg)
    ts = datetime(2025, 6, 1, tzinfo=timezone.utc)
    assert s1.should_rebalance(ts) is True


def test_s1_should_rebalance_false_within_same_month():
    prices = _make_prices()
    cfg = S1Config(rebalance_frequency=RebalanceFrequency.MONTHLY)
    s1 = TimeSeriesMomentum(prices, cfg)
    s1.mark_rebalanced(datetime(2025, 6, 1, tzinfo=timezone.utc))
    ts = datetime(2025, 6, 15, tzinfo=timezone.utc)
    assert s1.should_rebalance(ts) is False


def test_s1_should_rebalance_true_next_month():
    prices = _make_prices()
    cfg = S1Config(rebalance_frequency=RebalanceFrequency.MONTHLY)
    s1 = TimeSeriesMomentum(prices, cfg)
    s1.mark_rebalanced(datetime(2025, 6, 1, tzinfo=timezone.utc))
    ts = datetime(2025, 7, 1, tzinfo=timezone.utc)
    assert s1.should_rebalance(ts) is True


def test_s1_mark_rebalanced_updates_state():
    prices = _make_prices()
    s1 = TimeSeriesMomentum(prices, S1Config())
    ts = datetime(2025, 6, 10, tzinfo=timezone.utc)
    assert s1.should_rebalance(ts) is True
    s1.mark_rebalanced(ts)
    assert s1.should_rebalance(datetime(2025, 6, 20, tzinfo=timezone.utc)) is False
