# S2 — 01 Specificazione funzionale e matematica

**Strategia:** S2 `VRPStrategy` (Volatility Risk Premium)
**Data:** 2026-08-04
**Fonti:** `src/strategies/s2/{strategy,config,signal,regime,event_filter,exit,backtest}.py`, `config/strategies.yaml`, `docs/strategies/s2-vrp-theory.md`, `reports/s2_backtest/summary.json`
**Stato (lifecycle DB):** `mode=disabled`, `approved=false`, `gate_report_id=NULL`
**Stato (yaml):** `enabled=false`, `allocation_pct=0.00`, `mode=research`
**Registry safety:** `_validate_allocations` (registry.py:231-236) **raise ValueError se S2 è enabled** — "OOS Sharpe -0.55, all gates failed".

---

## 0. Avvertenza cruciale: tre oggetti distinti

S2 esiste in **tre formulazioni tra loro non equivalenti**, che vanno tenute separate:

1. **Teoria approvata (PO 2026-07-15)** — `docs/strategies/s2-vrp-theory.md` §15. Il VRP è
   `E_t^Q[QV(t,T)] − E_t^P[QV(t,T)]` (seller-sign, varianza, orizzonte 30g calendario).
   Strumento teoricamente più puro = variance swap / replica model-free di indice;
   short put = esposizione *mista*; **proxy azionaria senza derivati NON è VRP** senza
   identificazione empirica separata. Classificazione = alternative-beta assicurativa,
   **non alpha**. PO-decision (§19): perimetro investibile limitato a strumenti
   listed/cleared via IBKR con perdita finita per costruzione, max loss 2% NAV, margine
   stressato ≤50% della sleeve; **"nessuna sostituzione con proxy economicamente diverse"**
   (NO-GO se nessuno strumento soddisfa purezza/liquidità/perdita-limitata).
2. **Specificazione intesa (docstring moduli)** — "short-put selling con regime
   modulation e event filter": vende put cash-secured su SPY target-delta −0.20, DTE
   30-45, sizing `max_collateral_pct=20%` di NAV, regime scale, exit su
   profit-target/stop/time/signal-flip/expiry.
3. **Implementazione effettiva nel backtest** — il motore backtest gestisce **solo
   posizioni equity**; la short put è **modellata come posizione SPY-equivalent**
   (`shares = NAV · max_collateral_pct · regime_scale / spy_price`). Il segnale put
   (strike, delta, premium) è **tracciato internamente** per decidere le uscite e per
   P&L contabile interno, ma **non entra nel NAV del portafoglio** (vedi §6).

Questa fase 01 ricostruisce l'**implementazione effettiva** (oggetto 3), annotando
le divergenze con teoria (oggetto 1) e docstring (oggetto 2); le divergenze sono
analizzate nelle fasi 04 (alpha) e 05 (code mapping).

---

## 1. Universo, dati, frequenza

- **Underlying:** SPY (hardcoded `_UNDERLYING = "SPY"`, strategy.py:49).
- **Prezzo:** dal `DataReplay` / `MarketSnapshot` nel path backtest; fallback al
  DataFrame prezzi passato in ctor.
- **Realized vol:** `spy_close.pct_change().rolling(63).std() * sqrt(252)`
  (strategy.py:88). **63-giorni rolling, lookback passivo** — è RV ex post, NON una
  forecast `E^P[QV]` (divergenza con la teoria §3/§6).
- **Opzioni:** catena sintetica via `OptionChainDataLoader.generate_chain("SPY", as_of,
  expiry, underlying_price)` (signal.py:80). Le scadenze sono generate da
  `_generate_expiries(as_of, num_expiries=5)` e filtrate a `min_dte ≤ DTE ≤ max_dte`
  (30–45). Greci (delta, IV, mid, OI, volume) sono **sintetici** forniti dal loader,
  non di mercato.
- **Rebalance:** mensile (`_should_rebalance`: mese o anno diverso dall'ultimo,
  strategy.py:105-112). Una sola posizione short-put alla volta.
- **Backtest range:** 2007-01-01 → oggi, universo S1 (che include SPY),
  `loader.get_aligned_prices` (backtest.py:275). Walk-forward 1260g IS / 252g OOS
  → 3 finestre sul campione disponibile.

## 2. Regime modulation (entry gate)

Regime derivato **solo dalla RV realizzata** `_get_realized_vol_at(ts)`
(strategy.py:114-125):

