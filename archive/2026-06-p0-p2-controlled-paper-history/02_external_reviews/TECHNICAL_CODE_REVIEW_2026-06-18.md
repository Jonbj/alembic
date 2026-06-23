# Alembic — Code Review Tecnica 2026-06-18

**Review type:** Tecnica / Trading Systems Reliability / Code Review  
**Data:** 2026-06-18  
**Base document:** `docs/FUNCTIONAL_QUANT_PRODUCT_REVIEW_2026-06-17.md`  
**Modalità:** read-only, nessuna modifica al codice di trading, nessun commit, nessun ordine live.  
**Reviewer:** Staff Software Engineer + Code Reviewer + Trading Systems Reliability Reviewer.

---

## 1. Executive Summary

- **Architettura Alpha Miner rispettata**: LLM/sentiment rimangono offline/background; nessuna chiamata sincrona LLM nel hot path di esecuzione.
- **Backtest sistematicamente ottimistico**: same-bar fill (`orchestrator.py:92-96`), cost model con ADV fittizio 10M, stress test circolare (`s1/backtest.py:183-197`), sensitivity grid data-mined (`s1/sensitivity.py:152-160`).
- **Risk control non cablato**: regime detector calcolato ma `regime_mult=1.0` hardcodato nel live; vol targeter applicato **dopo** i vincoli; combiner additivo senza net-exposure cap.
- **Execution live fragile**: stop-loss non attivo (bracket disabilitato), kill-switch controllato solo all'ingresso del ciclo (race window), calendario fail-open su clock failure, nessuna gestione ordini pending/reject, duplicate BUY possibile.
- **Frontend fuorviente**: PEAD presentato come strategia attiva, regime visualizzato come applicato, pagina Config permette di alzare drawdown al 20% / stop-loss al 50% senza validazione backend.
- **Security/ops non production-grade**: API key hardcoded in script tracciato, JWT fallback efimero, Docker defaults insicuri, CI minima, test suite **~111 test rossi** (109 failed + 2 errors + 1 collection error per `ib_insync` mancante).
- **Verdetto generale:** Research-grade / early Paper-ready. **Nessuna promozione live prima di chiudere i P0 elencati in sezione 10.**

---

## 2. Metodologia

1. Lettura del report funzionale e triage di tutti i finding (D-01..D-08, F-01..F-14, E-01..E-22, RT-01..RT-15).
2. Ricerca mirata nel codice reale per ogni finding con `rg`, `Read` e agenti read-only su execution, backtest, security/ops, frontend.
3. Verifica diretta dei file più critici (portfolio_scheduler, orchestrator, registry, backtest engine, S1, admin, config_routes, jwt_utils, docker-compose, CI, frontend pages).
4. Esecuzione test suite (`uv run pytest --ignore=tests/brokers/test_ibkr_adapter.py`) per quantificare lo stato reale.
5. Classificazione ogni finding con stato, severità, probabilità, impatto, effort, priorità, ticket.

---

## 3. Test suite — stato reale

Eseguito:

```bash
uv run pytest tests/ -q --tb=short --ignore=tests/brokers/test_ibkr_adapter.py
```

Risultato:

- **109 failed**
- **2 errors** (autenticazione JWT)
- **1 collection error** originale (`tests/brokers/test_ibkr_adapter.py` → manca `ib_insync`)
- **1939 passed**, 1 skipped
- Tempo: ~6m30s

La maggior parte dei fallimenti è su test decorati con `@pytest.mark.asyncio` ma senza `pytest-asyncio` installato (`uv sync --dev` installa solo il dependency group `dev` che contiene `pytest>=9.0.3`, non le `optional-dependencies dev` dove risiedono `pytest-asyncio`, `mypy`, `ruff`, `pytest-cov`).

Questo rende `T-TEST-GREEN` un **P0 bloccante** per qualsiasi altro fix o deploy.

---

## 4. Tabella: Finding del report → stato verificato nel codice

