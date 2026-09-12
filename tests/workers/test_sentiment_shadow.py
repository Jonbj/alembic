"""Il perimetro del consumo shadow off-session e' asserito qui, non a vista (#432, C).

La deroga registrata in `docs/evidence/OBSERVATION_CHARTER.md` promette che il
turno notturno scrive **solo** `sentiment_signals_offsession_shadow`. Questi test
sono quella promessa: qualunque scrittura su `sentiment_signals`, `news_log` o via
`RedisStore`, e qualunque consumo della coda, fa fallire la suite.

Il punto delicato e' che i test esercitano la pipeline **vera** — `process_news_batch`
-> `process_news_item` -> sink — con la sola inferenza sostituita. Un test che
sostituisse anche `process_news_batch` verificherebbe il proprio mock, non il
perimetro.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from src.models.news import MarketAuxNewsItem, NewsItem
from src.models.signals import SentimentResult
from src.workers import sentiment_shadow as shadow
from src.workers.sentiment_shadow import (
    SHADOW_DEADLINE_UTC,
    SHADOW_MAX_PER_NIGHT,
    SHADOW_PROCESSED_TTL_S,
    OffSessionShadowSink,
    collect_unprocessed,
    run_sentiment_shadow_worker,
    shadow_deadline_for,
    shadow_night_key,
)

# Un istante notturno reale: 23:15Z, dentro la fascia del beat, prima della scadenza.
_NIGHT = datetime(2026, 9, 11, 23, 15, tzinfo=timezone.utc)

# Ogni metodo di RedisStore che scrive. Se ne compare uno nuovo va aggiunto qui:
# la lista e' volutamente esplicita perche' un `assert not mock.called` generico
# passerebbe anche sulle letture, e le letture (modelli attivi, pesi) servono.
_REDIS_STORE_WRITES = (
    "write_sentiment",
    "append_signal_history",
    "increment_fallback_counter",
    "reset_fallback_counter",
    "set_llm_models",
    "reset_fallback_alert_flag",
)

# Ogni scrittura di PostgreSQLStore che il path live esegue per un segnale.
_PG_LIVE_WRITES = (
    "write_signal",
    "log_news_item",
    "link_signal_to_news",
    "log_llm_responses",
    "log_shadow_responses",
    "record_fallback_increment",
    "record_fallback_reset",
    "record_news_discards",
    "record_news_queue_drops",
    "record_ingestion_stats",
    "write_resolved_entity",
)

# I soli attributi che il path shadow puo' toccare sui due store. E' questo —
# non le liste qui sopra — il guardiano vero del perimetro: una denylist di nomi
# resta muta su un metodo aggiunto domani, una allowlist no. Le denylist restano
# perche' dicono *quali* scritture live esistono, e falliscono con un messaggio
# leggibile invece che con un nome generico.
_PG_SHADOW_ALLOWED = {"write_offsession_shadow_signal", "close"}
_REDIS_STORE_ALLOWED = {
    "get_llm_models",
    "get_ensemble_weights",
    "get_weight_suggestion",
    "close",
}


def _attributi_chiamati(mock: MagicMock) -> set[str]:
    """Nomi di primo livello effettivamente invocati su un MagicMock."""
    return {c[0].split(".")[0] for c in mock.mock_calls if c[0]}

# Ogni comando Redis che consuma o muta la coda. LRANGE non c'e': e' di sola lettura.
_QUEUE_MUTATIONS = ("lmove", "lpop", "rpop", "blpop", "brpop", "rpush", "lpush", "lrem")


def _item(idx: int, ts: datetime | None = None) -> NewsItem:
    return NewsItem(
        id=f"item-{idx}",
        body=f"corpo {idx}",
        title=f"titolo {idx}",
        timestamp=ts or (_NIGHT - timedelta(hours=6)),
        source="alpaca_benzinga",
        asset_tags=["AAPL"],
        url=f"https://example.test/{idx}",
    )


def _marketaux_item(idx: int, sentiment: float) -> MarketAuxNewsItem:
    return MarketAuxNewsItem(
        **_item(idx).model_dump(), marketaux_sentiment=sentiment
    )


def _result(symbol: str = "AAPL", score: float = 0.42) -> SentimentResult:
    return SentimentResult(
        symbol=symbol,
        score=score,
        confidence=0.8,
        reasoning="test",
        model_id="glm52+gptoss",
        generated_at=_NIGHT,
    )


class _FakeRedis:
    """Redis abbastanza reale da poter fallire: registra ogni comando ricevuto."""

    def __init__(self, queue: list[NewsItem], processed: set[str] | None = None):
        self.queue = [i.model_dump_json() for i in queue]
        self.sets: dict[str, set[str]] = {}
        if processed:
            self.sets["preset"] = set(processed)
        self._preset = set(processed or ())
        self.calls: list[str] = []
        self.expires: dict[str, int] = {}
        self.closed = False

    def _rec(self, name):
        self.calls.append(name)

    def lrange(self, key, start, end):
        self._rec("lrange")
        return self.queue[start : (None if end == -1 else end + 1)]

    def sismember(self, key, member):
        self._rec("sismember")
        return member in self.sets.get(key, set()) or member in self._preset

    def sadd(self, key, *members):
        self._rec("sadd")
        self.sets.setdefault(key, set()).update(members)
        return len(members)

    def scard(self, key):
        self._rec("scard")
        return len(self.sets.get(key, set()) | self._preset)

    def expire(self, key, ttl):
        self._rec("expire")
        self.expires[key] = ttl
        return True

    def pipeline(self):
        return _FakePipeline(self)

    def close(self):
        self.closed = True

    def __getattr__(self, name):
        # Qualunque comando non implementato sopra (lmove, rpush, delete, ...) viene
        # registrato e poi fallisce il test tramite _QUEUE_MUTATIONS / assert espliciti.
        def _unexpected(*a, **k):
            self.calls.append(name)
            return None
        return _unexpected


class _FakePipeline:
    def __init__(self, r: _FakeRedis):
        self._r = r
        self._ops: list = []

    def sadd(self, key, *members):
        self._ops.append(lambda: self._r.sadd(key, *members))
        return self

    def expire(self, key, ttl):
        self._ops.append(lambda: self._r.expire(key, ttl))
        return self

    def execute(self):
        return [op() for op in self._ops]


def _run_task(
    *,
    queue: list[NewsItem],
    now: datetime = _NIGHT,
    processed: set[str] | None = None,
    market_open: bool = False,
    inference=None,
    batch_delay: float = 0.0,
):
    """Esegue il task con connessioni finte, pipeline vera, inferenza sostituita."""
    fake_redis = _FakeRedis(queue, processed=processed)
    redis_store = MagicMock()
    pg_store = MagicMock()
    finbert = MagicMock()
    budget_tracker = MagicMock()

    async def _fake_inference(item, clients, aggregator, fb, bt, weights=None):
        if batch_delay:
            await asyncio.sleep(batch_delay)
        if inference is not None:
            return inference(item)
        return _result(), []

    class _Clock(datetime):
        pass

    with patch.object(shadow, "Redis") as mock_redis_cls, \
         patch.object(shadow, "psycopg2") as mock_pg, \
         patch.object(shadow, "RedisStore", return_value=redis_store), \
         patch.object(shadow, "PostgreSQLStore", return_value=pg_store), \
         patch.object(shadow, "is_market_open", return_value=market_open), \
         patch.object(
             shadow,
             "build_inference_context",
             return_value=([MagicMock()], MagicMock(), finbert, budget_tracker, None),
         ), \
         patch("src.workers.sentiment.run_inference", side_effect=_fake_inference), \
         patch.object(shadow, "datetime", _Clock):
        mock_redis_cls.from_url.return_value = fake_redis
        mock_pg.connect.return_value = MagicMock()
        _Clock.now = staticmethod(lambda tz=None: now)
        result = run_sentiment_shadow_worker()
    return result, fake_redis, redis_store, pg_store


# --------------------------------------------------------------------------
# Perimetro: zero scritture live
# --------------------------------------------------------------------------

def test_nessuna_scrittura_live_ne_su_redis_ne_su_postgres():
    stats, fake_redis, redis_store, pg_store = _run_task(queue=[_item(i) for i in range(3)])

    assert stats["scored"] == 3

    for name in _REDIS_STORE_WRITES:
        assert not getattr(redis_store, name).called, (
            f"scrittura live su Redis vietata nel path shadow: RedisStore.{name}"
        )
    for name in _PG_LIVE_WRITES:
        assert not getattr(pg_store, name).called, (
            f"scrittura live vietata nel path shadow: PostgreSQLStore.{name}"
        )
    assert pg_store.write_offsession_shadow_signal.call_count == 3

    # La rete a maglia stretta: nulla al di fuori dell'allowlist e' stato toccato.
    assert _attributi_chiamati(pg_store) <= _PG_SHADOW_ALLOWED
    assert _attributi_chiamati(redis_store) <= _REDIS_STORE_ALLOWED


def test_le_denylist_del_perimetro_nominano_metodi_che_esistono_davvero():
    """Un nome sbagliato in denylist e' un assert che passa sempre: qui si rompe."""
    from src.store.pg_store import PostgreSQLStore
    from src.store.redis_store import RedisStore

    for name in _PG_LIVE_WRITES:
        assert hasattr(PostgreSQLStore, name), f"PostgreSQLStore.{name} non esiste piu'"
    for name in _REDIS_STORE_WRITES:
        assert hasattr(RedisStore, name), f"RedisStore.{name} non esiste piu'"
    for name in _PG_SHADOW_ALLOWED | _REDIS_STORE_ALLOWED - {"close"}:
        assert hasattr(PostgreSQLStore, name) or hasattr(RedisStore, name), name


