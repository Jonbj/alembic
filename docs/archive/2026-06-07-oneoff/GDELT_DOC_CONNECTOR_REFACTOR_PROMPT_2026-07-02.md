# Prompt — Refactoring del connettore GDELT (GKG bulk CSV → DOC 2.0 API)

> Data: 2026-07-02 · Destinatario: modello di sviluppo (Sonnet) · Fonte: analisi fonti Alembic

---

## Task: refactoring del connettore GDELT — da GKG bulk CSV a DOC 2.0 API

### Contesto
Il connettore GDELT attuale (`src/connectors/gdelt_gkg.py`) scarica i file **GKG bulk CSV**
(`data.gdeltproject.org/gdeltv2/lastupdate.txt`), che:
- NON hanno parametri di query → si scarica tutto il feed globale e si filtra localmente;
- estrae i ticker via **org_lookup** (nomi organizzazione → ticker) = la principale fonte di
  **false-positive ticker** del sistema (precision estrazione ~0.24);
- ha un **lag ~24h** (le news arrivano vecchie) → oggi vengono skippate dal filtro freschezza.

Vogliamo passare alla **GDELT DOC 2.0 API** (`api.gdeltproject.org/api/v2/doc/doc`), che è
**interrogabile per ticker** e supporta freschezza e ordinamento — così GDELT diventa una terza
fonte fresca, mirata e diversificata (news mondiali, 100+ lingue) accanto ad alpaca_benzinga e
marketaux.

### API DOC 2.0 (pubblica, nessuna API key)
- Endpoint: `https://api.gdeltproject.org/api/v2/doc/doc`
- Parametri chiave:
  - `query` — termini di ricerca (es. `"Apple Inc" sourcelang:english`)
  - `mode=artlist` — lista articoli
  - `timespan` — finestra recente (min 15 min; es. `12h`, `1d`)
  - `sort=DateDesc` — più recenti prima
  - `maxrecords` — fino a 250 (NOI dobbiamo tenerlo BASSO, vedi sotto)
  - `format=json`
- Risposta (artlist json): array `articles` con campi `title`, `url`, `domain`, `seendate`
  (formato `YYYYMMDDTHHMMSSZ`), `language`, `sourcecountry`. **NON c'è il body**: solo headline
  + metadati (limite noto → sentiment headline-level).

### Requisiti di design
1. **Nuovo connettore** `src/connectors/gdelt_doc.py` con classe `GdeltDocConnector(NewsConnector)`
   (implementa `src/connectors/base.py`: `async def fetch() -> AsyncIterator[NewsItem]`).
   NON modificare il vecchio `gdelt_gkg.py` (resta disponibile ma dismesso).
2. **Query per-ticker mirata**: per ogni simbolo watchlist, interroga per **nome azienda**
   (il testo degli articoli usa i nomi, non i ticker). Usa la mappa nome↔ticker già presente:
   `SecCompanyTickers` in `src/connectors/ticker_resolver_providers.py` (ha i dizionari
   name→ticker / ticker→name), oppure la tabella `ticker_lookup`. Se non trovi il nome, fai
   fallback al ticker come cashtag `$TICKER`. Aggiungi `sourcelang:english` alla query.
3. **Tag esplicito**: taggare ogni articolo al ticker **interrogato** (`asset_tags=[ticker]`),
   con `extraction_method="gdelt_doc"` (nuovo valore, distinto da `org_lookup`). NB: è un
   keyword-match → può avere false-positive (es. "Apple" frutto/azienda): li gestisce a valle
   il resolver-shadow; non serve risolverli qui, ma la query dev'essere il più precisa possibile.
4. **Freschezza**: `timespan=12h` (allineato a `_SENTIMENT_MAX_NEWS_AGE_HOURS=12` nel sentiment
   worker) + `sort=DateDesc`. Mappare `seendate` → `NewsItem.timestamp` (tz-aware UTC).
5. **CONTROLLO VOLUME (critico)**: `maxrecords` BASSO per ticker (es. **5**). Lezione appresa:
   un mini-spike di Finnhub ha prodotto **2115 articoli/fetch** (5.5× il throughput del worker
   ~16/h) → flood della coda. Il worker sentiment processa ~16 item/h: NON inondarlo. Con 96
   ticker × 5 = max ~480/fetch, ma con dedup (Redis TTL 2h) e timespan i nuovi/fetch sono pochi.
   Rendi `maxrecords` un parametro del costruttore (default 5).
