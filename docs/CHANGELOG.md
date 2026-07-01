# CHANGELOG — Alembic Trading System

Registro delle modifiche rilevanti al sistema (decisioni architetturali, nuove strategie, configurazioni).

---

## 2026-06-30

### Operations Navigation + Auto-Improve Gate Counterfactuals
- **Frontend**: `Config`, `Admin` e `System` sono unificati nella nuova pagina `Operations` con tab dedicate; i vecchi URL fanno redirect verso `Operations?tab=...`. La sidebar segue il flusso operativo: Overview → Operations → News → Signals → Quality → Trading → Performance → Strategies → Auto-Improve → ricerca/strumenti.
- **Auto-Improve**: Phase B è presentata come feedback gate. La pagina distingue la soglia effettivamente applicata dal portfolio scheduler da `regime_scale`, che resta legacy/audit finché non viene cablato nel sizing portfolio.
- **Counterfactual**: Phase C include `SKIP_THRESHOLD` oltre a `SKIP_EMA` e `SKIP_CAP`; restano esclusi `SKIP_STALE`, `SKIP_FALLBACK` e `SKIP_POSITION`.
- **Docs**: aggiornata documentazione API, architettura, user guide e frontend operator guide per riflettere Operations e i nuovi counterfactual gate.

### S4 dev-doc punti 1-3 (da `S4_TICKER_SENTIMENT_DEV_INSTRUCTIONS_2026-06-30.md`)
- **(1) Soglie unificate + documentate**: `docs/strategies.md` riscritto col vero chain di gating live (freshness → prefiltro ranker `min_score 0.10`/`min_confidence 0.30` → **order gate** `feedback:entry_threshold` 0.30/dyn → ranking top-N), con tabella "Threshold map" che distingue i 3 concetti e segna il gate legacy `score>0.30 AND EMA20` come INATTIVO sotto `engine=portfolio`. Commento di chiarezza in `S4Config` (min_score = prefiltro, non order threshold). Corretti anche i modelli ensemble nel doc (Kimi+GLM-5.2 cloud, non Qwen/locale).
- **(2) Resolver in SHADOW (Fase A)**: nuovo `news_resolved_entities` (migr. 031) + `src/connectors/resolver_shadow.py` + `pg_store.write_resolved_entity`. Il worker sentiment calcola e **persiste** la risoluzione ticker deterministica (decision/confidence/ambiguity/directness/tradable + evidenze) per ogni news, **senza gating** del signal live (offline, fail-safe, flag `RESOLVER_SHADOW_ENABLED`). Prepara la misura precision resolver vs `news_labels`.
- **(3) Decision Log — `SKIP_STALE`**: i signal **forti** (|score| ≥ min_score) scartati per età (> max_age 4h) vengono registrati in `execution_decisions` (`decision=SKIP_STALE`, reason con età+score), così si vede quando si "perde" un segnale buono per scadenza. Frontend: label + help aggiornati.

### Signals page — evidenzia i segnali sopra soglia
- **Feat**: la colonna Score della pagina Signals evidenzia in **verde ✓** i segnali con `|score| ≥ soglia feedback gate` (soglia live da `/feedback/status`, default 0.35); legenda con la soglia corrente. Colpo d'occhio su quali segnali superano il gate senza incrociare Auto-Improve.

### Decision Log — visibilità signal scartati al feedback gate
- **Feat**: i signal scartati dal feedback gate S4 (score < soglia) vengono ora registrati in `execution_decisions` con `decision=SKIP_THRESHOLD` e `reason` (es. "score 0.180 < feedback threshold 0.350"). Prima sparivano senza traccia → nei giorni senza trade il Decision Log era vuoto e non si distingueva "valutati e scartati" da "nessun signal". Nuovo helper `_record_gate_drops` (fail-safe); frontend: label + help aggiornati (`SKIP_THRESHOLD`).

### Sentiment Worker — skip news stantie + drenaggio backlog (e2e fix)
- **Root cause** (diagnosi e2e): `news:queue` è FIFO e il worker (4 item/run, ~16/h) era **~13 giorni indietro** (item più vecchio 17 giu). Generava signal su news di 2 settimane fa con `generated_at=now()` → sentiment stantio iniettato nel ciclo live come se fosse fresco, tutto troppo debole per superare il feedback gate. Sintomo osservato: "signal con data di oggi ma nessun decision log".
- **Fix**: il worker ora pesca finché non ha **4 item freschi**, saltando senza chiamata LLM gli item più vecchi di `_SENTIMENT_MAX_NEWS_AGE_HOURS` (24h), con cap `_MAX_QUEUE_SCAN_PER_RUN=5000`. Gli item saltati vengono scartati da `news:processing` (anche nel ramo all-stale, altrimenti la crash-recovery li ri-accodava in loop). 5 test su `_is_stale_news`. (`28638f9`)
- **Risultato live**: backlog drenato **9309 → 835** in ~3 run (saltati ~8500 item vecchi); item più vecchio in coda ora ~24h invece di 13 giorni; il worker processa di nuovo news recenti.
- **Nota residua**: throughput ~16 signal/h (latenza LLM) < ingestion → la coda fresca si processa parzialmente e gli item invecchiati >24h vengono ora saltati. Da approfondire separatamente.

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
