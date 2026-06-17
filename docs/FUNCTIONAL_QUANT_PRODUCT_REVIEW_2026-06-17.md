# Alembic — Analisi Funzionale, Quant e Prodotto

**Review in read-only · Principal Functional Analyst + Quant Research Reviewer + Product Strategist**

- Data review: 2026-06-17
- Modalità: read-only, nessuna modifica al codice, nessun commit, nessun comando mutante, nessun ordine/script live eseguito.
- Ogni proposta implementativa è trasformata in requisito/ticket, non in patch.
- Le affermazioni senza riscontro nel codice sono esplicitamente segnalate (`?` = non verificato).
- Nuovi alpha trattati come ipotesi da falsificare, non come alpha validato.
- Priorità a robustezza, auditabilità e risk control sul rendimento teorico.
- Costo del falso positivo assunto alto.

---

## FASE 1 — Inventario

### 1.1 Mappa del sistema attuale

**Stack operativo**
- Backend: FastAPI + Celery (beat + 2 worker: `general` concurrency=4, `inference` concurrency=1) + Redis 7 + PostgreSQL 16. Containerized via `docker-compose.yml` (8 servizi: postgres, redis, api, worker, worker-inference, beat, frontend, grafana, backtest on-demand).
- Frontend: React + TanStack Query, 17 pagine, 13 client API tipizzati per dominio, componenti condivisi (Layout/Sidebar/ModeBadge/DataTable/KPICard/DirectionBadge/HelpButton/ErrorBoundary).
- LLM "Alpha Miner": pipeline offline/background; esecuzione legge segnali pre-calcolati da Redis/PG. **Il vincolo non-negoziabile "LLM mai nel hot path" è RISPETTATO** (verificato in executor/portfolio_scheduler/strategies/api: nessuna chiamata LLM sincrona in esecuzione).
- Sentiment: FinBERT (fallback, int8 quantizzato) + ensemble Ollama; score = polarity × confidence (verificato corretto in `src/llm/finbert.py`).
- Broker: Alpaca via `alpaca-py` diretto (nessun adapter astratto); paper/live via substring `"paper-api" in config.ALPACA_BASE_URL`.
- Auth: JWT (Bearer) + X-API-Key duale; bcrypt per admin.

**Strategie**
- S1 Time-Series Momentum Multi-Asset — **live 50%** (OOS Sharpe ~0.51, 5/5 gate passati).
- S2 VRP — research, **disabilitata 0%** (config dice "tutti gate falliti" ma gate 5 in realtà passato → config inesatta).
- S3 Cross-Sectional Residual Momentum — research, **disabilitata 0%** (gate 3/5 falliti, sospetto sizing lookahead).
- S4 News-Driven Tactical LLM — **paper 10%** (capped fino a gate report — che però è rotto).
- S7 PEAD — codice presente, **non cablato** all'esecuzione; ingestion EDGAR rotta (solo metadati).

**Backtest**: ibrido IC vectorizzato + orchestratore event-driven; DataReplay point-in-time gate; walk-forward IS/OOS; 5 gate (G1 Significance, G2 Walkforward, G3 Robustness, G4 Regime, G5 Stress).

**Risk machinery**: ConstraintEnforcer (5 vincoli), PortfolioRiskMonitor, PortfolioVolTargeter, DecayMonitor, kill-switch (Redis), loss-feedback, Brinson attribution.

**Costi**: RealisticCostModel (commissione $0, fee SEC/FINRA, spread a tier, square-root impact k=10) — ma il volume non è mai passato → impatto trascurabile (modello sottostima i costi reali del live).

### 1.2 Fonti analizzate

Codice: `src/strategies/{registry,__init__}.py`, `s7/strategy.py`; `src/workers/{celery_app,portfolio_scheduler,pead_worker}.py`; `src/portfolio/orchestrator.py`; `src/store/pg_store.py`; `src/llm/finbert.py`; `src/connectors/sec_edgar.py`; `src/api/routes/{system_routes,pead_routes}.py`; `src/api/{auth,jwt_utils}.py`; frontend `Layout.tsx, ModeBadge.tsx, client.ts, Overview.tsx, Strategies.tsx, SystemLog.tsx, api/system.ts`.
Config: `config/strategies.yaml, workers.yaml, trading.yaml`.
Infra: `docker-compose.yml`, `.github/workflows/ci.yml`, `scripts/daily_analysis.sh`, `scripts/run_s4_gate_report.py`.
Migrations: `001, 013, 016, 020, 021`.
Docs: `docs/superpowers/plans/2026-06-16-master-roadmap.md`.
Sottosistemi coperti da 5 agenti read-only (strategies, backend, backtest/risk, data/LLM, store/API) + indagine diretta su frontend/infra/config/migrations/tests.

### 1.3 Aree non analizzate / ambigue

- **Frontend pagine non lette singolarmente**: Admin, AutoImprove, Backtest, Config, Docs, LLM, News, Performance, Signals, Trades, Trading, LoginPage (sondaggio strutturale effettuato, non deep-read di ognuna).
- **Sorgenti dati di mercato**: non verificato se i prezzi OHLCV provengono da Alpaca, Polygon, o altro; non verificata la gestione di split/dividendi/adjusted-close a livello di data provider.
- **Modello di costi live effettivi**: RealisticCostModel esiste ma non verificato se applicato nel live o solo backtest; impatto square-root con volume=0 di fatto disattivato.
- **Stato reale dei test**: 33 fallimenti rilevati ma non mappati uno-a-uno ai moduli (rotazione da fix A-05/A-08; pytest-asyncio plugin non caricato).
- **Contenuto del `.env`** (intenzionalmente non letto; ma `daily_analysis.sh` contiene credenziali hardcoded → problema confermato).
- **Politica di disaster recovery / backup PG**: non documentata nel repo.

---

## FASE 2 — Spec-vs-realtà (discrepanze con severità e confidenza)

Formato per discrepanza: **[ID] Titolo · Tipo · Area · Evidenza · Descrizione · Impatto · Severità · Confidenza · Azione · Ticket**.

