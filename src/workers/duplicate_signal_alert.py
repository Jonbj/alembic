"""Misura e alert giornaliero sui news_log_id duplicati in sentiment_signals (#551).

Il ciclo sentiment non e' idempotente di natura: dopo un SoftTimeLimitExceeded
la crash-recovery re-incoda gli item rimasti in news:processing e un articolo
gia' persistito veniva ri-scorato, con esiti e provider diversi (F-072). Il fix
(LREM per-item + dedup difensiva nel sink) rende il duplicato un difetto, non
una routine — quindi va misurato: ogni IC, copertura articoli e conteggio di
segnali calcolato su sentiment_signals conterebbe due volte lo stesso articolo.

Sola lettura: nessuna scrittura, nessuna soglia di trading. L'alert e' lo
strumento che trasforma "la serie e' contaminata" in un segnale quotidiano.

Le 12 righe del 2026-09-08 (news_log_id 9902-9913) sono il baseline noto:
cancellarle e' una modifica di una serie osservata, quindi una decisione
dell'operatore da registrare, non un'azione silenziosa. Finche' quella
decisione non arriva, l'alert le distingue dai duplicati NUOVI — che soli
indicherebbero una ricaduta del difetto.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping, Sequence

from src.api.dependencies import init_asyncpg_pool
from src.notifications.base import AlertLevel
from src.notifications.telegram import TelegramNotifier
from src.workers._async_utils import run_async
from src.workers.celery_app import app


# Soglia del DoD: zero duplicati ammessi.
DUPLICATE_SIGNALS_ALERT_THRESHOLD = 0

# F-072, riverificato sul DB live il 2026-09-09 (issue #551): dodici gruppi,
# news_log_id 9902-9913, due giri di scoring a distanza di ~27 minuti.
F072_KNOWN_DUPLICATE_NEWS_LOG_IDS = frozenset(range(9902, 9914))


@dataclass(frozen=True)
class DuplicateSignalsMeasurement:
    duplicate_news_log_count: int
    news_log_ids: frozenset[int]
    alert_threshold: int

    @property
    def known_news_log_ids(self) -> frozenset[int]:
        """I dodici gruppi F-072: contaminazione nota, decisione pendente."""
        return self.news_log_ids & F072_KNOWN_DUPLICATE_NEWS_LOG_IDS

    @property
    def new_news_log_ids(self) -> frozenset[int]:
        """Duplicati fuori dal baseline: qui il difetto sarebbe ricaduto."""
        return self.news_log_ids - F072_KNOWN_DUPLICATE_NEWS_LOG_IDS

    @property
    def alert_required(self) -> bool:
        return self.duplicate_news_log_count > self.alert_threshold


def build_duplicate_signals_measurement(
    rows: Sequence[Mapping[str, Any]],
    *,
    alert_threshold: int = DUPLICATE_SIGNALS_ALERT_THRESHOLD,
) -> DuplicateSignalsMeasurement:
    """Costruisce il verdetto senza DB, dalle righe di collect_..._rows."""
    news_log_ids = frozenset(int(row["news_log_id"]) for row in rows)
    return DuplicateSignalsMeasurement(
        duplicate_news_log_count=len(news_log_ids),
        news_log_ids=news_log_ids,
        alert_threshold=alert_threshold,
    )


async def collect_duplicate_news_log_rows(connection: Any) -> list[dict[str, Any]]:
    """Un news_log_id per gruppo di segnali duplicati, con il dettaglio per l'alert."""
    rows = await connection.fetch(
        """
        SELECT news_log_id,
               COUNT(*)::int AS signal_count,
               STRING_AGG(DISTINCT symbol, ',') AS symbols,
               MIN(generated_at) AS first_generated_at,
               MAX(generated_at) AS last_generated_at
        FROM sentiment_signals
        WHERE news_log_id IS NOT NULL
        GROUP BY news_log_id
        HAVING COUNT(*) > 1
        ORDER BY news_log_id
        """
    )
    return [dict(row) for row in rows]


def _format_generated_at(value: Any) -> str:
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%MZ")
    return str(value)


def format_duplicate_signals_alert(
    measurement: DuplicateSignalsMeasurement,
    rows: Sequence[Mapping[str, Any]] = (),
) -> str:
    """Un solo alert: totale, poi i nuovi, poi i F-072 noti come contesto."""
    if not measurement.alert_required:
        return ""
    known = measurement.known_news_log_ids
    new = measurement.new_news_log_ids
    lines = [
        "Duplicate sentiment signals (#551/F-072)",
        f"Threshold: {measurement.alert_threshold} — "
        f"{measurement.duplicate_news_log_count} news_log_id duplicated",
    ]
    if new:
        lines.append(f"NEW ({len(new)}): {', '.join(str(i) for i in sorted(new))}")
    if known:
        lines.append(
            f"Known F-072 2026-09-08, operator decision pending (#551) "
            f"({len(known)}): {', '.join(str(i) for i in sorted(known))}"
        )
    for row in rows:
        lines.append(
            f"  news_log {row['news_log_id']}: {row['signal_count']} signals, "
            f"{row['symbols']}, "
            f"{_format_generated_at(row['first_generated_at'])} → "
            f"{_format_generated_at(row['last_generated_at'])}"
        )
    return "\n".join(lines)


@app.task(name="src.workers.duplicate_signal_alert.run_duplicate_signals_alert")
def run_duplicate_signals_alert() -> dict[str, Any]:
    """Conta i news_log_id duplicati (DoD #551) e allerta se ce n'e' qualcuno."""

    async def _run() -> dict[str, Any]:
        pool = await init_asyncpg_pool()
        async with pool.acquire() as connection:
            rows = await collect_duplicate_news_log_rows(connection)

        measurement = build_duplicate_signals_measurement(rows)
        alerted = 0
        if measurement.alert_required:
            await TelegramNotifier().send_alert(
                format_duplicate_signals_alert(measurement, rows),
                level=AlertLevel.WARNING,
            )
            alerted = 1
        return {
            "status": "ok",
            "duplicated_news_log": measurement.duplicate_news_log_count,
            "alerted": alerted,
        }

    return run_async(_run())