| Regime | Condizione (RV ann.) | `position_scale` |
|---|---|---|
| `bull` | RV < 0.12 | 1.00 |
| `sideways` | 0.12 ≤ RV < 0.20 | 0.75 |
| `bear` | 0.20 ≤ RV < 0.35 | 0.25 |
| `high_vol` | RV ≥ 0.35 | 0.00 (blocco entry) |

`modulate_by_regime` (regime.py:31-41) restituisce `position_scale = regime_scales[regime]`.
Se `position_scale ≤ 0` → **nessuna entrata** (strategy.py:252-254).

## 3. Event filter (entry gate)

`check_event_filter(as_of, spy_sentiment, config)` (event_filter.py:74-103). Blocca
entry se `event_filter_enabled` (default True) e almeno una delle:

- **Sentiment SPY** `< sentiment_block_threshold` (= −0.5). Nel backtest
  `spy_sentiment = None` (strategy.py:257) → **controllo sentiment sempre saltato**;
  nel path live non è wiring documentato (vedi §7).
- **FOMC proximity:** `as_of` entro `pre_event_block_days` (=1) di un FOMC
  approssimato come **3° mercoledì** di mesi in `{1,3,5,6,7,9,10,12}`.
- **NFP proximity:** entro 1 giorno del **primo venerdì** del mese.

Le date macro sono **approssimate deterministiche** (no calendario reale).

## 4. Segnale di entrata: `select_put`

`select_put(as_of, capital, config, underlying_price, realized_vol)` (signal.py:44-138):

1. Genera 5 scadenze, mantiene quelle con `min_dte ≤ DTE ≤ max_dte` (30–45).
2. Per ciascuna, catena sintetica SPY; concatena. Filtra `right == "P"`.
3. **Filtro delta:** `target_delta ± delta_tolerance` = −0.20 ± 0.05 → delta in [−0.25, −0.15].
4. **Filtro liquidità:** `open_interest ≥ 100` e `volume ≥ 10` (su catena sintetica).
5. **Filtro VRP:** `implied_vol − realized_vol ≥ vrp_entry_threshold` con
   threshold = **0.0** → entra quando `IV ≥ RV` (≥, non >). **Attivato solo se
   `realized_vol is not None`**; nel path backtest `realized_vol` è passato, quindi attivo.
6. Seleziona il contratto con **delta più vicino** a `target_delta` (`_delta_dist` min).
7. **Sizing opzioni:** `quantity = floor(capital · max_collateral_pct / (strike · 100))`.
   Ritorna `None` se `quantity < 1`.

Se `select_put` ritorna `None`, la strategia **entra comunque** in posizione SPY
(strategy.py:273-277: "Even without a put signal, take the SPY position for VRP
exposure") creando un `PutSignal` sintetico (strike = 0.95·price, delta −0.20,
mid = 0.02·price, expiry = as_of+30g).

## 5. Sizing della posizione SPY-equivalent

`_target_spy_shares` (strategy.py:176-186):

```
target_notional = NAV · max_collateral_pct · regime_scale
target_shares   = target_notional / spy_price
```

con `max_collateral_pct = 0.20` e `regime_scale ∈ {1.0, 0.75, 0.25, 0.0}`.
NAV stimato = `portfolio.cash + |existing_SPY_qty| · spy_price` (strategy.py:283-288).
Ordine: `BUY max(0, target_shares − current_qty)` SPY (strategy.py:330-342).
**Il sizing non dipende dal delta del put selezionato né dal premio**: è un'esposizione
equity fissa al 20%·scale del NAV, indipendente dal segnale VRP.

## 6. Exit logic (valutata in priorità)

`evaluate_exit` (exit.py:48-105), in ordine:

1. **EXPIRY** — `DTE ≤ force_close_dte` (=2) → chiusura forzata (evita assignment).
2. **STOP_LOSS** — `pnl < −stop_loss_multiplier · initial_premium` (=2×) **oppure**
   `(entry_price − current_price)/entry_price > underlying_stop_loss_pct` (=0.05,
   underlying giù >5%).
3. **TARGET_PROFIT** — `(entry_mid − current_mid)/entry_mid ≥ profit_target_pct` (=0.50).
4. **TIME_DECAY** — `DTE < min_dte_exit` (=7).
5. **SIGNAL_FLIP** — `implied_vol − realized_vol < 0`.

Dove:
- `pnl = (signal.mid − current_mid) · quantity · 100` (exit.py:39-45), short-put
  P&L contabile.
- `current_mid = _reprice_put(ts, signal, spy_price)`: **Black-Scholes** con
  `S=spy_price`, `K=signal.strike`, `T=dte/365`, **`r=0.05` fisso**,
  **`sigma=signal.implied_vol` (IV di entry, non IV corrente)** (strategy.py:158-174).
