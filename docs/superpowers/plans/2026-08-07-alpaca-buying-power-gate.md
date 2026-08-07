# buying_power/multiplier pre-flight gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate silent Alpaca 422 rejects (notional > buying_power) by adding a pre-flight gate at the BUY sizing step. Phase 1 (default `shadow`): log + alert when `notional > buying_power`, no behavior change. Phase 2 (operator flips `BUYING_POWER_GATE_MODE=cap`): cap notional to `buying_power`, re-round, log + alert. Guard edge: `buying_power` None/0 → skip + alert (never submit a 0-qty order). `account.multiplier` is logged for observability only (Alpaca's `buying_power` already embeds the Reg-T multiplier → no separate multiplier math).

**Architecture:** A pure decision helper `evaluate_buying_power_gate(...)` in `src/portfolio/buying_power_gate.py` (no I/O — the unit-testable core) is called at the sizing step of `_submit_portfolio_orders` (`src/workers/portfolio_scheduler.py`, after `notional` is computed at :3767 and `is_fractionable` at :3776, before the submit branch at :3777) and at the legacy path (`src/workers/execution.py`, after the price check at :720, before `qty = round(notional/price, 4)` at :722). Side effects (Telegram alert via `_fire_alert`, Decision Log row via `write_execution_decision`) are emitted on shadow/cap/skip. The gate is a no-op when the caller does not thread `buying_power` (sentinel `_BUYING_POWER_UNSET`) — preserves backward compat with existing tests that call `_submit_portfolio_orders` without the new params.

**Tech Stack:** Python 3.13, pydantic v2 (frozen `Config`), `alpaca-py` (`TradingClient.get_account()` → `Account.buying_power: Optional[str]`, `Account.multiplier: Optional[str]`), pytest + pytest-mock. No new dependencies.

**Rollout & Governance Notes (operator):**
- **`freeze-ok`:** this is correctness/risk-control (NOT tuning) — within the #171 freeze window (03/08→28/09). The spec classifies §1 as `freeze-ok`.
- **Live sizing change → operator sign-off required.** Phase 1 (`shadow`, the shipped default) makes ZERO behavior change (no cap, log+alert only). The flip to `cap` (`BUYING_POWER_GATE_MODE=cap`) is a live sizing change — the operator decides after reviewing one trading session of shadow evidence.
- **Shadow-first rollout:** the default `shadow` mode must run for at least one trading session before the operator flips to `cap`. Do NOT ship with `cap` as the default.
- **`account.multiplier` is observability-only:** Alpaca's `buying_power` already embeds the Reg-T multiplier (per alpaca-py `Account` docstring: "If multiplier = 2 then buying_power = max(equity-initial_margin(0) * 2)"). No separate multiplier math is performed; `multiplier` is only logged at :2072.
- **Known conservative edge:** in `_submit_portfolio_orders`, the gate runs after `_accepted_risk += ...` (:3774), so a skipped/capped order slightly over-counts aggregate stop-risk budget. This is conservative (more restrictive, never over-deploys) and acceptable for a shadow-first rollout. A capped notional that falls below `_MIN_ORDER_NOTIONAL` (100.0) still submits because the min-notional check at :3768 ran on the original (larger) notional — in practice `buying_power` >> 100, so this is a rare edge.

---

## File Structure

| File | Status | Responsibility |
|------|--------|----------------|
| `src/config.py` | Modify | Add `BUYING_POWER_GATE_MODE` field (default `"shadow"`) + `field_validator` restricting to `{shadow, cap, off}`. |
| `tests/test_config.py` | Modify | `TestBuyingPowerGateMode` — defaults, env override, valid modes, invalid-mode rejection. |
| `src/portfolio/buying_power_gate.py` | Create | PURE decision helper `evaluate_buying_power_gate(*, notional, buying_power, is_fractionable, mode, price)` → `BuyingPowerGateResult(action, capped_notional, capped_qty, delta)`. No I/O. |
| `tests/test_buying_power_gate.py` | Create | Unit tests for all helper branches: pass, off, skip (None/0), shadow, cap-fractional, cap-whole-share, cap-whole-share-can't-afford-one-share, cap-whole-share-no-price, unknown-mode. |
| `src/workers/portfolio_scheduler.py` | Modify | (Task 3) Add `_BUYING_POWER_UNSET` sentinel, `_write_buying_power_gate_decision` helper, `_account_debug_line` helper; log `account.multiplier` at :2072. (Task 4) Add `buying_power`/`notifier`/`ts`/`gate_mode` params to `_submit_portfolio_orders`; insert gate call at :3776→:3777; use `capped_qty` at :3798; thread params from call site at :2841. |
| `tests/test_buying_power_gate_wiring.py` | Create | Integration tests for the wired gate in `_submit_portfolio_orders` (cap/shadow/skip/pass/backward-compat/whole-share-capped-qty) + `_account_debug_line` format. |
| `src/workers/execution.py` | Modify | (Task 5) Read `buying_power` at :456; add `_apply_buying_power_gate_legacy` helper; call it at :720→:722 (legacy BUY path). |
| `tests/test_buying_power_gate_legacy.py` | Create | Unit tests for `_apply_buying_power_gate_legacy` (skip/cap/shadow/pass return values + decision row written). |

---

### Task 1: Add `BUYING_POWER_GATE_MODE` config flag

**Files:**
- Modify `src/config.py` (insert field after :213, validator after :454)
- Test `tests/test_config.py` (append `TestBuyingPowerGateMode` class)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_config.py`:

```python
class TestBuyingPowerGateMode:
    def test_default_is_shadow(self):
        from src.config import Config
        cfg = Config(
            ADMIN_API_KEY="a" * 32,
            DATABASE_URL="postgresql://localhost:5432/test",
        )
        assert cfg.BUYING_POWER_GATE_MODE == "shadow"

    def test_cap_mode_accepted(self):
        from src.config import Config
        cfg = Config(
            ADMIN_API_KEY="a" * 32,
            DATABASE_URL="postgresql://localhost:5432/test",
            BUYING_POWER_GATE_MODE="cap",
        )
        assert cfg.BUYING_POWER_GATE_MODE == "cap"

    def test_off_mode_accepted(self):
        from src.config import Config
        cfg = Config(
            ADMIN_API_KEY="a" * 32,
            DATABASE_URL="postgresql://localhost:5432/test",
            BUYING_POWER_GATE_MODE="off",
        )
        assert cfg.BUYING_POWER_GATE_MODE == "off"

    def test_invalid_mode_rejected(self):
        import pytest
        from src.config import Config
        with pytest.raises(Exception):
            Config(
                ADMIN_API_KEY="a" * 32,
                DATABASE_URL="postgresql://localhost:5432/test",
                BUYING_POWER_GATE_MODE="bogus",
            )

    def test_env_override(self, monkeypatch):
        from src.config import Config
        monkeypatch.setenv("BUYING_POWER_GATE_MODE", "cap")
        cfg = Config(
            ADMIN_API_KEY="a" * 32,
            DATABASE_URL="postgresql://localhost:5432/test",
        )
        assert cfg.BUYING_POWER_GATE_MODE == "cap"
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/test_config.py::TestBuyingPowerGateMode -x
```

Expected: `AttributeError: 'Config' object has no attribute 'BUYING_POWER_GATE_MODE'` (and `test_invalid_mode_rejected` may pass trivially because the field doesn't exist yet — the `test_default_is_shadow` failure is the primary signal).

- [ ] **Step 3: Write minimal implementation**

In `src/config.py`, insert after line 213 (after the `ALPACA_FRACTIONAL_STOP_ENABLED` field's closing `)`, before the blank line at :214 and the `# Telegram notifications` comment at :215):

