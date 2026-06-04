# ENTRY_THRESHOLD Analysis: Signal Distribution vs Threshold

**Date**: 2026-06-04  
**Branch**: phase-A-foundation  
**Analyst**: Claude (automated analysis)  
**Data window**: 1,822 signals from `sentiment_signals` table (May–Jun 2026)

---

## 1. Where ENTRY_THRESHOLD Is Defined

**File**: `src/workers/execution.py`, line 46  
**Value**: `0.3` (hardcoded constant)  
**Usage**: `src/workers/execution.py:303` — `if score <= ENTRY_THRESHOLD: continue`

The threshold is used to gate BUY orders in the live paper-trading execution worker. Only signals with `score > 0.30` AND `price > EMA20` result in a BUY order.

```python
ENTRY_THRESHOLD = 0.3  # src/workers/execution.py:46
```

A secondary copy exists at `quantconnect/intraday_strategy.py:28` (unused in live trading).

---

## 2. What the Backtests Used — and the Mismatch

### S1 backtest (`reports/s1_backtest/`, `config/s1_strategy.yaml`)

The S1 backtest is a **pure price-momentum strategy** (time-series momentum over 21/63/126/252-day lookbacks). It has a `signal_threshold: 0.0` in its YAML config, but this refers to a **price-momentum signal cutoff** (a z-score-like quantity), **not** an LLM sentiment score. LLM signals are not part of S1 at all.

The S1 OOS Sharpe (0.51) reported in `reports/s1_backtest/summary.json` is the momentum-only result — it tells us nothing about what ENTRY_THRESHOLD should be for LLM-gated execution.

**The sensitivity grid** in `src/strategies/s1/sensitivity.py` tests thresholds `(0.0, 0.25, 0.5, 0.75, 1.0)` — again, these are momentum thresholds, not LLM score thresholds.

### GDELT backtest IC reports (`reports/backtest_gkg-*.json`)

These reports **do** operate on LLM sentiment signals (GDELT-sourced, Nov 2025 – Jan 2026). They show strong composite IC:

| Period | Composite IC (24h) | ICIR (24h) | Signals w/ returns |
|--------|--------------------|------------|--------------------|
| Nov 2025 | 0.289 | 16.7 | 1,706 |
| Dec 2025 | 0.272 | ~16 | 1,576 |
| Jan 2026 | 0.258 | ~19 | 3,299 |

**However**, these IC metrics were computed over **all signals with no threshold applied** — the signal population was not filtered at 0.30 before IC calculation. Furthermore, "composite IC" is a multi-component formula (Pearson IC + weighted hit rate + Brier score), not the simple Pearson correlation used in Section 4 below.

**Bottom line: `ENTRY_THRESHOLD = 0.30` has never been tested in any backtest.** The value was set directly in `execution.py` with no empirical calibration against signal data.

---

## 3. Score Distribution

**Total signals in `sentiment_signals`**: 1,822  
**Date range**: May 2026 (1,581) + Jun 2026 (241, all with `forward_return IS NULL`)  
**Score range**: –0.80 to +0.90 | **Mean**: 0.186 | **Median**: 0.180 | **P25**: 0.000 | **P75**: 0.518

Special values:
- 192 signals with `score = 0.00` (ensemble returned "no opinion", polarity × confidence = 0)
- 450 signals with `score < 0.00` (negative sentiment, not eligible for BUY)
- 1,180 signals with `score > 0.00`

### Signal count by threshold

| Threshold | N signals (≥ threshold) | % of total | Avg score of passing |
|-----------|------------------------|------------|----------------------|
| 0.00 | 1,372 | 75.3% | 0.343 |
| 0.05 | 1,150 | 63.1% | 0.408 |
| 0.10 | 1,051 | 57.7% | 0.440 |
| 0.15 | 968 | 53.1% | 0.467 |
| 0.20 | 868 | 47.6% | 0.501 |
| 0.25 | 754 | 41.4% | 0.543 |
| **0.30 (current)** | **704** | **38.6%** | **0.562** |
| 0.35 | 642 | 35.2% | 0.586 |
| 0.40 | 592 | 32.5% | 0.604 |
| 0.45 | 536 | 29.4% | 0.623 |