**[D-01] Roadmap contraddice il codice su S7 PEAD (B-01)**
- Tipo: Contraddizione doc-codice · Area: Strategie/Roadmap
- Evidenza: `docs/.../2026-06-16-master-roadmap.md` B-01 marcato `[x]`; `config/strategies.yaml` nessuna voce S7; `src/strategies/registry.py` non registra S7; `src/strategies/s7/strategy.py` `compute_target_weights` esiste ma mai chiamato, manca `__call__` (incompatibile col backtest engine).
- Descrizione: la roadmap dichiara S7 "done" ma S7 non è registrato, non è cablato all'esecuzione, e non è compatibile col motore di backtest.
- Impatto: finta completezza; rischio di credere che una strategia PEAD sia attiva quando è un arto morto.
- Severità: High · Confidenza: High
- Azione: de-flaggare B-01 in roadmap, aprire ticket per cablare S7 (registration + `__call__` + consumer Redis).
- Ticket: T-S7-WIRE.

**[D-02] Roadmap contraddice il codice su S4 gate report (B-05)**
- Tipo: Contraddizione doc-codice · Area: Validazione
- Evidenza: roadmap B-05 `[x]`; `scripts/run_s4_gate_report.py:56` importa `load_universe` da `scripts.run_backtest` (non definita lì); righe 79-84 usano kwargs `sharpe_threshold/calmar_threshold/hit_rate_threshold/max_drawdown_threshold` inesistenti su `GateConfig` → ImportError + TypeError. Script mai smoke-testato.
- Descrizione: il gate report di S4 — prerequisito per promuovere S4 dal paper — non è mai stato eseguito con successo.
- Impatto: S4 è "capped at 10% until gate report" ma il gate report è inottenibile; la soglia di promozione è di fatto indefinita.
- Severità: Critical · Confidenza: High
- Azione: de-flaggare B-05; correggere lo script e validare l'API di GateConfig prima di eseguirlo.
- Ticket: T-S4-GATE-FIX.

**[D-03] Roadmap contraddice il codice su A-13 (FinBERT truncation)**
- Tipo: Contraddizione doc-codice · Area: LLM/Maintenance
- Evidenza: roadmap A-13 marcato `[ ]`; `src/llm/finbert.py:131` `pipe(clean_text, truncation=True, max_length=self._MAX_TOKENS)` — fix presente.
- Descrizione: il bug di troncamento a carattere è già stato risolto; la roadmap dice il contrario.
- Impatto: basso diretto, ma indica che la roadmap non è mantenuta in sync col codice → fonte non affidabile per lo status.
- Severità: Low · Confidenza: High
- Azione: flaggare A-13 `[x]`; introdurre un check di consistenza roadmap-codice.
- Ticket: T-ROADMAP-SYNC.

**[D-04] strategies.yaml mente sui gate di S2**
- Tipo: Contraddizione config-doc · Area: Validazione/Config
- Evidenza: `config/strategies.yaml` dice S2 "all gates failed"; memoria/roadmap: OOS Sharpe -0.55 ma gate 5 passato.
- Descrizione: la descrizione dei gate in config è inesatta (almeno uno passato).
- Impatto: decisioni di disabilitazione prese su dati descrittivi errati; difficoltà di audit.
- Severità: Medium · Confidenza: Medium
- Azione: riconciliare lo stato gate per ogni strategia in un'unica fonte (DB o YAML generato).
- Ticket: T-GATE-SOURCE-OF-TRUTH.

**[D-05] Invariante "S4 enforced at startup" non rispettata**
- Tipo: Contraddizione commento-codice · Area: Config/Execution
- Evidenza: `config/strategies.yaml` righe 10-11 "S4 enforced at startup"; `src/strategies/registry.py` `_validate_allocations` righe 164-181 solo `log.warning`, mai `raise`.
- Descrizione: la sicurezza dichiarata (rifiuto allo start se S4 > cap) non esiste; c'è solo un warning.
- Impatto: un config errato può mandare S4 oltre il cap senza blocco.
- Severità: High · Confidenza: High
- Azione: trasformare `_validate_allocations` in enforcement hard (raise) o rimuovere l'asserzione dal commento.
- Ticket: T-ALLOC-ENFORCE.

**[D-06] workers.yaml regime TTL non letto da config.py**
- Tipo: Config inutilizzata · Area: Risk/Regime
- Evidenza: `config/workers.yaml` `regime.redis_ttl_seconds: 90000`; `src/config.py` usa default env 259200 (72h).
- Descrizione: il TTL di regime in YAML è ignorato; si usa un valore diverso da codice.
- Impatto: comportamento di scadenza del regime non quello configurato; confusione operativa.
- Severità: Medium · Confidenza: Medium
- Azione: far leggere a config.py il valore YAML o documentare il default come sovrascrivente.
- Ticket: T-CONFIG-DRIFT.

**[D-07] Roadmap "~0 cost" vs trading.yaml annual_fixed_cost_usd 1440**
- Tipo: Contraddizione doc-doc · Area: Business/Economics
- Evidenza: roadmap dichiara costi ~0; `config/trading.yaml` `annual_fixed_cost_usd: 1440`.
- Descrizione: il claim "zero cost" è incompatibile con un costo fisso annuo ~$1440 dichiarato in config.
- Impatto: modellazione economica dell'edge incoerente; possibile sovrastima del Sharpe netto live.
- Severità: Medium · Confidenza: High
- Azione: riconciliare i due documenti; includere il fixed cost nel backtest/net-Sharpe.
- Ticket: T-COST-MODEL-TRUTH.

**[D-08] system_routes.py schedule mirror divergente**
- Tipo: Drift duplicazione · Area: API/Observability
- Evidenza: `src/api/routes/system_routes.py:16-75` static `_SCHEDULE` (rss-ingestion `*/30` vs celery `*/15`; risk-monitor `*/30 14-21` vs `30 22`). Bypassa il pg store iniettato (apre psycopg2 diretto righe 89,133). Molti `except Exception: pass` (righe 102,104,153,177,199,218,221).
- Descrizione: lo schedule mostrato all'utente è una copia manuale non sincronizzata con la fonte reale (celery beat).
- Impatto: l'operatore vede schedule sbagliate; errori DB silenziati → "No data" interpretabile come "mai eseguito".
- Severità: Medium · Confidenza: High
- Azione: generare lo schedule dal beat stesso; usare il pg store iniettato; sostituire `except: pass` con log strutturato.
- Ticket: T-SYSTEM-ROUTES-SYNC.

