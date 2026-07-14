# Capital Deployment Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore capital deployment by fixing the four independent chokepoints found in the 2026-07-09 forensic analysis: S1 (50% sleeve) silently dead since 2026-06-01, loss-feedback threshold pinned near max by an asymmetric ratchet, S4 ranker discarding lone survivors, and no alerting when an enabled strategy goes silent.

**Architecture:** All fixes are surgical changes to existing modules — no new subsystems. S1's cross-sectional signal gains a per-ticker validity filter (partially done, uncommitted) and sleeve-sum normalization; the portfolio scheduler gains a zero-weight watchdog; the loss-feedback Celery task gains a relative (equity-scaled) trigger and time-decay recovery; S4's `min_stocks` drops to 1.

**Tech Stack:** Python 3.11, Celery workers, Redis, PostgreSQL, Alpaca SDK (paper), pytest. Tests run locally via `.venv/bin/pytest`. Live stack runs in Docker Compose (`alembic-*` containers); `src/` is **baked into the images, not bind-mounted** — deploying requires `docker compose build`.

---

## Context you need (read this first)

The system is an LLM-driven trading system ("Alpha Miner"): background workers compute sentiment signals, a portfolio scheduler (`src/workers/portfolio_scheduler.py`, Celery task `run_portfolio_cycle`, every 15 min during US market hours) merges per-strategy target weights and submits delta orders to Alpaca paper trading. Read `CLAUDE.md` at the repo root before starting.

Forensic findings this plan fixes (measured on the live stack 2026-07-09, account $110K, deployment 0.0%):

1. **S1 dead** — `src/strategies/s1/signal.py::compute_signal` kept only price-panel rows where **all** ~96 watchlist tickers had valid signals. AZN (IEX bars only since 2026-02-02: 109/409) and SPCX (18/409 bars) poisoned every row → `generate_signals` empty → S1 returned `{}` silently every cycle since 2026-06-01. **A fix is already in the working tree, uncommitted, tests passing** (Task 1 verifies and commits it).
2. **Loss-feedback ratchet asymmetry** — `src/workers/performance.py::run_loss_feedback_check` raises the S4 entry threshold (0.30 baseline → up to 0.60) whenever the rolling 10-trade P&L is negative **by any amount** (a -$208 blip on $110K equity re-pinned it at 0.55 on 2026-07-09), every 4h; recovery needs 3 *consecutive* wins, nearly impossible at 2-6 tiny trades/day. Tasks 4-5 make the trigger relative to equity and add time-decay.
3. **S4 `min_stocks=2`** — with the threshold high, the rare surviving signal is discarded because the ranker refuses to build a 1-name bucket. Task 6 lowers it to 1.
4. **Silent failure** — nothing alerts when an enabled strategy produces 0 target weights for days/weeks. Task 3 adds a watchdog.

**Explicitly OUT OF SCOPE (product-owner decisions, do not touch):** `config/strategies.yaml` allocations (S1 0.50 / S4 0.10), `risk.max_portfolio_exposure: 0.50` and `risk.max_position_pct: 0.10` in `config/trading.yaml`, the regime multiplier logic, switching the price feed from IEX to SIP, adding a 3rd ensemble model. Do not enable S2/S3/S7.

Useful live-stack facts: Postgres → `docker exec alembic-postgres-1 psql -U trading -d trading`; Redis → `docker exec alembic-redis-1 redis-cli`; worker logs → `docker logs alembic-worker-1`. Market hours ≈ 13:30–20:00 UTC Mon–Fri.

---

### Task 1: Verify and commit the in-progress S1 sparse-ticker fix

The working tree already contains the fix (parameter `min_observation_ratio: float = 0.75` in `compute_signal`/`generate_signals`: tickers with <75% non-NaN signal observations are dropped from the panel instead of invalidating every row) and two tests. Your job is to verify and commit it — do not rewrite it.

**Files:**
- Already modified (uncommitted): `src/strategies/s1/signal.py`
- Already modified (uncommitted): `tests/strategies/test_s1_signal.py`

- [ ] **Step 1: Inspect the pending diff**

Run: `git diff src/strategies/s1/signal.py tests/strategies/test_s1_signal.py`
Expected: `min_observation_ratio` parameter, a sparse-ticker drop block with `log.warning`, and two new tests (`test_sparse_ticker_does_not_poison_panel`, `test_all_sparse_tickers_return_empty`).

- [ ] **Step 2: Run the S1 test files**

