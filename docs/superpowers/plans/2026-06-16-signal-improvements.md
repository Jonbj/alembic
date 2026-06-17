# Signal Improvements — Tier 1 & 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implementare cinque miglioramenti al pipeline di segnali di Alembic: timeout LLM per-model, attivazione dei connettori SEC EDGAR e RSS già scritti ma inattivi, uscita forzata su sentiment reversal, e scoring con signal velocity.

**Architecture:** I task sono indipendenti e possono essere implementati in ordine (1→5). Ogni task modifica un sottoinsieme di file isolato. Il sistema di ingestion usa il pattern Producer→Redis→Consumer già esistente: aggiungere una sorgente = aggiungere un Celery task che pushes a `news:queue`. La sentiment reversal e la velocity operano nel `portfolio_scheduler.py` leggendo da Redis dopo che il SentimentWorker ha scritto.

**Tech Stack:** Python, Celery + Redis, aiohttp, pydantic, pytest

**Contesto — cosa è già implementato:**
- `src/connectors/sec_edgar.py` — `SECEdgarConnector.fetch()` esiste, ritorna `NewsItem` con `asset_tags=[ticker]`
- `src/connectors/rss.py` — `RSSConnector.fetch()` esiste, richiede `asset_tags` a costruzione
- `src/store/redis_store.py` — `write_sentiment()` scrive `signal:{symbol}:sentiment`, `read_sentiment()` legge
- `src/llm/client.py` — `OllamaCloudClient._OLLAMA_TIMEOUT = 90` è un costante di classe, non configurabile
- `src/workers/ingestion.py` — pattern completo per GDELT, MarketAux, Alpaca — da replicare per SEC e RSS
- `src/workers/portfolio_scheduler.py` — linea 367 carica posizioni Alpaca; linea 398 esegue orchestrator

---

## File Structure

| File | Modifica |
|------|----------|
| `src/config.py` | Task 1: 4 nuovi campi timeout per-model; Task 4: SENTIMENT_REVERSAL_EXIT_THRESHOLD; Task 5: SIGNAL_VELOCITY_BOOST |
| `src/llm/client.py` | Task 1: ogni sottoclasse OllamaCloudClient legge il suo timeout da config |
| `src/workers/ingestion.py` | Task 2: `run_sec_edgar_ingestion_worker`; Task 3: `run_rss_ingestion_worker` + `_extract_tickers_from_text` |
| `src/workers/celery_app.py` | Task 2: beat per SEC EDGAR; Task 3: beat per RSS |
| `src/store/redis_store.py` | Task 5: `append_signal_history` + `get_signal_history` |
| `src/workers/sentiment.py` | Task 5: chiama `append_signal_history` dopo ogni write |
| `src/workers/portfolio_scheduler.py` | Task 4: `_sentiment_reversal_sells` helper; Task 5: `_compute_signal_velocity` + applica a signals_df |
| `tests/llm/test_ollama_timeout.py` | Task 1: test per timeout configurabile |
| `tests/workers/test_sec_edgar_ingestion.py` | Task 2: test del worker SEC EDGAR |
| `tests/workers/test_rss_ingestion.py` | Task 3: test del worker RSS |
| `tests/workers/test_sentiment_reversal.py` | Task 4: test exit forzato su sentiment negativo |
| `tests/workers/test_signal_velocity.py` | Task 5: test velocity history e boost |

---

## Task 1: Per-model LLM timeout configurabile

**Il problema:** `OllamaCloudClient._OLLAMA_TIMEOUT = 90` è fisso per tutti e quattro i modelli Ollama (Kimi, Qwen, DeepSeek, GLM). Se un modello è in rate-limit e risponde lentamente, non c'è modo di abbassarne il timeout operativamente senza un deploy. L'obiettivo: ogni sottoclasse legge il proprio timeout da un env var, con default 90s.

**Files:**
- Modify: `src/config.py` (aggiungere 4 campi)
- Modify: `src/llm/client.py:758-779` (4 sottoclassi OllamaCloudClient)
- Create: `tests/llm/test_ollama_timeout.py`

---

- [ ] **Step 1: Scrivi i test che falliscono**

Crea `tests/llm/test_ollama_timeout.py`:

```python
"""Test per-model LLM timeout configuration."""
import pytest
from unittest.mock import patch


def test_kimi_client_reads_timeout_from_config():
    """OllamaKimiClient deve usare OLLAMA_KIMI_TIMEOUT_SECONDS da config."""
    with patch.dict("os.environ", {"OLLAMA_KIMI_TIMEOUT_SECONDS": "30"}):
        # Reimport per ricaricare config con il nuovo env var
        import importlib
        import src.config as cfg_mod
        importlib.reload(cfg_mod)
        import src.llm.client as client_mod
        importlib.reload(client_mod)
        client = client_mod.OllamaKimiClient()
        assert client._OLLAMA_TIMEOUT == 30


def test_qwen_client_reads_timeout_from_config():
    """OllamaQwen35Client deve usare OLLAMA_QWEN_TIMEOUT_SECONDS da config."""
    with patch.dict("os.environ", {"OLLAMA_QWEN_TIMEOUT_SECONDS": "45"}):
        import importlib
        import src.config as cfg_mod
        importlib.reload(cfg_mod)
        import src.llm.client as client_mod
        importlib.reload(client_mod)
        client = client_mod.OllamaQwen35Client()
        assert client._OLLAMA_TIMEOUT == 45


def test_default_timeout_is_90():
    """Senza env var, il default deve essere 90s."""
    with patch.dict("os.environ", {}, clear=False):
        import importlib
        import src.config as cfg_mod
        importlib.reload(cfg_mod)
        import src.llm.client as client_mod
        importlib.reload(client_mod)
        client = client_mod.OllamaKimiClient()
        assert client._OLLAMA_TIMEOUT == 90
```

- [ ] **Step 2: Verifica che i test falliscano**

```bash
cd /home/stefano/Documents/Projects/Alembic
pytest tests/llm/test_ollama_timeout.py -v
```

Expected: FAIL — `AssertionError: 90 != 30`

- [ ] **Step 3: Aggiungi 4 campi timeout in config.py**

In `src/config.py`, dopo `LLM_TIMEOUT_SECONDS` (riga ~32), aggiungi:

