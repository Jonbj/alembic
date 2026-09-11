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
            "went_stale_off_session": 0,
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
        went_stale_off_session=0,
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


# --- #432 Opzione B: coorte di accodamento + quarto gruppo causale -----------
#
# Deroga registrata in docs/evidence/OBSERVATION_CHARTER.md il 2026-09-10.
# La serie cambia chiave di aggregazione e partizione causale; questi test
# fissano il contratto nuovo, incluso il criterio di accettazione della deroga.


def test_la_quota_off_session_e_pubblicata_ma_non_concorre_alla_soglia() -> None:
    """08-09/09 su alpaca_benzinga: la coorte notturna non e' un guasto."""
    measurement = build_stale_drop_measurement(
        day=date(2026, 9, 8),
        source="alpaca_benzinga",
        queued=541,
        stale_drops=157,
        already_stale_at_fetch=2,
        went_stale_in_queue=3,
        went_stale_off_session=152,
    )

    # La quota complessiva resta pubblicata: 157/541 = 29,0%, sopra il 25%.
    assert measurement.stale_drop_share == pytest.approx(157 / 541)
    assert measurement.stale_drop_share > STALE_DROP_ALERT_THRESHOLD
    # Ma la soglia si applica alla sola quota accodata entro seduta.
    assert measurement.in_session_stale_drops == 5
    assert measurement.in_session_stale_drop_share == pytest.approx(5 / 541)
    assert measurement.alert_required is False


def test_un_outage_entro_seduta_resta_in_breach() -> None:
    """Criterio di accettazione della deroga (outage Ollama 2026-09-09 15-16Z).

    Se dopo la correzione questa finestra non allerta piu', la correzione e'
    sbagliata e va revertata.
    """
    measurement = build_stale_drop_measurement(
        day=date(2026, 9, 9),
        source="alpaca_benzinga",
        queued=200,
        stale_drops=90,
        already_stale_at_fetch=10,
        went_stale_in_queue=80,
        went_stale_off_session=0,
    )

    assert measurement.in_session_stale_drop_share == pytest.approx(0.45)
    assert measurement.alert_required is True


def test_uno_scarto_di_provenienza_ignota_conta_verso_la_soglia() -> None:
    """Senza raw_ingested_at la seduta non e' ricostruibile: fail-closed.

    Un dato incompleto non scusa un guasto (stesso principio di #324): resta
    nel gruppo che concorre alla soglia.
    """
    measurement = build_stale_drop_measurement(
        day=date(2026, 9, 9),
        source="alpaca_benzinga",
        queued=100,
        stale_drops=40,
        already_stale_at_fetch=0,
        went_stale_in_queue=0,
        went_stale_off_session=10,
        unclassified_stale=30,
    )

    assert measurement.in_session_stale_drops == 30
    assert measurement.alert_required is True


def test_la_somma_delle_quattro_cause_deve_fare_gli_scarti() -> None:
    with pytest.raises(ValueError, match="add up"):
        build_stale_drop_measurement(
            day=date(2026, 9, 8),
            source="alpaca_benzinga",
            queued=541,
            stale_drops=157,
            already_stale_at_fetch=2,
            went_stale_in_queue=3,
            went_stale_off_session=151,
        )


def test_un_conteggio_off_session_negativo_e_rifiutato() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        build_stale_drop_measurement(
            day=date(2026, 9, 8),
            source="alpaca_benzinga",
            queued=541,
            stale_drops=0,
            already_stale_at_fetch=0,
            went_stale_in_queue=0,
            went_stale_off_session=-1,
        )


def test_alert_pubblica_il_gruppo_off_session_e_la_quota_su_cui_decide() -> None:
    measurement = build_stale_drop_measurement(
        day=date(2026, 9, 9),
        source="alpaca_benzinga",
        queued=200,
        stale_drops=110,
        already_stale_at_fetch=10,
        went_stale_in_queue=80,
        went_stale_off_session=20,
        avg_fetch_latency_hours=0.02,
        avg_queue_wait_hours=6.10,
    )

    message = format_stale_drop_alert([measurement])

    # La decisione e' sulla quota in-seduta, e il messaggio deve dirlo:
    # 90/200 = 45,0%, non 110/200 = 55,0%.
    assert "In-session stale drops: 90/200 (45.0%)" in message
    assert "Enqueued off-session: 20" in message
    assert "Total stale drops: 110/200 (55.0%)" in message
    assert "in-session" in message.lower()


