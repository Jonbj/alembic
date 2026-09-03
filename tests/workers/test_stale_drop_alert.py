"""#432 — aggregato persistente e alert EOD sugli scarti stale."""

from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.notifications.base import AlertLevel
from src.workers.stale_drop_alert import (
    STALE_DROP_ALERT_THRESHOLD,
    StaleDropMeasurement,
    build_stale_drop_measurement,
    collect_stale_drop_measurements,
    format_stale_drop_alert,
    persist_stale_drop_measurements,
    run_stale_drop_alert,
)


@pytest.mark.parametrize(
    ("day", "stale_drops", "queued", "expected_share", "expected_alert"),
    [
        (date(2026, 8, 27), 39, 300, 0.13, False),
        (date(2026, 8, 28), 168, 336, 0.50, True),
        # La issue dice "exceeds": il confine esatto non deve allertare.
        (date(2026, 8, 26), 72, 288, 0.25, False),
    ],
)
def test_soglia_riproduce_le_sedute_di_riferimento(
    day: date,
    stale_drops: int,
    queued: int,
    expected_share: float,
    expected_alert: bool,
) -> None:
    measurement = build_stale_drop_measurement(
        day=day,
        source="alpaca_benzinga",
        queued=queued,
        stale_drops=stale_drops,
        already_stale_at_fetch=stale_drops // 2,
        went_stale_in_queue=stale_drops - stale_drops // 2,
    )

    assert measurement.stale_drop_share == pytest.approx(expected_share)
    assert measurement.alert_required is expected_alert
    assert measurement.alert_threshold == STALE_DROP_ALERT_THRESHOLD == 0.25


def test_alert_separa_le_due_cause_con_i_conteggi() -> None:
    measurement = build_stale_drop_measurement(
        day=date(2026, 8, 28),
        source="alpaca_benzinga",
        queued=336,
        stale_drops=168,
        already_stale_at_fetch=123,
        went_stale_in_queue=45,
        avg_fetch_latency_hours=4.28,
        avg_queue_wait_hours=0.36,
    )

    message = format_stale_drop_alert([measurement])

    assert "alpaca_benzinga" in message
    assert "168/336 (50.0%)" in message
    assert "Already stale at fetch: 123" in message
    assert "Went stale in queue: 45" in message
    assert "Fetch latency avg: 4.28h" in message
    assert "Queue wait avg: 0.36h" in message


@pytest.mark.asyncio
async def test_collettore_classifica_con_la_finestra_senza_toccare_il_drop() -> None:
    connection = AsyncMock()
    connection.fetch.return_value = [
        {
            "day": date(2026, 8, 28),
            "source": "alpaca_benzinga",
            "queued": 336,
            "stale_drops": 168,
            "already_stale_at_fetch": 123,
            "went_stale_in_queue": 45,
            "unclassified_stale": 0,
            "avg_fetch_latency_hours": 4.28,
            "avg_queue_wait_hours": 0.36,
        }
    ]

    measurements = await collect_stale_drop_measurements(
        connection,
        start_day=date(2026, 8, 24),
        end_day=date(2026, 8, 28),
        max_news_age_hours=2.0,
    )

    assert len(measurements) == 1
    assert measurements[0].already_stale_at_fetch == 123
    sql, *params = connection.fetch.await_args.args
    assert "news_queue_drops" in sql
    assert "ingestion_stats_daily" in sql
    assert "discarded_reason = 'stale'" in sql
    assert "raw_ingested_at - published_at" in sql
    assert "dropped_at - raw_ingested_at" in sql
    assert params == [date(2026, 8, 24), date(2026, 8, 28), 2.0]


@pytest.mark.asyncio
async def test_persistenza_e_idempotente_per_giorno_e_fonte() -> None:
    connection = AsyncMock()
    measurement = StaleDropMeasurement(
        day=date(2026, 8, 28),
        source="alpaca_benzinga",
        queued=336,
        stale_drops=168,
        already_stale_at_fetch=123,
        went_stale_in_queue=45,
        unclassified_stale=0,
        stale_drop_share=0.5,
        avg_fetch_latency_hours=4.28,
        avg_queue_wait_hours=0.36,
        max_news_age_hours=2.0,
        alert_threshold=0.25,
        alert_required=True,
    )

    await persist_stale_drop_measurements(connection, [measurement])

    connection.executemany.assert_awaited_once()
    sql, rows = connection.executemany.await_args.args
    assert "INSERT INTO stale_drop_metrics_daily" in sql
    assert "ON CONFLICT (day, source) DO UPDATE" in sql
    assert rows[0][0:4] == (
        date(2026, 8, 28),
        "alpaca_benzinga",
        336,
        168,
    )


def test_task_eod_persiste_tutto_e_allerta_solo_il_breach(monkeypatch) -> None:
    from src.workers import stale_drop_alert as worker

    pool = MagicMock()
    connection = AsyncMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=connection)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
    measurements = [
        build_stale_drop_measurement(
            day=date(2026, 8, 27),
            source="alpaca_benzinga",
            queued=300,
            stale_drops=39,
            already_stale_at_fetch=2,
            went_stale_in_queue=37,
        ),
        build_stale_drop_measurement(
            day=date(2026, 8, 28),
            source="alpaca_benzinga",
            queued=336,
            stale_drops=168,
            already_stale_at_fetch=123,
            went_stale_in_queue=45,
        ),
    ]
    monkeypatch.setattr(worker, "init_asyncpg_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(
        worker, "collect_stale_drop_measurements", AsyncMock(return_value=measurements)
    )
    persist = AsyncMock()
    monkeypatch.setattr(worker, "persist_stale_drop_measurements", persist)
    notifier = MagicMock()
    notifier.send_alert = AsyncMock(return_value=True)
    monkeypatch.setattr(worker, "TelegramNotifier", MagicMock(return_value=notifier))

    result = worker.run_stale_drop_alert.run("2026-08-27", "2026-08-28")

    persist.assert_awaited_once_with(connection, measurements)
    notifier.send_alert.assert_awaited_once()
    message, = notifier.send_alert.await_args.args
    assert "2026-08-28" in message
    assert "2026-08-27" not in message
    assert notifier.send_alert.await_args.kwargs["level"] == AlertLevel.WARNING
    assert result == {"status": "ok", "measured": 2, "alerted": 1}


def test_task_e_cablato_dopo_il_close_senza_importare_il_money_path() -> None:
    from src.workers.celery_app import app

    entry = app.conf.beat_schedule["stale-drop-alert"]
    assert entry["task"] == run_stale_drop_alert.name
    assert set(entry["schedule"].hour) == {22}
    assert set(entry["schedule"].minute) == {55}
    assert set(entry["schedule"].day_of_week) == {1, 2, 3, 4, 5}