---

## FASE 3 — Review funzionale e di business

**[F-01] Regime detector calcolato ma non applicato**
- Tipo: Funzionale · Area: Risk/Execution
- Evidenza: `src/workers/portfolio_scheduler.py:543,626` `regime_mult=1.0` hardcodato.
- Descrizione: il regime detector gira quotidianamente ma il moltiplicatore è fissato a 1.0 → nessun de-risking in bear/high_vol.
- Impatto: in regime avverso il sistema espone come in bull; principale gap di risk control.
- Severità: Critical · Confidenza: High
- Azione: cablare il regime_mult dal regime detector (con fallback deterministico).
- Ticket: T-REGIME-WIRE.

**[F-02] Vol targeter applicato DOPO i vincoli**
- Tipo: Funzionale · Area: Risk/Combiner
- Evidenza: `src/portfolio/orchestrator.py:220-223`.
- Descrizione: il vol targeter scala dopo i constraint → può ri-violare il cap 50% esposizione.
- Impatto: esposizione potenzialmente oltre il limite dichiarato.
- Severità: High · Confidenza: High
- Azione: applicare il vol targeter prima dei constraint, o ri-validare dopo.
- Ticket: T-VOLTARGET-ORDER.

**[F-03] Combiner additivo senza risoluzione conflitti né net-exposure**
- Tipo: Architetturale · Area: Combiner
- Evidenza: `src/portfolio/orchestrator.py:135` `merged_weights[sym] += wt * alloc`.
- Descrizione: i pesi si sommano senza arbitraggio di conflitti (BUY + SELL sullo stesso simbolo) né controllo dell'esposizione net.
- Impatto: segnali opposti possono compensarsi silenziosamente o saturare; nessun limite net.
- Severità: High · Confidenza: Medium
- Azione: introdurre risoluzione conflitti e cap net-exposure.
- Ticket: T-COMBINER-CONFLICT.

**[F-04] Backtest non modella il kill-switch live**
- Tipo: Funzionale · Area: Backtest/Live parity
- Evidenza: kill-switch in `config/trading.yaml` (vix_spike 40, drawdown 0.05); non implementato nel backtest.
- Descrizione: il backtest ignora il circuit breaker che in live ferma il sistema → overstatement della performance live.
- Impatto: aspettative di Sharpe live gonfiate.
- Severità: High · Confidenza: High
- Azione: modellare kill-switch in backtest o etichettare i risultati come "pre-risk-control".
- Ticket: T-BT-KILLSWITCH.

**[F-05] EDGAR ingestion rotta (PEAD)**
- Tipo: Funzionale · Area: Data/PEAD
- Evidenza: `src/connectors/sec_edgar.py:74` `body = f"{period_of_report} {entity_name}"` (solo metadati); JSON-path param invalido riga 55.
- Descrizione: il corpo inviato all'LLM non contiene il filing → EPS non estraibile.
- Impatto: S7 riceve input inutilizzabile; tutta la pipeline PEAD produce rumore.
- Severità: High (blocca S7) · Confidenza: High
- Azione: fetch del contenuto 8-K reale; validare il JSON-path.
- Ticket: T-EDGAR-BODY.

**[F-06] pead_worker scrive su Redis senza consumer**
- Tipo: Funzionale · Area: PEAD/Execution
- Evidenza: `src/workers/pead_worker.py:115` scrive segnali; nessun consumer; `eps_consensus` chiesto all'LLM (righe 58-67) senza fonte esterna.
- Descrizione: i segnali PEAD finiscono in Redis ma nessuno li legge; il consensus è allucinabile.
- Impatto: S7 è orfano end-to-end.
- Severità: High · Confidenza: High
- Azione: prima di cablare S7 (T-S7-WIRE) definire la fonte consensus (esterna, non LLM).
- Ticket: T-PEAD-CONSUMER.

**[F-07] API key hardcoded in script tracciato**
- Tipo: Security · Area: Ops/Scripts
- Evidenza: `scripts/daily_analysis.sh:51` `API_KEY="eJvMeuHhJS27FPugKIu4qKGgV7roIdLfcv7h20MwuQg"`.
- Descrizione: credenziale in chiaro nel repo; lo script gira in cron col sistema (`claude --dangerously-skip-permissions`).
- Impatto: chiunque col repo ha accesso API; rotazione obbligatoria.
- Severità: Critical · Confidenza: High
- Azione: revocare/ruotare la chiave; spostare in `.env`; ruotare tutti i secret esposti.
- Ticket: T-SECRET-ROTATION (A-09).

**[F-08] JWT secret con fallback efimero**
- Tipo: Security · Area: Auth
- Evidenza: `src/api/jwt_utils.py:15-16` fallback a chiave efimera se `JWT_SECRET_KEY` unset.
- Descrizione: ogni restart invalida tutti i token; in deploy con secret placeholder (docker-compose:37) il comportamento è indefinito.
- Impatto: sessioni instabili; auth debole in deploy default.
- Severità: High · Confidenza: High
- Azione: rendere JWT_SECRET_KEY obbligatorio (fail-fast); rimuovere il fallback.
- Ticket: T-JWT-FAILFAST.

**[F-09] Docker defaults insicuri**
- Tipo: Security · Area: Infra
- Evidenza: `docker-compose.yml`: POSTGRES_PASSWORD `trading` (8); ADMIN_PASSWORD_HASH committato (36); JWT_SECRET_KEY placeholder (37); Grafana anonymous viewer + `alembic123` (109-113); nessun USER non-root; nessun resource limit; Redis senza appendonly; healthcheck senza timeout (47).
- Descrizione: immagine di default non production-grade.
- Impatto: superficie di attacco ampia se esposto; nessun limite di risorse → noisy-neighbor/OOM.
- Severità: High · Confidenza: High
- Azione: secret via env/.env(gitignored), USER non-root, resource limits, appendonly, healthcheck completi.
- Ticket: T-DOCKER-HARDENING.

