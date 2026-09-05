"""#490: misura deterministica della degenerazione del sizing S1."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.strategies.s1.sizing import compute_sizing_metrics, compute_weights
from src.strategies.s1.strategy import S1Config, TimeSeriesMomentum


def test_same_volatility_gets_same_weight_despite_different_signal() -> None:
    """Il segnale filtra i nomi, ma non scala il loro peso."""
    dates = pd.date_range("2025-01-02", periods=80, freq="B")
    returns = np.tile((0.01, -0.005), 40)
    prices = pd.DataFrame(
        {
            "WEAK": 100 * np.cumprod(1 + returns),
            "STRONG": 250 * np.cumprod(1 + returns),
        },
        index=dates,
    )

    latest = compute_weights(prices).query("as_of == @dates[-1]").set_index("ticker")
    target = {ticker: float(latest.loc[ticker, "weight"]) for ticker in latest.index}
    metrics = compute_sizing_metrics(
        target_weights=target,
        signals={"WEAK": 0.1, "STRONG": 2.0},
        raw_weights=target,
        max_weight=0.20,
    )

    assert target["WEAK"] == pytest.approx(target["STRONG"])
    assert metrics["spearman_signal_weight"] is None


def test_cap_bound_share_is_one_when_every_raw_weight_hits_cap() -> None:
    metrics = compute_sizing_metrics(
        target_weights={"A": 0.5, "B": 0.5},
        signals={"A": 0.2, "B": 1.8},
        raw_weights={"A": 0.20, "B": 0.20},
        max_weight=0.20,
    )

    assert metrics["n_target"] == 2
    assert metrics["cap_bound_share"] == pytest.approx(1.0)


def test_effective_positions_matches_hand_calculation() -> None:
    metrics = compute_sizing_metrics(
        target_weights={"A": 0.5, "B": 0.3, "C": 0.2},
        signals={"A": 3.0, "B": 2.0, "C": 1.0},
        raw_weights={"A": 0.20, "B": 0.12, "C": 0.08},
        max_weight=0.20,
    )

    assert metrics["n_eff"] == pytest.approx(1 / (0.5**2 + 0.3**2 + 0.2**2))
    assert metrics["spearman_signal_weight"] == pytest.approx(1.0)


def test_strategy_exposes_metrics_for_the_target_it_just_decided() -> None:
    dates = pd.date_range("2023-01-02", periods=400, freq="B")
    rng = np.random.default_rng(490)
    prices = pd.DataFrame(
        {
            f"T{i}": 100
            * np.exp(np.cumsum(rng.normal(0.0005 + i * 0.0002, 0.01, len(dates))))
            for i in range(8)
        },
        index=dates,
    )
    strategy = TimeSeriesMomentum(prices, S1Config())

    target = strategy.compute_target_weights(prices)
    metrics = strategy.last_sizing_metrics

    assert target
    assert metrics is not None
    assert metrics["n_target"] == len(target)
    assert metrics["cap_bound_share"] == pytest.approx(1.0)
