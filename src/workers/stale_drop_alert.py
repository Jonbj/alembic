"""Misura e alert EOD sulla quota di news scartate come stale (#432).

Il worker legge esclusivamente i ledger osservativi gia' esistenti, persiste un
rollup giornaliero per fonte e invia Telegram solo quando la quota supera il
25%. Non e' importato dal money path e non cambia il destino di alcuna news.

**2026-09-10 — Opzione B, deroga registrata in `docs/evidence/OBSERVATION_CHARTER.md`.**
Due difetti dello strumento, corretti insieme perche' l'uno senza l'altro
lascerebbe la serie illeggibile:

1. *Il denominatore era cross-day.* Il numeratore era raggruppato su
   `dropped_at::date`, il denominatore (`ingestion_stats_daily.queued`) sul
   giorno di **accodamento**. La coorte accodata di notte stava al numeratore di
   D+1 e al denominatore di D: le quote pubblicate non erano rapporti sulla
   stessa coorte. Ora la chiave e' la **coorte di accodamento**.
2. *La causa che serviva non era registrata.* Per il WebSocket
   `raw_ingested_at ~= published_at`, quindi tutta la coorte notturna cadeva in
   `went_stale_in_queue` — la stessa casella di un outage del consumatore a
   mercato aperto, che ha il fix opposto. Il quarto gruppo
   `went_stale_off_session` le separa; e' **pubblicato** ma non concorre alla
   soglia, che resta 0,25 e si applica alla sola quota accodata entro seduta.

Il criterio di accettazione della deroga e' un test di sensibilita', non
un'aspettativa: l'outage del 2026-09-09 15-16Z deve restare in breach sul gruppo
in-seduta. Se non allerta piu', la correzione e' sbagliata e va revertata.
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
    went_stale_off_session: int
    unclassified_stale: int
    stale_drop_share: float | None
    avg_fetch_latency_hours: float | None
    avg_queue_wait_hours: float | None
    max_news_age_hours: float
    alert_threshold: float
    alert_required: bool

    @property
    def in_session_stale_drops(self) -> int:
        """Scarti su cui si decide: tutto cio' che non e' coorte fuori seduta.

        Include `unclassified_stale` di proposito. Senza `raw_ingested_at` la
        seduta non e' ricostruibile, e un dato incompleto non scusa un guasto —
        stesso fail-closed di #324, dove un dato mancante preserva l'incidente
        invece di dichiarare una falsa rientranza.
        """
        return self.stale_drops - self.went_stale_off_session

    @property
    def in_session_stale_drop_share(self) -> float | None:
        if self.queued <= 0:
            return None
        return self.in_session_stale_drops / self.queued


def build_stale_drop_measurement(
    *,
    day: date,
    source: str,
    queued: int,
    stale_drops: int,
    already_stale_at_fetch: int,
    went_stale_in_queue: int,
    went_stale_off_session: int = 0,
    unclassified_stale: int = 0,
    avg_fetch_latency_hours: float | None = None,
    avg_queue_wait_hours: float | None = None,
    max_news_age_hours: float = 2.0,
    alert_threshold: float = STALE_DROP_ALERT_THRESHOLD,
) -> StaleDropMeasurement:
    """Costruisce il verdetto senza DB, lasciando esplicito il denominatore."""
    counts = (
        queued,
        stale_drops,
        already_stale_at_fetch,
        went_stale_in_queue,
        went_stale_off_session,
        unclassified_stale,
    )
    if any(value < 0 for value in counts):
        raise ValueError("stale-drop counts must be non-negative")
    if (
        already_stale_at_fetch
        + went_stale_in_queue
        + went_stale_off_session
        + unclassified_stale
        != stale_drops
    ):
        raise ValueError("stale-drop cause counts must add up to stale_drops")
    if alert_threshold < 0 or max_news_age_hours <= 0:
        raise ValueError("measurement thresholds must be positive")

    # La quota complessiva resta pubblicata — e' la serie storica. Ma la
    # decisione si prende sulla quota accodata entro seduta: la coorte a mercato
    # chiuso non e' un guasto, e' la fisiologia di un consumatore con guardia di
    # seduta. Vedi la deroga del 2026-09-10 nella carta.
    share = stale_drops / queued if queued > 0 else None
    in_session_share = (
        (stale_drops - went_stale_off_session) / queued if queued > 0 else None
    )
    return StaleDropMeasurement(
        day=day,
        source=source,
        queued=queued,
        stale_drops=stale_drops,
        already_stale_at_fetch=already_stale_at_fetch,
        went_stale_in_queue=went_stale_in_queue,
        went_stale_off_session=went_stale_off_session,
        unclassified_stale=unclassified_stale,
        stale_drop_share=share,
        avg_fetch_latency_hours=avg_fetch_latency_hours,
        avg_queue_wait_hours=avg_queue_wait_hours,
        max_news_age_hours=max_news_age_hours,
        alert_threshold=alert_threshold,
        alert_required=in_session_share is not None
        and in_session_share > alert_threshold,
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
    """Aggrega un intervallo inclusivo; la stessa query serve per EOD e backfill.

    La chiave di aggregazione e' la **coorte di accodamento**, non il giorno di
    scarto: `ingestion_stats_daily.queued` — il denominatore — e' incrementato
    all'accodamento, e con due chiavi diverse il rapporto mescolava coorti.

    La **finestra** resta invece su `dropped_at`, e le due cose non sono
    intercambiabili. Il beat gira alle 22:55Z su un giorno solo: la coorte
    accodata dal WebSocket dopo la chiusura del giorno D e' ancora in coda a
    quell'ora, viene scartata alla campana di D+1, e una finestra sulla sola
    coorte non la vedrebbe mai — ne' il giro di D (non ancora scartata) ne'
    quello di D+1 (coorte sbagliata). E' proprio la coorte notturna, cioe' il
    fenomeno che questa misura esiste per descrivere.

    Il rovescio della finestra su `dropped_at` — riscrivere **parziale** via
    ON CONFLICT DO UPDATE una coorte precedente gia' completa — e' evitato
    separando le due cose: `dropped_at` decide *quali* coorti toccare, ma il
    conteggio di ciascuna e' sempre su **tutti** i suoi scarti, senza bound
    temporale. Una coorte viene riscritta solo per intero.
    """
    rows = await connection.fetch(
        """
        WITH drops AS (
            SELECT (COALESCE(raw_ingested_at, dropped_at) AT TIME ZONE 'UTC')::date AS day,
                   COALESCE(source, 'unknown') AS source,
                   raw_ingested_at,
                   published_at,
                   dropped_at,
                   enqueued_off_session
            FROM news_queue_drops
            WHERE discarded_reason = 'stale'
        ), coorti AS (
            -- Quali coorti toccare. Una coorte entra se cade nell'intervallo
            -- richiesto, oppure se qualcuno dei suoi item e' stato scartato
            -- dentro la finestra: e' cosi' che il drop tardivo del giorno dopo
            -- riporta in gioco la coorte notturna che lo ha accodato.
            SELECT day, source
            FROM ingestion_stats_daily
            WHERE day BETWEEN $1 AND $2
            UNION
            SELECT day, source
            FROM drops
            WHERE day BETWEEN $1 AND $2
               OR (
                   dropped_at >= ($1::date::timestamp AT TIME ZONE 'UTC')
                   AND dropped_at < (($2::date + 1)::timestamp AT TIME ZONE 'UTC')
               )
        ), stale AS (
            -- Conteggio COMPLETO delle coorti toccate: nessun bound su
            -- dropped_at qui dentro, o l'upsert riscriverebbe parziale una
            -- coorte gia' chiusa.
            SELECT drops.day AS day,
                   drops.source AS source,
                   COUNT(*)::int AS stale_drops,
                   COUNT(*) FILTER (
                       WHERE raw_ingested_at IS NOT NULL
                         AND published_at IS NOT NULL
                         AND enqueued_off_session IS NOT TRUE
                         AND raw_ingested_at - published_at
                             >= ($3::double precision * INTERVAL '1 hour')
                   )::int AS already_stale_at_fetch,
                   COUNT(*) FILTER (
                       WHERE raw_ingested_at IS NOT NULL
                         AND published_at IS NOT NULL
                         AND enqueued_off_session IS NOT TRUE
                         AND raw_ingested_at - published_at
                             < ($3::double precision * INTERVAL '1 hour')
                   )::int AS went_stale_in_queue,
                   COUNT(*) FILTER (
                       WHERE raw_ingested_at IS NOT NULL
                         AND published_at IS NOT NULL
                         AND enqueued_off_session IS TRUE
                   )::int AS went_stale_off_session,
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
            FROM drops
            JOIN coorti USING (day, source)
            GROUP BY drops.day, drops.source
        )
        SELECT coorti.day,
               coorti.source,
               COALESCE(stats.queued, 0)::int AS queued,
               COALESCE(stale.stale_drops, 0)::int AS stale_drops,
               COALESCE(stale.already_stale_at_fetch, 0)::int
                   AS already_stale_at_fetch,
               COALESCE(stale.went_stale_in_queue, 0)::int
                   AS went_stale_in_queue,
               COALESCE(stale.went_stale_off_session, 0)::int
                   AS went_stale_off_session,
               COALESCE(stale.unclassified_stale, 0)::int AS unclassified_stale,
               stale.avg_fetch_latency_hours,
               stale.avg_queue_wait_hours
        FROM coorti
        LEFT JOIN ingestion_stats_daily AS stats USING (day, source)
        LEFT JOIN stale USING (day, source)
        ORDER BY coorti.day, coorti.source
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
            went_stale_off_session=int(row["went_stale_off_session"]),
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
            already_stale_at_fetch, went_stale_in_queue, went_stale_off_session,
            unclassified_stale,
            stale_drop_share, avg_fetch_latency_hours, avg_queue_wait_hours,
            max_news_age_hours, alert_threshold, alert_required, measured_at
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, now())
        ON CONFLICT (day, source) DO UPDATE SET
            queued = EXCLUDED.queued,
            stale_drops = EXCLUDED.stale_drops,
            already_stale_at_fetch = EXCLUDED.already_stale_at_fetch,
            went_stale_in_queue = EXCLUDED.went_stale_in_queue,
            went_stale_off_session = EXCLUDED.went_stale_off_session,
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
                item.went_stale_off_session,
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
        f"Threshold: > {breached[0].alert_threshold:.0%} of in-session queued items",
        "Cohort = enqueue day; off-session drops are reported, not counted (#432)",
    ]
    for item in breached:
        share = item.stale_drop_share or 0.0
        in_session_share = item.in_session_stale_drop_share or 0.0
        lines.extend(
            [
                "",
                f"{item.day.isoformat()} — {item.source}",
                # La riga su cui si e' deciso viene per prima; il totale resta
                # pubblicato sotto, cosi' la serie storica e' ancora leggibile.
                f"In-session stale drops: {item.in_session_stale_drops}"
                f"/{item.queued} ({in_session_share:.1%})",
                f"Total stale drops: {item.stale_drops}/{item.queued} ({share:.1%})",
                f"Already stale at fetch: {item.already_stale_at_fetch}",
                f"Went stale in queue: {item.went_stale_in_queue}",
                f"Enqueued off-session: {item.went_stale_off_session}",
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
