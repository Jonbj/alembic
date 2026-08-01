# P0 Correctness Bugs — Kimi Execution Spec (#107, #110, #111, #113)

> **For the executing agent (Kimi):** You have NO prior context on this repo. Read this whole document once before starting. Execute each bug section **in order**, exactly as written, one git branch + one PR per bug. Do NOT improvise fixes beyond what each section specifies. When a section is done, run the full test suite, open the PR, and move to the next. A human reviewer (Claude/Sonnet) will review every PR before merge — your job is to execute and hand back, not to merge.

**Repo:** `/home/stefano/Documents/Projects/Alembic` — an LLM-based algorithmic **paper-trading** system. These four bugs are on the money path, so precision matters more than speed.

**Goal:** Close GitHub issues #113, #111, #107 and add the regression lock for #110, each as an independently-reviewable PR.

**Tech stack:** Python 3, Pydantic v2, pytest (run via `uv run pytest`), Alpaca SDK (`alpaca-py`), PostgreSQL, Redis, Celery. Test framework already configured in `pyproject.toml`.

---

## Session protocol (read once, apply to every bug)

1. **Test runner:** always `uv run pytest <path> -v` for a targeted run, `uv run pytest -q` for the full suite. Never invoke bare `pytest`.
2. **TDD, strictly:** for every change — (a) write the failing test, (b) run it and SEE it fail for the right reason, (c) write the minimal implementation, (d) run it and SEE it pass, (e) run the file's whole test module, (f) commit. Do not write implementation before its test.
3. **One branch + one PR per bug.** Branch names are given per section. PR title = the issue title; PR body must contain `closes #<N>` and a 2-3 line summary of the root cause and the fix. Do not squash the four bugs together.
4. **Do not touch anything outside the files listed in each section.** In particular, the following are **out of scope for every bug here** — if a fix seems to need them, STOP and leave a note in the PR instead of editing them: order-submission call sites in `src/workers/execution.py`; the kill-switch / `portfolio:peak_equity` logic in `portfolio_scheduler.py`; the sentiment **scoring formula** `score = polarity × confidence` (`src/workers/sentiment.py`); `src/connectors/ticker_resolver*.py`; anything under `config/trading.yaml` risk thresholds. These are governed by non-negotiable constraints in `CLAUDE.md`.
5. **No DB migrations.** All four fixes are designed to need zero schema change. If you think you need a new column, you have misread the spec — re-read it.
6. **Never delete or weaken an existing test.** If an existing test now fails because it encoded the *old buggy behavior*, fix the test to assert the new correct behavior and call it out explicitly in the PR body. Do not `xfail`/`skip` to make green.
7. **Full-suite gate before each PR:** `uv run pytest -q` must be green (pre-existing unrelated failures, if any, must be identical before and after your change — capture the baseline first with `uv run pytest -q 2>&1 | tail -5`).
8. **Do not deploy, do not restart containers, do not push to `main`.** PRs only.

Execution order (isolation, low→high blast radius): **#113 → #111 → #107 → #110.**

---

## BUG 1 — #113: fractional protective-stop sized against total qty, not available qty

**Branch:** `fix/113-fractional-stop-qty-available`

### Root cause (verified)
`plan_protective_stop` in `src/portfolio/fractional_stop_orders.py` sizes the protective stop order to `whole_qty = math.floor(abs(position_qty))` — the whole-share floor of the **entire** position. When some of those shares are already reserved by another open order (e.g. a pending scheduler SELL), Alpaca rejects the stop with `40310000 "insufficient qty available for order"` (observed live 2026-07-22 for HOOD). The position is then briefly unprotected until the next cycle. The Alpaca `Position` object exposes `qty_available` (total shares minus shares held for open orders) — the stop must be sized against that, adding back the shares held by the existing stop orders we cancel this cycle (those free up before the replacement is submitted).

### Files
- Modify: `src/portfolio/fractional_stop_orders.py` (`plan_protective_stop`, `build_protective_stop_plans`, `execute_protective_stop_plans`)
- Test: `tests/portfolio/test_fractional_stop_orders.py` (add a new test class)

### Steps

- [ ] **Step 1 — Write the failing tests.** Append this class to `tests/portfolio/test_fractional_stop_orders.py` (the file already imports `ExistingStopOrder`, `SimpleNamespace`, and has the `_plan`, `stop_policy`, `cycle_ts` fixtures):

