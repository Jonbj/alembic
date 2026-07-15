# S1 Momentum Refinements Implementation Plan

> **Status (2026-07-15):** All tasks implemented and tested on branch `s1-refinements-2026-07-12` (NOT merged — by design, awaiting operator review of the variants-comparison report + flag-flip decision). Checkboxes below reflect implementation status, not merge status.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (or superpowers:subagent-driven-development) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add three flag-gated refinements to the S1 Time-Series Momentum strategy — skip-month lookbacks, absolute-momentum filter, cap-after-normalization sizing — plus doc fixes and a variants-comparison backtest, WITHOUT changing live behavior (all flags default to current behavior).

**Architecture:** All changes live in `src/strategies/s1/` (signal.py, strategy.py, config.py) behind three new `S1Config` fields. A new standalone script runs the walk-forward backtest for 5 config variants and writes a comparison report. Live keeps running the baseline until a human reviews the report and flips flags.

**Tech Stack:** Python 3.11, pandas/numpy, pytest (`.venv/bin/pytest`). Live stack is Docker Compose but **no deploy is needed for this plan** (defaults preserve behavior; nothing merges to main).

---

## Context (read before Task 1)

Read `CLAUDE.md` first. S1 is a multi-lookback vol-normalized momentum strategy with
cross-sectional z-scoring (`docs/strategies.md` §S1 — which contains doc/code drift you
will fix in Task 1). Motivating findings (2026-07-11/12 analysis):

- The final signal correlates 0.31 with the raw last-21-day return — short-term
  reversal contaminates the momentum signal. Classic fix: skip the most recent month
  (Jegadeesh-Titman "12-2" style construction).
- The selection threshold applies to the cross-sectional **z-score**, so ~half the
  universe is always long (42/94 on 2026-07-11) regardless of market direction. An
  **absolute** momentum gate (raw vol-normalized momentum > 0) prevents bear-market
  "least-bad" longs. Today it would exclude 0 names — it is tail-risk insurance.
- Inverse-vol sizing (`weight = target_vol/vol` capped at `max_weight=0.20`) caps 67%
  of names, then sleeve normalization flattens weights (max/min ≈ 2.2) — the cap
  applied BEFORE normalization destroys most of the inverse-vol differentiation.

Constraints:
- Work on branch `s1-refinements-2026-07-12` off `main`. Do NOT merge to main, do NOT
  deploy, do NOT change `config/trading.yaml` or `config/strategies.yaml`.
- All new flags default to CURRENT behavior. A dedicated regression test per task
  proves default-config output is unchanged.
- Strict TDD: failing test first, watch it fail, minimal code, watch it pass.
- Full suite must end green except the 10 known pre-existing failures:
  5 in `tests/api/test_weight_approval.py`, 3 in `tests/workers/test_sec_edgar_ingestion.py`,
  2 in `tests/workers/test_sentiment_worker.py::TestEnsembleWeightReading`.

---

### Task 1: Fix doc drift in docs/strategies.md (§S1)

**Files:**
- Modify: `docs/strategies.md` (S1 section, starts ~line 22)

- [x] **Step 1: Fix the three drift points**

(a) The Sizing bullet reads `raw_weight ∝ signal × (target_vol / realised_vol)`.
The code (`src/strategies/s1/sizing.py::compute_weights`) does NOT multiply by the
signal — the signal only gates selection. Replace the bullet with:

```markdown
- `raw_weight = target_vol / realised_vol`, capped at `max_weight` — inverse-vol
  sizing; the momentum signal gates selection (signal > threshold) but does not
  scale the weight
```

(b) The Key Parameters table lists `target_vol` default `0.15`; the code default
(`S1Config.target_vol`, `src/strategies/s1/strategy.py`) is `0.10`. Change to `0.10`.

(c) Add one line under Integration documenting actual rebalance behavior:

```markdown
> **Rebalance cadence note:** `rebalance_frequency` is MONTHLY in config, but the live
> scheduler builds a fresh strategy instance every 15-min cycle (`_last_rebalance=None`
> → gate always passes), so S1 effectively re-targets continuously; churn is contained
> by the orchestrator's 2% delta band and the anti-churn hysteresis in trading.yaml.
```