| ID | Titolo | Stato | Sev tecnica | Probabilità | Priorità | Effort | File chiave |
|---|---|---|---|---|---|---|---|
| D-01 | S7 PEAD non cablato | VERIFIED_BUG | High | High | P1 | M | `src/strategies/registry.py`, `s7/strategy.py` |
| D-02 | S4 gate report script rotto | VERIFIED_BUG | Critical | High | P0 | S | `scripts/run_s4_gate_report.py`, `src/backtest/gates/runner.py` |
| D-03 | Roadmap A-13 vs finbert truncation | VERIFIED_GAP (doc) / codice FALSE_POSITIVE | Low | High | P2 | XS | `docs/...master-roadmap.md`, `src/llm/finbert.py:131` |
| D-04 | strategies.yaml mente su gate S2 | VERIFIED_BUG | Medium | Medium | P2 | XS | `config/strategies.yaml:24` |
| D-05 | S4 enforcement soft (solo warning) | VERIFIED_BUG | High | High | P0 | XS | `src/strategies/registry.py:164-181` |
| D-06 | Regime TTL YAML ignorato | VERIFIED_BUG | Medium | Medium | P2 | XS | `config/workers.yaml:71`, `src/config.py:222-224` |
| D-07 | Costi ~0 vs 1440/anno | VERIFIED_GAP | Medium | High | P2 | XS | `config/trading.yaml:178`, `docs/...master-roadmap.md:8` |
| D-08 | system_routes schedule drift + except:pass | VERIFIED_BUG | Medium | High | P1 | S | `src/api/routes/system_routes.py:16-222` |
| F-01 | Regime detector calcolato ma non applicato | VERIFIED_BUG | Critical | High | P0 | S | `src/workers/portfolio_scheduler.py:543,626`, `src/portfolio/orchestrator.py` |
| F-02 | Vol targeter post-constraint | VERIFIED_BUG | High | High | P0 | XS | `src/portfolio/orchestrator.py:220-223` |
| F-03 | Combiner additivo senza net-exposure | VERIFIED_BUG | High | Medium | P1 | M | `src/portfolio/orchestrator.py:135` |
| F-04 | Backtest non modella kill-switch | VERIFIED_GAP | High | High | P1 | M | `config/trading.yaml:131-149`, backtest engine |
| F-05 | EDGAR ingestion rotta (solo metadati) | VERIFIED_BUG | High | High | P1 | M | `src/connectors/sec_edgar.py:55,74` |
| F-06 | pead_worker scrive su Redis senza consumer | VERIFIED_BUG | High | High | P1 | M | `src/workers/pead_worker.py:115` |
| F-07 | API key hardcoded in script tracciato | VERIFIED_BUG | Critical | High | P0 | XS | `scripts/daily_analysis.sh:51` |
| F-08 | JWT secret fallback efimero | VERIFIED_BUG | High | High | P0 | XS | `src/api/jwt_utils.py:12-16` |
| F-09 | Docker defaults insicuri | VERIFIED_BUG | High | High | P1 | S | `docker-compose.yml:8-113` |
| F-10 | CI minimo (no mypy/pip-audit/coverage) | VERIFIED_GAP | Medium | High | P2 | S | `.github/workflows/ci.yml` |
| F-11 | audit_log table morta | VERIFIED_GAP | Low | High | P3 | XS | `migrations/001_initial.sql`, `pg_store.py` |
| F-12 | Nessun broker adapter + partial fill | VERIFIED_GAP/VERIFIED_RISK | Medium | Medium | P2 | M | `src/workers/portfolio_scheduler.py:401,878-905` |
| F-13 | PEAD tab fuorviante | VERIFIED_BUG | Medium | High | P0 | XS | `frontend/src/pages/SystemLog.tsx:32-81,165-221` |
| F-14 | Docstring strategies/__init__.py stale | VERIFIED_BUG | Low | High | P3 | XS | `src/strategies/__init__.py:8-13` |
| RT-1 | Same-bar backtest fill | VERIFIED_BUG | Critical | High | P0 | M | `src/backtest/engine/orchestrator.py:92-96`, `s1/signal.py:63`, `s1/sizing.py:29` |
| RT-2 | Gate 5 stress falso (drawdown interno OOS) | VERIFIED_BUG | High | High | P0 | S | `src/strategies/s1/backtest.py:183-197` |
| RT-3 | Sensitivity grid data mining | VERIFIED_RISK | High | High | P1 | S | `src/strategies/s1/sensitivity.py:152-160`, `frontend/src/pages/Strategies.tsx:277-308` |
| RT-4 | S1 universe inception post-2007 | VERIFIED_RISK | Medium | High | P2 | XS | `config/universe.yaml:9-25`, `s1/signal.py:71-73` |
| RT-5 | Cost model impact ~0 (ADV default 10M) | VERIFIED_BUG | High | High | P1 | XS | `src/backtest/costs/realistic.py:51` |
| RT-6 | Regime fake in UI | VERIFIED_BUG | High | High | P0 | XS | `frontend/src/pages/Performance.tsx:126-145`, `portfolio_scheduler.py:543` |
| RT-7 | Config UI senza validazione backend | VERIFIED_BUG | Critical | High | P0 | S | `frontend/src/pages/Config.tsx:89-106`, `src/api/routes/config_routes.py:29-44` |
| RT-8 | Kill-switch race + niente re-check | VERIFIED_BUG | Critical | Medium | P0 | S | `src/api/routes/admin.py:119-140`, `portfolio_scheduler.py:212-233,878-897` |
| RT-9 | Calendario fail-open su clock failure | VERIFIED_BUG | High | Medium | P0 | XS | `src/workers/portfolio_scheduler.py:255-261` |
| RT-10 | DST/TZ cron vs beat | VERIFIED_RISK | Medium | Medium | P2 | XS | `celery_app.py:50-51`, `scripts/daily_analysis.sh:3` |
| RT-11 | Partial/reject/disconnect solo batch | VERIFIED_RISK | High | Medium | P1 | M | `portfolio_scheduler.py:903-905`, `pg_store.py:730-821` |
| RT-12 | Stop-loss in live inesistente | VERIFIED_BUG | Critical | High | P0 | XS-S | `portfolio_scheduler.py:870-876`, `src/config.py:117-118`, `execution.py` |
| RT-13 | Duplicate BUY da ordini pending | VERIFIED_BUG | High | Medium | P0 | S | `portfolio_scheduler.py:401,878-881,897-899` |
| RT-14 | `claude --dangerously-skip-permissions` su cron + API key | VERIFIED_BUG | High | High | P0 | XS | `scripts/daily_analysis.sh:47,51` |
| RT-15 | Test suite rossa + backtest non riproducibile | VERIFIED_BUG | Critical | High | P0 | M-L | `.github/workflows/ci.yml`, `pyproject.toml`, test suite |
| E-02 | Split/dividendi/adjusted-close | NOT_ENOUGH_EVIDENCE | High | ? | P2 | ? | data provider non verificato |
| E-18 | Backtest non riproducibile | VERIFIED_GAP | Critical | High | P0 | M | workflow backtest, seed |

---

## 5. Dettaglio finding Critical/High

### [CR-001] Regime detector calcolato ma mai applicato nel live (F-01 / E-14 / O-A1)

- **Finding originale:** F-01 — `regime_mult=1.0` hardcodato, nessun de-risking.
- **Stato:** VERIFIED_BUG
- **Area:** Risk / Execution
- **Evidenza codice:**
  - `src/workers/portfolio_scheduler.py:543` e `:627` — `regime_mult=1.0` hardcodato in `write_execution_decision` e `open_trade`.
  - `src/portfolio/orchestrator.py` — nessun parametro regime, nessuna applicazione a target weights.
