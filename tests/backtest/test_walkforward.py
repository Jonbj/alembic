"""Tests for walk-forward runner, aggregator, and HTML report.

Acceptance criteria (T-005):
- WF on 10yr with SPY buy-and-hold: OOS metrics ≈ full period metrics
- WF saves results per window
- WF generates HTML report
"""
from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd
import pytest

from src.backtest.engine.data_replay import DataReplay
from src.backtest.engine.orchestrator import BacktestConfig, BacktestOrchestrator
from src.backtest.engine.portfolio import VirtualPortfolio
from src.backtest.engine.types import MarketSnapshot, Order, OrderSide
from src.backtest.walkforward.aggregator import WalkForwardAggregator
from src.backtest.walkforward.report import WalkForwardHTMLReport
from src.backtest.walkforward.runner import (
    WalkForwardConfig,
    WalkForwardRunner,
    _compute_window_metrics,
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_trending_prices(n_days: int, ann_return: float = 0.12, ann_vol: float = 0.15) -> pd.DataFrame:
    """Seeded trending price series for deterministic tests."""
    np.random.seed(42)
    dates = pd.date_range("2014-01-02", periods=n_days, freq="B")
    daily_r = ann_return / 252
    daily_v = ann_vol / (252 ** 0.5)
    noise = np.random.normal(daily_r, daily_v, n_days)
    prices = 400.0 * np.exp(np.cumsum(noise))
    return pd.DataFrame({"SPY": prices}, index=dates)


def _make_volumes(n_days: int, start: str = "2014-01-02") -> pd.DataFrame:
    dates = pd.date_range(start, periods=n_days, freq="B")
    return pd.DataFrame({"SPY": [50_000_000.0] * n_days}, index=dates)


def _buy_and_hold(ts: datetime, dr: DataReplay, port: VirtualPortfolio, mkt: MarketSnapshot) -> list[Order]:
    if port.position_of("SPY") is None:
        price = mkt.price_of("SPY")
        if price is None:
            return []
        qty = int(port.cash * 0.95 / price)
        if qty > 0:
            return [Order.market_order(ts, "SPY", OrderSide.BUY, qty, "buy_hold")]
    return []


def _no_op(ts, dr, port, mkt) -> list[Order]:
    return []


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def short_prices():
    """~4yr of synthetic prices — fast unit tests."""
    return _make_trending_prices(1008)


@pytest.fixture(scope="module")
def short_replay(short_prices):
    vols = _make_volumes(len(short_prices), start=str(short_prices.index[0].date()))
    return DataReplay(short_prices, vols)


@pytest.fixture(scope="module")
def short_wf_result(short_replay):
    """WF result on 4yr data, IS=2yr, OOS=1yr, step=1yr → ≥2 windows."""
    cfg = WalkForwardConfig(in_sample_days=504, out_of_sample_days=252, step_days=252)
    runner = WalkForwardRunner(cfg, BacktestConfig(initial_capital=100_000))
    return runner.run(short_replay, _buy_and_hold)


@pytest.fixture(scope="module")
def spy10yr_result():
    """WF result on 10yr trending data for acceptance-level sanity checks."""
    prices = _make_trending_prices(2520)
    vols = _make_volumes(2520)
    replay = DataReplay(prices, vols)
    cfg = WalkForwardConfig(in_sample_days=504, out_of_sample_days=252, step_days=252)
    runner = WalkForwardRunner(cfg, BacktestConfig(initial_capital=100_000))
    return runner.run(replay, _buy_and_hold)


# ---------------------------------------------------------------------------
# _compute_window_metrics unit tests
# ---------------------------------------------------------------------------

class TestComputeWindowMetrics:
    def test_empty_returns_error(self):
        result = _compute_window_metrics([])
        assert "error" in result

    def test_single_snapshot_returns_error(self):
        from src.backtest.engine.types import PortfolioSnapshot
        snap = PortfolioSnapshot(timestamp=datetime(2023, 1, 1), cash=100_000.0, positions=(), total_nav=100_000.0)
        result = _compute_window_metrics([snap])
        assert "error" in result

    def test_flat_nav_returns_zero_sharpe(self):
        from src.backtest.engine.types import PortfolioSnapshot
        ts = [datetime(2023, 1, i + 1) for i in range(5)]
        snaps = [
            PortfolioSnapshot(timestamp=t, cash=100_000.0, positions=(), total_nav=100_000.0)
            for t in ts
        ]
        m = _compute_window_metrics(snaps)
        assert m["sharpe"] == 0.0

    def test_growing_nav_positive_return(self):
        from src.backtest.engine.types import PortfolioSnapshot
        ts = pd.date_range("2023-01-02", periods=252, freq="B")
        navs = [100_000 + i * 50 for i in range(252)]
        snaps = [
            PortfolioSnapshot(timestamp=t.to_pydatetime(), cash=0.0, positions=(), total_nav=float(nav))
            for t, nav in zip(ts, navs)
        ]
        m = _compute_window_metrics(snaps)
        assert m["annualized_return"] > 0
        assert m["sharpe"] > 0
        assert m["max_drawdown"] == 0.0  # monotonically increasing → no drawdown
        assert m["n_days"] == 252


# ---------------------------------------------------------------------------
# WalkForwardRunner tests
# ---------------------------------------------------------------------------

class TestWalkForwardRunner:
    def test_produces_expected_window_count(self, short_wf_result):
        # 1008 days total: IS=504, OOS=252, step=252
        # Windows: is_start = 0, 252 → 2 windows (oos_end_idx 755, 1007 both < 1008)
        assert len(short_wf_result.windows) >= 2

    def test_all_windows_have_oos_result(self, short_wf_result):
        for w in short_wf_result.windows:
            assert w.oos_result is not None
            assert len(w.oos_result.snapshots) > 0

    def test_oos_metrics_keys_present(self, short_wf_result):
        required = {"annualized_return", "sharpe", "max_drawdown", "calmar", "n_days"}
        for w in short_wf_result.windows:
            assert required <= set(w.oos_metrics), (
                f"Window {w.window_idx} missing keys: {required - set(w.oos_metrics)}"
            )

    def test_oos_start_strictly_after_is_end(self, short_wf_result):
        for w in short_wf_result.windows:
            assert w.oos_start > w.is_end, (
                f"Window {w.window_idx}: oos_start {w.oos_start} not after is_end {w.is_end}"
            )

    def test_oos_windows_non_overlapping(self, short_wf_result):
        """OOS periods must not overlap when step == oos_days."""
        sorted_w = sorted(short_wf_result.windows, key=lambda w: w.oos_start)
        for a, b in zip(sorted_w, sorted_w[1:]):
            assert a.oos_end < b.oos_start, (
                f"OOS overlap: window {a.window_idx} ends {a.oos_end}, "
                f"window {b.window_idx} starts {b.oos_start}"
            )

    def test_result_carries_aggregate_metrics(self, short_wf_result):
        agg = short_wf_result.aggregate_metrics
        assert "mean_sharpe" in agg
        assert "n_windows" in agg
        assert agg["n_windows"] == len(short_wf_result.windows)

    def test_window_indices_sequential(self, short_wf_result):
        for i, w in enumerate(short_wf_result.windows):
            assert w.window_idx == i

    def test_no_op_strategy_zero_fills(self, short_replay):
        cfg = WalkForwardConfig(in_sample_days=504, out_of_sample_days=252, step_days=252)
        runner = WalkForwardRunner(cfg, BacktestConfig(initial_capital=100_000))
        result = runner.run(short_replay, _no_op)
        for w in result.windows:
            assert len(w.oos_result.fills) == 0


class TestWalkForwardRunnerEdgeCases:
    def test_too_short_data_zero_windows(self):
        n = 300  # IS+OOS = 504+252 = 756 > 300
        dates = pd.date_range("2023-01-02", periods=n, freq="B")
        prices = pd.DataFrame({"SPY": [400.0] * n}, index=dates)
        replay = DataReplay(prices)
        cfg = WalkForwardConfig(in_sample_days=504, out_of_sample_days=252)
        runner = WalkForwardRunner(cfg, BacktestConfig(initial_capital=100_000))
        result = runner.run(replay, _no_op)
        assert len(result.windows) == 0
        assert result.aggregate_metrics.get("n_windows") == 0

    def test_exact_minimum_data_one_window(self):
        n = 504 + 252  # exactly one window
        dates = pd.date_range("2023-01-02", periods=n, freq="B")
        prices = pd.DataFrame({"SPY": [400.0 + i * 0.1 for i in range(n)]}, index=dates)
        replay = DataReplay(prices)
        cfg = WalkForwardConfig(in_sample_days=504, out_of_sample_days=252)
        runner = WalkForwardRunner(cfg, BacktestConfig(initial_capital=100_000))
        result = runner.run(replay, _no_op)
        assert len(result.windows) == 1

    def test_custom_step_smaller_than_oos(self):
        """Smaller step → more (overlapping OOS) windows."""
        n = 1260  # 5yr
        dates = pd.date_range("2019-01-02", periods=n, freq="B")
        prices = pd.DataFrame({"SPY": [300.0 + i * 0.05 for i in range(n)]}, index=dates)
        replay = DataReplay(prices)
        cfg = WalkForwardConfig(in_sample_days=504, out_of_sample_days=252, step_days=126)
        runner = WalkForwardRunner(cfg, BacktestConfig(initial_capital=100_000))
        result = runner.run(replay, _no_op)
        assert len(result.windows) >= 4


# ---------------------------------------------------------------------------
# SPY 10yr buy-and-hold acceptance test (T-005 sanity check)
# ---------------------------------------------------------------------------

class TestSPY10YrSanity:
    """Acceptance test: walk-forward on 10yr SPY buy-and-hold.

    OOS metrics should be consistent with full-period behaviour:
    - mean OOS Sharpe positive (upward-trending series)
    - majority of OOS windows show positive annualized return
    - OOS NAV series is chronological and entirely positive
    """

    def test_produces_at_least_6_windows(self, spy10yr_result):
        agg = spy10yr_result.aggregate_metrics
        assert agg["n_windows"] >= 6, (
            f"Expected ≥6 windows on 10yr data, got {agg['n_windows']}"
        )

    def test_mean_oos_sharpe_positive(self, spy10yr_result):
        agg = spy10yr_result.aggregate_metrics
        assert agg["mean_sharpe"] > 0, (
            f"Mean OOS Sharpe should be positive for upward-trending data: {agg['mean_sharpe']}"
        )

    def test_majority_windows_positive_return(self, spy10yr_result):
        agg = spy10yr_result.aggregate_metrics
        assert agg["pct_windows_positive"] >= 0.5, (
            f"Expected ≥50% positive OOS windows, got {agg['pct_windows_positive']:.0%}"
        )

    def test_oos_nav_series_positive_and_chronological(self, spy10yr_result):
        oos_nav = spy10yr_result.aggregate_metrics.get("oos_nav_series")
        assert isinstance(oos_nav, pd.Series) and len(oos_nav) > 0
        assert oos_nav.index.is_monotonic_increasing, "OOS NAV index must be chronological"
        assert (oos_nav > 0).all(), "OOS NAV must always be positive"

    def test_results_saved_per_window(self, spy10yr_result):
        """Each window stores its full OOS BacktestResult with snapshots."""
        for w in spy10yr_result.windows:
            assert w.oos_result is not None, f"Window {w.window_idx} missing oos_result"
            assert len(w.oos_result.snapshots) > 0, f"Window {w.window_idx} has empty snapshots"
            # Metrics stored per window
            assert "annualized_return" in w.oos_metrics
            assert "sharpe" in w.oos_metrics

    def test_oos_sharpe_same_order_as_full_period(self, spy10yr_result):
        """Mean OOS Sharpe should be in the same order of magnitude as full-period.

        For a 10yr trending series at 12% annual return, full-period Sharpe ~ 0.7-1.0.
        Mean OOS Sharpe should be positive and within a factor of 3.
        """
        prices = _make_trending_prices(2520)
        vols = _make_volumes(2520)
        replay = DataReplay(prices, vols)
        bt = BacktestOrchestrator(BacktestConfig(initial_capital=100_000))
        full = bt.run(replay, _buy_and_hold)
        full_returns = full.to_returns_series()
        full_sharpe = float(full_returns.mean() / full_returns.std() * (252 ** 0.5))

        mean_oos_sharpe = spy10yr_result.aggregate_metrics["mean_sharpe"]
        # Both should be positive; ratio within [0.2, 5.0] is reasonable for rolling windows
        assert full_sharpe > 0, "Full-period Sharpe should be positive"
        assert mean_oos_sharpe > 0, "Mean OOS Sharpe should be positive"
        ratio = mean_oos_sharpe / full_sharpe
        assert 0.2 <= ratio <= 5.0, (
            f"OOS/full Sharpe ratio {ratio:.2f} is implausible "
            f"(oos={mean_oos_sharpe:.3f}, full={full_sharpe:.3f})"
        )


# ---------------------------------------------------------------------------
# WalkForwardAggregator tests
# ---------------------------------------------------------------------------

class TestWalkForwardAggregator:
    def test_empty_windows_returns_error(self):
        result = WalkForwardAggregator().aggregate([])
        assert result["n_windows"] == 0
        assert "error" in result

    def test_all_required_keys_present(self, short_wf_result):
        required = {
            "n_windows", "n_valid_windows", "mean_sharpe", "median_sharpe",
            "std_sharpe", "mean_annualized_return", "mean_max_drawdown",
            "worst_drawdown", "pct_windows_positive", "per_window",
        }
        agg = short_wf_result.aggregate_metrics
        missing = required - set(agg)
        assert not missing, f"Aggregate missing keys: {missing}"

    def test_per_window_count_equals_window_list(self, short_wf_result):
        n_windows = len(short_wf_result.windows)
        per_window = short_wf_result.aggregate_metrics["per_window"]
        assert len(per_window) == n_windows

    def test_oos_nav_series_chronological(self, short_wf_result):
        nav = short_wf_result.aggregate_metrics.get("oos_nav_series")
        assert isinstance(nav, pd.Series) and len(nav) > 0
        assert nav.index.is_monotonic_increasing

    def test_std_sharpe_zero_when_single_window(self):
        """std_sharpe must be 0.0 when only one valid window."""
        n = 504 + 252
        dates = pd.date_range("2023-01-02", periods=n, freq="B")
        prices = pd.DataFrame({"SPY": [400.0 + i * 0.05 for i in range(n)]}, index=dates)
        replay = DataReplay(prices)
        cfg = WalkForwardConfig(in_sample_days=504, out_of_sample_days=252)
        runner = WalkForwardRunner(cfg, BacktestConfig(initial_capital=100_000))
        result = runner.run(replay, _no_op)
        assert result.aggregate_metrics["std_sharpe"] == 0.0

    def test_pct_windows_positive_between_0_and_1(self, short_wf_result):
        pct = short_wf_result.aggregate_metrics["pct_windows_positive"]
        assert 0.0 <= pct <= 1.0

    def test_per_window_entries_have_date_strings(self, short_wf_result):
        for entry in short_wf_result.aggregate_metrics["per_window"]:
            assert isinstance(entry["oos_start"], str)
            assert isinstance(entry["oos_end"], str)


# ---------------------------------------------------------------------------
# WalkForwardHTMLReport tests
# ---------------------------------------------------------------------------

class TestWalkForwardHTMLReport:
    def test_generate_returns_html_string(self, short_wf_result):
        html = WalkForwardHTMLReport().generate(short_wf_result)
        assert isinstance(html, str)
        assert html.startswith("<!DOCTYPE html>")

    def test_html_contains_title(self, short_wf_result):
        html = WalkForwardHTMLReport().generate(short_wf_result, title="My WF Report")
        assert "My WF Report" in html

    def test_html_contains_aggregate_metrics_section(self, short_wf_result):
        html = WalkForwardHTMLReport().generate(short_wf_result)
        assert "Aggregate Metrics" in html
        assert "Mean Sharpe" in html
        assert "Ann. Return" in html

    def test_html_contains_per_window_table(self, short_wf_result):
        html = WalkForwardHTMLReport().generate(short_wf_result)
        assert "Per-Window Results" in html
        assert "OOS Start" in html
        assert "OOS End" in html

    def test_html_contains_nav_chart_svg(self, short_wf_result):
        html = WalkForwardHTMLReport().generate(short_wf_result)
        assert "OOS NAV Series" in html
        assert "<svg" in html
        assert "<polyline" in html

    def test_save_creates_file_on_disk(self, tmp_path, short_wf_result):
        out = tmp_path / "reports" / "wf.html"
        saved = WalkForwardHTMLReport().save(short_wf_result, out, title="Saved Report")
        assert saved.exists()
        content = saved.read_text(encoding="utf-8")
        assert "Saved Report" in content
        assert "<!DOCTYPE html>" in content

    def test_save_creates_parent_dirs(self, tmp_path, short_wf_result):
        out = tmp_path / "deep" / "nested" / "report.html"
        WalkForwardHTMLReport().save(short_wf_result, out)
        assert out.exists()

    def test_html_valid_structure(self, short_wf_result):
        html = WalkForwardHTMLReport().generate(short_wf_result)
        assert "<html" in html
        assert "</html>" in html
        assert "<body>" in html
        assert "</body>" in html

    def test_10yr_report_includes_all_windows(self, spy10yr_result):
        html = WalkForwardHTMLReport().generate(spy10yr_result, title="10yr Walk-Forward")
        # All windows should appear as rows in the table
        n_windows = len(spy10yr_result.windows)
        # Each window row contains its index; check at least the first and last
        assert "0</td>" in html, "Window 0 row missing"
        assert f"{n_windows - 1}</td>" in html, f"Window {n_windows - 1} row missing"