Run: `.venv/bin/pytest tests/strategies/test_s1_signal.py tests/strategies/test_s1_strategy.py tests/strategies/test_s1_backtest.py tests/strategies/test_s1_rebalance.py -q`
Expected: all PASS (test_s1_signal.py alone was 21 passed as of 2026-07-10).

- [ ] **Step 3: Commit**

```bash
git add src/strategies/s1/signal.py tests/strategies/test_s1_signal.py
git commit -m "fix(s1): drop sparse tickers instead of poisoning the whole cross-sectional panel

AZN (IEX coverage only since 2026-02) and SPCX (18/409 bars) made the
all-tickers-valid row filter reject every date, so S1 produced zero target
weights every cycle since 2026-06-01. Tickers below a 75% observation ratio
are now dropped per-ticker with a WARNING log."
```

---

### Task 2: Normalize S1 sleeve weights to sum ≤ 1.0

`config/strategies.yaml` documents the sleeve contract: *"Weights produced by compute_target_weights() are sleeve-local (sum ≤ 1.0 within the sleeve)"*. S1 violates it: each name gets an inverse-vol weight capped at `max_weight=0.20`, with no cap on the sum. With S1 revived, ~41 names × 0.2 = 8.2 sleeve-local (×0.50 allocation = 4.1× NAV of BUY targets). The `ConstraintEnforcer` would scale that down to the 50% exposure cap, but it would also proportionally crush S4's contribution in the same pass. Fix at the source.