> **Disambiguation (added 2026-07-13, after commit 22c8fe5/F6a):** there are TWO
> distinct `target_vol` in this system. (1) `S1Config.target_vol` = per-position
> inverse-vol sizing input (code default 0.10) — THIS is what the doc fix above
> refers to. (2) The PORTFOLIO-level `PortfolioVolTargeter` target_vol, now
> config-driven via the new `vol_target:` section in `config/trading.yaml` (F6a)
> — do NOT touch that section or conflate the two when fixing the docs.

- [x] **Step 2: Commit**

```bash
git add docs/strategies.md
git commit -m "docs(s1): fix sizing formula, target_vol default, rebalance cadence drift"
```

---

### Task 2: Skip-month lookbacks (`skip_days`)

**Files:**
- Modify: `src/strategies/s1/signal.py` (`compute_signal`, `generate_signals`)
- Modify: `src/strategies/s1/strategy.py` (`S1Config` — the dataclass lives HERE, not in a config.py — plus `from_yaml` and the pass-through in `TimeSeriesMomentum.__init__`)
- Test: `tests/strategies/test_s1_signal.py`

- [x] **Step 1: Write the failing tests**

Add to `tests/strategies/test_s1_signal.py` inside `class TestComputeSignal` (reuse the
existing `trending_prices` fixture; it has columns A, B, C):

```python
    def test_skip_days_zero_is_identical_to_default(self, trending_prices: pd.DataFrame) -> None:
        """skip_days=0 (the default) must reproduce current behavior exactly."""
        base = compute_signal(trending_prices)
        explicit = compute_signal(trending_prices, skip_days=0)
        pd.testing.assert_frame_equal(base, explicit)

    def test_skip_days_ignores_last_month_crash(self, trending_prices: pd.DataFrame) -> None:
        """A crash confined to the last 21 days must not degrade the signal when
        skip_days=21 (the window ends at t-21), but must degrade it when skip_days=0."""
        prices = trending_prices.copy()
        # A crashes 40% over the last 21 rows only; long-horizon trend untouched.
        crash = np.linspace(1.0, 0.6, 21)
        prices.iloc[-21:, prices.columns.get_loc("A")] *= crash

        with_skip = compute_signal(prices, skip_days=21)
        without_skip = compute_signal(prices, skip_days=0)

        a_with = with_skip[with_skip["ticker"] == "A"].iloc[-1]["signal"]
        a_without = without_skip[without_skip["ticker"] == "A"].iloc[-1]["signal"]
        assert a_with > a_without, "skip_days=21 must shield the signal from a last-month crash"

    def test_skip_days_drops_degenerate_legs(self, trending_prices: pd.DataFrame) -> None:
        """Lookbacks <= skip_days have an empty window and must be dropped, not crash."""
        result = compute_signal(trending_prices, lookbacks=(21, 252), skip_days=21)
        assert not result.empty  # the 252 leg alone still produces a signal
```

- [x] **Step 2: Run to verify they fail**

Run: `.venv/bin/pytest tests/strategies/test_s1_signal.py -q -k "skip_days"`
Expected: FAIL with `TypeError: compute_signal() got an unexpected keyword argument 'skip_days'`

- [x] **Step 3: Implement in signal.py**

In `src/strategies/s1/signal.py::compute_signal`, add the parameter as the LAST
one in the signature (so no existing positional call breaks):

```python
    skip_days: int = 0,
```

Document it in the docstring:

```python
        skip_days: Skip the most recent N trading days when computing each
            lookback return (window becomes [t-lb, t-skip]). 0 = classic
            construction including the last month. 21 ≈ Jegadeesh-Titman
            skip-month, which removes short-term-reversal contamination
            (measured corr(signal, 21d return) = 0.31 with skip_days=0).
            Lookbacks <= skip_days are dropped and remaining leg weights
            renormalized.
```

Replace the accumulation loop:

```python
    for lb, w in zip(lookbacks, weights):
        lb_ret = prices / prices.shift(lb) - 1
        vol_norm = lb_ret / rolling_vol
        signal_raw += w * vol_norm.fillna(0.0)
        nan_mask |= vol_norm.isna()
```