6. **Throttle**: `asyncio.sleep(~1s)` tra le query (96 richieste; GDELT ha rate limit soft).
   Gestisci 429/errori fail-open (skip il ticker, non crashare).
7. **Body**: dato che la DOC artlist non dà il body, usa il `title` come `body` del NewsItem
   (headline-level). Skippa articoli con title vuoto.

### Pattern da seguire (coerenza col codebase)
- Mirrora `src/connectors/finnhub_news.py` (aggiunto di recente): struttura fetch async +
  aiohttp + `_parse_article` + throttle + `NewsItem(..., extraction_method=..., source="gdelt")`.
- Modello: `src/models/news.py` (`NewsItem`: id, body, title, url, timestamp, source, asset_tags,
  extraction_method, language).

### Ingestion + sicurezza-by-default
8. Aggiungi in `src/workers/ingestion.py`: `_fetch_gdelt_doc_items`, `_process_gdelt_doc_items`
   (mirror di `_process_finnhub_items`), `run_gdelt_doc_ingestion_worker`.
9. **Gate di sicurezza** (lezione Finnhub): il task deve essere **OFF di default** dietro
   `GDELT_DOC_INGESTION_ENABLED` (env, default "0" → ritorna `{"skipped": True}`), come già
   fatto per `FINNHUB_INGESTION_ENABLED`. NON aggiungere la schedule beat finché non è verificato.
10. Il vecchio `run_gdelt_ingestion_worker` (GKG) va lasciato ma NON deve girare in parallelo
    a questo (evita doppio GDELT).

### Mini-spike di verifica (obbligatorio prima di dichiarare fatto)
Come per Finnhub: dopo aver costruito il connettore, esegui un fetch reale su ~5-10 ticker della
watchlist e RIPORTA: (a) volume totale, (b) freschezza (età mediana degli articoli), (c) qualità/
rilevanza (per 2-3 ticker, i titoli sono davvero sull'azienda o generici?). Se il volume esplode
o la rilevanza è larga (come Finnhub), proponi cap/filtri prima di abilitare.

### Vincoli
- TDD: test per `_parse_article` (seendate→timestamp, title vuoto→None, tag+extraction_method) e
  `fetch` mockato (aiohttp), mirrando `tests/connectors/test_finnhub_news.py`. Throttle mockato.
- Fail-open ovunque; nessuna eccezione deve propagarsi al worker.
- Non rompere i test esistenti. La suite dei connettori deve restare verde.
- Commit atomici; NON usare `git add -A` (working tree condiviso); aggiungi solo i file toccati.

### File attesi
- Nuovo: `src/connectors/gdelt_doc.py`, `tests/connectors/test_gdelt_doc.py`
- Modifica: `src/workers/ingestion.py` (task + guard), `docs/CHANGELOG.md`
- (Beat: NON aggiungere finché il mini-spike non conferma volume/qualità)

### Definition of Done
1. `GdeltDocConnector` interroga per ticker con timespan+sort+maxrecords, tagga esplicitamente,
   `extraction_method="gdelt_doc"`, fail-open, throttle.
2. Task ingestion OFF di default dietro `GDELT_DOC_INGESTION_ENABLED`.
3. Test verdi (parse + fetch mockato).
4. Mini-spike eseguito e riportato (volume/freschezza/rilevanza) con raccomandazione se abilitare.
5. CHANGELOG aggiornato.

---

## Note per chi coordina (contesto Alembic, non parte del prompt operativo)
- Il pipeline a valle: news → sentiment ensemble (Kimi+GLM) → signal (`score=polarity×confidence`)
  → resolver-shadow (`news_resolved_entities`) → ranking S4 → gate feedback (floor 0.30) → ordini.
- `extraction_method` è tracciato in `news_log` (QT-03) e l'harness `scripts/validate_ticker_sentiment.py`
  fa il breakdown precision per-metodo → misureremo `gdelt_doc` vs `source_metadata` con QX-01.
- Fonti attuali: `alpaca_benzinga` (fresco+pulito), `marketaux` (fixato 2026-07-02, fresco+diverso),
  `finnhub` (SHELVED — flood+rilevanza larga), `gdelt_gkg` (dismesso — org_lookup rumoroso + lag 24h).
