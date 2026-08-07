# S2 — 05 Mappatura codice (spec → sorgente)

**Strategia:** S2 `VRPStrategy`
**Data:** 2026-08-04
**Metodo:** lettura diretta di `src/strategies/s2/*.py`, `src/strategies/registry.py`,
`src/workers/portfolio_scheduler.py`, `src/backtest/engine/portfolio.py`,
`src/backtest/engine/orchestrator.py`. Ogni componente è mappato a `file:line`.
Le divergenze (DV-*) sono puntatori alle fasi 04/06/07.

---

## 1. Mappatura componente → codice

| Componente spec (fase 01) | Codice `file:line` | Note |
|---|---|---|
| Underlying hardcoded SPY | `strategy.py:49` `_UNDERLYING = "SPY"` | |
| Realized vol (RV63) | `strategy.py:88` `spy_close.pct_change().rolling(63).std() * np.sqrt(252)` | Lato "P" = RV passata (DV-2) |
| `_get_realized_vol_at` | `strategy.py:127-135` | fallback 0.15 se nessun dato |
| Regime da RV | `strategy.py:114-125` (`_get_regime`) | soglie 0.12/0.20/0.35 |
| `regime_scales` | `config.py:25-32` | bull 1.0/sidew 0.75/bear 0.25/high_vol 0.0 |
| `modulate_by_regime` | `regime.py:31-41` | `position_scale = regime_scales[regime]` |
| `apply_regime_scale` (put qty) | `regime.py:44-62` | **non chiamato** nel path backtest (vedi §3 DV-10) |
| Event filter FOMC/NFP | `event_filter.py:30-65` | date deterministiche (3° mer / 1° ven) |
| `check_event_filter` | `event_filter.py:74-103` | sentiment skippato (sentiment=None nel backtest) |
| `select_put` | `signal.py:44-138` | delta −0.20±0.05, DTE 30-45, OI≥100, vol≥10 |
| Filtro delta | `signal.py:89-91` | banda [−0.25, −0.15] |
| Filtro liquidità | `signal.py:94-97` | su catena **sintetica** |
| Filtro VRP `IV−RV≥0` | `signal.py:100-101` | threshold 0.0; `vrp_entry_threshold` (DV-1) |
| Selezione delta più vicino | `signal.py:107-109` | `_delta_dist` min |
| Sizing opzioni `quantity` | `signal.py:112-115` | `floor(capital·max_collateral/(strike·100))` |
| PutSignal sintetico (se select_put=None) | `strategy.py:306-327` | strike 0.95·price, mid 0.02·price, expiry +30g |
| Sizing SPY-equivalent | `strategy.py:176-186` (`_target_spy_shares`) | `shares = NAV·0.20·scale/spy_price` (indipendente dal put) |
| NAV stimato | `strategy.py:283-288` | `cash + |SPY_qty|·spy_price` |
| Ordine BUY SPY | `strategy.py:334-342` | `BUY max(0, target_shares − current_qty)` |
| Exit `evaluate_exit` | `exit.py:48-105` | priorità EXPIRY→STOP→TARGET→TIME→FLIP |
| `compute_pnl` short-put | `exit.py:39-45` | `(entry_mid − current_mid)·qty·100` — **non scritto nel NAV** (DV-4) |
| Reprice put BS | `strategy.py:158-174` (`_reprice_put`) | `sigma=signal.implied_vol` (entry IV), r=0.05 fisso (DV-7) |
| Exit SELL SPY | `strategy.py:228-238` | vende quote SPY, non chiude put reale |
| SIGNAL_FLIP | `exit.py:101-103` | `implied_vol − realized_vol < 0` con IV=entry (DV-7) |
| Rebalance mensile | `strategy.py:105-112` (`_should_rebalance`) | mese/anno diverso |
| Una posizione alla volta | `strategy.py:92` `_open_position` | |
| `health_check` | `strategy.py:95-103` | len≥252, RV non vuota |
| Live build | `portfolio_scheduler.py:3058-3074` | `VRPStrategy(prices=bars_df)`, S2Config() defaults, no from_yaml (DV-9) |
| Hard-block enable S2 | `registry.py:231-236` | `raise ValueError` se S2.enabled |
| Portfolio NAV | `portfolio.py:97` | `cash + total_position_value` (solo equity) |
| Backtest entry | `backtest.py:27-154` (`run_s2_backtest_from_prices`) | WF 1260/252, 3 finestre |
| Backtest full | `backtest.py:257-285` (`run_s2_backtest_full`) | start 2007-01-01, universo S1 |
| Regime split (gate 4) | `backtest.py:187-213` (`_split_regime_returns`) | `fwd_21d` look-ahead (DV-11) |
| Stress extraction (gate 5) | `backtest.py:216-254` | COVID/Volmageddon/2022 hardcoded |
| Perturbation (gate 3) | `backtest.py:157-184` (`_run_perturbation`) | 5 config; gate 3 riporta "no data" |

