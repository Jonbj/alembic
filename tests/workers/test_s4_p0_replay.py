"""#296: wiring read-only del replay P0 nel worker di riconciliazione."""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

from src.strategies.s4.lifecycle import (
    BrokerOrderSnapshot,
    MarketSession,
    SubmittedIntent,
    reconcile_entry,
)
from src.strategies.s4.p0_runtime import replay_p0_candidates

ENTRY_AT = datetime(2026, 8, 25, 15, 7, 4, tzinfo=UTC)
TRIGGER_AT = datetime(2026, 8, 25, 17, 52, tzinfo=UTC)
EXIT_AT = TRIGGER_AT + timedelta(seconds=3)


def _candidate(**overrides) -> dict:
    intent = SubmittedIntent(
        intent_id="34d6c4c0-bcb2-55ef-a0f4-e3db1a4a13b0",
        symbol="AMD",
        order_id="entry-order-1",
        submitted_at=ENTRY_AT - timedelta(seconds=4),
        requested_quantity=2.0,
        requested_notional=210.0,
        first_executable_price=105.0,
        first_executable_price_source="alpaca_snapshot.latest_trade",
        policy_version="s4-exit-trial:1.0.0",
        sleeve_contributions={"S4": 1.0},
    )
    sessions = [
        MarketSession(
            session_date=date(2026, 8, day),
            open_at=datetime(2026, 8, day, 13, 30, tzinfo=UTC),
            close_at=datetime(2026, 8, day, 20, 0, tzinfo=UTC),
        )
        for day in (25, 26, 27)
    ]
    entry = reconcile_entry(
        intent,
        BrokerOrderSnapshot(
            order_id="entry-order-1",
            status="filled",
            filled_at=ENTRY_AT,
            filled_quantity=2.0,
            filled_avg_price=105.25,
        ),
        sessions,
        ENTRY_AT + timedelta(minutes=5),
        broker_position_quantity=2.0,
    )
    values = {
        **asdict(entry),
        "runtime_trade_id": 77,
        "runtime_order_ids": ["exit-order-1"],
        "runtime_exit_time": EXIT_AT,
        "runtime_exit_reason": "portfolio_sell",
        "runtime_decision_id": 901,
        "trigger_at": TRIGGER_AT,
        "exit_mechanism": "expired",
        "runtime_reason": "[expired] signal discarded for age",
    }
    values.update(overrides)
    return values


def _filled_order(**overrides):
    values = {
        "id": "exit-order-1",
        "status": "filled",
        "filled_at": EXIT_AT,
        "filled_qty": "2.0",
        "filled_avg_price": "110.0",
        "type": "market",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_worker_riproduce_p0_senza_submit_cancel_o_replace():
    store = MagicMock()
    store.fetch_s4_p0_replay_candidates.return_value = [_candidate()]
    broker = MagicMock()
    broker.get_order_by_id.return_value = _filled_order()

    count = replay_p0_candidates(store, broker)

    assert count == 1
    [event] = store.write_s4_exit_policy_events.call_args.args[0]
    assert event.status == "CLOSED"
    assert event.reason_code == "P0_TARGET_ZERO_EXPIRED"
    assert event.virtual_exit_quantity == 2.0
    assert event.first_executable_at == EXIT_AT
    assert event.first_executable_price == 110.0
    assert event.shadow_order_id is None
    broker.submit_order.assert_not_called()
    broker.cancel_order_by_id.assert_not_called()
    broker.replace_order_by_id.assert_not_called()


def test_worker_persiste_il_lifecycle_runtime_ancora_aperto_senza_leggere_ordini():
    store = MagicMock()
    store.fetch_s4_p0_replay_candidates.return_value = [_candidate(
        runtime_order_ids=[],
        runtime_exit_time=None,
        runtime_exit_reason=None,
        runtime_decision_id=None,
        trigger_at=None,
        exit_mechanism=None,
        runtime_reason=None,
    )]
    broker = MagicMock()

    count = replay_p0_candidates(store, broker)

    assert count == 1
    [event] = store.write_s4_exit_policy_events.call_args.args[0]
    assert event.status == "OPEN"
    assert event.reason_code == "P0_RUNTIME_OPEN"
    assert event.comparable is True
    broker.get_order_by_id.assert_not_called()


def test_stop_broker_e_overlay_dhard_comune_non_stop_stretto():
    store = MagicMock()
    store.fetch_s4_p0_replay_candidates.return_value = [_candidate(
        exit_mechanism=None,
        runtime_exit_reason="stop_loss",
    )]
    broker = MagicMock()
    broker.get_order_by_id.return_value = _filled_order(type="stop")

    replay_p0_candidates(store, broker)

    [event] = store.write_s4_exit_policy_events.call_args.args[0]
    assert event.status == "RISK_EXITED"
    assert event.reason_code == "P0_D_HARD"
    assert event.comparable is True


def test_take_profit_live_e_censurato_secondo_il_contratto_comune():
    store = MagicMock()
    store.fetch_s4_p0_replay_candidates.return_value = [_candidate(
        exit_mechanism=None,
        runtime_exit_reason="take_profit",
    )]
    broker = MagicMock()
    broker.get_order_by_id.return_value = _filled_order(type="limit")

    replay_p0_candidates(store, broker)

    [event] = store.write_s4_exit_policy_events.call_args.args[0]
    assert event.status == "CENSORED"
    assert event.reason_code == "P0_TAKE_PROFIT_DISABLED"
    assert event.comparable is False


def test_scale_out_conserva_tutti_gli_ordini_runtime_nella_provenance():
    store = MagicMock()
    store.fetch_s4_p0_replay_candidates.return_value = [_candidate(
        runtime_order_ids=["exit-order-1", "exit-order-2"],
        exit_mechanism=None,
    )]
    broker = MagicMock()
    broker.get_order_by_id.side_effect = [
        _filled_order(filled_qty="0.5", filled_avg_price="109.0"),
        _filled_order(
            id="exit-order-2",
            filled_at=EXIT_AT + timedelta(minutes=15),
            filled_qty="1.5",
            filled_avg_price="111.0",
        ),
    ]

    replay_p0_candidates(store, broker)

    [event] = store.write_s4_exit_policy_events.call_args.args[0]
    assert event.status == "CENSORED"
    assert event.reason_code == "P0_SCALE_OUT_DISABLED"
    assert event.details["runtime_order_ids"] == ["exit-order-1", "exit-order-2"]


def test_lookup_fill_fallito_resta_residuo_esplicito():
    store = MagicMock()
    store.fetch_s4_p0_replay_candidates.return_value = [_candidate()]
    broker = MagicMock()
    broker.get_order_by_id.side_effect = RuntimeError("order unavailable")

    replay_p0_candidates(store, broker)

    [event] = store.write_s4_exit_policy_events.call_args.args[0]
    assert event.status == "TRIGGERED"
    assert event.reason_code == "P0_EXIT_FILL_MISSING"
    assert event.divergence_reasons == ("EXIT_FILL_MISSING",)


def test_retry_dello_stesso_snapshot_mantiene_un_evento_logico():
    store = MagicMock()
    store.fetch_s4_p0_replay_candidates.return_value = [_candidate()]
    broker = MagicMock()
    broker.get_order_by_id.return_value = _filled_order()

    replay_p0_candidates(store, broker)
    first = store.write_s4_exit_policy_events.call_args.args[0][0]
    replay_p0_candidates(store, broker)
    retry = store.write_s4_exit_policy_events.call_args.args[0][0]

    assert retry.event_id == first.event_id
