# Code Review Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 4 outstanding code review findings (CR-05, CR-06, CR-07, and Issue #2 risk params) that were not yet applied when the previous session was interrupted.

**Architecture:** Each fix is isolated to a small number of files. CR-06 (S4 double scaling) touches only `ranking.py` and its tests. CR-07 (economy toggle) is a pure frontend change. CR-05 (rebalance bypass) adds two public methods to S1/S4 and a gate check to the orchestrator. Issue #2 (risk params) extends `_load_risk_params()` to return `max_position_pct` and wires it into `run_execution_cycle()`.

**Tech Stack:** Python (FastAPI, dataclasses), TypeScript/React (Zustand), pytest

**Context — what was already fixed before this plan:**
- Issue #1 (kill switch GET/POST/DELETE) — fixed, `src/api/routes/admin.py` has all three endpoints
- Issue #4 (`/api/strategies` auth) — fixed, router uses `dependencies=[Depends(require_api_key)]`
- Issue #5 (news `fetched_at`) — fixed, `get_news_recent()` selects and orders by `fetched_at`
- Issue #7 (config relative paths) — fixed, all three files use `Path(__file__).resolve().parents[N]`

---

## File Structure

Files modified by this plan:

| File | Change |
|------|--------|
| `src/strategies/s4/ranking.py` | Fix `per_ticker_weight = 1.0 / n` (was `bucket_pct / n`) |
| `src/strategies/s1/strategy.py` | Add public `should_rebalance(ts)` and `mark_rebalanced(ts)` |
| `src/strategies/s4/strategy.py` | Add public `should_rebalance(ts)` and `mark_rebalanced(ts)` |
| `src/portfolio/orchestrator.py` | Gate `compute_target_weights()` behind `should_rebalance()` |
| `src/workers/execution.py` | Extend `_load_risk_params()` to return `max_position_pct` |
| `frontend/src/components/layout/Sidebar.tsx` | Check `res.ok` before `setLlmModels(next)` |
| `tests/strategies/test_s4_ranking.py` | Update weight assertions (0.02 → 0.20, etc.) + add sleeve-sum test |
| `tests/strategies/test_s4_strategy.py` | Add rebalance gate tests |
| `tests/strategies/test_s1_rebalance.py` | New file: S1 rebalance gate tests |
| `tests/portfolio/test_orchestrator_rebalance.py` | New file: orchestrator respects rebalance gate |
| `tests/workers/test_execution_risk_params.py` | New file: `max_position_pct` read from config |

---

## Task 1: Fix S4 double scaling

S4's `CrossSectionalRanker` computes `per_ticker_weight = bucket_pct / n` (e.g. `0.10/5 = 0.02`). The orchestrator then multiplies these weights by `allocation_pct = 0.10`, giving a final portfolio weight of `0.002` per ticker (1% total) instead of the intended 10%. The fix: return sleeve-local weights that sum to 1.0, so the orchestrator's `× allocation_pct` yields the correct portfolio fraction.

**Files:**
- Modify: `src/strategies/s4/ranking.py:101`
- Modify: `tests/strategies/test_s4_ranking.py` (update broken assertions + add new test)

- [ ] **Step 1: Write failing tests first**

Open `tests/strategies/test_s4_ranking.py`. The tests `test_equal_weight_calculation`, `test_custom_bucket_pct`, `test_fewer_candidates_than_n_top`, `test_ties_all_selected_equal_weight`, and `test_ranking_result_weights_property` all assert old `bucket_pct / n` weights. Add the new test at the bottom before touching production code:

```python
def test_sleeve_local_weights_sum_to_one():
    """Sleeve-local weights must sum to 1.0 so orchestrator × allocation_pct is correct."""
    signals = _make_signals(10)
    ranker = CrossSectionalRanker()
    result = ranker.rank(signals)

    assert result.n_selected == 5
    total = sum(result.weights.values())
    assert total == pytest.approx(1.0, rel=1e-9)


def test_orchestrator_scale_gives_correct_portfolio_weight():
    """With allocation_pct=0.10 and 5 tickers, each ticker's portfolio weight = 0.02."""
    signals = _make_signals(10)
    ranker = CrossSectionalRanker()
    result = ranker.rank(signals)

    allocation_pct = 0.10
    for weight in result.weights.values():
        portfolio_weight = weight * allocation_pct
        assert portfolio_weight == pytest.approx(0.02, rel=1e-9)
```