```python
# Per-model Ollama timeouts (seconds). Override the class default of 90s.
# Useful to reduce per-model timeout when a model is known to be rate-limited.
OLLAMA_KIMI_TIMEOUT_SECONDS: int = Field(
    default_factory=lambda: int(os.environ.get("OLLAMA_KIMI_TIMEOUT_SECONDS", "90"))
)
OLLAMA_QWEN_TIMEOUT_SECONDS: int = Field(
    default_factory=lambda: int(os.environ.get("OLLAMA_QWEN_TIMEOUT_SECONDS", "90"))
)
OLLAMA_DEEPSEEK_TIMEOUT_SECONDS: int = Field(
    default_factory=lambda: int(os.environ.get("OLLAMA_DEEPSEEK_TIMEOUT_SECONDS", "90"))
)
OLLAMA_GLM_TIMEOUT_SECONDS: int = Field(
    default_factory=lambda: int(os.environ.get("OLLAMA_GLM_TIMEOUT_SECONDS", "90"))
)
```

- [ ] **Step 4: Modifica le 4 sottoclassi in client.py**

In `src/llm/client.py`, sostituisci le quattro sottoclassi (righe 758–779):

```python
class OllamaKimiClient(OllamaCloudClient):
    """Kimi-k2.6 via Ollama cloud HTTP API — thinking model, long context."""
    model_id = "kimi-k2.6:cloud"
    model_name = "Kimi k2.6 (Ollama)"
    _OLLAMA_TIMEOUT = config.OLLAMA_KIMI_TIMEOUT_SECONDS


class OllamaGlmClient(OllamaCloudClient):
    """GLM-5.1 via Ollama cloud HTTP API."""
    model_id = "glm-5.1:cloud"
    model_name = "GLM 5.1 (Ollama)"
    _OLLAMA_TIMEOUT = config.OLLAMA_GLM_TIMEOUT_SECONDS


class OllamaQwen35Client(OllamaCloudClient):
    """Qwen3.5 via Ollama cloud HTTP API."""
    model_id = "qwen3.5:cloud"
    model_name = "Qwen 3.5 (Ollama)"
    _OLLAMA_TIMEOUT = config.OLLAMA_QWEN_TIMEOUT_SECONDS


class OllamaDeepseekClient(OllamaCloudClient):
    """DeepSeek V4 Pro via Ollama cloud HTTP API."""
    model_id = "deepseek-v4-pro:cloud"
    model_name = "DeepSeek V4 Pro (Ollama)"
    _OLLAMA_TIMEOUT = config.OLLAMA_DEEPSEEK_TIMEOUT_SECONDS
```

**Nota:** `config` è già importato a livello modulo in `client.py`. L'assegnazione `_OLLAMA_TIMEOUT = config.OLLAMA_KIMI_TIMEOUT_SECONDS` avviene a definizione della classe (import time), dopo che `Config()` è istanziato.

- [ ] **Step 5: Verifica che i test passino**

```bash
pytest tests/llm/test_ollama_timeout.py -v
```

Expected: PASS (3 test)

- [ ] **Step 6: Verifica che i test di regressione passino**

```bash
pytest tests/llm/ -v --tb=short
```

Expected: nessuna regressione

- [ ] **Step 7: Commit**

```bash
git add src/config.py src/llm/client.py tests/llm/test_ollama_timeout.py
git commit -m "feat(llm): per-model Ollama timeout configurable via env var

OLLAMA_KIMI/QWEN/DEEPSEEK/GLM_TIMEOUT_SECONDS default 90s.
Allows reducing timeout for rate-limited models without deploy."
```

---

## Task 2: Wire SEC EDGAR al pipeline di ingestion

**Il problema:** `SECEdgarConnector` esiste ma non è mai chiamato. I filing 8-K (earnings surprise, M&A, guidance revision) sono eventi aziendali ufficiali con rapporto segnale/rumore altissimo. Il connector li fetcha già — basta agganciarli alla coda `news:queue`.

**Pattern di riferimento:** `run_alpaca_ingestion_worker()` in `src/workers/ingestion.py` (riga 264) — la stessa struttura si applica.

**Files:**
- Modify: `src/workers/ingestion.py` (aggiungere task + 2 helper)
- Modify: `src/workers/celery_app.py` (aggiungere beat schedule + include)
- Create: `tests/workers/test_sec_edgar_ingestion.py`

---

- [ ] **Step 1: Scrivi i test che falliscono**

Crea `tests/workers/test_sec_edgar_ingestion.py`:

```python
"""Tests for SEC EDGAR ingestion worker."""
import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.models.news import NewsItem
from datetime import datetime, timezone


def _make_edgar_item(ticker: str, id_: str = None) -> NewsItem:
    return NewsItem(
        id=id_ or f"edgar:{ticker}:8-K-2026-06-16",
        source="sec_edgar",
        timestamp=datetime.now(timezone.utc),
        title=f"{ticker} — 8-K",
        body="Quarterly earnings report",
        url=f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0001234",
        language="en",
        asset_tags=[ticker],
    )


def test_sec_edgar_worker_queues_watchlist_items():
    """Worker deve pushare items per ticker in watchlist, skippare gli altri."""
    items = [
        _make_edgar_item("AAPL"),
        _make_edgar_item("UNKNOWN_CORP"),  # non in watchlist
        _make_edgar_item("MSFT"),
    ]

    mock_redis = MagicMock()
    mock_dedup = MagicMock()
    mock_dedup.is_duplicate_by_id.return_value = False

    with patch("src.workers.ingestion.SECEdgarConnector") as mock_connector_cls, \
         patch("src.workers.ingestion.Deduplicator", return_value=mock_dedup), \
         patch("src.workers.ingestion.Redis") as mock_redis_cls, \
         patch("src.workers.ingestion.config") as mock_cfg:

        mock_cfg.WATCHLIST_SYMBOLS = ["AAPL", "MSFT", "GOOGL"]
        mock_cfg.REDIS_URL = "redis://localhost:6379/0"
        mock_redis_cls.from_url.return_value = mock_redis

        # SECEdgarConnector().fetch() è async generator
        async def fake_fetch():
            for item in items:
                yield item

        mock_connector_cls.return_value.fetch.return_value = fake_fetch()

        from src.workers.ingestion import run_sec_edgar_ingestion_worker
        result = run_sec_edgar_ingestion_worker()

    assert result["queued"] == 2        # AAPL + MSFT
    assert result["filtered"] == 1      # UNKNOWN_CORP
    assert mock_redis.rpush.call_count == 2


def test_sec_edgar_worker_deduplicates():
    """Worker deve skippare item già visto."""
    items = [_make_edgar_item("AAPL")]

    mock_redis = MagicMock()
    mock_dedup = MagicMock()
    mock_dedup.is_duplicate_by_id.return_value = True  # già in cache

    with patch("src.workers.ingestion.SECEdgarConnector") as mock_connector_cls, \
         patch("src.workers.ingestion.Deduplicator", return_value=mock_dedup), \
         patch("src.workers.ingestion.Redis") as mock_redis_cls, \
         patch("src.workers.ingestion.config") as mock_cfg:

        mock_cfg.WATCHLIST_SYMBOLS = ["AAPL"]
        mock_cfg.REDIS_URL = "redis://localhost:6379/0"
        mock_redis_cls.from_url.return_value = mock_redis

        async def fake_fetch():
            for item in items:
                yield item

        mock_connector_cls.return_value.fetch.return_value = fake_fetch()

        from src.workers.ingestion import run_sec_edgar_ingestion_worker
        result = run_sec_edgar_ingestion_worker()

    assert result["queued"] == 0
    assert result["duplicates"] == 1
    assert mock_redis.rpush.call_count == 0


def test_sec_edgar_worker_skips_item_with_no_ticker():
    """Item senza asset_tags viene skippato."""
    item_no_ticker = NewsItem(
        id="edgar:no-ticker",
        source="sec_edgar",
        timestamp=datetime.now(timezone.utc),
        title="Unknown Corp — 8-K",
        body="Filing body",
        url="https://www.sec.gov",
        language="en",
        asset_tags=[],  # nessun ticker
    )

    mock_redis = MagicMock()
    mock_dedup = MagicMock()

    with patch("src.workers.ingestion.SECEdgarConnector") as mock_connector_cls, \
         patch("src.workers.ingestion.Deduplicator", return_value=mock_dedup), \
         patch("src.workers.ingestion.Redis") as mock_redis_cls, \
         patch("src.workers.ingestion.config") as mock_cfg:

        mock_cfg.WATCHLIST_SYMBOLS = ["AAPL"]
        mock_cfg.REDIS_URL = "redis://localhost:6379/0"
        mock_redis_cls.from_url.return_value = mock_redis

        async def fake_fetch():
            yield item_no_ticker

        mock_connector_cls.return_value.fetch.return_value = fake_fetch()

        from src.workers.ingestion import run_sec_edgar_ingestion_worker
        result = run_sec_edgar_ingestion_worker()

    assert result["queued"] == 0
    assert result["filtered"] == 1
```

