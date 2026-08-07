# S1 — 06 Audit di implementazione

**Strategia:** S1 Multi-Lookback Relative Momentum
**Data:** 2026-08-04
**Metodo:** lettura sorgente (`src/strategies/s1/`, `src/backtest/engine/`, `src/workers/`) + evidenza runtime DB (read-only). Verdetto esplicito per asse.

## 6.1 Data timing

- **Segnale**: costruito da prezzi di chiusura ≤ `as_of` (`signal.py:78` `prices.shift(lb)`, `signal.py:70-71` rolling vol backward). Nessun look-ahead nel **valore** del segnale. ✅
- **Fill**: `BacktestConfig.fill_at_next_open=True` (`orchestrator.py:95`) → ordini generati al bar `t` riempiti all'**open del bar t+1** (`orchestrator.py:214-231`). `WalkForwardRunner` usa i default → T+1 (`runner.py:60-62`). ✅
- **Verdetto asse**: `OK` sul timing di fill (T+1). La nota di demotion "same-bar fill (t+0)" in `config/strategies.yaml` è **STALE** — il fix P1-BACKTEST-TPLUS1-FILL è stato applicato dopo la demotion del 2026-06-19, ma la nota non è stata aggiornata.

## 6.2 Look-ahead bias

- **(a) Filtro inclusione ticker full-window** — `signal.py:92-116`: `coverage_ok = prices.notna().sum(axis=0) >= 0.75*len(prices)` calcolato su **tutta** la finestra passata al backtest. Nel backtest `prices` = storico 1993→oggi ⇒ la copertura di un ticker usa informazione futura. **Ammesso nel docstring** `signal.py:54-57`. ❌ **CONFIRMED look-ahead** (per 07).
- **(b) Pannello bilanciato** — `signal.py:118-120` `valid_rows = signal_raw.notna().all(axis=1)`: droppa ogni data in cui un ticker incluso manca. Induce bias di pannello (date droppate retroattivamente una volta noto l'insieme incluso). ⚠️ sospetto, da confermare in 07.
- **Verdetto asse**: `FAIL` — look-ahead nella selezione universo.

## 6.3 Leakage

- Il segnale di un titolo usa solo la sua storia prezzi + la cross-section alla data `t` (z-score per-data, `signal.py:122-132`). Nessun leakage cross-sectionale futuro nel valore. ✅
- Il leakage è confinato alla **selezione dell'universo** (§6.2), non al calcolo del segnale. **Verdetto**: `OK` sul segnale, `FAIL` sull'universo.

## 6.4 Survivorship bias

- `run_s1_backtest_full` (`backtest.py:207-212`): `universe = load_universe("s1")` (universo **odierno**) + `loader.get_aligned_prices(universe, start=date(1993,1,1), end=date.today())`. Prezzi 1993→oggi sull'universo attuale ⇒ **solo titoli sopravvissuti**; nessun delisted. ❌ **CONFIRMED survivorship** (project-acknowledged in `config/strategies.yaml` nota P0-01; locus: `backtest.py:207-212` + `src/backtest/data/universe.py::load_universe`).
- **Verdetto asse**: `FAIL`.

## 6.5 Metodologia backtest

- Walk-forward 1260 IS / 252 OOS (`backtest.py:40`) ✅
- T+1 fill ✅ (§6.1)
- Cost model realistico `RealisticCostModel(config/cost_model.yaml)` (`orchestrator.py:171-172`) — spread, commission, impact adv-based ✅ (la nota "zero-cost" è **stale**)
- Manifest riproducibilità: `BacktestManifest` con data_hash, seed, code_version, config_hash (`orchestrator.py:58-86`) ✅ (P0-10)
- **DSR n_trials**: perturbazione solo 3 configurazioni (`backtest.py:155-159`). La nota "DSR n_trials=1" è in parte stale (3>1), ma 3 è ancora piccolo per un Deflated Sharpe robusto. ⚠️
- **Regime split circolare** — `_split_regime_returns` (`backtest.py:180-193`) definisce regimi high/low-vol usando `rolling_vol` calcolato **sugli stessi OOS returns** che valuta → hindsight intra-OOS. ❌ conferma la nota "circular stress/regime".
- **Verdetto asse**: `PARTIAL` — fondamenta migliorate (T+1, costi, manifest), ma survivorship + look-ahead universo + regime circolare + DSR n_trials piccolo restano.

## 6.6 Generazione segnale (live vs backtest)

- **Backtest**: `strategy.__call__` (`strategy.py:204-268`) genera `Order` diretti (market orders BUY/SELL).
- **Live**: il path portfolio usa `compute_target_weights` (`strategy.py:87-153`) → restituisce pesi → `portfolio_scheduler` scala per `allocation_pct=0.50`, applica cap, regime scale, stop, → invia ad Alpaca.
- **Divergenza path**: due codepath distinte. Il backtest non replica il sleeve-scaling, i cap, regime_mult, stop, né l'accounting di costo del path live. ⚠️ → il backtest **non è una simulazione fedele del live** anche a parità di segnale.
- **Verdetto asse**: `DRIFT` — backtest e live divergono strutturalmente.

## 6.7 Allocazione portafoglio

- Sleeve S1 = 0.50 (`config/strategies.yaml`); pesi sleeve-local normalizzati a ≤1.0 (`strategy.py:150-152`); orchestrator scala ×0.50.
- `max_position_pct=0.10`, `max_portfolio_exposure=0.50` (`config/trading.yaml`).
- Sizing inverso-vol cap `max_weight=0.20` (`sizing.py:31`).
- **Verdetto asse**: `OK` (meccanica coerente; il fatto che il sizing non scales con signal strength è una scelta di design, già notata in 05 D2).

## 6.8 Risk controls

- `risk.stop_loss=0.0` → protective stop **disabilitato** (paper); `stop_loss_mode=fixed`; `stop_shadow_enabled=true` (`config/trading.yaml:182-194`).
- `stop_strategy_params S1 {k:3.5, floor:0.06, cap:0.12}` (`portfolio_scheduler.py:1065`) — usato per **shadow** d_hard, non enforce.
- `killswitch_recovery.enabled=true`; drawdown cap `portfolio_drawdown=0.05`.
- **Runtime (evidenza DB)**: `stop_shadow_log` mostra **15 `d_hard_breached` su NOK/S1 nelle 24h**, adverse 20.86–22.99% (audit 2026-08-03). Nessun floor enforce → le posizioni S1 corrono oltre il d_hard (12-20%) senza intervento. ⚠️
- **Verdetto asse**: `AMBER` — rail di risk disabilitati per decisione paper, ma lo shadow log mostra proprio la condizione che `trading.yaml` dice should trigger il wire di d_hard ("if any position rides past -15/20%").

## 6.9 Esecuzione

- Live: `portfolio_scheduler` portfolio-cycle → Alpaca SDK paper (`TradingClient`/`MarketOrderRequest`). Nessun `AlpacaBroker` class (per `CLAUDE.md`).
- Backtest: `BacktestOrchestrator` + `RealisticCostModel` → `VirtualPortfolio`.
- Nessun ordine reale (audit read-only; `GLOBAL_LIVE_PROMOTION_ENABLED=False`).
- **Verdetto asse**: `OK` (path noto; non eseguito dall'audit).

## 6.10 Accounting

- Tabella `trades`: `gross_pnl`, `slippage_est`, `net_pnl`, `cost_bps`, `cost_usd`, `spread_cost_bps`, `impact_cost_bps`, `regulatory_cost_usd` — accounting di costo dettagliato. ✅
- **Verdetto asse**: `OK` (struttura completa; qualità dei valori da spot-checkare in 07).

## 6.11 Paper-trading behavior

- S1 `mode=supervised_paper`, `approved=true` (lifecycle DB), ma `GLOBAL_LIVE_PROMOTION_ENABLED=False` ⇒ paper observation.
- `promotion_blocked` implicito; re-promotion gated (P0-05/06/07…).
- **Verdetto asse**: `OK` — governance rispettata; S1 non va live.

## 6.12 Runtime behavior (cosa fa davvero il sistema live)

Evidenza DB (read-only, ultimo 7g):
- `portfolio_cycles` gira `[S1, S4]` ogni ciclo (~15 min). S1 è attivo.
- **Trades S1 ultimi 7g: 15 trade, avg net_pnl −\$11.45, sum −\$68.71** (vs S4: 20 trade, +\$145.40). S1 sta **perdendo** nel paper recente.
- S1 entry recenti su titoli momentum (es. ARM score 0.0054 — z-score appena sopra 0, conferma gate binario con strength trascurabile).
- **Verdetto asse**: `AMBER` — S1 attivo e in perdita nel paper, coerente con verdetto `DECAYED + LIKELY_BETA` (fase 04). Le perdite sono piccole (paper, sizing contenuto) ma la direzione è negativa.

## 6.13 Sintesi per asse

| Asse | Verdetto |
|---|---|
| Data timing / fill | ✅ OK (T+1; nota stale) |
| Look-ahead bias | ❌ FAIL (filtro universo full-window) |
| Leakage | ⚠️ OK segnale / FAIL universo |
| Survivorship | ❌ FAIL (universo odierno, 1993→oggi) |
| Metodologia backtest | ⚠️ PARTIAL (costi/T+1/manifest ok; regime circolare, DSR n_trials piccolo) |
| Segnale live vs backtest | ⚠️ DRIFT (due codepath) |
| Allocazione | ✅ OK |
| Risk controls | ⚠️ AMBER (stop off; d_hard shadow breach 15× su NOK) |
| Esecuzione | ✅ OK (read-only) |
| Accounting | ✅ OK |
| Paper-trading | ✅ OK |
| Runtime | ⚠️ AMBER (S1 in perdita 7g, −\$68.71) |

## 6.14 Note stale di demotion (importante per governance)

`config/strategies.yaml` (S1) elenca come motivi di demotion: same-bar t+0, zero-cost, walk-forward decorativo, DSR n_trials=1. L'audit trova che **t+0 e zero-cost sono stati fixati** (P1-BACKTEST-TPLUS1-FILL, P1-COST-MODEL-REALISM, manifest P0-10) ma la nota **non aggiornata**. I motivi **ancora validi** sono: survivorship, look-ahead filtro universo, regime circolare, DSR n_trials piccolo, divergenza backtest↔live. ⇒ La demotion resta giustificata, ma per **motivi in parte diversi** da quelli documentati. Aggiornare la nota è un finding (non un'azione — fuori audit read-only).

---
**Stato fase:** 06_implementation_audit = **done**. Prossimo cursore: `S1:07_bugs`.