**Files:**
- Modify: `src/strategies/s1/strategy.py:113-122` (the return of `compute_target_weights`)
- Test: `tests/strategies/test_s1_strategy.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/strategies/test_s1_strategy.py` (reuse the file's existing imports — it already imports `pd`, `np`, `TimeSeriesMomentum`, `S1Config`; add any that are missing):

```python
class TestSleeveNormalization:
    def test_weights_sum_capped_at_one(self) -> None:
        # 16 uptrending tickers → the cross-sectional z-score puts roughly half
        # above the mean (positive signal), each inverse-vol weight capped at
        # max_weight=0.20 → the sleeve sum lands well above 1.0 without
        # normalization (portfolio over-allocation before the enforcer).
        idx = pd.date_range("2023-01-02", periods=400, freq="B")
        rng = np.random.default_rng(7)
        data = {}
        for i in range(16):
            drift = 0.0008 + 0.0002 * i
            noise = rng.normal(0, 0.01, len(idx))
            data[f"T{i:02d}"] = 100 * np.exp(np.cumsum(drift + noise))
        prices = pd.DataFrame(data, index=idx)

        strat = TimeSeriesMomentum(prices=prices, config=S1Config())
        weights = strat.compute_target_weights(prices)

        assert weights, "expected non-empty target weights"
        assert sum(weights.values()) <= 1.0 + 1e-9
        assert all(w > 0 for w in weights.values())
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/pytest tests/strategies/test_s1_strategy.py::TestSleeveNormalization -q`
Expected: FAIL — sum of weights > 1.0 (if it passes instead, the synthetic data produced too few positive signals: increase periods to 500 or drift values, and confirm the assert on non-empty weights holds).

- [ ] **Step 3: Implement the normalization**

In `src/strategies/s1/strategy.py`, `compute_target_weights` currently ends with:

```python
        return {
            ticker: float(weights_row[ticker])
            for ticker in signals_row.index
            if (
                pd.notna(signals_row[ticker])
                and pd.notna(weights_row[ticker])
                and signals_row[ticker] > threshold
                and (eligible is None or ticker in eligible)
            )
        }
```

Replace with:

```python
        weights = {
            ticker: float(weights_row[ticker])
            for ticker in signals_row.index
            if (
                pd.notna(signals_row[ticker])
                and pd.notna(weights_row[ticker])
                and signals_row[ticker] > threshold
                and (eligible is None or ticker in eligible)
            )
        }
        # Sleeve contract (config/strategies.yaml): sleeve-local weights must sum
        # to ≤ 1.0. Per-name inverse-vol weights are only capped individually
        # (max_weight), so with many qualifying names the sum can far exceed 1.
        total = sum(weights.values())
        if total > 1.0:
            weights = {t: w / total for t, w in weights.items()}
        return weights
```

- [ ] **Step 4: Run the S1 test files**

Run: `.venv/bin/pytest tests/strategies/test_s1_strategy.py tests/strategies/test_s1_signal.py tests/strategies/test_s1_backtest.py tests/strategies/test_s1_rebalance.py tests/strategies/test_s1_sensitivity.py -q`
Expected: all PASS. If an existing test asserts exact unnormalized weight values, inspect it: tests exercising few tickers (sum ≤ 1.0) are unaffected by design; only adjust a test if it deliberately constructs a >1.0 sum.

- [ ] **Step 5: Commit**

```bash
git add src/strategies/s1/strategy.py tests/strategies/test_s1_strategy.py
git commit -m "fix(s1): normalize sleeve weights to sum <= 1.0 per the sleeve contract"
```

---

### Task 3: Zero-target-weights watchdog in the portfolio scheduler

An enabled strategy that produces 0 target weights every cycle must page the operator instead of failing silently for five weeks. `CycleResult.orders_per_strategy` (from `src/portfolio/orchestrator.py`) already maps `strategy_id → number of target weights produced`.

**Files:**
- Modify: `src/workers/portfolio_scheduler.py` (new helper + call site after the cycle-complete log around line 1150)
- Test: create `tests/workers/test_zero_weights_watchdog.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/workers/test_zero_weights_watchdog.py`:

```python
"""Tests for the zero-target-weights watchdog in the portfolio scheduler."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from src.workers.portfolio_scheduler import (
    _ZERO_WEIGHT_ALERT_CYCLES,
    _track_zero_weight_strategies,
)


def test_zero_weights_increments_counter_no_alert_below_threshold():
    r = MagicMock()
    r.incr.return_value = 1
    with patch("src.workers.portfolio_scheduler._fire_alert") as alert:
        _track_zero_weight_strategies({"S1": 0}, r, notifier=MagicMock())
    r.incr.assert_called_once_with("monitor:zero_weights:S1")
    alert.assert_not_called()


def test_alert_fires_exactly_at_threshold():
    r = MagicMock()
    r.incr.return_value = _ZERO_WEIGHT_ALERT_CYCLES
    with patch("src.workers.portfolio_scheduler._fire_alert") as alert:
        _track_zero_weight_strategies({"S1": 0}, r, notifier=MagicMock())
    alert.assert_called_once()


def test_alert_repeats_at_threshold_multiples():
    r = MagicMock()
    r.incr.return_value = _ZERO_WEIGHT_ALERT_CYCLES * 2
    with patch("src.workers.portfolio_scheduler._fire_alert") as alert:
        _track_zero_weight_strategies({"S1": 0}, r, notifier=MagicMock())
    alert.assert_called_once()


def test_no_alert_between_threshold_multiples():
    r = MagicMock()
    r.incr.return_value = _ZERO_WEIGHT_ALERT_CYCLES + 1
    with patch("src.workers.portfolio_scheduler._fire_alert") as alert:
        _track_zero_weight_strategies({"S1": 0}, r, notifier=MagicMock())
    alert.assert_not_called()


def test_nonzero_weights_resets_counter():
    r = MagicMock()
    with patch("src.workers.portfolio_scheduler._fire_alert") as alert:
        _track_zero_weight_strategies({"S1": 5, "S4": 3}, r, notifier=MagicMock())
    assert r.delete.call_count == 2
    r.incr.assert_not_called()
    alert.assert_not_called()


def test_redis_error_does_not_raise():
    r = MagicMock()
    r.incr.side_effect = RuntimeError("redis down")
    _track_zero_weight_strategies({"S1": 0}, r, notifier=MagicMock())  # must not raise
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/pytest tests/workers/test_zero_weights_watchdog.py -q`
Expected: FAIL with `ImportError: cannot import name '_ZERO_WEIGHT_ALERT_CYCLES'`.

- [ ] **Step 3: Implement the watchdog helper**

In `src/workers/portfolio_scheduler.py`, add near the other module-level constants (there is `_PRICE_BARS = 300` around line 30):

```python
# Zero-weight watchdog: alert when an enabled strategy produced 0 target weights
# for this many consecutive cycles (~1 trading day at 15-min cadence). S1 was
# silently dead for 5 weeks (sparse-ticker panel poisoning) before this existed.
_ZERO_WEIGHT_ALERT_CYCLES = 24
```

Then add this function at module level (e.g. right after the `_fire_alert` definition, line ~150):

```python
def _track_zero_weight_strategies(
    orders_per_strategy: dict[str, int], redis_client, notifier
) -> None:
    """Count consecutive cycles in which each strategy produced 0 target weights.

    Increments monitor:zero_weights:{sid} on a zero-weight cycle, resets it on a
    productive one, and fires a WARNING alert at every _ZERO_WEIGHT_ALERT_CYCLES
    multiple. Never raises: monitoring must not break the trading cycle.
    """
    for sid, n_weights in orders_per_strategy.items():
        key = f"monitor:zero_weights:{sid}"
        try:
            if n_weights > 0:
                redis_client.delete(key)
                continue
            count = int(redis_client.incr(key))
            redis_client.expire(key, 7 * 86400)
            if count % _ZERO_WEIGHT_ALERT_CYCLES == 0:
                msg = (
                    f"⚠️ <b>Strategy {sid} silent for {count} consecutive cycles</b>\n\n"
                    f"{sid} is enabled but produced 0 target weights in each of the "
                    f"last {count} portfolio cycles (~{count // _ZERO_WEIGHT_ALERT_CYCLES} "
                    f"trading day(s)). Its capital sleeve is not being deployed. "
                    f"Check price-data coverage and signal filters."
                )
                _fire_alert(notifier, msg, AlertLevel.WARNING)
                log.warning(
                    "Zero-weight watchdog: %s produced 0 weights for %d consecutive cycles",
                    sid, count,
                )
        except Exception as exc:
            log.warning("Zero-weight watchdog failed for %s: %s", sid, exc)
```

- [ ] **Step 4: Wire the call site**

In `run_portfolio_cycle`, directly after the cycle-complete log block (the `log.info("Portfolio cycle: strategies=%s before=%d after=%d constraints=%d final=%d", ...)` call around line 1150, before the `_log_constraint_block_if_needed(result, _risk_cfg)` line), add:

```python
    # Zero-weight watchdog: page the operator when an enabled strategy has been
    # producing 0 target weights for a full trading day (silent-death detection).
    try:
        from redis import Redis as _RedisZW
        _r_zw = _RedisZW.from_url(config.REDIS_URL, decode_responses=True)
        try:
            _track_zero_weight_strategies(result.orders_per_strategy, _r_zw, notifier)
        finally:
            _r_zw.close()
    except Exception as _zw_exc:
        log.warning("Zero-weight watchdog error: %s — cycle continues", _zw_exc)
```

`notifier` is already in scope (created at line ~849). `AlertLevel` is already imported at the top of the file.

- [ ] **Step 5: Run the tests**

Run: `.venv/bin/pytest tests/workers/test_zero_weights_watchdog.py -q`
Expected: 6 passed.

- [ ] **Step 6: Commit**

```bash
git add src/workers/portfolio_scheduler.py tests/workers/test_zero_weights_watchdog.py
git commit -m "feat(monitoring): alert when an enabled strategy produces zero target weights for a full day"
```

---

### Task 4: Loss-feedback — make the rolling-P&L trigger relative to equity

`run_loss_feedback_check` currently escalates on `rolling_net_pnl < 0` — any rolling loss, even $1. Make it relative: trigger only when the rolling loss exceeds `rolling_pnl_trigger_pct` of account equity (read from the `portfolio:value` Redis key), falling back to an absolute floor when equity is unknown. Also make the portfolio scheduler write `portfolio:value` (today only the legacy execution worker writes it, and in `execution.engine=portfolio` mode that path may not run).

**Files:**
- Modify: `src/store/redis_store.py` (add `get_portfolio_value` next to `set_portfolio_value`, line ~667)
- Modify: `src/workers/performance.py` (`_load_loss_feedback_config` defaults ~line 1533; trigger logic ~line 1641; reason string ~line 1692)
- Modify: `src/workers/portfolio_scheduler.py` (write `portfolio:value` in the drawdown-cap block, line ~1042)
- Modify: `config/trading.yaml` (`loss_feedback` section)
- Test: `tests/workers/test_loss_feedback.py`

- [ ] **Step 1: Add the Redis getter**

In `src/store/redis_store.py`, right after `set_portfolio_value` (line ~667-669), add:

```python
    def get_portfolio_value(self) -> float | None:
        """Read cached portfolio equity (written each cycle); None if absent/invalid."""
        val = self._r.get("portfolio:value")
        try:
            return float(val) if val is not None else None
        except (TypeError, ValueError):
            return None
```

- [ ] **Step 2: Write `portfolio:value` from the portfolio scheduler**

In `src/workers/portfolio_scheduler.py`, inside the drawdown-cap block (the `try:` that creates `_r_dd` around line 1040), immediately after `_raw_peak = _r_dd.get(_PEAK_EQUITY_KEY)` reads and before the `if drawdown >= _dd_cap:` check, add one line (equity is already computed in scope):

```python
            # Cache equity for consumers that need account size (e.g. the
            # loss-feedback relative trigger). Legacy execution wrote this key;
            # in portfolio mode this is the authoritative writer.
            _r_dd.setex("portfolio:value", 86400, str(equity))
```

- [ ] **Step 3: Update config defaults and trading.yaml**

In `src/workers/performance.py::_load_loss_feedback_config` (~line 1533), the `defaults` dict currently contains keys like `consecutive_loss_trigger`, `rolling_pnl_window`, …, `feedback_ttl_hours`. Add two entries:

```python
        "rolling_pnl_trigger_pct": 0.005,
        "rolling_pnl_trigger_floor_usd": 250.0,
```

In `config/trading.yaml`, inside the `loss_feedback:` section, add:

```yaml
  # Relative rolling-P&L trigger (2026-07-10): a rolling loss must be material
  # relative to account size before it ratchets the entry threshold. A -$208
  # blip on $110K equity re-pinned the threshold at 0.55 on 2026-07-09.
  rolling_pnl_trigger_pct: 0.005        # trigger when rolling loss > 0.5% of equity
  rolling_pnl_trigger_floor_usd: 250.0  # used when equity is unknown in Redis
```

- [ ] **Step 4: Write the failing tests**

In `tests/workers/test_loss_feedback.py`:

(a) add the two new keys to the test-local `_default_cfg()` helper:

```python
        "rolling_pnl_trigger_pct": 0.005,
        "rolling_pnl_trigger_floor_usd": 250.0,
```

(b) extend `_patched_run` with an equity parameter — add `redis_equity: float | None = None` to its keyword args and, next to the other `mock_redis.*.return_value` lines:

```python
    mock_redis.get_portfolio_value.return_value = redis_equity
```

(This is mandatory even for old tests: an unset MagicMock return would make `equity * pct` a MagicMock and crash the comparison.)

(c) add the new test class:

```python
class TestRelativeRollingPnlTrigger:
    def test_small_rolling_loss_below_limit_does_not_trigger(self):
        # rolling −208 on 100K equity → limit is −500 → no trigger
        trades = _make_trades([-208, 40, 30, -20, -50])
        result, mock_redis = _patched_run(trades, redis_equity=100_000.0)
        assert result["triggered"] is False
        assert result["adjusted"] is False
        mock_redis.set_feedback_entry_threshold.assert_not_called()

    def test_large_rolling_loss_triggers(self):
        # rolling −600 on 100K equity → beyond the −500 limit → trigger
        trades = _make_trades([-600, 40, 30, -20, -50])
        result, _ = _patched_run(trades, redis_equity=100_000.0)
        assert result["triggered"] is True
        assert result["adjusted"] is True

    def test_floor_used_when_equity_missing(self):
        # equity unknown → floor $250 applies to the rolling SUM over the window:
        # sum(-400+40+30+10+5) = -315 triggers; sum(-200+40+30+10+5) = -115 does not
        result_hi, _ = _patched_run(_make_trades([-400, 40, 30, 10, 5]))
        assert result_hi["triggered"] is True
        result_lo, _ = _patched_run(_make_trades([-200, 40, 30, 10, 5]))
        assert result_lo["triggered"] is False

    def test_consecutive_losses_still_trigger_regardless_of_size(self):
        trades = _make_trades([-1, -1, -1, 8, 2])
        result, _ = _patched_run(trades, redis_equity=100_000.0)
        assert result["triggered"] is True
```

- [ ] **Step 5: Run to verify the new tests fail**

Run: `.venv/bin/pytest tests/workers/test_loss_feedback.py -q`
Expected: the four new tests FAIL (small losses still trigger); old tests pass.

- [ ] **Step 6: Implement the relative trigger**

In `src/workers/performance.py::run_loss_feedback_check`, replace (line ~1641):

```python
    triggered = (
        consecutive_losses >= cfg["consecutive_loss_trigger"]
        or rolling_net_pnl < 0
    )
```

with:

```python
    # Relative trigger: a rolling loss must be material vs account size. Equity
    # comes from the portfolio:value key (written each portfolio cycle); when
    # unknown, fall back to a conservative absolute floor.
    equity = redis.get_portfolio_value()
    if equity is not None and equity > 0:
        rolling_loss_limit = equity * cfg["rolling_pnl_trigger_pct"]
    else:
        rolling_loss_limit = cfg["rolling_pnl_trigger_floor_usd"]

    triggered = (
        consecutive_losses >= cfg["consecutive_loss_trigger"]
        or rolling_net_pnl < -rolling_loss_limit
    )
```

Add to the `result` dict (after `"rolling_net_pnl": ...`):

```python
        "rolling_loss_limit": round(rolling_loss_limit, 2),
```

And in the alert-reason block (~line 1692), replace `if rolling_net_pnl < 0:` with:

```python
        if rolling_net_pnl < -rolling_loss_limit:
            reason_parts.append(
                f"rolling P&L ${rolling_net_pnl:.2f} (limit -${rolling_loss_limit:.0f})"
            )
```

(delete the old `reason_parts.append(f"rolling P&L ${rolling_net_pnl:.2f}")` line inside that branch).

- [ ] **Step 7: Run the full loss-feedback test file**

Run: `.venv/bin/pytest tests/workers/test_loss_feedback.py -q`
Expected: PASS. Pre-existing tests that asserted a trigger from a *small* negative rolling P&L alone will fail — for each, decide from its name: if it tests the rolling-P&L mechanism itself, keep it meaningful by passing `cfg_override={"rolling_pnl_trigger_floor_usd": 0.0}` (restores strict `< 0` semantics for that test); if it tests something else and the rolling loss is incidental, make the loss larger than $250.

- [ ] **Step 8: Commit**

```bash
git add src/store/redis_store.py src/workers/performance.py src/workers/portfolio_scheduler.py config/trading.yaml tests/workers/test_loss_feedback.py
git commit -m "fix(feedback): rolling-P&L trigger must be material relative to equity, not merely negative"
```

---

### Task 5: Loss-feedback — time-decay of the raised threshold

Recovery currently requires `recovery_win_streak` consecutive wins, which at 2-6 tiny trades/day rarely completes — the threshold stays pinned long after the triggering cause is gone. Add passive decay: if no adjustment happened for `decay_hours` and nothing is currently triggering, step the threshold one notch back toward baseline (and the regime scale back up). The task runs every 30 min (see `celery_app.py` beat entry `loss-feedback-check`), so decay fires at most once per `decay_hours`.

**Files:**
- Modify: `src/workers/performance.py` (`run_loss_feedback_check` + `_load_loss_feedback_config`)
- Modify: `config/trading.yaml`
- Test: `tests/workers/test_loss_feedback.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/workers/test_loss_feedback.py` (also add `"decay_hours": 24,` to the test-local `_default_cfg()`):

```python
class TestTimeDecay:
    def _state_hours_ago(self, hours: float) -> dict:
        ts = datetime.now(timezone.utc) - timedelta(hours=hours)
        return {"last_adjustment_ts": ts.isoformat()}

    def test_threshold_decays_after_decay_hours(self):
        # no trigger (rolling positive, 1 consecutive loss), last adjustment 25h ago
        trades = _make_trades([10, -5, 8, 3, 2])
        result, mock_redis = _patched_run(
            trades,
            redis_threshold=0.55,
            redis_scale=0.33,
            redis_state=self._state_hours_ago(25),
            redis_equity=100_000.0,
        )
        assert result["decayed"] is True
        assert result["new_threshold"] == pytest.approx(0.50)
        mock_redis.set_feedback_entry_threshold.assert_called_once()

    def test_no_decay_within_window(self):
        trades = _make_trades([10, -5, 8, 3, 2])
        result, _ = _patched_run(
            trades,
            redis_threshold=0.55,
            redis_state=self._state_hours_ago(5),
            redis_equity=100_000.0,
        )
        assert result["decayed"] is False

    def test_no_decay_at_baseline(self):
        trades = _make_trades([10, -5, 8, 3, 2])
        result, mock_redis = _patched_run(
            trades,
            redis_threshold=0.30,
            redis_state=self._state_hours_ago(48),
            redis_equity=100_000.0,
        )
        assert result["decayed"] is False
        mock_redis.set_feedback_entry_threshold.assert_not_called()

    def test_no_decay_while_triggered(self):
        # big rolling loss → escalation path, not decay
        trades = _make_trades([-600, -5, 8, 3, 2])
        result, _ = _patched_run(
            trades,
            redis_threshold=0.55,
            redis_state=self._state_hours_ago(25),
            redis_equity=100_000.0,
        )
        assert result["decayed"] is False
        assert result["adjusted"] is True
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/pytest tests/workers/test_loss_feedback.py::TestTimeDecay -q`
Expected: FAIL with `KeyError: 'decayed'`.

- [ ] **Step 3: Implement the decay**

In `src/workers/performance.py`:

(a) add `"decay_hours": 24,` to the `defaults` dict in `_load_loss_feedback_config`.

(b) in `run_loss_feedback_check`, hoist `hours_since` out of the cooldown block. Replace:

```python
    cooldown_ok = True
    if last_adj_str:
```

with:

```python
    cooldown_ok = True
    hours_since: float | None = None
    if last_adj_str:
```

(the `hours_since = ...` assignment inside the `try` stays as is).

(c) add `"decayed": False,` to the initial `result` dict (next to `"recovered": False,`).

(d) after the entire recovery `elif not triggered and consecutive_wins >= cfg["recovery_win_streak"]:` block, add a third branch:

```python
    elif (
        not triggered
        and current_threshold > cfg["threshold_baseline"]
        and hours_since is not None
        and hours_since >= cfg["decay_hours"]
    ):
        # Time-decay: nothing re-triggered for decay_hours — step the threshold
        # back toward baseline even without a win streak. At 2-6 trades/day a
        # recovery_win_streak may never complete, leaving the gate pinned high
        # long after the triggering cause is fixed (observed 2026-07-09: 0.55
        # held by −$208 of rolling noise).
        new_threshold = max(current_threshold - cfg["threshold_step"], cfg["threshold_baseline"])
        new_scale = min(current_scale / cfg["regime_scale_factor"], 1.0)

        redis.set_feedback_entry_threshold(new_threshold, ttl=ttl_seconds)
        redis.set_feedback_regime_scale(new_scale, ttl=ttl_seconds)

        redis.set_feedback_state({
            "last_adjustment_ts": datetime.now(timezone.utc).isoformat(),
            "reason": "time_decay",
            "threshold_before": current_threshold,
            "threshold_after": new_threshold,
            "scale_before": current_scale,
            "scale_after": new_scale,
        }, ttl=ttl_seconds)

        result["decayed"] = True
        result["new_threshold"] = new_threshold
        result["new_scale"] = new_scale

        log.info(
            "Loss feedback time-decay: %.1fh since last adjustment — threshold %.2f→%.2f, scale %.2f→%.2f",
            hours_since, current_threshold, new_threshold, current_scale, new_scale,
        )
```

Note the state write updates `last_adjustment_ts`, so the next decay can only happen another `decay_hours` later.

- [ ] **Step 4: Run the whole file**

Run: `.venv/bin/pytest tests/workers/test_loss_feedback.py -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/workers/performance.py config/trading.yaml tests/workers/test_loss_feedback.py
git commit -m "feat(feedback): time-decay raised entry threshold back toward baseline after quiet 24h"
```

---

### Task 6: S4 ranker — allow a single-name bucket (min_stocks 2 → 1)

With the entry gate high, the rare surviving strong signal is discarded because `CrossSectionalRanker` refuses buckets smaller than `min_stocks=2` (`src/strategies/s4/ranking.py:83,95`). A 1-name bucket gets sleeve weight 1.0 → 10% allocation × regime multiplier ≈ 7% of NAV — within the 10% single-position risk cap, so this is safe.

**Files:**
- Modify: `src/strategies/s4/config.py:20`
- Test: `tests/strategies/test_s4_ranking.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/strategies/test_s4_ranking.py` (the file already has the `_sig(symbol, score=..., confidence=...)` helper):

```python
def test_single_candidate_forms_bucket_of_one():
    # A lone strong signal must trade, not be discarded (min_stocks=1 default).
    ranker = CrossSectionalRanker(S4Config())
    result = ranker.rank([_sig("AAPL", score=0.6, confidence=0.9)])
    assert result.n_selected == 1
    assert result.weights == {"AAPL": 1.0}
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/pytest tests/strategies/test_s4_ranking.py::test_single_candidate_forms_bucket_of_one -q`
Expected: FAIL — `n_selected == 0` (empty result under min_stocks=2).

- [ ] **Step 3: Change the default**

In `src/strategies/s4/config.py` replace `min_stocks: int = 2` with:

```python
    # 2 → 1 on 2026-07-10: with the loss-feedback gate raised, often exactly one
    # strong signal survives; requiring 2 discarded it and produced zero orders.
    # A 1-name bucket = sleeve weight 1.0 → ~10% of NAV → within max_position_pct.
    min_stocks: int = 1
```

- [ ] **Step 4: Fix the defaults assertion and run the S4 test files**

In `tests/strategies/test_s4_ranking.py::test_s4_config_defaults` (line ~48) change `assert cfg.min_stocks == 2` to `assert cfg.min_stocks == 1`.

Run: `.venv/bin/pytest tests/strategies/test_s4_ranking.py tests/strategies/test_s4_strategy.py tests/strategies/test_s4_backtest.py tests/strategies/test_s4_backtest_parity.py -q`
Expected: PASS. Any test that specifically exercises the min_stocks mechanism with an explicit `S4Config(min_stocks=N)` is unaffected; a test relying on the *default* rejecting one signal must be updated to pass `S4Config(min_stocks=2)` explicitly.

- [ ] **Step 5: Commit**

```bash
git add src/strategies/s4/config.py tests/strategies/test_s4_ranking.py
git commit -m "fix(s4): allow single-name bucket so a lone surviving signal still trades"
```

---

### Task 7: Full suite, deploy, live verification

- [ ] **Step 1: Full test suite**

Run: `.venv/bin/pytest -q`
Expected: 0 failures (baseline was ~2340 passed / 1 skipped). Fix any regression before proceeding — do not skip tests to get to green.

- [ ] **Step 2: Deploy (images bake `src/`, a restart is NOT enough)**

```bash
docker compose build api worker worker-inference beat
docker compose up -d api worker worker-inference beat
docker ps --format '{{.Names}}\t{{.Status}}'   # all Up, api healthy
```

- [ ] **Step 3: Reset the stale pinned threshold (one-time operator action)**

The old 0.55 threshold and 0.33 scale in Redis were produced by the pre-fix trigger (a -$208 rolling blip) and have a ~48h TTL; under the new rules they would not exist. Clear them so the gate returns to the 0.30 baseline immediately:

```bash
docker exec alembic-redis-1 redis-cli DEL feedback:entry_threshold feedback:regime_scale feedback:state
```

- [ ] **Step 4: Verify live during market hours (13:30–20:00 UTC, Mon–Fri)**

Wait for at least one 15-min portfolio cycle, then:

```bash
# S1 revived: sparse tickers dropped, weights produced
docker logs alembic-worker-1 --since 30m 2>&1 | grep -E "S1 compute_signal: dropped|merged_weights"
```
Expected: a WARNING naming `['AZN', 'SPCX']` as dropped, and `merged_weights=N symbols` with N > 0 (previously always 0).

```bash
# Orders flowing again
docker exec alembic-postgres-1 psql -U trading -d trading -c \
  "SELECT timestamp, strategies_run, orders_count FROM portfolio_cycles ORDER BY timestamp DESC LIMIT 4;"
```
Expected: `orders_count` > 0 on at least one recent cycle (S1 alone should target dozens of names; the ConstraintEnforcer will cap total exposure at 50% of NAV).

```bash
# Gate back at baseline
docker exec alembic-redis-1 redis-cli GET feedback:entry_threshold
```
Expected: `(nil)` (baseline 0.30 applies) or a value ≤ 0.35.

If the market is closed, verify S1 signal generation directly instead (same code path as the live cycle):

```bash
docker exec alembic-worker-1 python -c "
from datetime import datetime, timedelta, timezone
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.data.enums import DataFeed, Adjustment
from src.config import config
from src.strategies.s1.signal import generate_signals
end = datetime.now(timezone.utc); start = end - timedelta(days=600)
c = StockHistoricalDataClient(api_key=config.ALPACA_API_KEY, secret_key=config.ALPACA_SECRET_KEY)
bars = c.get_stock_bars(StockBarsRequest(symbol_or_symbols=list(config.WATCHLIST_SYMBOLS), timeframe=TimeFrame.Day, start=start, end=end, feed=DataFeed.IEX, adjustment=Adjustment.ALL)).df.reset_index().pivot(index='timestamp', columns='symbol', values='close')
comb = generate_signals(bars)
last = comb[comb['as_of'] == comb['as_of'].max()]
print('rows:', len(comb), '| latest tickers signal>0:', (last['signal'] > 0).sum())
"
```
Expected: `rows:` in the thousands and `latest tickers signal>0:` in the tens (it was `rows: 0` before the fix).

- [ ] **Step 5: Report**

Summarize for the operator: commits made, test counts, deploy status, and the live-verification evidence (which of the expected outcomes were observed). Flag explicitly if any verification could not run (market closed, missing data) so it can be re-checked next session.

---

## Self-review checklist (for the implementer)

- Every fix has a test that failed before the change and passes after.
- No changes to `config/strategies.yaml` allocations, risk caps, regime logic, or data feeds.
- `git log` shows one commit per task with the messages above.
- The full suite is green before the deploy step.
