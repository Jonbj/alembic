# Istruzioni per Review — Multi-Asset News-Driven Architecture

**Destinatario:** Agente di review (qualsiasi modello LLM)  
**Data:** 2026-05-13  
**Commit da revieware:** `main@6a33d6c`  
**Obiettivo:** Verificare correttezza, sicurezza, e conformità ai vincoli architetturali del progetto.

---

## 1. PRIMA DI TUTTO — Leggi questi file in ordine

1. **Questo documento** (`docs/superpowers/reviews/2026-05-13-multi-asset-review-instructions.md`)
2. **`CLAUDE.md`** — vincoli architetturali NON negoziabili
3. **`docs/superpowers/specs/2026-05-13-multi-asset-news-driven-design.md`** — specifica di design approvata
4. **`docs/superpowers/plans/2026-05-13-multi-asset-news-driven.md`** — piano di implementazione (task-by-task)
5. **`docs/superpowers/reviews/2026-05-13-multi-asset-news-driven-review.md`** — documento di review dello sviluppatore

Non iniziare la review senza aver letto tutti e cinque.

---

## 2. FILE DA CONTROLLARE — con checklist per file

### 2a. Nuovi file (creati ex-novo)

#### `src/connectors/gdelt_base.py`
- [ ] `_GDELTBaseConnector` è un mixin (non ABC), con metodo `_fetch_with_backoff`.
- [ ] Parametri di backoff hardcoded: BASE=2.0, MAX=60.0, RETRIES=5.
- [ ] Il metodo gestisce HTTP 429 con exponential backoff e ritorna `None` su fallimento permanente.
- [ ] `aiohttp.ClientSession` è passato dal caller (lifecycle gestito esternamente).
- [ ] **NON** deve essere usato da solo — deve essere ereditato.

#### `src/connectors/gdelt_gkg.py`
- [ ] `GDELTGKGConnector` eredita da `_GDELTBaseConnector` **e** `NewsConnector`.
- [ ] `_GDELT_GKG_QUERY` contiene solo temi finanziari in inglese.
- [ ] `fetch()` usa `async with aiohttp.ClientSession()` internamente (session lifecycle interno, OK perché è una fetch singola non chunked).
- [ ] `_parse_record()` salta record con `V2DocumentIdentifier` vuoto.
- [ ] `_parse_record()` salta record con timestamp non parsabile (look-ahead bias prevention).
- [ ] `V2Organizations` è split su `;` con strip e rimozione stringhe vuote.
- [ ] `extras.PageTitle` è passato a `sanitize_text()` prima di entrare nel modello.
- [ ] `asset_tags` è sempre `[]` nel GKGNewsItem prodotto.
- [ ] Il connector non fa chiamate LLM né query DB.

#### `src/connectors/ticker_extractor.py`
- [ ] `TickerExtractor.__init__` riceve una connessione PG, non un URL.
- [ ] `extract()` ritorna `[]` se `org_names` è vuoto (no query DB).
- [ ] Primary lookup: `lower(company_name) = ANY(%s)` con lista normalizzata.
- [ ] Fallback lookup: `aliases && %s::text[]` con nomi originali.
- [ ] **Nessuna interpolazione di stringhe nelle query SQL** — solo parametrizzato.
- [ ] `normalize()` strip suffissi societari (`Inc`, `Corp`, `Ltd`, `Co`, …) e punteggiatura.
- [ ] Risultato deduplicato con `dict.fromkeys()` (ordine preservato).
- [ ] `extract()` è side-effect-free rispetto al DB (solo SELECT).

#### `src/workers/ingestion.py`
- [ ] `_fetch_gkg_items()` è una funzione async separata per testabilità.
- [ ] `_process_gkg_items()` è una funzione pura (testabile senza Celery).
- [ ] Per ogni articolo con N ticker, crea N `NewsItem` con `id="{url}:{ticker}"`.
- [ ] Articoli senza ticker vengono scartati (stats["discarded"] incrementato).
- [ ] Deduplicazione usa `is_duplicate_by_id(item)` (chiave composta).
- [ ] `redis_client.rpush("news:queue", item.model_dump_json())` — serializzazione corretta Pydantic v2.
- [ ] Stats dict contiene tutte e 5 le chiavi: `fetched`, `tickers_found`, `discarded`, `queued`, `duplicates`.
- [ ] `run_news_ingestion_worker()` apre Redis e PG, li chiude in `finally`.
- [ ] `@app.task(name="src.workers.ingestion.run_news_ingestion_worker")` — nome task esplicito.
- [ ] **Il task NON chiama mai un LLM.**