def test_scrive_solo_la_tabella_shadow_con_i_campi_attesi():
    item = _item(1)
    _, _, _, pg_store = _run_task(queue=[item])

    kwargs = pg_store.write_offsession_shadow_signal.call_args.kwargs
    assert kwargs["item_id"] == item.id
    assert kwargs["symbol"] == "AAPL"
    assert kwargs["score"] == pytest.approx(0.42)
    assert kwargs["model"] == "glm52+gptoss"
    assert kwargs["fallback_used"] is False
    assert kwargs["published_at"] == item.timestamp
    assert kwargs["raw_item"]["id"] == item.id


def test_la_coda_non_viene_consumata():
    queue = [_item(i) for i in range(3)]
    _, fake_redis, _, _ = _run_task(queue=queue)

    assert "lrange" in fake_redis.calls
    for cmd in _QUEUE_MUTATIONS:
        assert cmd not in fake_redis.calls, f"la coda shadow e' di sola lettura: {cmd}"
    assert "delete" not in fake_redis.calls
    # La lista e' ancora integra: nessun item e' sparito.
    assert len(fake_redis.queue) == 3


def test_lo_stage2_di_confronto_modelli_non_viene_dispatchato():
    # _shadow_query_candidates scrive llm_shadow_responses: fuori perimetro.
    with patch("src.workers.sentiment._shadow_query_candidates") as stage2:
        _run_task(queue=[_item(1)])
    assert not stage2.called


