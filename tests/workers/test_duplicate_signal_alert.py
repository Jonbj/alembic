"""#551/F-072 — monitor giornaliero sui news_log_id duplicati in sentiment_signals."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.notifications.base import AlertLevel
from src.workers.duplicate_signal_alert import (
    DUPLICATE_SIGNALS_ALERT_THRESHOLD,
    F072_KNOWN_DUPLICATE_NEWS_LOG_IDS,
    build_duplicate_signals_measurement,
    collect_duplicate_news_log_rows,
    format_duplicate_signals_alert,
    run_duplicate_signals_alert,
)


def make_row(
    news_log_id: int,
    signal_count: int = 2,
    symbols: str = "AAPL",
    first_generated_at: datetime = datetime(2026, 9, 8, 15, 8, tzinfo=timezone.utc),
    last_generated_at: datetime = datetime(2026, 9, 8, 15, 35, tzinfo=timezone.utc),
) -> dict:
    return {
        "news_log_id": news_log_id,
        "signal_count": signal_count,
        "symbols": symbols,
        "first_generated_at": first_generated_at,
        "last_generated_at": last_generated_at,
    }


def test_zero_duplicati_non_allerta() -> None:
    measurement = build_duplicate_signals_measurement([])

    assert measurement.duplicate_news_log_count == 0
    assert measurement.alert_required is False
    assert format_duplicate_signals_alert(measurement) == ""


def test_soglia_zero_qualsiasi_duplicato_allerta() -> None:
    measurement = build_duplicate_signals_measurement(
        [make_row(9902), make_row(55555, symbols="MSFT")]
    )

    assert DUPLICATE_SIGNALS_ALERT_THRESHOLD == 0
    assert measurement.duplicate_news_log_count == 2
    assert measurement.alert_required is True


def test_i_dodici_f072_sono_il_baseline_noto() -> None:
    # La tabella della issue: 9902..9913, dodici news_log_id.
    assert F072_KNOWN_DUPLICATE_NEWS_LOG_IDS == frozenset(range(9902, 9914))


def test_messaggio_separa_i_duplicati_nuovi_dai_f072_noti() -> None:
    rows = [make_row(9902, symbols="GOOGL"), make_row(55555, symbols="MSFT")]
    measurement = build_duplicate_signals_measurement(rows)

    message = format_duplicate_signals_alert(measurement, rows)

    assert measurement.new_news_log_ids == frozenset({55555})
    assert measurement.known_news_log_ids == frozenset({9902})
    assert "55555" in message
    assert "MSFT" in message
    # I noti restano visibili ma marcati: la loro sorte e' una decisione
    # dell'operatore, non un difetto nuovo.
    assert "#551" in message
    assert "9902" in message


def test_messaggio_riporta_conteggio_e_finestra() -> None:
    rows = [make_row(9902)]
    measurement = build_duplicate_signals_measurement(rows)

    message = format_duplicate_signals_alert(measurement, rows)

    assert "news_log 9902: 2 signals" in message
    assert "2026-09-08 15:08Z → 2026-09-08 15:35Z" in message


@pytest.mark.asyncio
async def test_collettore_usa_la_query_del_dod() -> None:
    connection = AsyncMock()
    connection.fetch.return_value = [make_row(9902)]

    rows = await collect_duplicate_news_log_rows(connection)

    assert rows == [make_row(9902)]
    sql, = connection.fetch.await_args.args
    # La misura del DoD: conteggio dei news_log_id con piu' di una riga.
    assert "FROM sentiment_signals" in sql
    assert "news_log_id IS NOT NULL" in sql
    assert "GROUP BY" in sql
    assert "HAVING COUNT(*) > 1" in sql


def test_task_allerta_solo_con_duplicati(monkeypatch) -> None:
    from src.workers import duplicate_signal_alert as worker

    monkeypatch.setattr(
        worker,
        "collect_duplicate_news_log_rows",
        AsyncMock(return_value=[make_row(55555)]),
    )
    notifier = MagicMock()
    notifier.send_alert = AsyncMock(return_value=True)
    monkeypatch.setattr(
        worker, "TelegramNotifier", MagicMock(return_value=notifier)
    )

    result = worker.run_duplicate_signals_alert.run()

    notifier.send_alert.assert_awaited_once()
    assert notifier.send_alert.await_args.kwargs["level"] == AlertLevel.WARNING
    assert result == {"status": "ok", "duplicated_news_log": 1, "alerted": 1}


def test_task_silenzioso_senza_duplicati(monkeypatch) -> None:
    from src.workers import duplicate_signal_alert as worker

    monkeypatch.setattr(
        worker, "collect_duplicate_news_log_rows", AsyncMock(return_value=[])
    )
    notifier = MagicMock()
    notifier.send_alert = AsyncMock(return_value=True)
    monkeypatch.setattr(
        worker, "TelegramNotifier", MagicMock(return_value=notifier)
    )

    result = worker.run_duplicate_signals_alert.run()

    notifier.send_alert.assert_not_awaited()
    assert result == {"status": "ok", "duplicated_news_log": 0, "alerted": 0}


def test_task_e_cablato_dopo_la_scala_eod() -> None:
    from src.workers.celery_app import app

    entry = app.conf.beat_schedule["duplicate-signals-alert"]
    assert entry["task"] == run_duplicate_signals_alert.name
    assert set(entry["schedule"].hour) == {23}
    assert set(entry["schedule"].minute) == {5}
