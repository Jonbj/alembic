# S3 — 06 Implementation Audit

**Strategia:** S3 `CrossSectionalMomentum` (Residual Momentum)
**Data:** 2026-08-04
**Verdetto implementazione:** **INVALIDATO** — backtest non conclusivo a causa di
look-ahead (pannello bilanciato), survivorship, dead config, soglie banali;
**runtime morto** (zero trades, nessun path live).

---

## Asse 1 — Data timing (event-time vs bar-time)

**Verdetto: ACCETTABILE (causale).**

- I segnali sono precomputati su `prices` wide (`strategy.py:64-88`) con
  operazioni rolling **causali** (`pct_change`, `rolling(252).std`,
  `rolling().cov/var`) — nessuna aggregazione forward.
- `compute_residual_momentum` (`signal.py:60`) usa `prices.shift(lookback)`: la
  prima data utile è `t0+252`. Nessun look-ahead intrinseco nella formula.
- `__call__` consuma `data_replay.prices_until(ts)` (`strategy.py:188`): a ogni
  `ts` vede solo prezzi `≤ ts`. Causale.
- Limitazione: data **bar-time** (close giornaliero), non event-time; ma per
  momentum CS su close giornaliero è la convenzione canonica (JT 1993).

## Asse 2 — Look-ahead bias

**Verdetto: FAIL — pannello bilanciato (DV-7) + survivorship universe (DV-6).**

1. **Pannello bilanciato** (`signal.py:136` `valid_rows =
   residual.notna().all(axis=1)`): una data `t` è ammessa nel backtest iff TUTTI
   i ticker nel pannello (inclusi quelli listati successivamente) hanno residual
   non-NaN a `t`. Meccanismo:
   - `prices_wide` include ticker future-listed (es. listati nel 2010) perché
     `active_at(end)` seleziona i 50 sopravvissuti OGGI e `prices_wide` estrae
     le loro serie complete (`backtest.py:214`).
   - Per `t < 2010`, il ticker future-listed ha close=NaN → residual=NaN →
     `notna().all(axis=1)` è False → la data `t` è **droppata**.
   - Le date ammesse sono quindi determinate dai future-listed → **look-ahead
     nella selezione delle date**. Identico a S1 BUG-2.
   - Effetto: le finestre WF early sono droppate o skifate; il backtest misura un
   pannello che non era osservabile PIT.
2. **Survivorship universe** (`backtest.py:209-210` `active_at(end)[:50]` con
   `end=today`): i 50 sopravvissuti liquidi OGGI riusati su 2000-today. I
   delisted/dimessi non sono nel pannello → i rendimenti long sono
   meccanicamente inflati (survivorship bias classico).
3. `prices_wide.dropna(axis=1, how="all")` (`backtest.py:214`) droppa solo colonne
   interamente NaN, non risolve il problema.

## Asse 3 — Leakage

**Verdetto: OK sul sizing PIT; WARNING sul precompute full.**

- Sizing vol è PIT: `valid_vol_dates <= as_of` (`strategy.py:117-119`) — fix
  `e15d5e7` (2026-06-19) ha rimosso un look-ahead di sizing. Corretto.
- `compute_target_weights` lookup decile: `valid_dates <= as_of`
  (`strategy.py:101-104`) — PIT. Corretto.
- **Precompute full**: `_signals`, `_rank_wide`, `_vol_df` sono calcolati sul
  DataFrame **intero** al construction time (`strategy.py:64-88`). Per il backtest
  WF, la stessa istanza strategia è riusata tra finestre (review §2.2). I segnali
  sono rolling-causal, quindi il precompute non introduce look-ahead nei valori
  (una `rolling(252)` a data `t` usa solo `≤t`); MA il **pannello bilanciato**
  (DV-7) è calcolato sul full DataFrame → la selezione delle date ammissibili
  usa informazioni future (quali ticker saranno nel pannello). Questo è leakage
  di composizione, non di valore.

## Asse 4 — Survivorship bias

**Verdetto: FAIL.**

- `data/sp500_tickers.csv` è uno snapshot **corrente** (57 righe, `universe.py:128`)
  → solo sopravvissuti.
- `active_at(end)` con `end=today` (`backtest.py:209`) → 50 sopravvissuti liquidi
  OGGI.