**[F-10] CI minimo**
- Tipo: Process · Area: Quality
- Evidenza: `.github/workflows/ci.yml` solo `ruff check` + `pytest -x`; niente mypy, pip-audit, coverage.
- Descrizione: nessun controllo tipi, vulnerabilità dipendenze, né copertura.
- Impatto: regressioni silenziose; supply-chain non monitorato.
- Severità: Medium · Confidenza: High
- Azione: aggiungere mypy, pip-audit/`dependabot`, coverage gate.
- Ticket: T-CI-EXPAND (A-04/A-10).

**[F-11] audit_log table morta**
- Tipo: Data/dead-code · Area: Audit
- Evidenza: `migrations/001_initial.sql:85` `audit_log` mai scritta; catena reale è `execution_decisions`(016:9)+reason(020)+trades(016:28)+portfolio_cycles(013)+view(021).
- Descrizione: tabella di audit prevista mai popolata; per fortuna esiste una catena alternativa forte.
- Impatto: confusione su cosa sia l'audit; rumore nello schema.
- Severità: Low · Confidenza: High
- Azione: o popolare audit_log o rimuoverla; documentare la catena reale.
- Ticket: T-AUDIT-LOG.

**[F-12] Nessun adapter broker + niente partial-fill real-time**
- Tipo: Architetturale · Area: Execution
- Evidenza: `alpaca-py` usato diretto; `portfolio_scheduler.py` nessuna gestione real-time di partial fill.
- Descrizione: lock-in alpaca; fill parziali non gestiti in tempo reale (solo reconcile successiva).
- Impatto: migrare broker costa; stato ordine in tempo reale non accurato.
- Severità: Medium · Confidenza: Medium
- Azione: definire interfaccia broker; gestire partial fill via stream/websocket.
- Ticket: T-BROKER-ABSTRACTION.

**[F-13] PEAD tab nel frontend → false confidence**
- Tipo: Prodotto/UX · Area: Frontend
- Evidenza: `frontend/src/pages/SystemLog.tsx` tab PEAD; HelpButton dice il worker "classifica i filing 8-K ogni 30 min"; `frontend/src/api/system.ts` `fetchPeadSignals`. S7 non è in `strategies.yaml` e non trade.
- Descrizione: l'UI presenta S7 PEAD come strategia attiva quando è un arto morto (D-01/F-05/F-06).
- Impatto: operatore crede PEAD funzioni; segnali mostrati come prodotto reale.
- Severità: Medium · Confidenza: High
- Azione: etichettare PEAD come "R&D · non in trading" o nascondere finché S7 non è cablato.
- Ticket: T-PEAD-UI-DISCLAIMER.

**[F-14] Stale docstring in strategies/__init__.py**
- Tipo: Doc drift · Area: Codice
- Evidenza: `src/strategies/__init__.py` "s2 ... 20%", "s4 ... 30%" (reali 0%, 10%); nessun S7.
- Descrizione: docstring sballata rispetto alle allocazioni reali.
- Impatto: lettura errata dello stato a colpo d'occhio.
- Severità: Low · Confidenza: High
- Azione: rigenerare o rimuovere le allocazioni dalla docstring.
- Ticket: T-STRAT-DOC.

---

## FASE 4 — Review Quant / Trading per strategia

Convenzione classificazione: **plausible-alpha** / **alpha-to-validate** / **probable-false-alpha** / **risk-execution-improvement** / **product-opportunity**.

### S1 — Time-Series Momentum Multi-Asset (live 50%)
- Stato gate: 5/5 passati; OOS Sharpe ~0.51. → **alpha-to-validate** (live, ma validato solo su backtest; spec richiede 90gg paper + riproducibilità + DR + capital ≤5% — non verificato soddisfatti).
- Rischi: (a) backtest non modella kill-switch (F-04) → Sharpe live atteso <0.51; (b) cost model con impact≈0 (volume non passato) → cost live sottostimati; (c) fixed cost 1440/anno (D-07) non incluso nel Sharpe riportato; (d) regime unused (F-01) → nessun de-risking in bear.
- Verdetto: unica strategia genuinamente promossa, ma **promozione fondata su backtest-only**. Non sufficiente per "live-ready".

### S2 — VRP (research, 0%)
- OOS Sharpe -0.55; config dice "all gates failed" (inesatto, gate 5 passato — D-04). → **probable-false-alpha** (in questo setup).
- Rischi: il negative Sharpe suggerisce inversione di segno o modello mal specificato; ricercare la fonte del bias prima di ogni riabilitazione.
- Verdetto: lasciare disabilitata; non "opportunità di tuning", ma ipotesi da falsificare ex-novo.

### S3 — Cross-Sectional Residual Momentum (research, 0%)
- Gate 3/5 falliti; sospetto sizing lookahead (prezzo t usato per sizing a t). → **alpha-to-validate** con bug bloccante.
- Rischi: se il lookahead è reale, l'OOS parziale (0.15) può essere artefatto; sopravvivenza del watchlist non verificata.
- Verdetto: disabilitata correttamente; priorità è **provare il lookahead** prima di ogni ulteriore sviluppo.

### S4 — News-Driven Tactical LLM (paper 10%)
- Stato: capped fino a gate report **inottenibile** (D-02). → **alpha-to-validate** (bloccata a validazione).
- Rischi: (a) sentiment senza RAG/supervisor verificato in esecuzione? (la spec lo richiede per produzione — da verificare); (b) paper 10% ma enforcement soft (D-05); (c) prompt DK-CoT da auditare (role, step-by-step, few-shot, JSON, bull/bear — da confermare per S4).
- Verdetto: paper legittimo, ma la soglia di promozione è indefinita finché il gate script è rotto.

### S7 — PEAD (non cablato)
- Codice presente, non registrato, non `__call__`-compatibile, EDGAR rotto, no consumer, consensus allucinabile (F-05/F-06/D-01). → **probable-false-alpha finché non si fissa la pipeline**.
- Rischi: il PEAD è alpha accademico noto ma fragile (survivorship sulle aziende che battono, microstruttura, timing); qui è ipotesi grezza.
- Verdetto: R&D, non candidabile; falsificare la pipeline prima di ogni allocazione.

### Altro: regime, vol targeter, combiner
- Regime → **risk-execution-improvement** critico (F-01): il de-risking è alpha difensivo, non alpha direzionale, ma qui è completamente assente → è la "opportunità" più ad alto impatto per il drawdown.
- Vol targeter/Combiner → **risk-execution-improvement** (F-02/F-03).

