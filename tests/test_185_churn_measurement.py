"""#185: misura del churn S1 post-flip, senza DB o Redis reali."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from scripts.measure_185_churn import _fetch_rows, classify_drops, per_session


def _ts(day: int, hour: int, minute: int, second: int = 0) -> datetime:
    return datetime(2026, 8, day, hour, minute, second, tzinfo=timezone.utc)


def _row(
    day: int,
    hour: int,
    minute: int,
    symbol: str,
    decision: str,
    *,
    strategy_id: str = "S1",
    target_weight: float = 0.012,
    order_id: str | None = "executed-order",
    exit_mechanism: str | None = None,
) -> dict:
    return {
        "tick_time": _ts(day, hour, minute),
        "symbol": symbol,
        "decision": decision,
        "exit_mechanism": exit_mechanism,
        "strategy_id": strategy_id,
        "target_weight": target_weight,
        "order_id": order_id,
    }


def _drop(*, day: int = 5, hour: int = 17, minute: int = 52, **overrides) -> dict:
    return _row(
        day,
        hour,
        minute,
        overrides.pop("symbol", "BP"),
        "SELL",
        exit_mechanism="s1_weight_drop",
        **overrides,
    )


def _buy(*, day: int = 5, hour: int = 18, minute: int = 7, **overrides) -> dict:
    return _row(
        day,
        hour,
        minute,
        overrides.pop("symbol", "BP"),
        "BUY",
        **overrides,
    )


def test_same_s1_weight_rebought_after_15_minutes_is_churn():
    drops = classify_drops([_drop(), _buy()])

    assert drops == [
        {
            "tick_time": _ts(5, 17, 52),
            "symbol": "BP",
            "target_weight": pytest.approx(0.012),
            "reentry_time": _ts(5, 18, 7),
            "is_churn": True,
        }
    ]


def test_reentry_before_15_minutes_is_not_churn():
    drops = classify_drops([_drop(), _buy(hour=18, minute=6)])

    assert drops[0]["is_churn"] is False


def test_reentry_at_60_minutes_is_churn_but_later_is_not():
    at_limit = classify_drops([_drop(), _buy(hour=18, minute=52)])
    after_limit = classify_drops([_drop(), _buy(hour=18, minute=53)])

    assert at_limit[0]["is_churn"] is True
    assert after_limit[0]["is_churn"] is False


def test_s4_buy_is_not_an_s1_reentry():
    drops = classify_drops([_drop(), _buy(strategy_id="S4")])

    assert drops[0]["is_churn"] is False


def test_different_weight_is_not_the_round_trip_signature():
    drops = classify_drops([_drop(target_weight=0.012), _buy(target_weight=0.02)])

    assert drops[0]["is_churn"] is False


def test_same_reported_weight_uses_the_scheduler_display_granularity():
    # BP 2026-08-05: entrambi sono il target 1,2% riportato dal Decision Log.
    drops = classify_drops(
        [
            _drop(target_weight=0.01158564164115341),
            _buy(target_weight=0.011585121552000146),
        ]
    )

    assert drops[0]["is_churn"] is True


def test_buy_without_order_id_was_not_executed_and_is_not_churn():
    drops = classify_drops([_drop(), _buy(order_id=None)])

    assert drops[0]["is_churn"] is False


def test_different_symbol_is_not_a_reentry():
    drops = classify_drops([_drop(), _buy(symbol="SNOW")])

    assert drops[0]["is_churn"] is False


def test_only_executed_s1_weight_drops_are_classified():
    rows = [
        _drop(symbol="BP"),
        _drop(symbol="SNOW", strategy_id="S4"),
        _drop(symbol="SBUX", order_id=None),
        _row(5, 17, 52, "ABBV", "SELL", exit_mechanism="sentiment_reversal"),
    ]

    assert [drop["symbol"] for drop in classify_drops(rows)] == ["BP"]


def test_no_matching_reentry_is_a_definitive_monthly_liquidation():
    drops = classify_drops([_drop(day=7, hour=14, minute=22, symbol="BRK.B")])

    assert drops[0]["reentry_time"] is None
    assert drops[0]["is_churn"] is False


def test_fetch_rows_acquires_strategy_weight_and_executed_order_id():
    cursor = MagicMock()
    cursor.fetchall.return_value = [
        {
            "tick_time": _ts(5, 17, 52),
            "symbol": "BP",
            "decision": "SELL",
            "exit_mechanism": "s1_weight_drop",
            "strategy_id": "S1",
            "target_weight": 0.012,
            "order_id": "sell-order",
        }
    ]
    conn = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cursor

    rows = _fetch_rows(conn, _ts(1, 0, 0))

    assert rows == [dict(cursor.fetchall.return_value[0])]
    sql = " ".join(cursor.execute.call_args.args[0].split()).lower()
    assert "stop_strategy as strategy_id" in sql
    assert "score as target_weight" in sql
    assert sql.count("order_id is not null") == 2


def test_drops_are_aggregated_by_utc_session_and_deploy_phase():
    deploy = _ts(7, 14, 7)
    drops = [
        {
            "tick_time": _ts(5, 17, 52),
            "symbol": "BP",
            "target_weight": 0.012,
            "reentry_time": _ts(5, 18, 7),
            "is_churn": True,
        },
        {
            "tick_time": _ts(7, 14, 22),
            "symbol": "BRK.B",
            "target_weight": 0.012,
            "reentry_time": None,
            "is_churn": False,
        },
    ]

    assert per_session(drops, deploy) == [
        {"date": "2026-08-05", "phase": "pre", "drops": 1, "churn": 1},
        {"date": "2026-08-07", "phase": "post", "drops": 1, "churn": 0},
    ]
