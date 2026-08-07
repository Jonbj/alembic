# S3 — 01 Specificazione funzionale e matematica

**Strategia:** S3 `CrossSectionalMomentum` (Residual Momentum)
**Data:** 2026-08-04
**Fonti:** `src/strategies/s3/{strategy,signal,universe,backtest}.py`,
`config/strategies.yaml`, `docs/RESEARCH_S3_STRATEGY_REVIEW_2026-07-20.md`,
`reports/s3_backtest/summary.json`
**Stato (lifecycle DB):** **nessuna riga** (S3 non tracciata in `strategy_lifecycle`)
**Stato (yaml):** `enabled=false`, `allocation_pct=0.00`, `mode=research`; note:
"excluded from live; gate 3/5 failed, possible sizing lookahead"
**Registry:** **S3 NON è registrata** (`registry.py` carica solo S1/S2/S4); **nessun
path live** (`portfolio/orchestrator.py` restituisce pesi vuoti per ID non-S1/S4).

---

## 0. Avvertenza: design originale vs codice corrente

S3 esiste in **due formulazioni materialmente diverse** (vedi
`RESEARCH_S3_STRATEGY_REVIEW_2026-07-20.md` §3.1):

1. **Design originale** (issue #55 / `01_strategy_design.md`): 12-1 beta-adjusted
   **long-only** momentum, sizing inverse-vol 60d normalizzato, cap 10%.
2. **Codice corrente**: 12-0 beta-adjusted **long-short** residual momentum, sizing
   inverse-vol 252d **non normalizzato**, cap 20%, universo = primi 50 sopravvissuti
   alla data finale.

Queste differenze "definiscono un portafoglio economicamente diverso" (review §3.1).
L'OOS Sharpe 0.148 del `summary.json` misura il **codice corrente**, non il design
originale; non decide #55. Questa fase ricostruisce il **codice corrente**; le
divergenze con il design sono in §11 e analizzate nelle fasi 04/05.

## 1. Segnale: residual momentum

`compute_residual_momentum` (`signal.py:39-68`):

$$\mathrm{rm}_{i,t} = \underbrace{\left(\frac{P_{i,t}}{P_{i,t-252}} - 1\right)}_{\text{stock momentum 12-0}} - \beta_{i,t}^{(252)} \cdot \underbrace{\left(\frac{P_{\mathrm{SPY},t}}{P_{\mathrm{SPY},t-252}} - 1\right)}_{\text{market momentum 12-0}}$$

- `lookback = 252` (12 mesi, **0-1**: include il mese corrente, non skip-month).
- $\beta_{i,t}^{(252)}$ = `Cov(r_i, r_SPY).rolling(252) / Var(r_SPY).rolling(252)`
  (`signal.py:8-36`, OLS rolling su `beta_window=252`).
- Residuo = momentum azionario netto del contributo beta×momentum di mercato.
  Ipotesi: cattura la componente **idiosincratica** del momentum, meno esposta al
  beta di mercato (Gutman 2023 / Blitz-Hanauer-Vidojevic 2011 "residual momentum").

## 2. Ranking cross-sectionale e decili

`compute_cross_sectional_ranks` (`signal.py:71-108`):

- A ogni data `t`, rank ascendente (1=min, N=max), `method="average"`,
  `na_option="keep"`.
- `decile = ceil(rank · n_deciles / n_valid)`, `n_deciles=10`.
- Long = decile 10 (`long_decile=10`), Short = decile 1 (`short_decile=1` default →
  **long-short**).

`generate_s3_signals` (`signal.py:111-139`): richiede **tutti i ticker abbiano
residual momentum valido alla data** (`valid_rows = residual.notna().all(axis=1)`)
→ pannello **bilanciato**: una data è mantenuta iff ogni ticker nel pannello ha
NaN-free residual. Meccanismo correlato al look-ahead di S1 (BUG-2): i ticker
future-listed nel pannello rimuovono le date precedenti (§6).

## 3. Universo

`S3Universe.active_at(as_of)` (`universe.py:38-83`) — filtro di liquidità
**point-in-time**:
- Solo righe `<= as_of`; min 252 giorni di storia close non-NaN; close >= $5;
  ADV (close×volume, trailing 63g) >= $10M.
- `load_s3_universe` (`universe.py:94-146`): tickers da `data/sp500_tickers.csv`
  (snapshot **corrente**, 57 righe). Market-cap filter configurato **non
  implementato** (review §2.2).
- `run_s3_backtest_full` (`backtest.py:180-224`): `active = s3_universe.active_at(end)`
  con `end=today` → **50 nomi più liquidi OGGI**, riusati indietro su 2000-today.
  ⇒ **survivorship + look-ahead nella selezione universo** (§6).

## 4. Sizing

`compute_target_weights` (`strategy.py:92-139`):

- Per ogni long ticker: `raw_w = target_vol / vol_i`, capped `max_weight=0.20`;
  short: `−min(raw_w, max_weight)`.
- `vol_i` = `daily_rets.rolling(beta_window=252).std()·sqrt(252)`
  (`strategy.py:88`, precomputato su full prices, **causale** rolling).
- PIT lookup del vol: `valid_vol_dates <= as_of` (`strategy.py:117-119`) →
  sizing è PIT (fix del 2026-06-19, commit `e15d5e7`, vedi review §3.2).
- **Pesi NON normalizzati**: la somma dei pesi non è vincolata a 1 (né a 0 per
  long-short). Cap 20% per nome → gross exposure dipendente dal numero di nomi
  nel decile (variabile, tipicamente 5-10 nomi per decile su 50).
- `target_vol=0.10`, `max_weight=0.20`.

## 5. Rebalance, entry/exit

- `__call__` (`strategy.py:177-242`): rebalance **mensile** (`_should_rebalance`).
- `compute_target_weights(data_replay.prices_until(ts))` → `as_of = prices.index[-1]`
  (ultima data ≤ ts).
- **Exit**: chiude posizioni assenti dal target (SELL long / BUY short).
- **Entry/rebalance**: `target_qty = NAV·target_wt / price`; `delta = target_qty −
  current_qty`; BUY se delta>0, SELL se delta<0. Soglia `abs(delta) < 1e-4` skip.
- NAV = `cash + Σ pos.market_value(price)` (`_nav`, strategy.py:169-175).
- Una sola istanza strategia riusata tra finestre WF (review §2.2, stato
  mutabile `_last_rebalance`).

## 6. Pseudocodice completo (codice corrente)

```
precompute at construction (FULL prices):
  residual[i,t] = (P_i[t]/P_i[t-252]-1) - beta_252[i,t]·(P_SPY[t]/P_SPY[t-252]-1)
  balanced panel: keep date t iff ALL tickers have valid residual at t   # look-ahead date-selection
  decile[i,t] = ceil(rank_t(residual) · 10 / n_valid_t)
  vol[i,t] = std_rolling_252(r_i)·sqrt(252)   # causal

on each ts (monthly):
  as_of = last date <= ts in prices_until(ts)
  lookup_date = last date in rank_wide.index <= as_of
  long  = tickers with decile == 10 at lookup_date
  short = tickers with decile == 1  at lookup_date
  pit_vol = vol row at last vol date <= as_of
  for t in long:  w[t] =  min(target_vol/vol_t, 0.20)
  for t in short: w[t] = -min(target_vol/vol_t, 0.20)
  # weights NOT normalized
  NAV = cash + Σ market_value
  for pos not in target: close (SELL/BUY)
  for t in target: target_qty = NAV·w[t]/price; trade delta
```

## 7. Config effettivo (S3Config defaults)

| Parametro | Default | Ruolo |
|---|---|---|
| `lookback` | 252 | momentum 12-0 (include mese corrente) |
| `beta_window` | 252 | rolling OLS beta + vol sizing |
| `n_deciles` | 10 | bucket cross-sectionali |
| `target_vol` | 0.10 | inverse-vol target |
| `max_weight` | 0.20 | cap per nome (design originale: 0.10) |
| `long_decile` | 10 | top residuo |
| `short_decile` | 1 | bottom residuo (design originale: None = long-only) |
| `rebalance_frequency` | MONTHLY | |

**Dead config**: `S3Config.from_yaml` esiste (`strategy.py:37-53`) ma **nessun call
site** in `src/` (backtest.py:37 usa `S3Config()`); nessun `config/s3*.yaml`. Pattern
dead-config identico a S1 BUG-1 / S2 BUG-D.

## 8. Backtest (reports/s3_backtest/summary.json)

- **OOS Sharpe = 0.148**; `milestone_c_pass = false` (gates 3/5 fail).
- WF: 21 finestre (1260/252 su 2000-today), mean Sharpe 0.011, median 0.0,
  std 0.798, positive fraction 0.333. Worst DD −46.03%.
- Gate 1 significance **PASS** ma con `min_sharpe=0.0` (soglia banale; Sharpe 0.18).
- Gate 2 walk-forward **PASS** ma con `min_oos_sharpe=0.0` (soglia banale; 7/13
  positive = 0.54).
- Gate 3 robustness **FAIL** (CV 2.05 > 0.5; min_sharpe −0.027 non all_positive).
- Gate 4 regime **PASS**.
- Gate 5 stress **FAIL**.
- File datati 2026-06-01, ignorati da Git, nessun manifest dati/versione
  (review §2.2) → **non riproducibile**.

## 9. Stato di integrazione (N/A in produzione)

- **Registry**: S3 NON registrata (`registry.py` solo S1/S2/S4).
- **Orchestrator live**: `portfolio/orchestrator.py` gestisce esplicitamente S1/S4;
  per altri ID restituisce **pesi vuoti** (review §2.2).
- **Lifecycle DB**: nessuna riga S3.
- ⇒ S3 è **offline-only**: esiste come codice di backtest, nessun path live, nessun
  contratto di integrazione. Coerente con `mode=research`.

## 10. Risultati della review interna (RESEARCH_S3_STRATEGY_REVIEW_2026-07-20)

- **Verdetto review**: autorizzare un POC A/B offline circoscritto, NON paper
  trading né broker wiring. Il codice corrente **non riproduce** il design
  originale; il vecchio 0.148 non decide #55 perché misura una strategia diversa
  con dati/soglie/metodologia poi cambiati.
- Sizing PIT corretto (`e15d5e7`, 2026-06-19); metodologia stress (`d6d7f44`).
- Issue #55 (POC design-alignment) **ancora aperta**, `ready-for-human`.

## 11. Divergenze codice ↔ design originale (per fasi 04/05)

| ID | Divergenza | Codice | Design originale (#55) |
|---|---|---|---|
| DV-1 | Return di formazione | `P[t]/P[t-252]-1` (12-0) | `log(P[t-21]/P[t-252])` (12-1, skip mese) |
| DV-2 | Correzione mercato | `beta × SPY momentum to t` (12-0) | `beta × SPY 12-1` |
| DV-3 | Legs | long + short (default `short_decile=1`) | long-only (short escluso) |
| DV-4 | Sizing | inverse-vol 252d, **non normalizzato** | inverse-vol 60d, **normalizzato** |
| DV-5 | Cap | 20% | 10% |
| DV-6 | Universo | primi 50 sopravvissuti attivi alla data finale | US large/mid liquide PIT |
| DV-7 | Pannello bilanciato | date droppate se un ticker ha NaN | n/a (design non specifica) |
| DV-8 | Dead config | `from_yaml` mai chiamato, no yaml file | n/a |

---

**Stato fase:** 01_specification = **done**. Prossimo cursore: `S3:02_hypothesis`.