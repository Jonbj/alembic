"""Osservabilita' del ribilanciamento S1 prima dell'isteresi (#468)."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock


def test_osservazione_cattura_i_pesi_s1_passati_a_zero() -> None:
    from src.workers.portfolio_scheduler import _observe_rebalance_transitions

    result = SimpleNamespace(
        target_weights_per_strategy={
            "S1": {"AAPL": 0.6, "GOOGL": 0.4},
            "S4": {"NVDA": 1.0},
        }
    )

    rebalanced, zeroed = _observe_rebalance_transitions(
        result,
        {
            "S1": {"AAPL": 0.5, "GE": 0.25, "MMM": 0.25},
        },
    )

    assert rebalanced == ["S1", "S4"]
    assert zeroed == {"S1": ["GE", "MMM"]}


def test_osservazione_non_inventa_transizioni_senza_target_precedente() -> None:
    from src.workers.portfolio_scheduler import _observe_rebalance_transitions

    result = SimpleNamespace(target_weights_per_strategy={"S1": {"AAPL": 1.0}})

    rebalanced, zeroed = _observe_rebalance_transitions(result, {})

    assert rebalanced == ["S1"]
    assert zeroed == {}


def test_persist_cycle_result_scrive_i_campi_di_ribilanciamento() -> None:
    from src.workers.portfolio_scheduler import _persist_cycle_result

    cursor = MagicMock()
    conn = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cursor
    conn.cursor.return_value.__exit__.return_value = False
    cycle_data = {
        "timestamp": datetime(2026, 9, 1, 14, 7, tzinfo=UTC),
        "strategies_run": ["S1", "S4"],
        "orders_count": 45,
        "constraints_fired": [],
        "final_orders": [],
        "rebalanced_strategies": ["S1", "S4"],
        "zero_weight_symbols": {"S1": ["ARM", "GE", "MMM", "TXN"]},
    }

    _persist_cycle_result(cycle_data, conn=conn)

    sql, params = cursor.execute.call_args.args
    assert "rebalanced_strategies" in sql
    assert "zero_weight_symbols" in sql
    assert params[-2] == '["S1", "S4"]'
    assert params[-1] == '{"S1": ["ARM", "GE", "MMM", "TXN"]}'


def test_store_restituisce_i_campi_di_ribilanciamento() -> None:
    from src.store.pg_store import PostgreSQLStore

    ts = datetime(2026, 9, 1, 14, 7, tzinfo=UTC)
    cursor = MagicMock()
    cursor.fetchone.return_value = (
        ts,
        ["S1", "S4"],
        45,
        [],
        [],
        ["S1", "S4"],
        {"S1": ["ARM", "GE", "MMM", "TXN"]},
    )
    conn = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cursor
    conn.cursor.return_value.__exit__.return_value = False
    store = PostgreSQLStore(conn=conn, use_pool=False)

    row = store.get_last_portfolio_cycle()

    assert row is not None
    assert row["rebalanced_strategies"] == ["S1", "S4"]
    assert row["zero_weight_symbols"] == {
        "S1": ["ARM", "GE", "MMM", "TXN"]
    }
    sql = " ".join(cursor.execute.call_args.args[0].split())
    assert "rebalanced_strategies" in sql
    assert "zero_weight_symbols" in sql