with:

```python
    used = [(lb, w) for lb, w in zip(lookbacks, weights) if lb > skip_days]
    if not used:
        return pd.DataFrame(columns=["ticker", "as_of", "signal"])
    w_total = sum(w for _, w in used)
    for lb, w in used:
        # Window [t-lb, t-skip]: with skip_days=0 this is the classic
        # prices / prices.shift(lb) (shift(0) is the identity).
        lb_ret = prices.shift(skip_days) / prices.shift(lb) - 1
        vol_norm = lb_ret / rolling_vol
        signal_raw += (w / w_total) * vol_norm.fillna(0.0)
        nan_mask |= vol_norm.isna()
```

- [x] **Step 4: Thread the parameter through**

In `generate_signals` (same file): add `skip_days: int = 0` to the signature, document
it ("Passed to compute_signal"), and pass it in the `compute_signal(...)` call
(which uses keyword-style args after the recent `min_observation_ratio` change — match
the existing call style).

In `src/strategies/s1/strategy.py`:
- `S1Config` gains `skip_days: int = 0` (after `lookbacks`).
- `S1Config.from_yaml` gains `skip_days=int(data.get("skip_days", 0)),`.
- `TimeSeriesMomentum.__init__` passes `skip_days=config.skip_days` in its
  `generate_signals(...)` call.

- [x] **Step 5: Run the tests**

Run: `.venv/bin/pytest tests/strategies/test_s1_signal.py tests/strategies/test_s1_strategy.py -q`
Expected: all PASS (the skip_days=0 identity test proves no behavior change).

- [x] **Step 6: Commit**

```bash
git add src/strategies/s1/signal.py src/strategies/s1/strategy.py tests/strategies/test_s1_signal.py
git commit -m "feat(s1): flag-gated skip-month lookback construction (skip_days, default 0 = unchanged)"
```

---

### Task 3: Absolute-momentum filter (`absolute_filter`)

**Files:**
- Modify: `src/strategies/s1/signal.py` (export pre-z-score value as `signal_abs`)
- Modify: `src/strategies/s1/strategy.py` (`S1Config`, `__init__` pivot, `compute_target_weights` gate)
- Test: `tests/strategies/test_s1_signal.py`, `tests/strategies/test_s1_strategy.py`

- [x] **Step 1: Write the failing signal-level test**

Add to `tests/strategies/test_s1_signal.py::TestComputeSignal`:

```python
    def test_signal_abs_column_distinguishes_relative_from_absolute(
        self, trending_prices: pd.DataFrame
    ) -> None:
        """compute_signal exports the pre-z-score momentum as signal_abs.
        In an all-uptrend panel every absolute momentum is positive, while
        z-scores are centered (someone must be below the cross-sectional mean)."""
        result = compute_signal(trending_prices)
        assert "signal_abs" in result.columns
        last = result[result["as_of"] == result["as_of"].max()]
        assert (last["signal_abs"] > 0).all()
        assert (last["signal"] < 0).any()
```

- [x] **Step 2: Run to verify it fails**

Run: `.venv/bin/pytest tests/strategies/test_s1_signal.py -q -k "signal_abs"`
Expected: FAIL with `KeyError`/assert on missing `signal_abs` column.

- [x] **Step 3: Export signal_abs from compute_signal**

In `compute_signal`, the tail currently is:

```python
    signal_zscored = signal_raw.sub(cross_mean, axis=0).div(cross_std, axis=0)

    # Reshape to long format
    long_df = signal_zscored.stack().reset_index()
    long_df.columns = ["as_of", "ticker", "signal"]
    long_df = long_df.dropna(subset=["signal"])

    return long_df[["ticker", "as_of", "signal"]].reset_index(drop=True)
```

Replace with:

```python
    signal_zscored = signal_raw.sub(cross_mean, axis=0).div(cross_std, axis=0)

    # Reshape to long format; keep the pre-z-score value as the ABSOLUTE
    # momentum (signal_abs) so callers can apply a dual-momentum gate —
    # the z-score alone always ranks ~half the universe positive, even in
    # a bear market.
    long_z = signal_zscored.stack().reset_index()
    long_z.columns = ["as_of", "ticker", "signal"]
    long_abs = signal_raw.stack().reset_index()
    long_abs.columns = ["as_of", "ticker", "signal_abs"]
    long_df = long_z.merge(long_abs, on=["as_of", "ticker"], how="left")
    long_df = long_df.dropna(subset=["signal"])

    return long_df[["ticker", "as_of", "signal", "signal_abs"]].reset_index(drop=True)
```

Also update the two early-return empty frames in this function (the `len(keep_tickers) < 2`
return and the Task-2 `if not used` return) to
`pd.DataFrame(columns=["ticker", "as_of", "signal", "signal_abs"])`.

Run the Step-1 test: PASS. Run the whole file: `test_skip_days_zero_is_identical_to_default`
still passes (both frames carry the new column). If any existing test asserts the exact
column list, update it to include `signal_abs`.

- [x] **Step 4: Write the failing strategy-level test**

Add to `tests/strategies/test_s1_strategy.py`:

```python
class TestAbsoluteFilter:
    def _bear_panel(self) -> pd.DataFrame:
        # Everything falls; A falls least → A has a POSITIVE z-score but a
        # NEGATIVE absolute momentum. The classic "least bad long" trap.
        idx = pd.date_range("2023-01-02", periods=400, freq="B")
        rng = np.random.default_rng(11)
        data = {}
        for i, drift in enumerate([-0.0002, -0.0010, -0.0012, -0.0014, -0.0016]):
            noise = rng.normal(0, 0.008, len(idx))
            data[f"T{i}"] = 100 * np.exp(np.cumsum(drift + noise))
        return pd.DataFrame(data, index=idx)

    def test_default_config_longs_the_least_bad_name(self) -> None:
        prices = self._bear_panel()
        strat = TimeSeriesMomentum(prices, S1Config())
        weights = strat.compute_target_weights(prices)
        assert "T0" in weights, "baseline (relative-only) longs the least-bad name"

    def test_absolute_filter_blocks_negative_momentum_longs(self) -> None:
        prices = self._bear_panel()
        strat = TimeSeriesMomentum(prices, S1Config(absolute_filter=True))
        weights = strat.compute_target_weights(prices)
        assert weights == {}, "dual momentum must not long names with negative absolute momentum"
```

Note: if `test_default_config_longs_the_least_bad_name` fails because T0's z-score does
not clear threshold with seed 11, adjust the drift spread (make T0 `-0.0001` and the
others more negative) until the baseline test passes BEFORE implementing — it documents
current behavior and must be green pre-change; only the second test is the RED one.

- [x] **Step 5: Run to verify RED**

Run: `.venv/bin/pytest tests/strategies/test_s1_strategy.py::TestAbsoluteFilter -q`
Expected: first test PASS, second FAIL with `TypeError: S1Config.__init__() got an
unexpected keyword argument 'absolute_filter'`.

- [x] **Step 6: Implement**

In `src/strategies/s1/strategy.py`:

(a) `S1Config` gains (after `signal_threshold`):

```python
    # Dual momentum: additionally require the pre-z-score (absolute) momentum
    # to be positive. Off by default: flipping it is a backtest-gated decision.
    absolute_filter: bool = False
```

and `from_yaml` gains `absolute_filter=bool(data.get("absolute_filter", False)),`.

(b) In `TimeSeriesMomentum.__init__`, next to the existing `_signal_wide`/`_weight_wide`
pivots add:

```python
            self._abs_wide: pd.DataFrame | None = (
                self._combined.pivot(index="as_of", columns="ticker", values="signal_abs")
                if "signal_abs" in self._combined.columns
                else None
            )
```

and in the `else` (empty) branch: `self._abs_wide = None`.

(c) In `compute_target_weights`, after `lookup_date` is resolved and before the
weights dict is built:

```python
        abs_row = None
        if self._config.absolute_filter:
            if self._abs_wide is not None and lookup_date in self._abs_wide.index:
                abs_row = self._abs_wide.loc[lookup_date]
            else:
                # Fail-open: absolute data unavailable → relative-only behavior.
                log.warning("S1 absolute_filter on but signal_abs unavailable — filter skipped")
```