#### `migrations/004_add_ticker_lookup.sql`
- [ ] Tabella `ticker_lookup` con colonne: `id`, `company_name`, `aliases`, `ticker`, `source`.
- [ ] `company_name` è TEXT NOT NULL.
- [ ] `aliases` è TEXT[] NOT NULL DEFAULT '{}'.
- [ ] `ticker` è TEXT NOT NULL.
- [ ] `source` è TEXT NOT NULL.
- [ ] Indice unique su `(lower(company_name), ticker)`.
- [ ] Indice su `lower(company_name)`.
- [ ] Indice GIN su `aliases`.

#### `data/sp500_tickers.csv`
- [ ] Header: `company_name,ticker,source,aliases`.
- [ ] `aliases` separati da `|` (pipe).
- [ ] Source è `sp500` o `etf`.
- [ ] Almeno 50 righe (seed reale).

#### `scripts/seed_ticker_lookup.py`
- [ ] Legge da `DATA_PATH` relativo allo script (`../data/sp500_tickers.csv`).
- [ ] Split aliases su `|` con strip.
- [ ] INSERT con `ON CONFLICT (lower(company_name), ticker) DO NOTHING`.
- [ ] SQL parametrizzato — nessuna f-string o concatenazione.
- [ ] Conta `cur.rowcount` per reportare righe inserite.
- [ ] Richiede `DATABASE_URL` env var, esce con errore se mancante.

---

### 2b. File modificati (refactor / wire-up)

#### `src/models/news.py`
- [ ] `GKGNewsItem` eredita da `NewsItem`.
- [ ] `GKGNewsItem.org_names` è `list[str]` con default `[]`.
- [ ] `LLMSentimentOutput` non è stato rimosso o modificato.

#### `src/connectors/deduplicator.py`
- [ ] `is_duplicate_by_id()` è aggiunto, non sostituisce `is_duplicate()`.
- [ ] Usa chiave `dedup:id:{sha256(item.id)}` con stesso TTL di 2 ore.
- [ ] `is_duplicate_by_id` spiega nel docstring **perché** esiste (multi-ticker dedup).
- [ ] `is_duplicate()` non è stato modificato (verificare che `return result is None` sia presente).

#### `src/connectors/gdelt.py`
- [ ] `GDELTConnector` dichiara eredità da `_GDELTBaseConnector` e `NewsConnector`.
- [ ] `_fetch_with_backoff` è rimosso (logica spostata nel mixin).
- [ ] La chiamata in `fetch_historical` passa `url=_GDELT_DOC2_URL`.
- [ ] Nessun cambio di firma pubblica (`fetch()`, `fetch_historical()`).
- [ ] Nessun cambio di comportamento esterno.

#### `src/config.py`
- [ ] `WATCHLIST_SYMBOLS` è aggiunto come `list[str]`.
- [ ] Valore default caricato da `config/trading.yaml` (`symbols.watchlist`).
- [ ] `_load_trading_yaml()` gestisce file mancante (ritorna `{}`).
- [ ] `yaml` importato in cima al file.

#### `src/workers/celery_app.py`
- [ ] Nuovo entry `run-news-ingestion` nel beat schedule.
- [ ] Task name: `src.workers.ingestion.run_news_ingestion_worker`.
- [ ] Schedule: `crontab(minute="*/15", hour="14-21", day_of_week="1-5")`.
- [ ] Allineato con `sentiment-worker` (stesse ore e giorni).

#### `src/workers/performance.py`
- [ ] `symbols = config.WATCHLIST_SYMBOLS` sostituisce la lista hardcoded.
- [ ] `config` è già importato in cima al file.
- [ ] Nessun altro cambio funzionale.

---

## 3. ARCHITETTURA — Flusso dati da verificare

```
[GDELT GKG API]  →  GDELTGKGConnector.fetch()
                           ↓ org_names: ["Apple Inc", "Microsoft Corp"]
                     TickerExtractor.extract()
                           ↓ lookup PG: {company_name → ticker}
                           ↓ nessun match → scarta (log DEBUG)
                     NewsItem(asset_tags=["AAPL"])
                           ↓
[RSS feeds]      →  RSSConnector (invariato, asset_tags espliciti)
                           ↓
[SEC Edgar]      →  SecEdgarConnector (invariato)
                           ↓
              NewsIngestionWorker (Celery, ogni 15 min)
                           ↓ Deduplicator.is_duplicate_by_id (chiave: url:ticker)
                      news:queue (Redis LPUSH)
                           ↓
              SentimentWorker (invariato — legge asset_tags[0])
```

