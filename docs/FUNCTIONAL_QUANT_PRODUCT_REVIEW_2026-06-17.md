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

*Fine report (fase 1–7). Modalità read-only rispettata: nessun file modificato, nessun commit, nessun ordine/script live eseguito. Ogni proposta è un ticket, non una patch. Nuovi alpha (O-A1/A2/A3) trattati come ipotesi da falsificare. Le affermazioni non verificate nel codice sono segnalate con `?`. Contraddizioni tra documenti evidenziate (D-01…D-08). Costo del falso positivo assunto alto: priorità a robustezza, auditabilità e risk control sul rendimento teorico.*

---

# APPENDICE — RED TEAM REVIEW (2026-06-17)

Review avversaria del report precedente. Assunzione di partenza: **il progetto è più fragile di quanto le fasi 1–7 lascino intendere.** Qui si attacca ciò che il report dava per buono, in particolare S1 (l'unica strategia "valida") e il frontend (dà falsa sicurezza). Le obiezioni sono fondate su evidenza `file:line` verificata in read-only. Una sezione "Verifiche agent" riporta l'esito di due agent read-only (execution + backtest contamination).

## A. Le 15 obiezioni più forti al progetto

1. **Il backtest ha lookahead same-bar.** `BacktestOrchestrator.run` decide l'ordine con `market_at(ts)` e lo esegue con `simulate_fill(order, market)` **alla stessa barra** (`src/backtest/engine/orchestrator.py:92-96`). Il segnale S1 è calcolato con `price[t]` (`src/strategies/s1/signal.py:63` `prices/prices.shift(lb)-1`) e il sizing con `vol[t]` (`sizing.py:29`); poi il fill è a `price[t]`. In live decidi sul close e compri all'apertura del giorno dopo (gap). Qui compri allo stesso close su cui hai deciso. **Lo Sharpe 0.51 di S1 è sistematicamente ottimistico** e non implementabile così com'è.
2. **Il "Gate 5 Stress Test" è falso.** Non testa 2008/COVID. `_extract_stress_periods` (`src/strategies/s1/backtest.py`) trova il peggior drawdown **dentro l'OOS stesso** e ne prende ±15 giorni. È circolare: lo "stress" è già nel campione che genera lo Sharpe. Il report fasi 1–7 propagava "2008, COVID 2020" dalla documentazione, ma il codice non lo fa.
3. **Il "Gate 3 Robustness" è data mining.** `src/strategies/s1/sensitivity.py` fa `itertools.product` su lookback×vol_window e poi `max_sharpe = lv.max().max()` (riga ~154) — prende il MAX su una grid e dichiara "base near-optimum". Nessuna correzione per confronti multipli (Bonferroni/White reality check/Hansen SPA). Scansionare una grid OOS e reportare la migliore è la definizione di data snooping. Il frontend (`Strategies.tsx`) visualizza proprio questa grid colorata — invitando l'occhio alla cella verde = selection bias esposto in UI.
4. **S1 "valida" è quasi banalmente positiva nel periodo.** Momentum su ETF con volatility targeting, backtest da `date(1993,1,1)` (`s1/backtest.py:211`) — ma l'universo S1 è ETF il cui `inception_date` è post-2010 per molti (`src/backtest/data/universe.py`). Il segnale tiene solo righe dove **tutti i ticker hanno dati validi** (`signal.py:71-72`), quindi il backtest parte solo quando l'ETF più recente del paniere ha storia. Se l'OOS effettivo è 2015-2025, è quasi tutto post-GFC bull regime → momentum "funziona" per costruzione. La validità non è dimostrata fuori da un bull market.
5. **Il cost model "realistic" è realistic solo nominalmente.** `RealisticCostModel.simulate_fill` (`src/backtest/costs/realistic.py:51`) usa `adv_20d.get(symbol, 10_000_000)` — quando il market snapshot non porta l'ADV, l'impatto square-root collassa a ~0. Il modello "completo" degenera silenziosamente a solo-spread. Costi live non sono modellati in pratica; lo Sharpe è pre-cost realistici.
6. **Il regime è una finta nel live e una finta nella UI.** Live: `src/workers/portfolio_scheduler.py:543,626` hardcodano `regime_mult=1.0`. UI: `frontend/src/pages/Performance.tsx` mostra "Regime corrente ×{multiplier}", "Deployment ceiling", "Capitale trattenuto vs bull" come se il de-risking fosse attivo. L'operatore vede un risk control che **non è applicato**. Doppia falsa sicurezza: codice + frontend.
7. **Il frontend può smontare i risk control via UI.** `frontend/src/pages/Config.tsx`: slider "Max Drawdown" fino al 20%, `stop_loss` input `max=0.5`. Il backend `update_config` (`src/api/routes/config_routes.py:29-44`) fa `_deep_merge` + `yaml.dump` con **zero validazione** e accetta qualsiasi chiave. Il kill-switch di `trading.yaml` è 5%; l'operatore può portarlo a 20% (o stop_loss a 50%) con un click e una API key. Nessun bound backend, nessuna conferma, nessun audit log della modifica.
8. **Il kill-switch ha una race window (oltre a essere reversibile in un click).** `POST/DELETE /killswitch` (`src/api/routes/admin.py:119-140`) con sola API key, niente 2FA/cooldown. E il check è fatto **una sola volta all'ingresso del ciclo** (`portfolio_scheduler.py:212-233`) e **mai ricontrollato prima di `submit_order`** (`:879, :897`). Un halt (operatore o drawdown monitor) alzato durante l'orchestrator run (fino a ~10 min) **non ferma gli ordini di quel ciclo**. `system:halted_by_operator` non è riaggiornato; solo `system:mode` è ricontrollato (`:564-570`).
9. **Calendario borsa dinamico ma fail-open.** Esiste un pre-flight `trading_client.get_clock()` (`portfolio_scheduler.py:255-259`) che salta il ciclo se `clock.is_open == False` (copre festività e mezze sedere nel path felice). **MA** se la chiamata di clock fallisce, il sistema `proceeds anyway` (`:260-261`) → tradisce cieco in mercato chiuso. Nessuna integrazione `exchange_calendars`/`pandas_market_calendars`; il beat fisso UTC (`celery_app.py:166`) non allinea mai il trading con la sessione reale per tutto l'anno. (Correzione rispetto alla prima stesura della red team: il calendario c'è, ma non è fail-closed.)
10. **DST/timezone fragile.** Celery beat è UTC (`celery_app.py:50-51`); il cron di sistema è "30 14 * * 1-5" in ora locale Roma. In inverno (CET, UTC+1) 14:07 UTC = 15:07 CET → **prima dell'apertura NYSE (15:30 CET)**; il cron daily-analysis è in ora locale Roma e deriva di 1h vs NYSE attraverso le transizioni DST (EU e US cambiano orario in date diverse, ~1-2 settimane di sfasamento per stagione).
11. **Partial fill / rejected / disconnect gestiti solo a posteriori.** Nessuno stream/websocket per i trade fill (grep trova solo lo stream **news**, non fill). Fill detection è puro polling/reconciliation. Submit loop `portfolio_scheduler.py:804-905`: per-order `try/except` (`:903-905`) logga e continua; ordini falliti/rejectati sono silenziosamente droppati da `submitted_orders` (`:878-881`/`:897-899`). Reconcile path `pg_store.reconcile_trade_fills` (`pg_store.py:730-821`) è un job **batch notturno** (21:30 e 03:00 UTC, `celery_app.py:75-78`); un fill non riconciliato prima del ciclo 15-min successivo è invisibile alla decisione successiva.
12. **Lo stop-loss in live NON ESISTE (escalation).** Il `stop_loss: 0.02` di `trading.yaml` è letto **solo dal worker legacy** (`src/workers/execution.py:73-85, 553-623`), disattivato (`engine=portfolio`, `execution.py:829-831`) → codice morto. L'unico stop broker-side nel path live è il bracket (`portfolio_scheduler.py:870-876`), ma `ALPACA_BRACKET_ENABLED` default `false` (`src/config.py:117-118`) e **non è set in `.env`**. Nello stato attuale: **nessuno stop-loss funziona in live, né broker-side né software.** Un gap-down intraciclo resta in posizione fino al ciclo successivo, e solo se l'orchestratore genera una SELL (che il hold-min 30min può bloccare).
13. **Duplicate-BUY da ordini pending.** Il live path non fa `get_orders(status=OPEN)` (grep vuoto; il legacy `execution.py:513-524` lo faceva ma è inattivo). Se il BUY del ciclo N è ancora pending al ciclo N+1, `get_all_positions()` non lo include (`:401`) → il delta è ricalcolato → **BUY duplicato sullo stesso ticker**. Le posizioni sono lette solo da Alpaca ogni ciclo, nessuna tabella interna, nessuna riconciliazione intended-vs-actual.
14. **L'autonomo LLM con `--dangerously-skip-permissions` su cron.** `scripts/daily_analysis.sh:47` lancia `claude --dangerously-skip-permissions` con API key hardcoded (riga 51) su cron di sistema. Un agente LLM con permessi pieni gira quotidiano e chiama l'API di trading + legge log docker. Se il prompt/ambiente è compromesso o l'LLM allucina, può compiere azioni distruttive. È sia security che fragilità operativa.
15. **Niente source-of-truth e la roadmap mente + backtest non riproducibile.** Roadmap dice S7 done (non cablato, `src/strategies/s7/strategy.py` senza `__call__`), S4 gate done (script rotto, `scripts/run_s4_gate_report.py:56`+`:79-84`), A-13 todo (già fixato, `src/llm/finbert.py:131`). Nessun pin data/modello/seed; la grid di sensitivity non è seeded in modo dichiarato; 33 test rossi. Un sistema il cui status non è verificabile e con test rossi non è auditable — prerequisito per il live.