- **Analisi tecnica:** `detect_regime` scrive `regime:current` e `qc:sizing_multiplier` in Redis, ma il portfolio scheduler ignora entrambi. Esposizione full-size anche in bear/high_vol.
- **Impatto:** capitale reale / paper trading — drawdown non protetto.
- **Severità:** Critical, **Probabilità:** High, **Priorità:** P0, **Effort:** S
- **Test esistenti:** nessuno sull'applicazione regime nel live.
- **Test mancanti:**
  - unit test: cycle legge regime da Redis e scala target weights.
  - integration test: regime bear/high_vol → ordine ridotto.
  - regression test: nessun ordine full-size in regime high_vol.
- **Fix consigliato:**
  1. Leggere `regime:current` all'inizio del ciclo.
  2. Passare `regime_mult` all'orchestrator, applicarlo **prima** di constraint/vol-targeter.
  3. Propagare in audit (`write_execution_decision`, `open_trade`).
  4. Fallback deterministico conservativo se regime mancante.
- **Rischi del fix:** se applicato dopo i vincoli come ora, può ri-violare i cap.
- **Ticket:** `T-REGIME-WIRE`

---

### [CR-002] S4 gate report script rotto (D-02)

- **Finding originale:** D-02 — script `run_s4_gate_report.py` importa `load_universe` errato e passa kwargs inesistenti a `GateConfig`.
- **Stato:** VERIFIED_BUG
- **Area:** Validation / Config
- **Evidenza codice:**
  - `scripts/run_s4_gate_report.py:56` → `from scripts.run_backtest import load_universe` (non esiste).
  - `:79-84` → `GateConfig(sharpe_threshold=..., calmar_threshold=..., ...)`.
  - `src/backtest/gates/runner.py:17-37` — `GateConfig` ha `min_sharpe`, `max_drawdown_allowed`, `min_oos_sharpe`, ecc., non i kwargs usati.
- **Analisi tecnica:** Lo script non può importarsi; anche corretto l'import, `GateConfig` non accetta i kwargs. Gate report S4 ineseguibile → soglia promozione indefinita.
- **Impatto:** backtest validity / promotion gating.
- **Severità:** Critical, **Probabilità:** High, **Priorità:** P0, **Effort:** S
- **Test esistenti:** nessuno per `run_s4_gate_report.py`.
- **Test mancanti:** smoke test con mock DB/DataLoader; unit test API di `GateConfig`.
- **Fix consigliato:** correggere import, allineare kwargs a `GateConfig` o aggiungere factory, aggiungere smoke test CI.
- **Rischi del fix:** cambio API `GateConfig` può rompere altri script; preferire factory.
- **Ticket:** `T-S4-GATE-FIX`

---

### [CR-003] API key hardcoded in script tracciato (F-07 / RT-14)

- **Finding originale:** F-07 — API key in chiaro in `scripts/daily_analysis.sh:51`; script lancia `claude --dangerously-skip-permissions`.
- **Stato:** VERIFIED_BUG
- **Area:** Security / Ops
- **Evidenza codice:**
  - `scripts/daily_analysis.sh:47,51`
  ```bash
  ANALYSIS_OUTPUT=$(claude --dangerously-skip-permissions -p "$(cat <<'PROMPT'
  ...
  API_KEY="eJvMeuHhJS27FPugKIu4qKGgV7roIdLfcv7h20MwuQg"
  ```
- **Analisi tecnica:** Credenziale hardcoded in file git-tracked e schedulato su cron. Esposizione totale del repo.
- **Impatto:** capitale reale / operational reliability.
- **Severità:** Critical, **Probabilità:** High, **Priorità:** P0, **Effort:** XS
- **Test esistenti:** nessuno su secret scanning.
- **Test mancanti:** pre-commit / CI secret scan.
- **Fix consigliato:**
  1. Ruotare la chiave esposta.
  2. Rimuovere `API_KEY=...` e leggere da `.env` / env.
  3. Rimuovere o limitare `--dangerously-skip-permissions`.
  4. Aggiungere git-secrets / truffleHog in CI.
- **Ticket:** `T-SECRET-ROTATION`

---

### [CR-004] JWT secret fallback efimero (F-08)

- **Finding originale:** F-08 — fallback a chiave efimera se `JWT_SECRET_KEY` unset.
- **Stato:** VERIFIED_BUG
- **Area:** Auth / Security
- **Evidenza codice:**
  - `src/api/jwt_utils.py:12-16`
  ```python
  _EPHEMERAL_KEY = secrets.token_hex(32)
  def _secret() -> str:
      return config.JWT_SECRET_KEY or _EPHEMERAL_KEY
  ```
- **Analisi tecnica:** Ogni restart invalida i token. Il `docker-compose.yml:37` ha un placeholder che incoraggia deploy debole.
- **Impatto:** operational reliability / security.
- **Severità:** High, **Probabilità:** High, **Priorità:** P0, **Effort:** XS
- **Test esistenti:** nessuno su fail-fast JWT.
- **Test mancanti:** unit test: app rifiuta di avviarsi con `JWT_SECRET_KEY` vuoto.
- **Fix consigliato:** rimuovere fallback, fallire all'avvio se segreto mancante o troppo corto, rimuovere placeholder dal compose.
- **Rischi del fix:** deploy esistenti con placeholder smettono di avviarsi.
- **Ticket:** `T-JWT-FAILFAST`

---

### [CR-005] Backtest same-bar fill (RT-1)

- **Finding originale:** Red Team #1 — ordine deciso e riempito alla stessa barra.
- **Stato:** VERIFIED_BUG
- **Area:** Backtest correctness
- **Evidenza codice:**
  - `src/backtest/engine/orchestrator.py:92-96`
  ```python
  orders = strategy_callable(ts, data_replay, portfolio, market)
  for order in orders:
      fill = self.cost_model.simulate_fill(order, market)
      portfolio.apply_fill(fill)
  ```
  - `src/strategies/s1/signal.py:63` — `prices / prices.shift(lb) - 1` usa prezzo corrente.
  - `src/strategies/s1/sizing.py:29` — volatilità rolling su prezzo corrente.
