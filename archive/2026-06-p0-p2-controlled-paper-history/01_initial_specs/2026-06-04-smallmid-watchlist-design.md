# Small/Mid-Cap Watchlist Evaluation — Design Spec

**Date:** 2026-06-04  
**Status:** Approved  
**Scope:** Evaluate whether adding small/mid-cap symbols to the S4 trading strategy improves performance

---

## Context

The S4 (News-Driven Tactical) strategy fetches sentiment signals for watchlist symbols only. During analysis of a bug (off-watchlist symbols entering S4 ranking), we found that symbols like CRDO, ALAB, GFS, and ADI generate signals but cannot be traded (no market price in snapshot). Two large-caps — DELL and MRVL — were also found missing from the watchlist without justification.

The question: does adding small/mid-cap symbols improve S4 signal quality and portfolio performance?

---

## Step 0 — Immediate Watchlist Additions

Add **DELL** ($60B, large-cap) and **MRVL** ($60B, AI chip peer of NVDA/AMD) to `config/trading.yaml` in the semiconductors/tech section. No backtest required — liquidity and market cap are unambiguous. These are included in the next Alpaca news fetch and portfolio cycle automatically.

---

## Step 1 — IC Backtest Script

**File:** `scripts/backtest_smallmid_ic.py`

### Purpose
Measure signal quality (IC/ICIR) for small/mid-cap candidates against a watchlist baseline over 90 days of historical data.

### Candidate symbols
- `CRDO` (Credo Technology, ~$6B, AI interconnect)
- `ALAB` (Astera Labs, ~$10B, CXL/PCIe for AI servers)
- `GFS` (GlobalFoundries, ~$25B, foundry/AI supply chain)
- `ADI` (Analog Devices, ~$90B, analog semi — omitted from watchlist despite TXN peer being present)

### Baseline symbols (for comparison)
- `INTC`, `NVDA`, `MU`, `AMD` — already in watchlist, known behavior

### Flow
1. For each symbol in candidates + baseline: call `AlpacaNewsConnector.fetch_historical(start, end)` for the last 90 days
2. Run each article through `process_news_batch()` (existing async sentiment pipeline) in offline/batch mode — no Redis write, no DB write during this step
3. For each `SentimentResult`: fetch Alpaca minute bars, compute forward return at +1h, +4h, +24h
4. Write rows to `backtest_signals` table with `run_id = "alpaca-smallmid-YYYYMM"` and `news_source = "alpaca_benzinga"`
5. For each symbol: call `compute_composite_ic()` + `compute_icir()` from `src/performance/ic.py`, build report via `BacktestReportBuilder` → write `reports/backtest_alpaca-smallmid-YYYYMM.json`

### CLI interface
```
python scripts/backtest_smallmid_ic.py \
  --symbols CRDO ALAB GFS ADI \
  --baseline INTC NVDA MU AMD \
  --days 90 \
  --run-id alpaca-smallmid-2506
```

### Cost estimate
~90 days × 4 candidate symbols × ~3 articles/day = ~1,080 articles.  
LLM ensemble (2 models) ≈ $10–30 total. Acceptable.

---

## Step 2 — Promotion Gate

Printed at the end of Step 1. A symbol is **promoted** to Step 3 if:

| Metric | Threshold | Rationale |
|--------|-----------|-----------|
| `IC_24h` | ≥ 0.15 | Conservative vs `gkg-nov25-v1` baseline (0.289) |
| `ICIR_24h` | ≥ 2.0 | Statistical significance of IC |

Both conditions must hold. Output table:

```
Symbol  IC_24h  ICIR_24h  PROMOTED
CRDO    0.xxx   x.xx      YES / NO
ALAB    ...
GFS     ...
ADI     ...
```

If zero symbols are promoted, the process stops here with recommendation: do not expand universe.

---

## Step 3 — Portfolio S4 Universe Comparison

**File:** `scripts/compare_s4_universes.py`  
Only runs if ≥1 symbol was promoted in Step 2.

### Flow
1. Load Alpaca daily price bars for watchlist + promoted symbols (same 90-day window)
2. Load signals from `backtest_signals` where `run_id = "alpaca-smallmid-*"`
3. Run `run_s4_backtest_from_prices_and_signals()` twice:
   - **Universe A:** current watchlist only
   - **Universe B:** watchlist + promoted symbols
4. Compare metrics: OOS Sharpe, max drawdown, hit rate, number of trades
5. Write `reports/s4_universe_comparison.json`

### Note on walk-forward window
The S4 backtest default uses `in_sample_days=1260`. With only 90 days of signal data, we override to `in_sample_days=45, out_of_sample_days=45` (rolling 45-day windows). Results will be directional, not statistically conclusive — this is explicitly noted in the output.

---

## Step 4 — Decision Output

`compare_s4_universes.py` prints a final recommendation:

```
RECOMMENDATION: add [X, Y] to watchlist
  IC_24h ≥ 0.15         ✓
  ICIR_24h ≥ 2.0        ✓
  OOS Sharpe B > A      ✓  (0.xx vs 0.xx)

ACTION REQUIRED: manually add symbols to config/trading.yaml
```

The script never writes `trading.yaml` — the final decision is always manual.

---

## Architecture Notes

- Both scripts are standalone (no new modules introduced). They reuse:
  - `AlpacaNewsConnector.fetch_historical()`
  - `process_news_batch()` from `src/workers/sentiment.py`
  - `run_s4_backtest_from_prices_and_signals()` from `src/strategies/s4/backtest.py`
  - `compute_ic_report()` from the existing IC pipeline
- No changes to production code (pg_store, execution worker, etc.)
- Idempotent: re-running with same `run_id` relies on `ON CONFLICT ON CONSTRAINT idx_backtest_signals_dedup DO NOTHING` — unique index is `(run_id, symbol, article_url, generated_at)`

---

## Out of Scope

- Automated watchlist updates (always manual)
- Real-time signal infrastructure changes for new symbols
- Crypto or non-US symbols