# --------------------------------------------------------------------------
# Tetto notturno
# --------------------------------------------------------------------------

def test_tetto_notturno_esaurito_non_esegue_inferenza():
    processed = {f"vecchio-{i}" for i in range(SHADOW_MAX_PER_NIGHT)}
    stats, _, _, pg_store = _run_task(queue=[_item(1)], processed=processed)

    assert stats["reason"] == "night_cap_reached"
    assert stats["scored"] == 0
    assert not pg_store.write_offsession_shadow_signal.called


def test_tetto_notturno_tronca_il_lotto_al_residuo():
    residuo = 4
    processed = {f"vecchio-{i}" for i in range(SHADOW_MAX_PER_NIGHT - residuo)}
    stats, _, _, pg_store = _run_task(
        queue=[_item(i) for i in range(20)], processed=processed
    )

    assert stats["scored"] == residuo
    assert pg_store.write_offsession_shadow_signal.call_count == residuo


def test_gli_item_gia_scorati_non_vengono_ripagati():
    queue = [_item(i) for i in range(4)]
    stats, _, _, pg_store = _run_task(queue=queue, processed={"item-0", "item-2"})

    assert stats["already_processed"] == 2
    assert stats["scored"] == 2
    scored_ids = {
        c.kwargs["item_id"] for c in pg_store.write_offsession_shadow_signal.call_args_list
    }
    assert scored_ids == {"item-1", "item-3"}


