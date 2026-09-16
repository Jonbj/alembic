"""#541: la provenienza di trasporto (WebSocket vs REST) e' persistita per riga.

Oggi i due path scrivono la stessa `source` (`alpaca_benzinga`) e la separazione
WS/REST si **inferisce** dalla latenza `raw_ingested_at - published_at` — che e'
esattamente l'inferenza su cui si e' fermata l'analisi del 2026-09-15
(`docs/research/stale_cohort_fetch_latency_2026-09-15.md` §4.1: il gradino
`already_stale_at_fetch` 18 → 263 del 10/09 resta non attribuito).

Il contratto che questi test presidiano:
  1. il trasporto viaggia con l'item dentro la coda Redis;
  2. lo registra chi **osserva**, non chi ha pubblicato: l'item accodato porta il
     trasporto del primo avvistamento, la riga di scarto quello dell'avvistamento
     che l'ha prodotta;
  3. il dedup **non** e' partizionato per trasporto — il contratto unico di #455
     resta unico, altrimenti WS e REST smetterebbero di deduplicarsi a vicenda e
     ogni articolo entrerebbe due volte nella pipeline.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from src.models.news import NewsItem
from src.workers.news_discards import build_news_discard_row
from src.workers.news_transport import (
    TRANSPORT_REST,
    TRANSPORT_WS,
    TRANSPORTS,
    leggi_trasporto,
    marca_trasporto,
)


def _item(**kwargs) -> NewsItem:
    base = dict(
        id="alpaca:1:AAPL",
        title="Apple raises guidance",
        body="Demand remains strong.",
        url="https://example.test/apple-guidance",
        source="alpaca_benzinga",
        asset_tags=["AAPL"],
        timestamp=datetime(2026, 9, 15, 13, 0, tzinfo=UTC),
    )
    base.update(kwargs)
    return NewsItem(**base)


class FakeRedis:
    """Coda in memoria: raccoglie i payload accodati dal path di ingestione."""

    def __init__(self) -> None:
        self.queue: list[str] = []

    def rpush(self, key: str, payload: str) -> int:
        assert key == "news:queue"
        self.queue.append(payload)
        return len(self.queue)


class FakeDedup:
    """Dedup reale nel comportamento: prima volta passa, poi e' duplicato."""

    def __init__(self) -> None:
        self.visti_per_id: set[str] = set()
        self.visti_per_contenuto: set[tuple[str, str]] = set()

    def is_duplicate_by_id(self, item) -> bool:
        if item.id in self.visti_per_id:
            return True
        self.visti_per_id.add(item.id)
        return False

    def is_duplicate_content_symbol(self, item) -> bool:
        if not item.asset_tags:
            return False
        chiave = (item.title, item.asset_tags[0])
        if chiave in self.visti_per_contenuto:
            return True
        self.visti_per_contenuto.add(chiave)
        return False


# ── 1. Il trasporto attraversa la coda ────────────────────────────────────────


def test_il_trasporto_sopravvive_al_giro_in_coda_redis():
    """L'item e' serializzato su Redis e ricostruito dal worker di sentiment:
    se il campo non e' sul modello, lo scarto `stale` (che nasce li') non puo'
    sapere da dove l'articolo fosse entrato."""
    originale = marca_trasporto(_item(), TRANSPORT_WS)

    ricostruito = NewsItem(**json.loads(originale.model_dump_json()))

    assert ricostruito.transport == TRANSPORT_WS


def test_un_item_non_strumentato_non_dichiara_nessun_trasporto():
    assert _item().transport == ""
    assert leggi_trasporto(_item()) is None


def test_marca_trasporto_rifiuta_una_etichetta_non_prevista():
    """Stretto sul produttore: scrivere un'etichetta ignota in una serie
    pubblicata e' peggio che non scriverla."""
    with pytest.raises(ValueError):
        marca_trasporto(_item(), "sse")


def test_leggi_trasporto_e_permissiva_su_un_payload_gia_in_coda():
    """Permissiva sul consumatore: un payload malformato e' un difetto del
    produttore, non un motivo per far cadere la riga che lo documenterebbe."""
    item = _item()
    item.transport = "carrier-pigeon"

    assert leggi_trasporto(item) is None


def test_i_trasporti_ammessi_sono_solo_i_due_reali():
    assert TRANSPORTS == {"ws", "rest"}


