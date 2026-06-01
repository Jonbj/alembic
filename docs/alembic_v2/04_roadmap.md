# 04 — Roadmap

## Principi operativi della roadmap

1. **Una strategia alla volta**. No parallelizzazione su strategie incomplete.
2. **Backtest framework PRIMA delle strategie**. Senza framework, ogni strategia "validata" è in dubbio.
3. **Iterazione veloce dentro vectorbt, validazione finale dentro NautilusTrader**.
4. **Strategy passa tutti i 5 gate prima di entrare nel portfolio combinato**.
5. **Niente live trading senza 90 giorni di paper trading combinato post-validazione**.

---

## Convenzioni dei task

| Campo | Significato |
|-------|-------------|
| ID | Identificativo (T-NNN per task) |
| Priorità | P0 (bloccante) · P1 (core) · P2 (production) · P3 (R&D) |
| Effort | S (1-2d) · M (3-5d) · L (1-2w) · XL (3-4w) |
| Dipendenze | ID di task precedenti |
| Status | OPEN · IN_PROGRESS · DONE · BLOCKED |

---

## FASE A — Foundation backtest (settimane 1-4)

Senza questa fase, tutto il resto è speculativo. **Niente strategia viene scritta prima della fine di Fase A.**

### T-001 — Setup vectorbt + data loading

**Priorità**: P0 | **Effort**: M | **Dipendenze**: nessuna

Setup environment con vectorbt-pro (license community o open-source vectorbt è sufficiente). Implementare data loader unificato.

**Componenti**:
- `backtest/data/loader.py`: load price data da Yahoo + cache parquet
- `backtest/data/universe.py`: gestione universe (US ETFs + 72 equity esistente)
- Schema dataframes standard: `DatetimeIndex`, columns OHLCV
- Caching parquet per evitare re-download

**Acceptance**:
- [ ] Load 30 anni di daily data per 15 ETF cross-asset in < 30s
- [ ] Data cached in parquet
- [ ] Unit test: data point-in-time corretto (no future data leak)

---

### T-002 — Backtest engine event-driven base

**Priorità**: P0 | **Effort**: L | **Dipendenze**: T-001

Implementare backtest orchestrator con event loop, virtual portfolio, fill simulation base.

**Componenti**:
- `backtest/engine/orchestrator.py`: event loop con timestep advance
- `backtest/engine/virtual_portfolio.py`: tracking positions, NAV, P&L
- `backtest/engine/order_simulation.py`: convert orders → fills con cost model base
- `backtest/engine/data_replay.py`: serve dati point-in-time

**Acceptance**:
- [ ] Test: replay 1 anno di SPY buy-and-hold, NAV trajectory coincide con SPY adjusted close entro 0.5%
- [ ] Test: order BUY → position aumenta, order SELL → position diminuisce
- [ ] Test: anti-look-ahead automatico (sentinel test passes)
- [ ] Backtest 5 anni gira in < 2 min

---

### T-003 — Cost model serio

**Priorità**: P0 | **Effort**: M | **Dipendenze**: T-002

Implementare cost model con spread tiered + market impact + commission. Validato contro literature.

**Componenti**:
- `backtest/costs/spread_model.py`: spread tier lookup per ticker
- `backtest/costs/impact_model.py`: square-root impact
- `backtest/costs/commission.py`: Alpaca + IBKR + SEC fees

**Acceptance**:
- [ ] Test su SPY ordine 100k$: slippage < 5 bps total
- [ ] Test su small-cap ordine 1M$: slippage > 30 bps
- [ ] Config-driven, tutti i parametri in YAML

---

### T-004 — Anti-look-ahead enforcement test suite

**Priorità**: P0 | **Effort**: S | **Dipendenze**: T-002

Suite di test specifici per garantire no look-ahead.

**Componenti**:
- `tests/backtest/test_no_lookahead.py`: sentinel testing
- `tests/backtest/test_data_timestamps.py`: verifica che ogni data point letto abbia `timestamp <= as_of`
- CI integration: questi test non possono fallire mai

**Acceptance**:
- [ ] Tutti i test passano
- [ ] Sentinel test trova look-ahead se introdotto artificialmente
- [ ] CI fail-fast su questi test