def test_marcatura_prima_dello_scoring_con_ttl_36h():
    """Un item che fa esplodere l'inferenza non deve ripagarsi ogni notte."""
    def _boom(item):
        raise RuntimeError("modello esploso")

    stats, fake_redis, _, pg_store = _run_task(queue=[_item(1)], inference=_boom)

    key = shadow.shadow_processed_key(_NIGHT)
    assert "item-1" in fake_redis.sets[key], "marcato solo dopo lo scoring: budget a rischio"
    assert fake_redis.expires[key] == SHADOW_PROCESSED_TTL_S == 36 * 3600
    assert not pg_store.write_offsession_shadow_signal.called


def test_la_notte_e_una_sola_chiave_a_cavallo_della_mezzanotte():
    sera = datetime(2026, 9, 11, 22, 30, tzinfo=timezone.utc)
    mattina = datetime(2026, 9, 12, 5, 30, tzinfo=timezone.utc)
    assert shadow_night_key(sera) == shadow_night_key(mattina) == "2026-09-11"
    # Le 20:00Z sono ancora la notte precedente (il beat non gira, ma la chiave
    # deve restare monotona se un run manuale ci capita dentro).
    assert shadow_night_key(datetime(2026, 9, 12, 20, 0, tzinfo=timezone.utc)) == "2026-09-11"


# --------------------------------------------------------------------------
# Scadenza dura
# --------------------------------------------------------------------------

def test_dopo_la_scadenza_il_turno_non_parte():
    tardi = datetime(2026, 9, 12, 13, 20, tzinfo=timezone.utc)
    stats, _, _, pg_store = _run_task(queue=[_item(1)], now=tardi)

    assert stats["skipped"] is True
    assert stats["reason"] == "deadline"
    assert not pg_store.write_offsession_shadow_signal.called


def test_scadenza_dura_interrompe_un_turno_gia_iniziato():
    # 13:14:59Z: un secondo di margine, poi il wait_for taglia il lotto in corso.
    quasi = datetime(2026, 9, 12, 13, 14, 59, tzinfo=timezone.utc)
    stats, _, _, pg_store = _run_task(
        queue=[_item(i) for i in range(3)], now=quasi, batch_delay=5.0
    )

    assert stats["deadline_hit"] is True
    assert not pg_store.write_offsession_shadow_signal.called


def test_la_scadenza_e_1315z_e_il_giorno_successivo_se_gia_passata():
    assert SHADOW_DEADLINE_UTC.hour == 13 and SHADOW_DEADLINE_UTC.minute == 15
    prima = datetime(2026, 9, 12, 2, 0, tzinfo=timezone.utc)
    assert shadow_deadline_for(prima) == datetime(2026, 9, 12, 13, 15, tzinfo=timezone.utc)
    dopo = datetime(2026, 9, 12, 22, 0, tzinfo=timezone.utc)
    assert shadow_deadline_for(dopo) == datetime(2026, 9, 13, 13, 15, tzinfo=timezone.utc)


# --------------------------------------------------------------------------
# Contesa con il path live
# --------------------------------------------------------------------------

def test_mercato_aperto_il_turno_non_parte():
    stats, _, _, pg_store = _run_task(queue=[_item(1)], market_open=True)

    assert stats["skipped"] is True
    assert stats["reason"] == "market_open"
    assert not pg_store.write_offsession_shadow_signal.called


def test_il_beat_non_si_sovrappone_mai_al_beat_live():
    from src.workers.celery_app import app

    entry = app.conf.beat_schedule["sentiment-shadow-offsession"]
    live = app.conf.beat_schedule["sentiment-worker"]
    # Stessa coda, concurrency=1: la sovrapposizione sarebbe contesa vera.
    assert entry["options"]["queue"] == live["options"]["queue"] == "inference"

    ore = set(entry["schedule"].hour)
    # Il riferimento e' l'orario del path live letto dalla config, non un
    # intervallo riscritto a mano: se domani "sentiment-worker" si allarga,
    # questo test se ne accorge invece di restare d'accordo con se stesso.
    ore_live = set(live["schedule"].hour)
    assert ore.isdisjoint(ore_live), "il beat shadow contende worker-inference"
    assert max(ore_live) == 21, "il live arriva fino alle 21:45Z: shadow parte dopo"
    assert min(h for h in ore if h >= 14) == 22

    # L'ultimo turno e' alle 12:15Z: uno alle 13:15Z nascerebbe gia' scaduto.
    assert max(h for h in ore if h < 14) == 12
    assert SHADOW_DEADLINE_UTC.hour not in ore


