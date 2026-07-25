"""Worker tests for terminal broker-order projection into the mobile feed."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import asyncpg
import pytest
from alpaca.trading.client import TradingClient
from starlette.concurrency import run_in_threadpool

from src.mobile_monitoring.builder import MobileSnapshotBuilder
from src.mobile_monitoring.incidents import IncidentStore
from src.notifications.fcm import FcmDeliveryPort, FcmResult
from src.workers.portfolio_scheduler import _enqueue_mobile_broker_error
from src.workers.mobile_alert_task import (
    MobileAlertEvaluator,
    dispatch_due_notifications,
    record_mobile_order_failure,
    record_order_event,
    reconcile_terminal_order_events,
    run_mobile_alert_evaluation,
)

_OBSERVED_AT = datetime(2026, 7, 24, 12, 0, tzinfo=timezone.utc)


def _snapshot(
    *,
    state: str = "operational",
    reason: str | None = None,
    mode: str = "paper",
    pipeline_expected: bool = True,
    broker_status: str = "fresh",
    cycle_status: str = "fresh",
    drawdown: float | None = 0.01,
    drawdown_limit: float | None = 0.10,
    exposure: float | None = 0.20,
    exposure_limit: float | None = 1.0,
    degradations: list | None = None,
) -> SimpleNamespace:
    def component(status: str) -> SimpleNamespace:
        return SimpleNamespace(status=status, age_seconds=60)

    return SimpleNamespace(
        as_of=_OBSERVED_AT,
        operational=SimpleNamespace(
            state=state,
            primary_reason=reason,
            mode=mode,
            pipeline_expected=pipeline_expected,
        ),
        pipeline={
            "broker": component(broker_status),
            "portfolio_cycle": component(cycle_status),
            "signal": component("fresh"),
        },
        portfolio=SimpleNamespace(
            current_drawdown=drawdown,
            drawdown_limit=drawdown_limit,
            gross_exposure=exposure,
            gross_exposure_limit=exposure_limit,
        ),
        degradations=degradations or [],
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("snapshot", "fingerprint", "severity"),
    [
        (
            _snapshot(state="blocked", reason="killswitch_active"),
            "system:killswitch",
            "critical",
        ),
        (
            _snapshot(cycle_status="aging"),
            "pipeline:portfolio_cycle_late",
            "warning",
        ),
        (
            _snapshot(cycle_status="stale"),
            "pipeline:portfolio_cycle_late",
            "critical",
        ),
        (
            _snapshot(drawdown=0.10),
            "risk:drawdown:paper",
            "critical",
        ),
        (
            _snapshot(exposure=1.0),
            "risk:exposure:paper",
            "critical",
        ),
    ],
)
async def test_evaluator_maps_synthetic_alert_scenarios(
    snapshot: SimpleNamespace,
    fingerprint: str,
    severity: str,
) -> None:
    store = MagicMock(spec=IncidentStore)
    store.record_observation = AsyncMock()
    store.list_active_incidents = AsyncMock(return_value={})
    builder = MagicMock(spec=MobileSnapshotBuilder)
    builder.build_snapshot = AsyncMock(return_value=snapshot)

    await MobileAlertEvaluator(store=store, builder=builder).evaluate()

    observations = [call.kwargs for call in store.record_observation.await_args_list]
    matched = [row for row in observations if row["fingerprint"] == fingerprint]
    assert len(matched) == 1
    assert matched[0]["severity"].value == severity


@pytest.mark.asyncio
async def test_off_hours_suppresses_schedule_staleness_but_not_killswitch() -> None:
    store = MagicMock(spec=IncidentStore)
    store.record_observation = AsyncMock()
    store.list_active_incidents = AsyncMock(return_value={})
    builder = MagicMock(spec=MobileSnapshotBuilder)
    builder.build_snapshot = AsyncMock(
        return_value=_snapshot(
            state="blocked",
            reason="killswitch_active",
            pipeline_expected=False,
            cycle_status="stale",
        )
    )

    await MobileAlertEvaluator(store=store, builder=builder).evaluate()

    fingerprints = {
        call.kwargs["fingerprint"]
        for call in store.record_observation.await_args_list
    }
    assert "system:killswitch" in fingerprints
    assert "pipeline:portfolio_cycle_late" not in fingerprints


@pytest.mark.asyncio
async def test_off_hours_does_not_fabricate_pipeline_recovery() -> None:
    store = MagicMock(spec=IncidentStore)
    store.record_observation = AsyncMock()
    store.list_active_incidents = AsyncMock(
        return_value={"pipeline:portfolio_cycle_late": _OBSERVED_AT}
    )
    builder = MagicMock(spec=MobileSnapshotBuilder)
    builder.build_snapshot = AsyncMock(
        return_value=_snapshot(
            pipeline_expected=False,
            cycle_status="stale",
        )
    )

    await MobileAlertEvaluator(store=store, builder=builder).evaluate()

    store.record_observation.assert_not_awaited()


@pytest.mark.asyncio
async def test_off_hours_recovers_after_new_successful_cycle() -> None:
    store = MagicMock(spec=IncidentStore)
    store.record_observation = AsyncMock()
    store.list_active_incidents = AsyncMock(
        return_value={
            "pipeline:portfolio_cycle_late": _OBSERVED_AT.replace(hour=11, minute=50)
        }
    )
    builder = MagicMock(spec=MobileSnapshotBuilder)
    builder.build_snapshot = AsyncMock(
        return_value=_snapshot(
            pipeline_expected=False,
            cycle_status="fresh",
        )
    )

    await MobileAlertEvaluator(store=store, builder=builder).evaluate()

    recovery = store.record_observation.await_args.kwargs
    assert recovery["fingerprint"] == "pipeline:portfolio_cycle_late"
    assert recovery["expected"] is False


@pytest.mark.asyncio
async def test_missing_risk_values_do_not_fabricate_recovery() -> None:
    store = MagicMock(spec=IncidentStore)
    store.record_observation = AsyncMock()
    store.list_active_incidents = AsyncMock(
        return_value={
            "risk:drawdown:paper": _OBSERVED_AT,
            "risk:exposure:paper": _OBSERVED_AT,
        }
    )
    builder = MagicMock(spec=MobileSnapshotBuilder)
    builder.build_snapshot = AsyncMock(
        return_value=_snapshot(
            drawdown=None,
            exposure=None,
        )
    )

    await MobileAlertEvaluator(store=store, builder=builder).evaluate()

    store.record_observation.assert_not_awaited()


@pytest.mark.asyncio
async def test_exposure_recovery_requires_two_clear_observations() -> None:
    store = MagicMock(spec=IncidentStore)
    store.record_observation = AsyncMock()
    store.list_active_incidents = AsyncMock(
        return_value={"risk:exposure:paper": _OBSERVED_AT}
    )
    builder = MagicMock(spec=MobileSnapshotBuilder)
    builder.build_snapshot = AsyncMock(return_value=_snapshot(exposure=0.5))

    await MobileAlertEvaluator(store=store, builder=builder).evaluate()

    recovery = store.record_observation.await_args.kwargs
    assert recovery["fingerprint"] == "risk:exposure:paper"
    assert recovery["expected"] is False
    assert recovery["recovery_observations_required"] == 2


def test_mobile_alert_schedule_runs_every_minute_including_off_hours() -> None:
    from src.workers.celery_app import app

    schedule = app.conf.beat_schedule["mobile-alert-evaluation"]["schedule"]
    assert set(schedule.hour) == set(range(24))
    assert set(schedule.minute) == set(range(60))


@pytest.mark.asyncio
async def test_terminal_order_reconciliation_records_rejected_and_canceled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed_at = datetime(2026, 7, 23, 14, 5, tzinfo=timezone.utc)
    broker = MagicMock(spec=TradingClient)
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
    thread_call = AsyncMock(spec=run_in_threadpool, return_value=orders)
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
    incident_store = MagicMock(spec=IncidentStore)
    incident_store.list_active_fingerprints = AsyncMock(return_value=set())
    monkeypatch.setattr(
        "src.workers.mobile_alert_task.IncidentStore",
        MagicMock(return_value=incident_store),
    )

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


@pytest.mark.asyncio
async def test_terminal_reconciliation_skips_expected_cancellations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed_at = _OBSERVED_AT
    orders = [
        SimpleNamespace(
            id="protective-stop",
            symbol="AAPL",
            status="canceled",
            type="stop",
            replaced_by=None,
            failed_at=None,
            canceled_at=observed_at,
        ),
        SimpleNamespace(
            id="replaced-order",
            symbol="MSFT",
            status="canceled",
            type="limit",
            replaced_by="replacement-id",
            failed_at=None,
            canceled_at=observed_at,
        ),
    ]
    monkeypatch.setattr(
        "src.workers.mobile_alert_task.run_in_threadpool",
        AsyncMock(spec=run_in_threadpool, return_value=orders),
    )
    recorder = AsyncMock(spec=record_order_event)
    monkeypatch.setattr(
        "src.workers.mobile_alert_task.record_order_event",
        recorder,
    )
    incident_store = MagicMock(spec=IncidentStore)
    incident_store.list_active_fingerprints = AsyncMock(return_value=set())
    monkeypatch.setattr(
        "src.workers.mobile_alert_task.IncidentStore",
        MagicMock(return_value=incident_store),
    )

    await reconcile_terminal_order_events(
        MagicMock(spec=asyncpg.Pool),
        MagicMock(spec=TradingClient),
        now=observed_at,
    )

    recorder.assert_not_awaited()


def test_alert_entrypoint_uses_persistent_worker_event_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = MagicMock(
        spec=lambda awaitable: None,
        side_effect=lambda awaitable: awaitable.close(),
    )
    monkeypatch.setattr("src.workers.mobile_alert_task.run_async", run)

    assert run_mobile_alert_evaluation.run() == {"status": "ok", "processed": 1}

    run.assert_called_once()


def test_order_failure_entrypoint_uses_persistent_worker_event_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = MagicMock(
        spec=lambda awaitable: None,
        side_effect=lambda awaitable: awaitable.close(),
    )
    monkeypatch.setattr("src.workers.mobile_alert_task.run_async", run)

    result = record_mobile_order_failure.run(
        failure_id="failure-id",
        symbol="AAPL",
        side="buy",
        error_code="APIError",
    )

    assert result == {"status": "recorded", "failure_id": "failure-id"}
    run.assert_called_once()


def test_order_path_enqueues_redacted_mobile_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    delay = MagicMock(spec=record_mobile_order_failure.delay)
    monkeypatch.setattr(record_mobile_order_failure, "delay", delay)

    _enqueue_mobile_broker_error(
        "AAPL",
        "buy",
        RuntimeError("sensitive broker response"),
    )

    delay.assert_called_once()
    kwargs = delay.call_args.kwargs
    assert kwargs["symbol"] == "AAPL"
    assert kwargs["side"] == "buy"
    assert kwargs["error_code"] == "RuntimeError"
    assert "sensitive" not in str(kwargs)


@pytest.mark.asyncio
async def test_dispatch_uses_registered_fid_and_records_acceptance(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    claim_id = uuid4()
    row = {
        "id": 7,
        "event_id": "event-1",
        "device_id": "device-1",
        "transition": "open",
        "severity": "critical",
        "attempt_count": 0,
        "claim_id": claim_id,
        "firebase_installation_id": "real-firebase-installation-id",
        "fingerprint": "system:killswitch",
        "delivery_created_at": datetime(
            2026, 7, 24, 11, 59, 30, tzinfo=timezone.utc
        ),
    }
    store = MagicMock(spec=IncidentStore)
    store.list_due_deliveries = AsyncMock(side_effect=[[row], []])
    store.record_delivery_attempt = AsyncMock()
    adapter = MagicMock(spec=FcmDeliveryPort)
    adapter.send = AsyncMock(
        return_value=FcmResult(
            accepted=True,
            provider_message_id="provider-message-1",
        )
    )
    monkeypatch.setattr(
        "src.workers.mobile_alert_task.IncidentStore",
        MagicMock(return_value=store),
    )
    monkeypatch.setattr(
        "src.workers.mobile_alert_task.get_fcm_adapter",
        MagicMock(return_value=adapter),
    )

    accepted_at = datetime(2026, 7, 24, 12, 0, tzinfo=timezone.utc)
    caplog.set_level("INFO", logger="src.workers.mobile_alert_task")
    await dispatch_due_notifications(
        MagicMock(spec=asyncpg.Pool),
        now=accepted_at,
    )

    adapter.send.assert_awaited_once()
    assert (
        adapter.send.await_args.kwargs["firebase_installation_id"]
        == "real-firebase-installation-id"
    )
    store.record_delivery_attempt.assert_awaited_once_with(
        7,
        claim_id,
        provider_message_id="provider-message-1",
        accepted_at=accepted_at,
    )
    assert "latency_seconds=30.000 slo_met=True" in caplog.text


@pytest.mark.asyncio
async def test_dispatch_transient_error_schedules_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    claim_id = uuid4()
    row = {
        "id": 8,
        "event_id": "event-2",
        "device_id": "device-2",
        "transition": "open",
        "severity": "warning",
        "attempt_count": 0,
        "claim_id": claim_id,
        "firebase_installation_id": "real-firebase-installation-id",
        "fingerprint": "pipeline:portfolio_cycle_late",
        "delivery_created_at": datetime.now(timezone.utc),
    }
    store = MagicMock(spec=IncidentStore)
    store.list_due_deliveries = AsyncMock(side_effect=[[row], []])
    store.record_delivery_attempt = AsyncMock()
    adapter = MagicMock(spec=FcmDeliveryPort)
    adapter.send = AsyncMock(
        return_value=FcmResult(
            accepted=False,
            error_code="provider_unavailable",
        )
    )
    monkeypatch.setattr(
        "src.workers.mobile_alert_task.IncidentStore",
        MagicMock(return_value=store),
    )
    monkeypatch.setattr(
        "src.workers.mobile_alert_task.get_fcm_adapter",
        MagicMock(return_value=adapter),
    )

    await dispatch_due_notifications(MagicMock(spec=asyncpg.Pool))

    assert store.record_delivery_attempt.await_count == 1
    kwargs = store.record_delivery_attempt.await_args.kwargs
    assert kwargs["error_code"] == "provider_unavailable"
    assert kwargs["next_attempt_at"] is not None
    assert "failed_at" not in kwargs


@pytest.mark.asyncio
async def test_dispatch_terminal_error_disables_device(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    claim_id = uuid4()
    row = {
        "id": 9,
        "event_id": "event-3",
        "device_id": "device-3",
        "transition": "terminal",
        "severity": "critical",
        "attempt_count": 0,
        "claim_id": claim_id,
        "firebase_installation_id": "expired-firebase-installation-id",
        "fingerprint": "order:event-3:rejected",
        "delivery_created_at": datetime.now(timezone.utc),
    }
    store = MagicMock(spec=IncidentStore)
    store.list_due_deliveries = AsyncMock(side_effect=[[row], []])
    store.record_delivery_attempt = AsyncMock(return_value=True)
    store.disable_device_push = AsyncMock()
    adapter = MagicMock(spec=FcmDeliveryPort)
    adapter.send = AsyncMock(
        return_value=FcmResult(
            accepted=False,
            error_code="unregistered",
            terminal=True,
        )
    )
    monkeypatch.setattr(
        "src.workers.mobile_alert_task.IncidentStore",
        MagicMock(return_value=store),
    )
    monkeypatch.setattr(
        "src.workers.mobile_alert_task.get_fcm_adapter",
        MagicMock(return_value=adapter),
    )

    await dispatch_due_notifications(MagicMock(spec=asyncpg.Pool))

    store.disable_device_push.assert_awaited_once_with(
        "device-3",
        "expired-firebase-installation-id",
    )
    assert store.record_delivery_attempt.await_args.kwargs["failed_at"] is not None
