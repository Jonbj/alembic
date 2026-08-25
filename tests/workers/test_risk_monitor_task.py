"""Risk monitor task: real NAV/exposure from Alpaca (fix forensic 2026-07-02 findings).

Before this fix `_fetch_strategy_data` hardcoded total_exposure=1.0 (the
"exposure 100% > 50%" alert fired every single day) and approximated NAV as the
cumulative net_pnl sum (reported as a negative "NAV"). NAV must be the Alpaca
account equity and exposure the gross position value as a fraction of it.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.portfolio.risk_monitor import AlertLevel
from src.workers import risk_monitor_task as rmt


def _mock_client(equity: str, market_values: list[str]) -> MagicMock:
    client = MagicMock()
    client.get_account.return_value = MagicMock(equity=equity)
    client.get_all_positions.return_value = [
        MagicMock(market_value=mv) for mv in market_values
    ]
    return client


class TestFetchAccountState:
    def test_returns_equity_as_nav_and_gross_exposure_fraction(self):
        client = _mock_client("100000", ["30000", "-20000"])
        with patch("alpaca.trading.client.TradingClient", return_value=client):
            nav, exposure = rmt._fetch_account_state()
        assert nav == pytest.approx(100000.0)
        # gross = |30000| + |-20000| = 50000 → 50% of equity
        assert exposure == pytest.approx(0.5)

    def test_no_positions_means_zero_exposure(self):
        client = _mock_client("50000", [])
        with patch("alpaca.trading.client.TradingClient", return_value=client):
            nav, exposure = rmt._fetch_account_state()
        assert nav == pytest.approx(50000.0)
        assert exposure == 0.0

    def test_broker_unreachable_returns_zeros(self):
        with patch("alpaca.trading.client.TradingClient", side_effect=OSError("down")):
            nav, exposure = rmt._fetch_account_state()
        assert nav == 0.0
        assert exposure == 0.0


class TestFetchPositionWeights:
    """#75: per-symbol notional weights for a meaningful concentration metric."""

    def test_normalizes_by_gross(self):
        from unittest.mock import MagicMock, patch
        from src.workers.risk_monitor_task import _fetch_position_weights

        p1 = MagicMock(); p1.symbol = "AAPL"; p1.market_value = "3000"
        p2 = MagicMock(); p2.symbol = "MSFT"; p2.market_value = "1000"
        client = MagicMock()
        client.get_all_positions.return_value = [p1, p2]
        with patch("alpaca.trading.client.TradingClient", return_value=client):
            weights = _fetch_position_weights()
        assert weights == {"AAPL": 0.75, "MSFT": 0.25}

    def test_empty_on_broker_error(self):
        from unittest.mock import patch
        from src.workers.risk_monitor_task import _fetch_position_weights

        with patch("alpaca.trading.client.TradingClient", side_effect=RuntimeError("down")):
            assert _fetch_position_weights() == {}


class TestComputeRiskReportUsesRealAccountState:
    def test_report_carries_alpaca_nav_and_exposure_no_false_alert(self, monkeypatch):
        """Regression: with real exposure below the 50% threshold, the daily
        'Total portfolio exposure 100.0% exceeds 50%' false alert must not fire."""
        monkeypatch.setattr(rmt, "_fetch_account_state", lambda: (100000.0, 0.42))
        monkeypatch.setattr(
            rmt, "_fetch_equity_curve", lambda pg, ce: [100000.0, 101000.0]
        )
        monkeypatch.setattr(rmt, "_fetch_position_weights", lambda: {})
        stored = {}

        def fake_store(pg, report):
            stored["report"] = report
            return 1

        monkeypatch.setattr(rmt, "_store_risk_report", fake_store)
        with patch("src.store.pg_store.PostgreSQLStore"):
            result = rmt.compute_risk_report()

        report = stored["report"]
        assert report.nav == pytest.approx(100000.0)
        assert report.total_exposure == pytest.approx(0.42)
        assert not any("exposure" in a.message.lower() for a in report.alerts)
        assert result["total_exposure"] == pytest.approx(0.42)