- [ ] **Step 2: Run new tests to confirm they fail**

```bash
cd /home/stefano/Documents/Projects/Alembic
pytest tests/strategies/test_s4_ranking.py::test_sleeve_local_weights_sum_to_one -v
```

Expected: FAIL — `AssertionError: 0.1 != 1.0`

- [ ] **Step 3: Fix the weight calculation in ranking.py**

In `src/strategies/s4/ranking.py`, change line 101:

```python
# Before:
per_ticker_weight = cfg.bucket_pct / n

# After:
per_ticker_weight = 1.0 / n
```

Full context of the changed block (lines 100–113):

```python
n = len(selected)
per_ticker_weight = 1.0 / n

ranked = tuple(
    RankedTicker(
        ticker=sig.symbol,
        score=sig.score,
        confidence=sig.confidence,
        effective_strength=strength,
        rank=rank + 1,
        weight=per_ticker_weight,
    )
    for rank, (sig, strength) in enumerate(selected)
)
```

- [ ] **Step 4: Update the broken assertions in test_s4_ranking.py**

The following tests assume old `bucket_pct / n` semantics and need to be updated to use `1.0 / n` semantics. Replace the bodies of these tests:

```python
def test_equal_weight_calculation():
    """Sleeve-local weights are 1/n, not bucket_pct/n."""
    signals = _make_signals(10)
    ranker = CrossSectionalRanker()
    result = ranker.rank(signals)

    expected_weight = pytest.approx(1.0 / 5, rel=1e-9)  # 5 selected from 10
    for r in result.rankings:
        assert r.weight == expected_weight


def test_custom_bucket_pct():
    """bucket_pct does not affect per-ticker weight — only orchestrator allocation does."""
    signals = _make_signals(10)
    ranker = CrossSectionalRanker(S4Config(bucket_pct=0.20))
    result = ranker.rank(signals)

    # per_ticker_weight is 1.0/5 regardless of bucket_pct
    for r in result.rankings:
        assert r.weight == pytest.approx(1.0 / 5, rel=1e-9)


def test_fewer_candidates_than_n_top():
    """With 4 candidates and n_top=5, weight = 1.0/4."""
    signals = _make_signals(4)
    ranker = CrossSectionalRanker(S4Config(n_top=5, min_stocks=3))
    result = ranker.rank(signals)

    assert result.n_selected == 4
    for r in result.rankings:
        assert r.weight == pytest.approx(1.0 / 4, rel=1e-9)


def test_ties_all_selected_equal_weight():
    """5 tickers selected, each gets 1/5 sleeve weight."""
    signals = [_sig(f"T{i}", score=0.5, confidence=0.8) for i in range(5)]
    ranker = CrossSectionalRanker(S4Config(n_top=5))
    result = ranker.rank(signals)

    assert result.n_selected == 5
    weights = [r.weight for r in result.rankings]
    assert all(w == pytest.approx(1.0 / 5, rel=1e-9) for w in weights)


def test_ranking_result_weights_property():
    """RankingResult.weights property returns correct sleeve-local weights."""
    signals = _make_signals(5)
    ranker = CrossSectionalRanker(S4Config(n_top=5))
    result = ranker.rank(signals)

    weights = result.weights
    assert len(weights) == 5
    for v in weights.values():
        assert v == pytest.approx(1.0 / 5, rel=1e-9)
```

- [ ] **Step 5: Run all S4 ranking tests to confirm they pass**

```bash
cd /home/stefano/Documents/Projects/Alembic
pytest tests/strategies/test_s4_ranking.py -v
```

Expected: all tests PASS (including the new sleeve-sum tests)

- [ ] **Step 6: Commit**

```bash
git add src/strategies/s4/ranking.py tests/strategies/test_s4_ranking.py
git commit -m "fix(s4): sleeve-local weights sum to 1.0, fixing 10x underweight vs portfolio allocation"
```

---

## Task 2: Fix economy toggle false state on 403

