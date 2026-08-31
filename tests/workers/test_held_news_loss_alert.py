"""#324 — alert sulle posizioni in perdita che il canale news non vede."""

from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.mobile_monitoring.incidents import IncidentStore
from src.workers.held_news_loss_alert import (
    build_held_news_loss_coverage,
    evaluate_held_news_loss_alerts,
    run_held_news_loss_alert,
)


SEDUTE = [
    date(2026, 8, 17),
    date(2026, 8, 18),
    date(2026, 8, 19),
]


def _position(
    symbol: str,
    *,
    entry: str = "100",
    current: str = "90",
) -> SimpleNamespace:
    return SimpleNamespace(
        symbol=symbol,
        qty="10",
        avg_entry_price=entry,
        current_price=current,
    )


def test_live_coverage_riusa_la_definizione_del_dossier() -> None:
    coverage = build_held_news_loss_coverage(
        [_position("WDC"), _position("GE", current="104")],
        entry_times={
            "WDC": datetime(2026, 7, 22, 14, tzinfo=timezone.utc),
            "GE": datetime(2026, 7, 22, 14, tzinfo=timezone.utc),
        },
        sessions=SEDUTE,
        news_rows={"WDC": {"2026-08-17": 1}},
        signals_today={},
    )

    by_ticker = {row["ticker"]: row for row in coverage["posizioni"]}
    assert by_ticker["WDC"]["sedute_consecutive_senza_righe"] == 2
    assert by_ticker["WDC"]["ritorno_da_ingresso"] == pytest.approx(-0.10)
    assert by_ticker["WDC"]["cieco_lato_uscita"] is True
    assert by_ticker["GE"]["cieco_lato_uscita"] is False


def test_entry_time_sconosciuto_resta_unknown_e_non_inventa_uno_streak() -> None:
    coverage = build_held_news_loss_coverage(
        [_position("UNTRACKED")],
        entry_times={},
        sessions=SEDUTE,
        news_rows={},
        signals_today={},
    )

    (row,) = coverage["posizioni"]
    assert row["cieco_lato_uscita"] is None
    assert "entry_time_missing" in row["missingness"]


@pytest.mark.asyncio
async def test_alert_apre_un_incidente_mobile_deduplicabile_per_ticker() -> None:
    store = MagicMock(spec=IncidentStore)
    store.list_active_incidents = AsyncMock(return_value={})
    store.record_observation = AsyncMock()
    coverage = {
        "posizioni": [
            {
                "ticker": "WDC",
                "cieco_lato_uscita": True,
                "ritorno_da_ingresso": -0.10,
                "sedute_consecutive_senza_righe": 2,
                "righe_news_log_giorno": 0,
                "segnali_sentiment_giorno": 0,
                "notional_usd": 900.0,
            },
            {"ticker": "GE", "cieco_lato_uscita": False},
        ],
        "soglia_perdita_da_ingresso": -0.03,
        "sedute_minime": 2,
    }

    alerted = await evaluate_held_news_loss_alerts(store, coverage)

    assert alerted == ["WDC"]
    store.record_observation.assert_awaited_once()
    observation = store.record_observation.await_args.kwargs
    assert observation["fingerprint"] == "coverage:held_no_news_loss:WDC"
    assert observation["kind"].value == "position"
    assert observation["severity"].value == "warning"
    assert observation["expected"] is True
    assert observation["entity_id"] == "WDC"


@pytest.mark.asyncio
async def test_alert_recupera_solo_con_dato_nuovo_determinato() -> None:
    store = MagicMock(spec=IncidentStore)
    store.list_active_incidents = AsyncMock(
        return_value={
            "coverage:held_no_news_loss:GE": datetime.now(timezone.utc),
            "coverage:held_no_news_loss:UNKNOWN": datetime.now(timezone.utc),
            "risk:drawdown:paper": datetime.now(timezone.utc),
        }
    )
    store.record_observation = AsyncMock()
    coverage = {
        "posizioni": [
            {"ticker": "GE", "cieco_lato_uscita": False},
            {"ticker": "UNKNOWN", "cieco_lato_uscita": None},
        ],
        "soglia_perdita_da_ingresso": -0.03,
        "sedute_minime": 2,
    }

    await evaluate_held_news_loss_alerts(store, coverage)

    store.record_observation.assert_awaited_once()
    recovery = store.record_observation.await_args.kwargs
    assert recovery["fingerprint"] == "coverage:held_no_news_loss:GE"
    assert recovery["expected"] is False


def test_alert_ha_un_run_eod_separato_dal_money_path() -> None:
    from src.workers.celery_app import app

    entry = app.conf.beat_schedule["held-news-loss-alert"]
    assert entry["task"] == run_held_news_loss_alert.name
    # 22:50 UTC resta dopo il close sia in EDT sia in EST: l'alert non eredita
    # il difetto DST del beat intraday tracciato in #404.
    assert set(entry["schedule"].hour) == {22}
    assert set(entry["schedule"].minute) == {50}
    assert set(entry["schedule"].day_of_week) == {1, 2, 3, 4, 5}