- Nessun punto-in-time universe dinamico per il backtest: il filtro PIT
  (`active_at`) è corretto in sé, ma è applicato **una sola volta** alla data
  finale, non a ogni data di rebalance. Il design richiedeva un universo large/mid
  US liquido **PIT** (review §2.2: market-cap filter configurato non implementato).
- Effetto: backtest long-biased; il 0.148 è già inflato da survivorship e resta
  ~0 → indicatore negativo per la variante di codice.

## Asse 5 — Backtesting methodology

**Verdetto: DEBOLE — WF OK, ma costi/gate/riproducibilità carenti.**

- **Walk-forward**: `WalkForwardConfig(1260, 252)` (`backtest.py:38`), 21 finestre.
  IS/OOS split corretto. OOS Sharpe da concat di window returns (`backtest.py:62-67`).
- **Same-bar fills**: `Order.market_order` a `ts` con `price = market.price_of`
  (`strategy.py:210`) — fill allo stesso close del segnale. Backtest standard per
  momentum CS su close (decide al close t, esegue al close t; slippage non
  modellato). Accettabile ma ottimistico.
- **Costi non modellati**: nessuno slippage/commissione in `summary.json`
  (review §2.2). Il 0.148 è **pre-cost**. Patton-Weller 2020: costi momentum
  7.2-7.6%/anno → post-cost il 0.148 è quasi certamente negativo.
- **DSR / n_trials**: non presente. `_run_perturbation` (`backtest.py:132-161`)
  testa 3 perturbazioni di lookback/beta_window ma non corregge per multiple
  testing. `milestone_c_pass` (`backtest.py:97`) usa soglia `[0.0, 1.0]` banale.
- **Soglie gate banali**: gate 1/2 PASS con `min_sharpe=0.0` (fase 01 §8) →
  qualunque Sharpe ≥ 0 passa. Gate 3/5 FAIL. Il "PASS" di gate 1/2 non informa.
- **Riproducibilità**: file `summary.json` datati 2026-06-01, ignorati da Git,
  nessun manifest dati/versione (review §2.2) → **non riproducibile**.

## Asse 6 — Signal generation

**Verdetto: FORMULA CORRETTA, PARAMETRI NON CANONICI.**

- `compute_residual_momentum` (`signal.py:39-68`) implementa correttamente
  `stock_mom - beta·market_mom`. Matematicamente fedele al residual momentum.
- **DV-1/DV-2**: 12-0 (include mese corrente) vs canonico 12-1 (JT 1993, Carhart
  1997, Asness 2013). Il 12-0 contamina il segnale con la short-term reversal
  (Jegadeesh 1990): il rendimento dell'ultimo mese è dominato dalla reversal,
  non dal momentum. Wiest 2022 (fase 03) conferma la convenzione 12-1 è standard
  proprio per isolare momentum da reversal.
- **1-factor** (`signal.py:67`): sottrae solo beta×SPY, non FF3. La variante
  FF3-residual (Gutman 2023) è più pulita; S3 può contenere factor momentum
  residuo su size/value/quality.
- `compute_beta` rolling OLS (`signal.py:8-36`) corretto; NaN < window.

## Asse 7 — Portfolio allocation (sleeve scaling, caps)

**Verdetto: NON NORMALIZZATO (DV-4) + NO SLEEVE.**

- `compute_target_weights` (`strategy.py:92-139`) produce pesi **non
  normalizzati**: la somma non è vincolata a 1 (long) né a 0 (long-short).
  Design: inverse-vol normalizzato.
- Gross exposure dipendente dal #nomi nel decile (~5 su 50) → fino a 5×0.20=100%
  per gamba. Non è il sizing del design.
- **Nessuno sleeve scaling**: S3 non è in registry (`registry.py:27-30` solo
  S1/S2/S4) → nessun `allocation_pct` applicato. Il backtest è standalone.
- Cap `max_weight=0.20` (DV-5, design 0.10).
- Fallback `raw_w = target_vol` se vol NaN/≤0 (`strategy.py:125-126, 133-134`):
  se vol mancante, peso = `target_vol` (0.10) non `target_vol/vol`. Comportamento
  non documentato.

## Asse 8 — Risk controls (stops, drawdown, kill-switch)

**Verdetto: NESSUNO.**