**Verificare che:**
- [ ] Il `SentimentWorker` non è stato toccato.
- [ ] Nessun nuovo componente effettua chiamate LLM.
- [ ] Nessun componente effettua chiamate bloccanti nel loop di trading.

---

## 4. INVARIANTI E VINCOLI — checklist architetturale

| Vincolo | Come verificare |
|---|---|
| **Zero chiamate LLM sincrone nel loop di trading** | Controllare che `NewsIngestionWorker` non importi né usi alcun modulo LLM. Il SentimentWorker non è modificato. |
| **Async discipline (nessun I/O bloccante in next()/confirm_trade)** | `GDELTGKGConnector` usa `aiohttp` (async). `TickerExtractor` query PG sono nel worker Celery, mai nel loop di esecuzione. |
| **Input sanitization** | `sanitize_text()` è chiamato su `PageTitle` in `GDELTGKGConnector._parse_record`. |
| **SQL parametrizzato** | `TickerExtractor.extract()` usa `cur.execute(sql, params)`. Zero f-string o concatenazione nelle query. |
| **SentimentWorker NON modificato** | `src/workers/sentiment.py` non compare nella lista file modificati. |
| **Articoli senza ticker scartati silenziosamente** | `stats["discarded"]` incrementato; nessun log WARNING (deve essere DEBUG o assente). |
| **Deduplicazione su `(url, ticker)`** | `is_duplicate_by_id` con ID composto `f"{url}:{ticker}"`. Test `test_ingestion_worker_multi_ticker_article` verifica che due ticker dallo stesso articolo generano due item separati. |
| **GDELTConnector esistente non rotto** | Eseguire `pytest tests/connectors/test_gdelt.py tests/connectors/test_gdelt_historical.py -v` — tutti devono passare. |

---

## 5. TEST — Comandi da eseguire

**Suite completa:**
```bash
pytest --tb=short -q
```
**Atteso:** 464 passed, 0 failed.

**Test specifici per componente:**
```bash
# Task 3 — Deduplicator + GKGNewsItem
pytest tests/connectors/test_deduplicator.py -v

# Task 4 — Config WATCHLIST_SYMBOLS
pytest tests/test_config.py::TestWatchlistSymbols -v

# Task 5 — GDELT refactor (nessuna regressione)
pytest tests/connectors/test_gdelt.py tests/connectors/test_gdelt_historical.py -v

# Task 6 — GDELT GKG
pytest tests/connectors/test_gdelt_gkg.py -v

# Task 7 — TickerExtractor
pytest tests/connectors/test_ticker_extractor.py -v

# Task 8 — NewsIngestionWorker
pytest tests/workers/test_ingestion_worker.py -v

# Task 9 — Performance wire-up
pytest tests/workers/test_performance_worker.py::TestFetchAllSignalsForIC::test_fetch_all_signals_uses_watchlist_symbols -v
```

**Test di integrazione DB:**
```bash
# Verificare che la migration sia applicata
python -c "
import psycopg2, os
os.environ['DATABASE_URL'] = 'postgresql://trading:trading@localhost:5432/trading'
c = psycopg2.connect(os.environ['DATABASE_URL'])
cur = c.cursor()
cur.execute(\"SELECT count(*) FROM ticker_lookup\")
print('Rows:', cur.fetchone()[0])
c.close()
"
```
**Atteso:** Rows: 57 (o il numero effettivo di righe nel CSV seedato).

---

## 6. OUTPUT DELLA REVIEW

Al termine, scrivi un report in questo formato:

```markdown
# Review Report — Multi-Asset News-Driven Architecture

**Reviewer:** <modello/name>
**Data:** 2026-05-13
**Commit:** 6a33d6c

## Verdict
[ ] APPROVED
[ ] APPROVED with minor notes
[ ] CHANGES REQUESTED

## Checklist risultati
- [ ] Tutti i test passano (464/464)
- [ ] Nessuna violazione dei vincoli architetturali
- [ ] Nessun problema di sicurezza rilevato
- [ ] Codice leggibile e ben commentato

## Note (se presenti)
- <eventuali osservazioni, domande, o suggerimenti>
```

---

## 7. SE TROVI UN PROBLEMA

1. **Fermati** — non approvare se c'è un test che fallisce o un vincolo violato.
2. **Segnala** — descrivi il problema con file:line_number e il motivo.
3. **Non correggere da solo** — lascia allo sviluppatore originale la scelta di fixare o discutere.
