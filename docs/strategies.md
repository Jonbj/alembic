# Alembic — Strategy Reference

This document describes each trading strategy, its signal logic, sizing rules, and integration with the portfolio orchestrator.

> **Governance note (2026-06-21):** Live trading is NOT authorized. Strategy promotions require a passing gate report, an approved `strategy_lifecycle` DB row, and explicit PO sign-off. `GLOBAL_LIVE_PROMOTION_ENABLED` must remain `False`. Authoritative runtime state: `strategy_lifecycle` DB table (historical P2 status: `docs/archive/2026-06-p2-milestone/P2_STATUS_2026-06-21.md`).

---

## Strategy Mode Reference

| Mode | Meaning |
|------|---------|
| `research` | R&D only — no live capital, no portfolio orchestrator wiring |
| `paper` | Runs against paper account; observational only |
| `supervised_paper` | Paper trading with human review required before any promotion |
| `promotion_blocked` | Implementation complete but gate report missing or explicitly blocked; cannot be promoted |
| `live` | Real capital — requires `GLOBAL_LIVE_PROMOTION_ENABLED=True` (currently `False`) + PO sign-off |
| `disabled` | Not active; excluded from `StrategyRegistry.get_active_strategies()` |

---

## S1 — Multi-Lookback Relative Momentum

**Type:** Trend-following long-only
**File:** `src/strategies/s1/`
**Allocation:** 50% (see `config/strategies.yaml`)
**Status:** `supervised_paper` — demoted from paper to supervised_paper 2026-06-18 (P0-01, commit `cb1d43a`)

> Live trading is **NOT authorized** for S1. Promotion from `supervised_paper` to `live` requires: (1) 90 days of controlled paper evidence, (2) P2-05 closure, (3) Kimi P2 Acceptance Audit, (4) PO sign-off, (5) `GLOBAL_LIVE_PROMOTION_ENABLED=True` (currently `False`).

### Signal Logic

Computes a multi-lookback, vol-normalised momentum signal with cross-sectional z-scoring:

```
For each lookback lb in {21, 63, 126, 252} trading days:
    raw_lb = price / price.shift(lb) - 1          (raw return)
    norm_lb = raw_lb / rolling_vol(63d)            (vol-normalised)

signal_raw = weighted_sum(norm_lb, weights)         # exponential: longer lb → more weight
signal = cross_sectional_z_score(signal_raw)        # z-score across all symbols at each date
```

- **Lookbacks:** 1M (21d), 3M (63d), 6M (126d), 12M (252d) — captures momentum at multiple horizons
- **Weighting:** Exponential (longer lookbacks weighted more: 1×, e×, e²×, e³×, normalised)
- **Cross-sectional z-score:** Standardises signals across the universe at each date; a symbol ranks relative to peers, not on absolute return level
- **Long-only:** Negative signals produce zero weight; no shorting

> **Note:** This is _not_ the canonical Moskowitz et al. 12-1 TSMOM. It is best described as "Multi-Lookback Relative Momentum" — the cross-sectional z-score makes it a hybrid time-series/cross-sectional approach.

### Sizing

`src/strategies/s1/sizing.py`:
- `raw_weight ∝ signal × (target_vol / realised_vol)` — inverse-vol sizing
- Normalised to sum ≤ 1.0 across all long positions (sleeve-local weights)
- Output: `{symbol: sleeve_weight}` — orchestrator scales by `allocation_pct=0.50`

### Key Parameters (`S1Config`)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `lookbacks` | (21, 63, 126, 252) | Lookback windows in trading days |
| `vol_window_signal` | 63 | Rolling vol for return normalisation |
| `target_vol` | 0.15 | Annualised vol target for sizing |

### Integration

S1 exposes `compute_target_weights(prices: pd.DataFrame) → dict[str, float]`. The orchestrator calls this directly when `strategy_id == "S1"` in `_extract_target_weights()`.

---

## S2 — Volatility Risk Premium (VRP)

**Type:** Mean-reversion, overnight gap
**File:** `src/strategies/s2/`
**Allocation:** 0% — **disabled by default**
**Status:** Research only — OOS Sharpe −0.55, all backtest gates (1–4) failed