- `implied_vol` passato a `evaluate_exit` è `pos.signal.implied_vol` (entry IV,
  strategy.py:220) → **SIGNAL_FLIP confronta IV(entry) − RV(corrente) < 0**, non
  IV(corrente) − RV(corrente).

All'uscita: `SELL` tutte le quote SPY detenute (strategy.py:228-238) e reset
`_open_position=None`. **L'`ExitSignal.pnl` (P&L short-put) viene solo loggato
(`log.debug`), non scritto nel portafoglio.**

### 6.1 P&L misurato dal backtest ≠ P&L short-put

`VirtualPortfolio.total_nav = cash + total_position_value` (portfolio.py:97) —
**solo posizioni equity**. Il P&L della short-put (`compute_pnl`) è calcolato ma
**non alimonta il NAV**. Ne consegue che:

- L'`oos_sharpe` di `summary.json` (−0.613) è calcolato sui rendimenti di NAV di
  **una posizione long-SPY mensile gate-da-regime**, **non** sul P&L short-put.
- Il segnale put (strike/delta/premium) è **decorativo** ai fini del P&L backtest:
  serve solo a generare gli eventi di uscita (profit-target/stop/time/signal-flip),
  che si traducono in `SELL` SPY → chiusura della posizione equity.

Questo è il heart della divergenza spec↔implementazione (oggetto 1 vs 3 di §0).

## 7. Path live (portfolio_scheduler)

`_build_strategy_instance` (portfolio_scheduler.py:3056-3074):
```python
if sid == "S2":
    if len(bars_df) < 63: skip
    return VRPStrategy(prices=bars_df)   # S2Config() defaults, NO from_yaml
```
- **`S2Config()` defaults**, come S1: nessun `from_yaml` chiamato nel path live
  (pattern dead-config, vedi S1 BUG-1). `config/strategies.yaml` è la sola fonte
  per `enabled`/`allocation_pct`/`mode`, non per i parametri di strategia.
- S2 è `enabled=false` nel registry → `_build_strategy_instance` **non viene mai
  chiamato** nel path live (le guardie del registry bloccano). Il codice S2 è
  **morto in produzione**; esiste solo per backtest.
- Sentiment SPY (`event_filter`): non risulta wiring dal DB a `check_event_filter`
  nel path live; il filtro sentiment è inerte ovunque.

## 8. Config effettivo (S2Config defaults)

| Parametro | Default | Ruolo |
|---|---|---|
| `target_delta` | −0.20 | delta put target |
| `delta_tolerance` | 0.05 | banda [−0.25, −0.15] |
| `min_dte` / `max_dte` | 30 / 45 | finestra scadenza |
| `min_open_interest` | 100 | filtro liquidità (sintetico) |
| `min_volume` | 10 | filtro liquidità (sintetico) |
| `max_collateral_pct` | 0.20 | notionale equity = 20% NAV · scale |
| `vrp_entry_threshold` | 0.0 | entra se IV ≥ RV |
| `profit_target_pct` | 0.50 | exit target (50% premio) |
| `stop_loss_multiplier` | 2.0 | exit stop (loss > 2× premio) |
| `underlying_stop_loss_pct` | 0.05 | exit stop (underlying giù >5%) |
| `min_dte_exit` | 7 | exit time-decay |
| `force_close_dte` | 2 | exit expiry forzata |
| `regime_scales` | bull 1.0 / sideways 0.75 / bear 0.25 / high_vol 0.0 | gate regime |
| `sentiment_block_threshold` | −0.5 | (inerte: sentiment sempre None) |
| `pre_event_block_days` | 1 | blocco pre FOMC/NFP |
| `event_filter_enabled` | True | gate macro eventi |

## 9. Pseudocodice completo (implementazione effettiva)

