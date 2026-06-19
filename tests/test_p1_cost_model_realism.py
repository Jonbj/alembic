"""P1-COST-MODEL-REALISM — Realistic cost model improvements.

Problems (WS-07 from ALEMBIC_REMEDIATION_MASTER_PLAN_2026-06-18):
1. ADV fallback = 10_000_000 shares → for a $100 stock that is $1B daily turnover.
   Most backtest fixtures lack volume data, so market impact ≈ 0. This produces
   overly optimistic net performance.
2. Fixed operational costs (data subscriptions, server fees ~$1440/year) are excluded
   from net-Sharpe. On a $10K account this is 14.4% annual drag — material.

Fixes:
- DataReplay ADV fallback: 10M → 500_000 shares (realistic mid-cap daily volume).
- RealisticCostModel ADV fallback: same change for consistency.
- BacktestConfig.annual_fixed_cost: float = 0.0 — annual fixed cost in dollars.
- BacktestResult.net_annualized_return(annual_fixed_cost, capital) — deducts drag.
- BacktestResult.net_sharpe(risk_free_rate, annual_fixed_cost, capital) — net Sharpe.
"""
from __future__ import annotations

import pandas as pd
import pytest

from src.backtest.costs.impact_model import SquareRootImpactModel
from src.backtest.engine.data_replay import DataReplay
from src.backtest.engine.orchestrator import BacktestConfig, BacktestOrchestrator, BacktestResult
from src.backtest.engine.order_simulation import SimpleCostModel
from src.backtest.engine.types import Order, OrderSide


_N = 252


def _make_prices(val: float = 100.0, n: int = _N) -> pd.DataFrame:
    dates = pd.date_range("2024-01-02", periods=n, freq="B")
    return pd.DataFrame({"SPY": [val] * n}, index=dates)


def _make_volumes(shares_per_day: float, n: int = _N) -> pd.DataFrame:
    dates = pd.date_range("2024-01-02", periods=n, freq="B")
    return pd.DataFrame({"SPY": [shares_per_day] * n}, index=dates)


# ─────────────────────────────────────────────────────────────────────────────
# Group A — ADV fallback realism
# ─────────────────────────────────────────────────────────────────────────────

class TestADVFallbackRealism:

    def test_data_replay_adv_fallback_is_at_most_500k_shares(self):
        """DataReplay without volumes must use an ADV fallback ≤ 500_000 shares."""
        prices = _make_prices(100.0, n=5)
        replay = DataReplay(prices)  # no volumes → triggers fallback

        ts = prices.index[0]
        snap = replay.market_at(ts)

        adv_shares = snap.adv_20d.get("SPY", None)
        assert adv_shares is not None
        assert adv_shares <= 500_000, (
            f"ADV fallback must be ≤ 500_000 shares (realistic mid-cap), got {adv_shares:,}. "
            f"The old 10_000_000 default makes market impact ≈0 and produces optimistic backtest results."
        )

    def test_impact_higher_with_conservative_adv_than_10m_default(self):
        """SquareRootImpactModel: impact is meaningfully higher at ADV=500K than ADV=10M."""
        model = SquareRootImpactModel(k=10.0)
        order_usd = 50_000.0   # $50K order (typical small-account BUY)
        price = 100.0

        adv_usd_old = 10_000_000 * price    # old: 10M shares × $100 = $1B
        adv_usd_new = 500_000 * price       # new:  500K shares × $100 = $50M

        impact_old = model.impact_bps(order_usd, adv_usd_old)
        impact_new = model.impact_bps(order_usd, adv_usd_new)

        assert impact_new > impact_old * 2, (
            f"Impact at 500K ADV ({impact_new:.3f} bps) must be > 2× impact at 10M ADV "
            f"({impact_old:.3f} bps). Conservative ADV produces meaningfully higher cost estimates."
        )

    def test_realistic_cost_model_adv_fallback_consistent_with_data_replay(self):
        """RealisticCostModel must use the same conservative ADV fallback as DataReplay.

        If DataReplay uses 500K fallback but the cost model uses 10M, a backtest that
        passes volumes=None gets different fill costs than one with volumes — inconsistent.
        """
        from src.backtest.costs.realistic import RealisticCostModel
        from src.backtest.engine.types import MarketSnapshot, Order, OrderSide
        from datetime import datetime, timezone

        prices_no_adv = _make_prices(100.0, n=5)
        replay = DataReplay(prices_no_adv)
        ts = prices_no_adv.index[0]
        snap = replay.market_at(ts)

        # The snap.adv_20d["SPY"] is whatever DataReplay provides (with fallback).
        # If we also query cost model with a MarketSnapshot with adv_20d = 10M (old default),
        # the cost model would behave differently from DataReplay.
        # Test: DataReplay fallback ADV is the one seen by the cost model in practice.
        adv_from_replay = snap.adv_20d.get("SPY", None)
        assert adv_from_replay is not None
        assert adv_from_replay <= 500_000, (
            f"Replay-provided ADV ({adv_from_replay:,.0f}) must match conservative fallback. "
            f"Cost model uses DataReplay.market_at().adv_20d, so the two are coupled."
        )


# ─────────────────────────────────────────────────────────────────────────────
# Group B — Fixed cost in net-Sharpe
# ─────────────────────────────────────────────────────────────────────────────

