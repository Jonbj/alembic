# S2 — 06 Audit implementazione (12 assi)

**Strategia:** S2 `VRPStrategy`
**Data:** 2026-08-04
**Metodo:** lettura codice + DB read-only (`docker exec alembic-postgres-1 psql -U
trading -d trading`). Verdetto per asse. Fonti: fase 01 §1-11, fase 05 §1-3.

---

| # | Asse | Verdetto | Evidenza |
|---|---|---|---|
| 1 | Data timing | ✅ OK | Bar-time daily; RV63 rolling su close. Nessun event-time richiesto (no dati intraday). `strategy.py:88` |
| 2 | Look-ahead bias | ❌ FAIL | (a) Universo: usa S1 universe (inception-aware non delisting-aware, vedi S1 BUG-3) — eredita survivorship. (b) `_split_regime_returns` (`backtest.py:202-211`) classifica bull/bear con `fwd_21d = cum_return.shift(-21)/cum_return - 1` → **uso di rendimenti futuri** per il regime gate 4. Stessa famiglia di S1 OBS-4. |
| 3 | Leakage | ⚠️ PARTIAL | Nessuna normalizzazione fit su tutto il campione nel signal (RV63 è online). MA `_split_regime_returns` e `_extract_stress_periods` sono calcolati sull'intera serie OOS prima del gate → leakage intra-OOS nel gate evaluation (regime/stress definiti con hindsight). |
| 4 | Survivorship | ❌ FAIL | `run_s2_backtest_full` (backtest.py:271) usa `load_universe("s1")` = `sp500_tickers.csv` snapshot corrente + yfinance 1993→oggi → solo sopravvissuti; SPY ETF non delista, ma i componenti S1 sì. Eredita S1 BUG-3. |
| 5 | Backtest metodologia | ⚠️ PARTIAL | WF 1260/252 → 3 finestre (`summary.json` n_windows=3), DSR n_trials implicito piccolo. T+1 + costi realistici via `BacktestConfig` default (orchestrator, come S1). **MA** il P&L misurato è long-SPY equity, non short-put (DV-4) → la metodologia è corretta in forma ma misura l'oggetto sbagliato. |
| 6 | Signal generation | ⚠️ DRIFT | `select_put` opera su catena **sintetica** (`OptionChainDataLoader.generate_chain`), non di mercato. IV/delta/OI/volume sono simulati. Il VRP filter `IV−RV≥0` su IV sintetica ≈ RV63 (entrambe derivate dallo stesso underlying) → il filtro è quasi tautologico. |
| 7 | Portfolio allocation | ⚠️ PARTIAL | `max_collateral_pct=0.20` hardcoded; `apply_regime_scale` (regime.py:44) **mai chiamato** (DV-10) → il regime scala solo l'equity via `_target_spy_shares`, non il qty put. Sizing indipendente dal segnale. No sleeve ring-fence, no 2% NAV max-loss, no margine stressato (violazione PO §19). |
| 8 | Risk controls | ⚠️ AMBER | Exit logic (exit.py) ben strutturata (5 priorità). MA: reprice put con IV di entry stale (DV-7); SIGNAL_FLIP usa IV(entry)−RV(corrente); underlying_stop 5% su prezzo equity, non sul collaterale put. Nessun kill-switch, nessun drawdown cap. |
| 9 | Execution | ✅ OK (backtest) / N/A (live) | Backtest: `Order.market_order` SPY, fill T+1 via orchestrator. Live: S2 enabled=false + hard-block registry.py:231 → **mai eseguito**. |
| 10 | Accounting | ❌ FAIL | `compute_pnl` (exit.py:39) calcola P&L short-put ma **non è scritto nel NAV** (portfolio.py:97 = cash + equity). L'OOS Sharpe misura long-SPY, non P&L strategia (DV-4). Accounting divergence fondamentale. |
| 11 | Paper-trading | N/A | S2 mai in paper; `mode=disabled`, `approved=false`, hard-block. Nessun ciclo portfolio-cycle costruisce S2. |
| 12 | Runtime | ✅ CONFIRMED DEAD | DB `trades` (ultimi 30g): `stop_strategy` ∈ {S1:75, S4:64, NULL:56} — **zero S2**. Un trade SPY (2026-07-10) è NULL-attributed (pre-wiring), non S2. S2 è morto in produzione per costruzione. |

## Sintesi

- **Assi rossi (FAIL)**: 2 (look-ahead), 4 (survivorship), 10 (accounting — P&L sbagliato).
- **Assi gialli (PARTIAL/DRIFT/AMBER)**: 3, 5, 6, 7, 8.
- **Assi verdi**: 1 (timing), 9 (exec backtest), 12 (runtime: confermato inattivo).
- **N/A**: 11.

L'asse **10 (accounting)** è il più grave per la validità: il backtest non misura
la strategia descritta (short-put VRP) ma una sua proxy equity. Combinato con
**DV-5** (sostituzione vietata dal PO) e **asse 2** (regime look-ahead), l'evidenza
numerica interna (`oos_sharpe=−0.613`) non è interpretabile come test del VRP.

Il runtime è **concordemente inattivo** (DB + registry hard-block + yaml disabled +
lifecycle disabled/approved=false): S2 non rischia capitale, non ha bug runtime
attivi, e l'audit runtime si riduce a confermare l'inattività.

## Note per fase 07 (bug)

Candidati bug da confermare con repro/traccia:
- BUG-A: regime split look-ahead `fwd_21d` (backtest.py:202-211) — controesempio
  matematico (come S1 OBS-4 ma qui attivo nel gate 4).
- BUG-B: `apply_regime_scale` dead code (regime.py:44 mai chiamato) — grep 0 call site.
- BUG-C: reprice/SIGNAL_FLIP con IV di entry stale (strategy.py:171,220) — traccia
  statica.
- BUG-D: dead config S2Config() no from_yaml (scheduler:3074) — grep 0 `from_yaml`
  (come S1 BUG-1; S2 ha file yaml `config/s2`? da verificare; in ogni caso non wired).
- BUG-E: accounting divergence (compute_pnl non scritto nel NAV) — traccia statica
  + controesempio: due run identici tranne per il `current_mid` della put
  mostrano NAV identico (il NAV ignora il P&L put).

---
**Stato fase:** 06_implementation_audit = **done**. Prossimo cursore: `S2:07_bugs`.