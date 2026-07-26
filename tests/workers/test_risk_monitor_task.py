"""Risk monitor task: real NAV/exposure from Alpaca (fix forensic 2026-07-02 findings).

Before this fix `_fetch_strategy_data` hardcoded total_exposure=1.0 (the
"exposure 100% > 50%" alert fired every single day) and approximated NAV as the
cumulative net_pnl sum (reported as a negative "NAV"). NAV must be the Alpaca
account equity and exposure the gross position value as a fraction of it.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

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
    def test_report_carries_alpaca_nav_and_exposure_no_false_alert(self, monkeypatch):
        """Regression: with real exposure below the 50% threshold, the daily
        'Total portfolio exposure 100.0% exceeds 50%' false alert must not fire."""
        monkeypatch.setattr(rmt, "_fetch_strategy_data", lambda pg: (
            {"portfolio": [0.001] * 60}, {"portfolio": 1.0},
        ))
        monkeypatch.setattr(rmt, "_fetch_account_state", lambda: (100000.0, 0.42))
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

    def test_fetch_strategy_data_no_longer_reports_placeholder_exposure(self):
        """_fetch_strategy_data is PG-only now: returns/weights, no NAV/exposure."""
        pg = MagicMock()
        cur = pg._get_connection.return_value.cursor.return_value.__enter__.return_value
        cur.fetchall.return_value = [("2026-07-01", 0.001, 10.0)]
        returns, weights = rmt._fetch_strategy_data(pg)
        assert returns == {"portfolio": [0.001]}
        assert weights == {"portfolio": 1.0}