`Sidebar.tsx` calls `fetch('/api/admin/llm-models')` and unconditionally calls `setLlmModels(next)` after the fetch resolves — even if the server returned 403 (wrong API key). The fix: check `res.ok` and only update state on success; rollback to the previous state on error.

**Files:**
- Modify: `frontend/src/components/layout/Sidebar.tsx:30-40`

- [ ] **Step 1: Update Sidebar.tsx toggleSavings**

Replace the entire `toggleSavings` function:

```typescript
const toggleSavings = async () => {
  const next = isSavings ? 'all' : 'glm'
  try {
    const res = await fetch('/api/admin/llm-models', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-API-Key': apiKey },
      body: JSON.stringify({ models: next }),
    })
    if (res.ok) {
      setLlmModels(next)
    } else {
      console.warn(`LLM model toggle failed: ${res.status}`)
    }
  } catch { /* network error — no state change */ }
}
```

- [ ] **Step 2: Build frontend to confirm no TypeScript errors**

```bash
cd /home/stefano/Documents/Projects/Alembic/frontend
npm run build 2>&1 | tail -20
```

Expected: build succeeds, no TypeScript errors

- [ ] **Step 3: Commit**

```bash
cd /home/stefano/Documents/Projects/Alembic
git add frontend/src/components/layout/Sidebar.tsx
git commit -m "fix(frontend): economy toggle only updates state on HTTP 200, no false state on 403"
```

---

## Task 3: Fix rebalance frequency bypass in orchestrator

The portfolio orchestrator calls `compute_target_weights()` directly on S1 and S4 instances every hour (per Celery beat schedule), bypassing the `_should_rebalance()` gate that S1 configured as `MONTHLY` and S4 as `WEEKLY`. This causes excess turnover and cost.

Fix: add public `should_rebalance(ts)` and `mark_rebalanced(ts)` methods to both strategy classes, then have the orchestrator check the gate before calling `compute_target_weights()`.

**Files:**
- Modify: `src/strategies/s1/strategy.py` (add 2 public methods)
- Modify: `src/strategies/s4/strategy.py` (add 2 public methods)
- Modify: `src/portfolio/orchestrator.py:253-277` (`_extract_target_weights` method)
- Create: `tests/strategies/test_s1_rebalance.py`
- Create: `tests/portfolio/test_orchestrator_rebalance.py`

- [ ] **Step 1: Write failing tests for S1 rebalance gate**

Create `tests/strategies/test_s1_rebalance.py`:

```python
"""Tests for S1 TimeSeriesMomentum public rebalance gate."""
from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from src.strategies.s1.strategy import S1Config, TimeSeriesMomentum
from src.backtest.engine.types import RebalanceFrequency


def _make_prices(n: int = 300) -> pd.DataFrame:
    dates = pd.date_range("2024-01-01", periods=n, freq="B")
    return pd.DataFrame({"SPY": np.ones(n) * 100.0}, index=dates)


def test_s1_should_rebalance_returns_true_on_first_call():
    prices = _make_prices()
    cfg = S1Config(rebalance_frequency=RebalanceFrequency.MONTHLY)
    s1 = TimeSeriesMomentum(prices, cfg)

    ts = datetime(2025, 6, 1, tzinfo=timezone.utc)
    assert s1.should_rebalance(ts) is True


def test_s1_should_rebalance_false_within_same_month():
    prices = _make_prices()
    cfg = S1Config(rebalance_frequency=RebalanceFrequency.MONTHLY)
    s1 = TimeSeriesMomentum(prices, cfg)

    ts_first = datetime(2025, 6, 1, tzinfo=timezone.utc)
    s1.mark_rebalanced(ts_first)

    ts_second = datetime(2025, 6, 15, tzinfo=timezone.utc)
    assert s1.should_rebalance(ts_second) is False


def test_s1_should_rebalance_true_next_month():
    prices = _make_prices()
    cfg = S1Config(rebalance_frequency=RebalanceFrequency.MONTHLY)
    s1 = TimeSeriesMomentum(prices, cfg)

    s1.mark_rebalanced(datetime(2025, 6, 1, tzinfo=timezone.utc))
    ts_next = datetime(2025, 7, 1, tzinfo=timezone.utc)
    assert s1.should_rebalance(ts_next) is True


def test_s1_mark_rebalanced_updates_state():
    prices = _make_prices()
    s1 = TimeSeriesMomentum(prices, S1Config())

    ts = datetime(2025, 6, 10, tzinfo=timezone.utc)
    assert s1.should_rebalance(ts) is True
    s1.mark_rebalanced(ts)
    assert s1.should_rebalance(datetime(2025, 6, 20, tzinfo=timezone.utc)) is False
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd /home/stefano/Documents/Projects/Alembic
pytest tests/strategies/test_s1_rebalance.py -v
```

