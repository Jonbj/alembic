"""Tests for paper-validation metrics (point 3)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.analytics.paper_validation import (
    compute_churn,
    compute_exit_breakdown,
    compute_pnl,
    compute_turnover,
    compute_validation_metrics,
)

_T0 = datetime(2026, 6, 26, 14, 0, tzinfo=timezone.utc)


def _trade(symbol, notional, *, hold_min=None, net=None, gross=None, exit_reason=None):
    entry = _T0
    exit_t = _T0 + timedelta(minutes=hold_min) if hold_min is not None else None
    return {
        "symbol": symbol,
        "entry_time": entry,
        "entry_notional": notional,
        "exit_time": exit_t,
        "exit_reason": exit_reason,
        "net_pnl": net,
        "gross_pnl": gross,
    }


class TestTurnover:
    def test_ratio(self):
        trades = [_trade("A", 1000), _trade("B", 1000)]
        out = compute_turnover(trades, nav=100_000.0)
        assert out["traded_notional"] == 2000.0
        assert out["turnover_ratio"] == pytest.approx(0.02)

    def test_no_nav(self):
        assert compute_turnover([_trade("A", 1000)], nav=None)["turnover_ratio"] is None


class TestChurn:
    def test_roundtrips_detected(self):
        trades = [_trade("TSM", 900), _trade("TSM", 900), _trade("TSM", 900), _trade("AMD", 900)]
        out = compute_churn(trades)
        assert out["total_opens"] == 4
        assert out["distinct_symbols"] == 2
        assert out["roundtrip_symbols"] == {"TSM": 3}
        assert out["roundtrip_count"] == 1

    def test_avg_hold(self):
        trades = [_trade("A", 900, hold_min=90), _trade("B", 900, hold_min=120)]
        assert compute_churn(trades)["avg_hold_minutes"] == pytest.approx(105.0)

    def test_open_trades_no_hold(self):
        assert compute_churn([_trade("A", 900)])["avg_hold_minutes"] is None


class TestPnl:
    def test_realized_and_costs(self):
        trades = [
            _trade("A", 900, hold_min=90, net=10.0, gross=12.0, exit_reason="portfolio_sell"),
            _trade("B", 900, hold_min=90, net=-5.0, gross=-4.0, exit_reason="stop_loss"),
            _trade("C", 900),  # open
        ]
        out = compute_pnl(trades)
        assert out["closed_trades"] == 2
        assert out["open_trades"] == 1
        assert out["realized_net_pnl"] == pytest.approx(5.0)
        assert out["realized_gross_pnl"] == pytest.approx(8.0)
        assert out["cost_drag"] == pytest.approx(3.0)
        assert out["win_rate"] == pytest.approx(0.5)
        assert out["open_notional"] == pytest.approx(900.0)

    def test_no_closed(self):
        assert compute_pnl([_trade("A", 900)])["win_rate"] is None


class TestExitBreakdown:
    def test_counts(self):
        trades = [
            _trade("A", 900, hold_min=90, exit_reason="portfolio_sell"),
            _trade("B", 900, hold_min=90, exit_reason="portfolio_sell"),
            _trade("C", 900, hold_min=90, exit_reason="stop_loss"),
            _trade("D", 900),  # open — excluded
        ]
        assert compute_exit_breakdown(trades) == {"portfolio_sell": 2, "stop_loss": 1}


class TestAggregate:
    def test_deployment_pct(self):
        trades = [_trade("A", 900), _trade("B", 1100)]  # both open
        out = compute_validation_metrics(trades, nav=100_000.0, regime_mult=0.7, window_days=7)
        assert out["deployment_pct"] == pytest.approx(0.02)  # 2000/100000
        assert out["regime_mult"] == 0.7
        assert out["window_days"] == 7
        assert out["pnl"]["open_notional"] == pytest.approx(2000.0)

    def test_robust_to_none_values(self):
        trades = [{"symbol": "A", "entry_time": _T0, "entry_notional": None,
                   "exit_time": None, "exit_reason": None, "net_pnl": None, "gross_pnl": None}]
        out = compute_validation_metrics(trades, nav=None)
        assert out["nav"] is None
        assert out["deployment_pct"] is None
        assert out["turnover"]["traded_notional"] == 0.0

    def test_empty(self):
        out = compute_validation_metrics([], nav=100_000.0, regime_mult=0.7)
        assert out["pnl"]["closed_trades"] == 0
        assert out["deployment_pct"] == 0.0
