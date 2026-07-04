# CHANGELOG — Alembic Trading System

Registro delle modifiche rilevanti al sistema (decisioni architetturali, nuove strategie, configurazioni).

---

## 2026-07-04

### S7 revival month — POC-1 primo run, POC-2 riavviato via Alpha Vantage (correzione)
- **POC-1 (small/mid PEAD):** INCONCLUSIVE_DATA — n=15 eventi con barre+liquidità, sotto il minimo n≥30 pre-registrato. Due bug di codice trovati e corretti in esecuzione (mismatch unità market-cap `_market_caps` USD grezzi vs `classify_cap` milioni; crash batch Alpaca su ticker preferred). Nessuna vera small-cap (<$2B) è sopravvissuta ai filtri barre IEX/liquidità.
- **POC-2 (transcript tone, ALPHA-A3):** riavviato in serata — i transcript FMP richiedono Ultimate ($99/mo, non acquistato), ma il piano corretto (`0e84850`) usa Alpha Vantage `EARNINGS_CALL_TRANSCRIPT` (free tier, 25 req/giorno, `ALPHAVANTAGE_API_KEY` in `.env`); il primo executor seguiva la versione pre-correzione del piano. POC-1 in ri-esecuzione su universo completo (era 600 simboli alfabetici su 6.177). Resume plan: `docs/superpowers/plans/2026-07-04-s7-revival-resume.md`.
- Report: `reports/s7_poc/S7_REVIVAL_DECISION_REPORT_2026-07-04.md` (+ dettaglio POC-1 `reports/s7_poc/POC1_smallmid_report_2026-07-04.md`). Decisione S7 (rimozione/espansione POC/upgrade Ultimate) pendente dal PO.

### Risk monitor — NAV ed esposizione reali (fix finding forense #2)
- `_fetch_account_state()` in `risk_monitor_task.py`: NAV = equity Alpaca reale (era: somma cumulativa net_pnl → NAV negativo −578$), `total_exposure` = valore lordo posizioni / equity (era: hardcoded 1.0 → falso alert "exposure 100% > 50%" ogni giorno). Broker irraggiungibile → (0, 0) con warning, niente falso alert. TDD: `tests/workers/test_risk_monitor_task.py` (5 test). Verificato end-to-end nel worker: report id=21, NAV $110.307, exposure 5,7%, 0 alert.

---

## 2026-07-03

### Sprint 1 — Functional Review Remediation (merged su main)
- **FIX-01/02**: MarketAux e RSS rimosse dal beat (net-negative: 0/20 winner, 0 news/17g); task env-gated.
- **FIX-03**: freshness event-time — skip pre-inferenza 12h→2h (`MAX_NEWS_AGE_HOURS`); `sentiment_signals.published_at` (migr. 032) gate-a l'entry S4 nel ciclo live (default `None` per gli altri caller — sell-protection/audit vedono segnali più vecchi by design).
- **EN-03**: dedup cross-source content-hash+ticker wired su tutti i punti di ingestione.
- **B13**: drawdown cap unificato — 5% da `trading.yaml`, rimosso hardcode 10% dal portfolio scheduler; doc allineate (exposure 50%, stop S4 2%).
- **B20**: `reconcile-fills-evening` puntava a `run_daily_report` → ora `run_reconcile_fills_intraday`.
- **Resolver**: enforcement conservativo ON — `NO_TRADE_NOT_TRADABLE` droppato pre-inferenza (fail-open, `RESOLVER_ENFORCE_NOT_TRADABLE`).
- **B12**: soglie reali nei gate di backtest (Sharpe ≥0.5 IS / ≥0.3 OOS; erano 0.0 tautologiche).

### S2-1 — Source P&L Funnel (merged su main)
- `ingestion_stats_daily` (migr. 033) + `news_log.{raw_ingested_at,content_hash,discarded_reason}`; contatori persistiti da ogni worker (fail-safe).
- `GET /api/quality/sources` + sezione "Source Funnel & P&L" sulla pagina Quality con verdetti alle soglie roadmap §7.4.
- Backfill conservativo `news_log_id`: 435 orfani, 0 match non ambigui (gap genuino) → bucket `unknown`.

### S7 PEAD — SHELVED (gate ALPHA-A5 FAIL conclusivo)
- Run FMP (workaround free-tier: backward-walk su `to`): 97 eventi, drift +1.96% ma **excess vs SPY +0.05% (mediana −1.07%)** = beta + 5 outlier; nessuna dose-response; small/mid non testato (n=0). Audit in `strategy_lifecycle_audit`; riapertura solo via decisione PO (universo small/mid o POC transcript-tone — FMP free tier blocca i transcript).

### Doc coherence pass
- README/ARCHITECTURE/operations/frontend-guide/API/user_guide allineati al codice (B15/B16/B19/B21-B25); beat schedule tables riscritte dalla fonte (`celery_app.py`); API key rimossa da AGENT.md; doc storici archiviati in `docs/archive/`.

---

## 2026-07-02