---

## FASE 5 — Edge case & failure mode

Per ogni categoria: stato + gap + severità. (R = rilevato/verificato nel codice, ? = non verificato, ✗ = assente).

| # | Categoria | Stato | Gap | Sev |
|---|-----------|-------|-----|-----|
| E-01 | Dati mancanti/stale/retro-corretti | R: staleness 30min (`workers.yaml`); DataReplay PIT gate nel backtest | Nessun alert operativo se lo staleness supera soglia nel live; retroactive correction non gestita in UI | Medium |
| E-02 | Split/dividendi/adjusted-close | ? | Data provider e adjust policy non verificati; backtest può usare adjusted, live quote raw → divergence | High |
| E-03 | ETF sostituti | ? | Non documentato; S1 è multi-ETF → se un ETF cambia/sospende, fallback? | Medium |
| E-04 | Festività/mezza seduta | R: beat solo 1-5; cron 14:30 | Nessuna esclusione mezze sedute (close anticipato) → ordini a finestre vuote | Medium |
| E-05 | Close/open/timezone/DST | R: celery UTC; beat in UTC; commento timezone stale | Transizione DST non gestita nel cron del sistema; scheduler 14:30 CEST = orario fisico non solare | Medium |
| E-06 | Partial fill | ✗ (F-12) | Nessuna gestione real-time; solo reconcile differita | High |
| E-07 | Ordine rifiutato | R: pg_store reconcile; execution_decisions reason | Nessun retry/escalation policy documentata | Medium |
| E-08 | Broker disconnect | R: `restart: unless-stopped`; kill-switch Redis | Nessun circuit breaker su disconnect persistente lato executor | Medium |
| E-09 | DB/Redis down | R: healthcheck PG/Redis | Worker non hanno healthcheck; API apre psycopg2 diretto in system_routes → fragile | High |
| E-10 | Celery lag | ? | Nessun alert se beat/job lagga; cycle lock 840s (`portfolio_scheduler:160`) può mascherare stalli | Medium |
| E-11 | LLM timeout/drift | R: guardrail variance/timeout; FinBERT fallback; PSI drift giallo/rosso | Fallback a deterministico non auditato; PSI non blocca, solo classifica | High |
| E-12 | News duplicate/manipulation | R: sanitization (`sanitizer.py`) | Dedup news non verificato; omoglifi/BiDi sì, ma manipolazione intenzionale multipubblicazione? | Medium |
| E-13 | Ticker ambiguity | ? | Nessun disambiguatore documentato (es. "AAPL" vs OTC); CLAUDE.md chiede ASCII-safe | Medium |
| E-14 | Wrong regime | ✗ (F-01) | Regime detector corretto ma NON applicato → worst case: sistema full-size in bear | Critical |
| E-15 | Stop-loss non sincronizzato | R: stop_loss 0.02 (`trading.yaml`); hold-min 30min | Hold-min blocca SELL (non BUY); stop in live vs backtest parity? | Medium |
| E-16 | Combiner oltre vincoli | R: constraint 5 + vol targeter post (F-02) | Vol targeter può ri-violare 50%; nessun net cap | High |
| E-17 | Paper-live divergence | R: `paper-api in URL` (scheduler:250) | Cost/impact/kill-switch divergono (F-04); slippage live non modellato | High |
| E-18 | Backtest non riproducibile | ✗ | Nessun pin versione dati/modello/seed; seed random disabilitato in workflow ma non nei run; 33 test rossi | Critical |
| E-19 | Frontend stale | R: react-query refetch; SystemLog staleness 3h | system_routes `except:pass` → "No data" ambiguo; no SSE/socket, solo polling | Medium |
| E-20 | Utente interpreta paper come live | R: DataSourceBadge LIVE/BACKTEST in Strategies.tsx; ModeBadge | ModeBadge non evidenzia abbastanza il rischio; PEAD tab fuorviante (F-13) | Medium |
| E-21 | Tax/regulatory changes | ✗ | Nessuna modellazione; wash sale, short locate, PTU/non-PTU non considerati | Low |
| E-22 | Opzioni assignment/early-exercise/bid-ask/margin/greeks | ✗ | Nessun supporto opzioni; margin/short non modellati | Low (fuori scope ora) |

**Categorie a Critical/High da indirizzare prima di qualsiasi promozione live**: E-14 (regime), E-18 (riproducibilità), E-02 (adjust), E-06 (partial fill), E-09 (DB/Redis down), E-11 (LLM drift), E-16 (combiner), E-17 (paper-live divergence).

---

## FASE 6 — Nuove opportunità (A–E)

Per ognuna: Titolo · Descrizione · Categoria · Perché · Repo-evidence · Complessità · Impatto · Overfitting-risk · Data-prereqs · Validazione · Failure-mode · Priorità.

### A — Nuovo alpha / R&D

**[O-A1] Regime-aware sizing (de-risking difensivo)**
- Categoria: A/Risk-alpha · Descrizione: applicare `regime_mult` (bull 1.0/sideways 0.7/bear 0.4/high_vol 0.2) già definito in `workers.yaml`.
- Perché: il regime è calcolato ma ignorato (F-01) → drawdown non protetto. È il miglior alpha "difensivo" a costo zero.
- Repo-evidence: `portfolio_scheduler.py:543,626` `regime_mult=1.0`; `workers.yaml` multipliers.
- Complessità: Low · Impatto: High (riduzione drawdown) · Overfitting-risk: Medium (le soglie regime vanno validate OOS, non tarate sul drawdown storico) · Data-prereqs: serie regime storica · Validazione: walk-forward con regime effettivo (no lookahead sul regime); confronto DD p95 · Failure-mode: regime lagging → de-risk tardo; mitigare con regime hysteresis · Priorità: **P0**.

