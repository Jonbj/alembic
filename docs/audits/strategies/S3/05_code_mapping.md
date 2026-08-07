# S3 — 05 Code Mapping (spec → codice)

**Strategia:** S3 `CrossSectionalMomentum` (Residual Momentum)
**Data:** 2026-08-04
**Fonti:** `src/strategies/s3/{strategy,signal,universe,backtest}.py`,
`src/strategies/registry.py`, `src/portfolio/` (grep).

Questa fase mappa ogni componente della specifica (fase 01) al codice effettivo
con `file:line` e indica dove il codice diverge dal design originale (#55) e
dalla letteratura canonica (fase 03). Le divergenze sono etichettate DV-N
(riportate da fase 01 §11 e 02 §2).

---

## 1. Config (S3Config)

| Componente spec | Codice | Note |
|---|---|---|
| `lookback=252` (12-0) | `strategy.py:27` | DV-1: design 12-1 (`log(P[t-21]/P[t-252])`). Codice: `P[t]/P[t-252]-1` (12-0, include mese corrente). |
| `beta_window=252` | `strategy.py:28` | rolling OLS beta + vol sizing su 252d. |
| `n_deciles=10` | `strategy.py:29` | bucket cross-sectionali. |
| `target_vol=0.10` | `strategy.py:30` | inverse-vol target. |
| `max_weight=0.20` | `strategy.py:31` | DV-5: design 0.10. |
| `long_decile=10` | `strategy.py:32` | top residuo. |
| `short_decile=1` | `strategy.py:33` | DV-3: design `None` (long-only). Codice default `1` → long-short. |
| `rebalance_frequency=MONTHLY` | `strategy.py:34` | |
| `from_yaml` | `strategy.py:36-53` | **DV-8 / DEAD CONFIG**: definito ma **0 call site** in `src/` (grep); nessun `config/s3*.yaml` (`ls config/`). Backtest usa `S3Config()` bare (`backtest.py:37`, `backtest.py:146`). Pattern identico a S1 BUG-1 / S2 BUG-D. |

## 2. Segnale — residual momentum

| Componente spec | Codice | Note |
|---|---|---|
| `compute_beta` (rolling OLS) | `signal.py:8-36` | `Cov(r_i,r_SPY).rolling(window)/Var(r_SPY).rolling(window)`, `window=252`. NaN se <window. |
| `compute_residual_momentum` | `signal.py:39-68` | `residual = (P_t/P_{t-252}-1) - beta·(SPY_t/SPY_{t-252}-1)`. **DV-1/DV-2**: 12-0 sia stock sia market momentum (design 12-1). |
| `momentum = prices/prices.shift(lookback)-1` | `signal.py:60` | 12-0, include il mese corrente (contaminato da short-term reversal, Jegadeesh 1990). |
| `market_momentum` | `signal.py:61` | SPY momentum 12-0 (design: 12-1). |
| `residual = stock_mom - beta·market_mom` | `signal.py:67` | broadcast corretto. **1-factor** (solo beta×SPY): non pulisce size/value/quality → può contenere factor momentum residuo (fase 03 §5). |

## 3. Ranking cross-sectionale e decili

| Componente spec | Codice | Note |
|---|---|---|
| `compute_cross_sectional_ranks` | `signal.py:71-108` | rank ascendente `method="average"`, `na_option="keep"`. |
| `decile = ceil(rank·n_deciles/n_valid)` | `signal.py:97` | `np.ceil(ranks.div(n_valid,axis="index")*n_deciles)`. |
| `valid_rows = residual.notna().any(axis=1)` (ranks) | `signal.py:87` | in `compute_cross_sectional_ranks`: keep date if ANY ticker valid. |
| **`valid_rows = residual.notna().all(axis=1)` (signal gen) | `signal.py:136` | **DV-7 / pannello bilanciato**: in `generate_s3_signals` la data è mantenuta iff TUTTI i ticker hanno residual non-NaN. Look-ahead nella selezione delle date: i future-listed nel pannello rimuovono le date precedenti (come S1 BUG-2). |

**Inconsistenza sottile**: `compute_cross_sectional_ranks` usa `any(axis=1)`
(`signal.py:87`) ma `generate_s3_signals` filtra con `all(axis=1)` prima di
chiamarla (`signal.py:136`). Il filtro `all` domina → pannello bilanciato.

## 4. Universo

| Componente spec | Codice | Note |
|---|---|---|
| `S3Universe.active_at(as_of)` | `universe.py:38-83` | filtro liquidità **PIT**: righe `<= as_of`; min 252d close non-NaN; close≥$5; ADV trailing 63g ≥$10M. **Causale**, corretto. |
| `load_s3_universe` | `universe.py:94-146` | tickers da `data/sp500_tickers.csv` (snapshot **corrente**, 57 righe). Market-cap filter **configurato non implementato** (review §2.2). |
| `run_s3_backtest_full` selection | `backtest.py:209-210` | `active = s3_universe.active_at(end)` con `end=today` → **DV-6**: 50 nomi più liquidi OGGI riusati su 2000-today → survivorship + look-ahead nella selezione universo. |
| `tickers = list(active[:50])` | `backtest.py:210` | cap 50 per tractability. |
| `prices_wide = s3_universe.close[all_tickers]` | `backtest.py:214` | usa i close pre-downloadati; `dropna(axis=1, how="all")`. |

## 5. Sizing

| Componente spec | Codice | Note |
|---|---|---|
| Precompute vol | `strategy.py:86-88` | `daily_rets.rolling(beta_window).std()·sqrt(252)` su full prices (causale rolling). |
| `compute_target_weights` | `strategy.py:92-139` | |
| Lookup PIT vol | `strategy.py:114-119` | `valid_vol_dates <= as_of` → sizing è PIT (fix `e15d5e7` 2026-06-19). |
| `raw_w = target_vol/vol` (long) | `strategy.py:128-129` | capped `max_weight=0.20`. |
| `raw_w = -min(target_vol/vol, max_weight)` (short) | `strategy.py:136-137` | DV-3: gamba short presente. |
| **Pesi NON normalizzati** | (assente) | **DV-4**: nessuna normalizzazione (somma≠1, ≠0). Design: inverse-vol 60d normalizzato. Gross exposure variabile, dipendente dal #nomi nel decile. |
| Fallback `raw_w = target_vol` se vol NaN/≤0 | `strategy.py:125-126, 133-134` | se vol mancante usa target_vol come peso (non `target_vol/vol`). |

## 6. Rebalance, entry/exit

| Componente spec | Codice | Note |
|---|---|---|
| `__call__` | `strategy.py:177-242` | rebalance mensile. |
| `_should_rebalance` | `strategy.py:153-167` | MONTHLY: cambio mese/anno. |
| `compute_target_weights(data_replay.prices_until(ts))` | `strategy.py:188` | `as_of = prices.index[-1]` (ultima ≤ ts). |
| NAV = cash + Σ market_value | `strategy.py:169-175` (`_nav`) | |
| Exit: chiude posizioni assenti dal target | `strategy.py:192-206` | SELL se long, BUY se short. |
| Entry/rebalance: `target_qty = NAV·w/price` | `strategy.py:213` | |
| `delta = target_qty - current_qty` | `strategy.py:216` | soglia `abs(delta) < 1e-4` skip (`strategy.py:218`). |
| Order placement | `strategy.py:221-240` | `Order.market_order`, BUY se delta>0, SELL se delta<0. |
| Istanza riusata tra finestre WF | (review §2.2) | `_last_rebalance` mutabile condiviso. |

## 7. Backtest e gate

| Componente spec | Codice | Note |
|---|---|---|
| `run_s3_backtest_from_prices` | `backtest.py:22-129` | WF + gate. |
| `S3Config()` bare | `backtest.py:37` | DV-8: nessun yaml. |
| `WalkForwardConfig(1260, 252)` | `backtest.py:38` | IS 1260d / OOS 252d. |
| OOS Sharpe | `backtest.py:62-67` | concatena window returns, `sharpe_ratio(periods=252)`. |
| `_run_perturbation` | `backtest.py:132-161` | perturbazioni lookback/beta_window (126/126, 378/252, 252/504). |
| `_split_regime_returns` | `backtest.py:164-177` | split high/low vol su rolling 63d. |
| Stress periods | `backtest.py:81-83` | `extract_historical_stress_periods`. |
| `milestone_c_pass` | `backtest.py:97` | `(0.0 <= oos_sharpe <= 1.0) and gate_report.overall_passed` — **soglia banale** (qualunque Sharpe ≥0 e ≤1 passa la prima condizione). |
| `run_s3_backtest_full` | `backtest.py:180-224` | download reali + backtest; `start=2000-01-01`, `end=today`. |

## 8. Integrazione runtime (N/A in produzione)

| Componente spec | Codice | Note |
|---|---|---|
| Registry | `registry.py:27-30` | `_SAFE_DEFAULTS` contiene **solo S1/S2/S4**. S3 assente. |
| Orchestrator live | grep `src/portfolio/` | **0 riferimenti S3**. `orchestrator.py` gestisce S1/S4; altri ID → pesi vuoti (review §2.2). |
| Lifecycle DB | (fase 01 §9) | nessuna riga S3 in `strategy_lifecycle`. |
| Config yaml | `ls config/` | nessun `s3*.yaml`. |

⇒ S3 è **offline-only**: codice di backtest, nessun path live, nessun contratto
di integrazione. Coerente con `mode=research` di `strategies.yaml`.

## 9. Mappa divergenze codice ↔ design (#55) — riepilogo

| ID | Divergenza | Codice (file:line) | Design |
|---|---|---|---|
| DV-1 | Formation return 12-0 | `signal.py:60` (`prices/prices.shift(252)-1`) | 12-1 (`log(P[t-21]/P[t-252])`) |
| DV-2 | Market correction 12-0 | `signal.py:61` | 12-1 |
| DV-3 | Long-short | `strategy.py:33` (`short_decile=1`), `strategy.py:131-137` | long-only (`short=None`) |
| DV-4 | Sizing non normalizzato | `strategy.py:121-139` (nessuna normalizzazione) | inverse-vol 60d normalizzato |
| DV-5 | Cap 20% | `strategy.py:31` | 10% |
| DV-6 | Universo survivor 50 | `backtest.py:209-210` | US large/mid PIT |
| DV-7 | Pannello bilanciato | `signal.py:136` (`notna().all(axis=1)`) | n/a (look-ahead date-selection) |
| DV-8 | Dead config | `strategy.py:36-53` (0 call site), `backtest.py:37` | yaml-driven |

## 10. Punti chiave per le fasi 06/07

- **DV-7 / pannello bilanciato** (`signal.py:136`) è il candidato bug di
  look-ahead più grave: la data è ammessa iff tutti i ticker (inclusi
  future-listed) hanno residual non-NaN. Identico a S1 BUG-2. Sarà confermato in
  fase 07 con repro.
- **DV-6 / survivorship** (`backtest.py:209-210`): `active_at(end)[:50]` con
  `end=today`. Non un "bug" (è una scelta di backtest) ma invalida il backtest.
- **DV-8 / dead config** (`strategy.py:36-53`): `from_yaml` mai chiamato, no
  yaml. Pattern cross-strategy (S1 BUG-1, S2 BUG-D). Sarà confermato con repro
  statico in fase 07.
- **`milestone_c_pass` soglia banale** (`backtest.py:97`): `0.0 <= oos_sharpe`
  ammette Sharpe=0. Non un bug, ma il gate non informa.
- **1-factor residual** (`signal.py:67`): non pulisce size/value/quality.
  Limitazione di design, non bug.

---
**Stato fase:** 05_code_mapping = **done**. Prossimo cursore: `S3:06_implementation_audit`.