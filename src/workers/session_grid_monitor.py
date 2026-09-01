"""Misura EOD della copertura del portfolio-cycle sulla seduta reale (#428).

Il monitor legge il calendario Alpaca e le sole righe gia' persistite in
``portfolio_cycles``. Gli skip di pre-flight non arrivano in quella tabella:
primo e ultimo timestamp rappresentano quindi cicli effettivi, senza cambiare
il beat o il money path.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
import logging
from typing import Any, Sequence
from zoneinfo import ZoneInfo

from alpaca.trading.requests import GetCalendarRequest
from starlette.concurrency import run_in_threadpool

from src.mobile_monitoring.incidents import IncidentStore
from src.mobile_monitoring.models import EventCategory, EventKind, Severity
from src.mobile_monitoring.state import _aware_datetime
from src.util.retry import retry_transient

logger = logging.getLogger(__name__)

GAP_ALERT_THRESHOLD_MINUTES = 20
_ALERT_FINGERPRINT = "pipeline:portfolio_cycle_session_grid"
_MARKET_TIMEZONE = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class SessionGridMeasurement:
    session_date: date
    session_open: datetime
    session_close: datetime
    first_effective_cycle: datetime | None
    last_effective_cycle: datetime | None
    open_gap_minutes: float | None
    close_gap_minutes: float | None
    threshold_minutes: float
    alert_required: bool


def measure_session_grid(
    *,
    session_date: date,
    session_open: datetime,
    session_close: datetime,
    cycle_timestamps: Sequence[datetime],
    threshold_minutes: float = GAP_ALERT_THRESHOLD_MINUTES,
) -> SessionGridMeasurement:
    """Calcola i due margini della griglia usando solo cicli nella seduta."""
    if session_open.tzinfo is None or session_close.tzinfo is None:
        raise ValueError("session bounds must be timezone-aware")
    if session_close <= session_open:
        raise ValueError("session close must be after session open")
    if threshold_minutes <= 0:
        raise ValueError("threshold_minutes must be positive")

    effective = sorted(
        timestamp
        for timestamp in cycle_timestamps
        if timestamp.tzinfo is not None
        and session_open <= timestamp <= session_close
    )
    first = effective[0] if effective else None
    last = effective[-1] if effective else None
    open_gap = (
        (first - session_open).total_seconds() / 60.0
        if first is not None
        else None
    )
    close_gap = (
        (session_close - last).total_seconds() / 60.0
        if last is not None
        else None
    )
    alert_required = (
        open_gap is None
        or close_gap is None
        or open_gap > threshold_minutes
        or close_gap > threshold_minutes
    )
    return SessionGridMeasurement(
        session_date=session_date,
        session_open=session_open,
        session_close=session_close,
        first_effective_cycle=first,
        last_effective_cycle=last,
        open_gap_minutes=open_gap,
        close_gap_minutes=close_gap,
        threshold_minutes=threshold_minutes,
        alert_required=alert_required,
    )


def _calendar_date(row: object) -> date | None:
    value = getattr(row, "date", None)
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


async def collect_session_grid_measurement(
    connection: Any,
    trading_client: Any,
    *,
    observed_at: datetime,
    threshold_minutes: float = GAP_ALERT_THRESHOLD_MINUTES,
) -> SessionGridMeasurement | None:
    """Legge la seduta Alpaca corrente e i cicli effettivi gia' persistiti."""
    if observed_at.tzinfo is None:
        raise ValueError("observed_at must be timezone-aware")
    market_date = observed_at.astimezone(_MARKET_TIMEZONE).date()
    rows = await run_in_threadpool(
        retry_transient,
        lambda: trading_client.get_calendar(
            GetCalendarRequest(start=market_date, end=market_date)
        ),
    )
    session = next((row for row in rows if _calendar_date(row) == market_date), None)
    if session is None:
        return None

    session_open = _aware_datetime(getattr(session, "open", None), market_date)
    session_close = _aware_datetime(getattr(session, "close", None), market_date)
    if session_open is None or session_close is None:
        raise RuntimeError(f"confini Alpaca mancanti per la seduta {market_date}")
    session_open = session_open.astimezone(timezone.utc)
    session_close = session_close.astimezone(timezone.utc)

    cycle_rows = await connection.fetch(
        """
        SELECT timestamp
        FROM portfolio_cycles
        WHERE timestamp >= $1 AND timestamp <= $2
        ORDER BY timestamp
        """,
        session_open,
        session_close,
    )
    return measure_session_grid(
        session_date=market_date,
        session_open=session_open,
        session_close=session_close,
        cycle_timestamps=[row["timestamp"] for row in cycle_rows],
        threshold_minutes=threshold_minutes,
    )


