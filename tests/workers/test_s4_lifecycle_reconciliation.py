"""#295: il reconciler intraday estende gli intenti S4 fino al fill."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, time, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

from src.strategies.s4.lifecycle import SubmittedIntent
from src.workers.performance import _reconcile_s4_lifecycles


UTC = timezone.utc
NOW = datetime(2026, 8, 25, 15, 8, tzinfo=UTC)


def _intent() -> SubmittedIntent:
    return SubmittedIntent(
        intent_id="34d6c4c0-bcb2-55ef-a0f4-e3db1a4a13b0",
        symbol="AMD",
        order_id="alpaca-order-1",
        submitted_at=datetime(2026, 8, 25, 15, 7, tzinfo=UTC),
        requested_quantity=2.0,
        requested_notional=210.0,
        first_executable_price=105.0,
        first_executable_price_source="portfolio_market_snapshot.latest_price",
        policy_version="s4-exit-trial:1.0.0",
        sleeve_contributions={"S4": 0.01},
    )


def _calendar(day: int):
    return SimpleNamespace(
        date=date(2026, 8, day),
        open=datetime.combine(date(2026, 8, day), time(13, 30), tzinfo=UTC),
        close=datetime.combine(date(2026, 8, day), time(20, 0), tzinfo=UTC),
    )


def test_reconciler_scrive_fill_d0_due_session_e_quantita_broker():
    store = MagicMock()
    store.fetch_s4_submitted_intents.return_value = [_intent()]
    broker = MagicMock()
    broker.get_order_by_id.return_value = SimpleNamespace(
        id="alpaca-order-1",
        status="filled",
        filled_at=datetime(2026, 8, 25, 15, 7, 4, tzinfo=UTC),
        filled_qty="2.0",
        filled_avg_price="105.25",
    )
    broker.get_all_positions.return_value = [SimpleNamespace(symbol="AMD", qty="2.0")]
    broker.get_calendar.return_value = [_calendar(25), _calendar(26), _calendar(27)]

    count = _reconcile_s4_lifecycles(store, broker, observed_at=NOW)

    assert count == 1
    [event] = store.write_s4_lifecycle_events.call_args.args[0]
    assert event.intent_id == _intent().intent_id
    assert event.status == "FILLED"
    assert event.d0 == date(2026, 8, 25)
    assert event.due_session == date(2026, 8, 27)
    assert event.s4_virtual_quantity == 2.0
    assert event.broker_quantity == 2.0
    assert event.reconstructible is True


def test_lookup_mancante_diventa_missing_fill_non_un_errore_silenzioso():
    store = MagicMock()
    store.fetch_s4_submitted_intents.return_value = [_intent()]
    broker = MagicMock()
    broker.get_order_by_id.side_effect = RuntimeError("404 order not found")
    broker.get_all_positions.return_value = []
    broker.get_calendar.return_value = [_calendar(25), _calendar(26), _calendar(27)]

    count = _reconcile_s4_lifecycles(store, broker, observed_at=NOW)

    assert count == 1
    [event] = store.write_s4_lifecycle_events.call_args.args[0]
    assert event.status == "MISSING_FILL"
    assert event.reason_code == "BROKER_ORDER_LOOKUP_FAILED"
    assert event.reconstructible is False


def test_stesso_snapshot_dopo_restart_mantiene_un_event_id():
    store = MagicMock()
    store.fetch_s4_submitted_intents.return_value = [_intent()]
    broker = MagicMock()
    broker.get_order_by_id.return_value = SimpleNamespace(
        id="alpaca-order-1",
        status="filled",
        filled_at=datetime(2026, 8, 25, 15, 7, 4, tzinfo=UTC),
        filled_qty="2.0",
        filled_avg_price="105.25",
    )
    broker.get_all_positions.return_value = [SimpleNamespace(symbol="AMD", qty="2.0")]
    broker.get_calendar.return_value = [_calendar(25), _calendar(26), _calendar(27)]

    _reconcile_s4_lifecycles(store, broker, observed_at=NOW)
    first = store.write_s4_lifecycle_events.call_args.args[0][0]
    _reconcile_s4_lifecycles(store, broker, observed_at=NOW)
    retry = store.write_s4_lifecycle_events.call_args.args[0][0]

    assert retry.event_id == first.event_id
    assert retry.fill_id == first.fill_id


def test_reject_pre_ack_e_terminal_senza_lookup_di_un_order_inesistente():
    store = MagicMock()
    store.fetch_s4_submitted_intents.return_value = [replace(
        _intent(),
        order_id=None,
        submission_reason_code="BROKER_REJECT",
        submission_error="APIError",
    )]
    broker = MagicMock()
    broker.get_all_positions.return_value = []
    broker.get_calendar.return_value = [_calendar(25), _calendar(26), _calendar(27)]

    count = _reconcile_s4_lifecycles(store, broker, observed_at=NOW)

    assert count == 1
    broker.get_order_by_id.assert_not_called()
    [event] = store.write_s4_lifecycle_events.call_args.args[0]
    assert event.order_id is None
    assert event.status == "REJECTED"
    assert event.reason_code == "BROKER_REJECTED"
    assert event.reconstructible is True
