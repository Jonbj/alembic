"""Consumo shadow off-session della coda news — il controfattuale (#432, Opzione C).

Risponde a **una** domanda, pre-registrata in
`docs/evidence/PREREGISTRAZIONE_offsession_shadow_2026-09-10.md` prima del primo
run: delle news che oggi vengono scartate come stale fuori seduta, quante
avrebbero prodotto `|score| > 0,30` e qual e' il loro forward return a D+1?
Serve a decidere l'Opzione D il 2026-09-28 con un numero invece che con
un'intuizione. L'esito piu' probabile e' `INSUFFICIENT_N`, ed e' dichiarato tale
nella pre-registrazione perche' non venga riletto come una scoperta.

## Perimetro (deroga in carta, 2026-09-10)

Scrive **una sola tabella**: `sentiment_signals_offsession_shadow` (migrazione
068). Zero scritture su `sentiment_signals`, `news_log` e zero scritture via
`RedisStore` — niente cache dei segnali, niente contatori di fallback, niente
storia dei segnali. Il perimetro non e' affidato alla revisione a vista: e'
asserito da `tests/workers/test_sentiment_shadow.py`, che fallisce a ogni
scrittura live.

## La coda non viene consumata

`LRANGE`, **mai** `LMOVE`, mai `RPUSH`, mai `delete("news:processing")`. Gli item
gia' scorati sono marcati per `item_id` nel set Redis `shadow:processed:<notte>`
(TTL 36h) — le uniche chiavi Redis che questo worker scrive, tutte sotto il
prefisso `shadow:`, nessuna letta dal path live.

Marcatura **prima** dello scoring, non dopo: un item che fa esplodere
l'inferenza brucerebbe altrimenti budget LLM reale a ogni run successivo. La
conseguenza — un crash perde quell'item dal campione — e' il verso giusto in cui
sbagliare per una misura con un tetto di spesa.

## Contesa e scadenza

Il beat gira sulla coda `inference` **fuori** dalla finestra del beat live
(`sentiment-worker`, hour="14-21", ultima accensione 21:45Z): il primo turno
shadow e' alle 22:15Z, l'ultimo alle 12:15Z. La finestra di apertura e' la piu' preziosa che
il sistema abbia e `worker-inference` ha concurrency=1: la scadenza delle 13:15Z
e' quindi **dura** (`asyncio.wait_for`), non una speranza riposta nella durata
media di un turno. Un turno troncato dalla scadenza e' un troncamento del
campione dichiarato in pre-registrazione, non un errore.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import date, datetime, time, timedelta, timezone

import psycopg2
from redis import Redis

from src.config import config
from src.models.news import MarketAuxNewsItem, NewsItem
from src.store.pg_store import PostgreSQLStore
from src.store.redis_store import RedisStore
from src.workers.celery_app import app
from src.workers.market_clock import is_market_open
from src.workers.sentiment import (
    _SENTIMENT_BATCH_SIZE,
    _filter_neutral_items,
    build_inference_context,
    process_news_batch,
)

log = logging.getLogger(__name__)

# Tetto di inference per notte, dichiarato in pre-registrazione (§2). Raggiunto
# il tetto il turno esce e riprende la notte successiva: il controfattuale non
# puo' diventare la voce di spesa dominante del sistema.
SHADOW_MAX_PER_NIGHT = int(os.environ.get("SENTIMENT_SHADOW_MAX_PER_NIGHT", "200"))

# Scadenza dura in UTC. Oltre questo istante il turno si interrompe qualunque sia
# il suo stato: alle 13:30Z (apertura NYSE in EDT) `worker-inference` deve essere
# libero. Vedi il modulo-docstring.
SHADOW_DEADLINE_UTC = time(13, 15)

# Ora UTC da cui inizia una "notte": i run dalle 21:00Z del giorno D alle 13:15Z
# del giorno D+1 appartengono alla stessa notte D — la stessa coorte che la
# pre-registrazione (§1) dichiara accumularsi in coda dalle 21:00Z. Tetto e set
# di de-duplica usano questa chiave, altrimenti il tetto si azzererebbe a
# mezzanotte nel mezzo di un turno.
SHADOW_NIGHT_START_HOUR_UTC = 21

# TTL del set di marcatura: copre la notte piu' lunga (21:15Z -> 13:15Z = 16h)
# con margine abbondante, e scade da solo senza bisogno di pulizia.
SHADOW_PROCESSED_TTL_S = 36 * 3600

# Quanti item leggere dalla coda per run. Speculare a `_MAX_QUEUE_SCAN_PER_RUN`
# del path live: la coda notturna arriva a qualche migliaio di item e un LRANGE
# 0 -1 su tutta la lista sarebbe esso stesso un carico.
SHADOW_QUEUE_SCAN_CAP = 5000

_QUEUE_KEY = "news:queue"


def shadow_night_key(now: datetime) -> str:
    """Etichetta della notte a cui `now` appartiene (`YYYY-MM-DD`, giorno d'inizio)."""
    anchor: date = now.date()
    if now.hour < SHADOW_NIGHT_START_HOUR_UTC:
        anchor = anchor - timedelta(days=1)
    return anchor.isoformat()


def shadow_processed_key(now: datetime) -> str:
    return f"shadow:processed:{shadow_night_key(now)}"


def shadow_deadline_for(now: datetime) -> datetime:
    """Scadenza della notte a cui `now` appartiene: 13:15Z del mattino di quella notte.

    E' ancorata alla **notte** (`shadow_night_key`), non al prossimo 13:15Z di
    calendario. La differenza conta esattamente una volta al giorno ma e' quella
    che serve: alle 13:20Z la notte 21:15Z->13:15Z e' finita, e un run manuale a
    quell'ora deve trovare una scadenza gia' passata e uscire, non ereditare le
    24 ore della notte successiva ed entrare in inferenza a mercato che apre.
    """
    night = date.fromisoformat(shadow_night_key(now))
    return datetime.combine(
        night + timedelta(days=1), SHADOW_DEADLINE_UTC, tzinfo=timezone.utc
    )


def parse_queue_item(raw: bytes | str) -> NewsItem | None:
    """Stessa discriminazione MarketAux/NewsItem del path live. None se illeggibile.

    A differenza del path live NON sposta nulla in `news:dead-letter`: quella e'
    una scrittura sulla coda, e la coda qui e' di sola lettura. Un payload
    illeggibile viene semplicemente saltato — lo scarta comunque il consumatore
    live, che e' il proprietario di quella decisione.
    """
    try:
        data = json.loads(raw)
        return (
            MarketAuxNewsItem(**data)
            if "marketaux_sentiment" in data
            else NewsItem(**data)
        )
    except Exception as exc:
        log.debug("shadow: item di coda non parsabile, saltato: %s", exc)
        return None


class OffSessionShadowSink:
    """Sink del controfattuale: scrive **solo** `sentiment_signals_offsession_shadow`.

    Ha la stessa firma di `LiveSignalSink.persist` e ne prende il posto come
    parametro esplicito di `process_news_item`. Non riceve un `RedisStore`: non
    e' una dimenticanza, e' il perimetro — senza quel riferimento questa classe
    non ha alcun modo di scrivere su Redis, e la cosa e' verificabile leggendo
    il suo `__init__` invece che tutto il suo corpo.

    `shadow_tasks` viene accettato e **ignorato**: lo shadow Stage-2 di confronto
    modelli scrive `llm_shadow_responses`, che e' fuori dal perimetro dichiarato.
    """

    def __init__(self, pg_store: PostgreSQLStore) -> None:
        self.pg_store = pg_store
        self.written = 0

    async def persist(
        self,
        item: NewsItem,
        result,
        raw_outputs,
        shadow_tasks: list | None = None,
    ) -> None:
        published_at = item.timestamp
        if published_at is not None and published_at.tzinfo is None:
            published_at = published_at.replace(tzinfo=timezone.utc)
        self.pg_store.write_offsession_shadow_signal(
            item_id=item.id,
            symbol=result.symbol,
            score=result.score,
            model=result.model_id,
            fallback_used=bool(result.fallback_used),
            published_at=published_at,
            scored_at=result.generated_at or datetime.now(timezone.utc),
            raw_item=_raw_item_of(item),
        )
        self.written += 1


def _raw_item_of(item: NewsItem) -> dict | None:
    """Rappresentazione JSON-safe dell'item, per poter ricalcolare il controfattuale.

    Serve a rispondere a una domanda diversa (per esempio con un altro prompt)
    senza dipendere dalla coda Redis, che a quel punto e' da tempo consumata o
    scaduta. Fail-soft: un item non serializzabile perde il grezzo, non la riga.
    """
    try:
        return json.loads(item.model_dump_json())
    except Exception as exc:
        log.debug("shadow: raw_item non serializzabile per %s: %s", item.id, exc)
        return None


def collect_unprocessed(
    redis_client,
    processed_key: str,
    budget: int,
    scan_cap: int = SHADOW_QUEUE_SCAN_CAP,
) -> tuple[list[NewsItem], int, int]:
    """Item della coda non ancora scorati questa notte, senza consumare la coda.

    LRANGE di sola lettura dalla testa (gli item accodati per primi): il tetto
    notturno tronca quindi la coorte **piu' vecchia**, non un campione casuale.
    E' una limitazione nota, dichiarata in pre-registrazione §2, e non va
    "corretta" a posteriori scegliendo un altro ordinamento.

    Il pre-filtro MarketAux (`_filter_neutral_items`, la funzione del path live)
    e' applicato **dentro** la scansione, non dopo: il tetto notturno e' un
    budget di *inferenza*, e un item near-neutral non costa inferenza. Filtrarlo
    a valle avrebbe l'effetto opposto a quello voluto — una testa di coda fatta
    di piu' di `budget` item neutri verrebbe riletta identica a ogni turno, tutti
    scartati, e il worker non arriverebbe **mai** agli item scorabili dietro di
    essa (i neutri non vengono marcati, perche' marcarli consumerebbe il tetto).

    Restituisce (item, n_gia_processati, n_neutri_saltati).
    """
    if budget <= 0:
        return [], 0, 0
    raws = redis_client.lrange(_QUEUE_KEY, 0, scan_cap - 1)
    items: list[NewsItem] = []
    already = 0
    neutral = 0
    for raw in raws:
        if len(items) >= budget:
            break
        item = parse_queue_item(raw)
        if item is None:
            continue
        if redis_client.sismember(processed_key, item.id):
            already += 1
            continue
        # `discard_rows=None`: `news_queue_drops` e' fuori perimetro (§6).
        kept, skipped = _filter_neutral_items([item], discard_rows=None)
        if skipped:
            neutral += 1
            continue
        items.append(kept[0])
    return items, already, neutral


@app.task(name="src.workers.sentiment_shadow.run_sentiment_shadow_worker")
def run_sentiment_shadow_worker() -> dict:
    """Turno shadow off-session. Vedi il docstring del modulo per il perimetro."""
    now = datetime.now(timezone.utc)

    # Guardia di seduta al contrario, fail-closed: il beat gia' parte solo a
    # partire dalle 22:15Z, ma un run manuale o un beat mal configurato non deve
    # poter contendere `worker-inference` a mercato aperto.
    if is_market_open():
        log.info("shadow: mercato aperto — turno off-session saltato")
        return {"skipped": True, "reason": "market_open"}

    deadline = shadow_deadline_for(now)
    if now >= deadline:
        log.info("shadow: scadenza %s gia' raggiunta — nessun lavoro", deadline)
        return {"skipped": True, "reason": "deadline", "deadline": deadline.isoformat()}

    redis_client = Redis.from_url(config.REDIS_URL)
    pg_conn = psycopg2.connect(config.DATABASE_URL)
    # RedisStore serve solo perche' `build_inference_context` legge da Redis la
    # selezione dei modelli e i pesi LOO-ICIR — cioe' in **lettura**. Le sue
    # scritture (cache segnali, contatori di fallback, storia) non vengono mai
    # raggiunte, perche' il sink passato a valle non e' `LiveSignalSink`.
    redis_store = RedisStore(redis_client)
    pg_store = PostgreSQLStore(conn=pg_conn)
    processed_key = shadow_processed_key(now)

    budget_tracker = None
    stats = {
        "scored": 0,
        "queued_seen": 0,
        "already_processed": 0,
        "budget_remaining": 0,
        "deadline_hit": False,
        "failed_batches": 0,
        "night": shadow_night_key(now),
    }
    try:
        spent = int(redis_client.scard(processed_key) or 0)
        budget = SHADOW_MAX_PER_NIGHT - spent
        stats["budget_remaining"] = max(budget, 0)
        if budget <= 0:
            log.info(
                "shadow: tetto notturno raggiunto (%d/%d) per la notte %s",
                spent, SHADOW_MAX_PER_NIGHT, stats["night"],
            )
            stats["reason"] = "night_cap_reached"
            return stats

        # Il pre-filtro MarketAux del path live e' dentro `collect_unprocessed`:
        # e' importato e non riscritto, cosi' la coorte shadow coincide con
        # quella che il live avrebbe davvero mandato in inferenza.
        #
        # Il resolver invece NON viene invocato: `resolve_and_log_shadow` scrive
        # `news_resolved_entities`, fuori perimetro. La coorte shadow e' quindi
        # fail-open sull'enforcement NOT_TRADABLE, esattamente come il path live
        # quando il resolver e' indisponibile.
        items, already, skipped_neutral = collect_unprocessed(
            redis_client, processed_key, budget
        )
        stats["already_processed"] = already
        stats["skipped_neutral"] = skipped_neutral
        stats["queued_seen"] = len(items) + already + skipped_neutral
        if not items:
            stats["reason"] = "no_items"
            return stats

        (
            clients,
            aggregator,
            finbert,
            budget_tracker,
            model_weights,
        ) = build_inference_context(redis_store, pg_conn)
        sink = OffSessionShadowSink(pg_store)

        for chunk_start in range(0, len(items), _SENTIMENT_BATCH_SIZE):
            remaining = (deadline - datetime.now(timezone.utc)).total_seconds()
            if remaining <= 0:
                stats["deadline_hit"] = True
                break
            chunk = items[chunk_start : chunk_start + _SENTIMENT_BATCH_SIZE]
            # Marcatura PRIMA dello scoring — vedi il docstring del modulo.
            pipe = redis_client.pipeline()
            pipe.sadd(processed_key, *[i.id for i in chunk])
            pipe.expire(processed_key, SHADOW_PROCESSED_TTL_S)
            pipe.execute()
            try:
                asyncio.run(
                    asyncio.wait_for(
                        process_news_batch(
                            news_items=chunk,
                            clients=clients,
                            aggregator=aggregator,
                            finbert=finbert,
                            budget_tracker=budget_tracker,
                            redis_store=redis_store,
                            pg_store=pg_store,
                            weights=model_weights,
                            sink=sink,
                        ),
                        timeout=remaining,
                    )
                )
            except (asyncio.TimeoutError, TimeoutError):
                stats["deadline_hit"] = True
                log.warning(
                    "shadow: scadenza dura %sZ raggiunta a meta' turno — "
                    "%d item scorati, campione troncato",
                    SHADOW_DEADLINE_UTC.isoformat(), sink.written,
                )
                break
            except Exception as exc:
                # Un lotto che esplode (modello, rete, payload) non deve costare
                # l'intero turno: gli item sono gia' marcati, quindi il lotto e'
                # perso dal campione e il turno prosegue con i successivi. Il
                # conteggio e' pubblicato in stats — un tasso di errore alto e'
                # un dato sulla disponibilita' notturna, non un dettaglio da log.
                stats["failed_batches"] = stats.get("failed_batches", 0) + 1
                log.warning(
                    "shadow: lotto di %d item fallito (%s) — turno prosegue",
                    len(chunk), exc,
                )
                continue

        stats["scored"] = sink.written
        stats["budget_remaining"] = max(
            SHADOW_MAX_PER_NIGHT - int(redis_client.scard(processed_key) or 0), 0
        )
        log.info(
            "shadow: notte %s — %d item scorati, %d gia' visti, tetto residuo %d%s",
            stats["night"], stats["scored"], already, stats["budget_remaining"],
            " (scadenza)" if stats["deadline_hit"] else "",
        )
        return stats
    finally:
        if budget_tracker is not None:
            budget_tracker.close()
        redis_store.close()
        pg_store.close()
        redis_client.close()
        pg_conn.close()
