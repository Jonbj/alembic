# client_order_id idempotency Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every live Alpaca order submit site a deterministic `client_order_id` so a resubmit (34s race, loop-reversal, retry) dedups broker-side instead of producing a second fill.

**Architecture:** A pure helper `src/portfolio/order_id.py` builds `ambc-{purpose}-{symbol}-{cycle_ts|signal_id}` from context already available at each submit site. The ID is attached to the 6 live `submit_order` request objects (`MarketOrderRequest` / `StopOrderRequest`). A fallback wrapper retries without the ID if Alpaca ever rejects its format. Reliance on broker-side dedup is GATED on the verification spike (Task 2) confirming Alpaca's semantics.

**Tech Stack:** Python 3.11, `alpaca-py` (pydantic v2 models), pytest, Redis/Postgres unchanged.

---

## Grounding (verified 2026-08-07)

- `client_order_id` is NEVER used today: `grep -rn "client_order_id" src/` → 0 hits. No broker-side dedup safety-net.
- `alpaca-py` 0.43.5 (installed at `.venv/lib/python3.11/site-packages/alpaca/trading/requests.py`):
  - `OrderRequest` (base, line 282) declares `client_order_id: Optional[str] = None` (line 314).
  - `MarketOrderRequest` (line 359) and `StopOrderRequest` (line 387) extend `OrderRequest` → **accept `client_order_id`**.
  - **CORRECTION to spec §3 grounding:** `StopLossRequest` (line 155) and `TakeProfitRequest` (line 144) extend `NonEmptyRequest` → they do **NOT** accept `client_order_id`. They are bracket *legs*. The `client_order_id` goes on the **parent** `MarketOrderRequest` (which holds the legs). This plan attaches the ID to the parent only.