Expected: `AttributeError: 'TimeSeriesMomentum' object has no attribute 'should_rebalance'`

- [ ] **Step 3: Add `should_rebalance` and `mark_rebalanced` to S1**

In `src/strategies/s1/strategy.py`, add two methods after `health_check()` (before `_should_rebalance`):

```python
def should_rebalance(self, ts: datetime) -> bool:
    """Public gate: returns True if it is time to rebalance at timestamp ts."""
    return self._should_rebalance(ts)

def mark_rebalanced(self, ts: datetime) -> None:
    """Record that a rebalance was performed at ts."""
    self._last_rebalance = ts
```

Full insertion point — after `health_check()` which ends at line 129, before `_should_rebalance` which starts at line 131:

```python
    def health_check(self) -> bool:
        """Return True when precomputed signals are non-empty, finite, and NaN-free."""
        if self._combined.empty:
            return False
        if self._combined["signal"].isna().any():
            return False
        if self._combined["weight"].isna().any():
            return False
        if np.isinf(self._combined["signal"]).any():
            return False
        if np.isinf(self._combined["weight"]).any():
            return False
        return True

    def should_rebalance(self, ts: datetime) -> bool:
        """Public gate: returns True if it is time to rebalance at timestamp ts."""
        return self._should_rebalance(ts)

    def mark_rebalanced(self, ts: datetime) -> None:
        """Record that a rebalance was performed at ts."""
        self._last_rebalance = ts

    def _should_rebalance(self, ts: datetime) -> bool:
```

- [ ] **Step 4: Run S1 rebalance tests to confirm they pass**

```bash
cd /home/stefano/Documents/Projects/Alembic
pytest tests/strategies/test_s1_rebalance.py -v
```

Expected: all 4 tests PASS

- [ ] **Step 5: Write failing tests for S4 rebalance gate**

Open `tests/strategies/test_s4_strategy.py` and append:

```python
def test_s4_should_rebalance_true_on_first_call():
    from src.strategies.s4.strategy import NewsDrivenTactical
    from src.strategies.s4.config import S4Config
    from src.backtest.engine.types import RebalanceFrequency
    from datetime import datetime, timezone

    s4 = NewsDrivenTactical(S4Config(rebalance_frequency=RebalanceFrequency.WEEKLY))
    ts = datetime(2025, 6, 2, tzinfo=timezone.utc)  # Monday
    assert s4.should_rebalance(ts) is True


def test_s4_should_rebalance_false_within_same_week():
    from src.strategies.s4.strategy import NewsDrivenTactical
    from src.strategies.s4.config import S4Config
    from src.backtest.engine.types import RebalanceFrequency
    from datetime import datetime, timezone

    s4 = NewsDrivenTactical(S4Config(rebalance_frequency=RebalanceFrequency.WEEKLY))
    s4.mark_rebalanced(datetime(2025, 6, 2, tzinfo=timezone.utc))  # Monday
    ts = datetime(2025, 6, 4, tzinfo=timezone.utc)   # Wednesday same week
    assert s4.should_rebalance(ts) is False


def test_s4_should_rebalance_true_next_week():
    from src.strategies.s4.strategy import NewsDrivenTactical
    from src.strategies.s4.config import S4Config
    from src.backtest.engine.types import RebalanceFrequency
    from datetime import datetime, timezone

    s4 = NewsDrivenTactical(S4Config(rebalance_frequency=RebalanceFrequency.WEEKLY))
    s4.mark_rebalanced(datetime(2025, 6, 2, tzinfo=timezone.utc))  # week 23
    ts = datetime(2025, 6, 9, tzinfo=timezone.utc)   # next Monday, week 24
    assert s4.should_rebalance(ts) is True
```

- [ ] **Step 6: Run S4 rebalance tests to confirm they fail**