## B. Le 10 cose che bloccherebbero il passaggio a live

1. **Stop-loss inesistente in live** (`execution.py` morto + bracket off) — nessuna protezione downside intraciclo. **Bloccante, la più grave.**
2. **Backtest same-bar** (`orchestrator.py:92-96`): finché il fill non è t+1 con gap model, ogni Sharpe è inflato. **Bloccante.**
3. **Gate stress falso + robustness data-mined** (`backtest.py _extract_stress_periods`, `sensitivity.py max_sharpe`): le validazioni che certificano S1 non certificano nulla. **Bloccante.**
4. **Regime non applicato** (`portfolio_scheduler.py:543,626`): nessun de-risking in bear/high_vol. **Bloccante.**
5. **Kill-switch race window + reversibile senza 2FA** (`admin.py:119-140`, `portfolio_scheduler.py:212-233` non ricontrolla prima di submit): safety net bucata e revocabile dall'operatore. **Bloccante.**
6. **Calendario fail-open** (`portfolio_scheduler.py:260-261`): su fail del clock, ordini a mercato chiuso. **Bloccante.**
7. **Config senza validazione** (`config_routes.py:29-44`) + slider UI fino a 20%/50%: risk control disabilitabili da UI. **Bloccante.**
8. **API key nel repo** (`daily_analysis.sh:51`): credenziale esposta. **Bloccante.**
9. **Backtest non riproducibile + 33 test rossi**: impossibile validare un cambiamento o una riproduzione. **Bloccante.**
10. **Cost model impact ~0 di fatto + costi non modellati nel sizing live** (`realistic.py:51`, `portfolio_scheduler.py:834`): P&L live sotto le aspettative su numeri non onesti; duplicate-BUY da pending peggiora l'esposizione. **Bloccante.**

## C. Le 10 verifiche minime prima di investire capitale reale