> ⚠️ S2 is **not active** in paper or live trading. It is registered in `StrategyRegistry` with `enabled=False, allocation_pct=0.00`. To activate it, you must manually edit `config/strategies.yaml` — doing so is explicitly flagged as requiring research milestone gates to pass first.

### Economic Rationale

The normative theory is documented in
[`docs/strategies/s2-vrp-theory.md`](strategies/s2-vrp-theory.md). In seller-sign terms,
the variance risk premium is the difference between risk-neutral expected variance and
physical expected variance over the same horizon. It is primarily compensation for
downside, jump, convexity, correlation, liquidity, and intermediary-capital risks, not
alpha by definition. A short put is a mixed exposure to that premium; long SPY overnight
is not an equivalent variance-premium exposure.

### Current Implementation (Proxy)

The current `S2ProxyStrategy` is an equity proxy — it does **not** use options. It goes long SPY at close when VRP (VIX / realised_vol_20d - 1) exceeds a threshold and exits at the next open.

This is a simplified stand-in. The intended S2 design (cash-secured short put on SPY at delta −0.20, DTE 30–45d) requires options data, greeks pricing, margin modeling, and an IBKR adapter (Phase D).

### Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `vrp_threshold` | 0.20 | Minimum implied/realised premium |
| `lookback_days` | 63 | Realised vol window (≈ 3 months) |
| `position_size` | 0.25 | Fraction of NAV per trade |

### Integration

S2 runs as `(ts, data_replay, portfolio, market) → list[Order]`. The orchestrator converts orders to implied weights. Currently inactive — all cycles skip S2 since it is disabled in `config/strategies.yaml`.

---

## S4 — News-Driven Tactical

**Type:** News sentiment momentum
**File:** `src/strategies/s4/`
**Allocation:** Configurable via `StrategyRegistry`
**Status:** `promotion_blocked` — allocation capped until dedicated gate report is produced (P0-13, commit `6d86d3f`)

### Signal Logic (live = portfolio path)

The authoritative execution path is `execution.engine: portfolio` — only the portfolio
cycle submits orders. S4 reads pre-computed ensemble sentiment from Redis/PostgreSQL
(written by SentimentWorker every 15 min) and gates it through a **documented chain**:

1. **Freshness** — only signals within `max_signal_age_hours` (4h) of the cycle tick;
   staler ones are dropped (Decision Log: `SKIP_STALE`). Per symbol, the most recent
   **ensemble** signal is preferred over a later FinBERT fallback.
2. **Prefilter (ranker)** — `CrossSectionalRanker` keeps signals with
   `score ≥ S4Config.min_score` (0.10) and `confidence ≥ S4Config.min_confidence`
   (0.30). These are **prefilters**, NOT the order threshold.
3. **Feedback gate = the order threshold** — a signal must clear the live
   `feedback:entry_threshold` (baseline **0.30**, currently raised to **0.35** by the
   loss-feedback loop, up to 0.60). Below it → dropped (Decision Log: `SKIP_THRESHOLD`).
4. **Cross-sectional ranking** — top-N (`n_top=5`) of the survivors, minimum 2 stocks,
   equal-weight within the bucket.

> **Threshold map — three distinct concepts, do not conflate:**
> | Name | Value | Role |
> |---|---|---|
> | `S4Config.min_score` / `min_confidence` | 0.10 / 0.30 | ranker **prefilter** |
> | `feedback:entry_threshold` | baseline 0.30, dynamic (→0.60) | **order gate (source of truth)** |
> | legacy `ENTRY_THRESHOLD` + `score>0.30 AND price>EMA20` | — | old `legacy_sentiment` path, **INACTIVE** under `engine=portfolio` |

Exit conditions:
- Stop-loss: position closed if price falls to `entry_price × (1 - stop_loss_pct)`
- Positions absent from the new target weights are closed at the next rebalance.

### Scoring Formula

```
score = polarity × confidence
```

Where `polarity ∈ [-1, +1]` is the direction of sentiment and `confidence ∈ [0, 1]` is model certainty. A strong call with low confidence yields a small score — the formula correctly penalises uncertainty.

