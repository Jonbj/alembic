# Prompt per Review con Claude Code

Copia questo testo intero in una nuova sessione Claude Code per eseguire la review completa.

---

```
Esegui una review completa del commit `6a33d6c` su `main` per la feature
"Multi-Asset News-Driven Architecture". Segui esattamente le istruzioni
qui sotto.

## 1. SKILL DA INVOCARE — in questo ordine

1. `superpowers:verification-before-completion` — per verificare che tutti i
   test passino e non ci siano regressioni prima di qualsiasi giudizio.
2. `superpowers:requesting-code-review` — per strutturare la review secondo
   gli standard del progetto.

## 2. FILE DA LEGGERE PRIMA DI INIZIARE

Leggi nell'ordine:
1. `CLAUDE.md` — vincoli architetturali NON negoziabili
2. `docs/superpowers/specs/2026-05-13-multi-asset-news-driven-design.md`
3. `docs/superpowers/plans/2026-05-13-multi-asset-news-driven.md`
4. `docs/superpowers/reviews/2026-05-13-multi-asset-review-instructions.md`
   — istruzioni dettagliate con checklist per ogni file
5. `docs/superpowers/reviews/2026-05-13-multi-asset-news-driven-review.md`
   — documento dello sviluppatore

## 3. COMANDI DA ESEGUIRE

```bash
# Verifica suite completa
pytest --tb=short -q
# Atteso: 464 passed

# Verifica componenti specifici
pytest tests/connectors/test_deduplicator.py -v
pytest tests/test_config.py::TestWatchlistSymbols -v
pytest tests/connectors/test_gdelt.py tests/connectors/test_gdelt_historical.py -v
pytest tests/connectors/test_gdelt_gkg.py -v
pytest tests/connectors/test_ticker_extractor.py -v
pytest tests/workers/test_ingestion_worker.py -v
pytest tests/workers/test_performance_worker.py::TestFetchAllSignalsForIC::test_fetch_all_signals_uses_watchlist_symbols -v

# Verifica DB migration e seed
python -c "
import psycopg2, os
os.environ['DATABASE_URL'] = 'postgresql://trading:trading@localhost:5432/trading'
c = psycopg2.connect(os.environ['DATABASE_URL'])
cur = c.cursor()
cur.execute(\"SELECT count(*) FROM ticker_lookup\")
print('ticker_lookup rows:', cur.fetchone()[0])
cur.execute(\"SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename='ticker_lookup'\")
print('table exists:', bool(cur.fetchone()))
c.close()
"
```

## 4. FILE DA CONTROLLARE — checklist

### Nuovi file
- `src/connectors/gdelt_base.py` — mixin backoff condiviso
- `src/connectors/gdelt_gkg.py` — connector GKG v2
- `src/connectors/ticker_extractor.py` — lookup PG ticker
- `src/workers/ingestion.py` — NewsIngestionWorker Celery
- `migrations/004_add_ticker_lookup.sql` — DDL tabella
- `data/sp500_tickers.csv` — seed data
- `scripts/seed_ticker_lookup.py` — seed script
- `tests/connectors/test_gdelt_gkg.py` — 7 test
- `tests/connectors/test_ticker_extractor.py` — 12 test
- `tests/workers/test_ingestion_worker.py` — 5 test

### Modificati
- `src/models/news.py` — GKGNewsItem
- `src/connectors/deduplicator.py` — is_duplicate_by_id
- `src/connectors/gdelt.py` — eredita da _GDELTBaseConnector
- `src/config.py` — WATCHLIST_SYMBOLS
- `src/workers/celery_app.py` — beat schedule ingestion
- `src/workers/performance.py` — simboli da config
- `tests/test_config.py` — 3 test WATCHLIST_SYMBOLS
- `tests/connectors/test_deduplicator.py` — 3 test is_duplicate_by_id
- `tests/workers/test_performance_worker.py` — 1 test wire-up

## 5. VINCOLI ARCHITETTURALI DA VERIFICARE

- [ ] Zero chiamate LLM sincrone nel loop di trading
- [ ] Nessuna chiamata bloccante in next() di Backtrader o confirm_trade_entry() di Freqtrade
- [ ] Input sanitization: sanitize_text() applicato prima di costruire prompt LLM
- [ ] SQL parametrizzato: zero f-string o concatenazione nelle query
- [ ] SentimentWorker NON modificato (src/workers/sentiment.py invariato)
- [ ] ALLOWED_MODEL_IDS validation se presente nuovi client LLM
- [ ] Articoli senza ticker scartati silenziosamente (DEBUG, non WARNING)
- [ ] Deduplicazione su (url, ticker) per supportare articoli multi-ticker
- [ ] GDELTConnector esistente non rotto (9/9 test passano)

## 6. OUTPUT RICHIESTO

Scrivi un report in questo formato esatto:

```markdown
# Review Report — Multi-Asset News-Driven Architecture

**Reviewer:** <nome modello>
**Data:** <data>
**Commit:** 6a33d6c

## Verdict
- [ ] APPROVED
- [ ] APPROVED with minor notes
- [ ] CHANGES REQUESTED

## Checklist risultati
- [ ] Tutti i test passano (464/464)
- [ ] Nessuna violazione dei vincoli architetturali
- [ ] Nessun problema di sicurezza rilevato
- [ ] Codice leggibile e ben commentato

## Test eseguiti
<Sommario dei test run e risultati>

## File-by-file notes
<Per ogni file controllato, una riga con stato: OK / NOTE / ISSUE>

## Issue dettagliate (se presenti)
<File:line_number — descrizione del problema — severità>
```

NON approvare se:
- Un qualsiasi test fallisce
- Un vincolo architetturale è violato
- Trovi SQL injection, XSS, o altre vulnerabilità OWASP top 10
- Il SentimentWorker è stato modificato
- Ci sono import circolari o dipendenze mancanti

Se trovi un problema, descrivilo con precisione (file:line_number) e
richiedi CHANGES REQUESTED. Non correggere autonomamente.
```

---

**Come usarlo:**
1. Apri una nuova sessione Claude Code nel repository.
2. Incolla l'intero blocco qui sopra (dalle triple-backtick in poi).
3. Attendi che Claude invochi le skill e completi la review.