- **Analisi tecnica:** Decisione e fill sullo stesso close. In live si avrebbe segnale al close e fill all'open t+1 con overnight gap. Sharpe 0.51 ottimistico.
- **Impatto:** backtest validity — tutte le metriche di promozione sono inflazionate.
- **Severità:** Critical, **Probabilità:** High, **Priorità:** P0, **Effort:** M
- **Test esistenti:** nessuno su fill t+1 / gap.
- **Test mancanti:**
  - anti-look-ahead: iniettare segnale con future close[t+1], verificare che esploda con same-bar ma non con t+1.
  - regression: confronto Sharpe same-bar vs t+1.
- **Fix consigliato:** usare `market_at(ts)` per decisione e `market_at(ts+1)` (o open t+1) per fill; aggiungere gap model.
- **Rischi del fix:** ricalibra tutte le metriche S1.
- **Ticket:** `T-BT-FILL-T1`

---

### [CR-006] Stop-loss in live inesistente (RT-12)

- **Finding originale:** Red Team #12 — `stop_loss` in `trading.yaml` letto solo dal worker legacy disattivato; bracket disabilitato di default.
- **Stato:** VERIFIED_BUG
- **Area:** Execution / Live safety
- **Evidenza codice:**
  - `src/workers/portfolio_scheduler.py:870-876` — bracket solo se `ALPACA_BRACKET_ENABLED`.
  - `src/config.py:117-118` — default `false`.
  - `src/workers/execution.py` — path legacy inattivo perché `engine=portfolio`.
- **Analisi tecnica:** Con default `false`, gli ordini sono market order senza stop-loss. Gap-down intraciclo resta in posizione fino al ciclo successivo.
- **Impatto:** capitale reale — nessuna protezione downside intraday.
- **Severità:** Critical, **Probabilità:** High, **Priorità:** P0, **Effort:** XS-S
- **Test esistenti:** nessuno e2e su bracket/stop.
- **Test mancanti:** integration test bracket attach; e2e gap-down simulation.
- **Fix consigliato:** default `ALPACA_BRACKET_ENABLED=true` in `.env` o implementare stop software nel portfolio scheduler.
- **Ticket:** `T-STOP-LOSS-LIVE`

---

### [CR-007] Kill-switch race window e niente re-check (RT-8)

- **Finding originale:** Red Team #8 — kill-switch controllato solo all'ingresso del ciclo, mai prima di `submit_order`.
- **Stato:** VERIFIED_BUG
- **Area:** Execution / Safety
- **Evidenza codice:**
  - `src/workers/portfolio_scheduler.py:212-233` — check iniziale.
  - `src/workers/portfolio_scheduler.py:878-897` — submit BUY/SELL senza ricontrollo.
  - `src/api/routes/admin.py:119-140` — POST/DELETE killswitch con sola API key.
- **Analisi tecnica:** Un ciclo può durare minuti. Se il kill-switch viene attivato durante il ciclo, gli ordini partono comunque. Admin API non ha 2FA/cooldown.
- **Impatto:** capitale reale — safety net bucata.
- **Severità:** Critical, **Probabilità:** Medium, **Priorità:** P0, **Effort:** S
- **Test esistenti:** nessuno sulla race.
- **Test mancanti:** integration test attivare kill-switch durante ciclo in volo.
- **Fix consigliato:**
  1. Re-check killswitch subito prima di ogni `submit_order`.
  2. Audit log per ogni cambio killswitch.
  3. 2FA/cooldown per disattivazione.
- **Ticket:** `T-KILLSWITCH-RACE`

---

### [CR-008] Config UI senza validazione backend (RT-7)

- **Finding originale:** Red Team #7 — slider UI permette drawdown fino al 20%, stop-loss fino al 50%; backend accetta qualsiasi chiave.
- **Stato:** VERIFIED_BUG
- **Area:** Frontend / API / Risk control
- **Evidenza codice:**
  - `frontend/src/pages/Config.tsx:89-106` — slider min/max solo frontend.
  - `src/api/routes/config_routes.py:29-44` — `update_config` fa deep-merge senza validazione.
- **Analisi tecnica:** Un client API può inviare valori estremi che vengono scritti su YAML e letti dai worker. Risk control smontabili via API.
- **Impatto:** capitale reale / paper.
- **Severità:** Critical, **Probabilità:** High, **Priorità:** P0, **Effort:** S
- **Test esistenti:** nessuno su validazione `update_config`.
- **Test mancanti:** unit test backend rifiuta valori fuori range; integration test frontend invia estremo e backend respinge.
- **Fix consigliato:** schema Pydantic con range fissi, rifiutare chiavi sconosciute, audit log modifiche.
- **Ticket:** `T-CONFIG-VALIDATION`

---

### [CR-009] Calendario fail-open su clock failure (RT-9)

- **Finding originale:** Red Team #9 — se `trading_client.get_clock()` fallisce, il sistema procede e trada.
- **Stato:** VERIFIED_BUG
- **Area:** Execution / Calendar
- **Evidenza codice:**
  - `src/workers/portfolio_scheduler.py:255-261`
  ```python
  try:
      clock = trading_client.get_clock()
      if not clock.is_open: ...
  except Exception as _clk_exc:
      log.warning("Could not fetch market clock: %s — proceeding anyway", _clk_exc)
  ```
