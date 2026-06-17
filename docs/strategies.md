# Alembic — Strategy Reference

This document describes each trading strategy, its signal logic, sizing rules, and integration with the portfolio orchestrator.

---

## S1 — Multi-Lookback Relative Momentum

**Type:** Trend-following long-only
**File:** `src/strategies/s1/`
**Allocation:** 50% (see `config/strategies.yaml`)
**Status:** Live/paper core — OOS Sharpe ~0.51, all gates passed

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

Implied vol (VIX) systematically exceeds realised vol by ~3–4 vol points annualised. Selling that premium (via short puts or long SPY overnight) captures a structural income edge.

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

### Signal Logic

Reads pre-computed LLM ensemble sentiment signals from Redis (written by the SentimentWorker every 15 min). Entry conditions:
1. `score > 0.3` — signal is meaningfully bullish (filters near-neutral signals)
2. `price > EMA20` — price is in an uptrend (avoids buying into a downtrend on sentiment alone)

Exit conditions:
- Stop-loss: position closed if price falls to `entry_price × (1 - stop_loss_pct)`
- Signal expiry: signal older than 30 min → skip (stale news has no edge)

### Scoring Formula

```
score = polarity × confidence
```

Where `polarity ∈ [-1, +1]` is the direction of sentiment and `confidence ∈ [0, 1]` is model certainty. A strong call with low confidence yields a small score — the formula correctly penalises uncertainty.

### LLM Ensemble

Due modelli attivi via Ollama (locale):
- Kimi K2.6, Qwen3.5

> DeepSeek-V4-Pro e GLM-5.1 rimossi il 2026-06-16 (OOM e IC inferiore rispettivamente). Vedi `docs/llm-config.md`.

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

| Parameter | Default | Description |
|-----------|---------|-------------|
| `score_threshold` | 0.3 | Minimum score to trigger BUY |
| `signal_max_age_min` | 30 | Max signal age before stale |
| `stop_loss_pct` | 0.05 | 5% stop-loss from entry |
| `base_position_size` | 0.02 | 2% of NAV per position |

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
| Max portfolio exposure | 95% NAV | Scale all BUYs |
| Max sector exposure | 25% NAV | Scale sector BUYs |
| Max correlation cluster | corr > 0.70 | Reduce higher-vol |

### Volatility Overlay

`PortfolioVolTargeter` computes EWMA portfolio vol from strategy return histories. BUY quantities are scaled by `target_vol / estimated_vol` (clamped to [0.5×, 2.0×]) so the portfolio targets 10% annualised volatility.

---

## S7 — PEAD (Post-Earnings Announcement Drift)

**Type:** Event-driven momentum
**File:** `src/strategies/s7/`
**Allocation:** 15% (see `config/strategies.yaml`)
**Status:** ATTIVO in produzione da 2026-06-07

### Segnale

Classifica gli 8-K filing SEC via LLM (Ollama). Estrae la direzione della sorpresa rispetto alle aspettative di consensus: dopo una sorpresa positiva, le azioni tendono a continuare a salire nei giorni successivi (drift). S7 cattura questo momentum post-annuncio.

**Gate di ingresso:** score LLM > 0.3, filing < 4 ore dalla pubblicazione

### Pipeline

```
SEC EDGAR API (ogni 30 min) → run_sec_edgar_ingestion_worker
       ↓
run_pead_ingestion_worker (+5 min offset) → Ollama LLM classification
       ↓
pead_signals table (PostgreSQL)
       ↓
Portfolio Orchestrator → weight target S7
```

### Schedule

`pead-ingestion` Celery beat task: ogni 30 min, 14:05–21:35 UTC, offset +5 min da SEC EDGAR ingestion (:00/:30) per garantire che i filing siano già disponibili prima della classificazione. Queue: `inference`.

**Worker:** `src/workers/pead_worker.py`
**Routes:** `src/api/routes/pead_routes.py`

Vedi `docs/strategies/s7-pead.md` per la documentazione completa.