# ── 2. Lo registra chi osserva ────────────────────────────────────────────────


def test_la_riga_di_scarto_registra_il_trasporto_dell_osservazione():
    riga = build_news_discard_row(
        marca_trasporto(_item(), TRANSPORT_REST),
        reason="duplicate_id",
        stage="ingestion",
    )

    assert riga["transport"] == TRANSPORT_REST


def test_la_riga_di_scarto_di_un_item_non_strumentato_scrive_none():
    """NULL = «non lo so», mai un'etichetta di comodo: la serie deve poter
    distinguere lo storico pre-#541 da un articolo davvero arrivato dal REST."""
    riga = build_news_discard_row(_item(), reason="stale", stage="sentiment")

    assert riga["transport"] is None


def test_lo_scarto_stale_porta_il_trasporto_del_primo_avvistamento():
    """E' la riga che serve per attribuire il gradino del 10/09: lo scarto nasce
    nel worker di sentiment, a valle della coda, e l'unica provenienza che ha e'
    quella che l'ingestione gli ha messo sull'item."""
    from src.workers.sentiment import build_stale_drop_row

    item = marca_trasporto(_item(), TRANSPORT_WS)
    item.raw_ingested_at = datetime(2026, 9, 15, 13, 1, tzinfo=UTC)

    riga = build_stale_drop_row(item, datetime(2026, 9, 15, 17, 5, tzinfo=UTC))

    assert riga["transport"] == TRANSPORT_WS


# ── 3. I due path di produzione ───────────────────────────────────────────────


def test_il_path_rest_marca_rest_gli_item_accodati_e_le_righe_di_scarto():
    from src.workers.ingestion import _process_alpaca_items

    redis = FakeRedis()
    dedup = FakeDedup()
    scarti: list[dict] = []

    _process_alpaca_items(
        [_item(id="alpaca:1")],
        dedup,
        redis,
        discard_rows=scarti,
        transport=TRANSPORT_REST,
    )
    accodato = NewsItem(**json.loads(redis.queue[0]))
    assert accodato.transport == TRANSPORT_REST

    _process_alpaca_items(
        [_item(id="alpaca:1")],
        dedup,
        redis,
        discard_rows=scarti,
        transport=TRANSPORT_REST,
    )
    assert [r["transport"] for r in scarti] == [TRANSPORT_REST]


def test_il_worker_rest_dichiara_il_proprio_trasporto():
    """Il default non deve decidere al posto del chiamante: e' il worker REST a
    dire di essere REST."""
    from src.workers import ingestion

    with patch.object(ingestion, "is_market_open", return_value=True), \
         patch.object(ingestion, "Redis") as mock_redis_cls, \
         patch.object(ingestion, "AlpacaNewsConnector"), \
         patch.object(ingestion, "Deduplicator"), \
         patch.object(ingestion.asyncio, "run", return_value=[]), \
         patch.object(ingestion, "_process_alpaca_items") as mock_process, \
         patch.object(ingestion, "_persist_ingestion_observability"), \
         patch.object(ingestion, "config") as mock_config:
        mock_config.ALPACA_API_KEY = "k"
        mock_config.ALPACA_SECRET_KEY = "s"
        mock_config.WATCHLIST_SYMBOLS = ["AAPL"]
        mock_config.REDIS_URL = "redis://redis:6379/0"
        mock_redis_cls.from_url.return_value = MagicMock()
        mock_process.return_value = {"fetched": 0, "queued": 0}

        ingestion.run_alpaca_ingestion_worker.run()

    assert mock_process.call_args.kwargs["transport"] == TRANSPORT_REST


def test_il_path_websocket_dichiara_ws():
    from src.workers.news_stream import _on_news

    article = {
        "id": 123,
        "headline": "Apple raises guidance",
        "summary": "Demand remains strong.",
        "url": "https://example.test/apple-guidance",
        "created_at": datetime(2026, 9, 15, 13, 0, tzinfo=UTC),
        "symbols": ["AAPL"],
    }

    with patch("src.workers.news_stream.config") as mock_config, \
         patch("src.workers.news_stream.Redis") as mock_redis_cls, \
         patch("src.workers.news_stream.Deduplicator"), \
         patch("src.workers.news_stream._process_alpaca_items") as mock_process, \
         patch("src.workers.news_stream._persist_ingestion_observability"), \
         patch("src.workers.news_stream.app.send_task"):
        mock_config.REDIS_URL = "redis://redis:6379/0"
        mock_config.WATCHLIST_SYMBOLS = ["AAPL"]
        mock_redis_cls.from_url.return_value = MagicMock()
        mock_process.return_value = {
            "fetched": 1, "tickers_found": 1, "discarded": 0,
            "queued": 1, "duplicates": 0,
        }

        asyncio.run(_on_news(article))

    assert mock_process.call_args.kwargs["transport"] == TRANSPORT_WS


