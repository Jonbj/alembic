# Multi-Asset News-Driven Architecture — Design Spec

**Date:** 2026-05-13
**Status:** Approved

## Obiettivo

Passare da un'architettura **symbol-driven** (watchlist fissa, ogni connettore riceve `asset_tags` espliciti) a una **news-driven** (GDELT scopre automaticamente i ticker tramite entity tag GKG + lookup table PostgreSQL). L'universo è aperto: qualsiasi ticker trovato nella lookup table (~600 simboli: S&P 500 + ETF principali) può ricevere un segnale.

## Decisioni di design

| Domanda | Decisione |
|---|---|
| Universo simboli | Aperto — S&P 500 + ETF (~600 simboli) |
| Articoli senza ticker | Scartati |
| Lookup table storage | PostgreSQL (`ticker_lookup`) |
| Cadenza ingestion worker | Ogni 15 minuti (allineato con SentimentWorker) |
| Approccio entity extraction | GDELT GKG API + lookup PG — solo per GDELT |
| RSS e SEC Edgar | Invariati — rimangono symbol-driven con `asset_tags` espliciti, nessuna extraction necessaria |

## Architettura e flusso dati

```
[GDELT GKG API]  →  GDELTGKGConnector
                           ↓ org_names: ["Apple Inc", "Microsoft Corp", ...]
                     TickerExtractor
                           ↓ lookup PG: {company_name → ticker}
                           ↓ nessun match → scarta
                     NewsItem(asset_tags=["AAPL"])
                           ↓
[RSS feeds]      →  RSSConnector (invariato, asset_tags espliciti)
                           ↓
[SEC Edgar]      →  SecEdgarConnector (invariato, CIK → ticker già gestito)
                           ↓
              NewsIngestionWorker (Celery, ogni 15 min)
                           ↓ Deduplicator (chiave: url+ticker)
                      news:queue (Redis)
                           ↓
              SentimentWorker (invariato)
```

Il `SentimentWorker` rimane completamente invariato: legge `asset_tags[0]` dalla coda come oggi.

## Componenti nuovi

### 1. `src/connectors/gdelt_gkg.py` — `GDELTGKGConnector`

Usa l'endpoint GDELT GKG v2 (`api/v2/gkg/gkg`) in modalità `gkg`. Il campo `V2Organizations` restituisce nomi di organizzazioni già disambiguati da GDELT (non estratti dal testo grezzo).

**Query GDELT:**
```
sourcelang:english (theme:ECON_STOCKMARKET OR theme:COMPANY_EARNINGS OR theme:ECON_MERGE OR theme:ECON_BANKRUPTCY)
```

**Nuovo dataclass:**
```python
class GKGNewsItem(NewsItem):
    org_names: list[str] = []  # da V2Organizations (split su ";")
```

**Backoff:** condivide la logica `_fetch_with_backoff` estratta in `_GDELTBaseConnector` (refactor del `GDELTConnector` esistente, nessun cambio comportamentale esterno).

**Parsing:**
- `V2Organizations` → split su `";"` → strip whitespace → lista org names
- `extras.PageTitle` → titolo articolo
- Timestamp invalido → articolo scartato (stesso comportamento del connettore attuale)

### 2. `src/connectors/ticker_extractor.py` — `TickerExtractor`

Mappa una lista di org names GDELT a ticker tramite lookup PG.

**Matching:** case-insensitive exact match dopo normalizzazione:
- Lowercase
- Strip suffissi societari: `Inc`, `Corp`, `Ltd`, `LLC`, `Co`, `S.p.A.`, `plc`, `Group`, `Holdings`

**Algoritmo:**
1. Normalizza ogni `org_name`
2. `SELECT ticker FROM ticker_lookup WHERE lower(company_name) = ANY(%(normalized_names)s)`
3. Fallback: `SELECT ticker FROM ticker_lookup WHERE %(name)s = ANY(aliases)` per varianti storiche (es. "Apple Computer" → AAPL)
4. Nessun match → lista vuota → articolo scartato

**Interfaccia:**
```python
class TickerExtractor:
    def __init__(self, pg_conn): ...
    def extract(self, org_names: list[str]) -> list[str]: ...
    @staticmethod
    def normalize(name: str) -> str: ...
```

### 3. `src/workers/ingestion.py` — `run_news_ingestion_worker`

Task Celery schedulato ogni 15 minuti.