- S3 non ha stop-loss, drawdown cap, né kill-switch nel codice
  (`strategy.py` non implementa alcun risk overlay).
- Exit solo per assenza dal target decile (`strategy.py:192-206`): rebalance
  mensile, nessun stop intra-mese.
- Coerente con `mode=research` (offline), ma se mai promossa mancano tutti i
  risk overlay che S1/S4 hanno.

## Asse 9 — Execution (order placement path)

**Verdetto: BACKTEST-ONLY.**

- `Order.market_order` (`strategy.py:199-205, 222-239`) genera ordini nel
  `VirtualPortfolio` del backtest. Nessun path live.
- S3 non è in registry → nessun `portfolio-cycle`/`run-execution` lo invoca.
- `src/portfolio/`: 0 riferimenti S3 (grep). Nessun wiring broker.

## Asse 10 — Accounting (P&L, slippage, costs)

**Verdetto: DEBOLE.**

- NAV = cash + Σ market_value (`strategy.py:169-175`). Mark-to-market corretto
  nel backtest.
- Nessun slippage/commissione modellato (asse 5). `cost_bps`/`cost_usd` in
  `trades` (asse 12) non sono popolati perché S3 non ha trades.
- P&L di backtest è gross-of-cost.

## Asse 11 — Paper-trading behavior

**Verdetto: N/A.**

- S3 non ha path paper-trading: non è in registry, non ha lifecycle row
  (asse 12), nessun worker lo esegue. `mode=research` in `strategies.yaml`.
- La review interna (2026-07-20) raccomanda esplicitamente **non** paper trading
  né broker wiring; solo POC A/B offline.

## Asse 12 — Runtime behavior (live workers vs codice)

**Verdetto: MORTO — zero attività runtime.**

Verifiche DB read-only (2026-08-04):

```
trades per stop_strategy:
  (blank) | 288
  S1      | 75
  S4      | 64
  (nessuna riga S3)

strategy_lifecycle:
  S1 | supervised_paper | approved
  S2 | disabled         | not approved
  S4 | paper            | approved
  S7 | research         | not approved
  (nessuna riga S3)
```

- **Zero trades S3** in `trades.stop_strategy` (vs S1=75, S4=64).
- **Nessuna riga S3** in `strategy_lifecycle` (S7 ce l'ha in mode research; S3 no).
- S3 non è in `_SAFE_DEFAULTS` (`registry.py:27-30`) né in `src/portfolio/`.
- ⇒ S3 è **offline-only**: il codice esiste come backtest; nessun worker, nessun
  ciclo, nessun ordine, nessuna riga DB. Coerente con `mode=research`.

## Sintesi assi

| Asse | Verdetto | Note |
|---|---|---|
| 1 Data timing | OK | rolling causale, prices_until PIT |
| 2 Look-ahead | **FAIL** | pannello bilanciato DV-7 + survivorship DV-6 |
| 3 Leakage | OK sizing / WARNING precompute | pannello bilanciato = leakage di composizione |
| 4 Survivorship | **FAIL** | snapshot corrente + active_at(end) |
| 5 Backtest method | DEBOLE | WF OK, no costi, no DSR, soglie banali, non riproducibile |
| 6 Signal gen | FORMULA OK, PARAMETRI NON CANONICI | 12-0 vs 12-1, 1-factor |
| 7 Allocation | NON NORMALIZZATO | DV-4, no sleeve |
| 8 Risk controls | NESSUNO | no stop/DD/kill-switch |
| 9 Execution | BACKTEST-ONLY | no path live |
| 10 Accounting | DEBOLE | NAV MTM ok, no costi |
| 11 Paper trading | N/A | mode=research |
| 12 Runtime | **MORTO** | zero trades, zero lifecycle, zero registry |

**Convergenza**: l'implementazione S3 è un backtest di ricerca invalidato da
look-ahead (pannello bilanciato) e survivorship, con costi non modellati e
soglie banali, su una variante (12-0 long-short non normalizzata) diversa dal
design e dalla letteratura. A runtime è completamente morta. Il backtest 0.148
non è conclusivo per nessuna delle due domande (codice o fenomeno).

---
**Stato fase:** 06_implementation_audit = **done**. Prossimo cursore: `S3:07_bugs`.