"""#544 — censimento della coda news: osservabilità pura, mai consumo.

I tre invarianti che la strumentazione deve rispettare, e che qui sono asseriti
invece che rivisti a vista:

1. la run non muta la coda (nessun LMOVE, nessun DELETE, nessun RPUSH);
2. la classificazione fresh/stale delega a ``_is_stale_news`` di ``sentiment``
   invece di ricopiarne la soglia (regola #169/#467);
3. il campione ha un tetto esplicito, così il censimento non diventa esso stesso
   un carico sulla coda che sta osservando.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from src.workers import sentiment as sentiment_module
from src.workers.news_queue_census import (
    CENSUS_SAMPLE_CAP,
    DEAD_LETTER_KEY,
    PROCESSING_KEY,
    QUEUE_KEY,
    QueueCensusRow,
    collect_queue_census,
    sample_queue,
)


NOW = datetime(2026, 9, 10, 6, 0, tzinfo=timezone.utc)


class ReadOnlyFakeRedis:
    """Redis in-memory con le sole letture usate dal censimento.

    Qualunque altro attributo — ``lmove``, ``delete``, ``rpush``, ``pipeline`` —
    solleva: il test fallisce sul *tentativo* di mutazione, non sul suo effetto.
    """

    def __init__(self, lists: dict[str, list[bytes]]) -> None:
        self._lists = {key: list(values) for key, values in lists.items()}
        self.lrange_calls: list[tuple[str, int, int]] = []
        # Conteggio degli item effettivamente restituiti: si accumula qui invece di
        # rigiocare `lrange_calls` a posteriori, perche' rigiocarla la farebbe
        # crescere mentre la si scorre.
        self.items_read = 0

    def llen(self, key: str) -> int:
        return len(self._lists.get(key, []))

    def lrange(self, key: str, start: int, end: int) -> list[bytes]:
        self.lrange_calls.append((key, start, end))
        data = self._lists.get(key, [])
        size = len(data)
        real_start = start if start >= 0 else max(size + start, 0)
        real_end = end if end >= 0 else size + end
        if real_end < real_start:
            return []
        window = data[real_start : real_end + 1]
        self.items_read += len(window)
        return window

    def snapshot(self) -> dict[str, list[bytes]]:
        return {key: list(values) for key, values in self._lists.items()}

    def __getattr__(self, name: str):  # pragma: no cover - solo per fallire
        raise AssertionError(
            f"il censimento non deve chiamare {name}() sulla coda news"
        )


def _payload(
    *,
    item_id: str,
    source: str = "alpaca_benzinga",
    age_hours: float = 0.5,
    marketaux: bool = False,
) -> bytes:
    published = NOW - timedelta(hours=age_hours)
    data = {
        "id": item_id,
        "body": "corpo",
        "title": "titolo",
        "timestamp": published.isoformat(),
        "source": source,
        "asset_tags": ["AAPL"],
        "url": f"https://example.test/{item_id}",
    }
    if marketaux:
        data["marketaux_sentiment"] = 0.4
    return json.dumps(data).encode()


def _rows_by_source(rows: list[QueueCensusRow]) -> dict[str | None, QueueCensusRow]:
    return {row.source: row for row in rows}


# ---------------------------------------------------------------- (a) no mutation


def test_la_run_non_muta_la_coda() -> None:
    redis_client = ReadOnlyFakeRedis(
        {
            QUEUE_KEY: [_payload(item_id=f"n{i}", age_hours=i) for i in range(12)],
            PROCESSING_KEY: [_payload(item_id="p0")],
            DEAD_LETTER_KEY: [b"{corrotto", b"{anche questo"],
        }
    )
    before_lengths = {
        key: redis_client.llen(key)
        for key in (QUEUE_KEY, PROCESSING_KEY, DEAD_LETTER_KEY)
    }
    before_content = redis_client.snapshot()

    rows = collect_queue_census(redis_client, now=NOW)

    assert rows, "il censimento deve produrre almeno una riga"
    after_lengths = {
        key: redis_client.llen(key)
        for key in (QUEUE_KEY, PROCESSING_KEY, DEAD_LETTER_KEY)
    }
    assert after_lengths == before_lengths
    assert redis_client.snapshot() == before_content


def test_le_profondita_vengono_da_llen_sulle_tre_chiavi() -> None:
    redis_client = ReadOnlyFakeRedis(
        {
            QUEUE_KEY: [_payload(item_id=f"n{i}") for i in range(7)],
            PROCESSING_KEY: [_payload(item_id="p0"), _payload(item_id="p1")],
            DEAD_LETTER_KEY: [b"{corrotto"],
        }
    )

    rows = collect_queue_census(redis_client, now=NOW)

    assert all(row.queue_depth == 7 for row in rows)
    assert all(row.processing_depth == 2 for row in rows)
    assert all(row.dead_letter_depth == 1 for row in rows)


def test_istogramma_per_sorgente_con_eta_e_mediana() -> None:
    redis_client = ReadOnlyFakeRedis(
        {
            QUEUE_KEY: [
                _payload(item_id="a1", source="alpaca_benzinga", age_hours=0.5),
                _payload(item_id="a2", source="alpaca_benzinga", age_hours=1.0),
                _payload(item_id="a3", source="alpaca_benzinga", age_hours=9.0),
                _payload(item_id="g1", source="gdelt_gkg", age_hours=4.0),
            ],
        }
    )

    rows = _rows_by_source(collect_queue_census(redis_client, now=NOW))

    alpaca = rows["alpaca_benzinga"]
    assert (alpaca.n_fresh, alpaca.n_stale) == (2, 1)
    assert alpaca.oldest_age_hours == pytest.approx(9.0)
    assert alpaca.p50_age_hours == pytest.approx(1.0)

    gdelt = rows["gdelt_gkg"]
    assert (gdelt.n_fresh, gdelt.n_stale) == (0, 1)
    assert gdelt.oldest_age_hours == pytest.approx(4.0)


def test_timestamp_naive_letto_come_utc() -> None:
    """Stessa convenzione tz di ``_is_stale_news``: naive == UTC, non locale."""
    naive = (NOW - timedelta(hours=0.5)).replace(tzinfo=None)
    data = {
        "id": "naive",
        "body": "corpo",
        "timestamp": naive.isoformat(),
        "source": "alpaca_benzinga",
    }
    redis_client = ReadOnlyFakeRedis({QUEUE_KEY: [json.dumps(data).encode()]})

    row = collect_queue_census(redis_client, now=NOW)[0]

    assert row.n_fresh == 1
    assert row.oldest_age_hours == pytest.approx(0.5)


# -------------------------------------------------- (b) la soglia resta una sola


def test_la_soglia_patchata_cambia_il_conteggio(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prova che la soglia è letta da ``sentiment``, non ridichiarata qui."""
    redis_client = ReadOnlyFakeRedis(
        {QUEUE_KEY: [_payload(item_id=f"n{i}", age_hours=6.0) for i in range(3)]}
    )

    baseline = collect_queue_census(redis_client, now=NOW)[0]
    assert (baseline.n_fresh, baseline.n_stale) == (0, 3)

    monkeypatch.setattr(sentiment_module, "_SENTIMENT_MAX_NEWS_AGE_HOURS", 24.0)
    patched = collect_queue_census(redis_client, now=NOW)[0]

    assert (patched.n_fresh, patched.n_stale) == (3, 0)