```python
class TestQtyAvailableSizing:
    """#113: stop qty must not exceed shares actually free to reserve."""

    def test_sizes_stop_to_available_when_shares_held_for_orders(self, stop_policy, cycle_ts):
        # 5 whole shares held, but only 2.3 free (rest reserved by a pending SELL).
        plan = _plan(
            position_qty=5.4, qty_available=2.3, avg_entry_price=100.0,
            stop_policy=stop_policy, cycle_ts=cycle_ts, existing_stop_orders=[],
        )
        assert plan.action == "create"
        assert plan.whole_qty == 2  # floor(2.3), NOT floor(5.4)

    def test_skip_when_no_shares_available(self, stop_policy, cycle_ts):
        plan = _plan(
            position_qty=5.4, qty_available=0.0, avg_entry_price=100.0,
            stop_policy=stop_policy, cycle_ts=cycle_ts, existing_stop_orders=[],
        )
        assert plan.action == "skip_insufficient_qty"
        assert plan.whole_qty == 0

    def test_replace_adds_back_own_reserved_shares(self, stop_policy, cycle_ts):
        # All 5 shares reserved by our OWN existing stop → qty_available reads 0,
        # but cancelling that stop frees them, so we must still size to 5.
        existing = ExistingStopOrder(id="ord-1", qty=5, stop_price=70.0)
        plan = _plan(
            position_qty=5.4, qty_available=0.0, avg_entry_price=100.0,
            stop_policy=stop_policy, cycle_ts=cycle_ts, existing_stop_orders=[existing],
        )
        assert plan.action in ("replace", "noop")
        assert plan.whole_qty == 5

    def test_none_qty_available_keeps_legacy_full_size(self, stop_policy, cycle_ts):
        plan = _plan(
            position_qty=5.4, qty_available=None, avg_entry_price=100.0,
            stop_policy=stop_policy, cycle_ts=cycle_ts, existing_stop_orders=[],
        )
        assert plan.action == "create"
        assert plan.whole_qty == 5
```

- [ ] **Step 2 — Run the tests, confirm they fail.**

Run: `uv run pytest tests/portfolio/test_fractional_stop_orders.py::TestQtyAvailableSizing -v`
Expected: FAIL — `plan_protective_stop() got an unexpected keyword argument 'qty_available'`.

- [ ] **Step 3 — Implement.** In `src/portfolio/fractional_stop_orders.py`, replace the whole `plan_protective_stop` function body with this (adds the `qty_available` parameter and the available-qty sizing; keeps the None default = legacy behavior so existing callers/tests are unaffected):

```python
def plan_protective_stop(
    symbol: str,
    position_qty: float,
    avg_entry_price: float,
    strategy: str | None,
    current_sigma_eff: float | None,
    stop_policy: StopPolicy,
    cycle_ts: datetime,
    existing_stop_orders: list[ExistingStopOrder],
    price_tolerance: float = 0.005,
    qty_available: float | None = None,
) -> ProtectiveStopPlan:
    """Decide whether to create/replace/leave-alone the protective stop for one symbol.

    #113: the stop qty must not exceed the shares actually free to reserve. When
    other open orders (e.g. a pending scheduler SELL) already hold part of the
    position, Alpaca rejects a stop sized to the full whole-share floor with
    40310000 "insufficient qty available". We size against qty_available, adding
    back the shares held by the existing stop orders we cancel this cycle (they
    free up before the replacement is submitted). If nothing is placeable this
    cycle, emit skip_insufficient_qty and retry next cycle. qty_available=None
    preserves the pre-#113 behavior (size to the full position).
    """
    whole_qty = math.floor(abs(position_qty))
    if whole_qty < 1:
        return ProtectiveStopPlan(action="skip_no_whole_share", symbol=symbol, whole_qty=0, stop_price=None)

    if qty_available is None:
        target_qty = whole_qty
    else:
        reserved_by_existing = sum(o.qty for o in existing_stop_orders)
        placeable = math.floor(abs(qty_available) + reserved_by_existing)
        target_qty = min(whole_qty, placeable)
        if target_qty < 1:
            return ProtectiveStopPlan(action="skip_insufficient_qty", symbol=symbol, whole_qty=0, stop_price=None)

    frozen = stop_policy.freeze(symbol, strategy, avg_entry_price, cycle_ts)
    d_hard = stop_policy.d_hard(symbol, frozen, current_sigma_eff)
    stop_price = round(avg_entry_price * (1.0 - d_hard), 2)

    if len(existing_stop_orders) == 1:
        existing = existing_stop_orders[0]
        qty_matches = int(existing.qty) == target_qty
        price_matches = abs(existing.stop_price - stop_price) / stop_price <= price_tolerance
        if qty_matches and price_matches:
            return ProtectiveStopPlan(action="noop", symbol=symbol, whole_qty=target_qty, stop_price=stop_price)

    if not existing_stop_orders:
        return ProtectiveStopPlan(action="create", symbol=symbol, whole_qty=target_qty, stop_price=stop_price)

    cancel_ids = tuple(o.id for o in existing_stop_orders)
    return ProtectiveStopPlan(
        action="replace", symbol=symbol, whole_qty=target_qty, stop_price=stop_price, cancel_order_ids=cancel_ids,
    )
```

