# Istruzioni per Review — GKG Historical Backtest Pipeline

**Destinatario:** Agente di review (qualsiasi modello LLM)  
**Data:** 2026-05-13  
**Commit da revieware:** `main@8fb2932`  
**Obiettivo:** Verificare correttezza, sicurezza, e conformita ai vincoli architetturali del progetto.

---

## 1. PRIMA DI TUTTO — Leggi questi file in ordine

1. **Questo documento** (`docs/superpowers/reviews/2026-05-13-gkg-backtest-review-instructions.md`)
2. **`CLAUDE.md`** — vincoli architetturali NON negoziabili
3. **`docs/superpowers/specs/2026-05-13-gkg-backtest-design.md`** — specifica di design approvata
4. **`docs/superpowers/plans/2026-05-13-gkg-backtest.md`** — piano di implementazione (task-by-task)

Non iniziare la review senza aver letto tutti e quattro.

---

## 2. FILE DA CONTROLLARE — con checklist per file

### 2a. Nuovi file (creati ex-novo)

#### `migrations/005_add_backtest_signals.sql`
- [ ] Tabella `backtest_signals` con 15 colonne come da design spec.
- [ ] `score` e `forward_return_*` sono `DOUBLE PRECISION` (nullable).
- [ ] `fallback_used` BOOLEAN NOT NULL DEFAULT FALSE.
- [ ] `generated_at` TIMESTAMPTZ NOT NULL.
- [ ] Indice UNIQUE su `(run_id, symbol, article_url, generated_at)`.
- [ ] Indice su `(run_id, symbol, generated_at)`.
- [ ] Indice parziale su `(run_id, score) WHERE score IS NULL`.

#### `src/backtest/forward_returns.py`
- [ ] `ForwardReturns` dataclass con tre campi nullable.
- [ ] `ForwardReturnCalculator.__init__` riceve connessione PG.
- [ ] `populate()` scarica prezzi 1h e 1d una sola volta per ticker.
- [ ] `_download_prices()` espande start/end di ±1/±2 giorni per coprire edge signals.
- [ ] `_download_prices()` gestisce DataFrame vuoto e Exception per ticker singoli.
- [ ] `_compute_returns()` trova barra >= ts con `searchsorted`.
- [ ] `_compute_returns()` accetta barra entro 30 min dal target (DST/offset).
- [ ] `_compute_returns()` ritorna None per 1h/4h/24h quando barra mancante.
- [ ] **Nessuna interpolazione** — mai "inventare" prezzi.
- [ ] SQL UPDATE e SELECT sono parametrizzati.

#### `src/backtest/report.py`
- [ ] `BacktestReport` dataclass con IC/ICIR a tre orizzonti.
- [ ] `BacktestReport.to_dict()` serializza ICResult e ICIRResult correttamente.
- [ ] `BacktestReportBuilder.build()` usa `_MIN_SAMPLES = 30`.
- [ ] `build()` esclude righe con `fallback_used=True` dal calcolo IC.
- [ ] Per-horizon extraction usa lista index `[r1h, r4h, r24h]`.
- [ ] Per-model breakdown calcolato solo su orizzonte 24h.
- [ ] `signals_with_returns` = max count tra i tre orizzonti.

#### `scripts/run_backtest.py`
- [ ] CLI argparse con `--start`, `--end`, `--run-id`, `--dry-run`, `--max-per-chunk`.
- [ ] Fase 1: `fetch_historical` → `TickerExtractor.extract()` → INSERT pending.
- [ ] INSERT con `ON CONFLICT DO NOTHING` (idempotenza).
- [ ] Fase 2: SELECT `score IS NULL` per checkpoint/resume automatico.
- [ ] Fase 2 dry-run: scrive `score=0.0` senza chiamare LLM.
- [ ] Fase 2 live: stima costo, prompt utente se > $10.
- [ ] Fase 2 live: usa `run_inference()` (estratto da sentiment.py).
- [ ] Fase 3: delega a `ForwardReturnCalculator.populate()`.
- [ ] Fase 4: stampa report stdout + salva JSON in `reports/`.
- [ ] Connessione PG aperta in `main()`, chiusa in `finally`.
- [ ] **Nessuna chiamata LLM in main()** — solo in `phase2_infer`.

#### `tests/backtest/test_forward_returns.py`
- [ ] 8 test: 1h, 4h, 24h, missing 1h bar, missing daily close, after last bar, no price data, populate DB update.

#### `tests/backtest/test_backtest_report.py`
- [ ] 5 test: three horizons IC, below min samples, by-model, exclude None returns, JSON serialization.

#### `tests/backtest/test_backtest_runner.py`
- [ ] 4 test: cost estimate scales, dry-run writes zero, checkpoint skips scored, SQL filters by run_id.

---

### 2b. File modificati

#### `src/connectors/gdelt_gkg.py`
- [ ] `fetch_historical()` aggiunto come metodo async.
- [ ] Chunking mensile con `STARTDATETIME` / `ENDDATETIME`.
- [ ] `asyncio.sleep(1.0)` tra chunk (rate limit GDELT).
- [ ] Dicembre → Gennaio rollover gestito correttamente.
- [ ] `_parse_record()` condiviso tra `fetch()` e `fetch_historical()`.