- **Analisi tecnica:** Comportamento fail-open: ordini possono partire a mercato chiuso.
- **Impatto:** capitale reale.
- **Severità:** High, **Probabilità:** Medium, **Priorità:** P0, **Effort:** XS
- **Test esistenti:** nessuno.
- **Test mancanti:** unit test `get_clock` raise → cycle skip.
- **Fix consigliato:** cambiare in fail-closed (skip + alert); aggiungere fallback calendario NYSE locale.
- **Ticket:** `T-CALENDAR-FAILCLOSED`

---

### [CR-010] Duplicate BUY da ordini pending (RT-13)

- **Finding originale:** Red Team #13 — se BUY ciclo N è ancora pending al ciclo N+1, `get_all_positions()` non lo include → ricalcolo delta → BUY duplicato.
- **Stato:** VERIFIED_BUG
- **Area:** Execution / Idempotency
- **Evidenza codice:**
  - `src/workers/portfolio_scheduler.py:401` — solo `get_all_positions()`.
  - Nessun `get_orders(status=OPEN)`.
- **Analisi tecnica:** Delta calcolato contro posizioni Alpaca, non intended. Ordini pending invisibili possono portare a sovra-esposizione.
- **Impatto:** capitale reale / paper.
- **Severità:** High, **Probabilità:** Medium, **Priorità:** P0, **Effort:** S
- **Test esistenti:** nessuno.
- **Test mancanti:** integration test con pending order; unit test `_submit_portfolio_orders` rifiuta duplicati.
- **Fix consigliato:** leggere ordini aperti, tracciare intended vs actual, idempotenza per symbol+side.
- **Ticket:** `T-PENDING-ORDERS`

---

### [CR-011] Combiner additivo / vol targeter post-constraint (F-02 / F-03)

- **Finding originale:** F-02/F-03 — vol targeter dopo vincoli; pesi sommati senza risoluzione conflitti.
- **Stato:** VERIFIED_BUG
- **Area:** Portfolio combiner / Risk
- **Evidenza codice:**
  - `src/portfolio/orchestrator.py:135`
  ```python
  merged_weights[sym] = merged_weights.get(sym, 0.0) + wt * alloc
  ```
  - `src/portfolio/orchestrator.py:220-223` — vol targeter dopo `ConstraintEnforcer` (riga 216).
- **Analisi tecnica:** BUY+SELL sullo stesso ticker si sommano. Vol targeter scala dopo i vincoli, potendo ri-violare cap 50%.
- **Impatto:** paper/live.
- **Severità:** High, **Probabilità:** Medium, **Priorità:** P0/P1, **Effort:** M
- **Test esistenti:** test su `ConstraintEnforcer` ma non su ordine vol-vs-constraint.
- **Test mancanti:** unit test conflitto S1 BUY / S4 SELL; test cap 50% post-vol-targeter.
- **Fix consigliato:** vol targeter prima dei vincoli (o re-validare dopo); regole net-exposure per symbol; cap globale net exposure.
- **Ticket:** `T-COMBINER-CONFLICT`, `T-VOLTARGET-ORDER`

---

### [CR-012] Regime fake in UI (RT-6)

- **Finding originale:** Red Team #6 — `Performance.tsx` mostra regime attivo mentre live hardcodato a 1.0.
- **Stato:** VERIFIED_BUG
- **Area:** Frontend / Risk
- **Evidenza codice:**
  - `frontend/src/pages/Performance.tsx:126-145` mostra regime, multiplier, deployment ceiling, capitale trattenuto.
  - `src/workers/portfolio_scheduler.py:543` — `regime_mult=1.0`.
- **Analisi tecnica:** UI mostra risk control attivo che non è applicato. Falsa sicurezza operativa.
- **Impatto:** frontend trust / operational reliability.
- **Severità:** High, **Probabilità:** High, **Priorità:** P0, **Effort:** XS
- **Test esistenti:** nessuno.
- **Test mancanti:** frontend test warning regime non applicato.
- **Fix consigliato:** flag `regime_applied` nel report; mostrare warning prominente fino a T-REGIME-WIRE.
- **Ticket:** `T-REGIME-UI-WARNING`

---

### [CR-013] EDGAR ingestion rotta + PEAD orfano (F-05 / F-06 / D-01)

- **Finding originale:** F-05/F-06/D-01 — EDGAR passa metadati all'LLM, pead_worker scrive su Redis senza consumer, S7 non registrato.
- **Stato:** VERIFIED_BUG
- **Area:** Data / PEAD / Strategies
- **Evidenza codice:**
  - `src/connectors/sec_edgar.py:55,74` — parametro `hits.hits.total.value` invalido; `body = f"{period_of_report} {entity_name}"` (solo metadati).
  - `src/workers/pead_worker.py:58-67,115` — chiede `eps_consensus` all'LLM; scrive su Redis senza consumer.
  - `src/strategies/s7/strategy.py` — `compute_target_weights` ma nessun `__call__`; non registrato in `StrategyRegistry`.
- **Analisi tecnica:** Pipeline S7 end-to-end non funzionante. Input inutilizzabile, consensus allucinabile, nessun consumer.
- **Impatto:** backtest validity / product trust.
- **Severità:** High, **Probabilità:** High, **Priorità:** P1, **Effort:** M
- **Test esistenti:** nessuno e2e PEAD.
- **Test mancanti:** integration EDGAR fetch reale con mock; unit test `PEADStrategy.__call__`.
- **Fix consigliato:** riparare EDGAR fetch contenuto, fonte consensus esterna, `__call__` e registrazione S7, nascondere/etichettare tab PEAD.
- **Ticket:** `T-EDGAR-BODY`, `T-PEAD-CONSUMER`, `T-S7-WIRE`

---

### [CR-014] Backtest non modella kill-switch + cost model impact ~0 (F-04 / RT-5)