---

### T-005 — Walk-forward framework

**Priorità**: P0 | **Effort**: M | **Dipendenze**: T-002

Implementare walk-forward con rolling windows, concat OOS results.

**Componenti**:
- `backtest/walkforward/runner.py`: rolling window orchestration
- `backtest/walkforward/aggregator.py`: concat OOS results, compute aggregate metrics

**Acceptance**:
- [ ] WF su 10 anni con SPY buy-and-hold: OOS metrics ≈ full period metrics (sanity check)
- [ ] WF salva risultati per ogni window
- [ ] WF report HTML auto-generato

---

### T-006 — Metrics engine completo

**Priorità**: P0 | **Effort**: M | **Dipendenze**: T-002

Implementare tutte le metriche di performance + risk + attribution + signal quality.

**Componenti**:
- `backtest/metrics/performance.py`: Sharpe, Sortino, Calmar
- `backtest/metrics/risk.py`: VaR, ES, drawdown, skew/kurt
- `backtest/metrics/signal_quality.py`: IC, ICIR, p-value, DSR
- `backtest/metrics/attribution.py`: per-strategy contributions
- Validation contro `empyrical` library

**Acceptance**:
- [ ] Tutti i metric coincidono con empyrical su test data noto
- [ ] DSR implementato seguendo López de Prado correttamente
- [ ] Report markdown + HTML auto-generato

---

### T-007 — Validation gates implementation

**Priorità**: P0 | **Effort**: M | **Dipendenze**: T-006

Implementare i 5 validation gates come funzioni rieseguibili.

**Componenti**:
- `backtest/gates/gate_1_significance.py`
- `backtest/gates/gate_2_walkforward.py`
- `backtest/gates/gate_3_robustness.py`
- `backtest/gates/gate_4_regime.py`
- `backtest/gates/gate_5_stress.py`
- `backtest/gates/runner.py`: esegue tutti, produce gate report

**Acceptance**:
- [ ] Test su strategia placeholder (random): fallisce tutti i gate
- [ ] Test su SPY buy-and-hold: passa gate 1, 2, 5; fallisce 3, 4 (ok, atteso)
- [ ] Gate report ben formattato

---

### **Milestone A: Backtest Foundation Ready**

Alla fine di Fase A (~4 settimane part-time):
- [ ] Posso girare un backtest custom su strategia placeholder in < 5 min
- [ ] Anti-look-ahead automatico
- [ ] Walk-forward funzionante
- [ ] Tutti i metric standard disponibili
- [ ] 5 validation gates implementati e testati

**Niente strategia oltre questa milestone se i gate non sono pronti**.

---

## FASE B — Strategia 1: Time-Series Momentum (settimane 5-7)

La strategia più "boring" e robusta. Prima da implementare perché:
- Letteratura più chiara
- Implementation più semplice
- Setup multi-asset universe utile per le altre strategie

### T-101 — Universe definition e data per S1

**Priorità**: P0 | **Effort**: S | **Dipendenze**: T-001

Definire 15-ticker universe cross-asset, download data 30+ anni, validare quality.

**Acceptance**:
- [ ] 15 ETF + adjusted close storici (alcuni hanno solo 10-15 anni di storia es. TIP, gestire)
- [ ] Data validato (no gap, no spike anomali, dividend-adjusted)
- [ ] Universe documentato in YAML

---

### T-102 — S1 signal computation

**Priorità**: P0 | **Effort**: M | **Dipendenze**: T-101

Implementare signal computation: 12-1 momentum + vol normalization.

**Componenti**:
- `strategies/s1/signal.py`: signal generation
- `strategies/s1/sizing.py`: inverse-vol sizing
- Test unit per ogni componente

**Acceptance**:
- [ ] Signal computato per universe e timestamp
- [ ] Output dataframe `(ticker, as_of, signal, weight)`
- [ ] Unit test su synthetic data noto

---

### T-103 — S1 strategy module (interfaccia standard)

**Priorità**: P0 | **Effort**: S | **Dipendenze**: T-102

Wrap signal+sizing in `BaseStrategy` interface per essere usato dal backtest engine.