and add one condition to the dict-comprehension filter (after the
`signals_row[ticker] > threshold` line):

```python
                and (abs_row is None or (pd.notna(abs_row[ticker]) and abs_row[ticker] > 0.0))
```

- [x] **Step 7: Run the tests**

Run: `.venv/bin/pytest tests/strategies/test_s1_strategy.py tests/strategies/test_s1_signal.py -q`
Expected: all PASS.

- [x] **Step 8: Commit**

```bash
git add src/strategies/s1/signal.py src/strategies/s1/strategy.py tests/strategies/test_s1_signal.py tests/strategies/test_s1_strategy.py
git commit -m "feat(s1): flag-gated absolute-momentum filter (dual momentum, default off)"
```

---

### Task 4: Cap AFTER normalization (`cap_after_normalization`)

**Files:**
- Modify: `src/strategies/s1/strategy.py` (`S1Config`, `__init__`, `compute_target_weights`)
- Test: `tests/strategies/test_s1_strategy.py`

- [x] **Step 1: Write the failing test**

Add to `tests/strategies/test_s1_strategy.py` (mirror the synthetic-panel style of the
existing `TestSleeveNormalization`):

```python
class TestCapAfterNormalization:
    def _hetero_vol_panel(self) -> pd.DataFrame:
        # 16 uptrending tickers with very different vols: inverse-vol sizing
        # should differentiate them, but the pre-normalization 0.20 cap binds
        # for most names and flattens the sleeve.
        idx = pd.date_range("2023-01-02", periods=400, freq="B")
        rng = np.random.default_rng(5)
        data = {}
        for i in range(16):
            vol = 0.006 + 0.002 * i          # daily vol from 0.6% to 3.6%
            noise = rng.normal(0, vol, len(idx))
            data[f"T{i:02d}"] = 100 * np.exp(np.cumsum(0.0010 + noise))
        return pd.DataFrame(data, index=idx)

    def test_flag_off_preserves_current_behavior(self) -> None:
        prices = self._hetero_vol_panel()
        base = TimeSeriesMomentum(prices, S1Config()).compute_target_weights(prices)
        explicit = TimeSeriesMomentum(
            prices, S1Config(cap_after_normalization=False)
        ).compute_target_weights(prices)
        assert base == explicit

    def test_cap_after_normalization_restores_differentiation(self) -> None:
        prices = self._hetero_vol_panel()
        flat = TimeSeriesMomentum(prices, S1Config()).compute_target_weights(prices)
        diff = TimeSeriesMomentum(
            prices, S1Config(cap_after_normalization=True)
        ).compute_target_weights(prices)

        assert diff, "expected non-empty weights"
        assert sum(diff.values()) <= 1.0 + 1e-9
        assert max(diff.values()) <= S1Config().max_weight + 1e-9
        # Differentiation must strictly increase vs the flattened baseline.
        import numpy as np
        spread = lambda w: np.std(list(w.values())) / np.mean(list(w.values()))
        assert spread(diff) > spread(flat) * 1.5
```

- [x] **Step 2: Run to verify RED**

Run: `.venv/bin/pytest tests/strategies/test_s1_strategy.py::TestCapAfterNormalization -q`
Expected: FAIL with `TypeError: ... unexpected keyword argument 'cap_after_normalization'`.

- [x] **Step 3: Implement**

(a) `S1Config` gains:

```python
    # When True: inverse-vol weights are normalized to sum 1.0 FIRST and the
    # max_weight concentration cap is applied AFTER (with one redistribution
    # pass). The legacy order (cap in sizing.py, then normalize) leaves ~2/3
    # of names at the cap and flattens the sleeve to near-equal-weight.
    cap_after_normalization: bool = False
```

plus `from_yaml`: `cap_after_normalization=bool(data.get("cap_after_normalization", False)),`.

(b) In `TimeSeriesMomentum.__init__`, the `generate_signals(...)` call passes
`max_weight=1.0 if config.cap_after_normalization else config.max_weight` so the
upstream sizing cap is disabled in the new mode (a comment explaining why belongs
here). `S1Config.max_weight` keeps its meaning as the post-normalization cap.