def test_il_task_e_registrato_nella_app_celery():
    # Un beat che punta a un task non incluso e' un job che non gira mai, e la
    # CI non se ne accorge: il modulo va in `include=` di celery_app.
    from src.workers.celery_app import app

    assert "src.workers.sentiment_shadow" in app.conf.include
    assert "src.workers.sentiment_shadow.run_sentiment_shadow_worker" in app.tasks


# --------------------------------------------------------------------------
# Lettura della coda
# --------------------------------------------------------------------------

def test_collect_unprocessed_rispetta_budget_e_salta_i_gia_visti():
    queue = [_item(i) for i in range(10)]
    r = _FakeRedis(queue, processed={"item-0", "item-1"})
    items, already, neutri = collect_unprocessed(r, "shadow:processed:x", budget=3)

    assert [i.id for i in items] == ["item-2", "item-3", "item-4"]
    assert already == 2
    assert neutri == 0


def test_collect_unprocessed_ignora_i_payload_illeggibili_senza_dead_letter():
    r = _FakeRedis([_item(1)])
    r.queue.insert(0, "{non-json")
    items, _, _ = collect_unprocessed(r, "shadow:processed:x", budget=5)

    assert [i.id for i in items] == ["item-1"]
    assert "rpush" not in r.calls  # niente news:dead-letter: la coda e' di sola lettura


def test_budget_non_positivo_non_legge_nemmeno_la_coda():
    r = _FakeRedis([_item(1)])
    items, already, neutri = collect_unprocessed(r, "shadow:processed:x", budget=0)

    assert items == [] and already == 0 and neutri == 0
    assert "lrange" not in r.calls


def test_una_testa_di_coda_tutta_neutrale_non_blocca_il_turno():
    """I neutri non consumano il tetto: sono gratis e non vengono marcati.

    Se il pre-filtro girasse *dopo* il taglio al budget, una testa di coda di
    piu' di `budget` item neutri verrebbe riletta identica ogni notte e gli item
    scorabili dietro di essa non arriverebbero mai in inferenza.
    """
    neutri = [_marketaux_item(i, sentiment=0.05) for i in range(5)]
    r = _FakeRedis(neutri + [_item(99)])
    items, already, n_neutri = collect_unprocessed(r, "shadow:processed:x", budget=3)

    assert [i.id for i in items] == ["item-99"]
    assert n_neutri == 5
    assert already == 0


def test_gli_item_marketaux_non_neutri_restano_nel_campione():
    r = _FakeRedis([_marketaux_item(1, sentiment=0.65)])
    items, _, n_neutri = collect_unprocessed(r, "shadow:processed:x", budget=3)

    assert [i.id for i in items] == ["item-1"]
    assert n_neutri == 0


# --------------------------------------------------------------------------
# Il sink, isolato
# --------------------------------------------------------------------------

def test_il_sink_non_ha_alcun_riferimento_a_redis():
    sink = OffSessionShadowSink(MagicMock())
    assert not hasattr(sink, "redis_store")


def test_il_sink_normalizza_un_timestamp_naive_a_utc():
    pg_store = MagicMock()
    sink = OffSessionShadowSink(pg_store)
    naive = datetime(2026, 9, 11, 20, 2)
    item = _item(9, ts=naive)

    asyncio.run(sink.persist(item=item, result=_result(), raw_outputs=[]))

    kwargs = pg_store.write_offsession_shadow_signal.call_args.kwargs
    assert kwargs["published_at"] == naive.replace(tzinfo=timezone.utc)


def test_il_sink_ignora_lo_stage2_anche_se_gli_viene_passato():
    pg_store = MagicMock()
    sink = OffSessionShadowSink(pg_store)
    tasks: list = []

    asyncio.run(
        sink.persist(item=_item(1), result=_result(), raw_outputs=[], shadow_tasks=tasks)
    )

    assert tasks == []