```bash
cd /home/stefano/Documents/Projects/Alembic
pytest tests/strategies/test_s4_strategy.py::test_s4_should_rebalance_true_on_first_call -v
```

Expected: `AttributeError: 'NewsDrivenTactical' object has no attribute 'should_rebalance'`

- [ ] **Step 7: Add `should_rebalance` and `mark_rebalanced` to S4**

In `src/strategies/s4/strategy.py`, add two public methods after `health_check()` (before `_signals_as_of`):

```python
    def health_check(self) -> bool:
        return True

    def should_rebalance(self, ts: datetime) -> bool:
        """Public gate: returns True if it is time to rebalance at timestamp ts."""
        return self._should_rebalance(ts)

    def mark_rebalanced(self, ts: datetime) -> None:
        """Record that a rebalance was performed at ts."""
        self._last_rebalance = ts

    def _signals_as_of(self, ts: datetime) -> list[SentimentResult]:
```

- [ ] **Step 8: Run S4 strategy tests to confirm they pass**

```bash
cd /home/stefano/Documents/Projects/Alembic
pytest tests/strategies/test_s4_strategy.py -v
```

Expected: all tests PASS including new rebalance tests

- [ ] **Step 9: Write failing test for orchestrator rebalance gate**

Create `tests/portfolio/test_orchestrator_rebalance.py`:

```python
"""Tests that PortfolioOrchestrator respects strategy rebalance gates (CR-05)."""
from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from src.backtest.engine.data_replay import DataReplay
from src.backtest.engine.portfolio import VirtualPortfolio
from src.backtest.engine.types import MarketSnapshot, RebalanceFrequency
from src.portfolio.constraints import ConstraintEnforcer
from src.portfolio.orchestrator import PortfolioOrchestrator
from src.strategies.registry import StrategyEntry, StrategyRegistry


def _make_registry(entry: StrategyEntry) -> StrategyRegistry:
    reg = StrategyRegistry(load_defaults=False)
    reg.register(entry)
    return reg


def _make_market() -> MarketSnapshot:
    return MarketSnapshot(
        timestamp=datetime(2025, 6, 2, tzinfo=timezone.utc),
        prices={"AAPL": 150.0},
        volumes={"AAPL": 1_000_000.0},
        adv_20d={"AAPL": 1_000_000.0},
    )


def _make_data_replay() -> DataReplay:
    dates = pd.date_range("2024-01-01", periods=300, freq="B")
    prices = pd.DataFrame({"AAPL": np.ones(300) * 150.0}, index=dates)
    return DataReplay(prices)


class _GatedStrategy:
    """Strategy with public should_rebalance gate for testing."""

    def __init__(self, weights: dict[str, float]) -> None:
        self._weights = weights
        self._allow_rebalance = True
        self.compute_count = 0

    def should_rebalance(self, ts: datetime) -> bool:
        return self._allow_rebalance

    def mark_rebalanced(self, ts: datetime) -> None:
        pass

    def compute_target_weights(self, *args, **kwargs) -> dict[str, float]:
        self.compute_count += 1
        return self._weights


def test_orchestrator_skips_compute_when_should_rebalance_false():
    """Orchestrator must not call compute_target_weights when should_rebalance returns False."""
    strategy = _GatedStrategy({"AAPL": 1.0})
    strategy._allow_rebalance = False

    entry = StrategyEntry(strategy_id="S1", allocation_pct=0.5, active=True)
    registry = _make_registry(entry)
    orc = PortfolioOrchestrator(
        registry=registry,
        strategy_instances={"S1": strategy},
        constraint_enforcer=ConstraintEnforcer(),
    )

    ts = datetime(2025, 6, 2, tzinfo=timezone.utc)
    portfolio = VirtualPortfolio(initial_cash=100_000.0)
    result = orc.run_cycle(ts, _make_data_replay(), portfolio, _make_market())

    assert strategy.compute_count == 0
    assert result.final_orders == []


def test_orchestrator_calls_compute_when_should_rebalance_true():
    """Orchestrator must call compute_target_weights when should_rebalance returns True."""
    strategy = _GatedStrategy({"AAPL": 1.0})
    strategy._allow_rebalance = True

    entry = StrategyEntry(strategy_id="S1", allocation_pct=0.5, active=True)
    registry = _make_registry(entry)
    orc = PortfolioOrchestrator(
        registry=registry,
        strategy_instances={"S1": strategy},
        constraint_enforcer=ConstraintEnforcer(),
    )

    ts = datetime(2025, 6, 2, tzinfo=timezone.utc)
    portfolio = VirtualPortfolio(initial_cash=100_000.0)
    result = orc.run_cycle(ts, _make_data_replay(), portfolio, _make_market())

    assert strategy.compute_count == 1


def test_orchestrator_calls_mark_rebalanced_after_compute():
    """Orchestrator must call mark_rebalanced after a successful rebalance."""
    marked_ts = []

    class _TrackingStrategy(_GatedStrategy):
        def mark_rebalanced(self, ts):
            marked_ts.append(ts)

    strategy = _TrackingStrategy({"AAPL": 1.0})
    strategy._allow_rebalance = True

    entry = StrategyEntry(strategy_id="S1", allocation_pct=0.5, active=True)
    registry = _make_registry(entry)
    orc = PortfolioOrchestrator(
        registry=registry,
        strategy_instances={"S1": strategy},
        constraint_enforcer=ConstraintEnforcer(),
    )

    ts = datetime(2025, 6, 2, tzinfo=timezone.utc)
    portfolio = VirtualPortfolio(initial_cash=100_000.0)
    orc.run_cycle(ts, _make_data_replay(), portfolio, _make_market())

    assert len(marked_ts) == 1
    assert marked_ts[0] == ts
```