def test_la_classificazione_delega_a_is_stale_news(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Se il predicato importato cambia, il censimento cambia con lui."""
    redis_client = ReadOnlyFakeRedis(
        {QUEUE_KEY: [_payload(item_id=f"n{i}", age_hours=0.1) for i in range(4)]}
    )
    assert collect_queue_census(redis_client, now=NOW)[0].n_stale == 0

    monkeypatch.setattr(
        sentiment_module, "_is_stale_news", lambda item, now, max_age_hours=2: True
    )
    row = collect_queue_census(redis_client, now=NOW)[0]

    assert (row.n_fresh, row.n_stale) == (0, 4)


# ------------------------------------------------------------- (c) tetto campione


def test_campionamento_rispetta_il_tetto() -> None:
    depth = 1300
    redis_client = ReadOnlyFakeRedis(
        {QUEUE_KEY: [_payload(item_id=f"n{i}") for i in range(depth)]}
    )

    rows = collect_queue_census(redis_client, now=NOW)

    assert CENSUS_SAMPLE_CAP == 500
    row = rows[0]
    assert row.queue_depth == depth, "la profondità resta esatta: viene da LLEN"
    assert row.n_fresh + row.n_stale == CENSUS_SAMPLE_CAP
    assert redis_client.items_read == CENSUS_SAMPLE_CAP, (
        "il censimento deve leggere al piu' il tetto, non l'intera coda"
    )


def test_il_campione_prende_testa_e_coda() -> None:
    depth = 1300
    items = [_payload(item_id=f"n{i}") for i in range(depth)]
    redis_client = ReadOnlyFakeRedis({QUEUE_KEY: items})

    sampled = sample_queue(redis_client, QUEUE_KEY, depth)

    assert len(sampled) == CENSUS_SAMPLE_CAP
    assert sampled[0] == items[0], "manca la testa (gli item più vecchi)"
    assert sampled[-1] == items[-1], "manca la coda (gli item più recenti)"


def test_coda_sotto_al_tetto_letta_per_intero_senza_duplicati() -> None:
    items = [_payload(item_id=f"n{i}") for i in range(9)]
    redis_client = ReadOnlyFakeRedis({QUEUE_KEY: items})

    sampled = sample_queue(redis_client, QUEUE_KEY, len(items))

    assert sampled == items


# ------------------------------------------------------------- casi degeneri


def test_item_non_parseabile_scartato_dal_campione() -> None:
    """Non è un drop: esce dal campione e non gonfia né fresh né stale."""
    redis_client = ReadOnlyFakeRedis(
        {
            QUEUE_KEY: [
                _payload(item_id="buono", age_hours=0.2),
                b"{non-json",
                json.dumps({"id": "senza-body"}).encode(),
            ]
        }
    )

    rows = collect_queue_census(redis_client, now=NOW)

    assert len(rows) == 1
    assert (rows[0].n_fresh, rows[0].n_stale) == (1, 0)
    assert rows[0].queue_depth == 3, "la profondità resta quella vera"


def test_coda_vuota_produce_comunque_la_riga_di_profondita() -> None:
    """Senza questa riga la serie avrebbe buchi proprio quando la coda è a zero."""
    redis_client = ReadOnlyFakeRedis({QUEUE_KEY: [], PROCESSING_KEY: []})

    rows = collect_queue_census(redis_client, now=NOW)

    assert len(rows) == 1
    row = rows[0]
    assert row.source is None
    assert (row.n_fresh, row.n_stale) == (0, 0)
    assert row.oldest_age_hours is None and row.p50_age_hours is None
    assert row.queue_depth == 0


def test_marketaux_conta_come_la_sua_sorgente() -> None:
    redis_client = ReadOnlyFakeRedis(
        {
            QUEUE_KEY: [
                _payload(item_id="m1", source="marketaux", marketaux=True),
                _payload(item_id="m2", source="marketaux", marketaux=True, age_hours=8),
            ]
        }
    )

    row = _rows_by_source(collect_queue_census(redis_client, now=NOW))["marketaux"]

    assert (row.n_fresh, row.n_stale) == (1, 1)


def test_sorgente_vuota_etichettata_unknown() -> None:
    redis_client = ReadOnlyFakeRedis({QUEUE_KEY: [_payload(item_id="x", source="")]})

    row = collect_queue_census(redis_client, now=NOW)[0]

    assert row.source == "unknown"


def test_il_modulo_non_chiama_nessuna_primitiva_di_consumo() -> None:
    """Controllo statico: il fake copre il percorso eseguito, questo l'intero file.

    ``ReadOnlyFakeRedis`` fallisce se il censimento *chiama* una mutazione, ma solo
    sui rami che il test percorre. La regola e' piu' forte — nessuna primitiva di
    consumo deve comparire nel modulo, nemmeno in un ramo raro — quindi si ispeziona
    l'AST, non il testo (che nei commenti le nomina proprio per vietarle).
    """
    import ast
    import inspect

    from src.workers import news_queue_census

    vietate = {
        "lmove", "blmove", "rpoplpush", "brpoplpush",
        "lpop", "rpop", "blpop", "brpop",
        "ltrim", "lset", "lrem", "lpush", "rpush", "delete", "expire",
    }
    albero = ast.parse(inspect.getsource(news_queue_census))
    chiamate = {
        nodo.func.attr
        for nodo in ast.walk(albero)
        if isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Attribute)
    }

    assert not (chiamate & vietate), (
        f"il censimento non deve consumare la coda: {sorted(chiamate & vietate)}"
    )
    # Controprova: l'ispezione vede davvero le letture attese.
    assert {"llen", "lrange"} <= chiamate


# ------------------------------------------------------------------ beat 24/7


def test_beat_ogni_5_minuti_senza_finestra_oraria() -> None:
    from src.workers.celery_app import app

    entry = app.conf.beat_schedule["news-queue-census"]

    assert entry["task"] == "src.workers.news_queue_census.run_news_queue_census"
    schedule = entry["schedule"]
    assert schedule.minute == {0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55}
    # La notte è la parte interessante: nessun vincolo di ora né di giorno.
    assert schedule.hour == set(range(24))
    assert schedule.day_of_week == set(range(7))
    # Task leggero: non deve contendere worker-inference (concurrency=1).
    assert entry.get("options", {}).get("queue") != "inference"