**Acceptance**:
- [ ] `TimeSeriesMomentum(BaseStrategy)` implementa `compute_target_weights`
- [ ] Config caricato da YAML
- [ ] Health check implementato

---

### T-104 — S1 backtest individuale + gate run

**Priorità**: P0 | **Effort**: M | **Dipendenze**: T-103, T-007

Eseguire backtest completo S1 su 30+ anni, runare tutti i 5 gate.

**Acceptance**:
- [ ] Backtest completo gira clean
- [ ] Report: Sharpe, DD, attribution per asset class
- [ ] Tutti i 5 gate: report con pass/fail
- [ ] **Se non passa gate**: documentare why, fix, re-run. Niente paper trading se fail.

---

### T-105 — S1 sensitivity analysis

**Priorità**: P1 | **Effort**: S | **Dipendenze**: T-104

Test su varianti parametri per documentare sensitivity.

**Componenti**:
- Grid search su lookback_long_days ∈ [126, 189, 252, 378, 504]
- Grid search su vol_window_days ∈ [20, 30, 60, 90]
- Sharpe surface plot

**Acceptance**:
- [ ] Sensitivity report HTML/PDF
- [ ] Verify che parametri base scelti (252, 60) sono near-optimum ma non picco

---

### **Milestone B: S1 validated**

- [ ] S1 passa tutti i 5 gate
- [ ] Sensitivity analysis documentata
- [ ] OOS Sharpe ≥ 0.5 net of costs

---

## FASE C — Strategia 3: Cross-Sectional Momentum Equity (settimane 8-10) ✅ CODE COMPLETE, R&D SLEEVE

Implementata prima di S2 perché più semplice (no opzioni). Riusa il universe US equity esistente.
**DECISIONE 01/06/2026**: S3 gates 3&5 FALLITI. OOS Sharpe 0.15. Demoted a R&D sleeve.
Codice preservato, tuning parametri rimandato a post-Fase-F.

### T-201 — Universe + liquidity filter

**Priorità**: P0 | **Effort**: S | **Dipendenze**: nessuna oltre T-001

Implementare liquidity filter dinamico point-in-time sull'universe esistente.

**Acceptance**:
- [ ] Universe filtrato per liquidity, point-in-time corretto (no survivorship)
- [ ] N ticker tipico nell'universo dopo filter: 50-65

---

### T-202 — S3 signal: residual momentum

**Priorità**: P0 | **Effort**: M | **Dipendenze**: T-201

Signal: 12-1 momentum aggiustato per beta.

**Componenti**:
- Beta computation rolling 252d
- Residual momentum = momentum - beta × SPY_momentum
- Cross-sectional ranking

**Acceptance**:
- [ ] Output `(as_of, ticker, residual_momentum, rank, decile)`
- [ ] Unit test su synthetic data

---

### T-203 — S3 strategy module + backtest

**Priorità**: P0 | **Effort**: M | **Dipendenze**: T-202, T-007

Strategy module + backtest + gate run.

**Acceptance**:
- [ ] Passa tutti i gate (atteso: Sharpe 0.4-0.6 OOS, sotto S1)
- [ ] Drawdown peggiore in momentum crashes (2009, 2020): documentato

---

### **Milestone C: S3 R&D sleeve** (01/06/2026 — DECISION: S3 demoted to R&D)

S3 code completo (32 test passing) ma backtest su dati reali fallisce:
- OOS Sharpe 0.15 (vs S1 che 0.51)
- Gate 3 FAIL: CV=2.05 >> max_cv=0.5 (non robusta a perturbazione parametri)
- Gate 5 FAIL: cum_return=-10.07% < threshold=-10%

**Decisione**: S3 esclusa dal portfolio live. Codice preservato per futura R&D.
- [x] S3 code completo e funzionante (synthetic)
- [x] Gate run su dati reali completato
- [x] Decisione documentata: Option 4 — drop come R&D sleeve
- [ ] S3 sensitivity analysis (long-only, lookback diversi, universe più piccolo) rimandata a post-Fase-F

---

## FASE D — Strategia 2: Volatility Risk Premium (settimane 11-16) ← CURRENT