class TestF003NoFalsePortfolioDrawdownAlert:
    """F-003: portfolio_daily_state.daily_return is SUM(net_pnl)/SUM(entry_notional)
    over the trades closed that day — a closed-trades-only notional return, not a
    NAV-based portfolio return. Feeding it into the per-strategy drawdown machinery
    (_compute_drawdown cumprod's it) produced a bogus ~17% 'Strategy portfolio
    drawdown' ALERT every night (14 occurrences, 07-31 → 08-21), while the real
    whole-book drawdown (combined_drawdown, from the Alpaca equity curve) sat at
    ~1.2%. The per-strategy alert is meant for real strategies; the whole-book
    drawdown is combined_drawdown. So no synthetic 'portfolio' per-strategy entry
    must be registered, and the closed-trades series must never reach the per-strategy
    drawdown alert path.
    """

    def _setup_pg(self, daily_return_rows):
        pg = MagicMock()
        cur = pg._get_connection.return_value.cursor.return_value.__enter__.return_value
        cur.fetchall.return_value = daily_return_rows
        return pg, cur

    def test_closed_trades_series_does_not_fire_portfolio_drawdown_alert(
        self, monkeypatch
    ):
        # A closed-trades-only return series that _compute_drawdown would turn into
        # a ~46% drawdown if (wrongly) fed into the per-strategy path.
        noisy_rets = [0.01] * 10 + [-0.03] * 20 + [0.0] * 30
        rows = [
            (f"2026-07-{i+1:02d}", r, -100.0) for i, r in enumerate(noisy_rets)
        ]
        pg, cur = self._setup_pg(rows)

        monkeypatch.setattr(rmt, "_fetch_account_state", lambda: (100_000.0, 0.42))
        # Realistic equity curve → small whole-book drawdown, well under 15%.
        monkeypatch.setattr(
            rmt, "_fetch_equity_curve", lambda pg_, ce: [100_000.0, 99_000.0, 100_500.0]
        )
        monkeypatch.setattr(
            rmt, "_fetch_position_weights", lambda: {"AAPL": 0.6, "MSFT": 0.4}
        )
        stored = {}
        monkeypatch.setattr(
            rmt, "_store_risk_report", lambda pg_, rep: stored.__setitem__("r", rep) or 1
        )

        with patch("src.store.pg_store.PostgreSQLStore", return_value=pg):
            rmt.compute_risk_report()

        report = stored["r"]
        # The false per-strategy 'Strategy portfolio drawdown' ALERT must not fire.
        portfolio_drawdown_alerts = [
            a for a in report.alerts
            if a.strategy_id == "portfolio" and "drawdown" in a.message.lower()
        ]
        assert portfolio_drawdown_alerts == []
        # No synthetic 'portfolio' per-strategy entry at all.
        assert "portfolio" not in report.per_strategy_metrics
        # Whole-book drawdown comes from the equity curve, not the bogus series.
        assert report.combined_drawdown == pytest.approx(0.01, abs=1e-9)

    def test_report_still_carries_whole_book_metrics_without_per_strategy_data(
        self, monkeypatch
    ):
        """Even with no per-strategy return series, the report must still carry the
        meaningful whole-book metrics (combined_drawdown, herfindahl, exposure) and
        fire the exposure alert when exposure exceeds the threshold."""
        monkeypatch.setattr(rmt, "_fetch_account_state", lambda: (100_000.0, 0.55))
        monkeypatch.setattr(
            rmt, "_fetch_equity_curve", lambda pg_, ce: [100_000.0, 90_000.0]
        )
        monkeypatch.setattr(
            rmt, "_fetch_position_weights", lambda: {"AAPL": 0.6, "MSFT": 0.4}
        )
        stored = {}
        monkeypatch.setattr(
            rmt, "_store_risk_report", lambda pg_, rep: stored.__setitem__("r", rep) or 1
        )

        pg = MagicMock()
        with patch("src.store.pg_store.PostgreSQLStore", return_value=pg):
            result = rmt.compute_risk_report()

        report = stored["r"]
        assert report.per_strategy_metrics == {}
        # combined_drawdown from equity curve (100k → 90k = 10%), under the 15%
        # CRITICAL threshold, so no CRITICAL alert.
        assert report.combined_drawdown == pytest.approx(0.10, abs=1e-9)
        assert report.herfindahl_index == pytest.approx(0.52, abs=1e-9)  # 0.6²+0.4²
        # Exposure over 50% still fires its ALERT.
        assert any(
            a.level == AlertLevel.ALERT and "exposure" in a.message.lower()
            for a in report.alerts
        )
        assert result["total_exposure"] == pytest.approx(0.55)

    def test_skips_when_no_equity_curve_and_broker_unreachable(self, monkeypatch):
        """Truly no data (broker down → nav=0, no equity curve) → skip, mirroring the
        old 'no strategy data' skip but now keyed on the equity curve."""
        monkeypatch.setattr(rmt, "_fetch_account_state", lambda: (0.0, 0.0))
        monkeypatch.setattr(rmt, "_fetch_equity_curve", lambda pg_, ce: [])
        monkeypatch.setattr(rmt, "_fetch_position_weights", lambda: {})

        with patch("src.store.pg_store.PostgreSQLStore"):
            result = rmt.compute_risk_report()

        assert result == {"skipped": True, "reason": "no_data"}

    def test_stale_drawdown_warned_when_broker_unreachable(self, monkeypatch, caplog):
        """F-003 point 3: when the broker is unreachable (nav=0) the live equity is
        not appended to the curve, so combined_drawdown is frozen at a historical
        value. That staleness must be surfaced in the logs, not read as a live
        measurement."""
        import logging

        monkeypatch.setattr(rmt, "_fetch_account_state", lambda: (0.0, 0.0))
        # nav=0 so the live equity is NOT appended; curve is historical only.
        monkeypatch.setattr(
            rmt, "_fetch_equity_curve", lambda pg_, ce: [100_000.0, 98_757.1]
        )
        monkeypatch.setattr(rmt, "_fetch_position_weights", lambda: {})
        monkeypatch.setattr(rmt, "_store_risk_report", lambda pg_, rep: 1)

        with patch("src.store.pg_store.PostgreSQLStore"):
            with caplog.at_level(logging.WARNING, logger="src.workers.risk_monitor_task"):
                rmt.compute_risk_report()

        assert any("stale" in r.message.lower() for r in caplog.records)

    def test_no_stale_warning_when_broker_reachable(self, monkeypatch, caplog):
        """With a live nav the curve includes today's equity, so combined_drawdown
        is current and the stale-drawdown warning must not fire."""
        import logging

        monkeypatch.setattr(rmt, "_fetch_account_state", lambda: (100_000.0, 0.42))
        monkeypatch.setattr(
            rmt, "_fetch_equity_curve",
            lambda pg_, ce: [100_000.0, 99_000.0, 100_500.0],
        )
        monkeypatch.setattr(rmt, "_fetch_position_weights", lambda: {})
        monkeypatch.setattr(rmt, "_store_risk_report", lambda pg_, rep: 1)

        with patch("src.store.pg_store.PostgreSQLStore"):
            with caplog.at_level(logging.WARNING, logger="src.workers.risk_monitor_task"):
                rmt.compute_risk_report()

        assert not any("stale" in r.message.lower() for r in caplog.records)