### Connettore GDELT DOC 2.0 — SHELVED (stesso problema del GKG: lag indexing)
- **Connettore implementato** `src/connectors/gdelt_doc.py` (`GdeltDocConnector`) + task `run_gdelt_doc_ingestion_worker` — 11 test TDD verdi.
- **SHELVED dopo mini-spike** (2026-07-02): **NON abilitare, NON aggiungere beat schedule.**
- **Root cause**: GDELT DOC 2.0 ha un lag di indexing di **≥2 giorni** (confermato: articoli più recenti nel feed = 30 giugno; oggi = 2 luglio). Il filtro `_SENTIMENT_MAX_NEWS_AGE_HOURS=12` del sentiment worker scarterebbe sempre il 100% degli articoli GDELT. Stessa causa del GKG (`gdelt_gkg.py` già dismesso per lag 24h).
- **Rilevanza bassa**: query `NVIDIA sourcelang:english` ha restituito "Eli Lilly Upgraded, Carvana Downgraded" — nessuna relazione con NVIDIA. Full-text search loose, peggiore di `org_lookup`.
- **Rate limit**: 5s/request per IP; burst → ban multi-ora. 96 simboli × 6s ≈ 10 min/ciclo.
- **Fonti attive**: `alpaca_benzinga` + `marketaux` coprono il need di freschezza e diversificazione. GDELT DOC non aggiunge valore.

### Fonti — MarketAux fix lag (bug connector) → riattivata diversificazione
- **Root cause**: MarketAux era silente (news di ~13 giorni fa, skippate dallo skip freschezza 12h). Non era un ritardo del free tier — il `fetch()` live non passava `sort`/`published_after`, quindi l'API restituiva il default (articoli vecchi). Test live: con `sort=published_on` MarketAux serve news di **oggi**.
- **Fix**: `fetch()` ora richiede `sort=published_on` + `published_after=(ora−12h)` + `filter_entities=true` → news fresche, on-topic, entity-tagged. Riattiva una **seconda fonte fresca e diversificata** (5000+ testate) accanto ad alpaca_benzinga → riduce il rischio di single-source/polarizzazione.

---

## 2026-07-01

### Fix da analisi e2e del 2026-07-01 (giornata +$68, ma 3 affinamenti)
- **SKIP_STALE meno rumoroso**: la lookback a 96h del ciclo ri-scansiona segnali vecchi ogni 15 min → un segnale di 40h (es. INTC 0.451 di ~2gg prima) veniva loggato ogni ciclo come "appena scaduto" (94% dei 399 SKIP_STALE di ieri). Ora `_record_stale_drops` logga solo i segnali scaduti *da poco* (entro `_STALE_LOG_RECENT_BUFFER_H`=1h da max_age). (`b2c0f54`)
- **Floor order-gate a 0.30**: quando `feedback:entry_threshold` scade (TTL 48h), il gate cadeva al prefiltro `min_score 0.10` → segnali deboli tradavano (SPCX 0.180). Ora fa floor al `loss_feedback.threshold_baseline` (0.30). (`b2c0f54`)
- **Reversal non si fida dei fallback**: `_sentiment_reversal_sells` forzava un SELL leggendo solo lo score, anche su un **FinBERT fallback** (parte quando l'ensemble diverge → inaffidabile). Es. SPCX venduto su fallback −0.573 → perdita −20.23. Ora ignora i segnali `fallback_used`. Fix generale (tutte le posizioni).
- **Nota fonti** (side-effect): lo skip freschezza (24h→12h) ha silenziato GDELT e MarketAux perché le loro news sono intrinsecamente vecchie (GDELT ~24h+ lag GKG, MarketAux ~9 giorni). Resta solo alpaca_benzinga (fresco+pulito). Da decidere consapevolmente + indagare il lag MarketAux.

### Fonti — Finnhub aggiunto poi SHELVED dopo mini-spike
- **Analisi fonti** (via ricerca): principio "explicit tagging > NER > none". Aggiunto `FinnhubNewsConnector` (company-news US, ticker taggati dalla fonte, free tier) + breakdown precision per `extraction_method` nell'harness (`validate_ticker_sentiment.py`) per decidere data-driven su GDELT.
- **Mini-spike (verdict: SHELVE)**: un fetch reale ha prodotto **2115 articoli/fetch** (5,5× il throughput del worker ~16/h → flood) con **rilevanza larga** (news generiche/listicle/competitor taggate all'azienda, es. "Best CD rates" → GS, "31 Single-Stock ETFs" → TSM; ~40-60% issuer-specific). Conclusione: il *ticker* è pulito (source-tagged, no NER nostro) ma la *rilevanza* no → non è un win e floodderebbe la coda.
- **Azione**: Finnhub **shelved** — schedule beat rimossa + guard `FINNHUB_INGESTION_ENABLED` (default off). Connector/task/test restano pronti. Riabilitare SOLO con cap per-simbolo + filtro rilevanza.
- **Reframe**: il collo di bottiglia reale è il **throughput del worker**, non il numero di fonti. La leva è rilevanza/precisione per articolo, non volume.

---

## 2026-06-30

### Operations Navigation + Auto-Improve Gate Counterfactuals
- **Frontend**: `Config`, `Admin` e `System` sono unificati nella nuova pagina `Operations` con tab dedicate; i vecchi URL fanno redirect verso `Operations?tab=...`. La sidebar segue il flusso operativo: Overview → Operations → News → Signals → Quality → Trading → Performance → Strategies → Auto-Improve → ricerca/strumenti.
- **Auto-Improve**: Phase B è presentata come feedback gate. La pagina distingue la soglia effettivamente applicata dal portfolio scheduler da `regime_scale`, che resta legacy/audit finché non viene cablato nel sizing portfolio.
- **Counterfactual**: Phase C include `SKIP_THRESHOLD` oltre a `SKIP_EMA` e `SKIP_CAP`; restano esclusi `SKIP_STALE`, `SKIP_FALLBACK` e `SKIP_POSITION`.
- **Docs**: aggiornata documentazione API, architettura, user guide e frontend operator guide per riflettere Operations e i nuovi counterfactual gate.

### S4 dev-doc punti 1-3 (da `docs/archive/2026-06-07-oneoff/S4_TICKER_SENTIMENT_DEV_INSTRUCTIONS_2026-06-30.md`)
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
