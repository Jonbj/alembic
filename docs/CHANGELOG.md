# CHANGELOG — Alembic Trading System

Registro delle modifiche rilevanti al sistema (decisioni architetturali, nuove strategie, configurazioni).

---

## 2026-06-30

### Signal Selection — ensemble non sovrascritto da fallback FinBERT
- **Fix**: `fetch_signals_for_cycle` ora preferisce il segnale **ensemble** più recente al FinBERT fallback nella finestra 4h (`ORDER BY symbol, fallback_used ASC, generated_at DESC`). Prima si prendeva solo il più recente per simbolo, quindi un fallback debole generato dopo un ensemble forte lo sovrascriveva (es. AMKR +0.638 alle 15:16 → +0.009 fallback alle 15:48), facendo cadere il simbolo sotto soglia. Il fallback si usa solo se non c'è ensemble nella finestra. (`10c7836`)

### Watchlist S4 — +5 simboli (91 → 96)
- Aggiunti **ROKU, RDDT, HOOD, WDC, SPCX**: nomi off-watchlist con segnali ensemble forti **ricorrenti** su 14g (es. ROKU 4×≥0.35 avg 0.38), prima non tradabili perché il ciclo portfolio carica solo i simboli in watchlist. Il sentiment per questi nomi era già calcolato via estrazione entity/cashtag dalle news. Correttezza estrazione non ancora validata su QX-01 — rivedere dopo l'annotazione. (`38be96b`)

### Qualità & misurazione (QX-01 / QX-02) + igiene dati
- Golden label set: tabella `news_labels`, sampling stratificato (148), **UI Labeling blind** (`/labeling`), forward-return da Alpaca historical, harness `validate_ticker_sentiment.py`; **dashboard Quality** (`/quality`). (`9d21215`, `537471f`, `0dcf4da`)
- Igiene dati: QS-06 (`eligible` reale), QS-07 (backtest/live parity), QT-03 (`news_log.extraction_method`), QS-09 (backfill `news_log_id`), QS-10 (logging strutturato fallimenti ensemble), QS-03 (agreement→confidence, dietro flag). Dettaglio e stato in `docs/S4_NEWS_PIPELINE_RND_BACKLOG_2026-06-29.md`.

### Sentiment Worker — Observability Ollama semaphore
- **Feat**: notifica Telegram rate-limited (max 1 ogni 30 min) quando tutti i modelli ensemble vanno in timeout (`raw_outputs=[]`). Il messaggio include il comando di recovery esatto.
  - Nuova funzione `_maybe_notify_ollama_timeout()` in `src/workers/sentiment.py`.
  - `run_inference` ora usa reasoning `"FinBERT fallback (Ollama timeout)"` vs `"FinBERT fallback (ensemble divergence)"` per distinguere i due scenari.
  - 6 test TDD in `tests/workers/test_ollama_timeout_alert.py`.
- **Fix**: auto-recovery del semaphore Redis se tutti gli slot sono stati perduti (`LLEN==0`). Il worker li ripristina all'avvio del task successivo senza intervento manuale (sicuro: `worker-inference` ha `concurrency=1`).
  - Nuova funzione `_recover_ollama_semaphore_if_leaked()` in `src/workers/sentiment.py`.
  - 5 test TDD in `tests/workers/test_ollama_sem_recovery.py`.
- **Fix**: slot semaphore Ollama ridotti da 3 → 2 (ensemble ha 2 modelli; max 2 call parallele per item).
- **Root cause analisi** (2026-06-29 ore 21:xx UTC): Ollama API era UP ma il semaphore Redis era a 0/3 slot per leak da task killati da `SoftTimeLimitExceeded` (4 item × 270s/item > soft_limit 600s). Recovery manuale eseguito (`DEL ollama:sem ollama:sem:init`), ora automatico.

### Documentazione
- Aggiunta review qualitativa estrazione ticker + sentiment: `docs/TICKER_SENTIMENT_QUALITY_REVIEW_2026-06-30.md`

---

## 2026-06-29

### Portfolio Scheduler — Anti-stale-ranker-sell guard
- **Bug fix**: posizioni con segnale fresco positivo venivano vendute quando `CrossSectionalRanker` ritornava `{}` pesi per vincolo `min_stocks=2` (es. solo 1 segnale a forza positiva tra i 2 che passano il gate assoluto). L'orchestratore interpretava `merged_weights={}` come "sell all" per le posizioni correnti.
  - Root cause: il gate `abs(score) >= threshold` ammette segnali negativi (es. MU -0.4185) che passano il gate ma vengono scartati dal ranker long-only (`strength = score*confidence <= 0`). Con 1 candidato positivo < `min_stocks=2` il ranker ritorna vuoto.
  - Fix: nuovo `_fresh_signal_protected_symbols()` — protegge le posizioni aperte con segnale fresco >= threshold da SELL senza attributazione di strategy.
  - 8 test TDD aggiunti in `tests/workers/test_protected_sell.py`.
