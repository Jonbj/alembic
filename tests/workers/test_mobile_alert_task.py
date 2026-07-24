"""Worker tests for terminal broker-order projection into the mobile feed."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import asyncpg
import pytest

from src.workers.mobile_alert_task import (
    record_order_event,
    reconcile_terminal_order_events,
    run_mobile_alert_evaluation,
)


@pytest.mark.asyncio
async def test_terminal_order_reconciliation_records_rejected_and_canceled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed_at = datetime(2026, 7, 23, 14, 5, tzinfo=timezone.utc)
    broker = MagicMock()
    orders = [
        SimpleNamespace(
            id="rejected-1",
            symbol="AAPL",
            status="rejected",
            failed_at=observed_at,
            canceled_at=None,
        ),
        SimpleNamespace(
            id="canceled-1",
            symbol="MSFT",
            status="canceled",
            failed_at=None,
            canceled_at=observed_at,
        ),
        SimpleNamespace(
            id="filled-1",
            symbol="NVDA",
            status="filled",
            failed_at=None,
            canceled_at=None,
        ),
    ]
    thread_call = AsyncMock(return_value=orders)
    monkeypatch.setattr(
        "src.workers.mobile_alert_task.run_in_threadpool",
        thread_call,
    )
    recorder = AsyncMock(spec=record_order_event)
    monkeypatch.setattr(
        "src.workers.mobile_alert_task.record_order_event",
        recorder,
    )
    pool = MagicMock(spec=asyncpg.Pool)

    await reconcile_terminal_order_events(pool, broker, now=observed_at)

    thread_call.assert_awaited_once()
    assert recorder.await_count == 2
    assert {call.kwargs["kind"] for call in recorder.await_args_list} == {
        "rejected",
        "canceled",
    }
    assert {call.kwargs["order_id"] for call in recorder.await_args_list} == {
        "rejected-1",
        "canceled-1",
    }


def test_alert_entrypoint_uses_persistent_worker_event_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = MagicMock(
        spec=lambda awaitable: None,
        side_effect=lambda awaitable: awaitable.close(),
    )
    monkeypatch.setattr("src.workers.mobile_alert_task.run_async", run)

    assert run_mobile_alert_evaluation.run() is None

    run.assert_called_once()