La più complessa tecnicamente. Richiede options data + IBKR integration. Effort più alto, ma con ROI potenziale più alto.
**Portfolio live comporrà di S1 + S2 + S4** (S3 escluso come R&D sleeve).

### T-301 — IBKR API setup

**Priorità**: P0 | **Effort**: M | **Dipendenze**: nessuna

Setup IBKR connection (TWS paper account ok per development).

**Componenti**:
- `brokers/ibkr_adapter.py`: implementazione `BrokerAdapter`
- Connection management, auto-reconnect
- Auth via env variables

**Acceptance**:
- [ ] Connect to IBKR paper, get account state
- [ ] Submit and cancel test orders
- [ ] Get historical option chain

---

### T-302 — Option chain ingestion + storage

**Priorità**: P0 | **Effort**: L | **Dipendenze**: T-301

Pipeline per ingestion option chain (SPY initially), storage in Postgres.

**Componenti**:
- `data/options/ingestion.py`: pull chain end-of-day
- Tabella `option_chains` storica
- Backfill da provider esterno (CBOE, Tradier, IBKR historical)

**Acceptance**:
- [ ] 5+ anni di SPY option chain end-of-day in DB
- [ ] Query: chain at specific date in < 1s
- [ ] Data quality validato

---

### T-303 — Black-Scholes + greeks

**Priorità**: P0 | **Effort**: S | **Dipendenze**: nessuna

Pricing model base per validare prezzi e calcolare greeks.

**Acceptance**:
- [ ] Price + delta + theta + vega + gamma per opzione data
- [ ] Implied vol solver
- [ ] Validato contro option pricers pubblici

---

### T-304 — S2 signal: put selection + entry rules

**Priorità**: P0 | **Effort**: M | **Dipendenze**: T-302, T-303

Logica di selection: dato as_of, trovare put da vendere.

**Componenti**:
- Filter chain per: target delta -0.20, DTE 30-45
- Validazione liquidity (volume, OI)
- Sizing logic basata su collaterale disponibile

**Acceptance**:
- [ ] Dato as_of e capitale, output: contract specifico da vendere + quantity
- [ ] Test su 100 random as_of: nessuno fail

---

### T-305 — S2 exit logic

**Priorità**: P0 | **Effort**: M | **Dipendenze**: T-304

Logica di chiusura: target profit, stop loss, time decay, signal flip.

**Acceptance**:
- [ ] Profit target 50% premium: chiude correttamente
- [ ] Stop loss 2x premium: chiude correttamente
- [ ] Assignment risk monitoring (se put diventa deep ITM near expiry)

---

### T-306 — S2 regime modulation overlay

**Priorità**: P1 | **Effort**: S | **Dipendenze**: T-304, esistente regime_classifier

Integrazione del regime classifier per modulare aggressività.

**Acceptance**:
- [ ] RISK_OFF → 50% size
- [ ] STRESS → no new positions
- [ ] Config-driven

---

### T-307 — S2 event filter (LLM + news ingestion)

**Priorità**: P1 | **Effort**: M | **Dipendenze**: esistente LLM ensemble

Filter event risk usando ensemble esistente.

**Acceptance**:
- [ ] Sentiment SPY < -0.5: block new positions
- [ ] Pre-FOMC/NFP window: block
- [ ] Backtest mostra event filter effectivamente riduce DD

---

### T-308 — S2 backtest completo + gate run

**Priorità**: P0 | **Effort**: L | **Dipendenze**: T-304, T-305, T-306, T-307

Backtest completo S2 su 10+ anni di option data, gate run.

**Acceptance**:
- [ ] Passa tutti i gate
- [ ] OOS Sharpe ≥ 0.7 net of costs (atteso 0.9-1.1)
- [ ] Max DD ≤ 25% (con regime modulation + event filter attivi)
- [ ] Sopravvive marzo 2020 senza blow-up

---

### **Milestone D: S2 validated**

- [ ] S2 passa tutti i 5 gate
- [ ] Backtest robusto a stress test 2008, 2020, 2022, 2018

---

## FASE E — Strategia 4: News-Driven Tactical refactor (settimane 17-18)

Refactor della strategia attuale per renderla compatibile col framework multi-strategia. Effort basso perché 90% del codice esiste già.