**[O-A2] S7 PEAD come ipotesi falsificabile (pipeline prima di alpha)**
- Categoria: A/R&D · Descrizione: riparare EDGAR (F-05), definire consensus esterno (non LLM, F-06), cablare + `__call__` (D-01), poi backtest walk-forward.
- Perché: PEAD è alpha accademico noto ma qui è rotto end-to-end; non candidabile finché la pipeline non produce input valido.
- Repo-evidence: `sec_edgar.py:74`; `pead_worker.py:58-67,115`; `s7/strategy.py` senza `__call__`.
- Complessità: Medium · Impatto: Medium (se alpha regge) · Overfitting-risk: High (PEAD è notoriamente survivorship-prone) · Data-prereqs: consensus EPS storico point-in-time, 8-K content storico · Validazione: 5 gate + survivorship-free universe + costi · Failure-mode: consensus lookahead, bias sui beater · Priorità: **P2** (dopo de-risking).

**[O-A3] S3 residual momentum — prova lookahead prima di riabilitare**
- Categoria: A/R&D · Descrizione: test di contaminazione (size a t con prezzo t) prima di ogni ulteriore sviluppo.
- Perché: il lookahead sospetto invalida l'OOS 0.15.
- Repo-evidence: S3 gate 3/5 fail; sizing non verificato PIT.
- Complessità: Low (test) · Impatto: Medium · Overfitting-risk: n/a (è proprio il test) · Data-prereqs: serie PIT · Validazione: backtest con sizing shiftato t-1 · Failure-mode: se lookahead reale → scartare · Priorità: **P1**.

### B — Miglioramenti a strategie esistenti

**[O-B1] Modella il kill-switch nel backtest**
- Categoria: B/Parity · Perché: F-04 overstates Sharpe live.
- Complessità: Medium · Impatto: High (onesta attesa) · Overfitting-risk: Low · Validazione: confronta Sharpe con/senza kill-switch su storico · Failure-mode: kill-switch troppo aggressivo taglia recovery · Priorità: **P0**.

**[O-B2] Cost model realistico con volume reale**
- Categoria: B/Parity · Perché: impact square-root con volume=0 è inattivo → costi sottostimati.
- Complessità: Low · Impatto: Medium · Overfitting-risk: Low · Data-prereqs: ADV storico · Validazione: confronta turnover × cost · Failure-mode: sovrastima costi se liquidity data grezza · Priorità: **P1**.

**[O-B3] Includere fixed cost nel net-Sharpe**
- Categoria: B/Economics · Perché: D-07 (~0 cost vs 1440/anno).
- Complessità: Trivial · Impatto: Low-Medium · Overfitting-risk: n/a · Priorità: **P1**.

**[O-B4] Combiner: risoluzione conflitti + net-exposure cap**
- Categoria: B/Risk · Perché: F-03. S1+S4 possono sommare BUY/SELL sullo stesso ticker senza regole.
- Complessità: Medium · Impatto: High · Overfitting-risk: Low · Validazione: stress su segnali opposti simultanei · Failure-mode: regole troppo rigide soffocano alpha · Priorità: **P1**.

**[O-B5] Vol targeter pre-constraint**
- Categoria: B/Risk · Perché: F-02 ri-violazione cap 50%.
- Complessità: Low · Impatto: Medium · Overfitting-risk: Low · Priorità: **P0**.

### C — Risk management

**[O-C1] Kill-switch hard in live con recovery human-gated**
- Categoria: C/Risk · Perché: `trading.yaml` killswitch_recovery auto-on-drawdown, never operator halt → recupero automatico dopo un evento critico è rischioso.
- Complessità: Low · Impatto: High · Overfitting-risk: n/a · Failure-mode: false halt → tempo perso (accettabile) · Priorità: **P0**.

**[O-C2] Resource limits + healthcheck worker**
- Categoria: C/Ops · Perché: F-09/E-09 (worker senza healthcheck, no limits).
- Complessità: Low · Impatto: Medium · Priorità: **P1**.

**[O-C3] Regime history table + audit del de-risking**
- Categoria: C/Audit · Perché: nessuna tabella regime_history; se si cabla il regime serve traccia.
- Complessità: Low · Impatto: Medium · Priorità: **P1** (dipende O-A1).

**[O-C4] Alerting su LLM fallback rate e PSI red**
- Categoria: C/Monitoring · Perché: E-11 (fallback non auditato; PSI non blocca).
- Complessità: Low · Impatto: High · Priorità: **P0**.

### D — Prodotto / Frontend

**[O-D1] Disclaimer PEAD tab + stato strategie real-time**
- Categoria: D/UX · Perché: F-13 false confidence.
- Complessità: Trivial · Impatto: Medium (fiducia operatore) · Priorità: **P0**.

**[O-D2] "Promotion readiness" dashboard**
- Categoria: D/Product · Descrizione: una vista che per ogni strategia mostra gate status, paper days, riproducibilità, DR status, capital % — la "checklist live" della spec.
- Perché: oggi l'operatore non vede se S1 ha soddisfatto i 4 safeguard della spec (90gg paper, riproducibilità, DR, ≤5% capitale).
- Complessità: Medium · Impatto: High (decisioni di go-live informate) · Priorità: **P1**.

**[O-D3] ModeBadge prominente + banner paper≠live**
- Categoria: D/UX · Perché: E-20.
- Complessità: Trivial · Impatto: Medium · Priorità: **P1**.

**[O-D4] system_routes generato dal beat (no drift)**
- Categoria: D/Observability · Perché: D-08.
- Complessità: Low · Impatto: Medium · Priorità: **P1**.

### E — Processo

**[O-E1] Roadmap-vs-code consistency check in CI**
- Categoria: E/Process · Perché: D-01/D-02/D-03 mostrano roadmap non affidabile.
- Complessità: Low · Impatto: Medium · Priorità: **P1**.

**[O-E2] Test suite verde + pytest-asyncio plugin + coverage gate**
- Categoria: E/Quality · Perché: 33 test rossi invalidano la fiducia nella suite.
- Complessità: Medium · Impatto: High · Priorità: **P0**.

**[O-E3] CI: mypy + pip-audit + coverage**
- Categoria: E/Quality · Perché: F-10.
- Complessità: Low · Impatto: Medium · Priorità: **P1**.

**[O-E4] Reproducibility manifest per backtest (data+model+seed pin)**
- Categoria: E/Reproducibility · Perché: E-18.
- Complessità: Medium · Impatto: Critical (auditabilità) · Priorità: **P0**.