- **Fix**: falso alert Telegram "Execution fill divergence: 0/0 orders submitted" su cicli idle (nessun ordine pianificato). Il check viene ora saltato quando `final_count==0`.

### LLM Ensemble
- **Qwen3.5 sostituito da GLM-5.2**: Qwen3.5 estraeva ticker in modo aggressivo (es. MU da notizia macro); GLM-5.2 ha reasoning long-horizon migliore per analisi macroeconomica.
- Ensemble attivo: Kimi K2.6 + GLM-5.2 (2 modelli); fallback weights `{kimi-k2.6:cloud: 0.50, glm-5.2:cloud: 0.50}`.

---

## 2026-06-17

### Documentazione
- Riorganizzazione completa docs/: archiviate ~25 file obsoleti in `docs/archive/`
- Aggiornati: ARCHITECTURE.md, strategies.md, operations.md, API.md, CLAUDE.md, DECISIONS.md
- Creati: docs/strategies/s7-pead.md, docs/CHANGELOG.md, docs/llm-config.md

---

## 2026-06-16

### Modifiche
- **Worker split**: separato `worker-inference` (concurrency=1, queue `inference`) da `worker` (concurrency=4, queue `celery`) per isolare FinBERT/Ollama
- **Redis cycle lock**: aggiunto `SET portfolio:cycle:lock NX EX 840` in `portfolio_scheduler.py` per prevenire run concorrenti
- **Hold minimum 30 min**: filtro SELL su simboli comprati negli ultimi 30 minuti (previene roundtrip S4→S1)
- **FinBERT int8 quantization**: `torch.quantization.quantize_dynamic` applicato al load di FinBERT (~50% RAM reduction)
- **Daily analysis script**: `scripts/daily_analysis.sh` con cron 14:30 CEST lun-ven, output su Telegram

### LLM Ensemble
- DeepSeek-V4-Pro rimosso (OOM + latency eccessiva)
- GLM-5.1 rimosso (IC inferiore a Kimi K2.6 in A/B test)
- **Attivi**: Kimi K2.6, Qwen3.5

---

## 2026-06-15

### Code Review
- Review completa del codebase: vedi `archive/2026-06-p0-p2-controlled-paper-history/02_external_reviews/CODE_REVIEW_FULL_2026-06-15.md` (archived 2026-06-23)
- Identificati 13 fix prioritari ora tracciati in `docs/superpowers/plans/2026-06-16-master-roadmap.md`

---

## 2026-06-07

### Nuova Strategia
- **S7 PEAD** aggiunto: classifica 8-K filing SEC via Ollama, cattura Post-Earnings Announcement Drift
- Allocazione target: 15%
- Worker: `src/workers/pead_worker.py`
- Beat task: `pead-ingestion` (queue `inference`, ogni 30 min 14:05-21:35 UTC)

---

## 2026-06-06

### Bug Fix (P0/P1)
- Connection leak in PostgreSQL store: aggiunto `finally: pg.close()` in tutti i task Celery
- `asyncio.run()` in contesto async: sostituito con `await` corretto
- N+1 queries: batch query per simboli multipli
- Race condition PostgreSQL: aggiunto `FOR UPDATE` su operazioni critiche
- Vedi `archive/2026-06-p0-p2-controlled-paper-history/02_external_reviews/CODE_REVIEW_FULL_2026-06-15.md` per lista completa (archived 2026-06-23)

---

## 2026-05-26

### Backtest
- Completato backtest GKG novembre 2025 (run-id: gkg-nov25-v1)
- IC/ICIR analizzato; S2 disabilitata definitivamente (OOS IC = −0.55, tutti i gate falliti)

---

## 2026-05-18

### Frontend
- Dashboard React aggiunta: Overview, Signals, Trades, Performance, LLM, Admin
- Backend FastAPI: routes per trades, signals, decisions, performance, analytics

---

## 2026-05-13

### Infrastruttura
- GDELT GKG bulk ingestion implementata (`src/connectors/gdelt_gkg.py`)
- A/B test GDELT completato: GKG > standard per IC (~15% improvement)
- Multi-asset news-driven pipeline completata

---

## 2026-05-03

### Foundation
- Sistema LLM Alpha Miner implementato (pipeline offline)
- FinBERT sentiment + Ollama ensemble (4 modelli, poi ridotti a 2)
- Backtrader backtesting framework
- Celery + Redis + PostgreSQL stack operativo
- Portfolio Orchestrator (Phase G): weight-then-order multi-strategy cycle