The current threshold of 0.30 rejects **61.4%** of all signals. Given the median score is 0.18, more than half of all signals produced by the ensemble fall below threshold.

---

## 4. IC Analysis by Threshold

**Data quality warning**: 1,093 of 1,822 signals (60%) have `forward_return IS NULL`. All 241 June 2026 signals lack returns (too recent to have settled price data). One signal has `forward_return = 45.19` (a 4,519% return — confirmed outlier, excluded from calculations below). The IC analysis uses only the 591 non-null, non-outlier returns from May 2026 signals.

The "IC (Pearson)" column is the Pearson correlation between `score` and `forward_return` for signals passing each threshold. "T-stat" is the signal t-statistic for a one-sample test of mean return.

| Threshold | N w/ return | Avg fwd return | Std fwd return | IC (Pearson) | T-stat |
|-----------|-------------|----------------|----------------|--------------|--------|
| 0.00 | 591 | +0.0041 | 0.0499 | –0.024 | 1.98 |
| 0.05 | 505 | +0.0052 | 0.0498 | –0.079 | 2.35 |
| 0.10 | 471 | +0.0046 | 0.0497 | –0.068 | 2.02 |
| 0.15 | 441 | +0.0041 | 0.0489 | –0.061 | 1.78 |
| 0.20 | 395 | +0.0030 | 0.0482 | –0.035 | 1.25 |
| 0.25 | 350 | +0.0023 | 0.0488 | –0.012 | 0.90 |
| **0.30 (current)** | **328** | **+0.0025** | **0.0500** | **–0.022** | **0.91** |
| 0.35 | 299 | +0.0021 | 0.0513 | –0.006 | 0.70 |
| 0.40 | 281 | +0.0016 | 0.0518 | +0.013 | 0.51 |
| 0.45 | 259 | +0.0018 | 0.0519 | +0.011 | 0.55 |

**No threshold achieves statistically significant IC** (threshold: |t| > 1.96 for IC, two-tailed). The IC at thresholds 0.05–0.15 is *negative* (higher scores slightly predict lower returns in this dataset), though this is driven by the limited data window (2 months) and should not be over-interpreted.

IC first turns positive at threshold ≥ 0.40 (+0.013), but the t-stat there (0.51) is far below significance. The average forward return peaks at threshold 0.05 (+0.0052, ~0.5%) then declines monotonically with increasing threshold.

**Estimated Sharpe proxy**: The t-stats above are essentially annualized Sharpe estimates for each subset (for 24h hold periods). None exceed 2.5. At the current 0.30 threshold, t-stat = 0.91 → implied annual Sharpe ≈ 0.91 × √(252 / n_windows) ≈ 0.5 (rough; assumes independent daily trades), consistent with S1 OOS Sharpe of 0.51 — but that S1 figure is from a price-momentum backtest, not an LLM-gated strategy.

---

## 5. Backtest vs. Live Signal Mismatch

### Model composition

The GDELT backtest IC reports (Nov–Jan) were computed on a variety of 2–4 model ensembles. The live `sentiment_signals` table shows a very different distribution:

| Model ID | N signals | % | Avg score | % above 0.30 |
|----------|-----------|---|-----------|--------------|
| `ensemble:glm-5.1:cloud` (single model) | 1,565 | 85.9% | 0.201 | 41.3% |
| `ensemble:kimi-k2.6+qwen3.5:397b+deepseek-v4-pro+glm-5.1` (4-model) | 99 | 5.4% | 0.138 | 33.3% |
| `ensemble:kimi-k2.6+deepseek-v4-pro+glm-5.1` (3-model) | 39 | 2.1% | 0.047 | 20.5% |
| (other) | 119 | 6.5% | varies | varies |

**85.9% of live signals come from a single-model ensemble** (`glm-5.1` only). The budget constraints (token quota) are forcing the system into single-model mode most of the time. The backtest IC figures were measured on multi-model ensembles; the live operational mode is fundamentally different.

The full 4-model ensemble that the live signal description mentions (`ensemble:kimi-k2.6.2:cloud+qwen3.5:397b+deepseek-v4-pro:cloud+glm-5.1:cloud`) accounts for only ~5% of actual signals in the database. Its avg score (0.138) is lower than single-model GLM (0.201), and its pass rate at 0.30 (33.3%) is lower.