#### `src/workers/sentiment.py`
- [ ] `run_inference()` estratta come funzione pura (no store writes).
- [ ] `process_news_item()` è wrapper sottile: chiama `run_inference()` + store writes.
- [ ] `run_inference()` gestisce budget exhausted, ensemble divergence, e generic Exception.
- [ ] `run_inference()` registra spending per ogni modello nell'ensemble.
- [ ] **Nessuna modifica al comportamento di `process_news_item()` rispetto a prima**.

#### `tests/connectors/test_gdelt_gkg.py`
- [ ] 4 nuovi test per `fetch_historical`: chunks by month, sleeps 1s, skips bad records, empty response continues.

#### `tests/workers/test_sentiment_worker.py`
- [ ] 4 nuovi test per `run_inference`: ensemble success, divergence, budget exhausted, no store writes.

---

## 3. ARCHITETTURA — Flusso dati da verificare

```
[CLI: run_backtest.py]
    ↓
Phase 1: GDELTGKGConnector.fetch_historical(start, end)
    ↓ monthly chunks
TickerExtractor.extract(org_names)
    ↓
INSERT INTO backtest_signals (run_id, symbol, ..., score=NULL)
    ↓
Phase 2: SELECT pending rows (score IS NULL)
    ↓
run_inference(NewsItem) → SentimentResult
    ↓
UPDATE backtest_signals SET score=..., model_id=...
    ↓
Phase 3: ForwardReturnCalculator.populate(run_id)
    ↓ yfinance download once per ticker
UPDATE backtest_signals SET forward_return_1h=..., ...
    ↓
Phase 4: BacktestReportBuilder.build(run_id)
    ↓
compute_composite_ic() / compute_icir() (reused from src/performance/ic.py)
    ↓
stdout report + reports/backtest_{run_id}.json
```

**Verificare che:**
- [ ] `run_inference()` non scrive mai su Redis o PostgreSQL.
- [ ] Il backtest usa il **medesimo** codice inference del live worker.
- [ ] Nessun nuovo componente effettua chiamate bloccanti nel loop di trading.

---

## 4. INVARIANTI E VINCOLI — checklist architetturale

| Vincolo | Come verificare |
|---|---|
| **Zero chiamate LLM sincrone nel loop di trading** | `run_backtest.py` è CLI offline. `run_inference()` è async ma chiamata via `asyncio.run()` nel CLI, mai nel loop di esecuzione. |
| **Async discipline** | `fetch_historical()` è async (aiohttp). `run_inference()` è async. Nessun I/O bloccante in next()/confirm_trade. |
| **Input sanitization** | `sanitize_text()` era già presente in `_parse_record()` del GKG connector (non modificato in questo branch). |
| **SQL parametrizzato** | Tutte le query in `forward_returns.py`, `report.py`, `run_backtest.py` usano `%s` placeholders. Zero f-string o concatenazione. |
| **run_inference estratta correttamente** | `process_news_item()` delega a `run_inference()` e poi fa store writes. `run_inference()` resta side-effect-free. |
| **No interpolazione prezzi** | `_compute_returns()` ritorna `None` per barre mancanti. Mai interpolazione. |
| **Checkpoint/resume** | `phase2_infer` SELECT filtra `score IS NULL`. Righe parzialmente completate vengono saltate automaticamente. |

---

## 5. TEST — Comandi da eseguire

**Suite completa:**
```bash
pytest --tb=short -q
```
**Atteso:** 489 passed, 0 failed.

**Test specifici per componente:**
```bash
# Task 2 — fetch_historical
pytest tests/connectors/test_gdelt_gkg.py -v

# Task 3 — run_inference
pytest tests/workers/test_sentiment_worker.py -v

# Task 4 — ForwardReturnCalculator
pytest tests/backtest/test_forward_returns.py -v

# Task 5 — BacktestReportBuilder
pytest tests/backtest/test_backtest_report.py -v

# Task 6 — CLI runner
pytest tests/backtest/test_backtest_runner.py -v
```

**Test di integrazione DB:**
```bash
python -c "
import psycopg2, os
os.environ['DATABASE_URL'] = 'postgresql://trading:trading@localhost:5432/trading'
c = psycopg2.connect(os.environ['DATABASE_URL'])
cur = c.cursor()
cur.execute(\"SELECT column_name FROM information_schema.columns WHERE table_name = 'backtest_signals' ORDER BY ordinal_position\")
print('Columns:', [r[0] for r in cur.fetchall()])
c.close()
"
```
**Atteso:** 15 colonne listate.

---

## 6. OUTPUT DELLA REVIEW

Al termine, scrivi un report in questo formato:

```markdown
# Review Report — GKG Historical Backtest Pipeline

**Reviewer:** <modello/name>
**Data:** 2026-05-13
**Commit:** 8fb2932

## Verdict
[ ] APPROVED
[ ] APPROVED with minor notes
[ ] CHANGES REQUESTED

## Checklist risultati
- [ ] Tutti i test passano (489/489)
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
