"""Censimento periodico della coda news — osservabilità pura (#544, opzione A).

Perché esiste: oggi l'accumulo notturno di `news:queue` e il suo svuotamento alla
campana si inferiscono dai log dei container, che i rebuild delle 22:20Z e 06:20Z
hanno già distrutto una volta (#544). Questo task campiona ogni 5 minuti, 24/7,
profondità ed età della coda e le persiste in Postgres: il dente di sega diventa un
dato invece di un'inferenza, e sopravvive a qualunque ricostruzione.

Perimetro (rigido):
  * **Nessun consumo.** Solo `LLEN` e `LRANGE`. Mai `LMOVE`, mai `DELETE`, mai
    `RPUSH`: il destino di nessuna news cambia per effetto della misura.
  * **Nessuna lettura dal money path.** Non tocca `sentiment_signals`, `news_log`,
    Redis in scrittura, né alcuna decisione di ordine.
  * **Nessuna soglia nuova.** Fresh/stale è deciso da `_is_stale_news`
    *importato* da `src.workers.sentiment` — mai ricopiato. È la regola #169/#467:
    la misura chiama la regola di produzione, non la reimplementa. Se qui vivesse
    una seconda copia della soglia, la serie divergerebbe in silenzio da
    `build_stale_drop_row` alla prima modifica di una delle due.

Le profondità sono **esatte** (vengono da `LLEN`); le età sono di un **campione**
con tetto `CENSUS_SAMPLE_CAP`, preso a testa e coda, perché leggere per intero una
coda da migliaia di item ogni 5 minuti farebbe del censimento stesso un carico.
"""

from __future__ import annotations

import json
import logging
import statistics
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Sequence

from redis import Redis

from src.api.dependencies import init_asyncpg_pool
from src.config import config
from src.models.news import MarketAuxNewsItem, NewsItem
from src.workers import sentiment as _sentiment
from src.workers._async_utils import run_async
from src.workers.celery_app import app

log = logging.getLogger(__name__)


QUEUE_KEY = "news:queue"
PROCESSING_KEY = "news:processing"
DEAD_LETTER_KEY = "news:dead-letter"

# Tetto esplicito del campione per singola rilevazione: metà dalla testa (gli item
# più vecchi, quelli che raccontano l'accumulo) e metà dalla coda (gli ultimi
# arrivati). 500 item ogni 5 minuti sono I/O trascurabile; leggere l'intera coda no.
CENSUS_SAMPLE_CAP = 500


@dataclass(frozen=True)
class QueueCensusRow:
    """Una riga per sorgente per campione.

    `source is None` è la riga di sola profondità: si scrive quando il campione non
    contiene alcun item classificabile (coda vuota, o interamente illeggibile), così
    la serie delle profondità non ha buchi proprio nei momenti in cui vale zero.
    """

    source: str | None
    queue_depth: int
    processing_depth: int
    dead_letter_depth: int
    n_fresh: int
    n_stale: int
    oldest_age_hours: float | None
    p50_age_hours: float | None


def _stale_threshold_hours() -> float:
    """La soglia vive in `sentiment.py`: qui si legge, non si ridichiara (#169/#467)."""
    return float(_sentiment._SENTIMENT_MAX_NEWS_AGE_HOURS)


def _parse_item(raw: bytes | str) -> NewsItem | None:
    """Stessa costruzione del consumatore; illeggibile → fuori dal campione.

    Un payload non parseabile **non** viene contato come stale: sarebbe un drop
    inventato dalla misura. Esce dal campione e resta dov'è (il dead-letter è
    competenza del consumatore, non del censimento).
    """
    try:
        data = json.loads(raw)
        return (
            MarketAuxNewsItem(**data)
            if "marketaux_sentiment" in data
            else NewsItem(**data)
        )
    except Exception as exc:  # payload corrotto o schema cambiato
        log.debug("Item di coda non parseabile, escluso dal campione: %s", exc)
        return None


def _age_hours(item: NewsItem, now: datetime) -> float:
    """Età in ore da `published_at`, tz-safe come `_is_stale_news` (naive == UTC)."""
    ts = item.timestamp
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return (now - ts).total_seconds() / 3600.0


def sample_queue(
    redis_client: Any,
    key: str,
    depth: int,
    cap: int = CENSUS_SAMPLE_CAP,
) -> list[bytes]:
    """Campione a testa e coda, mai più di `cap` item, sempre in sola lettura."""
    if depth <= 0:
        return []
    if depth <= cap:
        return list(redis_client.lrange(key, 0, depth - 1))
    head = cap // 2
    tail = cap - head
    return list(redis_client.lrange(key, 0, head - 1)) + list(
        redis_client.lrange(key, -tail, -1)
    )