**Flusso:**
1. `GDELTGKGConnector.fetch()` → `GKGNewsItem` list
2. Per ogni item: `TickerExtractor.extract(org_names)` → lista ticker
3. Articolo con N ticker → N `NewsItem` separati (uno per ticker)
4. `RSSConnector.fetch()` → `NewsItem` già annotati (invariato)
5. Deduplicazione su chiave `(url, ticker)` — stessa istanza `Deduplicator`
6. `Redis LPUSH "news:queue"` per ogni item deduplicato

**Statistiche restituite:**
```python
{"fetched": int, "tickers_found": int, "discarded": int, "queued": int, "duplicates": int}
```

**Nota multi-ticker:** un articolo che menziona Apple e Microsoft genera due `NewsItem` distinti con `id=f"{url}:{ticker}"`. La deduplicazione usa questa chiave composta, non solo l'URL.

## Database

### Migrazione: `migrations/006_add_ticker_lookup.sql`

```sql
CREATE TABLE ticker_lookup (
    id           SERIAL PRIMARY KEY,
    company_name TEXT NOT NULL,
    aliases      TEXT[] NOT NULL DEFAULT '{}',
    ticker       TEXT NOT NULL,
    source       TEXT NOT NULL  -- 'sp500', 'etf', 'manual'
);
CREATE INDEX idx_ticker_lookup_name ON ticker_lookup (lower(company_name));
CREATE INDEX idx_ticker_lookup_aliases ON ticker_lookup USING GIN (aliases);
```

### Seed: `scripts/seed_ticker_lookup.py`

Carica S&P 500 + ETF principali da `data/sp500_tickers.csv` (committato nel repo). Eseguito una volta al deploy, aggiornabile manualmente per aggiungere alias o nuovi simboli.

## Modifiche al codice esistente

### `src/connectors/gdelt.py`
- Estrae `_fetch_with_backoff` in `_GDELTBaseConnector` (classe base condivisa con `GDELTGKGConnector`)
- Nessun cambio di comportamento esterno, nessun cambio ai test esistenti

### `src/config.py`
```python
WATCHLIST_SYMBOLS: list[str] = trading_cfg.get("symbols", {}).get("watchlist", [])
```
Connette `symbols.watchlist` da `config/trading.yaml` (attualmente ignorato).

### `src/workers/performance.py:78`
```python
# Prima
symbols = ["AAPL", "MSFT", "GOOGL", "NVDA", "SPY", "QQQ"]
# Dopo
symbols = config.WATCHLIST_SYMBOLS
```

### `src/workers/celery_app.py`
```python
"run-news-ingestion": {
    "task": "src.workers.ingestion.run_news_ingestion_worker",
    "schedule": crontab(minute="*/15"),
}
```

## Testing

### `GDELTGKGConnector`
- Parsing `V2Organizations` corretto (semicolon-split, strip whitespace)
- `extras.PageTitle` usato come titolo
- Timestamp invalido → articolo scartato
- HTTP 429 → backoff + retry (riusa fixture esistenti)

### `TickerExtractor`
- Match esatto case-insensitive → ticker corretto
- Normalizzazione suffissi societari ("Apple Inc." → "apple" → AAPL)
- Match su alias ("Apple Computer" → AAPL)
- Nessun match → lista vuota
- Org names vuoti → lista vuota (no query DB)

### `NewsIngestionWorker`
- Articolo con 2 org → 2 `NewsItem` in queue con ticker distinti
- Articolo senza ticker → 0 item accodati
- Duplicato `(url, ticker)` → deduplicator blocca
- Statistiche restituite corrette

### `performance.py`
- `_fetch_all_signals_for_ic` usa `config.WATCHLIST_SYMBOLS` (non lista hardcoded)

## Invarianti e vincoli

- Il `SentimentWorker` non viene modificato
- Nessuna chiamata LLM sincrona nel loop di esecuzione
- Articoli senza ticker vengono scartati silenziosamente (log a DEBUG, non WARNING)
- La deduplicazione usa chiave composta `(url, ticker)` per supportare articoli multi-ticker
- Il `GDELTGKGConnector` non sostituisce il `GDELTConnector` esistente — coesistono: il `GDELTConnector` (artlist) rimane disponibile per backfill storico e backtesting, il `GDELTGKGConnector` è usato esclusivamente dal `NewsIngestionWorker` per ingestion live