### LLM Ensemble

Due modelli attivi via Ollama Cloud:
- Kimi K2.6 + GLM-5.2

> Qwen3.5 sostituito da GLM-5.2 il 2026-06-29 (estrazione ticker troppo aggressiva su news macro). DeepSeek-V4-Pro e GLM-5.1 rimossi il 2026-06-16. Vedi `docs/llm-config.md` e `docs/CHANGELOG.md`.

Each uses **DK-CoT** (Domain Knowledge Chain-of-Thought) prompting:
1. Act as buy-side analyst
2. Reason through cash flows, competition, profitability
3. Provide explicit bull/bear cases
4. Return structured JSON (`polarity`, `confidence`, `reasoning`)

**Divergence check:** If `std(scores) > 0.30` → discard ensemble, use FinBERT local fallback.

### FinBERT Fallback

FinBERT (BERT fine-tuned on financial text) runs locally. Confidence uses **entropic confidence**:
```
confidence = 1 - H(p) / log(3)
```
where `H(p)` is Shannon entropy of the 3-class softmax (positive/negative/neutral). A peaked distribution → high confidence; flat distribution → near-zero score.

### Regime Scaling

Position size is scaled by `regime_multiplier` (written to Redis by RegimeDetector):
```
order_notional = base_size × regime_multiplier
```

The multiplier (0.2× to 1.0×) prevents full-size entries during bear markets or volatility spikes, even when the sentiment signal is strongly positive.

### Key Parameters (`S4Config`)

> **Verificato contro `src/strategies/s4/config.py` il 2026-08-03.** La tabella precedente
> elencava quattro parametri (`score_threshold`, `signal_max_age_min`, `base_position_size`,
> `stop_loss_pct`) di cui **nessuno esiste in `S4Config`**, e uno era fuorviante di un fattore
> otto: dichiarava una scadenza segnale di 30 minuti contro le 4 ore reali.