```
state: _open_position ∈ {None, OpenPosition(signal, entry_date, entry_price, entry_mid, qty, delta)}
       _last_rebalance ∈ {None, datetime}

on each ts:
  spy_price    = SPY price at ts
  realized_vol = RV63 at ts (63d rolling std * sqrt252)

  # --- EXIT ---
  if _open_position != None:
    current_mid = BS_put(spy_price, signal.strike, dte/365, r=0.05, sigma=signal.implied_vol)  # IV=entry
    exit = evaluate_exit(signal, spy_price, today, current_mid,
                        implied_vol=signal.implied_vol, realized_vol=realized_vol,
                        entry_price=signal.entry_price)
    if exit != None:
      SELL all current SPY shares
      _open_position = None; _last_rebalance = ts
      return            # re-enter next month

  # --- ENTRY ---
  if _open_position == None and _should_rebalance(ts):
    _last_rebalance = ts
    regime = regime_from_RV(realized_vol)               # bull/sideways/bear/high_vol
    scale  = regime_scales[regime]
    if scale <= 0: return                                # high_vol blocks
    ef = check_event_filter(today, spy_sentiment=None)  # sentiment check skipped
    if not ef.allowed: return                            # FOMC/NFP proximity only
    signal = select_put(today, capital=100k, underlying_price=spy_price, realized_vol)
            # delta -0.20±0.05, DTE 30-45, OI>=100, vol>=10, IV-RV>=0; else synthetic
    nav   = cash + |SPY_qty|·spy_price
    shares = nav · 0.20 · scale / spy_price
    if shares < 1: return
    _open_position = OpenPosition(signal or synthetic, today, spy_price, signal.mid, qty, delta)
    BUY max(0, shares − current_SPY_qty) SPY
```

## 10. Risultati backtest (reports/s2_backtest/summary.json)

- **OOS Sharpe = −0.613**; `milestone_d_pass = false` (gate: OOS Sharpe ≥ 0.5).
- Walk-forward: 3 finestre, Sharpe [−2.163, 0.379, 0.088], mean −0.565, positive
  fraction 0.667.
- Gate 1 (significance) FAIL: Sharpe −0.505, p=0.0, DSR=0.0.
- Gate 2 (walk-forward) FAIL: OOS Sharpe −0.613 < 0.3.
- Gate 3 (robustness) FAIL: "no perturbed sharpe data provided".
- Gate 4 (regime) FAIL: solo 2 regimi su 4 con Sharpe > 0 (high_vol 0.218,
  low_vol −1.78, bull 0.009, bear −0.874).
- Gate 5 (stress) PASS: 2/2 periodi (worst_drawdown, vix_2018) — **ma con
  rendimenti cumulati ~0 e DD ~0**: stress passato trivialmente perché la
  posizione era quasi nulla in quei periodi, non per resilienza.

## 11. Divergenze spec→teoria rilevate (per fasi 04/05)

| ID | Divergenza |
|---|---|
| DV-1 | **VRP definito come IV−RV** (signal.py:101, threshold 0.0) — la teoria (§3/§6, M01) vieta `IV−RV` come *definizione* del VRP e lo declassa a proxy ex post. Qui è il gate di entrata. |
| DV-2 | **Lato P = RV63 rolling** (passato, non forecast). La teoria richiede `E^P[QV]` ex ante; RV passata è esplicitamente "non sostituisce l'aspettativa" (§3 tabella). |
| DV-3 | **Posizione = long SPY equity**, non short variance/put. La teoria (§7, M05) classifica put-writing come "esposizione mista" e proxy equity come "non può essere chiamata VRP". |
| DV-4 | **P&L backtest = SPY equity, non short-put** (§6.1). Il segnale put è decorativo per il NAV. L'OOS Sharpe −0.613 misura long-SPY regime-gated, non VRP. |
| DV-5 | **Sostituzione con proxy economicamente diversa** — il PO-decision (§19) vieta esplicitamente: "Se nessuno strumento soddisfa purezza/liquidità/perdita-limitata → NO-GO, nessuna sostituzione con proxy economicamente diverse". L'implementazione è la sostituzione vietata. |
| DV-6 | **Perdita non finita per costruzione** — long SPY equity ha perdita non limitata al collaterale; niente max-loss 2% NAV, niente margine stressato ≤50% sleeve (§19). |
| DV-7 | **Reprice put con IV di entry** (strategy.py:171) e **SIGNAL_FLIP con IV(entry)−RV(corrente)** (strategy.py:220) — il flip dovrebbe usare IV corrente, non stale. |
| DV-8 | **Sentiment filter inerte** (sentiment sempre None) — la teoria (§19) esclude comunque LLM/sentiment dal VRP overlay, quindi l'inertie è coerente con la teoria ma il parametro è dead code. |
| DV-9 | **Gate 3 robustness non eseguito** nel summary ("no perturbed sharpe data provided") nonostante `run_robustness=True` e `_run_perturbation` definito — probabilmente `len(oos_returns) ≤ 20` (backtest.py:96). Su 3 finestre OOS da 252g il concat dovrebbe avere >20 punti; da verificare in fase 06. |

---

**Stato fase:** 01_specification = **done**. Prossimo cursore: `S2:02_hypothesis`.