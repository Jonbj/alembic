# S2-1 Source P&L Funnel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rendere il sistema non-cieco sulla qualità delle fonti: funnel di ingestione per-fonte persistito (`ingestion_stats_daily`), latenza e P&L per-fonte esposti via `GET /api/quality/sources`, e sezione "Source Funnel & P&L" nella pagina Quality del frontend (FIX-04/05 + EN-05/06 della review funzionale `docs/FUNCTIONAL_REVIEW_2026-07-03.md` §9.1 problema #6).

**Architecture:** Tutto offline/read-only, mai nel hot path. La catena di join esiste già (`trades.signal_id → sentiment_signals.id`, `sentiment_signals.news_log_id → news_log.id`, `news_log.source` — QS-09): questo piano la completa (colonne EN-05, stats table EN-06), la aggrega (endpoint) e la espone (frontend). Nessuna decisione di trading cambia: è puro measurement.

**Tech Stack:** PostgreSQL 16 (psycopg2, SQL raw come in `quality_routes.py`), FastAPI, Pydantic v2, React + TanStack Query (pattern `Quality.tsx`), pytest + TestClient.

**Esecutore:** una singola sessione Claude (modello Sonnet). Esegui i task in ordine numerico, uno alla volta, un commit per task. Non parallelizzare, non delegare a subagent. Spunta le checkbox (`- [x]`) in questo file man mano che completi gli step.

**Criterio di ingresso:** lo Sprint 1 (`docs/superpowers/plans/2026-07-03-functional-review-remediation.md`) è completato e merge-ato. In particolare questo piano assume che la migration `032_sentiment_signals_published_at.sql` esista già: la prima migration qui è la **033**. Se la numerazione è cambiata, adegua (`ls migrations/ | tail`).

> **Status (audit 2026-07-15):** tutti i 7 task implementati, testati (13/13 test mirati PASS + suite frontend 21/21 PASS) e committati (`273ff77`…`ecb9a50`). Migration 033 applicata e verificata live: `ingestion_stats_daily` popolata (es. `gdelt_gkg`/`alpaca_benzinga` con contatori reali), colonne `raw_ingested_at`/`content_hash`/`discarded_reason` presenti su `news_log`, endpoint `GET /api/quality/sources` verificato live con dati reali, `trace_coverage` 2170/2170 (100%) segnali linkati. Le uniche due checkbox lasciate aperte sono i due passi di "Verifica finale" che richiedono un'azione umana in-sessione (aprire `/quality` nel browser; riportare il riepilogo in chat al PO) — non verificabili da un audit ex-post. Fuori scope confermato invariato: `discarded_reason` esiste ma è NULL ovunque (popolamento = S2-2, non fatto); EN-07 alerting non fatto.

---

## Regole di ingaggio

1. **Vincolo non-negoziabile (CLAUDE.md):** niente LLM/API sincrone nel path di esecuzione. Questo piano non tocca il path di esecuzione: se ti sembra di doverlo fare, fermati.
2. **Non toccare:** `src/workers/portfolio_scheduler.py`, `src/workers/execution.py`, `src/strategies/`, `src/portfolio/`. Questo è un piano di *misura*, non di comportamento.
3. **Fail-safe ovunque:** ogni scrittura di statistiche deve essere best-effort (`try/except` + `log.warning`) — un errore di telemetria non deve MAI far fallire un task di ingestione.
4. **Test:** `pytest -q` deve passare dopo ogni task. Registra la baseline prima di iniziare.
5. **Convenzione commit:** conventional commits, un commit per task.
6. Se un anchor di riga non corrisponde più, cerca il simbolo per nome.

---

## Task 1: Migration 033 — `ingestion_stats_daily` + colonne EN-05 su `news_log`

**Files:**
- Create: `migrations/033_source_funnel.sql`

- [x] **Step 1: Scrivere la migration**

Crea `migrations/033_source_funnel.sql`:

```sql
-- S2-1 (FUNCTIONAL_REVIEW_2026-07-03 §9.1 #6, roadmap EN-05/EN-06):
-- per-source ingestion funnel + trace columns. Measurement only, never in hot path.

-- EN-06: one row per (day, source), counters incremented by each ingestion run.
CREATE TABLE IF NOT EXISTS ingestion_stats_daily (
    day                  DATE        NOT NULL,
    source               VARCHAR(50) NOT NULL,
    fetched              INTEGER     NOT NULL DEFAULT 0,
    queued               INTEGER     NOT NULL DEFAULT 0,
    duplicates           INTEGER     NOT NULL DEFAULT 0,
    discarded_no_ticker  INTEGER     NOT NULL DEFAULT 0,
    discarded_stale      INTEGER     NOT NULL DEFAULT 0,
    parse_fail           INTEGER     NOT NULL DEFAULT 0,
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (day, source)
);

-- EN-05: trace columns on news_log.
-- raw_ingested_at = when the connector fetched the article (vs published_at = event time,
--   vs sentiment processing time) → real per-source latency becomes measurable.
-- content_hash    = normalised title+body hash (same function as the Redis dedup) → offline
--   cross-source duplicate analysis on persisted data.
-- discarded_reason = created HERE, populated by S2-2 (discard logging); NULL until then.
ALTER TABLE news_log ADD COLUMN IF NOT EXISTS raw_ingested_at  TIMESTAMPTZ;
ALTER TABLE news_log ADD COLUMN IF NOT EXISTS content_hash     VARCHAR(64);
ALTER TABLE news_log ADD COLUMN IF NOT EXISTS discarded_reason VARCHAR(30);

-- Group-by / join support for the per-source endpoint.
CREATE INDEX IF NOT EXISTS idx_news_log_source ON news_log (source);
CREATE INDEX IF NOT EXISTS idx_sentiment_signals_news_log_id ON sentiment_signals (news_log_id);
```