- [ ] **Step 4 — Thread `qty_available` from the Alpaca position.** In the same file, in `build_protective_stop_plans`, replace the `for p in positions:` loop body (the block that appends `plan_protective_stop(...)`) with:

```python
    for p in positions:
        symbol = p.symbol
        held_symbols.add(symbol)
        _qa_raw = getattr(p, "qty_available", None)
        _qty_available = float(_qa_raw) if _qa_raw is not None else float(p.qty)
        plans.append(
            plan_protective_stop(
                symbol=symbol,
                position_qty=float(p.qty),
                avg_entry_price=float(p.avg_entry_price),
                strategy=strategy_by_symbol.get(symbol),
                current_sigma_eff=sigma_by_symbol.get(symbol),
                stop_policy=stop_policy,
                cycle_ts=cycle_ts,
                existing_stop_orders=stop_orders_by_symbol.get(symbol, []),
                qty_available=_qty_available,
            )
        )
```

- [ ] **Step 5 — Handle the new action in the executor.** In `execute_protective_stop_plans`, find the branch:

```python
        if plan.action == "skip_no_whole_share":
            summary["skipped"] += 1
            continue
```

and replace it with:

```python
        if plan.action in ("skip_no_whole_share", "skip_insufficient_qty"):
            summary["skipped"] += 1
            continue
```

- [ ] **Step 6 — Run the new tests, confirm they pass.**

Run: `uv run pytest tests/portfolio/test_fractional_stop_orders.py -v`
Expected: PASS — all tests in the file green (new class + all pre-existing tests).

- [ ] **Step 7 — Commit.**

```bash
git add src/portfolio/fractional_stop_orders.py tests/portfolio/test_fractional_stop_orders.py
git commit -m "fix(#113): size fractional protective stop against qty_available

Stop was sized to the whole-share floor of the full position, so shares
reserved by another open order caused Alpaca 40310000 and left the position
briefly unprotected. Size against qty_available (adding back the qty held by
the existing stops we cancel this cycle); skip cleanly when nothing is placeable.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

- [ ] **Step 8 — Full suite + PR.** `uv run pytest -q` green, then open PR with `closes #113`.

---

## BUG 2 — #111: single-model responses are mislabeled as full ensemble and pass every reliability guard

**Branch:** `fix/111-single-model-labeling`