```python

    # §1 (2026-08-07): buying_power pre-flight gate. Phase 1 = "shadow" (default —
    # log+alert only, no behavior change); Phase 2 = "cap" (operator flips after
    # one shadow session — caps notional to buying_power); "off" disables the gate.
    # See docs/superpowers/specs/2026-08-07-alpaca-exec-hardening-design.md §1.
    BUYING_POWER_GATE_MODE: str = Field(
        default_factory=lambda: os.environ.get("BUYING_POWER_GATE_MODE", "shadow")
    )
```

Then insert after line 454 (after the `validate_max_consecutive_fallbacks` validator's `return v`, before the blank lines at :455-456 and `# Global config instance` at :457):

```python

    @field_validator("BUYING_POWER_GATE_MODE")
    @classmethod
    def validate_buying_power_gate_mode(cls, v: str) -> str:
        """Validate BUYING_POWER_GATE_MODE is one of the allowed modes."""
        allowed = {"shadow", "cap", "off"}
        if v not in allowed:
            raise ValueError(
                f"BUYING_POWER_GATE_MODE must be one of {sorted(allowed)} (got {v!r})."
            )
        return v
```

- [ ] **Step 4: Run test to verify it passes**

```
pytest tests/test_config.py::TestBuyingPowerGateMode -x
```

Expected: `5 passed`.

- [ ] **Step 5: Commit**

```
git add src/config.py tests/test_config.py
git commit -m "feat(§1): add BUYING_POWER_GATE_MODE config flag (default shadow)

Pure config: field + validator restricting to {shadow, cap, off}.
Default 'shadow' = log+alert only (no behavior change); operator
flips to 'cap' after one shadow session. See spec §1.

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 2: Pure gate-decision helper `evaluate_buying_power_gate`

**Files:**
- Create `src/portfolio/buying_power_gate.py`
- Test `tests/test_buying_power_gate.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_buying_power_gate.py`:

```python
"""§1 — buying_power pre-flight gate: pure decision helper unit tests.

Tests every branch of evaluate_buying_power_gate in isolation (no I/O).
The wiring in portfolio_scheduler.py / execution.py is tested separately.
"""

from __future__ import annotations

import pytest

from src.portfolio.buying_power_gate import (
    BuyingPowerGateResult,
    evaluate_buying_power_gate,
)


class TestGatePass:
    def test_pass_when_notional_within_budget(self):
        r = evaluate_buying_power_gate(
            notional=100.0, buying_power=500.0, is_fractionable=True, mode="cap"
        )
        assert r.action == "pass"
        assert r.capped_notional is None
        assert r.capped_qty is None
        assert r.delta == 0.0

    def test_pass_when_mode_off(self):
        r = evaluate_buying_power_gate(
            notional=1000.0, buying_power=100.0, is_fractionable=True, mode="off"
        )
        assert r.action == "pass"
        assert r.delta == 0.0


class TestGateSkip:
    def test_skip_when_buying_power_none(self):
        r = evaluate_buying_power_gate(
            notional=100.0, buying_power=None, is_fractionable=True, mode="cap"
        )
        assert r.action == "skip"
        assert r.capped_notional is None
        assert r.capped_qty is None

    def test_skip_when_buying_power_zero(self):
        r = evaluate_buying_power_gate(
            notional=100.0, buying_power=0.0, is_fractionable=True, mode="cap"
        )
        assert r.action == "skip"

    def test_skip_when_buying_power_negative(self):
        r = evaluate_buying_power_gate(
            notional=100.0, buying_power=-1.0, is_fractionable=True, mode="cap"
        )
        assert r.action == "skip"


class TestGateShadow:
    def test_shadow_when_over_budget(self):
        r = evaluate_buying_power_gate(
            notional=1000.0, buying_power=500.0, is_fractionable=True, mode="shadow"
        )
        assert r.action == "shadow"
        assert r.capped_notional is None
        assert r.capped_qty is None
        assert r.delta == pytest.approx(500.0)

    def test_shadow_does_not_cap_even_if_fractionable(self):
        r = evaluate_buying_power_gate(
            notional=1000.0, buying_power=500.0, is_fractionable=False, mode="shadow",
            price=150.0,
        )
        assert r.action == "shadow"
        assert r.capped_notional is None


class TestGateCapFractional:
    def test_cap_fractional_when_over_budget(self):
        r = evaluate_buying_power_gate(
            notional=1000.0, buying_power=500.0, is_fractionable=True, mode="cap"
        )
        assert r.action == "cap"
        assert r.capped_notional == pytest.approx(500.0)
        assert r.capped_qty is None
        assert r.delta == pytest.approx(500.0)


class TestGateCapWholeShare:
    def test_cap_whole_share_when_over_budget(self):
        # notional=15000 (100 shares @ 150), buying_power=500 → 3 shares (450).
        r = evaluate_buying_power_gate(
            notional=15000.0, buying_power=500.0, is_fractionable=False, mode="cap",
            price=150.0,
        )
        assert r.action == "cap"
        assert r.capped_qty == 3
        assert r.capped_notional == pytest.approx(450.0)
        assert r.delta == pytest.approx(14500.0)

    def test_cap_whole_share_skip_when_cannot_afford_one_share(self):
        # buying_power=100 < price=150 → can't afford even 1 share → skip.
        r = evaluate_buying_power_gate(
            notional=15000.0, buying_power=100.0, is_fractionable=False, mode="cap",
            price=150.0,
        )
        assert r.action == "skip"
        assert r.capped_notional is None
        assert r.capped_qty is None

    def test_cap_whole_share_skip_when_price_none(self):
        r = evaluate_buying_power_gate(
            notional=1000.0, buying_power=500.0, is_fractionable=False, mode="cap",
            price=None,
        )
        assert r.action == "skip"

    def test_cap_whole_share_skip_when_price_zero(self):
        r = evaluate_buying_power_gate(
            notional=1000.0, buying_power=500.0, is_fractionable=False, mode="cap",
            price=0.0,
        )
        assert r.action == "skip"


class TestGateUnknownMode:
    def test_unknown_mode_treated_as_pass(self):
        r = evaluate_buying_power_gate(
            notional=1000.0, buying_power=100.0, is_fractionable=True, mode="bogus"
        )
        assert r.action == "pass"
        assert r.delta == 0.0


class TestGateResultIsFrozen:
    def test_result_is_frozen_dataclass(self):
        r = evaluate_buying_power_gate(
            notional=100.0, buying_power=500.0, is_fractionable=True, mode="cap"
        )
        with pytest.raises(Exception):
            r.action = "skip"  # type: ignore[misc]
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/test_buying_power_gate.py -x
```

Expected: `ModuleNotFoundError: No module named 'src.portfolio.buying_power_gate'`.

- [ ] **Step 3: Write minimal implementation**

Create `src/portfolio/buying_power_gate.py`:

```python
"""§1 (2026-08-07): buying_power pre-flight gate — pure decision helper.

Given (notional, buying_power, is_fractionable, mode, price) this module returns
the gate verdict (pass / shadow / cap / skip). It is intentionally pure (no I/O,
no logging) so it can be unit-tested in isolation. The wiring in
``src/workers/portfolio_scheduler.py`` and ``src/workers/execution.py`` calls
``evaluate_buying_power_gate`` at the sizing step and acts on the result.

See docs/superpowers/specs/2026-08-07-alpaca-exec-hardening-design.md §1.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BuyingPowerGateResult:
    """Verdict returned by ``evaluate_buying_power_gate``.

    Attributes:
        action:          "pass" (within budget or gate off), "shadow" (over budget,
                         log only — no cap), "cap" (over budget, cap notional to
                         buying_power), "skip" (buying_power unavailable or can't
                         afford one share — do not submit).
        capped_notional: Dollar notional after capping. None unless action == "cap".
        capped_qty:      Whole-share qty for a non-fractionable cap. None unless
                         action == "cap" and is_fractionable is False.
        delta:           notional - buying_power (>= 0 when over budget). 0.0 on
                         pass / skip.
    """

    action: str
    capped_notional: float | None
    capped_qty: int | None
    delta: float


def evaluate_buying_power_gate(
    *,
    notional: float,
    buying_power: float | None,
    is_fractionable: bool,
    mode: str,
    price: float | None = None,
) -> BuyingPowerGateResult:
    """Evaluate the buying_power pre-flight gate (pure, no I/O).

    Args:
        notional:        The USD notional the sizing step intends to submit.
        buying_power:    Alpaca ``account.buying_power`` (already embeds the Reg-T
                         multiplier — no separate multiplier math). None/<=0 → skip.
        is_fractionable: Whether the symbol supports notional/fractional orders.
                         When False and mode == "cap", the notional is re-rounded
                         to whole shares using ``price``.
        mode:            "shadow" (log only), "cap" (cap notional), "off" (no gate).
        price:           Current price; required for the non-fractionable cap
                         branch (whole-share re-rounding). Ignored otherwise.

    Returns:
        A ``BuyingPowerGateResult``. Branches:
          * mode == "off"                                  → pass
          * buying_power is None or <= 0                   → skip (API hiccup)
          * notional <= buying_power                        → pass
          * over budget + mode == "shadow"                 → shadow (no cap)
          * over budget + mode == "cap" + fractionable      → cap (capped_notional = buying_power)
          * over budget + mode == "cap" + whole-share       → cap (capped_qty = floor(buying_power/price))
          * over budget + mode == "cap" + whole-share,
            can't afford one share                          → skip
          * unknown mode                                    → pass (defensive)
    """
    if mode == "off":
        return BuyingPowerGateResult(action="pass", capped_notional=None, capped_qty=None, delta=0.0)
    if buying_power is None or buying_power <= 0:
        return BuyingPowerGateResult(action="skip", capped_notional=None, capped_qty=None, delta=0.0)
    if notional <= buying_power:
        return BuyingPowerGateResult(action="pass", capped_notional=None, capped_qty=None, delta=0.0)

    delta = round(notional - buying_power, 2)

    if mode == "shadow":
        return BuyingPowerGateResult(action="shadow", capped_notional=None, capped_qty=None, delta=delta)

    if mode == "cap":
        if is_fractionable:
            capped_notional = round(buying_power, 2)
            return BuyingPowerGateResult(
                action="cap", capped_notional=capped_notional, capped_qty=None, delta=delta,
            )
        # Non-fractionable: re-round to whole shares.
        if price is None or price <= 0:
            return BuyingPowerGateResult(action="skip", capped_notional=None, capped_qty=None, delta=delta)
        capped_qty = max(1, int(buying_power / price))
        if capped_qty * price > buying_power:
            # Can't afford even one share without exceeding buying_power → skip.
            return BuyingPowerGateResult(action="skip", capped_notional=None, capped_qty=None, delta=delta)
        capped_notional = round(capped_qty * price, 2)
        return BuyingPowerGateResult(
            action="cap", capped_notional=capped_notional, capped_qty=capped_qty, delta=delta,
        )

    # Unknown mode: treat as pass (defensive — config validator enforces the enum).
    return BuyingPowerGateResult(action="pass", capped_notional=None, capped_qty=None, delta=0.0)
```

- [ ] **Step 4: Run test to verify it passes**

```
pytest tests/test_buying_power_gate.py -x
```

Expected: `15 passed`.

- [ ] **Step 5: Commit**

```
git add src/portfolio/buying_power_gate.py tests/test_buying_power_gate.py
git commit -m "feat(§1): pure buying_power gate decision helper

evaluate_buying_power_gate(*, notional, buying_power, is_fractionable,
mode, price) -> BuyingPowerGateResult(action, capped_notional,
capped_qty, delta). Pure (no I/O). Branches: pass/off, skip (None/0
or can't-afford-one-share), shadow (no cap), cap (fractional or
whole-share re-rounded). See spec §1.

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 3: Observability infrastructure — Decision Log writer + `account.multiplier` log

This task builds the side-effect helpers that Task 4's gate wiring will call. It precedes Task 4 because the wiring calls `_write_buying_power_gate_decision` (defined here) — TDD requires the helper to exist before the caller. It also adds the `account.multiplier` observability log at :2072 (spec §1: "logged for observability only").

**Files:**
- Modify `src/workers/portfolio_scheduler.py` (insert helpers after :186; modify :2071-2072)
- Test `tests/test_buying_power_gate_wiring.py` (create with `TestGateDecisionWriter` + `TestAccountDebugLine`)

- [ ] **Step 1: Write the failing test**

Create `tests/test_buying_power_gate_wiring.py` (all imports at the top — Task 4 will append the `TestBuyingPowerGateWiring` class and shared helpers to this same file):

```python
"""§1 — buying_power gate observability infra + wiring tests.

Part 1 (Task 3): side-effect helpers in isolation — _write_buying_power_gate_decision
and _account_debug_line. Part 2 (Task 4): the full gate-wiring behavior in
_submit_portfolio_orders (TestBuyingPowerGateWiring, appended by Task 4).
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest


class TestGateDecisionWriter:
    def test_write_gate_decision_writes_row(self, monkeypatch):
        from src.workers.portfolio_scheduler import _write_buying_power_gate_decision

        captured: dict = {}

        class _FakePG:
            def write_execution_decision(self, **kwargs):
                captured.update(kwargs)
                return 1

            def close(self):
                pass

        monkeypatch.setattr("src.store.pg_store.PostgreSQLStore", _FakePG)

        _ts = datetime(2026, 8, 7, 14, 0, tzinfo=timezone.utc)
        _write_buying_power_gate_decision(
            _ts, "AAPL", 1.0, "BUY_POWER_CAP", "capped delta=$500.00",
        )

        assert captured["symbol"] == "AAPL"
        assert captured["decision"] == "BUY_POWER_CAP"
        assert captured["reason"] == "capped delta=$500.00"
        assert captured["regime_mult"] == 1.0
        assert captured["score"] == 0.0
        assert captured["signal_id"] is None
        assert captured["ema_pass"] is True
        assert captured["tick_time"] == _ts

    def test_write_gate_decision_swallows_db_failure(self, monkeypatch):
        from src.workers.portfolio_scheduler import _write_buying_power_gate_decision

        class _BoomPG:
            def __init__(self):
                raise RuntimeError("DB down")

            def close(self):
                pass

        monkeypatch.setattr("src.store.pg_store.PostgreSQLStore", _BoomPG)

        # Must NOT raise — a DB failure is logged but never blocks order submission.
        _write_buying_power_gate_decision(
            datetime(2026, 8, 7, 14, 0, tzinfo=timezone.utc),
            "AAPL", 1.0, "BUY_POWER_SHADOW", "would_cap",
        )


class TestAccountDebugLine:
    def test_includes_multiplier(self):
        from src.workers.portfolio_scheduler import _account_debug_line
        line = _account_debug_line(
            equity=10000.0, cash=5000.0, buying_power=10000.0, multiplier=2.0,
        )
        assert line == (
            "Account: equity=10000.00, cash=5000.00, "
            "buying_power=10000.00, multiplier=2.0"
        )

    def test_multiplier_one_for_cash_account(self):
        from src.workers.portfolio_scheduler import _account_debug_line
        line = _account_debug_line(
            equity=10000.0, cash=10000.0, buying_power=10000.0, multiplier=1.0,
        )
        assert "multiplier=1.0" in line
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/test_buying_power_gate_wiring.py -x
```

Expected: `AttributeError: module 'src.workers.portfolio_scheduler' has no attribute '_write_buying_power_gate_decision'`.

- [ ] **Step 3: Write minimal implementation**

In `src/workers/portfolio_scheduler.py`, insert after line 186 (after the `_fire_alert` function's `log.warning(...)` line at :186, before the two blank lines at :187-188 and `def _divergence_alert_enabled` at :189):

```python


# §1 (2026-08-07): buying_power pre-flight gate sentinel. When the caller does
# not thread ``buying_power`` (e.g. legacy tests), the gate is a no-op. This is
# distinct from buying_power == 0 (API returned 0 → skip).
_BUYING_POWER_UNSET = object()


def _write_buying_power_gate_decision(
    ts, symbol: str, regime_mult: float, decision: str, reason: str,
) -> None:
    """Write one execution_decisions row for a buying_power gate event (shadow/cap/skip).

    Best-effort: a DB failure is logged but never blocks order submission. Mirrors
    the stop-loss decision-write pattern (lines ~2960-2990).
    """
    try:
        from src.store.pg_store import PostgreSQLStore as _PGSgate
        _pg = _PGSgate()
        try:
            _pg.write_execution_decision(
                tick_time=ts,
                symbol=symbol,
                signal_id=None,
                score=0.0,
                regime_mult=regime_mult,
                ema_pass=True,
                decision=decision,
                reason=reason,
            )
        finally:
            _pg.close()
    except Exception as _gate_db_exc:
        log.warning("buying_power gate: failed to write decision for %s: %s", symbol, _gate_db_exc)


def _account_debug_line(equity: float, cash: float, buying_power: float, multiplier: float) -> str:
    """Format the account pre-flight debug line (§1: includes multiplier for observability).

    Pure helper so the multiplier log line is unit-testable without running the
    full cycle. ``multiplier`` is observability-only — Alpaca's ``buying_power``
    already embeds the Reg-T multiplier, so no separate multiplier math is done.
    """
    return (
        f"Account: equity={equity:.2f}, cash={cash:.2f}, "
        f"buying_power={buying_power:.2f}, multiplier={multiplier:.1f}"
    )
```

Then modify lines 2071-2072. Replace:

```python
    buying_power = float(account.buying_power) if account.buying_power else cash
    log.debug("Account: equity=%.2f, cash=%.2f, buying_power=%.2f", equity, cash, buying_power)
```

with:

```python
    buying_power = float(account.buying_power) if account.buying_power else cash
    # §1 (2026-08-07): multiplier logged for observability only — Alpaca's
    # buying_power already embeds the Reg-T multiplier, so no separate math.
    multiplier = float(account.multiplier) if account.multiplier else 1.0
    log.debug(_account_debug_line(equity, cash, buying_power, multiplier))
```

- [ ] **Step 4: Run test to verify it passes**

```
pytest tests/test_buying_power_gate_wiring.py -x
```

Expected: `4 passed`.

- [ ] **Step 5: Commit**

```
git add src/workers/portfolio_scheduler.py tests/test_buying_power_gate_wiring.py
git commit -m "feat(§1): gate observability infra (decision writer + multiplier log)

_write_buying_power_gate_decision: best-effort execution_decisions row
for shadow/cap/skip events (mirrors stop-loss pattern). _account_debug_line:
pure formatter so the multiplier observability log at :2072 is testable.
account.multiplier is logged only (buying_power embeds it — no math).

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 4: Wire the gate into `_submit_portfolio_orders` (BUY sizing step)

This task combines the user's tasks 3 (gate wiring) and 4 (Telegram alert + Decision Log) because they are one contiguous code insertion at lines 3776→3777; splitting them would require placeholder stubs, which this plan forbids. The alert (`_fire_alert`) and Decision Log (`_write_buying_power_gate_decision`, from Task 3) calls live inside the gate branching.

**Files:**
- Modify `src/workers/portfolio_scheduler.py` (signature :3596-3611; gate call :3776→3777; `whole_qty` :3798; call site :2841-2853)
- Test `tests/test_buying_power_gate_wiring.py` (append `TestBuyingPowerGateWiring` class)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_buying_power_gate_wiring.py` (imports are already at the top from Task 3; this appends shared helpers + the wiring test class):

```python


def _make_order(symbol="AAPL", qty=10.0):
    from src.backtest.engine.types import Order, OrderSide
    from datetime import datetime, timezone
    return Order.market_order(
        ts=datetime(2026, 8, 7, 14, 0, tzinfo=timezone.utc),
        symbol=symbol, side=OrderSide.BUY, qty=qty,
    )


def _make_market(price=100.0, symbol="AAPL"):
    from src.backtest.engine.types import MarketSnapshot
    from datetime import datetime, timezone
    return MarketSnapshot(
        timestamp=datetime(2026, 8, 7, 14, 0, tzinfo=timezone.utc),
        prices={symbol: price}, volumes={symbol: 1_000_000.0}, adv_20d={symbol: 1_000_000.0},
    )


def _ts():
    from datetime import datetime, timezone
    return datetime(2026, 8, 7, 14, 0, tzinfo=timezone.utc)


def _suppress_gate_side_effects(monkeypatch):
    """Patch cooldown readers + alert/decision writers so tests focus on sizing."""
    monkeypatch.setattr(
        "src.workers.portfolio_scheduler._get_stop_loss_cooldown_symbols", lambda url: set(),
    )
    monkeypatch.setattr(
        "src.workers.portfolio_scheduler._get_reversal_cooldown_symbols", lambda url: set(),
    )


class TestBuyingPowerGateWiring:
    def test_cap_reduces_notional_when_over_budget(self, monkeypatch):
        _suppress_gate_side_effects(monkeypatch)
        monkeypatch.setattr("src.workers.portfolio_scheduler._fire_alert", lambda *a, **k: None)
        monkeypatch.setattr(
            "src.workers.portfolio_scheduler._write_buying_power_gate_decision", lambda *a, **k: None,
        )
        from src.workers.portfolio_scheduler import _submit_portfolio_orders

        captured: list[float] = []
        def capture_fn(order, notional, _tc): captured.append(notional)

        _submit_portfolio_orders(
            [_make_order("AAPL", qty=10.0)], MagicMock(), _make_market(price=100.0),
            _submit_fn=capture_fn, fractionable_symbols=None,
            open_trade_symbols=frozenset(), regime_mult=1.0,
            buying_power=500.0, notifier=MagicMock(), ts=_ts(), gate_mode="cap",
        )
        # notional=1000 > buying_power=500 → capped to 500.
        assert captured == [pytest.approx(500.0)]

    def test_shadow_does_not_reduce_notional(self, monkeypatch):
        _suppress_gate_side_effects(monkeypatch)
        fired: list = []
        written: list = []
        monkeypatch.setattr(
            "src.workers.portfolio_scheduler._fire_alert", lambda *a, **k: fired.append(a),
        )
        monkeypatch.setattr(
            "src.workers.portfolio_scheduler._write_buying_power_gate_decision",
            lambda *a, **k: written.append(a),
        )
        from src.workers.portfolio_scheduler import _submit_portfolio_orders

        captured: list[float] = []
        def capture_fn(order, notional, _tc): captured.append(notional)

        _submit_portfolio_orders(
            [_make_order("AAPL", qty=10.0)], MagicMock(), _make_market(price=100.0),
            _submit_fn=capture_fn, fractionable_symbols=None,
            open_trade_symbols=frozenset(), regime_mult=1.0,
            buying_power=500.0, notifier=MagicMock(), ts=_ts(), gate_mode="shadow",
        )
        # shadow: notional unchanged (1000), but alert + decision fired.
        assert captured == [pytest.approx(1000.0)]
        assert len(fired) == 1
        assert len(written) == 1

    def test_skip_prevents_submit_when_buying_power_zero(self, monkeypatch):
        _suppress_gate_side_effects(monkeypatch)
        monkeypatch.setattr("src.workers.portfolio_scheduler._fire_alert", lambda *a, **k: None)
        monkeypatch.setattr(
            "src.workers.portfolio_scheduler._write_buying_power_gate_decision", lambda *a, **k: None,
        )
        from src.workers.portfolio_scheduler import _submit_portfolio_orders

        captured: list[float] = []
        def capture_fn(order, notional, _tc): captured.append(notional)

        _submit_portfolio_orders(
            [_make_order("AAPL", qty=10.0)], MagicMock(), _make_market(price=100.0),
            _submit_fn=capture_fn, fractionable_symbols=None,
            open_trade_symbols=frozenset(), regime_mult=1.0,
            buying_power=0.0, notifier=MagicMock(), ts=_ts(), gate_mode="cap",
        )
        # buying_power=0 → skip → no submit.
        assert captured == []

    def test_pass_when_within_budget(self, monkeypatch):
        _suppress_gate_side_effects(monkeypatch)
        fired: list = []
        written: list = []
        monkeypatch.setattr(
            "src.workers.portfolio_scheduler._fire_alert", lambda *a, **k: fired.append(a),
        )
        monkeypatch.setattr(
            "src.workers.portfolio_scheduler._write_buying_power_gate_decision",
            lambda *a, **k: written.append(a),
        )
        from src.workers.portfolio_scheduler import _submit_portfolio_orders

        captured: list[float] = []
        def capture_fn(order, notional, _tc): captured.append(notional)

        _submit_portfolio_orders(
            [_make_order("AAPL", qty=10.0)], MagicMock(), _make_market(price=100.0),
            _submit_fn=capture_fn, fractionable_symbols=None,
            open_trade_symbols=frozenset(), regime_mult=1.0,
            buying_power=2000.0, notifier=MagicMock(), ts=_ts(), gate_mode="cap",
        )
        # notional=1000 <= buying_power=2000 → pass, no alert, no decision.
        assert captured == [pytest.approx(1000.0)]
        assert fired == []
        assert written == []

    def test_gate_inactive_when_buying_power_not_threaded(self, monkeypatch):
        """Backward compat: callers that don't pass buying_power get no gate."""
        _suppress_gate_side_effects(monkeypatch)
        from src.workers.portfolio_scheduler import _submit_portfolio_orders

        captured: list[float] = []
        def capture_fn(order, notional, _tc): captured.append(notional)

        # No buying_power / notifier / ts / gate_mode kwargs.
        _submit_portfolio_orders(
            [_make_order("AAPL", qty=10.0)], MagicMock(), _make_market(price=100.0),
            _submit_fn=capture_fn, fractionable_symbols=None,
            open_trade_symbols=frozenset(), regime_mult=1.0,
        )
        assert captured == [pytest.approx(1000.0)]

    def test_cap_whole_share_uses_capped_qty_real_submit(self, monkeypatch):
        """Non-fractionable cap: the real submit path receives qty=capped_qty (3)."""
        _suppress_gate_side_effects(monkeypatch)
        monkeypatch.setattr("src.workers.portfolio_scheduler._fire_alert", lambda *a, **k: None)
        monkeypatch.setattr(
            "src.workers.portfolio_scheduler._write_buying_power_gate_decision", lambda *a, **k: None,
        )
        from src.workers.portfolio_scheduler import _submit_portfolio_orders

        captured_reqs: list = []
        tc = MagicMock()

        def _capture_submit(req):
            captured_reqs.append(req)
            resp = MagicMock()
            resp.id = "test-1"
            return resp

        tc.submit_order.side_effect = _capture_submit

        # notional=1500 (10 @ 150), buying_power=500 → 3 shares (450).
        _submit_portfolio_orders(
            [_make_order("AAPL", qty=10.0)], tc, _make_market(price=150.0),
            fractionable_symbols=set(),  # AAPL NOT fractionable
            open_trade_symbols=frozenset(), regime_mult=1.0,
            buying_power=500.0, notifier=MagicMock(), ts=_ts(), gate_mode="cap",
        )
        assert len(captured_reqs) == 1
        assert captured_reqs[0].qty == 3
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/test_buying_power_gate_wiring.py::TestBuyingPowerGateWiring -x
```

Expected: `TypeError: _submit_portfolio_orders() got an unexpected keyword argument 'buying_power'` (the new params don't exist yet).

- [ ] **Step 3: Write minimal implementation**

In `src/workers/portfolio_scheduler.py`, make four edits.

**Edit A — add params to `_submit_portfolio_orders` signature.** Replace line 3610 (`    sym_strats: dict | None = None,`) with:

```python
    sym_strats: dict | None = None,
    buying_power=_BUYING_POWER_UNSET,
    notifier=None,
    ts=None,
    gate_mode: str | None = None,
```

**Edit B — insert the gate call after `is_fractionable` (:3776), before `if _submit_fn is not None:` (:3777).** Replace:

```python
                is_fractionable = (fractionable_symbols is None or order.symbol in fractionable_symbols)
                if _submit_fn is not None:
```

with:

```python
                is_fractionable = (fractionable_symbols is None or order.symbol in fractionable_symbols)
                # §1 (2026-08-07): buying_power pre-flight gate. See
                # docs/superpowers/specs/2026-08-07-alpaca-exec-hardening-design.md §1.
                _gate_capped_qty: int | None = None
                if buying_power is not _BUYING_POWER_UNSET:
                    from src.config import config as _cfg_gate
                    from src.portfolio.buying_power_gate import evaluate_buying_power_gate
                    _gate_mode = gate_mode if gate_mode is not None else _cfg_gate.BUYING_POWER_GATE_MODE
                    _gate = evaluate_buying_power_gate(
                        notional=notional,
                        buying_power=buying_power,
                        is_fractionable=is_fractionable,
                        mode=_gate_mode,
                        price=price,
                    )
                    if _gate.action == "skip":
                        log.warning(
                            "buying_power gate SKIP: %s notional=$%.2f — buying_power unavailable (bp=%s)",
                            order.symbol, notional, buying_power,
                        )
                        if notifier is not None:
                            _fire_alert(
                                notifier,
                                f"⚠️ buying_power gate SKIP {order.symbol}: buying_power unavailable "
                                f"(bp={buying_power}) — order not submitted.",
                                AlertLevel.WARNING,
                            )
                        _write_buying_power_gate_decision(
                            ts, order.symbol, regime_mult, "SKIP_BUY_POWER",
                            reason=f"buying_power unavailable (bp={buying_power}) — order skipped",
                        )
                        continue
                    if _gate.action == "shadow":
                        log.info(
                            "buying_power gate SHADOW: %s notional=$%.2f > buying_power=$%.2f "
                            "(delta $%.2f) — NOT capping (shadow mode)",
                            order.symbol, notional, buying_power, _gate.delta,
                        )
                        if notifier is not None:
                            _fire_alert(
                                notifier,
                                f"⚠️ buying_power gate SHADOW {order.symbol}: notional ${notional:.2f} "
                                f"> buying_power ${buying_power:.2f} (delta ${_gate.delta:.2f}) — would cap.",
                                AlertLevel.WARNING,
                            )
                        _write_buying_power_gate_decision(
                            ts, order.symbol, regime_mult, "BUY_POWER_SHADOW",
                            reason=f"would_cap delta=${_gate.delta:.2f} "
                            f"(shadow mode, notional=${notional:.2f}, buying_power=${buying_power:.2f})",
                        )
                    elif _gate.action == "cap":
                        _orig_notional = notional
                        notional = _gate.capped_notional  # type: ignore[assignment]
                        _gate_capped_qty = _gate.capped_qty
                        log.info(
                            "buying_power gate CAP: %s notional $%.2f -> $%.2f "
                            "(delta $%.2f, buying_power=$%.2f)",
                            order.symbol, _orig_notional, notional, _gate.delta, buying_power,
                        )
                        if notifier is not None:
                            _fire_alert(
                                notifier,
                                f"⚠️ buying_power gate CAP {order.symbol}: notional "
                                f"${_orig_notional:.2f} -> ${notional:.2f} (delta ${_gate.delta:.2f}).",
                                AlertLevel.WARNING,
                            )
                        _write_buying_power_gate_decision(
                            ts, order.symbol, regime_mult, "BUY_POWER_CAP",
                            reason=f"capped delta=${_gate.delta:.2f} "
                            f"(notional ${_orig_notional:.2f} -> ${notional:.2f}, "
                            f"buying_power=${buying_power:.2f})",
                        )
                if _submit_fn is not None:
```

**Edit C — use `_gate_capped_qty` at the whole-share derivation (:3798).** Replace:

```python
                        whole_qty = max(1, int(notional / price))
```

with:

```python
                        if _gate_capped_qty is not None:
                            whole_qty = _gate_capped_qty
                        else:
                            whole_qty = max(1, int(notional / price))
```

**Edit D — thread the new params from the call site (:2841-2853).** Replace:

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
            buying_power=buying_power,
            notifier=notifier,
            ts=ts,
        )
```

- [ ] **Step 4: Run test to verify it passes**

```
pytest tests/test_buying_power_gate_wiring.py -x
```

Expected: `10 passed` (4 from Task 3 + 6 from Task 4). Also run the existing regime tests to confirm no backward-compat regression:

```
pytest tests/test_p0_09_regime_multiplier.py -x
```

Expected: all pass (the sentinel keeps the gate inactive when `buying_power` is not threaded).

- [ ] **Step 5: Commit**

```
git add src/workers/portfolio_scheduler.py tests/test_buying_power_gate_wiring.py
git commit -m "feat(§1): wire buying_power gate into _submit_portfolio_orders

Gate runs at the sizing step (after notional @ :3767 + is_fractionable
@ :3776, before submit @ :3777). shadow: log+alert, no cap. cap:
overwrite notional, use capped_qty for whole-share @ :3798. skip:
continue (buying_power None/0). Sentinel _BUYING_POWER_UNSET keeps
the gate inactive for callers that don't thread buying_power (backward
compat). Call site @ :2841 threads buying_power/notifier/ts.

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 5: Wire the gate into the `execution.py` legacy BUY path

The legacy path (`run_execution_cycle`) is a large function with many gates (kill-switch, regime, EMA, cycle cap), making it costly to test end-to-end. To keep the gate unit-testable, extract a small helper `_apply_buying_power_gate_legacy` (mirrors the existing `_write_decision` / `_fire_alert` extraction pattern in `execution.py`) and wire it at :720→:722. The legacy path uses fractional qty (4 decimals at :722), so `is_fractionable=True`.

**Files:**
- Modify `src/workers/execution.py` (read `buying_power` at :456; add helper after :314; call helper at :720→:722)
- Test `tests/test_buying_power_gate_legacy.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_buying_power_gate_legacy.py`:

```python
"""§1 — buying_power gate on the execution.py legacy BUY path.

Tests the _apply_buying_power_gate_legacy helper in isolation (the run_execution_cycle
wrapper has too many gates to test end-to-end cheaply). The helper delegates alert +
Decision Log to execution.py's existing _fire_alert / _write_decision.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest


def _ts():
    return datetime(2026, 8, 7, 14, 0, tzinfo=timezone.utc)


class TestLegacyGateSkip:
    def test_skip_returns_none_when_buying_power_zero(self):
        from src.workers.execution import _apply_buying_power_gate_legacy
        result = _apply_buying_power_gate_legacy(
            notional=1000.0, buying_power=0.0, price=100.0, symbol="AAPL",
            signal_id=1, score=0.5, regime_mult=1.0, tick_time=_ts(),
            pg_store=MagicMock(), notifier=None, mode="cap",
        )
        assert result is None

    def test_skip_returns_none_when_buying_power_none(self):
        from src.workers.execution import _apply_buying_power_gate_legacy
        result = _apply_buying_power_gate_legacy(
            notional=1000.0, buying_power=None, price=100.0, symbol="AAPL",
            signal_id=1, score=0.5, regime_mult=1.0, tick_time=_ts(),
            pg_store=MagicMock(), notifier=None, mode="cap",
        )
        assert result is None


class TestLegacyGateCap:
    def test_cap_returns_capped_notional(self):
        from src.workers.execution import _apply_buying_power_gate_legacy
        result = _apply_buying_power_gate_legacy(
            notional=1000.0, buying_power=500.0, price=100.0, symbol="AAPL",
            signal_id=1, score=0.5, regime_mult=1.0, tick_time=_ts(),
            pg_store=MagicMock(), notifier=None, mode="cap",
        )
        # Fractionable legacy path: capped_notional = buying_power = 500.
        assert result == pytest.approx(500.0)


class TestLegacyGateShadow:
    def test_shadow_returns_unchanged_notional(self):
        from src.workers.execution import _apply_buying_power_gate_legacy
        result = _apply_buying_power_gate_legacy(
            notional=1000.0, buying_power=500.0, price=100.0, symbol="AAPL",
            signal_id=1, score=0.5, regime_mult=1.0, tick_time=_ts(),
            pg_store=MagicMock(), notifier=None, mode="shadow",
        )
        assert result == pytest.approx(1000.0)


class TestLegacyGatePass:
    def test_pass_returns_unchanged_notional_when_within_budget(self):
        from src.workers.execution import _apply_buying_power_gate_legacy
        result = _apply_buying_power_gate_legacy(
            notional=100.0, buying_power=500.0, price=100.0, symbol="AAPL",
            signal_id=1, score=0.5, regime_mult=1.0, tick_time=_ts(),
            pg_store=MagicMock(), notifier=None, mode="cap",
        )
        assert result == pytest.approx(100.0)

    def test_pass_returns_unchanged_notional_when_mode_off(self):
        from src.workers.execution import _apply_buying_power_gate_legacy
        result = _apply_buying_power_gate_legacy(
            notional=1000.0, buying_power=100.0, price=100.0, symbol="AAPL",
            signal_id=1, score=0.5, regime_mult=1.0, tick_time=_ts(),
            pg_store=MagicMock(), notifier=None, mode="off",
        )
        assert result == pytest.approx(1000.0)


class TestLegacyGateDecisionLog:
    def test_cap_writes_decision_row(self, monkeypatch):
        from src.workers import execution
        captured: list = []
        monkeypatch.setattr(
            execution, "_write_decision",
            lambda pg, tt, sym, sid, sc, rm, ema_pass, decision, order_id=None, reason=None: captured.append(decision),
        )
        monkeypatch.setattr(execution, "_fire_alert", lambda *a, **k: None)
        execution._apply_buying_power_gate_legacy(
            notional=1000.0, buying_power=500.0, price=100.0, symbol="AAPL",
            signal_id=1, score=0.5, regime_mult=1.0, tick_time=_ts(),
            pg_store=MagicMock(), notifier=None, mode="cap",
        )
        assert captured == ["BUY_POWER_CAP"]

    def test_skip_writes_decision_row(self, monkeypatch):
        from src.workers import execution
        captured: list = []
        monkeypatch.setattr(
            execution, "_write_decision",
            lambda pg, tt, sym, sid, sc, rm, ema_pass, decision, order_id=None, reason=None: captured.append(decision),
        )
        monkeypatch.setattr(execution, "_fire_alert", lambda *a, **k: None)
        execution._apply_buying_power_gate_legacy(
            notional=1000.0, buying_power=0.0, price=100.0, symbol="AAPL",
            signal_id=1, score=0.5, regime_mult=1.0, tick_time=_ts(),
            pg_store=MagicMock(), notifier=None, mode="cap",
        )
        assert captured == ["SKIP_BUY_POWER"]
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/test_buying_power_gate_legacy.py -x
```

Expected: `AttributeError: module 'src.workers.execution' has no attribute '_apply_buying_power_gate_legacy'`.

- [ ] **Step 3: Write minimal implementation**

In `src/workers/execution.py`, make two edits.

**Edit A — read `buying_power` after the account fetch (:456).** Replace:

```python
        account = trading_client.get_account()
        portfolio_value = float(account.portfolio_value)
        redis_store.set_portfolio_value(portfolio_value)
```

with:

```python
        account = trading_client.get_account()
        portfolio_value = float(account.portfolio_value)
        # §1 (2026-08-07): buying_power for the pre-flight gate. Falls back to
        # portfolio_value (equity) when Alpaca returns no buying_power.
        buying_power = float(account.buying_power) if account.buying_power else portfolio_value
        redis_store.set_portfolio_value(portfolio_value)
```

**Edit B — add the `_apply_buying_power_gate_legacy` helper after `_write_decision` (after line 314, before `def _regime_label` at :317).** Insert:

```python


def _apply_buying_power_gate_legacy(
    *,
    notional: float,
    buying_power: float | None,
    price: float,
    symbol: str,
    signal_id: "int | None",
    score: float,
    regime_mult: float,
    tick_time,
    pg_store,
    notifier: "Notifier | None",
    mode: str,
) -> "float | None":
    """Apply the buying_power pre-flight gate to the legacy execution BUY path (§1).

    Returns the (possibly capped) notional, or ``None`` to skip the BUY. Writes a
    Decision Log row + Telegram alert on shadow/cap/skip. The legacy path uses
    fractional qty (4 decimals), so ``is_fractionable=True``.
    """
    from src.portfolio.buying_power_gate import evaluate_buying_power_gate
    _gate = evaluate_buying_power_gate(
        notional=notional, buying_power=buying_power,
        is_fractionable=True, mode=mode, price=price,
    )
    if _gate.action == "skip":
        log.warning(
            "buying_power gate SKIP: %s notional=$%.2f — buying_power unavailable (bp=%s)",
            symbol, notional, buying_power,
        )
        _fire_alert(
            notifier,
            f"⚠️ buying_power gate SKIP {symbol}: buying_power unavailable "
            f"(bp={buying_power}) — order not submitted.",
            AlertLevel.WARNING,
        )
        _write_decision(
            pg_store, tick_time, symbol, signal_id, score, regime_mult,
            ema_pass=True, decision="SKIP_BUY_POWER",
            reason=f"buying_power unavailable (bp={buying_power}) — order skipped",
        )
        return None
    if _gate.action == "shadow":
        log.info(
            "buying_power gate SHADOW: %s notional=$%.2f > buying_power=$%.2f "
            "(delta $%.2f) — NOT capping (shadow mode)",
            symbol, notional, buying_power, _gate.delta,
        )
        _fire_alert(
            notifier,
            f"⚠️ buying_power gate SHADOW {symbol}: notional ${notional:.2f} "
            f"> buying_power ${buying_power:.2f} (delta ${_gate.delta:.2f}) — would cap.",
            AlertLevel.WARNING,
        )
        _write_decision(
            pg_store, tick_time, symbol, signal_id, score, regime_mult,
            ema_pass=True, decision="BUY_POWER_SHADOW",
            reason=f"would_cap delta=${_gate.delta:.2f} "
            f"(shadow mode, notional=${notional:.2f}, buying_power=${buying_power:.2f})",
        )
        return notional
    if _gate.action == "cap":
        _orig_notional = notional
        notional = _gate.capped_notional
        log.info(
            "buying_power gate CAP: %s notional $%.2f -> $%.2f "
            "(delta $%.2f, buying_power=$%.2f)",
            symbol, _orig_notional, notional, _gate.delta, buying_power,
        )
        _fire_alert(
            notifier,
            f"⚠️ buying_power gate CAP {symbol}: notional "
            f"${_orig_notional:.2f} -> ${notional:.2f} (delta ${_gate.delta:.2f}).",
            AlertLevel.WARNING,
        )
        _write_decision(
            pg_store, tick_time, symbol, signal_id, score, regime_mult,
            ema_pass=True, decision="BUY_POWER_CAP",
            reason=f"capped delta=${_gate.delta:.2f} "
            f"(notional ${_orig_notional:.2f} -> ${notional:.2f}, "
            f"buying_power=${buying_power:.2f})",
        )
        return notional
    return notional  # pass
```

**Edit C — call the helper after the price-None check (:720), before `qty = round(...)` (:722).** Replace:

```python
                continue

            qty = round(notional / price, 4)
```

with:

```python
                continue

            # §1 (2026-08-07): buying_power pre-flight gate (legacy path).
            notional = _apply_buying_power_gate_legacy(
                notional=notional,
                buying_power=buying_power,
                price=price,
                symbol=symbol,
                signal_id=signal_id,
                score=score,
                regime_mult=regime_mult,
                tick_time=tick_time,
                pg_store=pg_store,
                notifier=notifier,
                mode=config.BUYING_POWER_GATE_MODE,
            )
            if notional is None:
                stats["skipped_buy_power"] = stats.get("skipped_buy_power", 0) + 1
                continue

            qty = round(notional / price, 4)
```

- [ ] **Step 4: Run test to verify it passes**

```
pytest tests/test_buying_power_gate_legacy.py -x
```

Expected: `8 passed`.

- [ ] **Step 5: Commit**

```
git add src/workers/execution.py tests/test_buying_power_gate_legacy.py
git commit -m "feat(§1): wire buying_power gate into execution.py legacy BUY path

_apply_buying_power_gate_legacy helper (testable in isolation) called
after the price check @ :720, before qty derivation @ :722. Returns
capped notional or None (skip). Fractionable=True (legacy uses 4-decimal
qty). mode read from config.BUYING_POWER_GATE_MODE. Lower priority than
the portfolio_scheduler path (execution.engine=legacy_sentiment).

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Final verification

After all 5 tasks, run the full gate-related test suite plus the existing regime tests (backward-compat regression check):

```
pytest tests/test_config.py::TestBuyingPowerGateMode tests/test_buying_power_gate.py tests/test_buying_power_gate_wiring.py tests/test_buying_power_gate_legacy.py tests/test_p0_09_regime_multiplier.py -v
```

Expected: all green. The default `BUYING_POWER_GATE_MODE=shadow` means zero behavior change on deploy — the gate only logs + alerts until the operator flips to `cap`.