### T-401 — Refactor signal generation a cross-sectional ranking

**Priorità**: P0 | **Effort**: S | **Dipendenze**: nessuna

Cambiare da "score > 0.30 → buy" a "rank top 5 in universe → long".

**Acceptance**:
- [ ] Output: top 5 ticker per as_of, equal weighted dentro bucket S4
- [ ] Bucket sized to 10% of portfolio
- [ ] Backward compatible con signal aggregation esistente

---

### T-402 — S4 strategy module (interfaccia standard)

**Priorità**: P0 | **Effort**: S | **Dipendenze**: T-401

Wrap in `BaseStrategy`.

**Acceptance**:
- [ ] Implementa interface
- [ ] Compatibile con backtest engine

---

### T-403 — S4 backtest su news replay storico + gate run

**Priorità**: P0 | **Effort**: M | **Dipendenze**: T-402, esistente news replay

Backtest S4 standalone usando news replay storico GDELT esistente.

**Acceptance**:
- [ ] Passa gate 1, 5 (significance + stress)
- [ ] Gate 2, 3, 4: best effort (alpha incerto)
- [ ] **Anche se non passa tutti i gate, S4 entra in portfolio combinato al 10%** (è R&D sleeve, criteri più tolleranti)

---

## FASE F — Portfolio combiner + integrazione (settimane 19-22)

### T-501 — Portfolio combiner base

**Priorità**: P0 | **Effort**: L | **Dipendenze**: T-103, T-308 (S1, S2 validati; S3 escluso dal portfolio iniziale)

Implementare combiner: aggregate strategy outputs, apply allocation %, base constraint.

**Acceptance**:
- [ ] Input: lista StrategyOutput, output: final target weights
- [ ] Test: con 1 sola strategia attiva, output = strategy output (sanity)
- [ ] Test: con 4 strategie, weights aggregati correttamente

---

### T-502 — Risk parity overlay

**Priorità**: P1 | **Effort**: M | **Dipendenze**: T-501

Risk parity allocation cross-strategy, sostituisce allocation fissa.

**Acceptance**:
- [ ] Risk parity calcola weights per uguale risk contribution
- [ ] Backtest combinato con e senza risk parity, comparison

---

### T-503 — Cross-strategy constraint enforcer

**Priorità**: P0 | **Effort**: M | **Dipendenze**: T-501

Constraint multi-strategy: max single asset, max sector, max correlation cluster.

**Acceptance**:
- [ ] Constraint violation logged con strategia che ha causato
- [ ] Iterative resolution stabile

---

### T-504 — Vol targeting overlay

**Priorità**: P0 | **Effort**: S | **Dipendenze**: T-503

Vol targeting finale sul portfolio combinato.

**Acceptance**:
- [ ] Portfolio vol stimato ≈ target_total_vol (10%)
- [ ] Backtest: vol realizzata vicina a target

---

### T-505 — Full multi-strategy backtest

**Priorità**: P0 | **Effort**: M | **Dipendenze**: T-501-T-504

Backtest combinato finale, 3 strategie attive (S1+S2+S4) + combiner (S3 esclusa come R&D sleeve).

**Acceptance**:
- [ ] OOS Sharpe combinato ≥ 0.8 net of costs (atteso 1.0-1.2)
- [ ] DD combinato ≤ 18%
- [ ] Diversification ratio > 1.3

---

### **Milestone F: Combined system validated**

- [ ] Multi-strategy backtest produce numbers attesi
- [ ] Tutte le strategie convivono senza conflitti
- [ ] Risk parity overlay funziona

---

## FASE G — Production deployment (settimane 23-30)

### T-601 — Strategy registry + Celery task per multi-strategia

**Priorità**: P0 | **Effort**: M

Setup orchestrazione Celery per multiple strategie.

---

### T-602 — Risk monitor multi-strategy

**Priorità**: P0 | **Effort**: M | **Dipendenze**: esistente risk_monitor

Estendere risk monitor per portfolio multi-strategia.

---

### T-603 — Dashboard monitoring multi-strategia

**Priorità**: P1 | **Effort**: L