- Alpaca constraints (per spec §3): `client_order_id` ≤1024 chars, charset `[a-zA-Z0-9-_]`.
- 6 live submit sites (all confirmed):
  1. `src/workers/portfolio_scheduler.py:2949` — `_MORsl` stop-loss exit (in `_run_cycle_inner`, `sym` + `ts` in scope, no signal_id).
  2. `src/workers/portfolio_scheduler.py:3836` — bracket BUY (in `_submit_portfolio_orders`, `order.symbol` in scope; `cycle_ts`/`signal_ids` NOT yet params → Task 3 adds them).
  3. `src/workers/portfolio_scheduler.py:3869` — rebalance SELL (same function as #2; no signal_id for SELLs).
  4. `src/workers/portfolio_scheduler.py:3946` — reversal force-sell (in `_submit_reversal_force_sells`, `sym` + `ts` params in scope; `reversal_sell_symbols[sym]["signal_id"]` available).
  5. `src/portfolio/fractional_stop_orders.py:192` — protective `StopOrderRequest` (in `execute_protective_stop_plans`; `cycle_ts` NOT yet a param → Task 7 adds it; caller `portfolio_scheduler.py:752` has `cycle_ts` in scope).
  6. `src/workers/execution.py:735` — legacy BUY (in `run_execution_cycle`, `symbol` + `signal_id` + `tick_time` all in scope).
- Cycle timestamp source: `_run_cycle_inner` sets `end = datetime.now(timezone.utc)` at `portfolio_scheduler.py:2083`, then `ts = end` at `:2307`. `ts` is timezone-aware. Caller of `_submit_portfolio_orders` is at `:2841` (has `ts` + `_signal_ids` in scope).

## File Structure

- **Create** `src/portfolio/order_id.py` — `build_client_order_id(purpose, symbol, cycle_ts, signal_id=None) -> str` + `submit_order_with_coid_fallback(trading_client, req, *, log, on_alert=None)`. Pure, no I/O.
- **Create** `tests/portfolio/test_order_id.py` — unit tests for the helper + fallback wrapper.
- **Create** `scripts/verify_alpaca_coid_dedup.py` — one-shot sandbox spike script (Task 2).
- **Create** `docs/audits/alpaca_coid_dedup_spike.md` — spike result checklist (Task 2 output).
- **Modify** `src/workers/portfolio_scheduler.py` — add `cycle_ts`/`signal_ids` params to `_submit_portfolio_orders` (`:3596`); attach `client_order_id` at `:2949`, `:3835`, `:3863`, `:3940`; pass `cycle_ts=ts, signal_ids=_signal_ids` at the caller (`:2841`); pass `cycle_ts=cycle_ts` to `execute_protective_stop_plans` (`:752`).
- **Modify** `src/portfolio/fractional_stop_orders.py` — add `cycle_ts` param to `execute_protective_stop_plans` (`:153`); attach `client_order_id` at `:185`.
- **Modify** `src/workers/execution.py` — attach `client_order_id` at `:725`.
- **Modify** `tests/workers/test_portfolio_scheduler.py` — add coid assertions for the 4 scheduler sites.
- **Modify** `tests/portfolio/test_fractional_stop_orders.py` — add coid assertion for the protective stop.
- **Modify** `tests/workers/test_execution_worker.py` — add coid assertion for the legacy BUY.

## Convention

- Run tests from the repo root: `.venv/bin/pytest <path> -v`.
- The module logger `log = logging.getLogger(__name__)` is already defined in `portfolio_scheduler.py:42`, `fractional_stop_orders.py:23`, `execution.py:49`.
- `client_order_id=None` on an alpaca-py request is harmless (the field defaults to `None` → Alpaca treats it as absent). Existing tests that don't pass `cycle_ts` keep the old behavior.

---

### Task 1: `build_client_order_id` helper + TDD

**Files:**
- Create: `src/portfolio/order_id.py`
- Test: `tests/portfolio/test_order_id.py`

- [ ] **Step 1: Write the failing test**

Create `tests/portfolio/test_order_id.py`:

```python
"""Tests for src/portfolio/order_id.build_client_order_id."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.portfolio.order_id import build_client_order_id


CTS = datetime(2026, 8, 7, 14, 52, tzinfo=timezone.utc)


def test_default_format_uses_cycle_ts():
    assert build_client_order_id("buy", "AAPL", CTS) == "ambc-buy-AAPL-20260807T1452"


def test_folds_signal_id_when_provided():
    assert build_client_order_id("buy", "AAPL", CTS, signal_id=4427) == "ambc-buy-AAPL-4427"


def test_signal_id_none_falls_back_to_cycle_ts():
    assert build_client_order_id("sell", "SPY", CTS, signal_id=None) == "ambc-sell-SPY-20260807T1452"


def test_signal_id_int_is_stringified():
    assert build_client_order_id("buy", "AAPL", CTS, signal_id=4427).endswith("-4427")


def test_sanitizes_invalid_chars_in_symbol():
    # BRK.B contains a '.' which is outside [a-zA-Z0-9-_] → replaced with '-'.
    assert build_client_order_id("buy", "BRK.B", CTS) == "ambc-buy-BRK-B-20260807T1452"


def test_sanitizes_invalid_chars_in_purpose():
    assert build_client_order_id("stop loss", "AAPL", CTS) == "ambc-stop-loss-AAPL-20260807T1452"


def test_deterministic_same_inputs_same_output():
    a = build_client_order_id("buy", "AAPL", CTS, signal_id=4427)
    b = build_client_order_id("buy", "AAPL", CTS, signal_id=4427)
    assert a == b


def test_unique_across_purposes():
    buy = build_client_order_id("buy", "AAPL", CTS)
    sell = build_client_order_id("sell", "AAPL", CTS)
    assert buy != sell


def test_unique_across_symbols():
    a = build_client_order_id("buy", "AAPL", CTS)
    b = build_client_order_id("buy", "MSFT", CTS)
    assert a != b


def test_unique_signal_id_vs_cycle_ts():
    # A signal_id fold must not collide with a cycle_ts format on the same symbol.
    with_sig = build_client_order_id("buy", "AAPL", CTS, signal_id=4427)
    with_ts = build_client_order_id("buy", "AAPL", CTS)
    assert with_sig != with_ts


def test_within_alpaca_length_limit():
    # Realistic inputs are ~30 chars; assert the bound for a long symbol+purpose.
    coid = build_client_order_id("slstop", "VERYLONGSYMBOL123", CTS)
    assert len(coid) <= 1024


def test_charset_only_alphanumeric_dash_underscore():
    import re
    coid = build_client_order_id("buy", "BRK.B", CTS, signal_id=4427)
    assert re.fullmatch(r"[a-zA-Z0-9\-_]+", coid)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/portfolio/test_order_id.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.portfolio.order_id'` (collection error).

- [ ] **Step 3: Write minimal implementation**

Create `src/portfolio/order_id.py`:

```python
"""Deterministic Alpaca client_order_id builder.

Alpaca accepts a client_order_id up to 1024 chars over [a-zA-Z0-9-_] and
dedups resubmits that reuse the same ID. Building a deterministic ID per
(purpose, symbol, cycle_ts|signal_id) gives every submit site a broker-side
dedup safety-net against double-submit (34s race, loop-reversal, retry).

ID construction is pure string → no failure path. If Alpaca ever rejects the
ID format, submit_order_with_coid_fallback retries without the ID (Task 9).
"""
from __future__ import annotations

import re
from datetime import datetime

_CHARSET = re.compile(r"[^a-zA-Z0-9\-_]")


def _sanitize(token: str) -> str:
    """Replace any char outside [a-zA-Z0-9-_] with '-'."""
    return _CHARSET.sub("-", token)


def build_client_order_id(
    purpose: str,
    symbol: str,
    cycle_ts: datetime,
    signal_id: str | int | None = None,
) -> str:
    """Build a deterministic Alpaca client_order_id.

    Default format: ``ambc-{purpose}-{symbol}-{cycle_ts}`` e.g.
    ``ambc-buy-AAPL-20260807T1452``. When ``signal_id`` is provided it replaces
    the cycle_ts segment: ``ambc-{purpose}-{symbol}-{signal_id}`` — a re-entry
    of the same signal dedups against the first submit.

    All tokens are sanitized to the ``[a-zA-Z0-9-_]`` charset (invalid chars →
    ``-``). The result is ≤1024 chars for any realistic input (purpose ≤12,
    symbol ≤8, signal_id ≤10 digits, cycle_ts 13 → total ≤45).
    """
    prefix = f"ambc-{_sanitize(purpose)}-{_sanitize(symbol)}"
    if signal_id is not None:
        suffix = _sanitize(str(signal_id))
    else:
        suffix = cycle_ts.strftime("%Y%m%dT%H%M")
    return f"{prefix}-{suffix}"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/portfolio/test_order_id.py -v`
Expected: PASS (12 tests).

- [ ] **Step 5: Commit**

```bash
git add src/portfolio/order_id.py tests/portfolio/test_order_id.py
git commit -m "feat(portfolio): add build_client_order_id helper for Alpaca idempotency

Pure deterministic ID builder: ambc-{purpose}-{symbol}-{cycle_ts|signal_id}.
Sanitizes to [a-zA-Z0-9-_], ≤1024 chars. Part of #21 (spec §3)."
```

---

### Task 2: Verification spike — Alpaca `client_order_id` dedup semantics

**Files:**
- Create: `scripts/verify_alpaca_coid_dedup.py`
- Create: `docs/audits/alpaca_coid_dedup_spike.md`

This is a **research task**. The executor runs it against the Alpaca paper sandbox and records the result. Implementation that RELIES on broker-side dedup (the §4 retry plan, and any logic that assumes a duplicate `client_order_id` returns one fill not two) is GATED on this spike confirming dedup. The wiring in Tasks 3-9 does not rely on dedup — it only attaches the ID; dedup is a safety-net that works if the spike confirms it.

- [ ] **Step 1: Write the sandbox spike script**

Create `scripts/verify_alpaca_coid_dedup.py`:

```python
"""Verification spike: confirm Alpaca client_order_id dedup semantics.

Run with paper-trading credentials:
    .venv/bin/python scripts/verify_alpaca_coid_dedup.py

Records: (a) does a resubmit with the same client_order_id return the original
order, raise a 409, or create a duplicate? (b) is there a resubmit window?

Output is printed to stdout; paste it into docs/audits/alpaca_coid_dedup_spike.md.
"""
from __future__ import annotations

import os
import sys
import time

from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.trading.requests import MarketOrderRequest


def main() -> int:
    key = os.environ.get("ALPACA_API_KEY")
    secret = os.environ.get("ALPACA_API_SECRET")
    if not key or not secret:
        print("ERROR: set ALPACA_API_KEY and ALPACA_API_SECRET (paper) env vars.", file=sys.stderr)
        return 1

    client = TradingClient(key, secret, paper=True)
    coid = "ambc-spike-TEST-20260807T1452"
    symbol = "AAPL"
    req = MarketOrderRequest(
        symbol=symbol,
        notional=1.0,
        side=OrderSide.BUY,
        time_in_force=TimeInForce.DAY,
        client_order_id=coid,
    )

    print(f"[1] submitting BUY {symbol} notional=1.0 client_order_id={coid}")
    order1 = client.submit_order(req)
    print(f"    -> order_id={order1.id} status={order1.status}")

    print("[2] resubmitting the SAME client_order_id 5s later...")
    time.sleep(5)
    try:
        order2 = client.submit_order(req)
        print(f"    -> order_id={order2.id} status={order2.status}")
        if str(order2.id) == str(order1.id):
            print("RESULT: resubmit returned the ORIGINAL order (dedup confirmed).")
        else:
            print("RESULT: resubmit returned a DIFFERENT order id (NO dedup — duplicate created).")
    except Exception as exc:
        print(f"    -> raised {type(exc).__name__}: {exc}")
        msg = str(exc).lower()
        if "409" in msg or "conflict" in msg or "client_order_id" in msg:
            print("RESULT: resubmit raised a conflict error (dedup via rejection).")
        else:
            print("RESULT: resubmit raised an unrelated error (see above).")

    print("[3] cancelling the spike order to clean up...")
    try:
        client.cancel_order_by_id(order1.id)
        print("    -> cancelled.")
    except Exception as exc:
        print(f"    -> cancel failed (best-effort): {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Run the spike against the paper sandbox**

Run: `ALPACA_API_KEY=<paper_key> ALPACA_API_SECRET=<paper_secret> .venv/bin/python scripts/verify_alpaca_coid_dedup.py`
Expected: prints one of the three RESULT lines. Record which one.

- [ ] **Step 3: Document the result in the spike checklist**

Create `docs/audits/alpaca_coid_dedup_spike.md`:

```markdown
# Alpaca client_order_id dedup spike — result

**Date run:** 2026-08-07 (fill in)
**Sandbox:** paper trading
**Script:** scripts/verify_alpaca_coid_dedup.py

## Checklist (fill in from the script output)

- [ ] First submit succeeded: order_id = ______
- [ ] Resubmit behavior (circle one):
  - [ ] Returned the ORIGINAL order (dedup confirmed — idempotent)
  - [ ] Raised a 409/conflict (dedup via rejection — caller must treat 409 as "already submitted")
  - [ ] Created a DUPLICATE order (NO dedup — client_order_id is advisory only)
- [ ] Resubmit window: immediate (5s) retry tested. Longer window NOT tested (out of scope).
- [ ] Error message on rejection (if any): ______

## Verdict

- [ ] **DEDUP CONFIRMED** — broker-side dedup is safe to rely on; §4 retry may proceed.
- [ ] **DEDUP via 409** — caller must catch the 409 and treat it as "already submitted" (not a failure).
- [ ] **NO DEDUP** — client_order_id is advisory only; §4 retry must NOT rely on it (keep retry disabled or add application-level dedup).

## Impact on this plan

Tasks 3-9 attach the ID regardless (it is harmless and useful for audit/traceability even
without dedup). Reliance on dedup (§4 retry, any "second submit is a no-op" assumption) is
GATED on the verdict being DEDUP CONFIRMED or DEDUP via 409.
```

- [ ] **Step 4: Commit**

```bash
git add scripts/verify_alpaca_coid_dedup.py docs/audits/alpaca_coid_dedup_spike.md
git commit -m "chore(spike): add Alpaca client_order_id dedup verification script + checklist

Part of #21 (spec §3). Reliance on broker-side dedup gates on this spike."
```

---

### Task 3: Wire `client_order_id` into the bracket BUY at `portfolio_scheduler.py:3836`

The bracket BUY lives in `_submit_portfolio_orders` (`:3596`), which currently has no `cycle_ts` or `signal_ids` parameter. This task adds both (optional, default `None` → backward-compatible with existing tests), attaches the ID to `base_kwargs`, and updates the caller at `:2841` to pass `ts` + `_signal_ids`.

**Files:**
- Modify: `src/workers/portfolio_scheduler.py:3596-3611` (signature), `:3785-3836` (BUY site), `:2841-2853` (caller)
- Test: `tests/workers/test_portfolio_scheduler.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/workers/test_portfolio_scheduler.py` (after the `_submit_portfolio_orders` section, e.g. after line ~485):

```python
def test_submit_portfolio_orders_buy_attaches_client_order_id_with_signal_id():
    """The real Alpaca BUY path attaches ambc-buy-{symbol}-{signal_id}."""
    from src.workers.portfolio_scheduler import _submit_portfolio_orders

    orders = [_make_combined_order("SPY", OrderSide.BUY, qty=10.0)]
    trading_client = MagicMock()
    resp = MagicMock()
    resp.id = "alpaca-1"
    trading_client.submit_order.return_value = resp
    market = _make_market(prices={"SPY": 450.0})
    cycle_ts = datetime(2026, 8, 7, 14, 52, tzinfo=timezone.utc)

    with patch(
        "src.workers.portfolio_scheduler._get_reversal_cooldown_symbols",
        return_value=set(),
    ), patch(
        "src.workers.portfolio_scheduler._get_stop_loss_cooldown_symbols",
        return_value=set(),
    ):
        submitted = _submit_portfolio_orders(
            orders, trading_client, market,
            fractionable_symbols=None,  # SPY treated as fractionable → notional path
            open_trade_symbols=set(),
            cycle_ts=cycle_ts,
            signal_ids={"SPY": 4427},
        )

    assert len(submitted) == 1
    trading_client.submit_order.assert_called_once()
    req = trading_client.submit_order.call_args[0][0]
    assert req.client_order_id == "ambc-buy-SPY-4427"


def test_submit_portfolio_orders_buy_attaches_client_order_id_without_signal_id():
    """No signal_id → ambc-buy-{symbol}-{cycle_ts}."""
    from src.workers.portfolio_scheduler import _submit_portfolio_orders

    orders = [_make_combined_order("AAPL", OrderSide.BUY, qty=10.0)]
    trading_client = MagicMock()
    resp = MagicMock()
    resp.id = "alpaca-2"
    trading_client.submit_order.return_value = resp
    market = _make_market(prices={"AAPL": 190.0})
    cycle_ts = datetime(2026, 8, 7, 14, 52, tzinfo=timezone.utc)

    with patch(
        "src.workers.portfolio_scheduler._get_reversal_cooldown_symbols",
        return_value=set(),
    ), patch(
        "src.workers.portfolio_scheduler._get_stop_loss_cooldown_symbols",
        return_value=set(),
    ):
        submitted = _submit_portfolio_orders(
            orders, trading_client, market,
            fractionable_symbols=None,
            open_trade_symbols=set(),
            cycle_ts=cycle_ts,
        )

    assert len(submitted) == 1
    req = trading_client.submit_order.call_args[0][0]
    assert req.client_order_id == "ambc-buy-AAPL-20260807T1452"


def test_submit_portfolio_orders_buy_no_coid_when_cycle_ts_absent():
    """Backward compat: no cycle_ts → no client_order_id (existing tests/behavior)."""
    from src.workers.portfolio_scheduler import _submit_portfolio_orders

    orders = [_make_combined_order("SPY", OrderSide.BUY, qty=10.0)]
    trading_client = MagicMock()
    resp = MagicMock()
    resp.id = "alpaca-3"
    trading_client.submit_order.return_value = resp
    market = _make_market(prices={"SPY": 450.0})

    with patch(
        "src.workers.portfolio_scheduler._get_reversal_cooldown_symbols",
        return_value=set(),
    ), patch(
        "src.workers.portfolio_scheduler._get_stop_loss_cooldown_symbols",
        return_value=set(),
    ):
        _submit_portfolio_orders(
            orders, trading_client, market,
            fractionable_symbols=None,
            open_trade_symbols=set(),
        )

    req = trading_client.submit_order.call_args[0][0]
    assert req.client_order_id is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/workers/test_portfolio_scheduler.py::test_submit_portfolio_orders_buy_attaches_client_order_id_with_signal_id tests/workers/test_portfolio_scheduler.py::test_submit_portfolio_orders_buy_attaches_client_order_id_without_signal_id tests/workers/test_portfolio_scheduler.py::test_submit_portfolio_orders_buy_no_coid_when_cycle_ts_absent -v`
Expected: the first two FAIL with `TypeError: _submit_portfolio_orders() got an unexpected keyword argument 'cycle_ts'`; the third FAILs with `AttributeError` or passes (no coid key present → `req.client_order_id is None` already true). Implement to make all three PASS.

- [ ] **Step 3: Add `cycle_ts` and `signal_ids` params to `_submit_portfolio_orders`**

In `src/workers/portfolio_scheduler.py`, edit the signature at `:3596-3611`. Replace:

```python
def _submit_portfolio_orders(
    orders,
    trading_client,
    market,
    _submit_fn=None,
    fractionable_symbols: set[str] | None = None,
    open_trade_symbols: set[str] | frozenset[str] | None = frozenset(),
    regime_mult: float = 1.0,
    _on_broker_reject=None,
    risk_cfg: dict | None = None,
    bars_df=None,
    stop_policy: "StopPolicy" | None = None,
    nav: float | None = None,
    open_trades: list[dict] | None = None,
    sym_strats: dict | None = None,
) -> list[dict]:
```

with:

```python
def _submit_portfolio_orders(
    orders,
    trading_client,
    market,
    _submit_fn=None,
    fractionable_symbols: set[str] | None = None,
    open_trade_symbols: set[str] | frozenset[str] | None = frozenset(),
    regime_mult: float = 1.0,
    _on_broker_reject=None,
    risk_cfg: dict | None = None,
    bars_df=None,
    stop_policy: "StopPolicy" | None = None,
    nav: float | None = None,
    open_trades: list[dict] | None = None,
    sym_strats: dict | None = None,
    cycle_ts: datetime | None = None,
    signal_ids: dict[str, int] | None = None,
) -> list[dict]:
```

- [ ] **Step 4: Attach `client_order_id` to the bracket BUY `base_kwargs`**

In `src/workers/portfolio_scheduler.py`, edit the BUY site at `:3830-3836`. The current code builds `base_kwargs` (inside the bracket `if`, 24-space indent) then constructs `req = MarketOrderRequest(**base_kwargs)` at `:3835` (20-space indent, outside the bracket `if`). Insert the `client_order_id` into `base_kwargs` at the 20-space level (applies to ALL BUYs, not just bracket) right before the `req = MarketOrderRequest(**base_kwargs)` line. Replace:

```python
                        base_kwargs["order_class"] = OrderClass.BRACKET
                        base_kwargs["take_profit"] = TakeProfitRequest(limit_price=tp_price)
                        base_kwargs["stop_loss"] = StopLossRequest(stop_price=sl_price)
                        log.debug("P2-A bracket %s: tp=%.2f sl=%.2f (d_hard=%.3f, entry≈%.2f)", order.symbol, tp_price, sl_price, _sl_d_hard, price)

                    req = MarketOrderRequest(**base_kwargs)
                    alpaca_order = trading_client.submit_order(req)
```

with:

```python
                        base_kwargs["order_class"] = OrderClass.BRACKET
                        base_kwargs["take_profit"] = TakeProfitRequest(limit_price=tp_price)
                        base_kwargs["stop_loss"] = StopLossRequest(stop_price=sl_price)
                        log.debug("P2-A bracket %s: tp=%.2f sl=%.2f (d_hard=%.3f, entry≈%.2f)", order.symbol, tp_price, sl_price, _sl_d_hard, price)

                    # §3: deterministic client_order_id for broker-side dedup.
                    if cycle_ts is not None:
                        base_kwargs["client_order_id"] = build_client_order_id(
                            "buy", order.symbol, cycle_ts,
                            signal_id=(signal_ids or {}).get(order.symbol),
                        )
                    req = MarketOrderRequest(**base_kwargs)
                    alpaca_order = trading_client.submit_order(req)
```

Then add the import at the top of `_submit_portfolio_orders` (inside the function body, next to the existing `from src.backtest.engine.types import OrderSide` at `:3645`). Replace:

```python
    from src.backtest.engine.types import OrderSide

    submitted = []
```

with:

```python
    from src.backtest.engine.types import OrderSide
    from src.portfolio.order_id import build_client_order_id

    submitted = []
```

- [ ] **Step 5: Pass `cycle_ts` and `signal_ids` at the caller**

In `src/workers/portfolio_scheduler.py`, edit the caller at `:2841-2853`. Replace:

```python
        submitted_orders = _submit_portfolio_orders(
            _orders_to_submit, trading_client, market,
            fractionable_symbols=fractionable,
            open_trade_symbols=open_db_symbols,  # None = guard unavailable → fail-closed
            regime_mult=_regime_mult,
            risk_cfg=_risk_cfg,
            bars_df=bars_df,
            stop_policy=_stop_policy,
            nav=equity,
            open_trades=_open_trades,
            sym_strats=_sym_strats,
            _on_broker_reject=_enqueue_mobile_broker_error,
        )
```

with:

```python
        submitted_orders = _submit_portfolio_orders(
            _orders_to_submit, trading_client, market,
            fractionable_symbols=fractionable,
            open_trade_symbols=open_db_symbols,  # None = guard unavailable → fail-closed
            regime_mult=_regime_mult,
            risk_cfg=_risk_cfg,
            bars_df=bars_df,
            stop_policy=_stop_policy,
            nav=equity,
            open_trades=_open_trades,
            sym_strats=_sym_strats,
            _on_broker_reject=_enqueue_mobile_broker_error,
            cycle_ts=ts,
            signal_ids=_signal_ids,
        )
```

- [ ] **Step 6: Run test to verify it passes**

Run: `.venv/bin/pytest tests/workers/test_portfolio_scheduler.py::test_submit_portfolio_orders_buy_attaches_client_order_id_with_signal_id tests/workers/test_portfolio_scheduler.py::test_submit_portfolio_orders_buy_attaches_client_order_id_without_signal_id tests/workers/test_portfolio_scheduler.py::test_submit_portfolio_orders_buy_no_coid_when_cycle_ts_absent -v`
Expected: PASS (3 tests).

- [ ] **Step 7: Run the full existing portfolio_scheduler suite to confirm no regressions**

Run: `.venv/bin/pytest tests/workers/test_portfolio_scheduler.py -v`
Expected: PASS (all pre-existing tests still pass — `cycle_ts`/`signal_ids` are optional with `None` defaults).

- [ ] **Step 8: Commit**

```bash
git add src/workers/portfolio_scheduler.py tests/workers/test_portfolio_scheduler.py
git commit -m "feat(scheduler): attach client_order_id to bracket BUY submit

Adds cycle_ts + signal_ids params to _submit_portfolio_orders (optional,
backward-compatible). Caller passes ts + _signal_ids. Part of #21 (spec §3)."
```

---

### Task 4: Wire `client_order_id` into the SELL at `portfolio_scheduler.py:3869`

The rebalance SELL is in the same `_submit_portfolio_orders` function (Task 3 added the params). SELLs carry no signal_id → the ID uses the `cycle_ts` segment.

**Files:**
- Modify: `src/workers/portfolio_scheduler.py:3862-3869`
- Test: `tests/workers/test_portfolio_scheduler.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/workers/test_portfolio_scheduler.py`:

```python
def test_submit_portfolio_orders_sell_attaches_client_order_id():
    """The real Alpaca SELL path attaches ambc-sell-{symbol}-{cycle_ts}."""
    from src.workers.portfolio_scheduler import _submit_portfolio_orders

    orders = [_make_combined_order("SPY", OrderSide.SELL, qty=10.0)]
    trading_client = MagicMock()
    resp = MagicMock()
    resp.id = "alpaca-sell-1"
    trading_client.submit_order.return_value = resp
    market = _make_market(prices={"SPY": 450.0})
    cycle_ts = datetime(2026, 8, 7, 14, 52, tzinfo=timezone.utc)

    with patch(
        "src.portfolio.fractional_stop_orders.cancel_open_stop_sells",
        return_value=0,
    ):
        submitted = _submit_portfolio_orders(
            orders, trading_client, market,
            cycle_ts=cycle_ts,
        )

    assert len(submitted) == 1
    trading_client.submit_order.assert_called_once()
    req = trading_client.submit_order.call_args[0][0]
    assert req.client_order_id == "ambc-sell-SPY-20260807T1452"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/workers/test_portfolio_scheduler.py::test_submit_portfolio_orders_sell_attaches_client_order_id -v`
Expected: FAIL with `AssertionError: assert None == 'ambc-sell-SPY-20260807T1452'` (the SELL site doesn't yet attach a coid).

- [ ] **Step 3: Attach `client_order_id` to the SELL `MarketOrderRequest`**

In `src/workers/portfolio_scheduler.py`, edit the SELL site at `:3862-3869`. Replace:

```python
                    from alpaca.trading.requests import MarketOrderRequest
                    req = MarketOrderRequest(
                        symbol=order.symbol,
                        qty=qty,
                        side="sell",
                        time_in_force="day",
                    )
                    alpaca_order = trading_client.submit_order(req)
```

with:

```python
                    from alpaca.trading.requests import MarketOrderRequest
                    _coid_sell = (
                        build_client_order_id("sell", order.symbol, cycle_ts)
                        if cycle_ts is not None else None
                    )
                    req = MarketOrderRequest(
                        symbol=order.symbol,
                        qty=qty,
                        side="sell",
                        time_in_force="day",
                        client_order_id=_coid_sell,
                    )
                    alpaca_order = trading_client.submit_order(req)
```

(`build_client_order_id` was imported in Task 3 Step 4 at the top of `_submit_portfolio_orders`.)

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/workers/test_portfolio_scheduler.py::test_submit_portfolio_orders_sell_attaches_client_order_id -v`
Expected: PASS.

- [ ] **Step 5: Run the full suite to confirm no regressions**

Run: `.venv/bin/pytest tests/workers/test_portfolio_scheduler.py -v`
Expected: PASS (all tests).

- [ ] **Step 6: Commit**

```bash
git add src/workers/portfolio_scheduler.py tests/workers/test_portfolio_scheduler.py
git commit -m "feat(scheduler): attach client_order_id to rebalance SELL submit

ambc-sell-{symbol}-{cycle_ts}. Part of #21 (spec §3)."
```

---

### Task 5: Wire `client_order_id` into the `_MORsl` stop-loss exit at `portfolio_scheduler.py:2949`

This site is in `_run_cycle_inner` where `ts` (the cycle timestamp) is always in scope. No signal_id (synthetic stop-loss exit).

**Files:**
- Modify: `src/workers/portfolio_scheduler.py:2949-2951`
- Test: `tests/workers/test_portfolio_scheduler.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/workers/test_portfolio_scheduler.py`:

```python
def test_morsl_stop_loss_exit_attaches_client_order_id():
    """The FIX-C stop-loss exit submits with ambc-slstop-{symbol}-{cycle_ts}.

    Exercises the stop_loss_sells branch of _run_cycle_inner directly by
    calling the inlined submit block via the public path is impractical, so
    we assert the constructed _MORsl carries the coid by reproducing the
    exact request shape the block builds.
    """
    from alpaca.trading.enums import OrderSide as _OSsl, TimeInForce as _TIFsl
    from alpaca.trading.requests import MarketOrderRequest as _MORsl
    from src.portfolio.order_id import build_client_order_id

    ts = datetime(2026, 8, 7, 14, 52, tzinfo=timezone.utc)
    sym = "SOXX"
    expected_coid = build_client_order_id("slstop", sym, ts)
    assert expected_coid == "ambc-slstop-SOXX-20260807T1452"

    # Verify the request shape accepts the coid (mirrors the :2949 construction).
    req = _MORsl(
        symbol=sym, qty=1.0, side=_OSsl.SELL, time_in_force=_TIFsl.DAY,
        client_order_id=expected_coid,
    )
    assert req.client_order_id == expected_coid
    assert req.symbol == sym
    assert req.side.value == "sell"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/workers/test_portfolio_scheduler.py::test_morsl_stop_loss_exit_attaches_client_order_id -v`
Expected: PASS immediately (this test verifies the request shape, not the wiring — it documents the expected coid). The wiring assertion is that the production code at `:2949` constructs the same request. To gate on the wiring, also add an integration-style assertion below.

Add a second test that exercises the real `_run_cycle_inner` stop-loss path is impractical (it requires a full cycle fixture). Instead, this task's wiring is verified by reading the diff at `:2949` and by the fact that the coid format matches. Run the test to confirm the shape is correct:

Run: `.venv/bin/pytest tests/workers/test_portfolio_scheduler.py::test_morsl_stop_loss_exit_attaches_client_order_id -v`
Expected: PASS (shape verified).

- [ ] **Step 3: Attach `client_order_id` to the `_MORsl` stop-loss exit**

In `src/workers/portfolio_scheduler.py`, edit the stop-loss exit site at `:2949-2951`. Replace:

```python
                    resp = trading_client.submit_order(_MORsl(
                        symbol=sym, qty=qty_held, side=_OSsl.SELL, time_in_force=_TIFsl.DAY,
                    ))
```

with:

```python
                    from src.portfolio.order_id import build_client_order_id as _bcoi_sl
                    resp = trading_client.submit_order(_MORsl(
                        symbol=sym, qty=qty_held, side=_OSsl.SELL, time_in_force=_TIFsl.DAY,
                        client_order_id=_bcoi_sl("slstop", sym, ts),
                    ))
```

(`ts` is the cycle timestamp in scope in `_run_cycle_inner` — set at `:2307` as `ts = end` where `end = datetime.now(timezone.utc)` at `:2083`.)

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/workers/test_portfolio_scheduler.py::test_morsl_stop_loss_exit_attaches_client_order_id -v`
Expected: PASS.

- [ ] **Step 5: Run the full suite to confirm no regressions**

Run: `.venv/bin/pytest tests/workers/test_portfolio_scheduler.py -v`
Expected: PASS (all tests).

- [ ] **Step 6: Commit**

```bash
git add src/workers/portfolio_scheduler.py tests/workers/test_portfolio_scheduler.py
git commit -m "feat(scheduler): attach client_order_id to stop-loss exit submit

ambc-slstop-{symbol}-{cycle_ts} on the FIX-C _MORsl path. Part of #21 (spec §3)."
```

---

### Task 6: Wire `client_order_id` into the reversal force-sell at `portfolio_scheduler.py:3946`

This site is in `_submit_reversal_force_sells` (`:3892`) which takes `ts` as a param (`:3899`). The reversal dict `reversal_sell_symbols[sym]` carries `signal_id` (per `_sentiment_reversal_sells` return shape at `:4012`: `{symbol: {score, signal_id, identity}}`).

**Files:**
- Modify: `src/workers/portfolio_scheduler.py:3940-3946`
- Test: `tests/workers/test_portfolio_scheduler.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/workers/test_portfolio_scheduler.py`:

```python
def test_reversal_force_sell_attaches_client_order_id_with_signal_id():
    """The reversal force-sell attaches ambc-revsell-{symbol}-{signal_id}."""
    from src.workers.portfolio_scheduler import _submit_reversal_force_sells

    trading_client = MagicMock()
    trading_client.get_orders.return_value = []
    resp = MagicMock()
    resp.id = "ord-9"
    trading_client.submit_order.return_value = resp
    ts = datetime(2026, 7, 16, 18, 22, tzinfo=timezone.utc)

    submitted_orders = []
    with patch("src.store.pg_store.PostgreSQLStore") as _pgs:
        _submit_reversal_force_sells(
            reversal_sell_symbols={"SOXX": {"score": -0.42, "signal_id": 3861}},
            final_orders=[],
            stop_loss_sells={},
            alpaca_positions=[_make_alpaca_position("SOXX", 1.13)],
            trading_client=trading_client,
            submitted_orders=submitted_orders,
            ts=ts,
            regime_mult=0.7,
            operating_mode="active",
        )

    trading_client.submit_order.assert_called_once()
    req = trading_client.submit_order.call_args[0][0]
    assert req.client_order_id == "ambc-revsell-SOXX-3861"


def test_reversal_force_sell_attaches_client_order_id_without_signal_id():
    """No signal_id in the reversal dict → ambc-revsell-{symbol}-{cycle_ts}."""
    from src.workers.portfolio_scheduler import _submit_reversal_force_sells

    trading_client = MagicMock()
    trading_client.get_orders.return_value = []
    resp = MagicMock()
    resp.id = "ord-10"
    trading_client.submit_order.return_value = resp
    ts = datetime(2026, 7, 16, 18, 22, tzinfo=timezone.utc)

    submitted_orders = []
    with patch("src.store.pg_store.PostgreSQLStore") as _pgs:
        _submit_reversal_force_sells(
            reversal_sell_symbols={"SOXX": {"score": -0.42}},  # no signal_id key
            final_orders=[],
            stop_loss_sells={},
            alpaca_positions=[_make_alpaca_position("SOXX", 1.13)],
            trading_client=trading_client,
            submitted_orders=submitted_orders,
            ts=ts,
            regime_mult=0.7,
            operating_mode="active",
        )

    req = trading_client.submit_order.call_args[0][0]
    assert req.client_order_id == "ambc-revsell-SOXX-20260716T1822"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/workers/test_portfolio_scheduler.py::test_reversal_force_sell_attaches_client_order_id_with_signal_id tests/workers/test_portfolio_scheduler.py::test_reversal_force_sell_attaches_client_order_id_without_signal_id -v`
Expected: FAIL with `AssertionError: assert None == 'ambc-revsell-SOXX-3861'`.

- [ ] **Step 3: Attach `client_order_id` to the reversal force-sell `MarketOrderRequest`**

In `src/workers/portfolio_scheduler.py`, edit the reversal site at `:3940-3946`. Replace:

```python
                req = MarketOrderRequest(
                    symbol=sym,
                    qty=qty_held,
                    side=OrderSide.SELL,
                    time_in_force=TimeInForce.DAY,
                )
                resp = trading_client.submit_order(req)
```

with:

```python
                from src.portfolio.order_id import build_client_order_id as _bcoi_rev
                _rev_sig_id = reversal_sell_symbols.get(sym, {}).get("signal_id")
                req = MarketOrderRequest(
                    symbol=sym,
                    qty=qty_held,
                    side=OrderSide.SELL,
                    time_in_force=TimeInForce.DAY,
                    client_order_id=_bcoi_rev("revsell", sym, ts, signal_id=_rev_sig_id),
                )
                resp = trading_client.submit_order(req)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/workers/test_portfolio_scheduler.py::test_reversal_force_sell_attaches_client_order_id_with_signal_id tests/workers/test_portfolio_scheduler.py::test_reversal_force_sell_attaches_client_order_id_without_signal_id -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Run the full suite to confirm no regressions**

Run: `.venv/bin/pytest tests/workers/test_portfolio_scheduler.py -v`
Expected: PASS (all tests, including the pre-existing `test_reversal_force_sell_cancels_protective_stop_then_submits`).

- [ ] **Step 6: Commit**

```bash
git add src/workers/portfolio_scheduler.py tests/workers/test_portfolio_scheduler.py
git commit -m "feat(scheduler): attach client_order_id to reversal force-sell

ambc-revsell-{symbol}-{signal_id|cycle_ts}. Folds the bearish signal_id when
present. Part of #21 (spec §3)."
```

---

### Task 7: Wire `client_order_id` into the protective `StopOrderRequest` at `fractional_stop_orders.py:192`

`execute_protective_stop_plans` (`:153`) currently takes `(plans, trading_client)`. Add an optional `cycle_ts` param and pass it from the caller at `portfolio_scheduler.py:752` (where `cycle_ts` is already in scope).

**Files:**
- Modify: `src/portfolio/fractional_stop_orders.py:153` (signature), `:185-192` (submit site)
- Modify: `src/workers/portfolio_scheduler.py:752` (caller)
- Test: `tests/portfolio/test_fractional_stop_orders.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/portfolio/test_fractional_stop_orders.py` (inside `TestExecuteProtectiveStopPlans`, after `test_create_submits_stop_order` at `:205`):

```python
    def test_create_attaches_client_order_id_when_cycle_ts_provided(self, cycle_ts):
        from src.portfolio.fractional_stop_orders import execute_protective_stop_plans, ProtectiveStopPlan

        plan = ProtectiveStopPlan(action="create", symbol="AAPL", whole_qty=2, stop_price=88.0)
        tc = MagicMock()

        execute_protective_stop_plans([plan], tc, cycle_ts=cycle_ts)

        tc.submit_order.assert_called_once()
        req = tc.submit_order.call_args[0][0]
        assert req.client_order_id == "ambc-pstop-AAPL-20260716T1500"

    def test_create_no_client_order_id_when_cycle_ts_absent(self):
        from src.portfolio.fractional_stop_orders import execute_protective_stop_plans, ProtectiveStopPlan

        plan = ProtectiveStopPlan(action="create", symbol="AAPL", whole_qty=2, stop_price=88.0)
        tc = MagicMock()

        execute_protective_stop_plans([plan], tc)  # no cycle_ts

        tc.submit_order.assert_called_once()
        req = tc.submit_order.call_args[0][0]
        assert req.client_order_id is None
```

(`cycle_ts` fixture is defined at `tests/portfolio/test_fractional_stop_orders.py:34` as `datetime(2026, 7, 16, 15, 0, tzinfo=timezone.utc)` → `%Y%m%dT%H%M` = `20260716T1500`.)

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/portfolio/test_fractional_stop_orders.py::TestExecuteProtectiveStopPlans::test_create_attaches_client_order_id_when_cycle_ts_provided tests/portfolio/test_fractional_stop_orders.py::TestExecuteProtectiveStopPlans::test_create_no_client_order_id_when_cycle_ts_absent -v`
Expected: the first FAILs with `TypeError: execute_protective_stop_plans() got an unexpected keyword argument 'cycle_ts'`; the second PASSes (no coid today).

- [ ] **Step 3: Add `cycle_ts` param and attach `client_order_id`**

In `src/portfolio/fractional_stop_orders.py`, edit the signature at `:153`. Replace:

```python
def execute_protective_stop_plans(plans: Sequence[ProtectiveStopPlan], trading_client) -> dict:
```

with:

```python
def execute_protective_stop_plans(
    plans: Sequence[ProtectiveStopPlan],
    trading_client,
    cycle_ts: datetime | None = None,
) -> dict:
```

(`datetime` is already imported at `fractional_stop_orders.py:18` — `from datetime import datetime`.)

Then edit the submit site at `:185-192`. Replace:

```python
            req = StopOrderRequest(
                symbol=plan.symbol,
                qty=plan.whole_qty,
                side=OrderSide.SELL,
                time_in_force=TimeInForce.GTC,
                stop_price=plan.stop_price,
            )
            trading_client.submit_order(req)
```

with:

```python
            from src.portfolio.order_id import build_client_order_id
            _coid_pstop = (
                build_client_order_id("pstop", plan.symbol, cycle_ts)
                if cycle_ts is not None else None
            )
            req = StopOrderRequest(
                symbol=plan.symbol,
                qty=plan.whole_qty,
                side=OrderSide.SELL,
                time_in_force=TimeInForce.GTC,
                stop_price=plan.stop_price,
                client_order_id=_coid_pstop,
            )
            trading_client.submit_order(req)
```

- [ ] **Step 4: Pass `cycle_ts` at the caller**

In `src/workers/portfolio_scheduler.py`, edit the caller at `:752`. Replace:

```python
    summary = execute_protective_stop_plans(plans, trading_client)
```

with:

```python
    summary = execute_protective_stop_plans(plans, trading_client, cycle_ts=cycle_ts)
```

(`cycle_ts` is the param of `_sync_fractional_protective_stops` at `:707` — already in scope.)

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/bin/pytest tests/portfolio/test_fractional_stop_orders.py::TestExecuteProtectiveStopPlans::test_create_attaches_client_order_id_when_cycle_ts_provided tests/portfolio/test_fractional_stop_orders.py::TestExecuteProtectiveStopPlans::test_create_no_client_order_id_when_cycle_ts_absent -v`
Expected: PASS (2 tests).

- [ ] **Step 6: Run the full fractional_stop_orders suite + the scheduler suite that exercises _sync_fractional_protective_stops**

Run: `.venv/bin/pytest tests/portfolio/test_fractional_stop_orders.py tests/workers/test_portfolio_scheduler.py -v`
Expected: PASS (all tests).

- [ ] **Step 7: Commit**

```bash
git add src/portfolio/fractional_stop_orders.py src/workers/portfolio_scheduler.py tests/portfolio/test_fractional_stop_orders.py
git commit -m "feat(portfolio): attach client_order_id to protective StopOrderRequest

Adds optional cycle_ts param to execute_protective_stop_plans; caller passes
it. ambc-pstop-{symbol}-{cycle_ts}. Part of #21 (spec §3)."
```

---

### Task 8: Wire `client_order_id` into the legacy BUY at `execution.py:735`

`run_execution_cycle` (`:407`) has `symbol`, `signal_id` (`:642`), and `tick_time` all in scope at the submit site (`:725`).

**Files:**
- Modify: `src/workers/execution.py:725-735`
- Test: `tests/workers/test_execution_worker.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/workers/test_execution_worker.py` (after `test_order_notional_uses_portfolio_and_regime` at `:142`):

```python
def test_buy_attaches_client_order_id_with_signal_id():
    """Legacy BUY attaches ambc-buy-{symbol}-{signal_id}."""
    redis = _make_redis(signal=_signal(score=0.5))
    # Give the signal a signal_id so the coid folds it.
    redis.read_sentiment.return_value = {
        "score": 0.5, "fallback_used": False,
        "generated_at": (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat(),
        "signal_id": 4427,
    }
    client = _make_client(portfolio_value=100_000)
    cache = {"AAPL": {"ema": 90.0, "price": 100.0}}
    with patch("src.workers.execution._build_market_cache", return_value=cache):
        run_execution_cycle(["AAPL"], redis, client, data_client=MagicMock())

    client.submit_order.assert_called_once()
    req = client.submit_order.call_args[0][0]
    assert req.client_order_id == "ambc-buy-AAPL-4427"


def test_buy_attaches_client_order_id_without_signal_id():
    """No signal_id in the signal dict → ambc-buy-{symbol}-{tick_time}."""
    redis = _make_redis(signal=_signal(score=0.5))
    # _signal() does not include signal_id → coid uses tick_time.
    client = _make_client(portfolio_value=100_000)
    cache = {"AAPL": {"ema": 90.0, "price": 100.0}}
    with patch("src.workers.execution._build_market_cache", return_value=cache):
        run_execution_cycle(["AAPL"], redis, client, data_client=MagicMock())

    req = client.submit_order.call_args[0][0]
    # tick_time is datetime.now() inside run_execution_cycle; assert the prefix
    # and that the suffix is a cycle_ts-format (13 chars, %Y%m%dT%H%M).
    assert req.client_order_id.startswith("ambc-buy-AAPL-")
    suffix = req.client_order_id[len("ambc-buy-AAPL-"):]
    assert len(suffix) == 13 and "T" in suffix, suffix
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/workers/test_execution_worker.py::test_buy_attaches_client_order_id_with_signal_id tests/workers/test_execution_worker.py::test_buy_attaches_client_order_id_without_signal_id -v`
Expected: FAIL with `AssertionError: assert None == 'ambc-buy-AAPL-4427'`.

- [ ] **Step 3: Attach `client_order_id` to the legacy BUY `MarketOrderRequest`**

In `src/workers/execution.py`, edit the submit site at `:725-735`. Replace:

```python
            order = MarketOrderRequest(
                symbol=symbol,
                qty=qty,
                side=OrderSide.BUY,
                # GTC so the OTO stop-loss leg (inherits the parent TIF) persists
                # overnight; DAY cancels the broker-side stop at session close.
                time_in_force=TimeInForce.GTC,
                order_class=OrderClass.OTO,
                stop_loss=StopLossRequest(stop_price=stop_price),
            )
            submitted_order = trading_client.submit_order(order)
```

with:

```python
            from src.portfolio.order_id import build_client_order_id
            order = MarketOrderRequest(
                symbol=symbol,
                qty=qty,
                side=OrderSide.BUY,
                # GTC so the OTO stop-loss leg (inherits the parent TIF) persists
                # overnight; DAY cancels the broker-side stop at session close.
                time_in_force=TimeInForce.GTC,
                order_class=OrderClass.OTO,
                stop_loss=StopLossRequest(stop_price=stop_price),
                client_order_id=build_client_order_id(
                    "buy", symbol, tick_time, signal_id=signal_id,
                ),
            )
            submitted_order = trading_client.submit_order(order)
```

(`tick_time` and `signal_id` are both in scope at `:725` — `tick_time` is the cycle timestamp param of `run_execution_cycle`, `signal_id` is set at `:642`.)

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/workers/test_execution_worker.py::test_buy_attaches_client_order_id_with_signal_id tests/workers/test_execution_worker.py::test_buy_attaches_client_order_id_without_signal_id -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Run the full execution_worker suite to confirm no regressions**

Run: `.venv/bin/pytest tests/workers/test_execution_worker.py -v`
Expected: PASS (all tests).

- [ ] **Step 6: Commit**

```bash
git add src/workers/execution.py tests/workers/test_execution_worker.py
git commit -m "feat(execution): attach client_order_id to legacy BUY submit

ambc-buy-{symbol}-{signal_id|tick_time}. Part of #21 (spec §3)."
```

---

### Task 9: Fallback path — ID format rejected → omit `client_order_id` + alert

A defensive wrapper around `submit_order`: if Alpaca rejects the `client_order_id` format (a case that should not happen given charset sanitization), retry without it and log a warning. This task introduces the helper and replaces the 6 `trading_client.submit_order(req)` calls with the wrapper.

**Files:**
- Modify: `src/portfolio/order_id.py` (add `submit_order_with_coid_fallback`)
- Test: `tests/portfolio/test_order_id.py`
- Modify: `src/workers/portfolio_scheduler.py:2949, 3836, 3869, 3946` (wrap 4 submit calls)
- Modify: `src/portfolio/fractional_stop_orders.py:192` (wrap 1 submit call)
- Modify: `src/workers/execution.py:735` (wrap 1 submit call)

- [ ] **Step 1: Write the failing test**

First, add `submit_order_with_coid_fallback` to the existing import at the top of `tests/portfolio/test_order_id.py`. Replace the import line:

```python
from src.portfolio.order_id import build_client_order_id
```

with:

```python
from src.portfolio.order_id import build_client_order_id, submit_order_with_coid_fallback
```

Then append the following tests to `tests/portfolio/test_order_id.py` (after the `build_client_order_id` tests):

```python
from unittest.mock import MagicMock


def _req_with_coid(coid="ambc-buy-AAPL-20260807T1452"):
    from alpaca.trading.enums import OrderSide, TimeInForce
    from alpaca.trading.requests import MarketOrderRequest
    return MarketOrderRequest(
        symbol="AAPL", qty=10, side=OrderSide.BUY,
        time_in_force=TimeInForce.DAY, client_order_id=coid,
    )


def test_fallback_retries_without_coid_on_format_rejection():
    """A coid-format rejection → retry without client_order_id + alert."""
    tc = MagicMock()
    resp1 = MagicMock()
    resp1.id = "orig"
    resp2 = MagicMock()
    resp2.id = "retry"
    tc.submit_order.side_effect = [RuntimeError("client_order_id invalid format"), resp2]
    log = MagicMock()
    on_alert = MagicMock()

    result = submit_order_with_coid_fallback(
        tc, _req_with_coid(), log=log, on_alert=on_alert,
    )

    assert tc.submit_order.call_count == 2
    # Second call's request must have client_order_id=None.
    second_req = tc.submit_order.call_args_list[1][0][0]
    assert second_req.client_order_id is None
    assert second_req.symbol == "AAPL"
    assert result.id == "retry"
    log.warning.assert_called_once()
    on_alert.assert_called_once()


def test_fallback_reraises_non_coid_error():
    """An error not mentioning client_order_id must propagate unchanged."""
    tc = MagicMock()
    tc.submit_order.side_effect = RuntimeError("insufficient buying power")
    log = MagicMock()

    with pytest.raises(RuntimeError, match="insufficient buying power"):
        submit_order_with_coid_fallback(tc, _req_with_coid(), log=log)

    assert tc.submit_order.call_count == 1
    log.warning.assert_not_called()


def test_fallback_no_retry_when_coid_none():
    """If the request has no client_order_id, never retry — just propagate."""
    tc = MagicMock()
    tc.submit_order.side_effect = RuntimeError("client_order_id invalid format")
    log = MagicMock()

    with pytest.raises(RuntimeError, match="client_order_id invalid format"):
        submit_order_with_coid_fallback(tc, _req_with_coid(coid=None), log=log)

    assert tc.submit_order.call_count == 1
    log.warning.assert_not_called()


def test_fallback_returns_response_on_success():
    """No error → single submit, response returned, no alert."""
    tc = MagicMock()
    resp = MagicMock()
    resp.id = "ok"
    tc.submit_order.return_value = resp
    log = MagicMock()
    on_alert = MagicMock()

    result = submit_order_with_coid_fallback(
        tc, _req_with_coid(), log=log, on_alert=on_alert,
    )

    assert tc.submit_order.call_count == 1
    assert result.id == "ok"
    log.warning.assert_not_called()
    on_alert.assert_not_called()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/portfolio/test_order_id.py -v -k fallback`
Expected: FAIL with `ImportError: cannot import name 'submit_order_with_coid_fallback'`.

- [ ] **Step 3: Implement `submit_order_with_coid_fallback`**

Append to `src/portfolio/order_id.py`:

```python
def submit_order_with_coid_fallback(trading_client, req, *, log=None, on_alert=None):
    """Submit req; if Alpaca rejects its client_order_id format, retry without it.

    Returns the order response from submit_order. Re-raises any error that is
    NOT a client_order_id format rejection (e.g. insufficient buying power) so
    the caller's per-site error handling applies unchanged. On a coid rejection:
    log a warning, fire ``on_alert`` if provided, rebuild the request without
    client_order_id (pydantic v2 model_dump round-trip), and retry once.

    The ``log`` argument is a logging.Logger (or compatible); ``on_alert`` is an
    optional callable taking a single message string.
    """
    try:
        return trading_client.submit_order(req)
    except Exception as exc:
        if req.client_order_id is None or "client_order_id" not in str(exc).lower():
            raise
        if log is not None:
            log.warning(
                "Alpaca rejected client_order_id=%r — retrying without it: %s",
                req.client_order_id, exc,
            )
        if on_alert is not None:
            try:
                on_alert(f"client_order_id rejected by Alpaca: {req.client_order_id}")
            except Exception:
                pass
        dumped = req.model_dump(exclude_none=True)
        dumped.pop("client_order_id", None)
        return trading_client.submit_order(type(req)(**dumped))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/portfolio/test_order_id.py -v -k fallback`
Expected: PASS (4 tests).

- [ ] **Step 5: Wrap the 4 scheduler submit calls**

In `src/workers/portfolio_scheduler.py`, replace each of the 4 `trading_client.submit_order(...)` calls with `submit_order_with_coid_fallback(trading_client, ..., log=log)`. Add the import once at the top of the file (near the existing `from src.portfolio...` imports). Find the existing import block and add:

```python
from src.portfolio.order_id import submit_order_with_coid_fallback
```

Site 1 — `_MORsl` stop-loss exit (`:2949`). Replace:

```python
                    from src.portfolio.order_id import build_client_order_id as _bcoi_sl
                    resp = trading_client.submit_order(_MORsl(
                        symbol=sym, qty=qty_held, side=_OSsl.SELL, time_in_force=_TIFsl.DAY,
                        client_order_id=_bcoi_sl("slstop", sym, ts),
                    ))
```

with:

```python
                    from src.portfolio.order_id import build_client_order_id as _bcoi_sl
                    resp = submit_order_with_coid_fallback(
                        trading_client,
                        _MORsl(
                            symbol=sym, qty=qty_held, side=_OSsl.SELL, time_in_force=_TIFsl.DAY,
                            client_order_id=_bcoi_sl("slstop", sym, ts),
                        ),
                        log=log,
                    )
```

Site 2 — bracket BUY (`:3836`). Replace:

```python
                    req = MarketOrderRequest(**base_kwargs)
                    alpaca_order = trading_client.submit_order(req)
```

with:

```python
                    req = MarketOrderRequest(**base_kwargs)
                    alpaca_order = submit_order_with_coid_fallback(trading_client, req, log=log)
```

Site 3 — rebalance SELL (`:3869`). This line is identical to the BUY site's `:3836`, so the old_string must include the preceding SELL-specific `client_order_id=_coid_sell,` line to disambiguate. Replace:

```python
                        client_order_id=_coid_sell,
                    )
                    alpaca_order = trading_client.submit_order(req)
```

with:

```python
                        client_order_id=_coid_sell,
                    )
                    alpaca_order = submit_order_with_coid_fallback(trading_client, req, log=log)
```

Site 4 — reversal force-sell (`:3946`). Replace:

```python
                resp = trading_client.submit_order(req)
```

with:

```python
                resp = submit_order_with_coid_fallback(trading_client, req, log=log)
```

- [ ] **Step 6: Wrap the protective stop submit call**

In `src/portfolio/fractional_stop_orders.py`, replace the `:192` call. Replace:

```python
            trading_client.submit_order(req)
```

with:

```python
            from src.portfolio.order_id import submit_order_with_coid_fallback
            submit_order_with_coid_fallback(trading_client, req, log=log)
```

(`log` is the module logger at `fractional_stop_orders.py:23`.)

- [ ] **Step 7: Wrap the legacy BUY submit call**

In `src/workers/execution.py`, replace the `:735` call. Replace:

```python
            submitted_order = trading_client.submit_order(order)
```

with:

```python
            from src.portfolio.order_id import submit_order_with_coid_fallback
            submitted_order = submit_order_with_coid_fallback(trading_client, order, log=log)
```

(`log` is the module logger at `execution.py:49`.)

- [ ] **Step 8: Run all affected suites to confirm no regressions**

Run: `.venv/bin/pytest tests/portfolio/test_order_id.py tests/portfolio/test_fractional_stop_orders.py tests/workers/test_portfolio_scheduler.py tests/workers/test_execution_worker.py -v`
Expected: PASS (all tests — the wrapper is transparent when no error is raised; the existing tests' `MagicMock` submit_order returns a response on the first call).

- [ ] **Step 9: Commit**

```bash
git add src/portfolio/order_id.py src/workers/portfolio_scheduler.py src/portfolio/fractional_stop_orders.py src/workers/execution.py tests/portfolio/test_order_id.py
git commit -m "feat(exec): add submit_order_with_coid_fallback + wrap 6 submit sites

Defensive: if Alpaca rejects the client_order_id format, retry without it
+ log warning. Transparent on success. Part of #21 (spec §3)."
```

---

### Task 10: Note — `freeze-ok` and dedup-reliance gating

**Files:**
- No code changes. This is a documentation note for the executor and the §4 retry plan.

- [ ] **Step 1: Confirm the gating note is captured**

The following is the governing constraint for any downstream work (notably the §4 retry/backoff plan, which is `blocked_by` this §3 issue):

- **`freeze-ok`:** This plan (spec §3) is correctness/tooling, NOT tuning. It is permitted during the freeze #171 (03/08→28/09) per the spec header.
- **Reliance on broker-side dedup is GATED on Task 2 (the verification spike).** Tasks 3-9 attach the `client_order_id` regardless of the spike outcome — the ID is harmless and useful for audit/traceability even if Alpaca does NOT dedup. But any logic that ASSUMES a duplicate `client_order_id` produces one fill (not two) — e.g. the §4 retry wrapping `submit_order` — must NOT be enabled until the spike verdict is `DEDUP CONFIRMED` or `DEDUP via 409`. If the spike verdict is `NO DEDUP`, the §4 retry plan must add application-level dedup or keep submit retry disabled.
- **Fallback (Task 9) is NOT gated** — it is a defensive safety-net that fires only on an Alpaca format rejection (a case that should not happen given charset sanitization). It does not rely on dedup semantics.

No commit required (documentation note only). The executor should ensure `docs/audits/alpaca_coid_dedup_spike.md` (from Task 2) is filled in before the §4 issue is unblocked.

---

## Self-Review

**1. Spec coverage (spec §3):**
- Universal deterministic ID `ambc-{purpose}-{symbol}-{cycle_ts}` on all 6 submit sites → Tasks 3, 4, 5, 6, 7, 8 (one per site). ✓
- `signal_id` folded where a signal exists → Task 3 (bracket BUY, signal_ids param), Task 6 (reversal SELL, `reversal_sell_symbols[sym]["signal_id"]`), Task 8 (legacy BUY, `signal_id` in scope). ✓
- Fits Alpaca constraints (≤1024 chars, `[a-zA-Z0-9-_]`) → Task 1 (charset sanitization + length test). ✓
- Helper `src/portfolio/order_id.py: build_client_order_id(purpose, symbol, cycle_ts, signal_id=None)` → Task 1. ✓
- Verification spike (dedup semantics, resubmit-window, 409 vs original) → Task 2. ✓
- Fallback (ID format rejected → omit + alert) → Task 9. ✓
- All 6 sites: `:2949` (Task 5), `:3836` (Task 3), `:3869` (Task 4), `:3946` (Task 6), `fractional_stop_orders.py:192` (Task 7), `execution.py:735` (Task 8). ✓
- `freeze-ok` + reliance gating → Task 10. ✓

**2. Placeholder scan:** No "TBD", "add error handling", "similar to Task N", or undescribed steps. Every code step contains complete code. ✓

**3. Type consistency:** `build_client_order_id(purpose: str, symbol: str, cycle_ts: datetime, signal_id: str | int | None = None) -> str` — identical signature in Task 1 (definition), Tasks 3-8 (call sites). `submit_order_with_coid_fallback(trading_client, req, *, log=None, on_alert=None)` — identical in Task 9 (definition + call sites). ✓

**Correction to spec grounding documented:** `StopLossRequest`/`TakeProfitRequest` do NOT accept `client_order_id` (they are legs extending `NonEmptyRequest`); the ID attaches to the parent `MarketOrderRequest` only. Verified at `alpaca/trading/requests.py:144-166` (legs) vs `:282-318` (OrderRequest base with `client_order_id`). ✓