def build_census_rows(
    raw_items: Sequence[bytes | str],
    *,
    now: datetime,
    queue_depth: int,
    processing_depth: int,
    dead_letter_depth: int,
) -> list[QueueCensusRow]:
    """Aggrega il campione per sorgente. Nessun accesso a Redis: testabile a secco."""
    threshold = _stale_threshold_hours()
    per_source: dict[str, dict[str, Any]] = {}
    for raw in raw_items:
        item = _parse_item(raw)
        if item is None:
            continue
        source = item.source or "unknown"
        bucket = per_source.setdefault(source, {"fresh": 0, "stale": 0, "ages": []})
        bucket["ages"].append(_age_hours(item, now))
        if _sentiment._is_stale_news(item, now, threshold):
            bucket["stale"] += 1
        else:
            bucket["fresh"] += 1

    def _row(source: str | None, bucket: dict[str, Any] | None) -> QueueCensusRow:
        ages = bucket["ages"] if bucket else []
        return QueueCensusRow(
            source=source,
            queue_depth=queue_depth,
            processing_depth=processing_depth,
            dead_letter_depth=dead_letter_depth,
            n_fresh=bucket["fresh"] if bucket else 0,
            n_stale=bucket["stale"] if bucket else 0,
            oldest_age_hours=max(ages) if ages else None,
            p50_age_hours=statistics.median(ages) if ages else None,
        )

    if not per_source:
        return [_row(None, None)]
    return [_row(source, per_source[source]) for source in sorted(per_source)]


def collect_queue_census(
    redis_client: Any,
    *,
    now: datetime | None = None,
) -> list[QueueCensusRow]:
    """Una rilevazione completa: profondità esatte + istogramma del campione."""
    moment = now or datetime.now(timezone.utc)
    queue_depth = int(redis_client.llen(QUEUE_KEY))
    processing_depth = int(redis_client.llen(PROCESSING_KEY))
    dead_letter_depth = int(redis_client.llen(DEAD_LETTER_KEY))
    # L'istogramma delle età riguarda `news:queue`: è lì che la coorte notturna
    # aspetta. Di `news:processing` e `news:dead-letter` interessa la profondità.
    raw_items = sample_queue(redis_client, QUEUE_KEY, queue_depth)
    return build_census_rows(
        raw_items,
        now=moment,
        queue_depth=queue_depth,
        processing_depth=processing_depth,
        dead_letter_depth=dead_letter_depth,
    )


async def persist_queue_census(
    connection: Any,
    rows: Sequence[QueueCensusRow],
    *,
    sampled_at: datetime | None = None,
) -> None:
    """Append puro: ogni campione aggiunge righe, non ne riscrive nessuna."""
    if not rows:
        return
    moment = sampled_at or datetime.now(timezone.utc)
    await connection.executemany(
        """
        INSERT INTO news_queue_census (
            sampled_at, queue_depth, processing_depth, dead_letter_depth,
            source, n_fresh, n_stale, oldest_age_hours, p50_age_hours
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8::double precision,
                $9::double precision)
        """,
        [
            (
                moment,
                row.queue_depth,
                row.processing_depth,
                row.dead_letter_depth,
                row.source,
                row.n_fresh,
                row.n_stale,
                row.oldest_age_hours,
                row.p50_age_hours,
            )
            for row in rows
        ],
    )


@app.task(name="src.workers.news_queue_census.run_news_queue_census")
def run_news_queue_census() -> dict[str, Any]:
    """Beat ogni 5 minuti, 24/7: fuori seduta è il caso interessante, non il rumore."""

    async def _run() -> dict[str, Any]:
        sampled_at = datetime.now(timezone.utc)
        redis_client = Redis.from_url(config.REDIS_URL)
        try:
            rows = collect_queue_census(redis_client, now=sampled_at)
        finally:
            redis_client.close()

        pool = await init_asyncpg_pool()
        async with pool.acquire() as connection:
            await persist_queue_census(connection, rows, sampled_at=sampled_at)

        head = rows[0]
        return {
            "status": "ok",
            "sampled_at": sampled_at.isoformat(),
            "queue_depth": head.queue_depth,
            "processing_depth": head.processing_depth,
            "dead_letter_depth": head.dead_letter_depth,
            "sources": len([row for row in rows if row.source is not None]),
            "sampled": sum(row.n_fresh + row.n_stale for row in rows),
        }

    return run_async(_run())