Dashboard Grafana o custom per visualizzare:
- Per-strategy PnL
- Combined PnL vs benchmark
- Risk metrics live
- Strategy health (decay scores)
- Alerts

---

### T-604 — Paper trading combinato

**Priorità**: P0 | **Effort**: continuative

Setup paper trading multi-strategia, monitor 90 giorni minimum.

**Acceptance**:
- [ ] Sistema gira senza crash 90gg consecutivi
- [ ] Live performance vs backtest entro 1σ
- [ ] Tutte le alert e safety check funzionano

---

### T-605 — Decay monitoring runtime

**Priorità**: P0 | **Effort**: M

Job mensile che gira walk-forward su data recente e confronta con backtest. Alert su degrado.

---

### **Milestone G: Paper trading 90gg passed**

- [ ] 90 giorni live paper senza problemi
- [ ] Performance entro tolerance
- [ ] Tutti i monitoring funzionanti

---

## FASE H — Optional next steps (post Milestone G)

### T-701 — Live trading small scale

Se Milestone G passata, valutare live con capitale piccolo (5-10k).

---

### T-702 — Strategy 5+ R&D

Sperimentare nuove strategie:
- **S3 Cross-Sectional Momentum R&D**: long-only, lookback diversi (6m, 3m), universe più piccolo (top 30 per liquidi), beta-adjusted vs raw momentum. Rifare gate run se i risultati sono promettenti.
- Trend-following commodities specifico
- Vol risk premium calls (covered call)
- Carry strategies cross-asset
- Macro factor portfolio

Ogni nuova strategia: stessi 5 gate, no exceptions.

---

### T-703 — Cross-asset correlations regime-conditional

Modello più sofisticato di correlation per il combiner.

---

## Sintesi temporale

| Fase | Settimane | Outcome |
|------|-----------|---------|
| A — Foundation backtest | 1-4 | Backtest engine + gates pronti |
| B — S1 Time-Series Momentum | 5-7 | S1 validated |
| C — S3 Cross-Sectional Momentum | 8-10 | S3 R&D sleeve (gates FAIL) |
| D — S2 Volatility Risk Premium | 11-16 | S2 validated |
| E — S4 News Refactor | 17-18 | S4 in portfolio (10%) |
| F — Portfolio combiner | 19-22 | Sistema integrato |
| G — Production deployment | 23-30 | Paper trading 90gg |

**Totale: ~30 settimane part-time** (~7 mesi a 15-20 ore/settimana).

---

## Anti-goals

Cose che esplicitamente NON facciamo in questa roadmap:

- ❌ Aggiungere altri ticker all'universe prima che il framework sia validato
- ❌ Inseguire alpha "interessante" trovato per caso senza gate run completo
- ❌ Andare live (capitale reale) prima di 90+ giorni paper trading passati
- ❌ Implementare features SaaS, multi-tenant, frontend cliente
- ❌ Costruire alpha miner separato prima delle 4 strategie base
- ❌ Ottimizzare hyperparameter su data recente
- ❌ Implementare strategie crypto/forex/futures (out of scope v2)
- ❌ Tax engine completo (solo bollo + lot accounting base per ora)
- ❌ Reporting LLM client-facing (siamo single-user)

Quando uno di questi anti-goals diventa interessante, va in `FASE H` o oltre, **dopo** milestone G.

---

## Decisioni esplicite di scope

**Capitale**: nessuno (backtest + paper only) durante tutta la roadmap. Decisione live dopo Milestone G.

**Broker**: Alpaca paper (S1, S4) + IBKR paper (S2). S3 non in paper trading (R&D sleeve). No live broker in roadmap.

**Mercati**: US-listed only. Italian/EU markets out of scope.

**Asset classes**: equity (single names + ETF), bond (ETF), commodity (ETF), gold (ETF), opzioni su SPY only.

**Frequenze**: daily o monthly per le strategie. Niente intraday per ora.

**Short selling**: disabilitato in v2 (long-only + cash). Re-evaluation in FASE H.

**LLM signals**: usati come overlay (S2 event filter, S4 alpha source). Non come signal direzionale primary per S1/S3.

**Compliance/legal**: out of scope. Sistema per uso personale.
