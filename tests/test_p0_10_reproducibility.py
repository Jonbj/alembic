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


class TestBacktestManifestVersionFields:
    """BacktestManifest must capture model, code, and config version (P0-10 follow-up)."""

    def test_manifest_has_code_version(self):
        """BacktestManifest must have a code_version field (git commit hash or fallback)."""
        from src.backtest.engine.orchestrator import BacktestManifest

        prices = _make_price_data()
        m = BacktestManifest.from_dataframe(prices, seed=42)
        assert hasattr(m, "code_version"), "BacktestManifest is missing code_version field"
        assert isinstance(m.code_version, str) and len(m.code_version) > 0, (
            "code_version must be a non-empty string (git sha or 'unknown')"
        )

    def test_manifest_has_config_hash(self):
        """BacktestManifest must capture a hash of trading.yaml at run time."""
        from src.backtest.engine.orchestrator import BacktestManifest

        prices = _make_price_data()
        m = BacktestManifest.from_dataframe(prices, seed=42)
        assert hasattr(m, "config_hash"), "BacktestManifest is missing config_hash field"
        assert isinstance(m.config_hash, str) and len(m.config_hash) > 0, (
            "config_hash must be a non-empty string (sha256 prefix of trading.yaml or 'unknown')"
        )

    def test_manifest_has_model_version(self):
        """BacktestManifest must record the model/inference stack version."""
        from src.backtest.engine.orchestrator import BacktestManifest

        prices = _make_price_data()
        m = BacktestManifest.from_dataframe(prices, seed=42)
        assert hasattr(m, "model_version"), "BacktestManifest is missing model_version field"
        assert isinstance(m.model_version, str) and len(m.model_version) > 0, (
            "model_version must be a non-empty string (e.g. 'finbert-int8+kimi-k2.6')"
        )

    def test_code_version_is_stable_within_run(self):
        """Two manifests created in the same process must have the same code_version."""
        from src.backtest.engine.orchestrator import BacktestManifest

        prices = _make_price_data()
        m1 = BacktestManifest.from_dataframe(prices, seed=1)
        m2 = BacktestManifest.from_dataframe(prices, seed=2)
        assert m1.code_version == m2.code_version, (
            "code_version must be stable within a process — it reflects the deployed commit"
        )

    def test_orchestrator_run_accepts_seed(self):
        """BacktestOrchestrator.run() must accept an optional seed parameter."""
        import inspect
        from src.backtest.engine.orchestrator import BacktestOrchestrator
        sig = inspect.signature(BacktestOrchestrator.run)
        assert "seed" in sig.parameters, (
            "BacktestOrchestrator.run() must accept a seed parameter so stochastic "
            "strategies can be made deterministic across re-runs"
        )

    def test_orchestrator_run_returns_manifest(self):
        """BacktestOrchestrator.run() must return a manifest alongside results."""
        from src.backtest.engine.data_replay import DataReplay
        from src.backtest.engine.orchestrator import BacktestConfig, BacktestOrchestrator, BacktestManifest

        prices = _make_price_data()
        replay = DataReplay(prices)
        orch = BacktestOrchestrator(config=BacktestConfig())
        result = orch.run(data_replay=replay, strategy_callable=lambda *_: [], seed=42)
        assert hasattr(result, "manifest"), (
            "BacktestResult must have a manifest attribute of type BacktestManifest"
        )
        assert isinstance(result.manifest, BacktestManifest)