- [ ] **Step 2: Verifica che i test falliscano**

```bash
pytest tests/workers/test_sec_edgar_ingestion.py -v
```

Expected: FAIL — `ImportError: cannot import name 'run_sec_edgar_ingestion_worker'`

- [ ] **Step 3: Aggiungi il task e gli helper in ingestion.py**

In `src/workers/ingestion.py`, aggiungi dopo gli import esistenti:
```python
from src.connectors.sec_edgar import SECEdgarConnector
```

Poi aggiungi alla fine del file:

```python
async def _fetch_sec_edgar_items(connector: SECEdgarConnector) -> list[NewsItem]:
    """Drain the async SEC EDGAR iterator into a concrete list."""
    return [item async for item in connector.fetch()]


def _process_sec_edgar_items(
    items: list[NewsItem],
    watchlist: set[str],
    deduplicator: Deduplicator,
    redis_client: Redis,
) -> dict:
    """Filter by watchlist, deduplicate, and push EDGAR NewsItems to news:queue."""
    stats = {"fetched": 0, "queued": 0, "filtered": 0, "duplicates": 0}
    for item in items:
        stats["fetched"] += 1
        ticker = item.asset_tags[0] if item.asset_tags else None
        if not ticker or ticker not in watchlist:
            stats["filtered"] += 1
            continue
        if deduplicator.is_duplicate_by_id(item):
            stats["duplicates"] += 1
            continue
        redis_client.rpush("news:queue", item.model_dump_json())
        stats["queued"] += 1
    return stats


@app.task(name="src.workers.ingestion.run_sec_edgar_ingestion_worker")
def run_sec_edgar_ingestion_worker() -> dict:
    """Celery entry-point: fetch SEC 8-K/10-Q/10-K filings, push to news:queue.

    Fetches today's EDGAR filings, filters by WATCHLIST_SYMBOLS, deduplicates,
    and pushes to news:queue for the SentimentWorker. Zero API cost (public API).

    Schedule: every 30 min, Mon–Fri 14:00–21:00 UTC.
    """
    redis_client = Redis.from_url(config.REDIS_URL)
    try:
        connector = SECEdgarConnector(form_types=["8-K", "10-Q", "10-K"])
        watchlist = set(config.WATCHLIST_SYMBOLS or [])
        deduplicator = Deduplicator(redis_client)

        items = asyncio.run(_fetch_sec_edgar_items(connector))
        stats = _process_sec_edgar_items(items, watchlist, deduplicator, redis_client)

        log.info("SEC EDGAR ingestion stats: %s", stats)
        return stats
    except Exception as exc:
        log.error("SEC EDGAR ingestion failed: %s", exc, exc_info=True)
        return {"error": str(exc)}
    finally:
        redis_client.close()
```

- [ ] **Step 4: Aggiungi include e beat schedule in celery_app.py**

In `src/workers/celery_app.py`, nell'array `include` (riga ~30), `src.workers.ingestion` è già presente — nessuna modifica.

Nel `beat_schedule`, aggiungi dopo `"run-alpaca-ingestion"`:

```python
    # SEC EDGAR filings every 30 min during market hours.
    # 8-K filings = earnings, M&A, guidance revision — high signal/noise ratio.
    # Public API, zero cost. Filters by WATCHLIST_SYMBOLS.
    "run-sec-edgar-ingestion": {
        "task": "src.workers.ingestion.run_sec_edgar_ingestion_worker",
        "schedule": crontab(minute="*/30", hour="14-21", day_of_week="1-5"),
    },
```

- [ ] **Step 5: Verifica che i test passino**

```bash
pytest tests/workers/test_sec_edgar_ingestion.py -v
```

Expected: PASS (3 test)

- [ ] **Step 6: Verifica regressioni ingestion**

```bash
pytest tests/workers/ -k "ingestion" -v --tb=short
```

Expected: nessuna regressione

- [ ] **Step 7: Commit**

```bash
git add src/workers/ingestion.py src/workers/celery_app.py tests/workers/test_sec_edgar_ingestion.py
git commit -m "feat(ingestion): wire SEC EDGAR connector to Celery beat

8-K/10-Q/10-K filings fetched every 30min during market hours.
Filters by WATCHLIST_SYMBOLS, deduplicates, pushes to news:queue.
Zero API cost (EDGAR public endpoint)."
```

---

## Task 3: Wire RSS al pipeline di ingestion

**Il problema:** `RSSConnector` esiste ma non è collegato. Reuters e CNBC RSS hanno latenza ~2-5 min vs 15 min del REST polling. Il connector prende `asset_tags` come parametro di costruzione — un solo tag per tutti gli articoli non ha senso per news di mercato generale.