1. **Riproducibilità backtest**: pinna data (hash), versione modello, seed. Rifa lo stesso backtest due volte su macchine diverse → metriche identiche al byte. Se non sono identiche, non investire.
2. **Test di lookahead diretto**: inietta un segnale che usa `price[t+1]` (future) — il backtest deve esplodere. Se non esplode, il gate PIT è rotto. Poi verifica che rimuovere il future riporti a baseline.
3. **Esecuzione t+1**: rifai il backtest con fill a open[t+1] (o close[t+1]) + gap. Confronta Sharpe con il same-bar. La differenza è il tuo "costo di realismo".
4. **Conta l'OOS reale**: quanti mesi/anni out-of-sample, e quanti includono un bear market vero (non 2020-flash che recuperava)? Sharpe su 2-3 anni tutti bull = privo di significato economico.
5. **Correzione multipla**: applica White Reality Check / Hansen SPA sulla grid di sensitivity. Se il "near-optimum" non sopravvive, l'alpha è data mining.
6. **Calendario NYSE fail-closed**: simula il live scheduler su un anno di calendario reale (festività, mezze sedute, halts) e verifica che su fail del clock il sistema **non** tradi (fail-closed, non fail-open).
7. **Stop-loss e2e in live**: verifica che `ALPACA_BRACKET_ENABLED` sia true in `.env` E che il bracket si attacchi realmente E che funzioni su un gap-down simulato. Se è off, non investire.
8. **Kill-switch e2e con re-check**: attiva il kill-switch mentre un ciclo è in volo, verifica che gli ordini non partano (richiede re-check prima di `submit_order`, non solo all'ingresso). Verifica cooldown + audit log + che NON torni a live automaticamente e che l'operatore non possa revocarlo senza 2FA.
9. **Paper-live divergence per ≥90 giorni**: stesso sistema su paper e su dati live (no execution), confronta slippage, fill rate, cost, duplicate-BUY. Se divergono >20%, il backtest non predice il live.
10. **Stress test indipendente**: ripeti 2008 e 2020 su un universo che esisteva allora (non ETF post-2010). Se l'universo S1 non c'era, costruisci un proxy onesto e ammetti che lo stress è sintetico.

## D. Le 5 opportunità più promettenti ma più rischiose (sembrano alpha, sono trappole)

1. **S7 PEAD** — alpha accademico noto, ma qui è rotto end-to-end (EDGAR solo metadati, `sec_edgar.py:74`; no consumer, `pead_worker.py:115`; consensus dall'LLM = allucinabile). Anche riparato, PEAD è **survivorship-prone** (tiri solo le aziende che battono e sopravvivono) e microstruttura-fragile. Promettente in letteratura, trappola in un'implementazione artigianale.
2. **S3 Cross-Sectional Residual Momentum** — sospetto lookahead nel sizing (prezzo t usato per size a t). Se il lookahead è reale, l'OOS 0.15 è artefatto. "Rimuovi il bug e diventa alpha" è l'errore classico: spesso il "bug" è l'alpha.
3. **Regime-aware sizing (O-A1 del report fasi 1–7)** — la ritenevo l'opportunità migliore. Rischio: le soglie regime (bull/sideways/bear/high_vol) e i moltiplicatori sono tarabili; se ottimizzati sul drawdown storico, il "de-risking" diventa un fit sul passato che peggiora il live (overfit del risk control). Promettentissimo, ma il tuning è data mining se non pre-specificato.
4. **Sensitivity grid come "robustness"** — la grid che il frontend mostra come prova di robustezza è, come sopra, data mining. Sembra rassicurante (area verde ampia), ma un'area verde ampia in-sample è esattamente il pattern pre-collapse OOS.
5. **LLM ensemble sentiment (S4)** — l'idea che più LLM (kimi/qwen/FinBERT) con ensemble variance riduca il rischio è attraente, ma: (a) i modelli possono condividere bias (stessi dati, stesso periodo, stessa epoca di training → correlation alta, non vera diversità); (b) la "divergence_std 0.30" come guardrail è una soglia arbitraria; (c) il fallback a FinBERT su timeout significa che nei momenti di mercato stress (dove serve il segnale) potresti avere solo il fallback deterministico — il peggior momento per il modello debole.

## E. Le 5 opportunità con miglior rapporto impatto/semplicità

1. **Validazione hard del config + bound su slider UI** — impatto: ferma la disabilitazione dei risk control via UI; complessità: banale (schema + range check in `update_config`, clamp lato frontend). Rapporto altissimo. (`config_routes.py:29-44`, `Config.tsx`)
2. **Kill-switch con 2FA/cooldown + re-check prima di submit + audit** — impatto: chiude la race window e la via di fuga dell'operatore in tilt; complessità: bassa (secondo fattore + TTL + re-check in `portfolio_scheduler.py` prima di `:879/:897` + scrittura su audit). (`admin.py:131-140`, `portfolio_scheduler.py:212-233`)
3. **Stop-loss broker-side ATTIVO in `.env` (bracket on) o stop software nel path portfolio** — impatto: dà al sistema una protezione downside che ora è inesistente; complessità: bassa (set `ALPACA_BRACKET_ENABLED=true` + verificare attach + gestire SELL senza bracket). (`portfolio_scheduler.py:870-876`, `config.py:117-118`)
4. **Fill t+1 + gap nel backtest** — impatto: rende lo Sharpe onesto (chiude il lookahead same-bar); complessità: bassa-media (uno shift nel fill + gap model). È la singola modifica che ricalibra ogni decisione di promozione. (`orchestrator.py:92-96`)
5. **Calendario NYSE fail-closed + skip a mercato chiuso** — impatto: evita ordini a seduta chiusa/halt anche su fail del clock; complessità: bassa (`exchange_calendars`, guard fail-closed prima di ogni ciclo). (`portfolio_scheduler.py:255-261`, `celery_app.py:166`)

## F. Verifiche agent (read-only) — esito

Due agent read-only lanciati per attaccare rispettivamente (1) contaminazione backtest/lookahead/survivorship e (2) execution/liquidity/broker/timezone.

### Agent execution — rientrato con evidenza dura (escalation)

| # | Area | Verdetto | Evidenza chiave |
|---|------|---------|-----------------|
| 1 | Order type/liquidity | FRAGILE | `portfolio_scheduler.py:878,891` market order; no VWAP/limit; `market.volumes`/`adv_20d` hardcodati `1_000_000` (`:357-358`) |
| 2 | Calendar/holidays | OK happy / FRAGILE fail-open | `:255-259` get_clock filtra, ma `:260-261` procede su fail del clock |
| 3 | TZ/DST | OK beat / FRAGILE cron | `celery_app.py:50-51,166` UTC beat + get_clock; cron `30 14` Roma deriva vs NYSE DST |
| 4 | Partial/reject/disconnect | FRAGILE | `:903-905` per-order try/except droppa i falliti; no websocket; `reconcile_trade_fills` batch-only (`pg_store.py:730`); hard-kill 660s (`celery_app.py:53-54`) → fill orfano |
| 5 | Stop-loss | BROKEN | `execution.py:553-623` morto (engine=portfolio); bracket `:870-876` off default (`config.py:117-118`, `.env` unset) |
| 6 | Position source | FRAGILE | `:401` solo posizioni Alpaca, no `get_orders(OPEN)` → duplicate BUY |
| 7 | Cost model in live | FRAGILE | `RealisticCostModel` backtest-only; `TradeCostCalculator` solo accounting in `pg_store.py:786`, non nel sizing (`:834` prezzo raw) |
| 8 | Kill-switch race | FRAGILE | `:212-233` check singolo all'ingresso, no re-check prima di `submit_order` (`:879/:897`); `system:halted_by_operator` non riaggiornato |

Rischi live-only in ordine di gravità (agent): (5) stop inesistente, (8) race kill-switch, (6) duplicate-BUY, (1) market order ciechi, (4) reject silenzioso, (7) divergenza P&L live vs model.

### Agent backtest-contamination — in volo al momento della stesura

I temi chiave (same-bar fill, stress circolare, selection bias sulla grid) sono già confermati direttamente dal codice in obiezioni #1–#3. Eventuali integrazioni su walk-forward fold-count e survivorship effettivo verranno allegate se l'agent rientra con elementi aggiuntivi.

## G. Verdetto red team (aggiornato)

Il report fasi 1–7 era troppo fiducioso su S1 e sulle "5 gate passate". Le 5 gate, lette nel codice, **non sono ciò che il documento descrive** (stress finto, robustness data-mined, same-bar lookahead). L'unica strategia "valida" è validata su una validazione che non valida. **S1 non è live-ready a maggior ragione.**

La fragilità peggiore non è nel backtest (già fragile) ma nel **gap backtest↔live**: il live path ha uno stop-loss inesistente, un kill-switch con race window, ordini a mercato ciechi su ADV finta, costi non modellati nel sizing, e duplicate-BUY da ordini pending. **Il backtest e il live non stanno misurando la stessa cosa.** Anche supponendo S1 alpha genuino, il live realizzato perderebbe spread + impact + fee su ogni roundtrip che il backtest ignora, senza stop, con kill-switch bucato.

Il frontend non è neutro: mostra risk control non applicati (regime in Performance.tsx) e permette di smontarli (slider Config.tsx, `DELETE /killswitch`). Prima di capitale reale, le 10 verifiche (sezione C) sono non-opzionali — e le verifiche 1, 2, 3, 5, 7 probabilmente faranno crollare lo Sharpe sotto soglia, il che è il risultato corretto.

*Fine appendice red team. Modalità read-only mantenuta: nessun file modificato oltre questo report, nessun commit, nessun ordine/script live eseguito. Evidenze verificate con `file:line` ognuna. Una correzione esplicita (#9 calendario) è segnalata rispetto alla prima stesura.*

---

# APPENDICE 2 — R&D BACKLOG DI NUOVE OPPORTUNITÀ (2026-06-18)

Backlog costruito sull'analisi precedente (fasi 1–7 + red team + agent). **Non idee vaghe**: ogni opportunità ha razionale economico, dati, edge, falso-alpha, validazione a 5 gate, integrazione architettura, impatto backend/frontend/monitoring, complessità, priorità.

## Premessa — agent backtest-contamination rientrato (carico sulla validazione S1)

L'agent read-only ha verificato il backtest e confermato che la validazione di S1 è più compromessa di quanto le fasi 1–7 dicessero. Load-bearing:

- **Survivorship CONTAMINATED**: l'universo S1 è l'attuale lista di 15 ETF (`config/universe.yaml:9-24`) applicata all'indietro; `active_at` (`src/backtest/data/universe.py:36`) esiste ma **non è usato nel path S1** (`src/strategies/s1/backtest.py:211-216`); nessuna gestione delisting.
- **Gate 2 passa per artefatto**: `gate_2_walkforward.py:51-56` esclude le finestre no-trade dal denominatore → positive_fraction 0.48→0.75; sulle 25 finestre raw sarebbe 0.48 < 0.5 (FAIL).
- **Gate 1 DSR inutile**: `n_trials=1` (`runner.py:20`) mentre si esplorano 40 combo (`sensitivity.py:19-21`) + 7 strategie → nessuna correzione multipla; DSR=1.0 privo di significato.
- **Gate 5 stress non documentato**: `s1/backtest.py:183-197` usa una sola finestra worst-30-day con hindsight; **2008 GFC non è stressato** perché i segnali S1 non esistono fino a ~2011 (`equity_curve.json` primo ritorno non-zero 2011-01-03).
- **Adjusted-close come prezzo eseguibile**: `loader.py:131` + `realistic.py:41` usano "Adj Close" (back-adjusted con dividendi futuri) come fill price → serie sintetica non tradable.
- **Walk-forward senza fitting**: `backtest.py:40-46` precomputa sul sample intero e valuta su slice OOS; nessun parametro stimato su IS → l'etichetta "walk-forward" è decorativa.
- **Gate 4 hindsight + clamp silenzioso**: `backtest.py:169-173` mediana sul full-OOS; `gate_4_regime.py:42` clampa `min_passing_regimes` 3→2 senza flag.
- **Sample effettivo**: ~16 anni attivi, t-stat ~2.04 pre-correzione, SE(SR)≈0.25 sui yearly → CI enorme.

Conseguenza sul backlog: la priorità assoluta non sono nuovi alpha, ma **rendere onesta la validazione di S1** (sezione 2), perché ogni decisione di promozione poggia su gate che non validano.

---

## 1. Alpha nuovi

### [N1] S3 — Residual Momentum riabilitato (survivorship-free, PIT) — P2
- **Razionale economico**: il momentum residuo (ritorno residuo dopo size/value/market beta) è documentato meno affollato e più persistente del raw momentum; de-correlato da S1 (cross-sectional vs time-series).
- **Dati necessari**: survivorship-free single-name equity universe con inception/delisting date; fattori di rischio (size, value, market) point-in-time; PIT prices (raw close + dividend adjustment esplicito).
- **Perché edge**: diversificazione rispetto a S1 (cross-section); la residualizzazione riduce l'esposizione ai fattori comuni che dominano S1.
- **Perché falso alpha**: il sospetto lookahead nel sizing (prezzo t usato per size a t) può rendere l'OOS 0.15 un artefatto; "rimuovi il bug e diventa alpha" è l'errore classico dove il bug è l'alpha.
- **Validazione 5 gate**: G1 con correzione multipla (Hansen SPA); G2 su fold effettivi **inclusi** i no-trade; G3 sulla grid completa (40 combo); G4 regime split causale; G5 stress su 2008/COVID reali dell'universo che esisteva allora.
- **Integrazione architettura**: registra in `registry.py` (oggi non caricato); aggiungi voce in `strategies.yaml`; usa `active_at` (già implementato in `universe.py`) per il PIT filtering; `__call__` compatibile col backtest engine.
- **Impatto backend/frontend/monitoring**: backend = nuovo modulo `s3/` + PIT loader; frontend = voce in Strategies.tsx con DataSourceBadge BACKTEST; monitoring = gate report S3.
- **Complessità**: Medium-High (PIT universe + fattori).

### [N2] S7 — PEAD riabilitato (consensus esterno + EDGAR body + consumer) — P2
- **Razionale economico**: il post-earnings-announcement drift è uno dei più robusti anomaly documentati; i mercati sottoreagiscono agli earnings surprise.
- **Dati necessari**: consensus EPS storico **point-in-time** da fonte esterna (Refinitiv/Estize/Bloomberg), non dall'LLM; contenuto reale dei filing 8-K; universe survivorship-free.
- **Perché edge**: anomaly ben replicata; non correlata al momentum; natura event-driven (rara, bassa turnover).
- **Perché falso alpha**: survivorship sulle aziende che battono E sopravvivono; microstruttura/quote-spread sui nomi meno liquidi; timing dell'entry post-earnings (già prizio?).
- **Validazione 5 gate**: G1 multiple-comparison; G2 inclusi no-trade; G3 grid; G4 regime; G5 stress (PEAD in 2020 flash?); plus survivorship-free universe obbligatorio.
- **Integrazione architettura**: fix `sec_edgar.py:74` (fetch body reale); fix `pead_worker.py` (consensus da fonte esterna, non LLM `eps_consensus`); aggiungi consumer Redis in `portfolio_scheduler`; `__call__` su `s7/strategy.py`.
- **Impatto backend/frontend/monitoring**: backend = EDGAR + consensus connector + consumer; frontend = tab PEAD in SystemLog con disclaimer "R&D"; monitoring = qualità consensus (coverage, staleness).
- **Complessità**: High (consensus esterno è il collo di bottiglia).

### [N3] Overnight / session-decomposition alpha — P3
- **Razionale economico**: su ETF liquidi (SPY/QQQ) esiste un premia notte vs session distinto e parzialmente spiegabile (flow notturno, gap globali). Decomporre il ritorno in overnight + intraday può isolare un componente tradable separato dal momentum daily.
- **Dati necessari**: dati intraday OHLC con timestamp di session (open/close NYSE); serie overnight gap.
- **Perché edge**: componente ortogonale al momentum daily; bassa correlazione con S1.
- **Perché falso alpha**: il gap che il backtest attualmente **ignora** (same-bar fill) potrebbe essere un costo, non un edge; spread all'open anomalo; il premia notte può essere compensation per risk notturno (non alpha puro).
- **Validazione 5 gate**: G1 significance con block-bootstrap (dati giornalieri autocorrelati); G2 walk-forward; G3 robustness; G4 regime (gap in bear vs bull); G5 stress (flash crash notturni).
- **Integrazione architettura**: nuovo modulo `s8/`; data loader intraday (estende `loader.py`); non tocca il portfolio engine (segni pre-open).
- **Impatto backend/frontend/monitoring**: backend = loader intraday + strategy; frontend = voce Strategies; monitoring = fill rate pre-open.
- **Complessità**: High (dati intraday + execution pre-open).

### [N4] Cross-sectional single-name LLM sentiment (estensione S4) — P3
- **Razionale economico**: S4 è ETF/news tactical; un cross-section single-name (sentiment per nome con ranking long-short) può sfruttare la dispersione di sentiment tra nomi, non solo il livello.
- **Dati necessari**: universe single-name survivorship-free; news per-name con dedup; sentiment ensemble già esistente.
- **Perché edge**: sfrutta dispersione (long-short) → market-neutral; l'ensemble esiste già.
- **Perché falso alpha**: i modelli LLM condividono bias (stessa epoca/dati → correlation alta, non diversità); sentiment su single-name è più rumoroso e manipolabile; costi su single-name > ETF.
- **Validazione 5 gate**: G1 con multiple-comparison; G2 walk-forward; G3 grid; G4 regime (sentiment in stress); G5 stress; più survivorship-free.
- **Integrazione architettura**: riusa `workers/sentiment.py` + ensemble; nuovo signal scorer cross-sectional; combiner con net-exposure cap (richiede F-03 fix).
- **Impatto backend/frontend/monitoring**: backend = scorer cross-sectional; frontend = nuovo tab; monitoring = ensemble correlation metric.
- **Complessità**: High (single-name + costi + survivorship).

---

## 2. Miglioramenti a S1

### [S1-1] Universo point-in-time + gestione delisting (fix survivorship) — P0
- **Razionale economico**: la survivorship gonfia lo Sharpe (tiri i 15 ETF sopravvissuti al 2026 all'indietro); un universo onesto è prerequisito per ogni claim di edge.
- **Dati necessari**: inception/delisting date per ogni ETF candidato; lista storica di ETF esistenti (non solo sopravvissuti).
- **Perché edge**: nessun edge diretto, ma rende onesti gli edge esistenti.
- **Perché falso alpha**: l'OOS 0.51 può collassare una volta rimosso il bias di selezione; questo è il risultato **corretto**.
- **Validazione 5 gate**: rifare tutti i gate con universo PIT; se lo Sharpe resta >0.5 con correzione multipla, l'edge è plausibile.
- **Integrazione architettura**: usare `active_at` (già in `universe.py:36`) in `s1/backtest.py:211-216`; estendere `universe.yaml` con delisting; screen PIT (non full-sample NaN).
- **Impatto backend/frontend/monitoring**: backend = loader PIT; frontend = universo mostrato con date attivazione; monitoring = coverage per data.
- **Complessità**: Medium.

### [S1-2] Esecuzione t+1 + gap model (fix same-bar lookahead) — P0
- **Razionale economico**: decidere sul close[t] e fillare al close[t] è non implementabile; il gap overnight è il rischio dominante del momentum e va modellato.
- **Dati necessari**: prezzi open/close (raw) per gap; nulla di nuovo.
- **Perché edge**: nessuno; rende lo Sharpe onesto (probabilmente lo abbassa).
- **Perché falso alpha**: parte dell'OOS 0.51 è optimism same-bar; rimuoverlo può portarlo sotto soglia.
- **Validazione 5 gate**: rifare G1–G5 con fill t+1; confronto Sharpe same-bar vs t+1 = "costo di realismo".
- **Integrazione architettura**: shift nel fill in `orchestrator.py:92-96` (fill a `market_at(t+1)` open); gap model opzionale.
- **Impatto backend/frontend/monitoring**: backend = engine; frontend = equity curve aggiornata; monitoring = gap contribution.
- **Complessità**: Low-Medium.

### [S1-3] Raw close + reinvestimento dividendi esplicito (fix adjusted-close come fill) — P0
- **Razionale economico**: "Adj Close" Yahoo è back-adjusted con dividendi futuri → prezzo sintetico non tradable; va sostituito con raw close + dividend reinvestment esplicito per il mark-to-market.
- **Dati necessari**: raw close + schedule dividendi PIT.
- **Perché edge**: nessuno; onestà.
- **Perché falso alpha**: parte del "rendimento" può essere dividendo riportato all'indietro (non alpha, è income).
- **Validazione 5 gate**: rifare i gate con raw close; il total return deve essere ricostruito esplicitamente.
- **Integrazione architettura**: `loader.py:131` field="Close" + colonna dividend; `realistic.py:41` fill su raw close.
- **Impatto backend/frontend/monitoring**: backend = loader + cost model; frontend = nessuno; monitoring = dividend contribution.
- **Complessità**: Low.

### [S1-4] Stress test reale (2008/COVID/2022 sull'universo esistente allora) — P0
- **Razionale economico**: il gate 5 attuale è una riaffermazione del drawdown OOS, non uno stress; un sistema live deve sopravvivere a regimi reali.
- **Dati necessari**: dati degli ETF esistenti in 2008/2020/2022 (subset del universe PIT).
- **Perché edge**: nessuno; validazione onesta.
- **Perché falso alpha**: se S1 non aveva segnali fino al 2011, il claim "stress 2008" è falso; il gate deve ammetterlo.
- **Validazione 5 gate**: G5 rifatto su finestre storiche reali; se i segnali non esistono, etichettare "stress non testabile" (non PASS fittizio).
- **Integrazione architettura**: sostituire `_extract_stress_periods` (`s1/backtest.py:183-197`) con finestre storiche fisse; `gate_5_stress.py` allineato al docstring.
- **Impatto backend/frontend/monitoring**: backend = gate 5; frontend = gate table onesta; monitoring = niente.
- **Complessità**: Low-Medium.

### [S1-5] Correzione multipla (Hansen SPA / White Reality Check) + n_trials reale — P0
- **Razionale economico**: 40 combo + 7 strategie provate con `n_trials=1` → DSR=1.0 privo di significato; il Sharpe 0.51 è marginalmente significativo (t~2.04) **prima** della correzione.
- **Dati necessari**: tutte le grid Sharpes + le strategie confrontate.
- **Perché edge**: nessuno; onestà statistica.
- **Perché falso alpha**: con correzione multipla, 0.51 può non sopravvivere → l'alpha è data mining.
- **Validazione 5 gate**: G1 con Hansen SPA su 40 combo + 7 strategie; `n_trials` reale in `runner.py:20`.
- **Integrazione architettura**: `gate_1_significance.py` + `signal_quality.py` DSR con n_trials; reporta p-value corretto.
- **Impatto backend/frontend/monitoring**: backend = gate 1; frontend = p-value mostrato; monitoring = niente.
- **Complessità**: Medium (SPA implementation).

### [S1-6] Integrità denominatore Gate 2 (non droppare no-trade windows) — P0
- **Razionale economico**: passare un gate droppando le finestre no-trade (0.48→0.75) è un aggiramento; un sistema che non trade 9/25 finestre ha un problema di deployment, non di robustezza.
- **Dati necessari**: nessuno.
- **Perché edge**: nessuno.
- **Perché falso alpha**: il gate "passa" per costruzione, non per merito.
- **Validazione 5 gate**: G2 con denominatore raw (25 finestre); se 0.48 < 0.5, S1 **fallisce** G2 onestamente.
- **Integrazione architettura**: `gate_2_walkforward.py:51-56` non escludere; o reportare entrambi.
- **Impatto backend/frontend/monitoring**: backend = gate 2; frontend = gate table onesta; monitoring = niente.
- **Complessità**: Trivial.

### [S1-7] Walk-forward con fitting reale su IS — P1
- **Razionale economico**: l'attuale "walk-forward" non stima parametri su IS; è una rolling OOS eval. Un vero WF ottimizza su IS e testa su OOS, catturando il degrado fuori-sample.
- **Dati necessari**: nessuno.
- **Perché edge**: nessuno; validazione più severa.
- **Perché falso alpha**: se il WF reale degrada molto, l'alpha è overfit.
- **Validazione 5 gate**: G2 con fitting IS → test OOS; reporta IS vs OOS Sharpe ratio.
- **Integrazione architettura**: `backtest.py:40-46` aggiungi fitting per-window (lookback/vol_window scelti su IS).
- **Impatto backend/frontend/monitoring**: backend = WF runner; frontend = IS/OOS ratio; monitoring = niente.
- **Complessità**: Medium.

### [S1-8] Regime split causale (rolling median, non full-sample) + no clamp silenzioso — P1
- **Razionale economico**: il regime label a t non deve usare dati futuri; il clamp 3→2 silenzioso abbassa la barra.
- **Dati necessari**: nessuno.
- **Perché edge**: nessuno.
- **Perché falso alpha**: la hindsight nel regime split può favorire S1.
- **Validazione 5 gate**: G4 con rolling median causale; `gate_4_regime.py:42` non clampare (o flag).
- **Integrazione architettura**: `backtest.py:169-173` rolling median; `gate_4_regime.py` clamp esplicito.
- **Impatto backend/frontend/monitoring**: backend = gate 4; frontend = regime count onesto; monitoring = niente.
- **Complessità**: Low.

### [S1-9] Net-of-cost Sharpe (impact con ADV reale + fixed cost 1440) — P0
- **Razionale economico**: impact con ADV fake 10M → ~0; fixed cost 1440/anno escluso → Sharpe pre-cost; il net Sharpe è quello che conta per il live.
- **Dati necessari**: ADV storico reale (non hardcodato 1_000_000).
- **Perché edge**: nessuno; onestà economica.
- **Perché falso alpha**: parte dell'edge può essere eroso da costi reali.
- **Validazione 5 gate**: G1 con Sharpe net-of-cost; se sotto soglia, l'alpha è cost-fragile.
- **Integrazione architettura**: `realistic.py:51` ADV reale dal market snapshot; fixed cost in `BacktestConfig`; `s1/backtest.py` reporta net Sharpe.
- **Impatto backend/frontend/monitoring**: backend = cost model + ADV loader; frontend = net Sharpe KPI; monitoring = cost drag.
- **Complessità**: Low-Medium.

---

## 3. Miglioramenti a S2 (VRP, disabilitata, OOS -0.55)

### [S2-1] Diagnosi del -0.55 (investigazione inversione di segno) — P1
- **Razionale economico**: un VRP negativo in-sample suggerisce inversione di segno o specificazione errata; prima di riabilitare serve capire il bias.
- **Dati necessari**: VIX/term-structure storico; serie VRP ricostruita; logica attuale di S2.
- **Perché edge**: VRP è premia documentato (short vol); se qui è negativo, il setup è sbagliato non l'alpha.
- **Perché falso alpha**: se dopo la diagnosi resta negativo, VRP è falso alpha in questo setup → archiviare.
- **Validazione 5 gate**: solo dopo la diagnosi: G1–G5 su serie corretta.
- **Integrazione architettura**: script diagnostico; nessun cambio live (S2 è 0%).
- **Impatto backend/frontend/monitoring**: backend = niente live; frontend = stato "R&D · diagnosi"; monitoring = niente.
- **Complessità**: Medium (diagnosi).

### [S2-2] VRP via VIX term-structure (slope) invece di raw VRP — P2
- **Razionale economico**: lo slope del VIX term-structure (contango/backwardation) è un segnale di regime di vol più pulito del VRP raw, con tail risk minore.
- **Dati necessari**: VIX futures curve storica (non solo VIX spot).
- **Perché edge**: cattura il carry della vol in modo meno tail-heavy; meno drawdown da spike.
- **Perché falso alpha**: il VIX contango è noto e affollato; può essere compensation per risk, non alpha.
- **Validazione 5 gate**: G1 significance; G2 WF; G3 robustness sulla soglia slope; G4 regime (slope in stress); G5 stress (Volmageddon 2018, COVID 2020).
- **Integrazione architettura**: nuovo signal in `s2/`; data loader VIX futures; registrazione solo dopo gate.
- **Impatto backend/frontend/monitoring**: backend = loader VIX futures; frontend = voce S2 BACKTEST; monitoring = curve staleness.
- **Complessità**: High (VIX futures data).

### [S2-3] Cost model per short-vol (tail risk esplicito) — P2
- **Razionale economico**: short-vol ha tail risk asimmetrico; i costi non sono solo spread ma expected shortfall nei spike.
- **Dati necessari**: distribuzione dei spike di vol storici.
- **Perché edge**: modellare la coda rende onesto il trade-off Sharpe vs tail.
- **Perché falso alpha**: ignorare la coda gonfia lo Sharpe (il problema attuale).
- **Validazione 5 gate**: G5 stress con coda reale (2018, 2020); Sortino/CVaR oltre Sharpe.
- **Integrazione architettura**: cost model con tail cost; metriche Sortino/CVaR in `report.py`.
- **Impatto backend/frontend/monitoring**: backend = cost/metric; frontend = Sortino/CVaR KPI; monitoring = tail alert.
- **Complessità**: Medium.

---

## 4. Miglioramenti a S4 (news-driven, paper 10%)

### [S4-1] RAG grounding + supervisor agent (spec non-negoziabile, verificare) — P0
- **Razionale economico**: la spec CLAUDE.md richiede RAG + ensemble variance + supervisor per produzione; senza, il sentiment è allucinabile.
- **Dati necessari**: knowledge base finanziaria per RAG; logica supervisor (rule-based o LLM secondario).
- **Perché edge**: RAG ancorato riduce hallucination; supervisor filtra output anomali.
- **Perché falso alpha**: senza RAG/supervisor, i segnali possono essere rumore LLM con look spettacolare in-sample.
- **Validazione 5 gate**: G1 con IC vs forward returns; G2 WF; G3 robustness; G4 regime; G5 stress (news in crash); plus audit del supervisor.
- **Integrazione architettura**: `workers/sentiment.py` + retrieval store; supervisor hook pre-signal-store.
- **Impatto backend/frontend/monitoring**: backend = RAG + supervisor; frontend = badge "RAG-grounded"; monitoring = supervisor rejection rate.
- **Complessità**: High.

### [S4-2] Audit correlazione ensemble (diversità reale) — P1
- **Razionale economico**: ensemble "diverso" solo se i modelli sono poco correlati; modelli della stessa epoca/dati tendono a corrrelare alta.
- **Dati necessari**: segnali per-modello storici.
- **Perché edge**: diversità reale riduce variance; diversità fittizia no.
- **Perché falso alpha**: se i modelli corrrelano 0.9, l'ensemble è un modello solo → variance non ridotta.
- **Validazione 5 gate**: G1 IC ensemble vs singolo; G3 robustness; aggiungere metrica di diversità.
- **Integrazione architettura**: log per-modello in `sentiment_signals`; metrica correlation in report.
- **Impatto backend/frontend/monitoring**: backend = per-model logging; frontend = ensemble correlation card; monitoring = correlation alert.
- **Complessità**: Low-Medium.

### [S4-3] Fix script gate report S4 — P0
- **Razionale economico**: S4 è "capped until gate report" ma il report è inottenibile; la soglia di promozione è indefinita.
- **Dati necessari**: API corretta di `GateConfig`.
- **Perché edge**: nessuno; sblocca la validazione.
- **Perché falso alpha**: nessuno.
- **Validazione 5 gate**: il report stesso (deve runnare).
- **Integrazione architettura**: `scripts/run_s4_gate_report.py:56,79-84` (import + kwargs corretti); smoke test.
- **Impatto backend/frontend/monitoring**: backend = script; frontend = gate table S4; monitoring = report freshness.
- **Complessità**: Trivial (ma bloccante).

### [S4-4] News dedup + detection manipolazione multi-pubblicazione — P1
- **Razionale economico**: news duplicate gonfiano il segnale; manipolazione multi-pubblicazione può invertire sentiment.
- **Dati necessari**: hash/semantic dedup; source diversity.
- **Perché edge**: segnale meno rumoroso.
- **Perché falso alpha**: senza dedup, lo stesso articolo N volte conta N volte → IC inflato.
- **Validazione 5 gate**: G1 IC con vs senza dedup; G3 robustness.
- **Integrazione architettura**: dedup in connector/ingestion; `sanitizer.py` esteso.
- **Impatto backend/frontend/monitoring**: backend = dedup; frontend = dedup rate; monitoring = manipulation alert.
- **Complessità**: Medium.

### [S4-5] Sentiment threshold cost-aware (l'alpha è thin, i costi pesano) — P1
- **Razionale economico**: sentiment alpha è thin; su single-name i costi erodono; la soglia di trade deve essere cost-aware.
- **Dati necessari**: cost model realistico (ADV reale).
- **Perché edge**: filtrare segnali deboli dove costo > edge atteso.
- **Perché falso alpha**: trade su score 0.1 dove l'edge < spread = perdita certa.
- **Validazione 5 gate**: G1 net-of-cost IC; G3 sensitivity della soglia.
- **Integrazione architettura**: threshold dinamica vs cost in `portfolio_scheduler`; collega a O-C4 alerting.
- **Impatto backend/frontend/monitoring**: backend = threshold logic; frontend = threshold card; monitoring = cost-vs-edge.
- **Complessità**: Low-Medium.

---

## 5. Risk/execution alpha

### [R1] Regime-aware sizing (de-risking) con moltiplicatori PRE-SPECIFICATI — P0
- **Razionale economico**: il regime è calcolato ma ignorato (`portfolio_scheduler.py:543,626` hardcodato 1.0); de-risking in bear/high_vol riduce il drawdown p95.
- **Dati necessari**: serie regime storica (già prodotta dal detector).
- **Perché edge**: alpha difensivo a costo quasi zero; il regime detector esiste già.
- **Perché falso alpha**: se i moltiplicatori (1.0/0.7/0.4/0.2) sono tarati sul drawdown storico → overfit del risk control; vanno PRE-SPECIFICATI e validati OOS.
- **Validazione 5 gate**: G4 regime con sizing attivo vs flat; confronto DD p95; hysteresis anti-lag.
- **Integrazione architettura**: `portfolio_scheduler` legge regime da Redis (TTL da config, non hardcode); fallback deterministico; `regime_history` table (audit).
- **Impatto backend/frontend/monitoring**: backend = scheduler + regime_history; frontend = regime multiplier ACTUAL (non finto come oggi); monitoring = de-risking audit.
- **Complessità**: Low (cablaggio; il detector c'è).

### [R2] Combiner: risoluzione conflitti + net-exposure cap — P1
- **Razionale economico**: `orchestrator.py:135` somma pesi senza arbitraggio (BUY+SELL stesso ticker) né limite net → saturazione o compensazione silenziosa.
- **Dati necessari**: nessuno.
- **Perché edge**: risk control; evita esposizione non intenzionale.
- **Perché falso alpha**: nessuno (è risk, non alpha).
- **Validazione 5 gate**: stress test su segnali opposti simultanei; net-exposure sempre ≤ cap.
- **Integrazione architettura**: regole in `portfolio/orchestrator.py`; cap net-exposure post-combiner; test.
- **Impatto backend/frontend/monitoring**: backend = combiner; frontend = net-exposure KPI; monitoring = cap violation alert.
- **Complessità**: Medium.

### [R3] Vol targeter PRE-constraint (fix ri-violazione cap 50%) — P0
- **Razionale economico**: `orchestrator.py:220-223` applica il vol targeter dopo i constraint → può ri-violare il cap 50%.
- **Dati necessari**: nessuno.
- **Perché edge**: risk control.
- **Perché falso alpha**: nessuno.
- **Validazione 5 gate**: test che il cap non sia mai violato post-targeting.
- **Integrazione architettura**: riordinare orchestrator; ri-validare cap dopo.
- **Impatto backend/frontend/monitoring**: backend = orchestrator; frontend = niente; monitoring = cap alert.
- **Complessità**: Low.

### [R4] Kill-switch re-check prima di submit + 2FA/cooldown + audit — P0
- **Razionale economico**: il kill-switch è controllato una sola volta all'ingresso (`portfolio_scheduler.py:212-233`) e mai prima di `submit_order` (`:879,:897`); race window fino a ~10 min; reversibile senza 2FA (`admin.py:131-140`).
- **Dati necessari**: nessuno.
- **Perché edge**: risk control (chiude il buco).
- **Perché falso alpha**: nessuno.
- **Validazione 5 gate**: drill operatore; halt mid-cycle → ordini non partono.
- **Integrazione architettura**: re-check `killswitch_active` prima di ogni submit; 2FA su DELETE; cooldown; audit in `execution_decisions`.
- **Impatto backend/frontend/monitoring**: backend = scheduler + admin; frontend = conferma 2FA; monitoring = halt audit.
- **Complessità**: Low-Medium.

### [R5] Stop-loss broker-side ATTIVO (bracket on) o stop software nel path portfolio — P0
- **Razionale economico**: oggi NESSUNO stop funziona in live (`execution.py` morto, bracket off default `config.py:117-118`); gap-down intraciclo non protetto.
- **Dati necessari**: nessuno.
- **Perché edge**: risk control essenziale.
- **Perché falso alpha**: nessuno.
- **Validazione 5 gate**: drill gap-down simulato → posizione chiusa.
- **Integrazione architettura**: `ALPACA_BRACKET_ENABLED=true` in `.env`; verificare attach su BUY; stop software su SELL nel path portfolio (non legacy).
- **Impatto backend/frontend/monitoring**: backend = scheduler + env; frontend = stop status; monitoring = stop trigger audit.
- **Complessità**: Low.

### [R6] Calendario NYSE fail-closed — P0
- **Razionale economico**: `get_clock` filtra festività ma fail-open (`portfolio_scheduler.py:260-261`); su fail del clock, ordini a mercato chiuso.
- **Dati necessari**: `exchange_calendars` NYSE.
- **Perché edge**: risk control.
- **Perché falso alpha**: nessuno.
- **Validazione 5 gate**: simula fail del clock → nessun ordine.
- **Integrazione architettura**: `exchange_calendars` come source + fallback fail-closed; rimuovi "proceeds anyway".
- **Impatto backend/frontend/monitoring**: backend = scheduler; frontend = market status; monitoring = calendar mismatch.
- **Complessità**: Low.

### [R7] Guard contro duplicate-BUY (pending-order fetch) — P0
- **Razionale economico**: nessun `get_orders(OPEN)` → BUY duplicato se ordine pending al ciclo successivo.
- **Dati necessari**: nessuno.
- **Perché edge**: risk control (evita over-exposure).
- **Perché falso alpha**: nessuno.
- **Validazione 5 gate**: simula pending → nessun duplicato.
- **Integrazione architettura**: fetch pending orders in `portfolio_scheduler` prima del sizing; escludi da delta.
- **Impatto backend/frontend/monitoring**: backend = scheduler; frontend = pending orders view; monitoring = duplicate guard.
- **Complessità**: Low-Medium.

---

## 6. Monitoring/product alpha

### [M1] Promotion-readiness dashboard — P1
- **Razionale economico**: l'operatore non vede se una strategia ha soddisfatto i 4 safeguard della spec (90gg paper, riproducibilità, DR, ≤5% capitale); le decisioni di go-live sono cieche.
- **Dati necessari**: paper days count, reproducibility hash, DR status, capital %.
- **Perché edge**: prodotto (decisioni informate).
- **Perché falso alpha**: n/a (non alpha).
- **Validazione 5 gate**: n/a.
- **Integrazione architettura**: nuovo endpoint + pagina che aggrega gate status + safeguard.
- **Impatto backend/frontend/monitoring**: backend = endpoint; frontend = nuova pagina; monitoring = promotion readiness metric.
- **Complessità**: Medium.

### [M2] Alerting fallback rate / PSI red / ensemble correlation — P0
- **Razionale economico**: fallback e PSI red non sono alertati (E-11); il degrado del segnale è silenzioso.
- **Dati necessari**: metriche già calcolate.
- **Perché edge**: monitoring (early warning).
- **Perché falso alpha**: n/a.
- **Validazione 5 gate**: n/a.
- **Integrazione architettura**: alert channel (Telegram/email) su soglie; dashboard in SystemLog.
- **Impatto backend/frontend/monitoring**: backend = alerting worker; frontend = alert card; monitoring = alert log.
- **Complessità**: Low-Medium.

### [M3] Paper-live divergence metric — P1
- **Razionale economico**: slippage, fill rate, cost diff tra paper e live; se >20%, il backtest non predice.
- **Dati necessari**: trade fills paper + live.
- **Perché edge**: monitoring (parity).
- **Perché falso alpha**: n/a.
- **Validazione 5 gate**: n/a (ma è la verifica 9 del red team).
- **Integrazione architettura**: worker che confronta; metric in performance.
- **Impatto backend/frontend/monitoring**: backend = divergence worker; frontend = divergence card; monitoring = alert >20%.
- **Complessità**: Medium.

### [M4] Reproducibility manifest + CI backtest di riferimento — P0
- **Razionale economico**: nessun pin data/modello/seed → nessuna verità di base (E-18); ogni numero non è riproducibile.
- **Dati necessari**: hash data, modello, seed.
- **Perché edge**: auditabilità (prerequisito per il live).
- **Perché falso alpha**: n/a.
- **Validazione 5 gate**: n/a.
- **Integrazione architettura**: manifest per run; CI job che rifà un backtest di riferimento e confronta hash/metriche.
- **Impatto backend/frontend/monitoring**: backend = manifest + CI; frontend = reproducibility badge; monitoring = drift alert.
- **Complessità**: Medium.

### [M5] Config validation hard + UI bounds + audit log — P0
- **Razionale economico**: `update_config` senza validazione (`config_routes.py:29-44`) + slider fino a 20%/50% (`Config.tsx`) → risk control disabilitabili.
- **Dati necessari**: schema di trading.yaml.
- **Perché edge**: risk control (ferma indebolimento via UI).
- **Perché falso alpha**: n/a.
- **Validazione 5 gate**: n/a.
- **Integrazione architettura**: schema + range check in `update_config`; clamp frontend; audit log della modifica.
- **Impatto backend/frontend/monitoring**: backend = config route; frontend = bounded inputs; monitoring = config change audit.
- **Complessità**: Low.

### [M6] Disclaimer PEAD tab + stato strategie real-time — P0
- **Razionale economico**: `SystemLog.tsx` presenta PEAD come attivo quando è R&D morto (F-13) → false confidence.
- **Dati necessari**: nessuno.
- **Perché edge**: prodotto (fiducia operatore).
- **Perché falso alpha**: n/a.
- **Validazione 5 gate**: n/a.
- **Integrazione architettura**: etichetta "R&D · non in trading"; nascondi finché S7 non è cablato.
- **Impatto backend/frontend/monitoring**: frontend = label; backend = niente; monitoring = niente.
- **Complessità**: Trivial.

### [M7] Regime history table + audit del de-risking — P1
- **Razionale economico**: se si cabla R1, serve traccia storica del regime e del multiplier applicato per audit.
- **Dati necessari**: regime label + multiplier per ciclo.
- **Perché edge**: auditabilità.
- **Perché falso alpha**: n/a.
- **Validazione 5 gate**: n/a.
- **Integrazione architettura**: migration `regime_history`; scrittura per ciclo; UI in Performance.
- **Impatto backend/frontend/monitoring**: backend = migration + writer; frontend = regime history; monitoring = de-risking audit.
- **Complessità**: Low-Medium.

---

## 7. Tax/broker/operational improvements

### [T1] Broker adapter abstraction (de-lock-in Alpaca) — P2
- **Razionale economico**: `alpaca-py` diretto ovunque; migrare broker costa; un adapter astratto rende il sistema portabile e testabile.
- **Dati necessari**: nessuno.
- **Perché edge**: opzione (non alpha); riduce lock-in.
- **Perché falso alpha**: n/a.
- **Validazione 5 gate**: n/a.
- **Integrazione architettura**: interfaccia `BrokerClient` (orders, positions, clock, fills) + adapter Alpaca; il portfolio_scheduler dipende dall'interfaccia.
- **Impatto backend/frontend/monitoring**: backend = adapter; frontend = niente; monitoring = niente.
- **Complessità**: Medium-High.

### [T2] Tax-aware P&L (italiano: 26% CG, ETF vs equity, no wash-sale) — P2
- **Razionale economico**: il sistema non modella le tasse → P&L mostrato pre-tax; per un residente italiano il capital gain è 26%, le ETF hanno regimi diversi, niente wash-sale (ma marking vs realizzato conta).
- **Dati necessari**: tipo strumento per ticker; aliquota per strumento; regole realizzo.
- **Perché edge**: onestà economica (net-of-tax).
- **Perché falso alpha**: ignorare le tassi gonfia il rendimento percepito.
- **Validazione 5 gate**: n/a (è reporting).
- **Integrazione architettura**: tax layer in performance/`pg_store`; P&L net-of-tax in frontend.
- **Impatto backend/frontend/monitoring**: backend = tax layer; frontend = net P&L; monitoring = tax drag.
- **Complessità**: Medium.

### [T3] Esecuzione VWAP/TWAP/limit invece di market ciechi — P1
- **Razionale economico**: market order a minuto fisso su ADV finta (`portfolio_scheduler.py:357-358` hardcodato 1M) → spread/impact non controllati.
- **Dati necessari**: quote book / VWAP availability via broker.
- **Perché edge**: riduce slippage reale (execution alpha difensivo).
- **Perché falso alpha**: n/a.
- **Validazione 5 gate**: confronto fill price market vs VWAP su paper.
- **Integrazione architettura**: ordine VWAP/limit con fallback; ParticipationRate; richiede T1 (adapter).
- **Impatto backend/frontend/monitoring**: backend = order type; frontend = execution quality; monitoring = slippage vs benchmark.
- **Complessità**: Medium.

### [T4] DR/backup policy + secret rotation (A-09) — P0
- **Razionale economico**: API key nel repo (`daily_analysis.sh:51`); niente DR/backup documentato; secret nel compose (`docker-compose.yml`).
- **Dati necessari**: nessuno.
- **Perché edge**: ops/security.
- **Perché falso alpha**: n/a.
- **Validazione 5 gate**: n/a.
- **Integrazione architettura**: ruotare tutti i secret; `.env` gitignored; backup PG pianificato; pre-commit secret scan.
- **Impatto backend/frontend/monitoring**: backend = env + backup; frontend = niente; monitoring = backup freshness.
- **Complessità**: Low-Medium.

### [T5] CI expansion (mypy + pip-audit + coverage) + roadmap-vs-code check — P1
- **Razionale economico**: CI minimo (`ci.yml` solo ruff+pytest-x); roadmap stale (D-01/D-02/D-03).
- **Dati necessari**: nessuno.
- **Perché edge**: qualità/processo.
- **Perché falso alpha**: n/a.
- **Validazione 5 gate**: n/a.
- **Integrazione architettura**: mypy, pip-audit/dependabot, coverage gate; job che verifica flag roadmap vs codice.
- **Impatto backend/frontend/monitoring**: backend = CI; frontend = niente; monitoring = CI badge.
- **Complessità**: Low-Medium.

### [T6] Test suite verde (33 reds) + pytest-asyncio + coverage gate — P0
- **Razionale economico**: 33 test rossi invalidano la suite → nessuna regressione intercettata.
- **Dati necessari**: nessuno.
- **Perché edge**: qualità.
- **Perché falso alpha**: n/a.
- **Validazione 5 gate**: n/a.
- **Integrazione architettura**: fix dei 33 rotti (rotazione A-05/A-08); pytest-asyncio plugin; coverage gate minimo.
- **Impatto backend/frontend/monitoring**: backend = tests; frontend = niente; monitoring = CI.
- **Complessità**: Medium.

### [T7] Docker hardening + resource limits + healthcheck worker — P1
- **Razionale economico**: default insicuri (POSTGRES_PASSWORD `trading`, Grafana anonimo+`alembic123`, no USER non-root, no limits, Redis senza appendonly, healthcheck senza timeout, worker senza healthcheck).
- **Dati necessari**: nessuno.
- **Perché edge**: security/ops.
- **Perché falso alpha**: n/a.
- **Validazione 5 gate**: n/a.
- **Integrazione architettura**: secret via env, USER non-root, resource limits, appendonly, healthcheck completi, worker healthcheck.
- **Impatto backend/frontend/monitoring**: backend = compose; frontend = niente; monitoring = resource alerts.
- **Complessità**: Low-Medium.

---

## Prioritizzazione di esecuzione del backlog

**P0 (prerequisiti per ogni decisione di promozione — onestà della validazione e risk control)**: S1-1, S1-2, S1-3, S1-4, S1-5, S1-6, S1-9, S4-1, S4-3, R1, R3, R4, R5, R6, R7, M2, M4, M5, M6, T4, T6.

**P1 (validazione più severa + monitoring + ops)**: S1-7, S1-8, S2-1, S4-2, S4-4, S4-5, R2, M1, M3, M7, T3, T5, T7.

**P2 (nuovo alpha + estensioni, solo dopo che P0 ha reso onesti i numeri)**: N1, N2, S2-2, S2-3, T1, T2.

**P3 (esplorativo, alto costo dati)**: N3, N4.

**Principio guida**: nessun nuovo alpha (P2/P3) prima che i P0 abbiano reso onesta la validazione di S1 — altrimenti si costruiscono strategie nuove su una base di validazione che non valida.

*Fine appendice 2 (R&D backlog). Modalità read-only mantenuta: nessun file modificato oltre questo report, nessun commit, nessun ordine/script live eseguito. Opportunità fondate sull'analisi fasi 1–7 + red team + agent (backtest contamination + execution). Ogni opportunità è un ticket/research item, non una patch. Priorità a robustezza, auditabilità e risk control sul rendimento teorico; costo del falso positivo assunto alto.*