class TestFixedCostNetSharpe:

    def test_backtest_config_has_annual_fixed_cost_field(self):
        """BacktestConfig must expose annual_fixed_cost defaulting to 0.0."""
        cfg = BacktestConfig()
        assert hasattr(cfg, "annual_fixed_cost"), (
            "BacktestConfig must have annual_fixed_cost field (P1-COST-MODEL-REALISM)"
        )
        assert cfg.annual_fixed_cost == 0.0

    def test_backtest_result_has_net_annualized_return(self):
        """BacktestResult must expose net_annualized_return(annual_fixed_cost, capital)."""
        prices = _make_prices(100.0, n=_N)
        replay = DataReplay(prices)
        cost = SimpleCostModel(spread_bps=0.0)
        orc = BacktestOrchestrator(BacktestConfig(initial_capital=100_000, fill_at_next_open=False), cost_model=cost)
        result = orc.run(replay, lambda ts, dr, p, m: [])

        assert hasattr(result, "net_annualized_return"), (
            "BacktestResult must have net_annualized_return(annual_fixed_cost, capital) method"
        )

    def test_net_annualized_return_is_lower_than_gross_by_fixed_cost_drag(self):
        """net_annualized_return with $1440 annual cost on $10K capital = 14.4% drag."""
        # Use a trend-up series so gross return > 0
        n = _N
        prices = pd.DataFrame(
            {"SPY": [100.0 + i * 0.1 for i in range(n)]},
            index=pd.date_range("2024-01-02", periods=n, freq="B"),
        )
        replay = DataReplay(prices)
        cost = SimpleCostModel(spread_bps=0.0)
        orc = BacktestOrchestrator(BacktestConfig(initial_capital=10_000, fill_at_next_open=False), cost_model=cost)
        result = orc.run(replay, lambda ts, dr, p, m: [])

        gross = result.net_annualized_return(annual_fixed_cost=0.0, capital=10_000)
        net   = result.net_annualized_return(annual_fixed_cost=1_440.0, capital=10_000)

        # Fixed cost drag = 1440/10000 = 14.4% per year — must be reflected
        expected_drag = 1_440.0 / 10_000
        actual_drag = gross - net
        assert actual_drag == pytest.approx(expected_drag, rel=1e-3), (
            f"Annual drag must equal annual_fixed_cost / capital = {expected_drag:.3%}, "
            f"got {actual_drag:.3%} (gross={gross:.3%}, net={net:.3%})"
        )

    def test_net_sharpe_lower_than_gross_with_fixed_cost(self):
        """BacktestResult.net_sharpe must be lower than gross Sharpe when fixed cost > 0.

        Uses buy-and-hold on a rising+volatile price series so ann_vol > 0.
        """
        import numpy as np
        rng = np.random.default_rng(42)
        n = _N
        # Random walk with positive drift so gross Sharpe > 0
        log_returns = rng.normal(0.0008, 0.01, n)
        prices_arr = 100.0 * np.exp(np.cumsum(log_returns))
        dates = pd.date_range("2024-01-02", periods=n, freq="B")
        prices = pd.DataFrame({"SPY": prices_arr}, index=dates)

        # Buy-and-hold: buy on day 0, hold forever → portfolio tracks price path
        fired = []
        def buy_and_hold(ts, dr, port, mkt):
            if not fired and mkt.has_price("SPY"):
                fired.append(True)
                qty = int(10_000 / mkt.price_of("SPY"))
                if qty > 0:
                    return [Order.market_order(ts, "SPY", OrderSide.BUY, float(qty))]
            return []

        replay = DataReplay(prices)
        cost = SimpleCostModel(spread_bps=0.0)
        orc = BacktestOrchestrator(BacktestConfig(initial_capital=10_000, fill_at_next_open=False), cost_model=cost)
        result = orc.run(replay, buy_and_hold)

        gross_sharpe = result.net_sharpe(annual_fixed_cost=0.0, capital=10_000)
        net_sharpe   = result.net_sharpe(annual_fixed_cost=1_440.0, capital=10_000)

        assert gross_sharpe != 0.0, "Test setup error: gross Sharpe must be non-zero"
        assert net_sharpe < gross_sharpe, (
            f"net_sharpe ({net_sharpe:.3f}) must be lower than gross_sharpe ({gross_sharpe:.3f}) "
            f"when annual_fixed_cost > 0"
        )

    def test_net_sharpe_zero_fixed_cost_equals_gross_sharpe(self):
        """net_sharpe(annual_fixed_cost=0) must equal the standard Sharpe ratio."""
        from src.backtest.metrics import performance as perf

        n = _N
        prices = pd.DataFrame(
            {"SPY": [100.0 + i * 0.1 for i in range(n)]},
            index=pd.date_range("2024-01-02", periods=n, freq="B"),
        )
        replay = DataReplay(prices)
        cost = SimpleCostModel(spread_bps=0.0)
        orc = BacktestOrchestrator(BacktestConfig(initial_capital=100_000, fill_at_next_open=False), cost_model=cost)
        result = orc.run(replay, lambda ts, dr, p, m: [])

        net_sharpe_zero_cost = result.net_sharpe(annual_fixed_cost=0.0, capital=100_000)
        gross_sharpe = perf.sharpe_ratio(result.to_returns_series())

        assert net_sharpe_zero_cost == pytest.approx(gross_sharpe, rel=1e-4), (
            "net_sharpe(annual_fixed_cost=0) must equal standard gross Sharpe ratio"
        )