**Soluzione:** Aggiungere un helper `_extract_tickers_from_text` che cerca i ticker della watchlist come parole intere nel testo dell'articolo (regex `\bTICKER\b`). Imperfetto ma cattura "AAPL rose 3%" senza NLP.

**Feeds configurati nel task (non in config — sono URL stabili di fonti pubbliche):**
- Reuters Business News: `https://feeds.reuters.com/reuters/businessNews`
- CNBC Top News: `https://www.cnbc.com/id/100003114/device/rss/rss.html`

**Files:**
- Modify: `src/workers/ingestion.py`
- Modify: `src/workers/celery_app.py`
- Create: `tests/workers/test_rss_ingestion.py`

---

- [ ] **Step 1: Scrivi i test che falliscono**

Crea `tests/workers/test_rss_ingestion.py`:

```python
"""Tests for RSS ingestion worker."""
import re
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

from src.models.news import NewsItem


def _make_rss_item(title: str, body: str = "", ticker: str = "") -> NewsItem:
    return NewsItem(
        id=f"rss:{hash(title)}",
        source="reuters",
        timestamp=datetime.now(timezone.utc),
        title=title,
        body=body,
        url="https://reuters.com/article/foo",
        language="en",
        asset_tags=[ticker] if ticker else [],
    )


class TestExtractTickersFromText:
    def test_finds_ticker_in_title(self):
        from src.workers.ingestion import _extract_tickers_from_text
        result = _extract_tickers_from_text("AAPL shares rose 3% today", {"AAPL", "MSFT"})
        assert "AAPL" in result
        assert "MSFT" not in result

    def test_finds_multiple_tickers(self):
        from src.workers.ingestion import _extract_tickers_from_text
        result = _extract_tickers_from_text("AAPL and MSFT both up", {"AAPL", "MSFT", "GOOGL"})
        assert set(result) == {"AAPL", "MSFT"}

    def test_no_match_returns_empty(self):
        from src.workers.ingestion import _extract_tickers_from_text
        result = _extract_tickers_from_text("Federal Reserve raises rates", {"AAPL", "MSFT"})
        assert result == []

    def test_partial_word_not_matched(self):
        """'APPS' non deve matchare 'APP' nella watchlist."""
        from src.workers.ingestion import _extract_tickers_from_text
        result = _extract_tickers_from_text("APPS rallied today", {"APP"})
        assert result == []


def test_rss_worker_queues_items_with_ticker_match():
    """Worker deve pushare solo articoli con almeno un ticker della watchlist."""
    items = [
        _make_rss_item("AAPL quarterly results beat estimates"),      # match
        _make_rss_item("Federal Reserve holds rates steady"),          # no match
        _make_rss_item("MSFT Azure revenue grows 30%"),                # match
    ]

    mock_redis = MagicMock()
    mock_dedup = MagicMock()
    mock_dedup.is_duplicate_by_id.return_value = False

    with patch("src.workers.ingestion.RSSConnector") as mock_rss_cls, \
         patch("src.workers.ingestion.Deduplicator", return_value=mock_dedup), \
         patch("src.workers.ingestion.Redis") as mock_redis_cls, \
         patch("src.workers.ingestion.config") as mock_cfg:

        mock_cfg.WATCHLIST_SYMBOLS = ["AAPL", "MSFT", "GOOGL"]
        mock_cfg.REDIS_URL = "redis://localhost:6379/0"
        mock_redis_cls.from_url.return_value = mock_redis

        async def fake_fetch():
            for item in items:
                yield item

        mock_rss_cls.return_value.fetch.return_value = fake_fetch()

        from src.workers.ingestion import run_rss_ingestion_worker
        result = run_rss_ingestion_worker()

    # AAPL article → 1 push; MSFT article → 1 push; Federal Reserve → filtered
    assert result["queued"] == 2
    assert result["filtered"] == 1


def test_rss_worker_expands_per_ticker():
    """Articolo con 2 ticker → 2 item separati in coda."""
    items = [_make_rss_item("AAPL and MSFT both surge on AI news")]

    mock_redis = MagicMock()
    mock_dedup = MagicMock()
    mock_dedup.is_duplicate_by_id.return_value = False

    with patch("src.workers.ingestion.RSSConnector") as mock_rss_cls, \
         patch("src.workers.ingestion.Deduplicator", return_value=mock_dedup), \
         patch("src.workers.ingestion.Redis") as mock_redis_cls, \
         patch("src.workers.ingestion.config") as mock_cfg:

        mock_cfg.WATCHLIST_SYMBOLS = ["AAPL", "MSFT"]
        mock_cfg.REDIS_URL = "redis://localhost:6379/0"
        mock_redis_cls.from_url.return_value = mock_redis

        async def fake_fetch():
            for item in items:
                yield item

        mock_rss_cls.return_value.fetch.return_value = fake_fetch()

        from src.workers.ingestion import run_rss_ingestion_worker
        result = run_rss_ingestion_worker()

    assert result["queued"] == 2  # un item per AAPL, uno per MSFT
    assert mock_redis.rpush.call_count == 2
```

- [ ] **Step 2: Verifica che i test falliscano**

```bash
pytest tests/workers/test_rss_ingestion.py -v
```

Expected: FAIL — `ImportError: cannot import name 'run_rss_ingestion_worker'`

- [ ] **Step 3: Aggiungi helper e task in ingestion.py**

In `src/workers/ingestion.py`, aggiungi import in cima:
```python
import re
from src.connectors.rss import RSSConnector
```

Poi aggiungi alla fine del file:

```python
# RSS feeds: stabile, URL pubblici senza API key.
_RSS_FEEDS = [
    ("https://feeds.reuters.com/reuters/businessNews", "reuters"),
    ("https://www.cnbc.com/id/100003114/device/rss/rss.html", "cnbc"),
]


def _extract_tickers_from_text(text: str, watchlist: set[str]) -> list[str]:
    """Find watchlist tickers mentioned as whole words in text.

    Uses word-boundary regex: 'AAPL' in 'AAPL rose' matches, but 'APP' in
    'APPS' does not. Simple but fast — no NLP required.
    """
    words = set(re.findall(r"\b[A-Z]{1,5}\b", text))
    return [t for t in watchlist if t in words]


async def _fetch_rss_items(connector: RSSConnector) -> list[NewsItem]:
    """Drain the async RSS iterator into a concrete list."""
    return [item async for item in connector.fetch()]


def _process_rss_items(
    items: list[NewsItem],
    watchlist: set[str],
    deduplicator: Deduplicator,
    redis_client: Redis,
    source_name: str,
) -> dict:
    """Extract tickers, expand per-ticker, deduplicate, push to news:queue."""
    stats = {"fetched": 0, "queued": 0, "filtered": 0, "duplicates": 0}
    for item in items:
        stats["fetched"] += 1
        search_text = f"{item.title} {item.body}"
        tickers = _extract_tickers_from_text(search_text, watchlist)
        if not tickers:
            stats["filtered"] += 1
            continue
        for ticker in tickers:
            per_ticker = NewsItem(
                id=f"{item.id}:{ticker}",
                source=source_name,
                timestamp=item.timestamp,
                title=item.title,
                body=item.body,
                url=item.url,
                language=item.language,
                asset_tags=[ticker],
            )
            if deduplicator.is_duplicate_by_id(per_ticker):
                stats["duplicates"] += 1
                continue
            redis_client.rpush("news:queue", per_ticker.model_dump_json())
            stats["queued"] += 1
    return stats


@app.task(name="src.workers.ingestion.run_rss_ingestion_worker")
def run_rss_ingestion_worker() -> dict:
    """Celery entry-point: fetch RSS feeds, push ticker-tagged articles to news:queue.

    Fetches Reuters + CNBC RSS, extracts watchlist ticker mentions via regex,
    expands per-ticker, deduplicates, and pushes to news:queue.
    Lower latency than REST polling: RSS updates every 2-5 min.

    Schedule: every 15 min, Mon–Fri 14:00–21:00 UTC.
    """
    redis_client = Redis.from_url(config.REDIS_URL)
    try:
        watchlist = set(config.WATCHLIST_SYMBOLS or [])
        deduplicator = Deduplicator(redis_client)
        total_stats: dict[str, int] = {"fetched": 0, "queued": 0, "filtered": 0, "duplicates": 0}

        for feed_url, source_name in _RSS_FEEDS:
            try:
                connector = RSSConnector(
                    feed_url=feed_url,
                    source_name=source_name,
                    asset_tags=[],  # asset_tags gestiti da _process_rss_items
                )
                items = asyncio.run(_fetch_rss_items(connector))
                stats = _process_rss_items(items, watchlist, deduplicator, redis_client, source_name)
                for k, v in stats.items():
                    total_stats[k] = total_stats.get(k, 0) + v
                log.info("RSS [%s] stats: %s", source_name, stats)
            except Exception as exc:
                log.warning("RSS feed [%s] failed: %s — skipping", source_name, exc)

        log.info("RSS total ingestion stats: %s", total_stats)
        return total_stats
    finally:
        redis_client.close()
```

- [ ] **Step 4: Aggiungi beat schedule in celery_app.py**

In `src/workers/celery_app.py`, nel `beat_schedule`, aggiungi dopo `"run-sec-edgar-ingestion"`:

```python
    # RSS news ingestion every 15 min during market hours.
    # Reuters + CNBC. Lower latency than REST polling (~2-5 min vs 15 min).
    # Uses watchlist ticker mention extraction (regex, no NLP).
    "run-rss-ingestion": {
        "task": "src.workers.ingestion.run_rss_ingestion_worker",
        "schedule": crontab(minute="*/15", hour="14-21", day_of_week="1-5"),
    },
```

- [ ] **Step 5: Verifica che i test passino**

```bash
pytest tests/workers/test_rss_ingestion.py -v
```

Expected: PASS (6 test)

- [ ] **Step 6: Verifica regressioni**

```bash
pytest tests/workers/ -v --tb=short
```

Expected: nessuna regressione

- [ ] **Step 7: Commit**

```bash
git add src/workers/ingestion.py src/workers/celery_app.py tests/workers/test_rss_ingestion.py
git commit -m "feat(ingestion): wire RSS connector (Reuters + CNBC) to Celery beat

Adds run_rss_ingestion_worker and _extract_tickers_from_text helper.
Word-boundary regex extracts watchlist mentions without NLP.
Expands per-ticker, deduplicates, pushes to news:queue every 15min."
```

---

## Task 4: Sentiment reversal exits

**Il problema:** Quando il sentiment di un titolo già in portafoglio diventa fortemente negativo, Alembic non esce fino al prossimo ciclo in cui il modello di portfolio genera un peso 0. Questo introduce un ritardo di 1–4 cicli (15–60 min). Un exit forzato basato sul segnale LLM riduce l'esposizione prima che la perdita si materializzi.

**Logica:**
1. Leggi le posizioni Alpaca aperte (già disponibili in `alpaca_positions` a riga 367)
2. Per ogni posizione long, leggi `signal:{symbol}:sentiment` da Redis
3. Se `score < SENTIMENT_REVERSAL_EXIT_THRESHOLD` (default -0.20) → aggiungi il simbolo alla lista `reversal_sells`
4. Dopo `orchestrator.run_cycle()`, per ogni simbolo in `reversal_sells` che non ha già un ordine SELL nel `result.final_orders`, submetti direttamente un ordine SELL

**Threshold:** -0.20 è il valore consigliato (segnale chiaramente negativo, non solo incerto). Configurabile via `SENTIMENT_REVERSAL_EXIT_THRESHOLD` in `.env`.

**Files:**
- Modify: `src/config.py` (aggiungere 1 campo)
- Modify: `src/workers/portfolio_scheduler.py` (aggiungere `_sentiment_reversal_sells` + hook nel ciclo)
- Create: `tests/workers/test_sentiment_reversal.py`

---

- [ ] **Step 1: Scrivi i test che falliscono**

Crea `tests/workers/test_sentiment_reversal.py`:

```python
"""Tests for sentiment reversal exit logic."""
import pytest
from unittest.mock import MagicMock


def _make_position(symbol: str, qty: float = 100.0) -> MagicMock:
    pos = MagicMock()
    pos.symbol = symbol
    pos.qty = str(qty)
    return pos


def test_reversal_sells_returns_symbols_with_negative_score():
    """Simboli con score < threshold devono essere restituiti per exit forzato."""
    from src.workers.portfolio_scheduler import _sentiment_reversal_sells

    positions = [_make_position("AAPL"), _make_position("MSFT"), _make_position("GOOGL")]

    mock_redis = MagicMock()
    # AAPL: score -0.5 (fortemente negativo) → sell
    # MSFT: score +0.3 (positivo) → hold
    # GOOGL: score -0.1 (sotto -0.20? No) → hold
    import json
    def redis_get(key):
        scores = {
            "signal:AAPL:sentiment": json.dumps({"score": -0.5}),
            "signal:MSFT:sentiment": json.dumps({"score": 0.3}),
            "signal:GOOGL:sentiment": json.dumps({"score": -0.1}),
        }
        return scores.get(key)
    mock_redis.get.side_effect = redis_get

    result = _sentiment_reversal_sells(positions, mock_redis, threshold=-0.20)

    assert "AAPL" in result
    assert "MSFT" not in result
    assert "GOOGL" not in result


def test_reversal_sells_skips_when_no_signal():
    """Simbolo senza segnale Redis → no exit forzato (fail-open)."""
    from src.workers.portfolio_scheduler import _sentiment_reversal_sells

    positions = [_make_position("NVDA")]
    mock_redis = MagicMock()
    mock_redis.get.return_value = None  # nessun segnale in Redis

    result = _sentiment_reversal_sells(positions, mock_redis, threshold=-0.20)

    assert "NVDA" not in result


def test_reversal_sells_handles_malformed_redis_value():
    """Valore Redis malformato → no exit forzato, nessuna eccezione."""
    from src.workers.portfolio_scheduler import _sentiment_reversal_sells

    positions = [_make_position("TSLA")]
    mock_redis = MagicMock()
    mock_redis.get.return_value = "not-valid-json"

    result = _sentiment_reversal_sells(positions, mock_redis, threshold=-0.20)

    assert "TSLA" not in result


def test_reversal_threshold_from_config():
    """SENTIMENT_REVERSAL_EXIT_THRESHOLD deve essere leggibile da config."""
    with __import__("unittest.mock", fromlist=["patch"]).patch.dict(
        "os.environ", {"SENTIMENT_REVERSAL_EXIT_THRESHOLD": "-0.30"}
    ):
        import importlib
        import src.config as cfg_mod
        importlib.reload(cfg_mod)
        assert cfg_mod.config.SENTIMENT_REVERSAL_EXIT_THRESHOLD == -0.30
```

- [ ] **Step 2: Verifica che i test falliscano**

```bash
pytest tests/workers/test_sentiment_reversal.py -v
```

Expected: FAIL — `ImportError: cannot import name '_sentiment_reversal_sells'`

- [ ] **Step 3: Aggiungi il campo in config.py**

In `src/config.py`, dopo i campi `ENSEMBLE_*` (riga ~112):

```python
# Sentiment reversal exit: if a held position's current LLM score drops below
# this threshold, a forced SELL is submitted in the next portfolio cycle.
# Default -0.20: clearly negative signal, not just uncertain.
SENTIMENT_REVERSAL_EXIT_THRESHOLD: float = Field(
    default_factory=lambda: float(
        os.environ.get("SENTIMENT_REVERSAL_EXIT_THRESHOLD", "-0.20")
    )
)
```

- [ ] **Step 4: Aggiungi `_sentiment_reversal_sells` in portfolio_scheduler.py**

Alla fine di `src/workers/portfolio_scheduler.py`, aggiungi:

```python
def _sentiment_reversal_sells(
    alpaca_positions: list,
    redis_client,
    threshold: float,
) -> set[str]:
    """Return symbols held long whose current sentiment score has gone negative.

    Reads signal:{symbol}:sentiment from Redis for each open position.
    Returns the set of symbols that should be force-sold this cycle.
    Fail-open: symbols with no signal or unparseable value are NOT sold.
    """
    import json as _json

    reversal = set()
    for pos in alpaca_positions:
        try:
            raw = redis_client.get(f"signal:{pos.symbol}:sentiment")
            if raw is None:
                continue
            data = _json.loads(raw)
            score = float(data.get("score", 0.0))
            if score < threshold:
                reversal.add(pos.symbol)
                log.info(
                    "Sentiment reversal: %s score=%.3f < threshold=%.2f — forced exit",
                    pos.symbol, score, threshold,
                )
        except Exception as exc:
            log.debug("Could not read sentiment for %s: %s", pos.symbol, exc)
    return reversal
```

- [ ] **Step 5: Aggiungi il hook nel ciclo in portfolio_scheduler.py**

In `_run_cycle_inner()`, subito dopo il blocco che carica le posizioni Alpaca (dopo la riga 375, dopo il `log.info("Loaded %d existing...")`):

```python
    # Sentiment reversal check: find held positions with strongly negative LLM signal.
    # Symbols in reversal_sell_symbols will be force-sold after orchestration.
    reversal_sell_symbols: set[str] = set()
    try:
        from redis import Redis as _RedisRev
        _r_rev = _RedisRev.from_url(config.REDIS_URL, decode_responses=True)
        try:
            reversal_sell_symbols = _sentiment_reversal_sells(
                alpaca_positions,
                _r_rev,
                threshold=config.SENTIMENT_REVERSAL_EXIT_THRESHOLD,
            )
        finally:
            _r_rev.close()
    except Exception as _rev_exc:
        log.warning("Sentiment reversal check failed: %s — skipping", _rev_exc)
```

Poi, dopo la riga che calcola `submitted_orders` (dopo il blocco `if operating_mode in ("dry_run", "halted")`):

```python
    # Submit forced sells for sentiment reversal (symbols not already being sold
    # by the orchestrator's normal output).
    if reversal_sell_symbols and operating_mode not in ("dry_run", "halted"):
        already_selling = {o.symbol for o in result.final_orders if o.side.value == "sell"}
        to_force_sell = reversal_sell_symbols - already_selling
        for sym in to_force_sell:
            try:
                from alpaca.trading.enums import OrderSide, TimeInForce
                from alpaca.trading.requests import MarketOrderRequest
                qty_held = next(
                    (float(p.qty) for p in alpaca_positions if p.symbol == sym), None
                )
                if qty_held and qty_held > 0:
                    req = MarketOrderRequest(
                        symbol=sym,
                        qty=qty_held,
                        side=OrderSide.SELL,
                        time_in_force=TimeInForce.DAY,
                    )
                    resp = trading_client.submit_order(req)
                    submitted_orders.append({
                        "symbol": sym,
                        "side": "sell",
                        "order_id": str(resp.id),
                        "notional": 0.0,
                        "reason": "sentiment_reversal",
                    })
                    log.info("Forced sell submitted for %s (sentiment reversal)", sym)
            except Exception as _fs_exc:
                log.warning("Failed to submit forced sell for %s: %s", sym, _fs_exc)
```

- [ ] **Step 6: Verifica che i test passino**

```bash
pytest tests/workers/test_sentiment_reversal.py -v
```

Expected: PASS (4 test)

- [ ] **Step 7: Verifica regressioni**

```bash
pytest tests/ -v --tb=short -q
```

Expected: nessuna regressione

- [ ] **Step 8: Commit**

```bash
git add src/config.py src/workers/portfolio_scheduler.py tests/workers/test_sentiment_reversal.py
git commit -m "feat(portfolio): sentiment reversal forced exit

Holdings with LLM score < SENTIMENT_REVERSAL_EXIT_THRESHOLD (-0.20 default)
trigger a forced market SELL in the same portfolio cycle.
Fail-open: symbols with no Redis signal are left unchanged."
```

