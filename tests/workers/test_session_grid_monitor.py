"""#428 — misura EOD della copertura del beat sulla seduta reale."""

from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.mobile_monitoring.incidents import IncidentStore
from src.workers.session_grid_monitor import (
    GAP_ALERT_THRESHOLD_MINUTES,
    SessionGridMeasurement,
    collect_session_grid_measurement,
    evaluate_session_grid_alert,
    measure_session_grid,
    persist_session_grid_measurement,
)


SESSION_DATE = date(2026, 8, 27)
SESSION_OPEN = datetime(2026, 8, 27, 13, 30, tzinfo=timezone.utc)
SESSION_CLOSE = datetime(2026, 8, 27, 20, 0, tzinfo=timezone.utc)


def test_misura_riproduce_il_gap_edt_senza_cambiare_il_beat() -> None:
    measurement = measure_session_grid(
        session_date=SESSION_DATE,
        session_open=SESSION_OPEN,
        session_close=SESSION_CLOSE,
        cycle_timestamps=[
            datetime(2026, 8, 27, 14, 7, tzinfo=timezone.utc),
            datetime(2026, 8, 27, 19, 52, tzinfo=timezone.utc),
        ],
    )

    assert measurement.open_gap_minutes == pytest.approx(37.0)
    assert measurement.close_gap_minutes == pytest.approx(8.0)
    assert measurement.first_effective_cycle == datetime(
        2026, 8, 27, 14, 7, tzinfo=timezone.utc
    )
    assert measurement.last_effective_cycle == datetime(
        2026, 8, 27, 19, 52, tzinfo=timezone.utc
    )
    assert measurement.alert_required is True
    assert measurement.threshold_minutes == GAP_ALERT_THRESHOLD_MINUTES == 20


def test_nessun_ciclo_effettivo_resta_misurato_e_allerta() -> None:
    measurement = measure_session_grid(
        session_date=SESSION_DATE,
        session_open=SESSION_OPEN,
        session_close=SESSION_CLOSE,
        cycle_timestamps=[],
    )

    assert measurement.first_effective_cycle is None
    assert measurement.last_effective_cycle is None
    assert measurement.open_gap_minutes is None
    assert measurement.close_gap_minutes is None
    assert measurement.alert_required is True


@pytest.mark.asyncio
async def test_alert_mobile_scata_quando_il_primo_ciclo_e_37_minuti_in_ritardo() -> None:
    store = MagicMock(spec=IncidentStore)
    store.list_active_incidents = AsyncMock(return_value={})
    store.record_observation = AsyncMock()
    measurement = measure_session_grid(
        session_date=SESSION_DATE,
        session_open=SESSION_OPEN,
        session_close=SESSION_CLOSE,
        cycle_timestamps=[
            datetime(2026, 8, 27, 14, 7, tzinfo=timezone.utc),
            datetime(2026, 8, 27, 19, 52, tzinfo=timezone.utc),
        ],
    )

    await evaluate_session_grid_alert(store, measurement)

    store.record_observation.assert_awaited_once()
    observation = store.record_observation.await_args.kwargs
    assert observation["fingerprint"] == "pipeline:portfolio_cycle_session_grid"
    assert observation["severity"].value == "warning"
    assert observation["expected"] is True
    assert observation["details"]["open_gap_minutes"] == pytest.approx(37.0)
    assert observation["details"]["close_gap_minutes"] == pytest.approx(8.0)


@pytest.mark.asyncio
async def test_persistenza_e_idempotente_per_seduta() -> None:
    connection = AsyncMock()
    measurement = SessionGridMeasurement(
        session_date=SESSION_DATE,
        session_open=SESSION_OPEN,
        session_close=SESSION_CLOSE,
        first_effective_cycle=datetime(2026, 8, 27, 14, 7, tzinfo=timezone.utc),
        last_effective_cycle=datetime(2026, 8, 27, 19, 52, tzinfo=timezone.utc),
        open_gap_minutes=37.0,
        close_gap_minutes=8.0,
        threshold_minutes=20,
        alert_required=True,
    )

    await persist_session_grid_measurement(connection, measurement)

    connection.execute.assert_awaited_once()
    sql, *params = connection.execute.await_args.args
    assert "INSERT INTO portfolio_session_grid_metrics" in sql
    assert "ON CONFLICT (session_date) DO UPDATE" in sql
    assert params[0] == SESSION_DATE
    assert params[5:7] == [37.0, 8.0]


@pytest.mark.asyncio
async def test_collettore_usa_calendario_alpaca_in_ora_di_mercato() -> None:
    calendar_row = SimpleNamespace(
        date=SESSION_DATE,
        open=datetime(2026, 8, 27, 9, 30),
        close=datetime(2026, 8, 27, 16, 0),
    )
    trading_client = MagicMock()
    trading_client.get_calendar.return_value = [calendar_row]
    connection = AsyncMock()
    connection.fetch.return_value = [
        {"timestamp": datetime(2026, 8, 27, 14, 7, tzinfo=timezone.utc)},
        {"timestamp": datetime(2026, 8, 27, 19, 52, tzinfo=timezone.utc)},
    ]

    measurement = await collect_session_grid_measurement(
        connection,
        trading_client,
        observed_at=datetime(2026, 8, 27, 22, 50, tzinfo=timezone.utc),
    )

    assert measurement is not None
    assert measurement.session_open == SESSION_OPEN
    assert measurement.session_close == SESSION_CLOSE
    assert measurement.open_gap_minutes == pytest.approx(37.0)
    trading_client.get_calendar.assert_called_once()
    connection.fetch.assert_awaited_once()