async def persist_session_grid_measurement(
    connection: Any,
    measurement: SessionGridMeasurement,
) -> None:
    """Upsert idempotente: un rerun EOD corregge la stessa seduta, non la duplica."""
    await connection.execute(
        """
        INSERT INTO portfolio_session_grid_metrics (
            session_date, session_open, session_close,
            first_effective_cycle, last_effective_cycle,
            open_gap_minutes, close_gap_minutes,
            threshold_minutes, alert_required, measured_at
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, now())
        ON CONFLICT (session_date) DO UPDATE SET
            session_open = EXCLUDED.session_open,
            session_close = EXCLUDED.session_close,
            first_effective_cycle = EXCLUDED.first_effective_cycle,
            last_effective_cycle = EXCLUDED.last_effective_cycle,
            open_gap_minutes = EXCLUDED.open_gap_minutes,
            close_gap_minutes = EXCLUDED.close_gap_minutes,
            threshold_minutes = EXCLUDED.threshold_minutes,
            alert_required = EXCLUDED.alert_required,
            measured_at = now()
        """,
        measurement.session_date,
        measurement.session_open,
        measurement.session_close,
        measurement.first_effective_cycle,
        measurement.last_effective_cycle,
        measurement.open_gap_minutes,
        measurement.close_gap_minutes,
        measurement.threshold_minutes,
        measurement.alert_required,
    )


async def evaluate_session_grid_alert(
    store: IncidentStore,
    measurement: SessionGridMeasurement,
) -> None:
    """Apre un warning durevole sul breach e lo recupera su una seduta sana."""
    active = await store.list_active_incidents()
    details = {
        key: value.isoformat() if isinstance(value, (date, datetime)) else value
        for key, value in asdict(measurement).items()
    }
    if measurement.alert_required:
        if measurement.first_effective_cycle is None:
            summary = "Nessun ciclo di portafoglio effettivo nella seduta."
        else:
            summary = (
                "La griglia dei cicli non copre i confini della seduta entro "
                f"{measurement.threshold_minutes:g} minuti: "
                f"open={measurement.open_gap_minutes:g}, "
                f"close={measurement.close_gap_minutes:g}."
            )
        await store.record_observation(
            fingerprint=_ALERT_FINGERPRINT,
            kind=EventKind.ALERT_INCIDENT,
            category=EventCategory.TRADING,
            severity=Severity.WARNING,
            title="Griglia portfolio-cycle fuori seduta",
            summary=summary,
            details=details,
            entity_type="portfolio_cycle",
            expected=True,
        )
        return

    if _ALERT_FINGERPRINT in active:
        await store.record_observation(
            fingerprint=_ALERT_FINGERPRINT,
            kind=EventKind.ALERT_INCIDENT,
            category=EventCategory.TRADING,
            severity=Severity.INFO,
            title="Copertura seduta portfolio-cycle rientrata",
            summary="Primo e ultimo ciclo effettivo sono entro la soglia dai confini.",
            details=details,
            entity_type="portfolio_cycle",
            expected=False,
        )


async def run_session_grid_monitor(
    pool: Any,
    trading_client: Any,
    *,
    observed_at: datetime,
) -> dict[str, Any]:
    """Raccoglie, persiste e pubblica la misura per il giro EOD esistente."""
    async with pool.acquire() as connection:
        measurement = await collect_session_grid_measurement(
            connection,
            trading_client,
            observed_at=observed_at,
        )
        if measurement is None:
            return {"status": "skipped", "reason": "no_market_session"}
        await persist_session_grid_measurement(connection, measurement)

    await evaluate_session_grid_alert(IncidentStore(pool), measurement)
    return {
        "status": "ok",
        "session_date": measurement.session_date.isoformat(),
        "open_gap_minutes": measurement.open_gap_minutes,
        "close_gap_minutes": measurement.close_gap_minutes,
        "alert_required": measurement.alert_required,
    }
