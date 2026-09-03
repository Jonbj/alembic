"""Misura e alert EOD sulla quota di news scartate come stale (#432).

Il worker legge esclusivamente i ledger osservativi gia' esistenti, persiste un
rollup giornaliero per fonte e invia Telegram solo quando la quota supera il
25%. Non e' importato dal money path e non cambia il destino di alcuna news.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Mapping, Sequence

from src.api.dependencies import init_asyncpg_pool
from src.config import config
from src.notifications.base import AlertLevel
from src.notifications.telegram import TelegramNotifier
from src.workers._async_utils import run_async
from src.workers.celery_app import app


STALE_DROP_ALERT_THRESHOLD = 0.25


@dataclass(frozen=True)
class StaleDropMeasurement:
    day: date
    source: str
    queued: int
    stale_drops: int
    already_stale_at_fetch: int
    went_stale_in_queue: int
    unclassified_stale: int
    stale_drop_share: float | None
    avg_fetch_latency_hours: float | None
    avg_queue_wait_hours: float | None
    max_news_age_hours: float
    alert_threshold: float
    alert_required: bool


def build_stale_drop_measurement(
    *,
    day: date,
    source: str,
    queued: int,
    stale_drops: int,
    already_stale_at_fetch: int,
    went_stale_in_queue: int,
    unclassified_stale: int = 0,
    avg_fetch_latency_hours: float | None = None,
    avg_queue_wait_hours: float | None = None,
    max_news_age_hours: float = 2.0,
    alert_threshold: float = STALE_DROP_ALERT_THRESHOLD,
) -> StaleDropMeasurement:
    """Costruisce il verdetto senza DB, lasciando esplicito il denominatore."""
    counts = (queued, stale_drops, already_stale_at_fetch, went_stale_in_queue)
    if any(value < 0 for value in counts) or unclassified_stale < 0:
        raise ValueError("stale-drop counts must be non-negative")
    if already_stale_at_fetch + went_stale_in_queue + unclassified_stale != stale_drops:
        raise ValueError("stale-drop cause counts must add up to stale_drops")
    if alert_threshold < 0 or max_news_age_hours <= 0:
        raise ValueError("measurement thresholds must be positive")

    share = stale_drops / queued if queued > 0 else None
    return StaleDropMeasurement(
        day=day,
        source=source,
        queued=queued,
        stale_drops=stale_drops,
        already_stale_at_fetch=already_stale_at_fetch,
        went_stale_in_queue=went_stale_in_queue,
        unclassified_stale=unclassified_stale,
        stale_drop_share=share,
        avg_fetch_latency_hours=avg_fetch_latency_hours,
        avg_queue_wait_hours=avg_queue_wait_hours,
        max_news_age_hours=max_news_age_hours,
        alert_threshold=alert_threshold,
        alert_required=share is not None and share > alert_threshold,
    )


def _optional_float(row: Mapping[str, Any], key: str) -> float | None:
    value = row.get(key)
    return float(value) if value is not None else None


async def collect_stale_drop_measurements(
    connection: Any,
    *,
    start_day: date,
    end_day: date,
    max_news_age_hours: float,
    alert_threshold: float = STALE_DROP_ALERT_THRESHOLD,
) -> list[StaleDropMeasurement]:
    """Aggrega un intervallo inclusivo; la stessa query serve per EOD e backfill."""
    rows = await connection.fetch(
        """
        WITH stale AS (
            SELECT (dropped_at AT TIME ZONE 'UTC')::date AS day,
                   COALESCE(source, 'unknown') AS source,
                   COUNT(*)::int AS stale_drops,
                   COUNT(*) FILTER (
                       WHERE raw_ingested_at IS NOT NULL
                         AND published_at IS NOT NULL
                         AND raw_ingested_at - published_at
                             >= ($3::double precision * INTERVAL '1 hour')
                   )::int AS already_stale_at_fetch,
                   COUNT(*) FILTER (
                       WHERE raw_ingested_at IS NOT NULL
                         AND published_at IS NOT NULL
                         AND raw_ingested_at - published_at
                             < ($3::double precision * INTERVAL '1 hour')
                   )::int AS went_stale_in_queue,
                   COUNT(*) FILTER (
                       WHERE raw_ingested_at IS NULL OR published_at IS NULL
                   )::int AS unclassified_stale,
                   AVG(
                       EXTRACT(EPOCH FROM (raw_ingested_at - published_at)) / 3600.0
                   ) FILTER (
                       WHERE raw_ingested_at IS NOT NULL AND published_at IS NOT NULL
                   ) AS avg_fetch_latency_hours,
                   AVG(
                       EXTRACT(EPOCH FROM (dropped_at - raw_ingested_at)) / 3600.0
                   ) FILTER (WHERE raw_ingested_at IS NOT NULL) AS avg_queue_wait_hours
            FROM news_queue_drops
            WHERE discarded_reason = 'stale'
              AND dropped_at >= ($1::date::timestamp AT TIME ZONE 'UTC')
              AND dropped_at < (
                  ($2::date + 1)::timestamp AT TIME ZONE 'UTC'
              )
            GROUP BY day, COALESCE(source, 'unknown')
        ), keys AS (
            SELECT day, source
            FROM ingestion_stats_daily
            WHERE day BETWEEN $1 AND $2
            UNION
            SELECT day, source FROM stale
        )
        SELECT keys.day,
               keys.source,
               COALESCE(stats.queued, 0)::int AS queued,
               COALESCE(stale.stale_drops, 0)::int AS stale_drops,
               COALESCE(stale.already_stale_at_fetch, 0)::int
                   AS already_stale_at_fetch,
               COALESCE(stale.went_stale_in_queue, 0)::int
                   AS went_stale_in_queue,
               COALESCE(stale.unclassified_stale, 0)::int AS unclassified_stale,
               stale.avg_fetch_latency_hours,
               stale.avg_queue_wait_hours
        FROM keys
        LEFT JOIN ingestion_stats_daily AS stats USING (day, source)
        LEFT JOIN stale USING (day, source)
        ORDER BY keys.day, keys.source
        """,
        start_day,
        end_day,
        max_news_age_hours,
    )
    return [
        build_stale_drop_measurement(
            day=row["day"],
            source=str(row["source"]),
            queued=int(row["queued"]),
            stale_drops=int(row["stale_drops"]),
            already_stale_at_fetch=int(row["already_stale_at_fetch"]),
            went_stale_in_queue=int(row["went_stale_in_queue"]),
            unclassified_stale=int(row["unclassified_stale"]),
            avg_fetch_latency_hours=_optional_float(row, "avg_fetch_latency_hours"),
            avg_queue_wait_hours=_optional_float(row, "avg_queue_wait_hours"),
            max_news_age_hours=max_news_age_hours,
            alert_threshold=alert_threshold,
        )
        for row in rows
    ]


async def persist_stale_drop_measurements(
    connection: Any,
    measurements: Sequence[StaleDropMeasurement],
) -> None:
    """Upsert idempotente: un backfill aggiorna il rollup senza duplicarlo."""
    if not measurements:
        return
    await connection.executemany(
        """
        INSERT INTO stale_drop_metrics_daily (
            day, source, queued, stale_drops,
            already_stale_at_fetch, went_stale_in_queue, unclassified_stale,
            stale_drop_share, avg_fetch_latency_hours, avg_queue_wait_hours,
            max_news_age_hours, alert_threshold, alert_required, measured_at
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, now())
        ON CONFLICT (day, source) DO UPDATE SET
            queued = EXCLUDED.queued,
            stale_drops = EXCLUDED.stale_drops,
            already_stale_at_fetch = EXCLUDED.already_stale_at_fetch,
            went_stale_in_queue = EXCLUDED.went_stale_in_queue,
            unclassified_stale = EXCLUDED.unclassified_stale,
            stale_drop_share = EXCLUDED.stale_drop_share,
            avg_fetch_latency_hours = EXCLUDED.avg_fetch_latency_hours,
            avg_queue_wait_hours = EXCLUDED.avg_queue_wait_hours,
            max_news_age_hours = EXCLUDED.max_news_age_hours,
            alert_threshold = EXCLUDED.alert_threshold,
            alert_required = EXCLUDED.alert_required,
            measured_at = now()
        """,
        [
            (
                item.day,
                item.source,
                item.queued,
                item.stale_drops,
                item.already_stale_at_fetch,
                item.went_stale_in_queue,
                item.unclassified_stale,
                item.stale_drop_share,
                item.avg_fetch_latency_hours,
                item.avg_queue_wait_hours,
                item.max_news_age_hours,
                item.alert_threshold,
                item.alert_required,
            )
            for item in measurements
        ],
    )


def format_stale_drop_alert(measurements: Sequence[StaleDropMeasurement]) -> str:
    """Formatta un unico alert con una sezione per fonte in breach."""
    breached = [item for item in measurements if item.alert_required]
    if not breached:
        return ""
    lines = [
        "Stale news queue alert",
        f"Threshold: > {breached[0].alert_threshold:.0%} of queued items",
    ]
    for item in breached:
        share = item.stale_drop_share or 0.0
        lines.extend(
            [
                "",
                f"{item.day.isoformat()} — {item.source}",
                f"Stale drops: {item.stale_drops}/{item.queued} ({share:.1%})",
                f"Already stale at fetch: {item.already_stale_at_fetch}",
                f"Went stale in queue: {item.went_stale_in_queue}",
                f"Unclassified: {item.unclassified_stale}",
            ]
        )
        if item.avg_fetch_latency_hours is not None:
            lines.append(f"Fetch latency avg: {item.avg_fetch_latency_hours:.2f}h")
        if item.avg_queue_wait_hours is not None:
            lines.append(f"Queue wait avg: {item.avg_queue_wait_hours:.2f}h")
    return "\n".join(lines)


def _parse_day(value: str | None, default: date) -> date:
    return date.fromisoformat(value) if value is not None else default


@app.task(name="src.workers.stale_drop_alert.run_stale_drop_alert")
def run_stale_drop_alert(
    start_day: str | None = None,
    end_day: str | None = None,
) -> dict[str, Any]:
    """Persiste una seduta o un intervallo; l'intervallo abilita il backfill."""

    async def _run() -> dict[str, Any]:
        today = datetime.now(timezone.utc).date()
        start = _parse_day(start_day, today)
        end = _parse_day(end_day, start)
        if end < start:
            raise ValueError("end_day must not precede start_day")

        pool = await init_asyncpg_pool()
        async with pool.acquire() as connection:
            measurements = await collect_stale_drop_measurements(
                connection,
                start_day=start,
                end_day=end,
                max_news_age_hours=float(config.MAX_NEWS_AGE_HOURS),
            )
            await persist_stale_drop_measurements(connection, measurements)

        breached = [item for item in measurements if item.alert_required]
        if breached:
            await TelegramNotifier().send_alert(
                format_stale_drop_alert(breached),
                level=AlertLevel.WARNING,
            )
        return {
            "status": "ok",
            "measured": len(measurements),
            "alerted": len(breached),
        }

    return run_async(_run())