---

## Task 5: Signal velocity scoring

**Il problema:** Un sentiment stabile a +0.6 da 3 giorni è meno predittivo di un sentiment che è passato da +0.1 a +0.6 nelle ultime 2 ore. La velocità del cambiamento è un segnale autonomo che l'S4 strategy non cattura.

**Logica:**
1. Ogni volta che il SentimentWorker scrive un segnale, appende lo score a una lista Redis `signal:{symbol}:history` (max 5 elementi)
2. Il portfolio scheduler legge gli ultimi 3 score per ogni simbolo S4 e calcola la velocity: `velocity = current_score - oldest_of_3`
3. Applica un boost moltiplicativo agli score di S4 prima di passarli alla strategy:
   - Se `velocity > SIGNAL_VELOCITY_THRESHOLD` (default 0.30) → moltiplica score × 1.20
   - Se `velocity < -SIGNAL_VELOCITY_THRESHOLD` → moltiplica score × 0.80
   - Altrimenti → nessuna modifica

**Files:**
- Modify: `src/config.py` (2 nuovi campi)
- Modify: `src/store/redis_store.py` (2 nuovi metodi)
- Modify: `src/workers/sentiment.py` (1 chiamata dopo write)
- Modify: `src/workers/portfolio_scheduler.py` (`_build_strategy_instance` per S4)
- Create: `tests/workers/test_signal_velocity.py`

---

- [ ] **Step 1: Scrivi i test che falliscono**

Crea `tests/workers/test_signal_velocity.py`:

```python
"""Tests for signal velocity scoring."""
import json
import pytest
from unittest.mock import MagicMock


class TestRedisStoreSignalHistory:
    def test_append_signal_history_pushes_and_trims(self):
        """append_signal_history deve LPUSH e mantenere max 5 elementi."""
        from src.store.redis_store import RedisStore

        store = RedisStore.__new__(RedisStore)
        store.redis = MagicMock()

        store.append_signal_history("AAPL", 0.6)

        store.redis.lpush.assert_called_once()
        call_args = store.redis.lpush.call_args[0]
        assert call_args[0] == "signal:AAPL:history"
        assert json.loads(call_args[1])["score"] == 0.6

        store.redis.ltrim.assert_called_once_with("signal:AAPL:history", 0, 4)

    def test_get_signal_history_returns_list_of_scores(self):
        """get_signal_history deve ritornare lista di float."""
        from src.store.redis_store import RedisStore

        store = RedisStore.__new__(RedisStore)
        store.redis = MagicMock()
        store.redis.lrange.return_value = [
            json.dumps({"score": 0.6}),
            json.dumps({"score": 0.3}),
            json.dumps({"score": 0.1}),
        ]

        result = store.get_signal_history("AAPL", n=3)

        assert result == [0.6, 0.3, 0.1]
        store.redis.lrange.assert_called_once_with("signal:AAPL:history", 0, 2)

    def test_get_signal_history_returns_empty_on_no_data(self):
        """Nessun dato Redis → lista vuota."""
        from src.store.redis_store import RedisStore

        store = RedisStore.__new__(RedisStore)
        store.redis = MagicMock()
        store.redis.lrange.return_value = []

        result = store.get_signal_history("NVDA", n=3)
        assert result == []


class TestComputeSignalVelocity:
    def test_positive_velocity_returns_boost(self):
        """Score crescente → boost 1.20."""
        from src.workers.portfolio_scheduler import _compute_signal_velocity
        # history: [current=0.6, previous=0.3, oldest=0.1]
        # velocity = 0.6 - 0.1 = 0.5 > threshold 0.30
        mock_redis = MagicMock()
        mock_redis.lrange.return_value = [
            json.dumps({"score": 0.6}),
            json.dumps({"score": 0.3}),
            json.dumps({"score": 0.1}),
        ]

        multiplier = _compute_signal_velocity("AAPL", mock_redis, threshold=0.30)

        assert multiplier == pytest.approx(1.20)

    def test_negative_velocity_returns_penalty(self):
        """Score decrescente → penalty 0.80."""
        from src.workers.portfolio_scheduler import _compute_signal_velocity

        mock_redis = MagicMock()
        mock_redis.lrange.return_value = [
            json.dumps({"score": -0.5}),
            json.dumps({"score": -0.2}),
            json.dumps({"score": 0.1}),
        ]

        multiplier = _compute_signal_velocity("AAPL", mock_redis, threshold=0.30)

        assert multiplier == pytest.approx(0.80)

    def test_stable_signal_returns_neutral(self):
        """Score stabile → nessun boost (1.0)."""
        from src.workers.portfolio_scheduler import _compute_signal_velocity

        mock_redis = MagicMock()
        mock_redis.lrange.return_value = [
            json.dumps({"score": 0.5}),
            json.dumps({"score": 0.5}),
            json.dumps({"score": 0.5}),
        ]

        multiplier = _compute_signal_velocity("AAPL", mock_redis, threshold=0.30)

        assert multiplier == pytest.approx(1.0)

    def test_insufficient_history_returns_neutral(self):
        """Meno di 2 punti in history → nessun boost."""
        from src.workers.portfolio_scheduler import _compute_signal_velocity

        mock_redis = MagicMock()
        mock_redis.lrange.return_value = [json.dumps({"score": 0.5})]

        multiplier = _compute_signal_velocity("AAPL", mock_redis, threshold=0.30)

        assert multiplier == pytest.approx(1.0)
```

- [ ] **Step 2: Verifica che i test falliscano**

```bash
pytest tests/workers/test_signal_velocity.py -v
```

Expected: FAIL — `ImportError: cannot import name 'append_signal_history'` e simili

- [ ] **Step 3: Aggiungi i campi config in config.py**

In `src/config.py`, dopo `SENTIMENT_REVERSAL_EXIT_THRESHOLD`:

```python
# Signal velocity: rate of change of sentiment score across recent cycles.
# If velocity (latest_score - oldest_of_N) exceeds threshold, apply score boost.
SIGNAL_VELOCITY_THRESHOLD: float = Field(
    default_factory=lambda: float(os.environ.get("SIGNAL_VELOCITY_THRESHOLD", "0.30"))
)
SIGNAL_VELOCITY_BOOST: float = Field(
    default_factory=lambda: float(os.environ.get("SIGNAL_VELOCITY_BOOST", "0.20"))
)
```

- [ ] **Step 4: Aggiungi metodi Redis store in redis_store.py**

In `src/store/redis_store.py`, aggiungi dopo il metodo `write_sentiment` (riga ~105):