**[O-E5] DR/backup policy documentata**
- Categoria: E/Ops · Perché: area non analizzata; spec menziona DR.
- Complessità: Low · Impatto: High · Priorità: **P1**.

---

## FASE 7 — Roadmap di prioritizzazione (10 output obbligatori)

### 7.1 Executive summary (≤20 righe)
Alembic è un ATS multi-strategia "Alpha Miner" architetturalmente sano: LLM mai nel hot path (rispettato), sentiment score = polarity×confidence (corretto), audit chain forte (execution_decisions→trades→portfolio_cycles→daily_state), frontend tipizzato con distinzione LIVE/BACKTEST e paper/live badge. **MA** il sistema non è live-ready: la roadmap è stale in entrambe le direzioni (S7 e S4-gate flaggati done ma rotti; A-13 flaggato todo ma fatto), il regime detector è calcolato ma **mai applicato** (de-risking assente → drawdown non protetto), il backtest non modella il kill-switch e non è riproducibile (no pin data/modello/seed; 33 test rossi), il cost model ha impact≈0 e ignora i $1440/anno fissi, l'EDGAR ingestion passa solo metadati all'LLM (S7 orfano), una API key è hardcoded in script tracciato e i default docker sono insicuri. Solo S1 è genuinamente live (50%, OOS Sharpe ~0.51, 5/5 gate) ma la sua promozione è backtest-only senza i safeguard della spec (90gg paper, riproducibilità, DR, ≤5% capitale). **Verdetto: Research-grade / early Paper-ready, NON Live-ready.** Nessuna strategia dovrebbe essere promossa oltre il paper finché i gate di S4 sono indefiniti, il regime è cablato e il backtest è riproducibile.

### 7.2 Top 10 problemi
1. Regime detector ignorato → nessun de-risking (F-01/E-14) — Critical
2. API key hardcoded in `daily_analysis.sh:51` (F-07) — Critical
3. S4 gate report script rotto → soglia promozione indefinita (D-02) — Critical
4. Backtest non riproducibile + 33 test rossi (E-18/O-E2/O-E4) — Critical
5. Vol targeter post-constraint ri-violazione cap 50% (F-02) — High
6. Combiner additivo senza conflitti/net-exposure (F-03) — High
7. EDGAR rotto + PEAD orfano (F-05/F-06/D-01) — High
8. Backtest non modella kill-switch (F-04) — High
9. JWT fallback efimero + docker insicuri + secret nel compose (F-08/F-09) — High
10. `_validate_allocations` solo warning, enforcement S4 soft (D-05) — High

### 7.3 Top 10 opportunità
1. O-A1 Regime-aware sizing (de-risking difensivo) — P0
2. O-B1 Modella kill-switch in backtest — P0
3. O-E4 Reproducibility manifest backtest — P0
4. O-E2 Test suite verde + async plugin + coverage — P0
5. O-C1 Kill-switch hard + recovery human-gated — P0
6. O-C4 Alerting fallback rate/PSI red — P0
7. O-B5 Vol targeter pre-constraint — P0
8. O-D1 Disclaimer PEAD + stato strategie — P0
9. O-D2 Promotion-readiness dashboard — P1
10. O-B4 Combiner conflict + net cap — P1

### 7.4 Tabella Fix-now / Validate-next / R&D-later / Ignore

| Bucket | Item | Ticket |
|--------|------|--------|
| **Fix-now (P0)** | Ruotare secret + rimuovere API key dal repo | T-SECRET-ROTATION |
| Fix-now | Cablare regime_mult (fallback deterministico) | T-REGIME-WIRE |
| Fix-now | Riparare `run_s4_gate_report.py` + validare GateConfig API | T-S4-GATE-FIX |
| Fix-now | Vol targeter pre-constraint | T-VOLTARGET-ORDER |
| Fix-now | Enforcement hard allocazioni | T-ALLOC-ENFORCE |
| Fix-now | JWT fail-fast (no fallback efimero) | T-JWT-FAILFAST |
| Fix-now | Test suite verde + pytest-asyncio | T-TEST-GREEN |
| Fix-now | Reproducibility manifest backtest | T-BT-REPRODUCIBLE |
| Fix-now | Kill-switch hard + recovery human-gated | T-KILLSWITCH-HARD |
| Fix-now | Disclaimer PEAD UI | T-PEAD-UI-DISCLAIMER |
| Fix-now | Alerting fallback/PSI | T-LLM-ALERTING |
| **Validate-next (P1)** | Modella kill-switch in backtest | T-BT-KILLSWITCH |
| Validate-next | Cost model con volume reale + fixed cost | T-COST-MODEL-TRUTH |
| Validate-next | Combiner conflict + net-exposure cap | T-COMBINER-CONFLICT |
| Validate-next | S3 lookahead test | T-S3-LOOKAHEAD |
| Validate-next | CI mypy+pip-audit+coverage | T-CI-EXPAND |
| Validate-next | Docker hardening | T-DOCKER-HARDENING |
| Validate-next | system_routes from beat + remove except:pass | T-SYSTEM-ROUTES-SYNC |
| Validate-next | Promotion-readiness dashboard | T-PROMO-DASHBOARD |
| Validate-next | DR/backup policy | T-DR-POLICY |
| Validate-next | Regime history table + audit | T-REGIME-HISTORY |
| Validate-next | Roadmap-vs-code CI check | T-ROADMAP-SYNC |
| **R&D-later (P2)** | S7 PEAD pipeline repair + falsificazione | T-S7-WIRE, T-EDGAR-BODY, T-PEAD-CONSUMER |
| R&D-later | S2 bias investigation (source of negative Sharpe) | T-S2-BIAS |
| **Ignore** | Param tuning recente; "S4 enforced" come sicurezza reale; audit_log table (morta) | — |

### 7.5 Domande aperte per il PO
1. S1 è stato promosso al 50% live con quali evidenze oltre il backtest? Sono soddisfatti i 4 safeguard della spec (90gg paper, riproducibilità, DR, ≤5% capitale)?
2. Qual è il data provider di mercato e la policy di adjusted-close/split/dividend? (E-02 non verificato)
3. Il consensus EPS per PEAD deve venire da una fonte esterna (refinitiv/estimize) — è in scope? Senza, S7 va scartato.
4. La kill-switch recovery è volutamente auto-on-drawdown? Confermare se si vuole human-gate (O-C1).
5. I $1440/anno fissi sono da includere nel net-Sharpe? Il claim "~0 cost" è da ritirare?
6. S2 con OOS Sharpe -0.55: si indaga la fonte del bias o si archivia definitivamente?
7. La modalità paper-live è decisa solo da URL substring — è accettabile o serve un interruttore esplicito con conferma?

