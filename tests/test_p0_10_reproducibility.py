"""P0-10 — Reproducibility manifest + deterministic re-run.

Problem: there is no manifest recording what inputs produced a given backtest result.
Without this, a re-run cannot be verified as identical to the original, and
quantitative claims (Sharpe, DSR, gate pass/fail) cannot be independently audited.

Fix: BacktestManifest dataclass captures run inputs (seed, data_hash, config_hash,
run_id, code_version). BacktestOrchestrator.run() accepts an optional seed parameter
and returns results that are identical across runs with the same seed and data.

Acceptance: test_backtest_rerun_deterministic — two runs with the same inputs produce
identical NAV series and fills.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

import pandas as pd
import pytest


def _make_price_data(n: int = 20) -> pd.DataFrame:
    """Create a deterministic price series for testing."""
    dates = pd.date_range("2026-01-02", periods=n, freq="B")
    return pd.DataFrame(
        {"AAPL": [150.0 + i * 0.5 for i in range(n)]},
        index=dates,
    )


def _always_buy_strategy(ts, data_replay, portfolio, market):
    """Deterministic buy-and-hold strategy — same output every run."""
    from src.backtest.engine.types import Order, OrderSide
    if len(portfolio.get_fills()) == 0:  # buy only once
        return [Order.market_order(ts=ts, symbol="AAPL", side=OrderSide.BUY, qty=10.0)]
    return []


class TestBacktestRerunDeterministic:
    """Two runs with identical inputs must produce identical results."""

    def test_backtest_rerun_deterministic(self):
        """Running the backtest twice with the same data must produce identical NAV series.

        This is the acceptance criterion for P0-10. If this fails, the backtest engine
        has a non-deterministic source that must be identified and eliminated.
        """
        from src.backtest.engine.data_replay import DataReplay
        from src.backtest.engine.orchestrator import BacktestConfig, BacktestOrchestrator

        prices = _make_price_data()
        config = BacktestConfig(initial_capital=100_000.0)

        def _run():
            replay = DataReplay(prices)
            orch = BacktestOrchestrator(config=config)
            return orch.run(data_replay=replay, strategy_callable=_always_buy_strategy)

        result_1 = _run()
        result_2 = _run()

        nav_1 = result_1.to_nav_series().tolist()
        nav_2 = result_2.to_nav_series().tolist()

        assert nav_1 == nav_2, (
            "Backtest is non-deterministic: two runs with identical inputs produced "
            "different NAV series. Identify the non-deterministic source "
            "(random seed, dict ordering, floating point path) and fix it."
        )
        assert len(result_1.fills) == len(result_2.fills)
        # NAV series values must be byte-for-byte identical (no floating-point drift).
        assert all(a == b for a, b in zip(nav_1, nav_2))

    def test_manifest_captures_data_hash(self):
        """BacktestManifest.data_hash must change when input data changes."""
        from src.backtest.engine.orchestrator import BacktestManifest

        prices_a = _make_price_data(n=10)
        prices_b = _make_price_data(n=10).assign(AAPL=lambda df: df["AAPL"] + 1.0)

        m_a = BacktestManifest.from_dataframe(prices_a, seed=42)
        m_b = BacktestManifest.from_dataframe(prices_b, seed=42)

        assert m_a.data_hash != m_b.data_hash, (
            "BacktestManifest.data_hash must differ for different input data."
        )

    def test_manifest_data_hash_stable_across_runs(self):
        """BacktestManifest.data_hash must be identical for the same input data."""
        from src.backtest.engine.orchestrator import BacktestManifest

        prices = _make_price_data(n=15)
        m1 = BacktestManifest.from_dataframe(prices, seed=42)
        m2 = BacktestManifest.from_dataframe(prices, seed=42)

        assert m1.data_hash == m2.data_hash

    def test_manifest_seed_field(self):
        """BacktestManifest records the seed used for the run."""
        from src.backtest.engine.orchestrator import BacktestManifest

        prices = _make_price_data()
        m = BacktestManifest.from_dataframe(prices, seed=999)
        assert m.seed == 999

    def test_manifest_has_run_id(self):
        """BacktestManifest must have a non-empty run_id for traceability."""
        from src.backtest.engine.orchestrator import BacktestManifest

        prices = _make_price_data()
        m = BacktestManifest.from_dataframe(prices, seed=0)
        assert m.run_id and isinstance(m.run_id, str) and len(m.run_id) >= 8