```python
def append_signal_history(self, symbol: str, score: float) -> None:
    """Append score to signal history list (max 5 entries, newest first).

    Key: signal:{symbol}:history — Redis list, LPUSH keeps newest at index 0.
    TTL is not set: history entries expire naturally as the list is trimmed.
    """
    import json
    key = f"signal:{symbol}:history"
    self.redis.lpush(key, json.dumps({"score": score}))
    self.redis.ltrim(key, 0, 4)  # keep last 5

def get_signal_history(self, symbol: str, n: int = 3) -> list[float]:
    """Return the last n sentiment scores for symbol (newest first).

    Returns empty list if no history exists or on any error.
    """
    import json
    key = f"signal:{symbol}:history"
    raw_list = self.redis.lrange(key, 0, n - 1)
    scores = []
    for raw in raw_list:
        try:
            scores.append(float(json.loads(raw)["score"]))
        except (KeyError, ValueError, TypeError):
            pass
    return scores
```

- [ ] **Step 5: Chiama `append_signal_history` nel SentimentWorker**

In `src/workers/sentiment.py`, trova il punto dove viene chiamato `write_sentiment`. Cerca:

```python
redis_store.write_sentiment(result, signal_id=signal_id)
```

Aggiungi subito dopo:

```python
try:
    redis_store.append_signal_history(result.symbol, result.score)
except Exception as _vh_exc:
    log.debug("Could not append signal history for %s: %s", result.symbol, _vh_exc)
```

**Nota:** Se il metodo `write_sentiment` è in una coroutine `process_news_item`, aggiungi lì. Cerca nel file la chiamata con `grep -n "write_sentiment" src/workers/sentiment.py`.

- [ ] **Step 6: Aggiungi `_compute_signal_velocity` in portfolio_scheduler.py**

Alla fine di `src/workers/portfolio_scheduler.py`:

```python
def _compute_signal_velocity(
    symbol: str,
    redis_client,
    threshold: float,
    boost: float = 0.20,
) -> float:
    """Return a score multiplier based on how fast the sentiment is changing.

    Reads the last 3 entries from signal:{symbol}:history.
    velocity = scores[0] - scores[-1]  (current minus oldest of 3)
    - velocity >  threshold → multiplier = 1 + boost (accelerating upward)
    - velocity < -threshold → multiplier = 1 - boost (accelerating downward)
    - |velocity| <= threshold → multiplier = 1.0 (stable, no adjustment)

    Returns 1.0 (neutral) if fewer than 2 history points exist.
    """
    import json as _json

    try:
        raw_list = redis_client.lrange(f"signal:{symbol}:history", 0, 2)
        if len(raw_list) < 2:
            return 1.0
        scores = [float(_json.loads(r)["score"]) for r in raw_list]
        velocity = scores[0] - scores[-1]
        if velocity > threshold:
            return 1.0 + boost
        if velocity < -threshold:
            return 1.0 - boost
        return 1.0
    except Exception as exc:
        log.debug("Signal velocity error for %s: %s", symbol, exc)
        return 1.0
```

- [ ] **Step 7: Applica velocity ai signals di S4 in _build_strategy_instance**

In `src/workers/portfolio_scheduler.py`, nella funzione `_build_strategy_instance()`, dopo che `signals_df` viene costruito (riga ~637, dopo `log.info("S4: loaded %d signals..."`):

```python
        # Apply signal velocity multiplier to S4 scores.
        # Scores accelerating upward/downward get a ±SIGNAL_VELOCITY_BOOST factor.
        if signals_df is not None and not signals_df.empty:
            try:
                from redis import Redis as _RedisSV
                from src.config import config as _cfg_sv
                _r_sv = _RedisSV.from_url(_cfg_sv.REDIS_URL, decode_responses=True)
                try:
                    multipliers = {
                        sym: _compute_signal_velocity(
                            sym, _r_sv,
                            threshold=_cfg_sv.SIGNAL_VELOCITY_THRESHOLD,
                            boost=_cfg_sv.SIGNAL_VELOCITY_BOOST,
                        )
                        for sym in signals_df["symbol"].unique()
                    }
                finally:
                    _r_sv.close()
                signals_df["score"] = signals_df.apply(
                    lambda row: row["score"] * multipliers.get(row["symbol"], 1.0),
                    axis=1,
                )
                n_boosted = sum(1 for m in multipliers.values() if m != 1.0)
                if n_boosted:
                    log.info("Signal velocity: %d/%d symbols adjusted", n_boosted, len(multipliers))
            except Exception as exc:
                log.warning("Signal velocity application failed: %s — using raw scores", exc)
```

- [ ] **Step 8: Verifica che i test passino**

```bash
pytest tests/workers/test_signal_velocity.py -v
```

Expected: PASS (7 test)

- [ ] **Step 9: Verifica regressioni**

```bash
pytest tests/ -q --tb=short
```

Expected: nessuna regressione

- [ ] **Step 10: Commit**

```bash
git add src/config.py src/store/redis_store.py src/workers/sentiment.py src/workers/portfolio_scheduler.py tests/workers/test_signal_velocity.py
git commit -m "feat(signals): signal velocity scoring for S4 strategy

Tracks per-symbol score history in Redis (last 5 entries).
Scores accelerating by ±SIGNAL_VELOCITY_THRESHOLD (0.30) get
±SIGNAL_VELOCITY_BOOST (20%) multiplier applied to S4 weights."
```

---

## Self-review checklist

**Spec coverage:**
- [x] Per-model LLM timeout → Task 1
- [x] Wire SEC EDGAR → Task 2
- [x] Wire RSS → Task 3
- [x] Exit su sentiment reversal → Task 4
- [x] Signal velocity (delta sentiment) → Task 5
- [ ] Earnings calendar integration → **fuori scope di questo piano** (dipende da EDGAR — pianificare in sessione successiva dopo paper trading)

**Placeholder scan:** Nessun TBD o TODO nel piano. Tutti i blocchi di codice sono completi.

**Type consistency:**
- `_sentiment_reversal_sells` restituisce `set[str]` e viene usata come tale nel ciclo
- `_compute_signal_velocity` restituisce `float` e viene usata come moltiplicatore `row["score"] * multiplier`
- `append_signal_history` e `get_signal_history` usano lo stesso key pattern `signal:{symbol}:history`
- `get_signal_history` ritorna `list[float]`; `_compute_signal_velocity` usa `redis_client.lrange` direttamente (non `get_signal_history`) per mantenere il metodo standalone — consistente

**Tier non inclusi in questo piano (da pianificare separatamente):**
- Short selling su segnali negativi (richiede verifica margine Alpaca EU)
- Position sizing volatility-adjusted (ATR-based)
- Earnings calendar (prossima sessione, dopo Task 2 che abilita EDGAR)
- Ensemble LLM con variance check (post-live)