- **Finding originale:** F-04 — backtest ignora kill-switch; RT-5 — `RealisticCostModel` usa ADV default 10M.
- **Stato:** VERIFIED_BUG / VERIFIED_GAP
- **Area:** Backtest / Live parity
- **Evidenza codice:**
  - `src/backtest/costs/realistic.py:51` — `adv_shares = market.adv_20d.get(order.symbol, 10_000_000.0)`.
  - `config/trading.yaml:131-149` — kill-switch triggers.
  - `BacktestOrchestrator` non ha logica kill-switch.
- **Analisi tecnica:** Cost model degenera a spread-only; backtest non simula kill-switch. Sharpe live atteso < Sharpe backtest.
- **Impatto:** backtest validity / live divergence.
- **Severità:** High, **Probabilità:** High, **Priorità:** P1, **Effort:** M/XS
- **Test esistenti:** cost model test probabilmente con ADV fittizio.
- **Test mancanti:** backtest con/senza kill-switch; cost model con ADV reale.
- **Fix consigliato:** passare ADV storico reale; modellare kill-switch in backtest; includere fixed cost 1440/anno in net-Sharpe.
- **Ticket:** `T-BT-KILLSWITCH`, `T-COST-REAL-ADV`, `T-COST-MODEL-TRUTH`

---

### [CR-015] Stress test circolare + sensitivity data mining (RT-2 / RT-3)

- **Finding originale:** RT-2 — stress test prende peggior drawdown dentro l'OOS; RT-3 — sensitivity grid usa max Sharpe senza correzione multipla.
- **Stato:** VERIFIED_BUG / VERIFIED_RISK
- **Area:** Validation / Backtest
- **Evidenza codice:**
  - `src/strategies/s1/backtest.py:183-197` — worst drawdown ±15 giorni dentro OOS.
  - `src/strategies/s1/sensitivity.py:152-160` — `max_sharpe = lv.max().max()`; near-optimum senza correzione.
  - `frontend/src/pages/Strategies.tsx:277-308` — visualizza grid come robustezza.
- **Analisi tecnica:** Stress test non indipendente; sensitivity grid è data snooping OOS.
- **Impatto:** backtest validity — 5 gate non certificano alpha.
- **Severità:** High, **Probabilità:** High, **Priorità:** P0/P1, **Effort:** S-M
- **Test esistenti:** nessuno su indipendenza stress / multiple testing.
- **Test mancanti:** stress con periodi esterni a OOS; reality-check White/Hansen.
- **Fix consigliato:** periodi fissi storici (GFC 2008, COVID 2020, 2022 bear); aggiungere Bonferroni/White/Hansen; rimuovere claim near-optimum o mostrare p-value.
- **Ticket:** `T-GATE5-INDEPENDENT`, `T-SENSITIVITY-REALITY-CHECK`

---

### [CR-016] Test suite rossa + pytest-asyncio mancante (RT-15 / F-10)

- **Finding originale:** RT-15 — test rossi, reproducibility mancante; F-10 — CI minimo.
- **Stato:** VERIFIED_BUG
- **Area:** Quality / CI
- **Evidenza codice:**
  - `pyproject.toml:61-68` — `[tool.pytest.ini_options]` con `asyncio_mode = "auto"`.
  - `pyproject.toml:43-55` — `optional-dependencies dev` con `pytest-asyncio`, `mypy`, `ruff`, `pytest-cov`.
  - `pyproject.toml:66-68` — dependency group `dev` contiene solo `pytest>=9.0.3`.
  - `.github/workflows/ci.yml:60-63` — solo ruff + pytest -x.
- **Analisi tecnica:** `uv sync --dev` installa il group `dev`, non le optional-dependencies dev. Quindi `pytest-asyncio` e altri dev tools non sono installati. Test `test_ibkr_adapter.py` fallisce per `ib_insync` mancante, e con `-x` blocca la suite.
- **Impatto:** operational reliability / reproducibility.
- **Severità:** Critical, **Probabilità:** High, **Priorità:** P0, **Effort:** M
- **Test esistenti:** suite presente ma non funzionante.
- **Test mancanti:** CI mypy, pip-audit, coverage, reproducibility manifest.
- **Fix consigliato:**
  1. Allineare dependency group `dev` con optional-dependencies dev.
  2. Aggiungere `ib_insync` opzionale o rimuovere test se non in scope.
  3. Espandere CI con mypy, pip-audit, coverage gate.
  4. Aggiungere reproducibility manifest.
- **Ticket:** `T-TEST-GREEN`, `T-CI-EXPAND`, `T-BT-REPRODUCIBLE`

---

## 6. False positive / finding già coperti

- **D-03 (A-13 FinBERT truncation):** il codice è già corretto (`src/llm/finbert.py:131` usa `truncation=True, max_length=512`). Problema solo documentale: roadmap non aggiornata. **Stato codice: FALSE_POSITIVE; stato doc: VERIFIED_GAP.**
- **E-01 (Data stale 30min):** configurazione presente in `config/workers.yaml:10` e usata dal sentiment worker. Manca alert operativo se lo staleness supera la soglia → **gap, non false positive.**
- **E-07 (Ordine rifiutato):** `pg_store.reconcile_trade_fills` esiste e `execution_decisions.reason` logga. Manca retry/escalation policy documentata → **gap, non false positive.**
- **E-08 (Broker disconnect):** `restart: unless-stopped` e kill-switch Redis esistono, ma nessun circuit breaker su disconnect persistente → **gap parziale.**
- **E-11 (LLM timeout/drift):** FinBERT fallback e PSI drift esistono. Manca audit fallback e PSI non blocca → **gap parziale.**

---

## 7. Gaps senza evidenza sufficiente (NOT_ENOUGH_EVIDENCE)