- [ ] **Step 10: Run orchestrator rebalance tests to confirm they fail**

```bash
cd /home/stefano/Documents/Projects/Alembic
pytest tests/portfolio/test_orchestrator_rebalance.py -v
```

Expected: `test_orchestrator_skips_compute_when_should_rebalance_false` FAILS (compute still called even when gate returns False)

- [ ] **Step 11: Update PortfolioOrchestrator._extract_target_weights**

In `src/portfolio/orchestrator.py`, modify `_extract_target_weights` to check the rebalance gate before calling `compute_target_weights`. Replace the method body (starting at line 254):

```python
    def _extract_target_weights(
        self, strategy_id: str, callable_fn, ts, data_replay, portfolio, market, nav
    ) -> dict[str, float]:
        """Extract target weights from a strategy.

        Strategies that expose should_rebalance(ts) → check the gate first.
        If the gate returns False, return {} (no rebalance this cycle).
        After computing weights, call mark_rebalanced(ts) if available.

        Strategies that expose compute_target_weights() → call that.
        Otherwise, run the callable to get orders → infer weights from order notional values.
        """
        # Check rebalance gate before computing
        if hasattr(callable_fn, 'should_rebalance'):
            if not callable_fn.should_rebalance(ts):
                log.debug("Strategy %s: rebalance gate blocked — skipping this cycle", strategy_id)
                return {}

        if hasattr(callable_fn, 'compute_target_weights'):
            if strategy_id == "S1":
                prices = data_replay.prices_until(ts)
                weights = callable_fn.compute_target_weights(prices)
            elif strategy_id == "S4":
                signals = getattr(callable_fn, '_signals_as_of', lambda t: None)(ts)
                weights = callable_fn.compute_target_weights(signals, as_of=ts)
            else:
                weights = {}

            # Mark rebalance time after successful computation
            if hasattr(callable_fn, 'mark_rebalanced'):
                callable_fn.mark_rebalanced(ts)
            return weights

        # S2 returns orders → infer weights
        orders = callable_fn(ts, data_replay, portfolio, market)
        if not orders:
            return {}

        weights: dict[str, float] = {}
        for order in orders:
            price = market.price_of(order.symbol)
            if price is None or price <= 0 or nav <= 0:
                continue
            value = price * order.quantity
            wt = value / nav
            sign = 1.0 if order.side == OrderSide.BUY else -1.0
            weights[order.symbol] = weights.get(order.symbol, 0.0) + sign * wt

        return weights
```

- [ ] **Step 12: Run orchestrator rebalance tests to confirm they pass**

```bash
cd /home/stefano/Documents/Projects/Alembic
pytest tests/portfolio/test_orchestrator_rebalance.py -v
```