## 2. Divergenze spec↔codice (richiamo, dettaglio in fasi 04/06/07)

| ID | Divergenza | Codice | Gravità |
|---|---|---|---|
| DV-1 | VRP gate = `IV−RV` (proxy vietata dalla teoria) | `signal.py:100-101` | BLOCCANTE (design) |
| DV-2 | Lato P = RV63 passata, non forecast `E^P` | `strategy.py:88` | BLOCCANTE |
| DV-3 | Strumento = long SPY equity, non short variance | `strategy.py:334-342` | BLOCCANTE |
| DV-4 | P&L backtest = SPY equity, non short-put (put decorativa) | `portfolio.py:97` + `strategy.py:158-174` | CRITICAL (invalida evidenza) |
| DV-5 | Sostituzione con proxy vietata dal PO-decision | `strategy.py` intero | BLOCCANTE (governance) |
| DV-6 | Perdita non finita; no max-loss 2% NAV, no margine stressato | nessun codice | BLOCCANTE (governance) |
| DV-7 | Reprice/SIGNAL_FLIP usano IV di entry (stale), non IV corrente | `strategy.py:171,220` | HIGH (logica exit) |
| DV-8 | Sentiment filter inerte (sentiment sempre None) | `strategy.py:257` | LOW (dead code coerente con teoria) |
| DV-9 | Dead config: `S2Config()` defaults, no from_yaml nel path live | `portfolio_scheduler.py:3074` | HIGH (latente, come S1 BUG-1) |
| DV-10 | `apply_regime_scale` (regime.py:44-62) definito ma **mai chiamato** | `strategy.py` non lo invoca | MED (dead code; il regime scale è applicato via `_target_spy_shares`, non sul qty put) |
| DV-11 | Regime split con `fwd_21d` look-ahead | `backtest.py:202-211` | CRITICAL (gate 4 non valido) |

## 3. Dettaglio DV-10 — `apply_regime_scale` mai chiamato

`regime.py:44-62` definisce `apply_regime_scale(signal, modulation)` che scala
`signal.quantity` di `floor(qty·scale)` e aggiorna il collaterale. È progettato per
applicare il regime al **numero di contratti put**. Ma nel path `__call__`
(strategy.py:188-348):
- il regime scale è applicato via `_target_spy_shares` (linea 290) al notionale
  equity, **non** via `apply_regime_scale` al qty put;
- `signal.quantity` (calcolato in `select_put` su `capital=100_000` fisso,
  signal.py:114) è **ignorato** nel sizing SPY (linea 290 usa `NAV`, non `quantity`).
- `apply_regime_scale` è importato (strategy.py:43) ma **0 call site** → dead code.

Conseguenza: la "regime modulation sul put" documentata (regime.py docstring) non
avviene; il regime scala solo l'esposizione equity. Coerente con DV-3/DV-4 (la put
è decorativa) ma diverge dallo spec del modulo regime.

## 4. Path live vs backtest

| Aspetto | Backtest | Live |
|---|---|---|
| Istanza | `VRPStrategy(prices, S2Config())` (backtest.py:61) | `VRPStrategy(prices=bars_df)` (scheduler:3074) — defaults identici |
| Config | `S2Config()` defaults ovunque | `S2Config()` defaults (no from_yaml) |
| Abilitazione | n/a (backtest script) | `enabled=false` + hard-block registry — **mai eseguito** |
| DataReplay/portfolio | `DataReplay(prices)` + `VirtualPortfolio` | n/a (S2 non attivo) |
| Sentiment | `None` (skippato) | non wiring documentato |

S2 è **morto in produzione** (enabled=false + hard-block): il codice esiste solo
per backtest. Nessun divario backtest↔live da validare perché il path live non
parte; la divergenza è che **il path live stesso è inesistente**.

---
**Stato fase:** 05_code_mapping = **done**. Prossimo cursore: `S2:06_implementation_audit`.