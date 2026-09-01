"""Alert EOD per posizioni in perdita senza copertura news (#324).

Il dossier misura gia' la cecita' lato uscita con una definizione dichiarata:
perdita di almeno il 3% dall'ingresso, almeno due sedute consecutive senza righe
``news_log`` e zero segnali nella seduta corrente. Questo worker riusa quella
misura e la proietta nel registro incidenti mobile una volta a fine seduta.

E' sola strumentazione: non scrive segnali, non cambia ordini e non e' importato
dal money path. Se calendario, broker o DB non sono leggibili, fallisce aperto e
non chiude incidenti esistenti sulla base di un dato incompleto.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, cast
from zoneinfo import ZoneInfo

import asyncpg
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import GetCalendarRequest
from starlette.concurrency import run_in_threadpool

from src.analysis.dossier.exit_coverage import build_exit_coverage
from src.api.dependencies import init_asyncpg_pool
from src.config import config
from src.mobile_monitoring.incidents import IncidentStore
from src.mobile_monitoring.models import EventCategory, EventKind, Severity
from src.util.retry import retry_transient
from src.workers._async_utils import run_async
from src.workers.celery_app import app
from src.workers.session_grid_monitor import run_session_grid_monitor

logger = logging.getLogger(__name__)

_ALERT_PREFIX = "coverage:held_no_news_loss:"
_COVERAGE_WINDOW_SESSIONS = 10
_MARKET_TIMEZONE = ZoneInfo("America/New_York")


def _as_float(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _session_date(row: object) -> date | None:
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


def build_held_news_loss_coverage(
    positions: Sequence[object],
    *,
    entry_times: Mapping[str, datetime],
    sessions: Sequence[date],
    news_rows: Mapping[str, Mapping[str, int]],
    signals_today: Mapping[str, int],
) -> dict:
    """Adatta lo snapshot broker alla misura canonica del dossier.

    Il prezzo medio e il mark vengono dal broker, mentre la data d'ingresso viene
    dai trade aperti. Se quest'ultima manca, la posizione resta ``UNKNOWN``: senza
    sapere da quando e' detenuta non si puo' attribuirle uno streak di due sedute.
    """
    session_ids = [session.isoformat() for session in sorted(set(sessions))]
    target = session_ids[-1] if session_ids else ""
    rows: list[dict[str, Any]] = []
    bars: dict[str, dict[str, float | None]] = {}
    missing_entry: set[str] = set()

    for position in positions:
        symbol = str(getattr(position, "symbol", "")).strip().upper()
        if not symbol:
            continue
        entry_time = entry_times.get(symbol)
        if entry_time is None:
            missing_entry.add(symbol)
        current_price = _as_float(getattr(position, "current_price", None))
        rows.append(
            {
                "trade_id": None,
                "symbol": symbol,
                "strategia": None,
                "qty": _as_float(getattr(position, "qty", None)),
                # Un prezzo medio senza data non basta a stabilire da quante sedute
                # la posizione e' esposta: rendiamo il verdetto indeterminato.
                "entry_price": (
                    _as_float(getattr(position, "avg_entry_price", None))
                    if entry_time is not None
                    else None
                ),
                "entry_time": entry_time.isoformat() if entry_time is not None else None,
                "exit_time": None,
                "exit_price": None,
            }
        )
        bars[symbol] = {"close": current_price}

    coverage = build_exit_coverage(
        rows,
        data=target,
        sedute=session_ids,
        righe_per_seduta=news_rows,
        fonti_finestra={},
        copertura_per_ticker={},
        segnali_per_ticker=signals_today,
        barre=bars,
    )
    for row in coverage["posizioni"]:
        if row["ticker"] in missing_entry:
            row["missingness"].append("entry_time_missing")
    return coverage


async def evaluate_held_news_loss_alerts(
    store: IncidentStore,
    coverage: Mapping[str, Any],
) -> list[str]:
    """Apre, aggiorna o recupera gli incidenti per ticker.

    Le righe ``UNKNOWN`` preservano un incidente attivo: dato mancante non e'
    prova di recovery. Una posizione scomparsa da uno snapshot broker riuscito e'
    invece una recovery legittima, perche' non e' piu' detenuta.
    """
    active = await store.list_active_incidents()
    expected: set[str] = set()
    unknown: set[str] = set()
    alerted: list[str] = []
    threshold = coverage.get("soglia_perdita_da_ingresso")
    minimum_sessions = coverage.get("sedute_minime")

    for row in coverage.get("posizioni") or []:
        symbol = str(row.get("ticker") or "").strip().upper()
        if not symbol:
            continue
        verdict = row.get("cieco_lato_uscita")
        if verdict is None:
            unknown.add(symbol)
            continue
        if verdict is not True:
            continue

        fingerprint = f"{_ALERT_PREFIX}{symbol}"
        expected.add(fingerprint)
        alerted.append(symbol)
        await store.record_observation(
            fingerprint=fingerprint,
            kind=EventKind.POSITION,
            category=EventCategory.TRADING,
            severity=Severity.WARNING,
            title=f"Copertura news assente su {symbol}",
            summary=(
                f"{symbol} e' in perdita marcata, non ha news da "
                f"{row.get('sedute_consecutive_senza_righe')} sedute ne' "
                "segnali nella seduta corrente."
            ),
            details={
                "symbol": symbol,
                "return_from_entry": row.get("ritorno_da_ingresso"),
                "loss_threshold": threshold,
                "zero_news_sessions": row.get("sedute_consecutive_senza_righe"),
                "minimum_sessions": minimum_sessions,
                "news_rows_today": row.get("righe_news_log_giorno"),
                "signals_today": row.get("segnali_sentiment_giorno"),
                "notional_usd": row.get("notional_usd"),
            },
            entity_type="position",
            entity_id=symbol,
            expected=True,
        )

    for fingerprint in set(active) - expected:
        if not fingerprint.startswith(_ALERT_PREFIX):
            continue
        symbol = fingerprint.removeprefix(_ALERT_PREFIX)
        if symbol in unknown:
            continue
        await store.record_observation(
            fingerprint=fingerprint,
            kind=EventKind.POSITION,
            category=EventCategory.TRADING,
            severity=Severity.INFO,
            title=f"Copertura news rientrata su {symbol}",
            summary="La posizione non soddisfa piu' le condizioni dell'alert.",
            entity_type="position",
            entity_id=symbol,
            expected=False,
        )

    return sorted(alerted)


async def _market_sessions(
    trading_client: TradingClient,
    *,
    observed_at: datetime,
) -> list[date]:
    market_day = observed_at.astimezone(_MARKET_TIMEZONE).date()
    request = GetCalendarRequest(
        start=market_day - timedelta(days=3 * _COVERAGE_WINDOW_SESSIONS),
        end=market_day,
    )
    rows = await run_in_threadpool(
        retry_transient,
        lambda: trading_client.get_calendar(request),
    )
    sessions = sorted(
        session
        for row in rows
        if (session := _session_date(row)) is not None and session <= market_day
    )
    return sessions[-_COVERAGE_WINDOW_SESSIONS:]


async def _coverage_inputs(
    pool: asyncpg.Pool,
    symbols: Sequence[str],
    sessions: Sequence[date],
) -> tuple[dict[str, datetime], dict[str, dict[str, int]], dict[str, int]]:
    start = datetime.combine(sessions[0], time.min, tzinfo=timezone.utc)
    end = datetime.combine(sessions[-1] + timedelta(days=1), time.min, tzinfo=timezone.utc)
    today_start = datetime.combine(sessions[-1], time.min, tzinfo=timezone.utc)

    async with pool.acquire() as conn:
        entry_rows = await conn.fetch(
            """
            SELECT symbol, MIN(entry_time) AS entry_time
            FROM trades
            WHERE exit_time IS NULL AND symbol = ANY($1::text[])
            GROUP BY symbol
            """,
            list(symbols),
        )
        news = await conn.fetch(
            """
            SELECT ticker, (fetched_at AT TIME ZONE 'UTC')::date AS session_date,
                   COUNT(*) AS row_count
            FROM news_log
            WHERE ticker = ANY($1::text[]) AND fetched_at >= $2 AND fetched_at < $3
            GROUP BY ticker, session_date
            """,
            list(symbols),
            start,
            end,
        )
        signals = await conn.fetch(
            """
            SELECT symbol, COUNT(*) AS signal_count
            FROM sentiment_signals
            WHERE symbol = ANY($1::text[])
              AND generated_at >= $2 AND generated_at < $3
            GROUP BY symbol
            """,
            list(symbols),
            today_start,
            end,
        )

    entry_times = {
        str(row["symbol"]).upper(): row["entry_time"]
        for row in entry_rows
        if row["entry_time"] is not None
    }
    news_rows: dict[str, dict[str, int]] = {}
    for row in news:
        symbol = str(row["ticker"]).upper()
        news_rows.setdefault(symbol, {})[row["session_date"].isoformat()] = int(
            row["row_count"]
        )
    signal_counts = {
        str(row["symbol"]).upper(): int(row["signal_count"])
        for row in signals
    }
    return entry_times, news_rows, signal_counts


async def _collect_held_news_loss_coverage(
    pool: asyncpg.Pool,
    trading_client: TradingClient,
    *,
    observed_at: datetime,
) -> dict:
    sessions = await _market_sessions(trading_client, observed_at=observed_at)
    if len(sessions) < 2:
        raise RuntimeError("calendario Alpaca insufficiente per due sedute")

    positions = cast(
        Sequence[object],
        await run_in_threadpool(retry_transient, trading_client.get_all_positions),
    )
    symbols = sorted(
        {
            str(getattr(position, "symbol", "")).strip().upper()
            for position in positions
            if str(getattr(position, "symbol", "")).strip()
        }
    )
    if not symbols:
        return build_held_news_loss_coverage(
            [], entry_times={}, sessions=sessions, news_rows={}, signals_today={}
        )

    entry_times, news_rows, signal_counts = await _coverage_inputs(
        pool, symbols, sessions
    )
    return build_held_news_loss_coverage(
        positions,
        entry_times=entry_times,
        sessions=sessions,
        news_rows=news_rows,
        signals_today=signal_counts,
    )


@app.task(name="src.workers.held_news_loss_alert.run_held_news_loss_alert")
def run_held_news_loss_alert() -> dict[str, Any]:
    """Valuta la cecita' EOD e la pubblica come incidente mobile durevole."""

    async def _run() -> dict[str, Any]:
        pool = await init_asyncpg_pool()
        trading_client = TradingClient(
            api_key=config.ALPACA_API_KEY,
            secret_key=config.ALPACA_SECRET_KEY,
            paper=config.ALPACA_PAPER_MODE,
        )
        observed_at = datetime.now(timezone.utc)
        try:
            session_grid = await run_session_grid_monitor(
                pool,
                trading_client,
                observed_at=observed_at,
            )
        except Exception as exc:
            logger.warning("#428: session-grid monitor unavailable: %s", exc)
            session_grid = {"status": "skipped", "reason": "measurement_unavailable"}

        try:
            coverage = await _collect_held_news_loss_coverage(
                pool,
                trading_client,
                observed_at=observed_at,
            )
        except Exception as exc:
            logger.warning("#324: held news-loss alert unavailable: %s", exc)
            return {
                "status": "skipped",
                "reason": "coverage_data_unavailable",
                "session_grid": session_grid,
            }

        alerted = await evaluate_held_news_loss_alerts(
            IncidentStore(pool), coverage
        )
        return {
            "status": "ok",
            "alerted": len(alerted),
            "symbols": alerted,
            "session_grid": session_grid,
        }

    return run_async(_run())