Expected: all 3 tests PASS

- [ ] **Step 13: Run all orchestrator tests to check for regressions**

```bash
cd /home/stefano/Documents/Projects/Alembic
pytest tests/portfolio/ -v
```

Expected: all tests PASS

- [ ] **Step 14: Commit**

```bash
git add src/strategies/s1/strategy.py src/strategies/s4/strategy.py \
        src/portfolio/orchestrator.py \
        tests/strategies/test_s1_rebalance.py \
        tests/strategies/test_s4_strategy.py \
        tests/portfolio/test_orchestrator_rebalance.py
git commit -m "fix(portfolio): respect rebalance frequency gate in orchestrator (CR-05)"
```

---

## Task 4: Fix max_position_pct hardcoded in execution worker

`run_execution_cycle()` computes order notional as `portfolio_value * MAX_POSITION_PCT * regime_mult` where `MAX_POSITION_PCT = 0.10` is a module constant. The Config UI saves `risk.max_position_pct` to `config/trading.yaml`, but the worker never reads it. The fix: extend `_load_risk_params()` to return `max_position_pct` from the YAML.

**Files:**
- Modify: `src/workers/execution.py:71-83` (`_load_risk_params`), line 444 (call site), line 668 (usage)
- Create: `tests/workers/test_execution_risk_params.py`

- [ ] **Step 1: Write failing test**

Create `tests/workers/test_execution_risk_params.py`:

```python
"""Tests that run_execution_cycle respects risk params from trading.yaml (Issue #2)."""
from __future__ import annotations

import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest
import yaml

from src.workers.execution import _load_risk_params


def _write_yaml(path: str, stop_loss: float, drawdown: float, max_position_pct: float):
    with open(path, "w") as f:
        yaml.dump(
            {"risk": {
                "stop_loss": stop_loss,
                "portfolio_drawdown": drawdown,
                "max_position_pct": max_position_pct,
            }},
            f,
        )


def test_load_risk_params_reads_all_three_values():
    with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as tf:
        _write_yaml(tf.name, stop_loss=0.03, drawdown=0.07, max_position_pct=0.05)
        with patch("src.workers.execution._TRADING_YAML", tf.name):
            stop_loss, drawdown, max_pos = _load_risk_params()
    assert stop_loss == pytest.approx(0.03)
    assert drawdown == pytest.approx(0.07)
    assert max_pos == pytest.approx(0.05)


def test_load_risk_params_falls_back_to_defaults():
    with patch("src.workers.execution._TRADING_YAML", "/nonexistent/trading.yaml"):
        stop_loss, drawdown, max_pos = _load_risk_params()
    from src.workers.execution import STOP_LOSS_PCT, MAX_DRAWDOWN_PCT, MAX_POSITION_PCT
    assert stop_loss == pytest.approx(STOP_LOSS_PCT)
    assert drawdown == pytest.approx(MAX_DRAWDOWN_PCT)
    assert max_pos == pytest.approx(MAX_POSITION_PCT)


def test_execution_cycle_uses_max_position_pct_from_config():
    """When trading.yaml sets max_position_pct=0.05, notional = portfolio_value * 0.05 * regime."""
    with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as tf:
        _write_yaml(tf.name, stop_loss=0.02, drawdown=0.10, max_position_pct=0.05)

    # Build a minimal mock environment
    redis_store = MagicMock()
    redis_store.is_killswitch_active.return_value = False
    redis_store.get_regime.return_value = MagicMock(multiplier=1.0)
    redis_store.get_feedback_entry_threshold.return_value = None
    redis_store.get_feedback_regime_scale.return_value = None
    redis_store._r.get.return_value = None
    redis_store.read_sentiment.return_value = None

    account = MagicMock()
    account.portfolio_value = "100000"
    account.last_equity = "100000"
    trading_client = MagicMock()
    trading_client.get_account.return_value = account
    trading_client.get_all_positions.return_value = []
    trading_client.get_orders.return_value = []

    # Inject a signal that would trigger a BUY
    sentinel_signal = {
        "score": 0.9,
        "confidence": 0.9,
        "generated_at": "2025-06-08T14:00:00+00:00",
        "fallback_used": False,
    }
    redis_store.read_sentiment.return_value = sentinel_signal

    submitted_orders = []
    def capture_order(order):
        submitted_orders.append(order)
        return MagicMock(id="order-123")
    trading_client.submit_order.side_effect = capture_order

    from src.workers.execution import run_execution_cycle
    with patch("src.workers.execution._TRADING_YAML", tf.name):
        run_execution_cycle(
            symbols=["AAPL"],
            redis_store=redis_store,
            trading_client=trading_client,
            data_client=None,
        )

    assert len(submitted_orders) == 1
    # Notional should be portfolio_value(100k) * max_position_pct(0.05) * regime(1.0) = 5000
    submitted = submitted_orders[0]
    assert submitted.notional == pytest.approx(5000.0, rel=0.01)

    os.unlink(tf.name)
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd /home/stefano/Documents/Projects/Alembic
pytest tests/workers/test_execution_risk_params.py::test_load_risk_params_reads_all_three_values -v
```

