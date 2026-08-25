"""T-602: PortfolioRiskMonitor tests."""
from __future__ import annotations

import math
from dataclasses import asdict
from datetime import datetime, timezone

import numpy as np
import pytest

from src.portfolio.risk_monitor import (
    Alert,
    AlertLevel,
    PortfolioRiskMonitor,
    RiskReport,
    StrategyRiskMetrics,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _flat_returns(n: int = 60, val: float = 0.001) -> list[float]:
    """Flat daily returns (no drawdown)."""
    return [val] * n


def _trending_down(n: int = 60) -> list[float]:
    """Returns that produce a large drawdown."""
    returns = [0.01] * 10 + [-0.03] * 20 + [0.0] * 30
    return returns[:n]


def _make_monitor(
    target_weights: dict[str, float] | None = None,
) -> PortfolioRiskMonitor:
    if target_weights is None:
        target_weights = {"S1": 0.4, "S2": 0.3, "S4": 0.3}
    return PortfolioRiskMonitor(target_weights=target_weights)


def _make_report(monitor: PortfolioRiskMonitor | None = None, **kwargs) -> RiskReport:
    if monitor is None:
        monitor = _make_monitor()
    defaults = dict(
        strategy_returns={
            "S1": _flat_returns(),
            "S2": _flat_returns(),
            "S4": _flat_returns(),
        },
        current_weights={"S1": 0.4, "S2": 0.3, "S4": 0.3},
        total_exposure=0.45,
        nav=100_000.0,
    )
    defaults.update(kwargs)
    return monitor.compute_report(**defaults)


# ── RiskReport structure ──────────────────────────────────────────────────────

def test_risk_report_has_timestamp():
    report = _make_report()
    assert isinstance(report.timestamp, datetime)


def test_risk_report_has_nav():
    report = _make_report(nav=150_000.0)
    assert report.nav == 150_000.0


def test_risk_report_has_total_exposure():
    report = _make_report(total_exposure=0.45)
    assert report.total_exposure == pytest.approx(0.45)


def test_risk_report_has_herfindahl_index():
    report = _make_report()
    assert hasattr(report, "herfindahl_index")
    assert 0.0 <= report.herfindahl_index <= 1.0


def test_risk_report_has_combined_drawdown():
    report = _make_report()
    assert hasattr(report, "combined_drawdown")


def test_risk_report_has_per_strategy_metrics():
    report = _make_report()
    assert isinstance(report.per_strategy_metrics, dict)
    assert "S1" in report.per_strategy_metrics


def test_risk_report_has_alerts_list():
    report = _make_report()
    assert isinstance(report.alerts, list)


# ── StrategyRiskMetrics ───────────────────────────────────────────────────────

def test_strategy_metrics_has_drawdown():
    report = _make_report()
    metrics = report.per_strategy_metrics["S1"]
    assert isinstance(metrics, StrategyRiskMetrics)
    assert hasattr(metrics, "drawdown")


def test_strategy_metrics_has_sharpe():
    report = _make_report()
    metrics = report.per_strategy_metrics["S1"]
    assert hasattr(metrics, "sharpe")


def test_strategy_metrics_has_volatility():
    report = _make_report()
    metrics = report.per_strategy_metrics["S1"]
    assert hasattr(metrics, "volatility")
    assert metrics.volatility >= 0.0


def test_strategy_metrics_has_daily_pnl():
    report = _make_report(nav=100_000.0)
    metrics = report.per_strategy_metrics["S1"]
    assert hasattr(metrics, "daily_pnl")


def test_strategy_metrics_present_for_all_strategies():
    report = _make_report()
    assert set(report.per_strategy_metrics.keys()) == {"S1", "S2", "S4"}


# ── Drawdown computation ──────────────────────────────────────────────────────

def test_flat_returns_produce_zero_drawdown():
    report = _make_report(strategy_returns={"S1": _flat_returns(), "S2": _flat_returns(), "S4": _flat_returns()})
    dd = report.per_strategy_metrics["S1"].drawdown
    assert dd == pytest.approx(0.0, abs=1e-6)


def test_trending_down_returns_produce_large_drawdown():
    rets = _trending_down()
    report = _make_report(strategy_returns={"S1": rets, "S2": _flat_returns(), "S4": _flat_returns()})
    dd = report.per_strategy_metrics["S1"].drawdown
    assert dd > 0.05


def test_drawdown_is_non_negative():
    report = _make_report(
        strategy_returns={"S1": _trending_down(), "S2": _flat_returns(), "S4": _flat_returns()}
    )
    for metrics in report.per_strategy_metrics.values():
        assert metrics.drawdown >= 0.0


# ── Herfindahl index ──────────────────────────────────────────────────────────

def test_equal_weights_produce_low_herfindahl():
    report = _make_report(current_weights={"S1": 1 / 3, "S2": 1 / 3, "S4": 1 / 3})
    # HHI for 3 equal weights = 3 * (1/3)^2 = 1/3
    assert report.herfindahl_index == pytest.approx(1 / 3, abs=0.01)


def test_concentrated_weights_produce_high_herfindahl():
    report = _make_report(current_weights={"S1": 0.9, "S2": 0.05, "S4": 0.05})
    assert report.herfindahl_index > 0.7


def test_herfindahl_bounded_between_zero_and_one():
    report = _make_report()
    assert 0.0 <= report.herfindahl_index <= 1.0


# ── Alert thresholds ──────────────────────────────────────────────────────────

def test_strategy_drawdown_over_10pct_fires_alert():
    bad_rets = [0.02] * 5 + [-0.04] * 25 + [0.0] * 30
    monitor = _make_monitor()
    report = monitor.compute_report(
        strategy_returns={"S1": bad_rets, "S2": _flat_returns(), "S4": _flat_returns()},
        current_weights={"S1": 0.4, "S2": 0.3, "S4": 0.3},
        total_exposure=0.40,
        nav=100_000.0,
    )
    alert_msgs = [a.message for a in report.alerts]
    strategy_alerts = [a for a in report.alerts if a.strategy_id == "S1" and a.level == AlertLevel.ALERT]
    assert len(strategy_alerts) > 0


def test_strategy_drawdown_under_10pct_no_alert():
    ok_rets = [0.005] * 10 + [-0.002] * 10 + [0.005] * 40
    report = _make_report(
        strategy_returns={"S1": ok_rets, "S2": _flat_returns(), "S4": _flat_returns()}
    )
    strategy_drawdown_alerts = [
        a for a in report.alerts
        if a.strategy_id == "S1" and a.level == AlertLevel.ALERT and "drawdown" in a.message.lower()
    ]
    assert len(strategy_drawdown_alerts) == 0


def test_combined_drawdown_over_15pct_fires_critical():
    bad_rets = [0.02] * 3 + [-0.06] * 30 + [0.0] * 27
    monitor = _make_monitor()
    report = monitor.compute_report(
        strategy_returns={"S1": bad_rets, "S2": bad_rets, "S4": bad_rets},
        current_weights={"S1": 0.4, "S2": 0.3, "S4": 0.3},
        total_exposure=0.40,
        nav=100_000.0,
    )
    critical = [a for a in report.alerts if a.level == AlertLevel.CRITICAL]
    assert len(critical) > 0


def test_weight_drift_over_5pct_fires_warning():
    monitor = _make_monitor(target_weights={"S1": 0.4, "S2": 0.3, "S4": 0.3})
    report = monitor.compute_report(
        strategy_returns={"S1": _flat_returns(), "S2": _flat_returns(), "S4": _flat_returns()},
        current_weights={"S1": 0.47, "S2": 0.3, "S4": 0.23},  # S1 drifted +7%, S4 -7%
        total_exposure=0.40,
        nav=100_000.0,
    )
    weight_warnings = [
        a for a in report.alerts if a.level == AlertLevel.WARNING and "weight" in a.message.lower()
    ]
    assert len(weight_warnings) > 0


def test_weight_drift_under_5pct_no_warning():
    monitor = _make_monitor(target_weights={"S1": 0.4, "S2": 0.3, "S4": 0.3})
    report = monitor.compute_report(
        strategy_returns={"S1": _flat_returns(), "S2": _flat_returns(), "S4": _flat_returns()},
        current_weights={"S1": 0.42, "S2": 0.30, "S4": 0.28},  # all within 2%
        total_exposure=0.40,
        nav=100_000.0,
    )
    weight_warnings = [
        a for a in report.alerts if a.level == AlertLevel.WARNING and "weight" in a.message.lower()
    ]
    assert len(weight_warnings) == 0


def test_high_correlation_fires_warning():
    # Two strategies with nearly identical returns → correlation ≈ 1.0
    rets = [0.01 * (i % 5 - 2) for i in range(60)]
    slightly_different = [r + 0.0001 * i for i, r in enumerate(rets)]
    monitor = _make_monitor()
    report = monitor.compute_report(
        strategy_returns={"S1": rets, "S2": slightly_different, "S4": _flat_returns()},
        current_weights={"S1": 0.4, "S2": 0.3, "S4": 0.3},
        total_exposure=0.40,
        nav=100_000.0,
    )
    corr_warnings = [
        a for a in report.alerts if a.level == AlertLevel.WARNING and "corr" in a.message.lower()
    ]
    assert len(corr_warnings) > 0


def test_low_correlation_no_warning():
    rets_s1 = [0.01 * math.sin(i * 0.3) for i in range(60)]
    rets_s2 = [0.01 * math.cos(i * 0.3) for i in range(60)]
    monitor = _make_monitor()
    report = monitor.compute_report(
        strategy_returns={"S1": rets_s1, "S2": rets_s2, "S4": _flat_returns(val=0.0)},
        current_weights={"S1": 0.4, "S2": 0.3, "S4": 0.3},
        total_exposure=0.40,
        nav=100_000.0,
    )
    corr_warnings = [
        a for a in report.alerts if a.level == AlertLevel.WARNING and "corr" in a.message.lower()
    ]
    assert len(corr_warnings) == 0


def test_exposure_over_50pct_fires_alert():
    report = _make_report(total_exposure=0.55)
    exposure_alerts = [
        a for a in report.alerts if a.level == AlertLevel.ALERT and "exposure" in a.message.lower()
    ]
    assert len(exposure_alerts) > 0


def test_exposure_under_50pct_no_alert():
    report = _make_report(total_exposure=0.45)
    exposure_alerts = [
        a for a in report.alerts if a.level == AlertLevel.ALERT and "exposure" in a.message.lower()
    ]
    assert len(exposure_alerts) == 0


def test_multiple_alerts_can_fire_simultaneously():
    bad_rets = [0.02] * 3 + [-0.05] * 30 + [0.0] * 27
    monitor = _make_monitor(target_weights={"S1": 0.4, "S2": 0.3, "S4": 0.3})
    report = monitor.compute_report(
        strategy_returns={"S1": bad_rets, "S2": bad_rets, "S4": bad_rets},
        current_weights={"S1": 0.5, "S2": 0.3, "S4": 0.2},
        total_exposure=0.60,
        nav=100_000.0,
    )
    assert len(report.alerts) >= 2


def test_clean_portfolio_produces_no_alerts():
    report = _make_report(
        strategy_returns={"S1": _flat_returns(), "S2": _flat_returns(val=0.0015), "S4": _flat_returns(val=0.0008)},
        current_weights={"S1": 0.4, "S2": 0.3, "S4": 0.3},
        total_exposure=0.40,
    )
    assert len(report.alerts) == 0


# ── AlertLevel enum ───────────────────────────────────────────────────────────

def test_alert_level_has_three_levels():
    assert hasattr(AlertLevel, "WARNING")
    assert hasattr(AlertLevel, "ALERT")
    assert hasattr(AlertLevel, "CRITICAL")


def test_alert_has_level_strategy_and_message():
    alert = Alert(level=AlertLevel.WARNING, message="test", strategy_id="S1")
    assert alert.level == AlertLevel.WARNING
    assert alert.message == "test"
    assert alert.strategy_id == "S1"


class TestEquityDrawdown:
    """#107: alert drawdown must come from the equity level curve."""

    def test_monotonic_increase_has_no_drawdown(self):
        from src.portfolio.risk_monitor import max_drawdown_from_equity
        assert max_drawdown_from_equity([100.0, 110.0, 120.0]) == 0.0

    def test_peak_to_trough(self):
        from src.portfolio.risk_monitor import max_drawdown_from_equity
        # peak 120 → trough 90 → 25%
        assert max_drawdown_from_equity([100.0, 120.0, 90.0, 110.0]) == 0.25

    def test_needs_two_positive_points(self):
        from src.portfolio.risk_monitor import max_drawdown_from_equity
        assert max_drawdown_from_equity([100.0]) == 0.0
        assert max_drawdown_from_equity([]) == 0.0

    def test_ignores_nonpositive_points(self):
        from src.portfolio.risk_monitor import max_drawdown_from_equity
        # only [100, 90] count → 10%
        assert max_drawdown_from_equity([0.0, -5.0, 100.0, 90.0]) == pytest.approx(0.10)


class TestCombinedDrawdownOverride:
    """#107: when an equity-derived drawdown override is supplied it drives the
    field and the CRITICAL alert, not the trade-return series."""

    def test_override_above_threshold_fires_critical(self):
        from src.portfolio.risk_monitor import AlertLevel
        report = _make_report(combined_drawdown_override=0.20)
        assert report.combined_drawdown == 0.20
        assert any(a.level == AlertLevel.CRITICAL for a in report.alerts)

    def test_override_below_threshold_no_critical(self):
        from src.portfolio.risk_monitor import AlertLevel
        report = _make_report(combined_drawdown_override=0.10)
        assert report.combined_drawdown == 0.10
        assert not any(a.level == AlertLevel.CRITICAL for a in report.alerts)


class TestHerfindahlOverride:
    """#75: HHI must come from real per-symbol weights, supplied via override."""

    def test_override_used_when_provided(self):
        report = _make_report(herfindahl_override=0.25)
        assert report.herfindahl_index == 0.25

    def test_explicit_none_marks_metric_unavailable(self):
        report = _make_report(herfindahl_override=None)
        assert report.herfindahl_index is None

    def test_falls_back_to_current_weights_without_override(self):
        # No override → uses _herfindahl(current_weights). With the same synthetic
        # single-entry dict that risk_monitor_task passes, HHI = 1.0.
        report = _make_report(current_weights={"portfolio": 1.0})
        assert report.herfindahl_index == pytest.approx(1.0)


class TestFetchEquityCurve:
    def test_appends_current_equity_and_drops_bad_rows(self):
        from unittest.mock import MagicMock
        from src.workers.risk_monitor_task import _fetch_equity_curve

        cur = MagicMock()
        cur.fetchall.return_value = [(110_000.0,), (108_000.0,)]
        conn = MagicMock()
        conn.cursor.return_value.__enter__.return_value = cur
        pg = MagicMock()
        pg._get_connection.return_value = conn

        curve = _fetch_equity_curve(pg, current_equity=109_000.0)
        assert curve == [110_000.0, 108_000.0, 109_000.0]

    def test_db_error_returns_current_equity_only(self):
        from unittest.mock import MagicMock
        from src.workers.risk_monitor_task import _fetch_equity_curve

        pg = MagicMock()
        pg._get_connection.side_effect = RuntimeError("db down")
        curve = _fetch_equity_curve(pg, current_equity=109_000.0)
        assert curve == [109_000.0]