### Scoring formula consistency

The score formula `score = polarity × confidence` is defined in `src/workers/sentiment.py`. The live signals use this formula. The GDELT backtest IC reports computed IC on signals from a different pipeline state (Nov–Jan) with potentially different model combinations. There is no evidence of a normalization change, but the model composition change alone is enough to shift the score distribution.

### EMA filter as additional gate

Even when `score > 0.30`, orders are only placed if `price > EMA20`. This second gate further reduces live execution. Tiny allocation weights (2.5%) noted in the problem description suggest the `regime_multiplier` is also at a low setting (likely `bear: 0.4` or `high_vol: 0.2` per `config/workers.yaml`).

---

## 6. Data Caveats

1. **Forward return coverage is 40%**: Only 729 of 1,822 signals have `forward_return` populated. All June 2026 signals (241) are missing returns. IC estimates are from a subset that may not be representative.

2. **Single 2-month window**: The analysis covers only May–June 2026 — a single market regime. IC estimates from a 2-month window are highly unstable. The central limit theorem requires ~250 independent signal observations per threshold for reliable IC estimates at the 5% level.

3. **One extreme outlier** (`forward_return = 45.19`) was excluded. This is likely a data error (e.g., a stock split or a mis-matched price) in whatever process populates `forward_return`. It inflates avg_fwd_return by ~20x at thresholds < 0.20 if included. It should be investigated and corrected in the data pipeline.

4. **Model mismatch between backtest and live**: The strong GDELT backtest IC (composite IC ≈ 0.26–0.29) was measured on a different time window (Nov 2025 – Jan 2026) with a different model mix. Live data is 85.9% single-model (GLM), which was not the dominant model in the backtest period.

5. **No position-level P&L data**: There is no table recording trade-level P&L from the paper trading execution. Sharpe estimates above are proxies from per-signal return statistics, not actual portfolio Sharpe.

---

## RECOMMENDATION

> **This section is a recommendation, NOT a code change. No production files were modified.**

### Do not lower the threshold purely on this analysis

The IC data is insufficient in quality (40% coverage, 2-month window, one outlier) and too noisy (no threshold achieves significant IC) to make a confident data-driven argument for any specific threshold value. Lowering the threshold without better evidence risks increasing turnover with no improvement in signal quality.

### The core issue is not the threshold — it's model composition

85.9% of live signals are generated by a single cheap model (GLM-5.1) with avg score 0.20. The full 4-model ensemble that was expected to be operational (based on the model_id in the problem description) produces only 5.4% of signals. The `ENTRY_THRESHOLD = 0.30` is calibrated against what a 4-model ensemble would produce — but the 4-model ensemble is barely running due to token budget constraints.

**Priority fix**: Restore the 4-model ensemble to operational status, or recalibrate ENTRY_THRESHOLD against the score distribution of whichever model configuration is actually running.

### Provisional threshold estimates for three scenarios

If the threshold must be adjusted before ensemble composition is fixed, these are the data-consistent options:

| Scenario | Threshold | Signal pass rate | Rationale |
|----------|-----------|------------------|-----------|
| Conservative (status quo) | 0.30 | 38.6% | Unchanged; well above median, high-conviction only |
| Moderate | 0.15 | 53.1% | Near the P50 of GLM scores; IC not worse than 0.30 |
| Aggressive | 0.05 | 63.1% | Accepts all positive-opinion signals; highest avg return in dataset, but IC is negative |

The moderate scenario (0.15) would bring signal pass rate above 50% and is consistent with the GLM-5.1 median score (0.21) being just above the threshold. There is no evidence of IC improvement going from 0.15 to 0.30.

### Before any threshold change: collect better data

The minimum for a defensible threshold decision:
1. Populate `forward_return` for all signals (fix the ETL lag — currently 60% NULL)
2. Investigate and clean the 45.19 outlier in `forward_return`
3. Accumulate ≥3 months of signals with returns before computing IC per threshold
4. Run a proper LLM-gated backtest that connects sentiment signals to position P&L (not just per-signal return stats)

Once `forward_return` coverage reaches ≥80%, re-run the IC query in Section 4 and look for the first threshold where IC turns positive AND t-stat > 1.65.