@pytest.mark.asyncio
async def test_il_collettore_aggrega_sulla_coorte_di_accodamento() -> None:
    """Numeratore e denominatore devono parlare della stessa coorte.

    `ingestion_stats_daily.queued` e' incrementato all'accodamento: raggruppare
    il numeratore su `dropped_at` metteva la coorte notturna al numeratore di
    D+1 e al denominatore di D.
    """
    connection = AsyncMock()
    connection.fetch.return_value = [
        {
            "day": date(2026, 9, 8),
            "source": "alpaca_benzinga",
            "queued": 541,
            "stale_drops": 157,
            "already_stale_at_fetch": 2,
            "went_stale_in_queue": 3,
            "went_stale_off_session": 152,
            "unclassified_stale": 0,
            "avg_fetch_latency_hours": 0.01,
            "avg_queue_wait_hours": 11.2,
        }
    ]

    measurements = await collect_stale_drop_measurements(
        connection,
        start_day=date(2026, 9, 8),
        end_day=date(2026, 9, 9),
        max_news_age_hours=2.0,
    )

    assert measurements[0].went_stale_off_session == 152
    assert measurements[0].alert_required is False
    sql, *params = connection.fetch.await_args.args
    # La coorte, non il giorno di scarto, e' la chiave di aggregazione.
    assert "(COALESCE(raw_ingested_at, dropped_at) AT TIME ZONE 'UTC')::date AS day" in sql
    assert "(dropped_at AT TIME ZONE 'UTC')::date AS day" not in sql
    # Il flag e' letto dalla colonna persistita, non ri-derivato da un orario UTC.
    assert "enqueued_off_session" in sql
    # Regola #169/#467: la seduta e' letta dalla colonna persistita, non
    # ricostruita qui da un fuso o da una crontab ricopiata.
    assert "America/New_York" not in sql
    assert "EXTRACT(HOUR" not in sql
    assert params == [date(2026, 9, 8), date(2026, 9, 9), 2.0]


@pytest.mark.asyncio
async def test_un_drop_tardivo_riporta_in_gioco_la_coorte_che_lo_ha_accodato() -> None:
    """La finestra su `dropped_at` serve, la chiave di aggregazione no.

    Il beat gira alle 22:55Z su un giorno solo. La coorte accodata dal WebSocket
    dopo la chiusura dell'08 e' ancora in coda a quell'ora e viene scartata alla
    campana del 09: se anche la finestra fosse sulla coorte, quella coorte non
    sarebbe vista da nessuno dei due giri — ed e' esattamente il fenomeno che la
    misura esiste per descrivere.
    """
    connection = AsyncMock()
    connection.fetch.return_value = []

    await collect_stale_drop_measurements(
        connection,
        start_day=date(2026, 9, 8),
        end_day=date(2026, 9, 9),
        max_news_age_hours=2.0,
    )

    sql, *_ = connection.fetch.await_args.args
    selezione_coorti = " ".join(
        sql.split("), coorti AS (")[1].split("), stale AS (")[0].split()
    )
    assert "dropped_at >= ($1::date::timestamp AT TIME ZONE 'UTC')" in selezione_coorti
    assert "day BETWEEN $1 AND $2" in selezione_coorti


@pytest.mark.asyncio
async def test_una_coorte_toccata_e_ricontata_per_intero_non_a_fette() -> None:
    """Altrimenti l'upsert del giorno dopo riscriverebbe parziale una coorte chiusa.

    `persist_stale_drop_measurements` fa ON CONFLICT DO UPDATE con EXCLUDED:
    sovrascrive, non somma. Se il conteggio fosse ristretto alla finestra di
    `dropped_at`, il giro del 09 rimpiazzerebbe i 157 scarti dell'08 con la sola
    fetta scartata il 09.
    """
    connection = AsyncMock()
    connection.fetch.return_value = []

    await collect_stale_drop_measurements(
        connection,
        start_day=date(2026, 9, 8),
        end_day=date(2026, 9, 9),
        max_news_age_hours=2.0,
    )

    sql, *_ = connection.fetch.await_args.args
    conteggio = " ".join(sql.split("), stale AS (")[1].split("GROUP BY")[0].split())
    assert "FROM drops JOIN coorti USING (day, source)" in conteggio
    assert "dropped_at >=" not in conteggio
    assert "dropped_at <" not in conteggio


@pytest.mark.asyncio
async def test_la_persistenza_scrive_anche_il_quarto_gruppo() -> None:
    connection = AsyncMock()
    measurement = build_stale_drop_measurement(
        day=date(2026, 9, 8),
        source="alpaca_benzinga",
        queued=541,
        stale_drops=157,
        already_stale_at_fetch=2,
        went_stale_in_queue=3,
        went_stale_off_session=152,
    )

    await persist_stale_drop_measurements(connection, [measurement])

    sql, rows = connection.executemany.await_args.args
    assert "went_stale_off_session" in sql
    assert "went_stale_off_session = EXCLUDED.went_stale_off_session" in sql
    assert 152 in rows[0]