### 7.6 Ticket funzionali (estratti)
- T-REGIME-WIRE: cablare regime_mult dal detector; fallback deterministico; test di regressione per sizing per regime.
- T-S4-GATE-FIX: correggere import `load_universe` e kwargs di GateConfig; smoke-test; produrre report; definire soglia di promozione.
- T-SECRET-ROTATION: ruotare API key esposta; spostare in `.env`; aggiungere pre-commit secret scan.
- T-BT-REPRODUCIBLE: pin data+modello+seed; manifest per run; CI che rifà un backtest di riferimento e confronta hash/metriche.
- T-VOLTARGET-ORDER: riordinare orchestrator; test che il cap 50% non sia mai violato post-targeting.
- T-COMBINER-CONFLICT: regole risoluzione BUY/SELL stesso simbolo; cap net-exposure; test stress.
- T-KILLSWITCH-HARD: recovery human-gated; stato persistente; audit dell'evento.
- T-TEST-GREEN: 33 rossi → verdi; pytest-asyncio caricato; coverage gate minimo.
- T-DOCKER-HARDENING: secret via env, USER non-root, limits, appendonly, healthcheck completi.
- T-PEAD-UI-DISCLAIMER: etichetta R&D/non-trading o nascondi tab; stato strategie real-time.

### 7.7 Metriche mancanti (da esporre/collezionare)
- Drawdown p95 / p99 per regime (de-risking non misurato).
- Fallback rate FinBERT e PSI red nel tempo (oggi non alertato).
- Net-exposure reale post-combiner (cap violation non tracciato).
- Paper-live divergence metric (slippage, fill rate, cost diff).
- Backtest reproducibility score (hash confronto run-riferimento).
- Fixed-cost-adjusted net Sharpe.
- Per-strategy: paper days count, capital %, DR-verified flag (promotion readiness).
- Worker health/lag metric (Celery beat lag, job backlog).

### 7.8 Doc/config da aggiornare
- `docs/.../2026-06-16-master-roadmap.md`: de-flaggare B-01, B-05; flaggare A-13; riconciliare cost claim.
- `config/strategies.yaml`: correggere stato gate S2 (D-04); rimuovere/attuare invariante "S4 enforced" (D-05); aggiungere/rimuovere S7 a seconda della scelta.
- `config/workers.yaml` ↔ `src/config.py`: risolvere regime TTL drift (D-06).
- `config/trading.yaml`: riconciliare fixed cost (D-07).
- `src/strategies/__init__.py`: docstring allocazioni (F-14).
- `src/api/routes/system_routes.py`: schedule da beat; rimuovere `except:pass` (D-08).
- `frontend/src/pages/SystemLog.tsx`: disclaimer PEAD (F-13).
- `migrations/001_initial.sql`: rimuovere o popolare audit_log (F-11).
- `scripts/daily_analysis.sh`: rimuovere API key; documentare rotazione.
- `docker-compose.yml`: hardening (F-09).
- `.github/workflows/ci.yml`: espandere controlli (F-10).

### 7.9 Status assessment

**Verdetto: Research-grade / early Paper-ready — NON Live-ready.**

| Asse | Stato | Note |
|------|-------|------|
| Architettura core (LLM offline) | ✅ Live-ready | Vincolo rispettato; score formula corretta. |
| Audit chain | ✅ Paper-ready | execution_decisions→trades→cycles→daily_state robusta; audit_log morta. |
| Frontend/UX | 🟡 Paper-ready | Tipizzato, badge LIVE/BACKTEST, ma PEAD fuorviante e manca promotion-readiness. |
| Risk control | ❌ Not live-ready | Regime ignorato (F-01), vol targeter post-constraint (F-02), combiner senza net-cap (F-03), kill-switch non modellato in BT (F-04). |
| Validazione/gate | ❌ Not live-ready | S4 gate rotto (D-02); S3 lookahead; S2 config inesatta; S7 orfano. |
| Riproducibilità | ❌ Not live-ready | Nessun pin data/modello/seed (E-18); 33 test rossi. |
| Security/Ops | ❌ Not live-ready | API key nel repo (F-07); JWT fallback (F-08); docker default insicuro (F-09); CI minimo (F-10). |
| Strategia live (S1) | 🟡 early Paper-ready | 5/5 gate ma promozione backtest-only senza i 4 safeguard della spec. |

**Giustificazione sintetica**: l'architettura e la catena di audit sono solide e il paradigma Alpha Miner è rispettato — questo colloca Alembic sopra il livello "Prototype". Tuttavia tre blocchi critici impediscono il live: (1) **il risk control è incompleto** (regime ignorato = nessun de-risking, il peggior caso possibile in bear/high_vol); (2) **la validazione non è chiusa** (S4 senza gate report, S7 orfano, S3 con lookahead sospetto, backtest non riproducibile); (3) **security/ops non è production-grade** (secret nel repo, JWT instabile, docker insicuro, CI minimo, test rossi). Solo S1 ha superato i gate, ma su base backtest-only e senza i safeguard della specifica (90gg paper, riproducibilità, DR, capitale ≤5%). Raccomandazione: nessuna promozione oltre il paper finché P0 (sezione 7.4) non è chiusa; trattare S1 50% live come paper-de-facto fintanto che il regime è cablato, il backtest è riproducibile, i test sono verdi e i secret sono ruotati.

---

*Fine report. Modalità read-only rispettata: nessun file modificato, nessun commit, nessun ordine/script live eseguito. Ogni proposta è un ticket, non una patch. Nuovi alpha (O-A1/A2/A3) trattati come ipotesi da falsificare. Le affermazioni non verificate nel codice sono segnalate con `?`. Contraddizioni tra documenti evidenziate (D-01…D-08). Costo del falso positivo assunto alto: priorità a robustezza, auditabilità e risk control sul rendimento teorico.*