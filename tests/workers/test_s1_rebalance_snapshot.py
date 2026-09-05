"""Snapshot persistente delle decisioni mensili S1 (#489)."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


def test_snapshot_copre_segnali_target_e_posizioni() -> None:
    from src.workers.portfolio_scheduler import _build_s1_rebalance_snapshot_rows

    result = SimpleNamespace(
        target_weights_per_strategy={"S1": {"AAPL": 0.60, "MSFT": 0.40}}
    )
    instance = SimpleNamespace(
        last_signal_snapshot={"AAPL": 1.2, "MSFT": 0.4, "NVDA": -0.7}
    )
    portfolio = MagicMock()
    portfolio.cash = 100.0
    portfolio.all_positions.return_value = [
        SimpleNamespace(symbol="AAPL", quantity=2.0),
        SimpleNamespace(symbol="TSLA", quantity=1.0),
    ]
    market = SimpleNamespace(
        prices={"AAPL": 50.0, "MSFT": 25.0, "NVDA": 10.0, "TSLA": 100.0}
    )
    ts = datetime(2026, 9, 1, 14, 7, tzinfo=UTC)

    rows = _build_s1_rebalance_snapshot_rows(
        result=result,
        ts=ts,
        instance=instance,
        portfolio=portfolio,
        market=market,
        allocation_pct=0.50,
    )

    by_symbol = {row["symbol"]: row for row in rows}
    assert set(by_symbol) == {"AAPL", "MSFT", "NVDA", "TSLA"}
    assert by_symbol["AAPL"] == {
        "strategy_id": "S1",
        "rebalance_ts": ts,
        "symbol": "AAPL",
        "signal_z": pytest.approx(1.2),
        "weight": pytest.approx(0.60),
        "in_target": True,
        "held": True,
        "position_market_value": pytest.approx(100.0),
        "target_notional": pytest.approx(90.0),
    }
    assert by_symbol["NVDA"]["weight"] == 0.0
    assert by_symbol["NVDA"]["in_target"] is False
    assert by_symbol["NVDA"]["position_market_value"] == 0.0
    assert by_symbol["TSLA"]["signal_z"] is None
    assert by_symbol["TSLA"]["held"] is True
    assert by_symbol["TSLA"]["target_notional"] == 0.0


def test_snapshot_non_viene_costruito_quando_s1_non_ribilancia() -> None:
    from src.workers.portfolio_scheduler import _build_s1_rebalance_snapshot_rows

    rows = _build_s1_rebalance_snapshot_rows(
        result=SimpleNamespace(target_weights_per_strategy={}),
        ts=datetime(2026, 9, 2, 14, 7, tzinfo=UTC),
        instance=SimpleNamespace(last_signal_snapshot={"AAPL": 1.0}),
        portfolio=MagicMock(),
        market=SimpleNamespace(prices={"AAPL": 100.0}),
        allocation_pct=0.50,
    )

    assert rows == []


def test_un_errore_nello_snapshot_non_blocca_il_ciclo_live() -> None:
    from src.workers.portfolio_scheduler import _persist_s1_rebalance_snapshot

    portfolio = MagicMock()
    portfolio.all_positions.side_effect = RuntimeError("posizioni indisponibili")

    # La misura e' fail-open: nessun errore di osservabilita' deve impedire la
    # successiva submission degli ordini gia' decisi dall'orchestratore.
    _persist_s1_rebalance_snapshot(
        result=SimpleNamespace(target_weights_per_strategy={"S1": {"AAPL": 1.0}}),
        ts=datetime(2026, 9, 1, 14, 7, tzinfo=UTC),
        instance=SimpleNamespace(last_signal_snapshot={"AAPL": 1.0}),
        portfolio=portfolio,
        market=SimpleNamespace(prices={"AAPL": 100.0}),
        allocation_pct=0.50,
    )