| Parameter | Default | Description |
|-----------|---------|-------------|
| `n_top` | 5 | Numero di ticker selezionati per ciclo |
| `bucket_pct` | 0.10 | Quota di portafoglio assegnata alla sleeve S4 |
| `min_score` | 0.1 | **Prefiltro del ranker**, NON la soglia d'ordine |
| `min_confidence` | 0.3 | **Prefiltro del ranker**, NON la soglia d'ordine |
| `min_stocks` | 1 | Minimo di titoli per emettere ordini (1 = ammesso il lone survivor) |
| `fixed_slot_sizing` | True | Peso fisso 1/`n_top` per ticker; gli slot inutilizzati restano non investiti (#81) |
| `signals_lookback_hours` | 96 | Finestra di lettura dei segnali dal DB (copre il ponte festivo Ven→Mar) |
| `max_signal_age_hours` | 4 | Oltre questa età il segnale è scaduto e la posizione viene chiusa |
| `rebalance_frequency` | DAILY | Cadenza di ribilanciamento della sleeve |

**La soglia d'ordine non è in `S4Config`.** È `feedback:entry_threshold` in Redis (baseline 0.30,
alzata dinamicamente dal loop di loss-feedback) ed è applicata a monte, nel portfolio scheduler.
Confondere `min_score` con la soglia d'ordine è l'errore che nel luglio 2026 ha lasciato il gate
disarmato per un giorno e mezzo (issue #163).

---

## S3 — Cross-Sectional Momentum (R&D Sleeve)

**Status:** Research/development — not deployed in paper trading
**Type:** Cross-sectional equity momentum
**File:** `src/strategies/s3/`

### Signal Logic

Ranks all universe securities by 12-1 month return. Goes long top quintile (Q5), short bottom quintile (Q1). Rebalances monthly.

**Universe:** `src/strategies/s3/universe.py` — S&P 500 constituents filtered by liquidity.

**Status:** Gate validation pending. Not active in `StrategyRegistry` until backtest gates pass.

---

## Portfolio Orchestration

All active strategies flow through the `PortfolioOrchestrator` using a **weight-then-order** architecture.

### Sleeve-Local Allocation

Strategies produce **sleeve-local weights** — fractions of their own capital sleeve, not the whole portfolio. The orchestrator scales each by `allocation_pct` and sums to get portfolio-level targets:

```python
# Current active allocations (from config/strategies.yaml):
#   S1: allocation_pct=0.50  (50% of portfolio)
#   S2: disabled             (0% — OOS gates not passed)
#   S4: allocation_pct=0.10  (10% of portfolio, paper overlay)
# Remaining 40% = implicit cash residual

S1.compute_target_weights(prices)   → {AAPL: 0.40, NVDA: 0.20, ...}  # sleeve-local
S4.compute_target_weights(signals)  → {MSFT: 0.30, TSLA: 0.20, ...}  # sleeve-local

merged = {}
for strategy, alloc_pct in [(S1, 0.50), (S4, 0.10)]:
    for sym, wt in strategy_weights.items():
        merged[sym] = merged.get(sym, 0) + wt * alloc_pct
# → AAPL: 0.40×0.50 = 0.20 (20% of portfolio)
# → NVDA: 0.20×0.50 = 0.10
# → MSFT: 0.30×0.10 = 0.03

delta_orders = [BUY/SELL (target_qty - current_qty) for sym in merged]
```

Allocation config is in `config/strategies.yaml` — that file is the **single source of truth**. `StrategyRegistry` reads it at startup with startup validation (sum ≤ 1.0, S4 ≤ 10%, S2 enabled requires explicit override).

### Constraint Enforcement

Applied iteratively (up to 10 passes) after weight merging:

| Constraint | Default | Action |
|-----------|---------|--------|
| Max single asset | 10% NAV | Scale down BUY |
| Max strategy exposure | alloc_pct × 1.5 | Scale down excess |
| Max portfolio exposure | 50% NAV | Scale all BUYs |
| Max sector exposure | 25% NAV | Scale sector BUYs |
| Max correlation cluster | corr > 0.70 | Reduce higher-vol |

### Volatility Overlay

`PortfolioVolTargeter` computes EWMA portfolio vol from strategy return histories. BUY quantities are scaled by `target_vol / estimated_vol` (clamped to [0.5×, 2.0×]) so the portfolio targets 10% annualised volatility.

---

## S7 — PEAD (Post-Earnings Announcement Drift) — REMOVED 2026-07-15

**Status:** **REMOVED 2026-07-15.** Strategy dir, workers, routes, beat tasks, config,
API entries, tests e codice di supporto eliminati. S7 non è più in repo.

**Perché rimossa:** l'edge dichiarato di S7 (transcript tone → alpha, ALPHA-A3) è confutato
a decision-grade su dati reali. Tre valutazioni distinte, tutte negative:

| Valutazione | Data | Esito | n |
|---|---|---|---|
| ALPHA-A5 large-cap (FMP) | 2026-07-03 | FAIL — drift = beta SPY, hit 51%, no dose-response | 76 |
| POC-1 small/mid PEAD | 2026-07-04 | INCONCLUSIVE_DATA — copertura IEX/liquidità insufficiente | 15 |
| POC-2 transcript tone (ALPHA-A3) | 2026-07-15 | FAIL — IC≈0, spread invertito, split-half opposti, cross-model (kimi↔glm ρ=+0.858) | 73 |

La condizionale pre-registrata di PO-5 — *"Se POC-2 FAIL → REMOVE"* — è attivata.

**Cosa resta:** la documentazione storica completa in
`docs/S7_LIFECYCLE_HISTORY_2026-07-15.md` (design, implementazione, 4 run di valutazione,
decisioni PO, evidence synthesis) e i report/CSV raw in `reports/s7_*` (gitignored,
evidenza locale). Il codice rimosso è recuperabile da git se una futura strategia
event-driven volesse riutilizzare la superficie PEAD/8-K.

**Re-introduzione:** richiede un design fresco + gate evaluation ex novo (non una
riattivazione). Il test `TestS7NotInOperationalRegistry` (`tests/test_p0_13_*.py`) fa da
guard: S7 non deve ricomparire nel `StrategyRegistry` operativo, nemmeno disabilitata.