(c) In `compute_target_weights`, replace the sleeve-normalization tail

```python
        total = sum(weights.values())
        if total > 1.0:
            weights = {t: w / total for t, w in weights.items()}
        return weights
```

with:

```python
        total = sum(weights.values())
        if self._config.cap_after_normalization and total > 0:
            # Normalize first so inverse-vol ordering survives, THEN cap for
            # concentration; redistribute the capped excess once across names
            # with headroom (second-order residue is left as cash).
            cap = self._config.max_weight
            weights = {t: w / total for t, w in weights.items()}
            capped = {t: min(w, cap) for t, w in weights.items()}
            excess = 1.0 - sum(capped.values())
            headroom = {t: cap - w for t, w in capped.items() if cap - w > 1e-12}
            hr_total = sum(headroom.values())
            if excess > 1e-12 and hr_total > 1e-12:
                for t, hr in headroom.items():
                    capped[t] = min(cap, capped[t] + excess * hr / hr_total)
            return capped
        if total > 1.0:
            weights = {t: w / total for t, w in weights.items()}
        return weights
```

- [x] **Step 4: Run the tests**

Run: `.venv/bin/pytest tests/strategies/test_s1_strategy.py tests/strategies/test_s1_signal.py tests/strategies/test_s1_backtest.py tests/strategies/test_s1_rebalance.py tests/strategies/test_s1_sensitivity.py -q`
Expected: all PASS.

- [x] **Step 5: Commit**

```bash
git add src/strategies/s1/strategy.py tests/strategies/test_s1_strategy.py
git commit -m "feat(s1): flag-gated cap-after-normalization sizing (default off = current flattened behavior)"
```

---

### Task 5: Variants-comparison backtest script + report

**Files:**
- Create: `scripts/compare_s1_variants.py`
- Output: `reports/s1_variants/comparison_<date>.md` (gitignored dir is fine; commit the script only)

- [x] **Step 1: Read the backtest entry point**

Read `src/strategies/s1/backtest.py` fully. You will reuse
`run_s1_backtest_from_prices(prices, output_dir=..., wf_config=..., s1_config=...,
run_robustness=False)` which returns a dict containing `oos_sharpe` and
`milestone_b_pass`. Mirror ITS import for `WalkForwardConfig` (check the file header
for where it imports it from — do not guess).

- [x] **Step 2: Write the script**

Create `scripts/compare_s1_variants.py`:

```python
"""Compare S1 config variants on the same price panel (relative comparison only).

Runs the walk-forward backtest for 5 variants and writes a markdown table.
KNOWN LIMITS (P0-01): same-bar fills, no costs, survivorship-lite universe, and the
sparse-ticker filter uses full-window stats (look-ahead in ticker selection) — treat
results as RELATIVE evidence between variants, never as absolute validation.

Run inside the worker container (Alpaca keys live there):
    docker cp scripts/compare_s1_variants.py alembic-worker-1:/tmp/
    docker exec alembic-worker-1 python /tmp/compare_s1_variants.py
"""
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.data.enums import DataFeed, Adjustment

from src.config import config
from src.strategies.s1.strategy import S1Config

_LOOKBACK_DAYS = 2500  # calendar days of history (~6.8y): enough for IS 504 + OOS 126 windows

_VARIANTS: dict[str, S1Config] = {
    "baseline": S1Config(),
    "skip21": S1Config(lookbacks=(63, 126, 252), skip_days=21),
    "absfilter": S1Config(absolute_filter=True),
    "skip21+abs": S1Config(lookbacks=(63, 126, 252), skip_days=21, absolute_filter=True),
    "skip21+abs+capafter": S1Config(
        lookbacks=(63, 126, 252), skip_days=21,
        absolute_filter=True, cap_after_normalization=True,
    ),
}


def _fetch_panel():
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=_LOOKBACK_DAYS)
    client = StockHistoricalDataClient(
        api_key=config.ALPACA_API_KEY, secret_key=config.ALPACA_SECRET_KEY
    )
    req = StockBarsRequest(
        symbol_or_symbols=list(config.WATCHLIST_SYMBOLS),
        timeframe=TimeFrame.Day, start=start, end=end,
        feed=DataFeed.IEX, adjustment=Adjustment.ALL,
    )
    raw = client.get_stock_bars(req).df.reset_index()
    return raw.pivot(index="timestamp", columns="symbol", values="close")


def main() -> int:
    from src.strategies.s1.backtest import run_s1_backtest_from_prices
    # WalkForwardConfig: import from the same module backtest.py imports it from.
    from src.strategies.s1.backtest import WalkForwardConfig  # adjust if backtest.py sources it elsewhere

    prices = _fetch_panel()
    print(f"panel: {prices.shape[0]} rows x {prices.shape[1]} symbols "
          f"({prices.index[0].date()} → {prices.index[-1].date()})")

    wf = WalkForwardConfig(in_sample_days=504, out_of_sample_days=126)
    rows = []
    for name, cfg in _VARIANTS.items():
        print(f"=== variant: {name} ===")
        try:
            res = run_s1_backtest_from_prices(
                prices,
                output_dir=Path(f"/tmp/s1_variants/{name}"),
                wf_config=wf,
                s1_config=cfg,
                run_robustness=False,
            )
            rows.append((name, res.get("oos_sharpe"), res.get("milestone_b_pass")))
        except Exception as exc:
            print(f"variant {name} FAILED: {exc}")
            rows.append((name, None, None))

    out_dir = Path("reports/s1_variants")
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"comparison_{datetime.now(timezone.utc).date()}.md"
    with open(out, "w") as f:
        f.write("# S1 variants comparison (relative evidence only — see P0-01 limits)\n\n")
        f.write(f"Panel: {prices.shape[0]} rows × {prices.shape[1]} symbols, "
                f"{prices.index[0].date()} → {prices.index[-1].date()}; "
                f"WF: IS 504d / OOS 126d; costs NOT modeled.\n\n")
        f.write("| variant | OOS Sharpe | milestone B |\n|---|---|---|\n")
        for name, sharpe, mb in rows:
            f.write(f"| {name} | {sharpe if sharpe is None else f'{sharpe:.3f}'} | {mb} |\n")
    print(f"report → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

If the `WalkForwardConfig` import fails, open `src/strategies/s1/backtest.py`, find its
real source module, and fix the import — do not reimplement the class.

- [x] **Step 3: Run it in the container**

```bash
docker cp scripts/compare_s1_variants.py alembic-worker-1:/tmp/compare_s1_variants.py
docker exec alembic-worker-1 python /tmp/compare_s1_variants.py
docker cp alembic-worker-1:/app/reports/s1_variants/. reports/s1_variants/ 2>/dev/null || true
```

Note: the report writes relative to the container CWD (`/app`); the `docker cp` pulls it
back. Expected runtime: minutes (5 variants × walk-forward, robustness off). If a
variant errors with insufficient history for the WF windows, reduce to
`WalkForwardConfig(in_sample_days=378, out_of_sample_days=126)` and note it in the report.

- [x] **Step 4: Commit the script and echo the table**

```bash
git add scripts/compare_s1_variants.py
git commit -m "feat(s1): variants-comparison backtest script (baseline vs skip-month/abs-filter/cap-after)"
```

Paste the resulting comparison table into your final report.

---

### Task 6: Full suite + wrap-up

- [x] **Step 1:** `.venv/bin/pytest -q` → only the 10 known pre-existing failures
(listed in Context) are allowed. Fix any other regression before finishing.

- [x] **Step 2:** Final report: branch name, commits, test counts, the variants table
from Task 5, and an explicit statement that live behavior is unchanged (all flags off)
and that flag flips + merge are operator decisions pending the comparison review.

---

## Self-review checklist (implementer)

- Every behavior change has a test that failed first, plus a default-config
  regression test proving live behavior is untouched.
- No changes outside `src/strategies/s1/`, `scripts/`, `docs/strategies.md`, `tests/strategies/`.
- No merge to main, no deploy, no config/trading.yaml or strategies.yaml edits.