- [x] **Step 2: Applicare la migration all'ambiente locale (se il DB è attivo)**

Run: `docker compose exec -T postgres psql -U alembic -d alembic -f /dev/stdin < migrations/033_source_funnel.sql`
Expected: `CREATE TABLE` / `ALTER TABLE` / `CREATE INDEX`. Se il container non è attivo, salta e segnala nel commit che va applicata al deploy.

- [x] **Step 3: Commit**

```bash
git add migrations/033_source_funnel.sql
git commit -m "feat(db): ingestion_stats_daily + news_log trace columns (EN-05/EN-06, S2-1)"
```

---

## Task 2: `raw_ingested_at` sul `NewsItem` e propagazione dai worker

Le righe `news_log` sono scritte dal sentiment worker al momento dell'inferenza, quindi il tempo di fetch va trasportato sull'item attraverso la coda Redis.

**Files:**
- Modify: `src/models/news.py` (classe `NewsItem`)
- Modify: `src/workers/ingestion.py` (punti di push su `news:queue`)
- Test: `tests/models/test_news_item_raw_ingested_at.py` (nuovo)

- [x] **Step 1: Scrivere i test che falliscono**

Crea `tests/models/test_news_item_raw_ingested_at.py`:

```python
"""EN-05: NewsItem carries the connector fetch time through the Redis queue,
so news_log can record real per-source latency (fetch vs published vs processed)."""

from datetime import datetime, timezone

from src.models.news import NewsItem


def test_raw_ingested_at_defaults_to_none():
    item = NewsItem(id="u:AAPL", body="b")
    assert item.raw_ingested_at is None


def test_raw_ingested_at_survives_json_roundtrip():
    ts = datetime(2026, 7, 3, 15, 0, tzinfo=timezone.utc)
    item = NewsItem(id="u:AAPL", body="b", raw_ingested_at=ts)
    restored = NewsItem.model_validate_json(item.model_dump_json())
    assert restored.raw_ingested_at == ts


def test_old_queue_payload_without_field_still_parses():
    """Items already in the queue at deploy time lack the field — must not crash."""
    restored = NewsItem.model_validate_json('{"id": "u:AAPL", "body": "b"}')
    assert restored.raw_ingested_at is None
```

- [x] **Step 2: Eseguire i test per verificarne il fallimento**

Run: `pytest tests/models/test_news_item_raw_ingested_at.py -v`
Expected: FAIL (campo inesistente).

- [x] **Step 3: Aggiungere il campo al modello**

In `src/models/news.py`, dentro `NewsItem`, dopo `extraction_method`:

```python
    # EN-05: when the connector fetched this article (None = legacy/unknown).
    # Distinct from `timestamp` (publication time): the gap between the two is the
    # per-source ingestion latency, persisted to news_log.raw_ingested_at.
    raw_ingested_at: datetime | None = None
```

- [x] **Step 4: Eseguire i test per verificarne il pass**

Run: `pytest tests/models/test_news_item_raw_ingested_at.py -v`
Expected: 3 PASS.

- [x] **Step 5: Valorizzare il campo nei worker di ingestione**

In `src/workers/ingestion.py` trova TUTTI i punti dove gli item vengono serializzati e pushati sulla coda: `grep -n "news:queue\|lpush" src/workers/ingestion.py` (se esiste un helper condiviso di push, modifica solo quello). Immediatamente prima della serializzazione/push di ogni item aggiungi:

```python
            per_ticker.raw_ingested_at = datetime.now(timezone.utc)
```

(usa il nome di variabile reale di ciascun sito; verifica che `datetime`/`timezone` siano importati nel modulo, altrimenti aggiungi `from datetime import datetime, timezone`).

- [x] **Step 6: Eseguire i test dei worker**

Run: `pytest tests/workers/ tests/models/ -q`
Expected: tutti PASS.

- [x] **Step 7: Commit**

```bash
git add src/models/news.py src/workers/ingestion.py tests/models/test_news_item_raw_ingested_at.py
git commit -m "feat(ingestion): carry raw_ingested_at on NewsItem through the queue (EN-05)"
```

---

## Task 3: Persistere `raw_ingested_at` e `content_hash` in `news_log`

**Files:**
- Modify: `src/store/pg_store.py` (`_INSERT_NEWS_LOG` + `log_news_item`, righe ~220-262)
- Test: `tests/store/test_log_news_item_trace_columns.py` (nuovo)

- [x] **Step 1: Scrivere il test che fallisce**

Crea `tests/store/test_log_news_item_trace_columns.py` (segui il pattern di mock cursor già usato in `tests/store/`):