- **E-02 — Split/dividendi/adjusted-close:** data provider e policy non verificati.
- **E-03 — ETF sostituti / sospensione:** nessun fallback documentato.
- **E-13 — Ticker ambiguity / disambiguatore:** non trovato oltre `ticker_extractor`.
- **E-21 / E-22 — Tax/regulatory / options:** esplicitamente fuori scope, ma non modellati.
- **S3 lookahead:** sospetto nel report, non verificato direttamente in questa sessione.
- **Audit trail immutabile:** non verificato se `execution_decisions` permette update.
- **RAG / supervisor LLM in S4:** non verificato se l'esecuzione S4 applica RAG/supervisor prima di usare segnale.

---

## 8. Test mancanti più importanti

1. **Anti-look-ahead / same-bar fill:** iniettare future signal, verificare esplosione con same-bar; rifare con fill t+1.
2. **Idempotenza order flow:** Celery retry, cycle lock, pending orders, duplicate BUY.
3. **Kill-switch race:** attivare killswitch durante ciclo in volo.
4. **Config validation:** inviare valori estremi a `POST /api/config`.
5. **Regime application:** simulare regime bear e verificare sizing ridotto.
6. **Cost model realismo:** ADV reale → impact >0; fixed cost in net-Sharpe.
7. **Stop-loss e2e:** bracket attach e gap-down simulation.
8. **Calendar fail-closed:** `get_clock()` failure → no orders.
9. **Reproducibility manifest:** due run identiche → hash/metriche uguali.
10. **PEAD pipeline e2e:** fetch filing reale → classify → consumer.
11. **Sensitivity reality check:** Bonferroni/White/Hansen.
12. **Secret scan:** nessuna chiave hardcoded in repo.

---

## 9. File più rischiosi

| File | Perché |
|---|---|
| `src/workers/portfolio_scheduler.py` | Hot path live: ordini, kill-switch, regime, stop-loss, calendar, pending orders. |
| `src/portfolio/orchestrator.py` | Combiner, vol targeter, constraints. |
| `src/backtest/engine/orchestrator.py` | Same-bar fill invalida tutte le metriche. |
| `src/strategies/s1/backtest.py` | Stress test circolare. |
| `src/strategies/s1/sensitivity.py` | Data mining grid. |
| `src/strategies/s1/signal.py` | Signal/sizing su prezzo corrente. |
| `src/backtest/costs/realistic.py` | Impact disattivato da ADV default. |
| `src/api/routes/admin.py` | Kill-switch API senza 2FA/cooldown. |
| `src/api/routes/config_routes.py` | Config scrivibile senza validazione. |
| `src/api/jwt_utils.py` | JWT fallback efimero. |
| `scripts/daily_analysis.sh` | API key + claude skip permissions. |
| `docker-compose.yml` | Defaults insicuri. |
| `frontend/src/pages/Config.tsx` | Slider senza bound backend. |
| `frontend/src/pages/Performance.tsx` | Regime visualizzato come attivo. |
| `frontend/src/pages/SystemLog.tsx` | PEAD tab fuorviante. |

---

## 10. Moduli che richiedono refactor

1. **`src/workers/portfolio_scheduler.py`**: troppo lungo e con molte responsabilità. Separare in preflight, orchestration, submission, post-trade.
2. **`src/portfolio/orchestrator.py`**: aggiungere net-exposure cap, risoluzione conflitti, regime prima dei vincoli.
3. **`src/backtest/engine/orchestrator.py`**: supportare fill t+1/gap; separare decision market da fill market.
4. **`src/strategies/registry.py`**: trasformare `_validate_allocations` in enforcement hard.
5. **`src/api/routes/config_routes.py`**: schema Pydantic + audit.
6. **`src/api/routes/admin.py`**: 2FA/cooldown/audit per kill-switch.
7. **`src/api/routes/system_routes.py`**: schedule dal beat; usare pg store iniettato; rimuovere `except: pass`.
8. **`src/connectors/sec_edgar.py` + `src/workers/pead_worker.py`**: refactor pipeline PEAD con fonte consensus esterna.

---

## 11. Dipendenze tra fix

```text
T-TEST-GREEN, T-SECRET-ROTATION, T-JWT-FAILFAST  →  prerequisiti per qualsiasi deploy
T-REGIME-WIRE     →  richiede T-REGIME-UI-WARNING, T-COMBINER-CONFLICT, T-VOLTARGET-ORDER
T-BT-FILL-T1      →  blocca ricalibrazione di T-GATE5-INDEPENDENT, T-SENSITIVITY-REALITY-CHECK
T-STOP-LOSS-LIVE, T-KILLSWITCH-RACE, T-CALENDAR-FAILCLOSED  →  prerequisiti per paper/live con capitale
T-COST-REAL-ADV, T-BT-KILLSWITCH  →  prerequisiti per promuovere S1 oltre paper
T-S4-GATE-FIX     →  prerequisito per promuovere S4
T-S7-WIRE         →  dipende da T-EDGAR-BODY, T-PEAD-CONSUMER (P2)
T-CONFIG-VALIDATION  →  prerequisito per qualsiasi accesso operatori non trusted
```

---

## 12. Roadmap di remediation

### 12.1 Fix immediately (bloccanti per qualsiasi paper/live)

1. `T-SECRET-ROTATION` — ruotare API key, rimuovere da repo, secret scan CI.
2. `T-JWT-FAILFAST` — JWT secret obbligatorio, no fallback.
3. `T-KILLSWITCH-RACE` — re-check killswitch prima di ogni submit + audit.
4. `T-STOP-LOSS-LIVE` — attivare bracket o stop software.
5. `T-CALENDAR-FAILCLOSED` — fail-closed su clock failure.
6. `T-CONFIG-VALIDATION` — schema + bound backend.
7. `T-PENDING-ORDERS` — gestire ordini pending per evitare duplicate BUY.
8. `T-TEST-GREEN` — dependency group, pytest-asyncio, ib_insync.

### 12.2 Add tests

