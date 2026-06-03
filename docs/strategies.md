# Alembic — Strategy Reference

This document describes each trading strategy, its signal logic, sizing rules, and integration with the portfolio orchestrator.

---

## S1 — Time-Series Momentum

**Type:** Trend-following long-only
**File:** `src/strategies/s1/`
**Allocation:** Configurable via `StrategyRegistry`

### Signal Logic

Implements the Moskowitz, Ooi & Pedersen (2012) time-series momentum signal:

```
signal = sign(total_return_{t-12, t-1}) × annualised_sharpe_ratio
```

- **Lookback:** 12 months, skip the most recent month (avoids short-term reversal)
- **Entry:** Long when signal > 0, skip when signal ≤ 0 (long-only in this implementation)
- **EMA filter:** Price must be above EMA20 to enter (confirms trend direction)

### Sizing

`src/strategies/s1/sizing.py`:
- `base_weight = 1 / N_symbols` (equal-weight across positive signals)
- `vol_scaled_weight = base_weight × (target_vol / realised_vol)` using EWMA vol (60-day span)
- Output: dict of `{symbol: target_weight}` passed to PortfolioOrchestrator

### Key Parameters (`S1Config`)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `lookback_months` | 12 | Return lookback window |
| `skip_months` | 1 | Short-term reversal skip |
| `ema_period` | 20 | Trend filter EMA days |
| `target_vol` | 0.15 | Annualised vol target |

### Integration

S1 exposes `compute_target_weights(prices: pd.DataFrame) → dict[str, float]`. The orchestrator calls this directly when S1 is active.

---

## S2 — Volatility Risk Premium (VRP)

**Type:** Mean-reversion, overnight gap
**File:** `src/strategies/s2/`
**Allocation:** Configurable via `StrategyRegistry`

### Signal Logic

Exploits the **volatility risk premium**: implied vol (VIX) tends to exceed realised vol, meaning the market over-pays for fear. When VRP (VIX / realised_vol_20d - 1) is high, mean-reversion is more likely.

- **VRP threshold:** `vrp > 0.20` (20% implied premium over realised)
- **Entry:** At market close (hold overnight, exit at next open)
- **Direction:** Long SPY when VRP is elevated (expect overnight gap up)

### Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `vrp_threshold` | 0.20 | Minimum implied/realised premium |
| `lookback_days` | 63 | Realised vol window (≈ 3 months) |
| `position_size` | 0.25 | Fraction of NAV per trade |

### Integration

S2 runs as a callable `(ts, data_replay, portfolio, market) → list[Order]`. The orchestrator converts orders to implied weights for merging with weight-based strategies.

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

Four models queried in parallel via Ollama cloud:
- Kimi K2.6, Qwen3.5, DeepSeek-V4-Pro, GLM-5.1

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

All active strategies flow through the `PortfolioOrchestrator` using a **weight-then-order** architecture:

```
S1.compute_target_weights(prices)    → {AAPL: 0.05, NVDA: 0.03, ...}
S2(ts, data_replay, ...)            → orders → implied weights
S4.compute_target_weights(signals)   → {AAPL: 0.02, MSFT: 0.01, ...}

merged = {}
for strategy, alloc_pct in [(S1, 0.50), (S2, 0.30), (S4, 0.20)]:
    for sym, wt in strategy_weights.items():
        merged[sym] = merged.get(sym, 0) + wt * alloc_pct

delta_orders = [BUY/SELL target_qty - current_qty for each sym in merged]
```

This eliminates the double-counting problem where independent strategies each submit full-portfolio orders that would be additively merged.

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