```python
"""EN-05: log_news_item persists raw_ingested_at and content_hash."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from src.models.news import NewsItem
from src.store.pg_store import PostgreSQLStore


def test_insert_news_log_sql_has_trace_columns():
    assert "raw_ingested_at" in PostgreSQLStore._INSERT_NEWS_LOG
    assert "content_hash" in PostgreSQLStore._INSERT_NEWS_LOG


def test_log_news_item_passes_trace_values():
    store = PostgreSQLStore.__new__(PostgreSQLStore)
    cursor = MagicMock()
    cursor.fetchone.return_value = (1,)
    conn = MagicMock()
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cursor)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

    ts = datetime(2026, 7, 3, 15, 0, tzinfo=timezone.utc)
    item = NewsItem(id="u:AAPL", title="T", body="B", source="alpaca",
                    asset_tags=["AAPL"], raw_ingested_at=ts)
    with patch.object(PostgreSQLStore, "_get_connection", return_value=conn):
        store.log_news_item(item=item, ticker="AAPL", computed_sentiment=0.4)

    params = cursor.execute.call_args[0][1]
    assert ts in params                              # raw_ingested_at
    assert any(isinstance(p, str) and len(p) == 64 for p in params)  # sha256 hash
```

- [x] **Step 2: Eseguire il test per verificarne il fallimento**

Run: `pytest tests/store/test_log_news_item_trace_columns.py -v`
Expected: FAIL.

- [x] **Step 3: Estendere SQL e metodo**

In `src/store/pg_store.py`:

(a) In `_INSERT_NEWS_LOG` aggiungi le colonne `raw_ingested_at, content_hash` alla lista colonne e due `%s` ai VALUES, mantenendo INVARIATO tutto il resto (incluso l'`ON CONFLICT` e il `RETURNING`).

(b) In `log_news_item`, calcola l'hash e aggiungi i due parametri in coda alla tupla (nello stesso ordine delle colonne aggiunte):

```python
        from src.connectors.deduplicator import compute_dedup_hash
        try:
            content_hash = compute_dedup_hash(item)
        except Exception:
            content_hash = None
```

e nella tupla di `cur.execute`, dopo `getattr(item, "extraction_method", "") or None,`:

```python
                        item.raw_ingested_at,
                        content_hash,
```

- [x] **Step 4: Eseguire i test**

Run: `pytest tests/store/ -q`
Expected: tutti PASS (aggiorna eventuali test esistenti che contano i parametri di `_INSERT_NEWS_LOG`: +2).

- [x] **Step 5: Commit**

```bash
git add src/store/pg_store.py tests/store/test_log_news_item_trace_columns.py
git commit -m "feat(store): persist raw_ingested_at + content_hash on news_log (EN-05)"
```

---

## Task 4: EN-06 — Persistere il funnel per-fonte (`record_ingestion_stats`)

I worker di ingestione ritornano già dict di contatori per run (es. `_process_gkg_items` stats, `total_stats` RSS) ma i numeri vivono solo nei log. Questo task li persiste con upsert-increment su `ingestion_stats_daily`.

**Files:**
- Modify: `src/store/pg_store.py` (nuovo metodo)
- Modify: `src/workers/ingestion.py` (chiamata a fine run per ogni worker)
- Test: `tests/store/test_record_ingestion_stats.py` (nuovo)

- [x] **Step 1: Censire le chiavi reali dei contatori**

Run: `grep -n "stats\[" src/workers/ingestion.py` e `grep -n "return.*stats\|total_stats" src/workers/ingestion.py`
Annota le chiavi usate da ciascun worker (es. `fetched`, `queued`, `duplicates`, `skipped_no_ticker`, `skipped_stale`, ...). Ti servono allo Step 4 per completare la mappa dei sinonimi: la mappa qui sotto è pre-seminata con i nomi più probabili — estendila con le chiavi REALI trovate, non inventare.

- [x] **Step 2: Scrivere i test che falliscono**

Crea `tests/store/test_record_ingestion_stats.py`:

```python
"""EN-06: per-source funnel counters upserted into ingestion_stats_daily."""

from unittest.mock import MagicMock, patch

from src.store.pg_store import PostgreSQLStore


def _store_with_cursor():
    store = PostgreSQLStore.__new__(PostgreSQLStore)
    cursor = MagicMock()
    conn = MagicMock()
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cursor)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    return store, cursor, conn


def test_record_ingestion_stats_maps_synonyms_and_upserts():
    store, cursor, conn = _store_with_cursor()
    with patch.object(PostgreSQLStore, "_get_connection", return_value=conn):
        store.record_ingestion_stats(
            "gdelt_gkg",
            {"fetched": 10, "queued": 3, "duplicates": 5, "skipped_no_ticker": 2},
        )
    sql = cursor.execute.call_args[0][0]
    params = cursor.execute.call_args[0][1]
    assert "ingestion_stats_daily" in sql and "ON CONFLICT" in sql
    assert "gdelt_gkg" in params
    assert 10 in params and 3 in params and 5 in params and 2 in params


def test_record_ingestion_stats_never_raises():
    """Telemetry must be fail-safe: a DB error cannot break an ingestion task."""
    store = PostgreSQLStore.__new__(PostgreSQLStore)
    with patch.object(PostgreSQLStore, "_get_connection", side_effect=RuntimeError("db down")):
        store.record_ingestion_stats("alpaca", {"fetched": 1})  # must not raise


def test_record_ingestion_stats_ignores_unknown_keys():
    store, cursor, conn = _store_with_cursor()
    with patch.object(PostgreSQLStore, "_get_connection", return_value=conn):
        store.record_ingestion_stats("rss", {"weird_counter": 99})
    # all-zero rows are not written
    cursor.execute.assert_not_called()
```

- [x] **Step 3: Eseguire i test per verificarne il fallimento**

Run: `pytest tests/store/test_record_ingestion_stats.py -v`
Expected: FAIL (metodo inesistente).

- [x] **Step 4: Implementare il metodo**

In `src/store/pg_store.py` aggiungi (vicino a `log_news_item`):

```python
    # EN-06: canonical funnel counters ← worker stats-dict synonyms.
    # Extend with the REAL keys found in src/workers/ingestion.py (Task 4 Step 1).
    _INGESTION_STAT_SYNONYMS: dict[str, tuple[str, ...]] = {
        "fetched": ("fetched", "total_fetched", "items_fetched", "total"),
        "queued": ("queued", "pushed", "enqueued"),
        "duplicates": ("duplicates", "skipped_duplicate", "dupes"),
        "discarded_no_ticker": ("discarded_no_ticker", "skipped_no_ticker", "no_ticker", "no_asset_tags"),
        "discarded_stale": ("discarded_stale", "skipped_stale", "stale"),
        "parse_fail": ("parse_fail", "parse_errors", "errors"),
    }

    _UPSERT_INGESTION_STATS = """
        INSERT INTO ingestion_stats_daily
            (day, source, fetched, queued, duplicates,
             discarded_no_ticker, discarded_stale, parse_fail, updated_at)
        VALUES (CURRENT_DATE, %s, %s, %s, %s, %s, %s, %s, now())
        ON CONFLICT (day, source) DO UPDATE SET
            fetched             = ingestion_stats_daily.fetched + EXCLUDED.fetched,
            queued              = ingestion_stats_daily.queued + EXCLUDED.queued,
            duplicates          = ingestion_stats_daily.duplicates + EXCLUDED.duplicates,
            discarded_no_ticker = ingestion_stats_daily.discarded_no_ticker + EXCLUDED.discarded_no_ticker,
            discarded_stale     = ingestion_stats_daily.discarded_stale + EXCLUDED.discarded_stale,
            parse_fail          = ingestion_stats_daily.parse_fail + EXCLUDED.parse_fail,
            updated_at          = now()
    """

    def record_ingestion_stats(self, source: str, stats: dict) -> None:
        """Upsert-increment today's funnel counters for a source. Fail-safe: never raises."""
        try:
            canon = {
                key: sum(int(stats.get(s, 0) or 0) for s in synonyms)
                for key, synonyms in self._INGESTION_STAT_SYNONYMS.items()
            }
            if not any(canon.values()):
                return
            conn = self._get_connection()
            with conn.cursor() as cur:
                cur.execute(
                    self._UPSERT_INGESTION_STATS,
                    (source, canon["fetched"], canon["queued"], canon["duplicates"],
                     canon["discarded_no_ticker"], canon["discarded_stale"], canon["parse_fail"]),
                )
            conn.commit()
        except Exception as exc:
            log.warning("record_ingestion_stats(%s) failed (fail-safe): %s", source, exc)
```

Verifica che `log` esista a livello di modulo in `pg_store.py` (c'è: il modulo ha già logging).

- [x] **Step 5: Eseguire i test per verificarne il pass**

Run: `pytest tests/store/test_record_ingestion_stats.py -v`
Expected: 3 PASS.

- [x] **Step 6: Wire nei worker di ingestione**

In `src/workers/ingestion.py`, per ogni task worker che ritorna uno stats dict (GDELT GKG, Alpaca, MarketAux, RSS, Finnhub, GDELT DOC — anche quelli env-gated: la chiamata va DOPO il gate, così se riattivati misurano da subito), subito prima del `return stats` aggiungi:

```python
        try:
            from src.store.pg_store import PostgreSQLStore
            with PostgreSQLStore() as _pg:
                _pg.record_ingestion_stats("<source_name>", stats)
        except Exception as _stats_exc:
            log.warning("Could not persist ingestion stats: %s", _stats_exc)
```

dove `<source_name>` è il nome fonte coerente con `news_log.source` per quel worker (verificalo: `grep -n "source=" src/connectors/<connector>.py` — deve combaciare, altrimenti il funnel e il P&L non si joinano). Se `PostgreSQLStore` non supporta il context manager (`__enter__`), usa `pg = PostgreSQLStore()` / `try: ... finally: pg.close()` come fanno gli altri worker.

- [x] **Step 7: Eseguire i test**

Run: `pytest tests/workers/ tests/store/ -q`
Expected: tutti PASS.

- [x] **Step 8: Commit**

```bash
git add src/store/pg_store.py src/workers/ingestion.py tests/store/test_record_ingestion_stats.py
git commit -m "feat(ingestion): persist per-source funnel counters to ingestion_stats_daily (EN-06)"
```

---

## Task 5: Endpoint `GET /api/quality/sources`

Aggrega funnel, latenza, near-zero e P&L per fonte. Stesso stile di `quality_routes.py` (SQL raw + `_rows`, mai hot path).

**Files:**
- Modify: `src/api/routes/quality_routes.py`
- Test: `tests/api/test_quality_sources.py` (nuovo)

- [x] **Step 1: Scrivere i test che falliscono**

Crea `tests/api/test_quality_sources.py` (il conftest di `tests/api/` override-a già l'auth):

```python
"""FIX-04: per-source funnel + latency + P&L endpoint."""

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from src.api.main import app

client = TestClient(app)


def test_sources_endpoint_shape():
    with patch("src.store.pg_store.PostgreSQLStore") as MockStore:
        store = MockStore.return_value.__enter__.return_value
        cursor = MagicMock()
        cursor.description = [("source",), ("n",)]
        cursor.fetchall.return_value = []
        store._get_connection.return_value.cursor.return_value.__enter__ = MagicMock(return_value=cursor)
        store._get_connection.return_value.cursor.return_value.__exit__ = MagicMock(return_value=False)
        resp = client.get("/api/quality/sources?days=14")
    assert resp.status_code == 200
    body = resp.json()
    for key in ("window_days", "funnel", "signals", "trades", "trace_coverage"):
        assert key in body


def test_sources_endpoint_survives_db_error():
    """Read-only observability must degrade gracefully, like /api/quality/metrics."""
    with patch("src.store.pg_store.PostgreSQLStore", side_effect=RuntimeError("db down")):
        resp = client.get("/api/quality/sources")
    assert resp.status_code == 200
    assert resp.json()["funnel"] == []
```

NOTA: guarda come i test esistenti (`tests/api/test_llm_routes.py` o simili) mockano `PostgreSQLStore` e replica ESATTAMENTE quel pattern se differisce da questo — il target del patch deve essere il punto di import usato dentro la route (`src.store.pg_store.PostgreSQLStore`, import locale nella funzione, come in `quality_metrics`).

- [x] **Step 2: Eseguire i test per verificarne il fallimento**

Run: `pytest tests/api/test_quality_sources.py -v`
Expected: FAIL con 404 (endpoint inesistente).

- [x] **Step 3: Implementare l'endpoint**

In `src/api/routes/quality_routes.py`, dopo `quality_metrics`, aggiungi:

```python
@router.get("/sources")
def quality_sources(days: int = 14) -> dict:
    """Per-source funnel (EN-06), latency, near-zero and trade P&L (FIX-04).

    Removal thresholds (ROADMAP_DATA_ALPHA §7.4, applied in the frontend verdict):
    hit-rate <40% AND 30d P&L <0; or latency p50 >24h; or near-zero >50%.
    """
    from src.store.pg_store import PostgreSQLStore

    out: dict = {"window_days": days, "funnel": [], "signals": [], "trades": [],
                 "trace_coverage": {}}
    try:
        with PostgreSQLStore() as store:
            with store._get_connection().cursor() as cur:
                out["funnel"] = _rows(cur, """
                    SELECT source,
                           SUM(fetched)::int AS fetched,
                           SUM(queued)::int AS queued,
                           SUM(duplicates)::int AS duplicates,
                           SUM(discarded_no_ticker)::int AS discarded_no_ticker,
                           SUM(discarded_stale)::int AS discarded_stale,
                           SUM(parse_fail)::int AS parse_fail
                    FROM ingestion_stats_daily
                    WHERE day > CURRENT_DATE - %s::int
                    GROUP BY source ORDER BY fetched DESC
                """, (days,))

                out["signals"] = _rows(cur, """
                    SELECT nl.source,
                           COUNT(*)::int AS n_signals,
                           ROUND(AVG(ss.score)::numeric, 3) AS mean_score,
                           ROUND((SUM((ABS(ss.score) < 0.05)::int)::float
                                  / NULLIF(COUNT(*), 0))::numeric, 3) AS near_zero_rate,
                           ROUND((PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY
                               EXTRACT(EPOCH FROM (ss.generated_at - nl.published_at)) / 60
                           ))::numeric, 1) AS latency_p50_min,
                           ROUND((PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY
                               EXTRACT(EPOCH FROM (ss.generated_at - nl.published_at)) / 60
                           ))::numeric, 1) AS latency_p95_min
                    FROM sentiment_signals ss
                    JOIN news_log nl ON nl.id = ss.news_log_id
                    WHERE ss.generated_at > now() - (%s || ' days')::interval
                    GROUP BY nl.source ORDER BY n_signals DESC
                """, (str(days),))

                out["trades"] = _rows(cur, """
                    SELECT COALESCE(nl.source, 'unknown') AS source,
                           COUNT(*)::int AS n_trades,
                           SUM((t.net_pnl > 0)::int)::int AS winners,
                           ROUND((SUM((t.net_pnl > 0)::int)::float
                                  / NULLIF(COUNT(*), 0))::numeric, 3) AS hit_rate,
                           ROUND(SUM(t.net_pnl)::numeric, 2) AS total_net_pnl,
                           ROUND(AVG(t.net_pnl)::numeric, 2) AS avg_net_pnl
                    FROM trades t
                    LEFT JOIN sentiment_signals ss ON ss.id = t.signal_id
                    LEFT JOIN news_log nl ON nl.id = ss.news_log_id
                    WHERE t.exit_time > now() - (%s || ' days')::interval
                      AND t.net_pnl IS NOT NULL
                    GROUP BY 1 ORDER BY total_net_pnl ASC
                """, (str(days),))

                cov = _rows(cur, """
                    SELECT COUNT(*)::int AS total,
                           SUM((news_log_id IS NOT NULL)::int)::int AS linked
                    FROM sentiment_signals
                    WHERE generated_at > now() - (%s || ' days')::interval
                """, (str(days),))
                out["trace_coverage"] = cov[0] if cov else {}
    except Exception as exc:
        log.warning("quality_sources failed: %s", exc)
    return out
```

- [x] **Step 4: Eseguire i test**

Run: `pytest tests/api/ -q`
Expected: tutti PASS.

- [x] **Step 5: Verifica manuale sull'ambiente locale (se lo stack è attivo)**

Run: `curl -s -H "X-API-Key: $ADMIN_API_KEY" http://localhost:8001/api/quality/sources?days=14 | python3 -m json.tool | head -40`
Expected: JSON con le 5 chiavi; `funnel` può essere vuoto finché i worker non girano con il Task 4 deployato — non è un errore.

- [x] **Step 6: Commit**

```bash
git add src/api/routes/quality_routes.py tests/api/test_quality_sources.py
git commit -m "feat(api): GET /api/quality/sources — per-source funnel, latency, P&L (FIX-04)"
```

---

## Task 6: FIX-05 — Backfill best-effort dei `news_log_id` mancanti

QS-09 ha sistemato il go-forward, ma lo storico ha ~28% di segnali senza link a `news_log` (finiscono nel bucket `unknown` del P&L). Backfill conservativo: linka SOLO quando il match è non ambiguo.

**Files:**
- Create: `scripts/backfill_news_log_links.py`
- Test: nessuno (script offline one-shot; la logica critica è nella query, verificata con dry-run)

- [x] **Step 1: Scrivere lo script**

Crea `scripts/backfill_news_log_links.py`:

```python
#!/usr/bin/env python3
"""FIX-05: backfill sentiment_signals.news_log_id for legacy rows (pre QS-09).

Conservative by design: a signal is linked ONLY when exactly one news_log row
matches (same ticker, published/logged within ±30 min of the signal). Ambiguous
or unmatched rows stay NULL and keep reporting as source='unknown' — a wrong
link would corrupt per-source P&L attribution, which is worse than a gap.

Usage (inside the worker container):
    python scripts/backfill_news_log_links.py            # dry-run (default)
    python scripts/backfill_news_log_links.py --apply    # write links
"""
from __future__ import annotations

import argparse

from src.store.pg_store import PostgreSQLStore

_FIND_CANDIDATES = """
    SELECT ss.id AS signal_id,
           (ARRAY_AGG(nl.id))[1] AS news_log_id,
           COUNT(*) AS n_matches
    FROM sentiment_signals ss
    JOIN news_log nl
      ON nl.ticker = ss.symbol
     AND nl.published_at IS NOT NULL
     AND ABS(EXTRACT(EPOCH FROM (ss.generated_at - nl.published_at))) < 1800
    WHERE ss.news_log_id IS NULL
    GROUP BY ss.id
"""

_APPLY = "UPDATE sentiment_signals SET news_log_id = %s WHERE id = %s AND news_log_id IS NULL"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="write links (default: dry-run)")
    args = parser.parse_args()

    pg = PostgreSQLStore()
    try:
        conn = pg._get_connection()
        with conn.cursor() as cur:
            cur.execute(_FIND_CANDIDATES)
            rows = cur.fetchall()
        unambiguous = [(r[1], r[0]) for r in rows if r[2] == 1]
        print(f"signals without link matched: {len(rows)} "
              f"(unambiguous: {len(unambiguous)}, ambiguous skipped: {len(rows) - len(unambiguous)})")
        if not args.apply:
            print("dry-run — re-run with --apply to write")
            return
        with conn.cursor() as cur:
            for news_log_id, signal_id in unambiguous:
                cur.execute(_APPLY, (news_log_id, signal_id))
        conn.commit()
        print(f"linked {len(unambiguous)} signals")
    finally:
        pg.close()


if __name__ == "__main__":
    main()
```

- [x] **Step 2: Dry-run sull'ambiente locale (se il DB è attivo)**

Run: `docker compose exec -T worker python scripts/backfill_news_log_links.py`
Expected: stampa dei conteggi, nessuna scrittura. Riporta i numeri nel commit message. Esegui `--apply` SOLO se il dry-run mostra numeri plausibili (unambiguous > 0 e non superiore al totale segnali). Se il DB non è raggiungibile, committa lo script e segnala che il run va fatto al deploy.

- [x] **Step 3: Commit**

```bash
git add scripts/backfill_news_log_links.py
git commit -m "feat(scripts): conservative backfill of sentiment_signals.news_log_id (FIX-05)"
```

---

## Task 7: Frontend — sezione "Source Funnel & P&L" nella pagina Quality

**Files:**
- Modify: `frontend/src/api/quality.ts` (nuova fetch function — leggi prima il file e replica il pattern di `fetchQualityMetrics`)
- Modify: `frontend/src/pages/Quality.tsx` (nuova sezione)
- Test: `frontend/src/tests/source_verdict.test.ts` (nuovo — logica pura del verdetto)

- [x] **Step 1: Leggere i file target**

Leggi `frontend/src/api/quality.ts` e `frontend/src/pages/Quality.tsx` per intero. Replica ESATTAMENTE: il fetch helper usato (client API con auth header), lo stile inline (la pagina usa inline styles + componenti shared `KPICard`/`VerdictBox`), e il pattern `useQuery`.

- [x] **Step 2: Aggiungere tipi e fetch function**

In `frontend/src/api/quality.ts` aggiungi (adatta il nome del fetch helper a quello usato nel file):

```typescript
export interface SourceFunnelRow {
  source: string
  fetched: number
  queued: number
  duplicates: number
  discarded_no_ticker: number
  discarded_stale: number
  parse_fail: number
}

export interface SourceSignalRow {
  source: string
  n_signals: number
  mean_score: number | null
  near_zero_rate: number | null
  latency_p50_min: number | null
  latency_p95_min: number | null
}

export interface SourceTradeRow {
  source: string
  n_trades: number
  winners: number
  hit_rate: number | null
  total_net_pnl: number | null
  avg_net_pnl: number | null
}

export interface QualitySources {
  window_days: number
  funnel: SourceFunnelRow[]
  signals: SourceSignalRow[]
  trades: SourceTradeRow[]
  trace_coverage: { total?: number; linked?: number }
}

export async function fetchQualitySources(days = 14): Promise<QualitySources> {
  return apiFetch(`/api/quality/sources?days=${days}`)
}
```

- [x] **Step 3: Scrivere il test del verdetto (logica pura) — deve fallire**

Crea `frontend/src/tests/source_verdict.test.ts`:

```typescript
// ROADMAP_DATA_ALPHA §7.4 removal thresholds:
// remove if (hit-rate <40% AND P&L 30d <0) OR latency p50 >24h OR near-zero >50%.
import { describe, expect, it } from 'vitest'
import { sourceVerdict } from '@/pages/qualitySourceVerdict'

describe('sourceVerdict', () => {
  it('flags a source losing money with low hit rate', () => {
    expect(sourceVerdict({ hitRate: 0.29, totalPnl: -282, latencyP50Min: 60, nearZeroRate: 0.2 }).tone).toBe('bad')
  })
  it('flags a stale source even if P&L is flat', () => {
    expect(sourceVerdict({ hitRate: 0.5, totalPnl: 0, latencyP50Min: 25 * 60, nearZeroRate: 0.2 }).tone).toBe('bad')
  })
  it('warns on high near-zero rate', () => {
    expect(sourceVerdict({ hitRate: 0.5, totalPnl: 10, latencyP50Min: 60, nearZeroRate: 0.55 }).tone).toBe('bad')
  })
  it('passes a healthy source', () => {
    expect(sourceVerdict({ hitRate: 0.55, totalPnl: 120, latencyP50Min: 45, nearZeroRate: 0.2 }).tone).toBe('good')
  })
  it('is neutral without enough data', () => {
    expect(sourceVerdict({ hitRate: null, totalPnl: null, latencyP50Min: null, nearZeroRate: null }).tone).toBe('neutral')
  })
})
```

Run: `cd frontend && npx vitest run src/tests/source_verdict.test.ts`
Expected: FAIL (modulo inesistente). Se il progetto usa un comando test diverso, verifica in `frontend/package.json` → `scripts`.

- [x] **Step 4: Implementare il verdetto**

Crea `frontend/src/pages/qualitySourceVerdict.ts`:

```typescript
// Source removal thresholds from ROADMAP_DATA_ALPHA_2026-07-02 §7.4.
// Kept as a pure function so the policy is testable without rendering.
export interface SourceHealthInput {
  hitRate: number | null
  totalPnl: number | null
  latencyP50Min: number | null
  nearZeroRate: number | null
}

export function sourceVerdict(s: SourceHealthInput): { tone: 'good' | 'warn' | 'bad' | 'neutral'; reasons: string[] } {
  const reasons: string[] = []
  if (s.hitRate == null && s.totalPnl == null && s.latencyP50Min == null && s.nearZeroRate == null) {
    return { tone: 'neutral', reasons: ['no data yet'] }
  }
  if (s.hitRate != null && s.totalPnl != null && s.hitRate < 0.4 && s.totalPnl < 0) {
    reasons.push('hit-rate <40% with negative P&L — removal candidate')
  }
  if (s.latencyP50Min != null && s.latencyP50Min > 24 * 60) {
    reasons.push('latency p50 >24h — stale by design')
  }
  if (s.nearZeroRate != null && s.nearZeroRate > 0.5) {
    reasons.push('near-zero >50% — mostly wasted tokens')
  }
  if (reasons.length > 0) return { tone: 'bad', reasons }
  if ((s.hitRate != null && s.hitRate < 0.45) || (s.nearZeroRate != null && s.nearZeroRate > 0.4)) {
    return { tone: 'warn', reasons: ['borderline — keep under observation'] }
  }
  return { tone: 'good', reasons: ['healthy'] }
}
```

Run: `cd frontend && npx vitest run src/tests/source_verdict.test.ts`
Expected: 5 PASS.

- [x] **Step 5: Aggiungere la sezione alla pagina Quality**

In `frontend/src/pages/Quality.tsx`, aggiungi la query e la sezione. Query (accanto a quella esistente):

```typescript
const sourcesQ = useQuery({ queryKey: ['quality-sources', days], queryFn: () => fetchQualitySources(days) })
```

Sezione da renderizzare in fondo alla pagina (adatta lo stile alle tabelle/card già presenti nel file; sotto una versione minima coerente con gli inline styles del file):

```tsx
<h2 style={{ marginTop: 32 }}>Source Funnel &amp; P&amp;L</h2>
{sourcesQ.data && (
  <>
    <div style={{ fontSize: 12, color: '#64748b', marginBottom: 8 }}>
      trace coverage: {sourcesQ.data.trace_coverage.linked ?? '—'}/{sourcesQ.data.trace_coverage.total ?? '—'} signals linked to a news source
    </div>
    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13, marginBottom: 24 }}>
      <thead>
        <tr style={{ textAlign: 'left', borderBottom: '2px solid #cbd5e1' }}>
          <th>source</th><th>fetched</th><th>queued</th><th>dup</th>
          <th>no ticker</th><th>stale</th><th>parse fail</th>
          <th>signals</th><th>near-zero</th><th>lat p50</th>
          <th>trades</th><th>hit</th><th>P&amp;L</th><th>verdict</th>
        </tr>
      </thead>
      <tbody>
        {sourcesQ.data.funnel.map((f) => {
          const sig = sourcesQ.data!.signals.find((s) => s.source === f.source)
          const trd = sourcesQ.data!.trades.find((t) => t.source === f.source)
          const v = sourceVerdict({
            hitRate: trd?.hit_rate ?? null,
            totalPnl: trd?.total_net_pnl ?? null,
            latencyP50Min: sig?.latency_p50_min ?? null,
            nearZeroRate: sig?.near_zero_rate ?? null,
          })
          const tone = { good: '#166534', warn: '#854d0e', bad: '#991b1b', neutral: '#475569' }[v.tone]
          return (
            <tr key={f.source} style={{ borderBottom: '1px solid #e2e8f0' }}>
              <td style={{ fontWeight: 600 }}>{f.source}</td>
              <td>{f.fetched}</td><td>{f.queued}</td><td>{f.duplicates}</td>
              <td>{f.discarded_no_ticker}</td><td>{f.discarded_stale}</td><td>{f.parse_fail}</td>
              <td>{sig?.n_signals ?? '—'}</td><td>{pct(sig?.near_zero_rate)}</td>
              <td>{sig?.latency_p50_min != null ? `${Math.round(sig.latency_p50_min)}m` : '—'}</td>
              <td>{trd?.n_trades ?? '—'}</td><td>{pct(trd?.hit_rate)}</td>
              <td>{trd?.total_net_pnl != null ? `$${trd.total_net_pnl}` : '—'}</td>
              <td style={{ color: tone, fontWeight: 700 }} title={v.reasons.join('; ')}>{v.tone}</td>
            </tr>
          )
        })}
      </tbody>
    </table>
  </>
)}
```

Import in testa al file: `fetchQualitySources` da `@/api/quality`, `sourceVerdict` da `./qualitySourceVerdict`. Se la pagina non ha già una variabile `days`, usa il valore che passa a `fetchQualityMetrics`. Fonti presenti in `trades` ma non nel `funnel` (es. `unknown`): aggiungi una riga extra sotto la tabella o accetta la perdita per questa iterazione — annotalo nel commit.

- [x] **Step 6: Lint e build frontend**

Run: `cd frontend && npm run lint && npm run build`
Expected: nessun NUOVO errore lint nei file toccati (il progetto ha lint failure pre-esistenti: non peggiorarle); build OK.

- [x] **Step 7: Commit**

```bash
git add frontend/src/api/quality.ts frontend/src/pages/Quality.tsx frontend/src/pages/qualitySourceVerdict.ts frontend/src/tests/source_verdict.test.ts
git commit -m "feat(frontend): Source Funnel & P&L section on Quality page with removal-threshold verdicts (FIX-04)"
```

---

## Verifica finale

- [x] **Step 1: Suite completa backend**

Run: `pytest -q`
Expected: baseline + nuovi test, 0 nuove failure.

- [x] **Step 2: Test frontend**

Run: `cd frontend && npx vitest run`
Expected: tutti PASS (incluso il file f0 esistente).

- [x] **Step 3: Lint**

Run: `ruff check src/ tests/ scripts/`
Expected: 0 errori nei file toccati.

- [ ] **Step 4: Verifica end-to-end (se lo stack è attivo)**

1. Riavvia i worker: `docker compose restart worker worker-inference`
2. Attendi un run di ingestione (o trigger manuale del task GDELT), poi: `docker compose exec -T postgres psql -U alembic -d alembic -c "SELECT * FROM ingestion_stats_daily ORDER BY day DESC LIMIT 5;"`
3. Apri `/quality` nel frontend e verifica la nuova sezione.

- [ ] **Step 5: Riepilogo per il PO**

Riporta in chat: task completati, numeri del dry-run/apply del backfill (Task 6), coverage `trace_coverage` attuale, e cosa resta fuori scope (S2-2 `discarded_reason` logging — la colonna esiste da questo piano, il popolamento è il piano successivo; alerting EN-07).

---

## Fuori scope (esplicito)

- **S2-2** — popolare `discarded_reason` a ogni scarto (la colonna nasce qui, il logging è un piano dedicato).
- **EN-07** — alerting su degrado fonte (richiede prima che queste metriche accumulino storia).
- Qualunque azione sulle fonti in base ai verdetti (rimozione/riattivazione = decisione PO sulla base della dashboard).

## Riferimenti

- Review sorgente: `docs/FUNCTIONAL_REVIEW_2026-07-03.md` (§2.1, §9.1 problema #6)
- Roadmap dati: `docs/ROADMAP_DATA_ALPHA_2026-07-02.md` (FIX-04/05, EN-05/06, soglie §7.4)
- Piano Sprint 1 (prerequisito): `docs/superpowers/plans/2026-07-03-functional-review-remediation.md`