# ── 4. Il contratto di #455 resta unico ───────────────────────────────────────


def test_il_dedup_non_e_partizionato_per_trasporto():
    """Se il trasporto entrasse nella chiave di dedup, ogni articolo visto dal WS
    verrebbe riaccodato dal primo poll REST: il costo non sarebbe una riga di
    telemetria in piu', sarebbe il doppio della pipeline."""
    from src.connectors.deduplicator import Deduplicator, compute_dedup_hash

    dal_ws = marca_trasporto(_item(), TRANSPORT_WS)
    dal_rest = marca_trasporto(_item(), TRANSPORT_REST)

    assert compute_dedup_hash(dal_ws) == compute_dedup_hash(dal_rest)

    chiavi: dict[str, int] = {}

    class RedisChiavi:
        def set(self, key, value, ex=None, nx=None):
            if key in chiavi:
                return None
            chiavi[key] = 1
            return True

    dedup = Deduplicator(RedisChiavi())
    assert dedup.is_duplicate_by_id(dal_ws) is False
    assert dedup.is_duplicate_by_id(dal_rest) is True


def test_il_payload_accodato_aggiunge_solo_il_campo_trasporto():
    """Il worker di sentiment ricostruisce l'item da questo payload: il contratto
    di coda cresce di un campo e di nessun altro."""
    from src.workers.ingestion import _process_alpaca_items

    redis = FakeRedis()
    _process_alpaca_items(
        [_item(id="alpaca:1")], FakeDedup(), redis,
        discard_rows=[], transport=TRANSPORT_REST,
    )

    chiavi = set(json.loads(redis.queue[0]))
    assert chiavi == {
        "id", "body", "title", "timestamp", "source", "asset_tags", "url",
        "language", "extraction_method", "raw_ingested_at", "transport",
    }


def test_le_statistiche_di_ingestione_non_cambiano_forma():
    from src.workers.ingestion import _process_alpaca_items

    stats = _process_alpaca_items(
        [_item(id="alpaca:1")], FakeDedup(), FakeRedis(),
        discard_rows=[], transport=TRANSPORT_REST,
    )

    assert set(stats) == {"fetched", "tickers_found", "discarded", "queued", "duplicates"}
    assert stats["queued"] == 1


# ── 5. La sottoscrizione attiva va persistita, non inferita ───────────────────


def test_lo_stream_registra_la_propria_sottoscrizione_all_avvio():
    """Il tasso di WS-missed si calcola sui soli simboli sottoscritti: senza
    snapshot, un articolo su un simbolo fuori watchlist sembrerebbe un miss."""
    from src.workers import news_stream

    # `run_news_stream` reimporta `config` nel corpo del task: va patchato
    # alla sorgente, non sull'attributo di modulo.
    with patch("src.config.config") as mock_config, \
         patch("src.connectors.alpaca_news_stream.AlpacaNewsStreamConnector") as mock_cls, \
         patch.object(news_stream, "registra_sottoscrizione") as mock_registra:
        mock_config.ALPACA_API_KEY = "k"
        mock_config.ALPACA_SECRET_KEY = "s"
        mock_config.WATCHLIST_SYMBOLS = ["AAPL", "MSFT"]
        mock_cls.return_value = MagicMock()

        news_stream.run_news_stream.run()

    mock_registra.assert_called_once_with(["AAPL", "MSFT"])


def test_registra_sottoscrizione_non_blocca_lo_stream_se_postgres_e_giu():
    from src.workers.news_stream import registra_sottoscrizione

    with patch("src.store.pg_store.PostgreSQLStore", side_effect=RuntimeError("down")):
        registra_sottoscrizione(["AAPL"])