9. `T-ANTI-LOOKAHEAD` — test same-bar fill.
10. `T-KILLSWITCH-E2E` — race window.
11. `T-REGIME-TEST` — sizing per regime.
12. `T-REPROD-TEST` — reproducibility manifest.

### 12.3 Refactor safely

13. `T-REGIME-WIRE` — applicare regime multiplier.
14. `T-COMBINER-CONFLICT` + `T-VOLTARGET-ORDER` — combiner + vol targeter.
15. `T-BT-FILL-T1` — fill t+1 + gap.
16. `T-GATE5-INDEPENDENT` + `T-SENSITIVITY-REALITY-CHECK` — validazione corretta.
17. `T-COST-REAL-ADV` + `T-COST-MODEL-TRUTH` — costi realistici + fixed cost.

### 12.4 Validate later

18. `T-S4-GATE-FIX` — riparare gate report.
19. `T-S3-LOOKAHEAD` — verificare S3.
20. `T-PEAD-UI-DISCLAIMER` + `T-S7-WIRE` (P2) — PEAD.

### 12.5 Product/frontend improvements

21. `T-REGIME-UI-WARNING` — regime non applicato.
22. `T-PEAD-UI-DISCLAIMER` — PEAD R&D.
23. `T-PROMO-DASHBOARD` — promotion readiness.

---

## 13. Lista ticket tecnici implementabili (riepilogo)

| Ticket | Titolo | Priorità | Effort | Blocca |
|---|---|---|---|---|
| T-SECRET-ROTATION | Ruotare API key hardcoded e secret scan | P0 | XS | deploy |
| T-JWT-FAILFAST | JWT secret obbligatorio, no fallback | P0 | XS | deploy |
| T-KILLSWITCH-RACE | Re-check killswitch prima di ogni submit + audit | P0 | S | live |
| T-STOP-LOSS-LIVE | Attivare stop-loss live (bracket o software) | P0 | S | live |
| T-CALENDAR-FAILCLOSED | Fail-closed su market clock failure | P0 | XS | live |
| T-CONFIG-VALIDATION | Validazione schema e bound su POST /api/config | P0 | S | live |
| T-PENDING-ORDERS | Gestione ordini pending per evitare duplicate BUY | P0 | S | live |
| T-TEST-GREEN | Ripristinare test suite e pytest-asyncio | P0 | M | qualsiasi change |
| T-BT-FILL-T1 | Fill t+1 + gap nel backtest | P0 | M | S1 promotion |
| T-S4-GATE-FIX | Riparare script gate report S4 | P0 | S | S4 promotion |
| T-REGIME-WIRE | Applicare regime multiplier nel live | P0 | S | live |
| T-COMBINER-CONFLICT | Risoluzione conflitti + net-exposure cap | P1 | M | multi-strategy |
| T-VOLTARGET-ORDER | Vol targeter prima dei vincoli | P1 | XS | risk |
| T-BT-KILLSWITCH | Modellare kill-switch in backtest | P1 | M | S1 promotion |
| T-COST-REAL-ADV | ADV reale nel cost model | P1 | XS | live parity |
| T-COST-MODEL-TRUTH | Fixed cost in net-Sharpe + doc costi | P1 | XS | economics |
| T-GATE5-INDEPENDENT | Stress test con periodi indipendenti | P0 | S | S1 validation |
| T-SENSITIVITY-REALITY-CHECK | Reality check su sensitivity grid | P1 | S | S1 validation |
| T-REGIME-UI-WARNING | Warning regime non applicato in UI | P0 | XS | frontend trust |
| T-PEAD-UI-DISCLAIMER | Etichetta R&D per PEAD tab | P0 | XS | frontend trust |
| T-EDGAR-BODY | Fetch contenuto reale 8-K | P1 | M | S7 |
| T-PEAD-CONSUMER | Consumer PEAD signals in orchestrator | P1 | M | S7 |
| T-S7-WIRE | Registrare S7 e implementare `__call__` | P1 | M | S7 |
| T-SYSTEM-ROUTES-SYNC | Schedule da beat + rimuovere except:pass | P1 | S | observability |
| T-DOCKER-HARDENING | USER non-root, secret env, resource limits | P1 | S | ops |
| T-CI-EXPAND | mypy, pip-audit, coverage in CI | P2 | S | quality |
| T-BT-REPRODUCIBLE | Reproducibility manifest + test | P0 | M | audit |
| T-AUDIT-LOG | Rimozione/populamento audit_log | P3 | XS | cleanup |
| T-STRAT-DOC | Correggere docstring strategie | P3 | XS | cleanup |

---

## 14. Raccomandazione finale

**Non procedere a nessun deploy live o paper con capitale reale finché i ticket P0 della sezione 12.1 non sono chiusi, testati e validati.** In particolare, i blockers assoluti sono:

- Secret rotation (`T-SECRET-ROTATION`)
- JWT fail-fast (`T-JWT-FAILFAST`)
- Kill-switch race fix (`T-KILLSWITCH-RACE`)
- Stop-loss live attivo (`T-STOP-LOSS-LIVE`)
- Calendar fail-closed (`T-CALENDAR-FAILCLOSED`)
- Config validation (`T-CONFIG-VALIDATION`)
- Pending orders / duplicate BUY (`T-PENDING-ORDERS`)
- Test suite verde (`T-TEST-GREEN`)
- Backtest fill t+1 (`T-BT-FILL-T1`)
- Regime wiring (`T-REGIME-WIRE`)
- S4 gate fix (`T-S4-GATE-FIX`)

Solo dopo aver chiuso i P0 si può riaprire la discussione su S1 50% live, e solo con:

- 90 giorni di paper trading validato,
- reproducibility manifest (`T-BT-REPRODUCIBLE`),
- DR/backup policy verificata,
- capitale ≤5% come da spec.

---

*Documento prodotto in modalità read-only. Nessun file di codice modificato, nessun ordine live eseguito.*