Expected: `ValueError: too many values to unpack` (currently returns a 2-tuple)

- [ ] **Step 3: Update `_load_risk_params` to return 3-tuple**

In `src/workers/execution.py`, replace `_load_risk_params()` (lines 71–83):

```python
def _load_risk_params() -> tuple[float, float, float]:
    """Return (stop_loss_pct, max_drawdown_pct, max_position_pct) from trading.yaml."""
    try:
        import yaml
        with open(_TRADING_YAML) as f:
            cfg = yaml.safe_load(f)
        risk = cfg.get("risk", {})
        stop_loss = float(risk.get("stop_loss", STOP_LOSS_PCT))
        drawdown = float(risk.get("portfolio_drawdown", MAX_DRAWDOWN_PCT))
        max_pos = float(risk.get("max_position_pct", MAX_POSITION_PCT))
        return stop_loss, drawdown, max_pos
    except Exception as exc:
        log.warning("Could not load risk params from %s (%s) — using defaults", _TRADING_YAML, exc)
        return STOP_LOSS_PCT, MAX_DRAWDOWN_PCT, MAX_POSITION_PCT
```

- [ ] **Step 4: Update the call site and usage in `run_execution_cycle`**

In `run_execution_cycle`, line 444 changes from:

```python
_, max_drawdown_pct = _load_risk_params()
```

To:

```python
_, max_drawdown_pct, max_position_pct = _load_risk_params()
```

And line 668 changes from:

```python
notional = portfolio_value * MAX_POSITION_PCT * regime_mult
```

To:

```python
notional = portfolio_value * max_position_pct * regime_mult
```

Also update line 539 (cycle cap calculation) from:

```python
cycle_cap = portfolio_value * MAX_CYCLE_NOTIONAL_PCT
```

This line doesn't need changing (cycle cap uses a separate constant). Only the per-position notional line 668 uses `MAX_POSITION_PCT`.

- [ ] **Step 5: Run risk params tests to confirm they pass**

```bash
cd /home/stefano/Documents/Projects/Alembic
pytest tests/workers/test_execution_risk_params.py -v
```

Expected: all 3 tests PASS

- [ ] **Step 6: Run all execution worker tests to check for regressions**

```bash
cd /home/stefano/Documents/Projects/Alembic
pytest tests/workers/ -v 2>&1 | tail -30
```

Expected: PASS (no regressions in existing worker tests)

- [ ] **Step 7: Commit**

```bash
git add src/workers/execution.py tests/workers/test_execution_risk_params.py
git commit -m "fix(execution): max_position_pct read from trading.yaml risk config (Issue #2)"
```

---

## Task 5: Full test suite + merge

- [ ] **Step 1: Run full test suite**

```bash
cd /home/stefano/Documents/Projects/Alembic
pytest --tb=short -q 2>&1 | tail -30
```

Expected: all tests PASS (or pre-existing failures only — none introduced by this plan)

- [ ] **Step 2: Merge to main, rebuild, redeploy**

```bash
cd /home/stefano/Documents/Projects/Alembic
git checkout main
git merge feature/code-review-fixes
docker compose build
docker compose up -d
```

- [ ] **Step 3: Verify containers healthy**

```bash
docker compose ps
```

Expected: api, worker, frontend, beat, postgres, redis all `healthy` or `running`