### Root cause (verified)
In `src/workers/sentiment.py`, when the ensemble aggregation succeeds it always builds `model_id=f"ensemble:{'+'.join(aggregated.model_ids)}"` with `fallback_used=False` — **even when only one model actually responded** (the other timed out). A single-model read has no cross-model agreement signal but is stored looking like a full-reliability ensemble, so it passes every guard that keys on `fallback_used` (the #108 BUY-ranking filter, the reversal-SELL exclusion). Over a 7-day sample, 34% of signals were secretly single-model; the 10%-NAV concentration trade (#81) rode a gpt-oss-only read.

### Fix approach (no migration)
Introduce a small pure helper that maps the contributing model list to `(model_id, fallback_used, reasoning)`:
- **≥2 models** → `ensemble:a+b`, `fallback_used=False` (unchanged).
- **<2 models** → `single:<model>`, `fallback_used=True`, reasoning prefixed `[single-model:<model>]`.

Setting `fallback_used=True` routes single-model reads through **every** existing low-reliability gate with zero new guard sites. The distinct `single:` prefix keeps them separable from FinBERT (`finbert`) in metrics. No consumer parses the `ensemble:` prefix (verified), and no column changes.

**Intended side effects (call these out in the PR body):** single-model reads are now (a) dropped from S4 BUY ranking by the #108 filter, (b) excluded from reversal SELL, (c) excluded from the forward-return/ICIR performance query (`pg_store` selects `WHERE fallback_used = FALSE`), and (d) counted in `fallback_used` aggregates. All four are desired — a single-model read has no agreement signal and should not carry ensemble trust. Dashboards that want a FinBERT-only rate should filter `model_id = 'finbert'`.

### Files
- Modify: `src/workers/sentiment.py` (add helper; use it in the aggregated-success return)
- Test: create `tests/workers/test_single_model_labeling.py`

### Steps

- [ ] **Step 1 — Write the failing test.** Create `tests/workers/test_single_model_labeling.py`:

```python
"""#111: single-model reads must be labeled 'single:<model>' and gated like a
fallback (fallback_used=True), never mislabeled as a full ensemble."""
from src.workers.sentiment import _label_from_model_count


def test_two_models_is_ensemble():
    mid, fb, reasoning = _label_from_model_count(
        ["glm-5.2:cloud", "gpt-oss:20b-cloud"], "bull case"
    )
    assert mid == "ensemble:glm-5.2:cloud+gpt-oss:20b-cloud"
    assert fb is False
    assert reasoning == "bull case"


def test_single_model_labeled_and_gated():
    mid, fb, reasoning = _label_from_model_count(["gpt-oss:20b-cloud"], "bull case")
    assert mid == "single:gpt-oss:20b-cloud"
    assert fb is True
    assert reasoning == "[single-model:gpt-oss:20b-cloud] bull case"


def test_empty_model_ids_defensive():
    mid, fb, reasoning = _label_from_model_count([], "x")
    assert mid == "single:unknown"
    assert fb is True
```

- [ ] **Step 2 — Run it, confirm it fails.**

Run: `uv run pytest tests/workers/test_single_model_labeling.py -v`
Expected: FAIL — `ImportError: cannot import name '_label_from_model_count'`.

- [ ] **Step 3 — Add the helper.** In `src/workers/sentiment.py`, add this function at module scope (e.g. directly above the function that contains the `model_id=f"ensemble:..."` return — near line 220):

```python
def _label_from_model_count(model_ids: list[str], reasoning: str) -> tuple[str, bool, str]:
    """#111: a single-model read has no cross-model agreement signal, so it must
    not be labeled or trusted as a full ensemble. Return (model_id, fallback_used,
    reasoning): a <2-model aggregate is tagged 'single:<model>' with
    fallback_used=True so it is gated everywhere a FinBERT fallback is gated
    (BUY ranking #108, reversal SELL exclusion), while staying distinguishable
    from FinBERT (model_id='finbert') in metrics via the 'single:' prefix."""
    if len(model_ids) < 2:
        m = model_ids[0] if model_ids else "unknown"
        return f"single:{m}", True, f"[single-model:{m}] {reasoning}"
    return f"ensemble:{'+'.join(model_ids)}", False, reasoning
```

- [ ] **Step 4 — Use the helper in the aggregated-success return.** In `src/workers/sentiment.py`, find the success `return SentimentResult(...)` block that currently reads (around lines 282–291):

```python
        return SentimentResult(
            symbol=clean_symbol,
            score=max(-1.0, min(1.0, score)),
            confidence=aggregated.confidence,
            reasoning=aggregated.reasoning,
            model_id=f"ensemble:{'+'.join(aggregated.model_ids)}",
            ensemble_std=aggregated.ensemble_std,
            fallback_used=False,
            published_at=item.timestamp,
        ), raw_outputs
```

and replace it with:

```python
        _model_id, _fallback_used, _reasoning = _label_from_model_count(
            list(aggregated.model_ids), aggregated.reasoning
        )
        return SentimentResult(
            symbol=clean_symbol,
            score=max(-1.0, min(1.0, score)),
            confidence=aggregated.confidence,
            reasoning=_reasoning,
            model_id=_model_id,
            ensemble_std=aggregated.ensemble_std,
            fallback_used=_fallback_used,
            published_at=item.timestamp,
        ), raw_outputs
```

- [ ] **Step 5 — Run the new test, confirm it passes.**

Run: `uv run pytest tests/workers/test_single_model_labeling.py -v`
Expected: PASS.

- [ ] **Step 6 — Run the sentiment worker test module and fix any test that asserted the buggy behavior.**

Run: `uv run pytest tests/workers/test_sentiment_worker.py -v`
Expected: PASS. If a test fails **because it mocked a single model and asserted `model_id` started with `ensemble:` / `fallback_used is False`**, that test encoded the bug — update it to assert `single:` / `fallback_used is True`, and note it in the PR body. Do NOT change any test where two models were mocked.

- [ ] **Step 7 — Commit.**

```bash
git add src/workers/sentiment.py tests/workers/test_single_model_labeling.py
git commit -m "fix(#111): label single-model reads as single: + gate like fallback

A one-model aggregate (other model timed out) was stored as ensemble:*/
fallback_used=false and passed every reliability guard. Tag it single:<model>
with fallback_used=true so it is gated everywhere a FinBERT fallback is,
while remaining distinguishable from FinBERT in metrics.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

- [ ] **Step 8 — Full suite + PR.** `uv run pytest -q` green, then open PR with `closes #111`.

---

## BUG 3 — #107: combined_drawdown is trade-return-based, not equity — risks a spurious CRITICAL alert

**Branch:** `fix/107-equity-drawdown-alert`

### Root cause (verified)
`compute_risk_report` (`src/workers/risk_monitor_task.py`) feeds the risk monitor a returns series that is `portfolio_daily_state.daily_return = SUM(net_pnl)/SUM(entry_notional)` per day — the return on **notional traded that day**, not on account equity. `PortfolioRiskMonitor.compute_report` then takes the compounded max-drawdown of that series as `combined_drawdown`, and `_check_alerts` fires a **CRITICAL** when it exceeds `_COMBINED_DRAWDOWN_CRITICAL = 0.15`. On 2026-07-22 that number read 9.38% and climbing while the real account drawdown from the clean $110,307 baseline (2026-07-04) was ~0.4%. So the CRITICAL alert can fire on a number that is not portfolio drawdown at all.

### Fix approach (Issue option 1, no migration)
Compute the alert's drawdown from the **real account-equity curve** instead of the trade-return series:
- New pure function `max_drawdown_from_equity(equity_curve)` (peak-to-trough on equity **levels**).
- New `_fetch_equity_curve(pg, current_equity)`: historical `risk_reports.nav` (`nav > 0`, `timestamp::date >= baseline`) + the current live equity appended. Anchored at a config baseline date to exclude pre-baseline garbage NAV. On any error / <2 points → returns a short curve → drawdown 0.0 (fail-safe: never fire CRITICAL on missing data).
- `compute_report` gains an optional `combined_drawdown_override`; when provided it is used for both the `combined_drawdown` field and the CRITICAL check, bypassing the trade-return series.
- Config: `RISK_DRAWDOWN_BASELINE_DATE` (default `"2026-07-04"`).

### Files
- Modify: `src/portfolio/risk_monitor.py` (add `max_drawdown_from_equity`; add override param to `compute_report`)
- Modify: `src/workers/risk_monitor_task.py` (add `_fetch_equity_curve`; wire override)
- Modify: `src/config.py` (add `RISK_DRAWDOWN_BASELINE_DATE`)
- Test: `tests/portfolio/test_risk_monitor.py` (drawdown fn + override alert behavior)

### Steps

- [ ] **Step 1 — Write the failing tests for the pure pieces.** Append to `tests/portfolio/test_risk_monitor.py`:

```python
class TestEquityDrawdown:
    """#107: alert drawdown must come from the equity level curve."""

    def test_monotonic_increase_has_no_drawdown(self):
        from src.portfolio.risk_monitor import max_drawdown_from_equity
        assert max_drawdown_from_equity([100.0, 110.0, 120.0]) == 0.0

    def test_peak_to_trough(self):
        from src.portfolio.risk_monitor import max_drawdown_from_equity
        # peak 120 → trough 90 → 25%
        assert max_drawdown_from_equity([100.0, 120.0, 90.0, 110.0]) == 0.25

    def test_needs_two_positive_points(self):
        from src.portfolio.risk_monitor import max_drawdown_from_equity
        assert max_drawdown_from_equity([100.0]) == 0.0
        assert max_drawdown_from_equity([]) == 0.0

    def test_ignores_nonpositive_points(self):
        from src.portfolio.risk_monitor import max_drawdown_from_equity
        # only [100, 90] count → 10%
        assert max_drawdown_from_equity([0.0, -5.0, 100.0, 90.0]) == pytest.approx(0.10)


class TestCombinedDrawdownOverride:
    """#107: when an equity-derived drawdown override is supplied it drives the
    field and the CRITICAL alert, not the trade-return series."""

    def test_override_above_threshold_fires_critical(self):
        from src.portfolio.risk_monitor import AlertLevel
        report = _make_report(combined_drawdown_override=0.20)
        assert report.combined_drawdown == 0.20
        assert any(a.level == AlertLevel.CRITICAL for a in report.alerts)

    def test_override_below_threshold_no_critical(self):
        from src.portfolio.risk_monitor import AlertLevel
        report = _make_report(combined_drawdown_override=0.10)
        assert report.combined_drawdown == 0.10
        assert not any(a.level == AlertLevel.CRITICAL for a in report.alerts)
```

(`pytest` is already imported at the top of this test file. `_make_report` is the existing helper at line 41 and forwards `**kwargs` to `compute_report`.)

- [ ] **Step 2 — Run, confirm failure.**

Run: `uv run pytest tests/portfolio/test_risk_monitor.py::TestEquityDrawdown tests/portfolio/test_risk_monitor.py::TestCombinedDrawdownOverride -v`
Expected: FAIL — `cannot import name 'max_drawdown_from_equity'` and `compute_report() got an unexpected keyword argument 'combined_drawdown_override'`.

- [ ] **Step 3 — Add the pure drawdown function.** In `src/portfolio/risk_monitor.py`, add after `_compute_drawdown` (around line 67):

```python
def max_drawdown_from_equity(equity_curve: list[float]) -> float:
    """Peak-to-trough max drawdown of an equity LEVEL series (non-negative fraction).

    Distinct from _compute_drawdown, which consumes a *returns* series. This
    feeds the CRITICAL portfolio-drawdown alert (#107), so it must reflect real
    account equity, not trade-notional returns. Non-positive points are ignored;
    fewer than two usable points → 0.0 (fail-safe: no drawdown asserted).
    """
    levels = [e for e in equity_curve if e and e > 0]
    if len(levels) < 2:
        return 0.0
    peak = levels[0]
    max_dd = 0.0
    for e in levels:
        if e > peak:
            peak = e
        dd = (peak - e) / peak
        if dd > max_dd:
            max_dd = dd
    return float(max_dd)
```

- [ ] **Step 4 — Add the override parameter to `compute_report`.** In `src/portfolio/risk_monitor.py`, change the `compute_report` signature to add the keyword-only override at the end of its parameter list:

```python
    def compute_report(
        self,
        strategy_returns: dict[str, list[float]],
        current_weights: dict[str, float],
        total_exposure: float,
        nav: float,
        combined_drawdown_override: float | None = None,
    ) -> RiskReport:
```

Then find these two lines inside `compute_report`:

```python
        combined_rets = _combined_returns(strategy_returns, current_weights)
        combined_dd = _compute_drawdown(combined_rets)
```

and replace them with:

```python
        if combined_drawdown_override is not None:
            combined_dd = combined_drawdown_override
        else:
            combined_rets = _combined_returns(strategy_returns, current_weights)
            combined_dd = _compute_drawdown(combined_rets)
```

- [ ] **Step 5 — Run the pure/override tests, confirm pass.**

Run: `uv run pytest tests/portfolio/test_risk_monitor.py -v`
Expected: PASS (new classes + all pre-existing tests).

- [ ] **Step 6 — Add the config baseline.** In `src/config.py`, add this field immediately after the `SENTIMENT_REVERSAL_REENTRY_COOLDOWN_HOURS` field block (which closes with `)` at line ~254), before the `# Signal velocity:` comment:

```python

    # #107: real account-equity drawdown baseline. The risk-monitor CRITICAL
    # drawdown alert measures peak-to-trough over risk_reports.nav on/after this
    # date, excluding pre-baseline garbage NAV. YYYY-MM-DD.
    RISK_DRAWDOWN_BASELINE_DATE: str = Field(
        default_factory=lambda: os.environ.get("RISK_DRAWDOWN_BASELINE_DATE", "2026-07-04")
    )
```

- [ ] **Step 7 — Add `_fetch_equity_curve` and wire the override.** In `src/workers/risk_monitor_task.py`, add this function next to `_fetch_account_state` (after line ~114):

```python
def _fetch_equity_curve(pg, current_equity: float) -> list[float]:
    """Real account-equity curve for the drawdown alert (#107).

    Historical NAV from risk_reports (nav > 0, on/after the clean baseline date)
    plus the current live equity appended. Anchoring at the baseline excludes
    pre-baseline garbage NAV. On error / empty → returns whatever it has (caller
    reports 0 drawdown for <2 points: fail-safe, never a spurious CRITICAL).
    """
    from src.config import config

    baseline = getattr(config, "RISK_DRAWDOWN_BASELINE_DATE", "2026-07-04")
    curve: list[float] = []
    try:
        conn = pg._get_connection()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT nav FROM risk_reports
                WHERE nav > 0 AND timestamp::date >= %s::date
                ORDER BY timestamp ASC
                """,
                (baseline,),
            )
            curve = [float(r[0]) for r in cur.fetchall()]
    except Exception as e:
        log.warning("Could not fetch equity curve for drawdown (#107): %s", e)
        curve = []
    if current_equity and current_equity > 0:
        curve.append(float(current_equity))
    return curve
```

Then, in `compute_risk_report`, find the block that builds the report:

```python
        report = monitor.compute_report(
            strategy_returns=strategy_returns,
            current_weights=current_weights,
            total_exposure=total_exposure,
            nav=nav,
        )
```

and replace it with:

```python
        from src.portfolio.risk_monitor import max_drawdown_from_equity

        equity_curve = _fetch_equity_curve(pg, nav)
        equity_dd = max_drawdown_from_equity(equity_curve)

        report = monitor.compute_report(
            strategy_returns=strategy_returns,
            current_weights=current_weights,
            total_exposure=total_exposure,
            nav=nav,
            combined_drawdown_override=equity_dd,
        )
```

- [ ] **Step 8 — Write a mock-cursor test for `_fetch_equity_curve`.** Append to `tests/portfolio/test_risk_monitor.py`:

```python
class TestFetchEquityCurve:
    def test_appends_current_equity_and_drops_bad_rows(self):
        from unittest.mock import MagicMock
        from src.workers.risk_monitor_task import _fetch_equity_curve

        cur = MagicMock()
        cur.fetchall.return_value = [(110_000.0,), (108_000.0,)]
        conn = MagicMock()
        conn.cursor.return_value.__enter__.return_value = cur
        pg = MagicMock()
        pg._get_connection.return_value = conn

        curve = _fetch_equity_curve(pg, current_equity=109_000.0)
        assert curve == [110_000.0, 108_000.0, 109_000.0]

    def test_db_error_returns_current_equity_only(self):
        from unittest.mock import MagicMock
        from src.workers.risk_monitor_task import _fetch_equity_curve

        pg = MagicMock()
        pg._get_connection.side_effect = RuntimeError("db down")
        curve = _fetch_equity_curve(pg, current_equity=109_000.0)
        assert curve == [109_000.0]
```

- [ ] **Step 9 — Run everything for this bug, confirm pass.**

Run: `uv run pytest tests/portfolio/test_risk_monitor.py -v`
Expected: PASS. Also import-check the task module: `uv run python -c "import src.workers.risk_monitor_task"` → no error.

- [ ] **Step 10 — Commit.**

```bash
git add src/portfolio/risk_monitor.py src/workers/risk_monitor_task.py src/config.py tests/portfolio/test_risk_monitor.py
git commit -m "fix(#107): base combined_drawdown alert on real equity curve

The CRITICAL drawdown alert measured max-drawdown of a trade-notional return
series (SUM(net_pnl)/SUM(entry_notional)), which read ~9% while real account
drawdown was ~0.4%. Compute it from the risk_reports.nav equity curve (>= clean
baseline) + current equity; fail-safe to 0 on missing data.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

- [ ] **Step 11 — Full suite + PR.** `uv run pytest -q` green, then open PR with `closes #107`.

---

## BUG 4 — #110: regression lock for the fallback re-buy after a reversal exit

**Branch:** `test/110-fallback-rebuy-regression`

### Important context — read before doing anything
The incident reported in #110 (WDC reversal-sold on an ensemble −0.385, then re-bought after cooldown on a weaker FinBERT **fallback** +0.363) is **already structurally prevented** by fix #108 (merged 2026-07-22), which drops FinBERT-fallback signals from S4 BUY ranking (`_filter_fallback_signals`, `src/workers/portfolio_scheduler.py:3005`), combined with the #68 reversal cooldown that blocks any re-buy during the 2h window (`portfolio_scheduler.py:3244`). S1/S2 do not rank on sentiment signals at all. So the reported re-buy path no longer exists.

**Therefore this bug does NOT get a behavioral code change.** The #108 BUY-side filter shipped without its own regression test — your job is to add that missing test so the protection can't silently regress, then the reviewer closes #110 as covered. **Do not** add a new re-entry guard, change cooldown TTLs, or touch trading logic. If after reading the code you believe a real gap remains, STOP and write your finding in the PR description instead of coding — the reviewer will decide.

### Files
- Test only: create `tests/workers/test_fallback_buy_guard.py`

### Steps

- [ ] **Step 1 — Write the regression test.** Create `tests/workers/test_fallback_buy_guard.py`:

```python
"""#110/#108 regression lock: a FinBERT-fallback signal must never survive into
BUY ranking. Combined with the #68 reversal cooldown (blocks re-buy during the
window) and S4-only sentiment ranking, this prevents re-buying a reversal-sold
name on a weaker contradicting fallback signal (WDC, 2026-07-21). Behavior is
locked by test; do not weaken _filter_fallback_signals without updating this."""
from types import SimpleNamespace

from src.workers.portfolio_scheduler import _filter_fallback_signals


def _sig(symbol, fallback_used):
    return SimpleNamespace(symbol=symbol, fallback_used=fallback_used)


def test_fallback_signal_is_dropped_from_buy_ranking():
    ensemble = _sig("WDC", fallback_used=False)
    fallback = _sig("WDC", fallback_used=True)
    non_fallback, dropped = _filter_fallback_signals([ensemble, fallback])
    assert ensemble in non_fallback
    assert fallback not in non_fallback
    assert dropped == [fallback]


def test_all_ensemble_signals_pass_through():
    a = _sig("AAA", fallback_used=False)
    b = _sig("BBB", fallback_used=False)
    non_fallback, dropped = _filter_fallback_signals([a, b])
    assert non_fallback == [a, b]
    assert dropped == []


def test_missing_attribute_treated_as_non_fallback():
    # Defensive: a signal object without the attribute must not be dropped.
    s = SimpleNamespace(symbol="XYZ")
    non_fallback, dropped = _filter_fallback_signals([s])
    assert non_fallback == [s]
    assert dropped == []
```

- [ ] **Step 2 — Run it, confirm it passes against current code.**

Run: `uv run pytest tests/workers/test_fallback_buy_guard.py -v`
Expected: PASS immediately (this locks existing #108 behavior; it is a characterization test, so it passes without any source change). If any assertion FAILS, that is a real finding — stop and report it in the PR, do not "fix" the source.

- [ ] **Step 3 — Commit.**

```bash
git add tests/workers/test_fallback_buy_guard.py
git commit -m "test(#110): regression-lock the #108 fallback BUY-ranking guard

The #110 incident (re-buy of a reversal-sold name on a weaker FinBERT-fallback
signal) is already prevented by #108 (drops fallback from S4 BUY ranking) plus
the #68 reversal cooldown. #108 shipped without a test; lock it so it can't
silently regress.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

- [ ] **Step 4 — PR.** Open PR. Body must state: "#110 is covered by the merged #108 + #68; this PR adds the missing regression test. Recommend closing #110 as covered." Use `closes #110` only if the reviewer confirms; otherwise reference `#110` and let the reviewer close it.

---

## Hand-back checklist (for the human reviewer)

Four independent PRs, review each on its own:

1. **#113** — `plan_protective_stop` sizes to `qty_available` (+ existing-stop add-back); new `skip_insufficient_qty` action; `build_protective_stop_plans` reads `p.qty_available`. Verify: replacement stop is not under-sized when the position's own stop reserves the shares; skip path can't leave a placeable position unprotected two cycles running.
2. **#111** — single-model → `single:<model>` + `fallback_used=True`. Verify the four intended side effects are acceptable (esp. that single-model reads now drop out of the ICIR/forward-return `fallback_used = FALSE` query and inflate `fallback_used` aggregates). Confirm no consumer relied on the old `ensemble:` labeling of single-model reads.
3. **#107** — alert now driven by `risk_reports.nav` equity curve + current equity, anchored at `RISK_DRAWDOWN_BASELINE_DATE`. Verify fail-safe (missing/short curve → 0, no CRITICAL) and that the daily-granularity NAV curve is acceptable vs. Alpaca portfolio-history (documented tradeoff: no new external API surface). Consider whether the now-unused trade-return drawdown should still be logged under a separate name.
4. **#110** — test-only; confirm the characterization test matches intended behavior, then close #110 as covered by #108/#68. **Open decision for the operator (not for Kimi):** whether to additionally require a *positive ensemble* read (not merely a non-fallback signal) before re-entering a just-reversed name. That is a behavioral change to the money path and must be measured + operator-approved — spec it separately if wanted.
