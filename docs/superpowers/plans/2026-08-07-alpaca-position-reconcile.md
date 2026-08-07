# Position reconciliation (EOD beat + alert + auto-close orphan) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Schedule Alembic's existing read-only position reconciler (`scripts/reconcile_open_trades_vs_broker.py::classify_positions`) as an EOD Celery beat task that (a) ALWAYS alerts on the three anomaly categories via Telegram, and (b) conditionally force-closes `genuinely_orphan` trades in the DB (flag-gated, default OFF + dry-run ON). This closes class #121 ("accounting DB divergente") — the reconciler exists but is referenced only in tests, never scheduled.

**Architecture:**
- New Celery beat task `reconcile-positions-eod` at `crontab(hour=21, minute=35, day_of_week="1-5")` (5 min after `reconcile-fills-evening` at 21:30) → new task `run_reconcile_positions` in `src/workers/performance.py`, mirroring `run_reconcile_fills_intraday`'s credential-guard + try/except + `pg.close()` shape.
- `run_reconcile_positions` wraps the existing pure `classify_positions` + `summarize` (reused, unmodified) and:
  1. **Alert (always on):** Telegram on `genuinely_orphan`, `over_held`, `untracked_position` (the other two — `fully_held`, `partially_wound_down_coheld` — are normal states, no alert).
  2. **Auto-close (flag-gated, default OFF):** only `genuinely_orphan`. Broker holds 0 → NO broker SELL order; it is a DB force-close via `record_trade_exit(exit_reason="orphan_reconcile")`. `over_held`/`untracked_position` are alerted only (auto-closing those = broker orders = out of scope, riskier).
- New pure coordinator `force_close_orphans(records, *, writer, dry_run, now)` in `scripts/reconcile_open_trades_vs_broker.py` — takes the classify output + a writer callable (abstraction over `pg.record_trade_exit`), filters to `genuinely_orphan`, calls the writer per orphan (unless dry-run), continues on per-trade errors (never bulk). `classify_positions` stays pure.
- Exit-price recovery: `run_reconcile_positions` best-effort recovers the real broker SELL order id for each orphan (`_recover_exit_order_id` via `trading_client.get_orders`) and patches it into the record so the existing `reconcile_trade_fills` beat (intraday + 21:30 evening) can populate `exit_price` from the fill. If no fill is found, `force_close_orphans` falls back to a synthetic `orphan_reconcile:<trade_id>` id and `exit_price` stays NULL until operator manual review ("last-known" fallback).
- Idempotency: `record_trade_exit` uses `COALESCE(exit_time, %s)` + `COALESCE(exit_reason, %s)` + `COALESCE(exit_order_id, %s)` + `array_position` dedup on `exit_order_ids` — re-calling with the same `trade_id` does not corrupt the row (first non-null wins). `force_close_orphans` is deterministic (same inputs → same writer calls).

**Tech Stack:** Python 3.11, Celery beat, alpaca-py (`TradingClient.get_all_positions` / `get_orders`), PostgreSQL (`pg_store.record_trade_exit` — reused, idempotent), Telegram (`TelegramNotifier.send_alert`), pytest with `unittest.mock`.

**Spec:** `docs/superpowers/specs/2026-08-07-alpaca-exec-hardening-design.md` §2 + Cross-cutting. Classification: correctness/tooling → `freeze-ok`. Money-path DB write → backup + operator sign-off + flag default-off.

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `scripts/reconcile_open_trades_vs_broker.py` | Modify | Add `force_close_orphans()` pure coordinator after `summarize` (line 108). `classify_positions`/`summarize`/`_fetch_inputs`/`main` stay unmodified. |
| `src/config.py` | Modify | Add `RECONCILE_AUTOCLOSE_ENABLED` (default `false`) + `RECONCILE_AUTOCLOSE_DRY_RUN` (default `true`) after line 326. |
| `src/workers/performance.py` | Modify | Add `run_reconcile_positions` Celery task + `_recover_exit_order_id` + `_format_reconcile_alert` helpers after `run_reconcile_fills_intraday` (line 695). |
| `src/workers/celery_app.py` | Modify | Add `reconcile-positions-eod` beat entry at 21:35 UTC Mon-Fri after `reconcile-fills-evening` (line 99). |
| `tests/test_reconcile_open_trades.py` | Modify | Add `force_close_orphans` tests (dry-run, writer call, non-orphan filter, idempotency, per-trade error isolation). |
| `tests/test_config.py` | Modify | Add `TestReconcileAutocloseFlags` (default-off, env-true, dry-run-off). |
| `tests/workers/test_reconcile_positions.py` | Create | `run_reconcile_positions` task tests (mock `trading_client` + `pg` + `TelegramNotifier` + `run_async` + `config`). |
| `tests/workers/test_ingestion_source_gating.py` | Modify | Add `test_reconcile_positions_eod_beat_entry` after line 47. |

---

## Tasks

### Task 1: `force_close_orphans()` pure coordinator

**Files:**
- Modify: `scripts/reconcile_open_trades_vs_broker.py` (insert between line 108 `return counts` and line 111 `def _fetch_inputs`)
- Test: `tests/test_reconcile_open_trades.py` (append after line 73; add `from unittest.mock import MagicMock` after line 3)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_reconcile_open_trades.py`. First, add the `MagicMock` import after the existing `from datetime import datetime, timezone` line (line 3):

```python
from unittest.mock import MagicMock
```

Then append these tests at the end of the file (after line 73). Each test lazy-imports `force_close_orphans` so the existing tests still pass during the red phase (the new function does not exist yet):

```python

# ---------------------------------------------------------------------------
# force_close_orphans — pure coordinator over record_trade_exit (spec §2)
# ---------------------------------------------------------------------------

def test_force_close_orphans_dry_run_writes_nothing():
    from scripts.reconcile_open_trades_vs_broker import force_close_orphans
    writer = MagicMock()
    orphans = [
        {"trade_id": 9, "symbol": "BBB", "category": "genuinely_orphan"},
        {"trade_id": 11, "symbol": "DDD", "category": "genuinely_orphan"},
    ]
    results = force_close_orphans(
        orphans, writer=writer, dry_run=True,
        now=datetime(2026, 7, 27, 21, 35, tzinfo=timezone.utc),
    )
    assert len(results) == 2
    assert all(r["dry_run"] is True and r["closed"] is False for r in results)
    assert all(r["exit_reason"] == "orphan_reconcile" for r in results)
    assert results[0]["exit_order_id"] == "orphan_reconcile:9"
    writer.assert_not_called()


def test_force_close_orphans_calls_writer_with_orphan_reconcile_reason():
    from scripts.reconcile_open_trades_vs_broker import force_close_orphans
    writer = MagicMock()
    orphans = [{"trade_id": 9, "symbol": "BBB", "category": "genuinely_orphan"}]
    now = datetime(2026, 7, 27, 21, 35, tzinfo=timezone.utc)
    results = force_close_orphans(orphans, writer=writer, dry_run=False, now=now)
    assert len(results) == 1
    r = results[0]
    assert r["closed"] is True
    assert r["dry_run"] is False
    assert r["exit_reason"] == "orphan_reconcile"
    assert r["exit_order_id"] == "orphan_reconcile:9"
    writer.assert_called_once_with(
        symbol="BBB",
        exit_order_id="orphan_reconcile:9",
        exit_time=now,
        exit_reason="orphan_reconcile",
        trade_id=9,
    )


def test_force_close_orphans_uses_record_exit_order_id_when_present():
    """If the caller enriched the record with a real broker order id (recovered
    by the Celery task), force_close_orphans must use it, not the synthetic id."""
    from scripts.reconcile_open_trades_vs_broker import force_close_orphans
    writer = MagicMock()
    orphans = [{"trade_id": 9, "symbol": "BBB", "category": "genuinely_orphan",
                "exit_order_id": "real-sell-123"}]
    force_close_orphans(orphans, writer=writer, dry_run=False,
                        now=datetime(2026, 7, 27, 21, 35, tzinfo=timezone.utc))
    _, kwargs = writer.call_args
    assert kwargs["exit_order_id"] == "real-sell-123"


def test_force_close_orphans_ignores_non_orphan_categories():
    from scripts.reconcile_open_trades_vs_broker import force_close_orphans
    writer = MagicMock()
    records = [
        {"trade_id": 1, "symbol": "AAA", "category": "fully_held"},
        {"trade_id": 2, "symbol": "CCC", "category": "over_held"},
        {"symbol": "ZZZ", "category": "untracked_position", "trade_id": None},
        {"trade_id": 3, "symbol": "WDC", "category": "partially_wound_down_coheld"},
    ]
    results = force_close_orphans(records, writer=writer, dry_run=False)
    assert results == []
    writer.assert_not_called()


def test_force_close_orphans_idempotent_rerun_is_noop():
    """Re-run with the same records: the writer (record_trade_exit) is idempotent
    via COALESCE — first write wins, the second call does not overwrite
    exit_time. The closed set after the second call equals the first."""
    from scripts.reconcile_open_trades_vs_broker import force_close_orphans
    closed_times: dict[int, datetime] = {}

    def writer(*, symbol, exit_order_id, exit_time, exit_reason, trade_id):
        # Simulate record_trade_exit's COALESCE(exit_time, %s): first write wins.
        if trade_id not in closed_times:
            closed_times[trade_id] = exit_time
        return trade_id

    orphans = [{"trade_id": 9, "symbol": "BBB", "category": "genuinely_orphan"}]
    now1 = datetime(2026, 7, 27, 21, 35, tzinfo=timezone.utc)
    force_close_orphans(orphans, writer=writer, dry_run=False, now=now1)
    now2 = datetime(2026, 7, 28, 21, 35, tzinfo=timezone.utc)
    force_close_orphans(orphans, writer=writer, dry_run=False, now=now2)
    # First-write-wins: the second call did not overwrite exit_time.
    assert closed_times[9] == now1


def test_force_close_orphans_continues_on_per_trade_error():
    from scripts.reconcile_open_trades_vs_broker import force_close_orphans

    def writer(*, symbol, exit_order_id, exit_time, exit_reason, trade_id):
        if trade_id == 9:
            raise RuntimeError("db error")
        return trade_id

    orphans = [
        {"trade_id": 9, "symbol": "BBB", "category": "genuinely_orphan"},
        {"trade_id": 11, "symbol": "DDD", "category": "genuinely_orphan"},
    ]
    results = force_close_orphans(orphans, writer=writer, dry_run=False)
    assert results[0]["closed"] is False
    assert "db error" in results[0]["error"]
    assert results[1]["closed"] is True
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/stefano/Documents/Projects/Alembic
.venv/bin/python -m pytest tests/test_reconcile_open_trades.py::test_force_close_orphans_dry_run_writes_nothing -x -q
```

Expected: `ImportError: cannot import name 'force_close_orphans' from 'scripts.reconcile_open_trades_vs_broker'` (the 6 new tests fail; the 7 existing tests still pass). This is the TDD red phase.

- [ ] **Step 3: Write minimal implementation**

In `scripts/reconcile_open_trades_vs_broker.py`, insert `force_close_orphans` between `summarize` (ends at line 108 `return counts`) and `_fetch_inputs` (line 111). Use this exact anchor for the `Edit` tool:

old_string:
```
def summarize(records: list[dict]) -> dict[str, int]:
    """Count records per category."""
    counts: dict[str, int] = {}
    for r in records:
        counts[r["category"]] = counts.get(r["category"], 0) + 1
    return counts


def _fetch_inputs() -> tuple[list[dict], dict[str, float]]:
```

new_string:
```
def summarize(records: list[dict]) -> dict[str, int]:
    """Count records per category."""
    counts: dict[str, int] = {}
    for r in records:
        counts[r["category"]] = counts.get(r["category"], 0) + 1
    return counts


def force_close_orphans(
    records: list[dict],
    *,
    writer,
    dry_run: bool = True,
    now: datetime | None = None,
) -> list[dict]:
    """Force-close genuinely_orphan trades via the writer callable (spec §2).

    Pure coordinator — no DB, no broker. The writer is an abstraction over
    PostgreSQLStore.record_trade_exit (caller passes pg.record_trade_exit or a
    mock). Idempotent at the DB layer via record_trade_exit's COALESCE; this
    function is deterministic (same inputs -> same writer calls).

    Only acts on records with category == "genuinely_orphan" and a non-null
    trade_id. The other anomaly categories (over_held, untracked_position) are
    alerted only by the caller — auto-closing those needs broker orders, out of
    scope. untracked_position records have trade_id=None and are skipped.

    If a record carries an "exit_order_id" (enriched by the Celery task from
    the broker order history), it is used; otherwise a synthetic
    "orphan_reconcile:<trade_id>" id is used so the existing reconcile_trade_fills
    beat can later populate exit_price from the real fill.

    Args:
        records: output of classify_positions (all categories; filtered here).
        writer: callable matching record_trade_exit's signature, called as
            writer(symbol=, exit_order_id=, exit_time=, exit_reason=, trade_id=).
        dry_run: True -> plan only, do NOT call the writer.
        now: exit_time (defaults to UTC now).

    Returns:
        List of result dicts, one per orphan:
            {trade_id, symbol, exit_order_id, exit_reason, dry_run, closed, error?}
    """
    now = now or datetime.now(timezone.utc)
    results: list[dict] = []
    for r in records:
        if r.get("category") != "genuinely_orphan" or r.get("trade_id") is None:
            continue
        trade_id = int(r["trade_id"])
        symbol = r["symbol"]
        exit_order_id = r.get("exit_order_id") or f"orphan_reconcile:{trade_id}"
        result = {
            "trade_id": trade_id,
            "symbol": symbol,
            "exit_order_id": exit_order_id,
            "exit_reason": "orphan_reconcile",
            "dry_run": dry_run,
            "closed": False,
        }
        if dry_run:
            results.append(result)
            continue
        try:
            writer(
                symbol=symbol,
                exit_order_id=exit_order_id,
                exit_time=now,
                exit_reason="orphan_reconcile",
                trade_id=trade_id,
            )
            result["closed"] = True
        except Exception as exc:
            result["error"] = str(exc)
        results.append(result)
    return results


def _fetch_inputs() -> tuple[list[dict], dict[str, float]]:
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /home/stefano/Documents/Projects/Alembic
.venv/bin/python -m pytest tests/test_reconcile_open_trades.py -q
```

Expected: `13 passed` (7 existing + 6 new). If any new test fails, re-read the `force_close_orphans` body and fix before proceeding.

- [ ] **Step 5: Commit**

```bash
cd /home/stefano/Documents/Projects/Alembic
git add scripts/reconcile_open_trades_vs_broker.py tests/test_reconcile_open_trades.py
git commit -m "feat(reconcile): add force_close_orphans pure coordinator (spec §2)

Idempotent DB force-close of genuinely_orphan trades via a writer callable
(abstraction over record_trade_exit). Dry-run by default; per-trade error
isolation. classify_positions stays pure.

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 2: Config flags `RECONCILE_AUTOCLOSE_ENABLED` + `RECONCILE_AUTOCLOSE_DRY_RUN`

**Files:**
- Modify: `src/config.py` (insert between line 326 `)  # FRED series ID for daily VIX data` and line 327 `MIN_TRADE_PNL_THRESHOLD`)
- Test: `tests/test_config.py` (append `TestReconcileAutocloseFlags` class after the last test)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_config.py` (after the last test in the file):

```python


class TestReconcileAutocloseFlags:
    """spec §2: auto-close is a money-path DB write -> default OFF + dry-run ON."""

    def test_autoclose_disabled_and_dry_run_on_by_default(self):
        from src.config import Config
        env = {
            k: v for k, v in os.environ.items()
            if k not in ("RECONCILE_AUTOCLOSE_ENABLED", "RECONCILE_AUTOCLOSE_DRY_RUN")
        }
        with patch.dict(os.environ, env, clear=True):
            cfg = Config(
                ADMIN_API_KEY="a" * 32,
                DATABASE_URL="postgresql://localhost:5432/test",
            )
        assert cfg.RECONCILE_AUTOCLOSE_ENABLED is False
        assert cfg.RECONCILE_AUTOCLOSE_DRY_RUN is True

    def test_autoclose_enabled_when_env_true(self):
        from src.config import Config
        with patch.dict(os.environ, {"RECONCILE_AUTOCLOSE_ENABLED": "true"}):
            cfg = Config(
                ADMIN_API_KEY="a" * 32,
                DATABASE_URL="postgresql://localhost:5432/test",
            )
        assert cfg.RECONCILE_AUTOCLOSE_ENABLED is True

    def test_autoclose_dry_run_off_when_env_false(self):
        from src.config import Config
        with patch.dict(os.environ, {"RECONCILE_AUTOCLOSE_DRY_RUN": "false"}):
            cfg = Config(
                ADMIN_API_KEY="a" * 32,
                DATABASE_URL="postgresql://localhost:5432/test",
            )
        assert cfg.RECONCILE_AUTOCLOSE_DRY_RUN is False
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/stefano/Documents/Projects/Alembic
.venv/bin/python -m pytest tests/test_config.py::TestReconcileAutocloseFlags -x -q
```

Expected: `AttributeError: 'Config' object has no attribute 'RECONCILE_AUTOCLOSE_ENABLED'` (Pydantic v2) or similar — the fields do not exist yet.

- [ ] **Step 3: Write minimal implementation**

In `src/config.py`, insert the two flags between line 326 (`)  # FRED series ID for daily VIX data`) and line 327 (`MIN_TRADE_PNL_THRESHOLD`). Use this exact anchor:

old_string:
```
    AUTO_APPLY_VIX_FRED_SERIES: str = Field(
        default_factory=lambda: os.environ.get("AUTO_APPLY_VIX_FRED_SERIES", "VIXCLS")
    )  # FRED series ID for daily VIX data
    MIN_TRADE_PNL_THRESHOLD: float = Field(
```

new_string:
```
    AUTO_APPLY_VIX_FRED_SERIES: str = Field(
        default_factory=lambda: os.environ.get("AUTO_APPLY_VIX_FRED_SERIES", "VIXCLS")
    )  # FRED series ID for daily VIX data

    # Reconcile EOD position autoclose — money-path DB write (spec §2).
    # Default OFF + dry-run: first runs only log what would be closed. Flip to
    # live only after the operator reviews a dry-run + backs up the trades table.
    RECONCILE_AUTOCLOSE_ENABLED: bool = Field(
        default_factory=lambda: os.environ.get("RECONCILE_AUTOCLOSE_ENABLED", "false").lower() == "true"
    )  # Master switch — false = alert-only, never close
    RECONCILE_AUTOCLOSE_DRY_RUN: bool = Field(
        default_factory=lambda: os.environ.get("RECONCILE_AUTOCLOSE_DRY_RUN", "true").lower() == "true"
    )  # True = plan only (no writer calls); false = live force-close
    MIN_TRADE_PNL_THRESHOLD: float = Field(
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /home/stefano/Documents/Projects/Alembic
.venv/bin/python -m pytest tests/test_config.py::TestReconcileAutocloseFlags -q
```

Expected: `3 passed`.

- [ ] **Step 5: Commit**

```bash
cd /home/stefano/Documents/Projects/Alembic
git add src/config.py tests/test_config.py
git commit -m "feat(reconcile): add RECONCILE_AUTOCLOSE_* config flags (spec §2)

RECONCILE_AUTOCLOSE_ENABLED default false (alert-only), DRY_RUN default true
(plan only). Money-path DB write -> default-off + operator sign-off.

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 3: `run_reconcile_positions` Celery task

**Files:**
- Modify: `src/workers/performance.py` (insert new task + 2 helpers between line 695 `pg.close()` and line 698 `def _broker_mtm_snapshot`)
- Test: `tests/workers/test_reconcile_positions.py` (Create)

- [ ] **Step 1: Write the failing test**

Create `tests/workers/test_reconcile_positions.py`:

```python
"""EOD position reconciliation task (spec §2): alert on anomalies + flag-gated
auto-close of genuinely_orphan trades. Mirrors run_reconcile_fills_intraday's
credential guard + try/except shape."""
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from src.workers.performance import run_reconcile_positions


def _mock_pg(open_trades):
    pg = MagicMock()
    pg.fetch_trades.return_value = open_trades
    pg.record_trade_exit.return_value = 1
    return pg


def _mock_tc(held_positions, orders=None):
    tc = MagicMock()
    tc.get_all_positions.return_value = held_positions
    tc.get_orders.return_value = orders or []
    return tc


def _cfg(enabled=False, dry_run=True):
    cfg = MagicMock()
    cfg.ALPACA_API_KEY = "xxx"
    cfg.ALPACA_SECRET_KEY = "xxx"
    cfg.ALPACA_PAPER_MODE = True
    cfg.RECONCILE_AUTOCLOSE_ENABLED = enabled
    cfg.RECONCILE_AUTOCLOSE_DRY_RUN = dry_run
    return cfg


def _trade(tid, symbol, qty):
    return {"id": tid, "symbol": symbol, "qty": qty,
            "entry_time": "2026-07-22T16:00:00+00:00", "stop_strategy": "S4"}


def test_skips_when_no_credentials():
    cfg = _cfg()
    cfg.ALPACA_API_KEY = ""
    with patch("src.workers.performance.config", cfg):
        result = run_reconcile_positions()
    assert result["skipped"] is True
    assert result["reason"] == "no_credentials"


def test_alerts_on_genuinely_orphan_anomaly():
    pg = _mock_pg([_trade(9, "BBB", 3.0)])
    tc = _mock_tc([])  # broker holds nothing -> BBB is genuinely_orphan
    with patch("src.workers.performance.config", _cfg(enabled=False)), \
         patch("src.workers.performance.PostgreSQLStore", return_value=pg), \
         patch("alpaca.trading.client.TradingClient", return_value=tc), \
         patch("src.workers.performance.TelegramNotifier") as tn, \
         patch("src.workers.performance.run_async"):
        result = run_reconcile_positions()
    assert result["counts"]["genuinely_orphan"] == 1
    assert result["anomalies"] == 1
    tn.assert_called_once()
    msg = tn.return_value.send_alert.call_args.args[0]
    assert "genuinely_orphan" in msg
    pg.record_trade_exit.assert_not_called()  # autoclose disabled


def test_no_anomalies_sends_no_alert():
    pg = _mock_pg([_trade(1, "AAA", 2.0)])
    held = [MagicMock(symbol="AAA", qty="2.0")]  # fully_held -> not an anomaly
    tc = _mock_tc(held)
    with patch("src.workers.performance.config", _cfg(enabled=False)), \
         patch("src.workers.performance.PostgreSQLStore", return_value=pg), \
         patch("alpaca.trading.client.TradingClient", return_value=tc), \
         patch("src.workers.performance.TelegramNotifier") as tn, \
         patch("src.workers.performance.run_async"):
        result = run_reconcile_positions()
    assert result["anomalies"] == 0
    tn.assert_not_called()


def test_autoclose_dry_run_does_not_write():
    pg = _mock_pg([_trade(9, "BBB", 3.0)])
    tc = _mock_tc([])
    with patch("src.workers.performance.config", _cfg(enabled=True, dry_run=True)), \
         patch("src.workers.performance.PostgreSQLStore", return_value=pg), \
         patch("alpaca.trading.client.TradingClient", return_value=tc), \
         patch("src.workers.performance.TelegramNotifier"), \
         patch("src.workers.performance.run_async"):
        result = run_reconcile_positions()
    assert result["autoclose"]["dry_run"] is True
    assert result["autoclose"]["planned"] == 1
    assert result["autoclose"]["closed"] == 0
    pg.record_trade_exit.assert_not_called()


def test_autoclose_live_calls_record_trade_exit_with_synthetic_id():
    pg = _mock_pg([_trade(9, "BBB", 3.0)])
    tc = _mock_tc([])  # no broker SELL orders found -> synthetic id
    with patch("src.workers.performance.config", _cfg(enabled=True, dry_run=False)), \
         patch("src.workers.performance.PostgreSQLStore", return_value=pg), \
         patch("alpaca.trading.client.TradingClient", return_value=tc), \
         patch("src.workers.performance.TelegramNotifier"), \
         patch("src.workers.performance.run_async"):
        result = run_reconcile_positions()
    assert result["autoclose"]["dry_run"] is False
    assert result["autoclose"]["closed"] == 1
    pg.record_trade_exit.assert_called_once()
    _, kwargs = pg.record_trade_exit.call_args
    assert kwargs["exit_reason"] == "orphan_reconcile"
    assert kwargs["trade_id"] == 9
    assert kwargs["symbol"] == "BBB"
    assert kwargs["exit_order_id"] == "orphan_reconcile:9"
    assert isinstance(kwargs["exit_time"], datetime)


def test_autoclose_recovers_real_exit_order_id_from_broker():
    pg = _mock_pg([_trade(9, "BBB", 3.0)])
    order = MagicMock()
    order.id = "real-sell-123"
    order.status = MagicMock(value="filled")
    order.filled_avg_price = "150.00"
    tc = _mock_tc([], orders=[order])
    with patch("src.workers.performance.config", _cfg(enabled=True, dry_run=False)), \
         patch("src.workers.performance.PostgreSQLStore", return_value=pg), \
         patch("alpaca.trading.client.TradingClient", return_value=tc), \
         patch("src.workers.performance.TelegramNotifier"), \
         patch("src.workers.performance.run_async"):
        result = run_reconcile_positions()
    assert result["autoclose"]["closed"] == 1
    _, kwargs = pg.record_trade_exit.call_args
    assert kwargs["exit_order_id"] == "real-sell-123"


def test_over_held_and_untracked_are_alerted_not_closed():
    """over_held + untracked_position -> alerted only, never force-closed
    (auto-closing those = broker orders = out of scope)."""
    pg = _mock_pg([_trade(2, "CCC", 1.0)])
    # CCC over_held (broker holds 3.0 > 1.0) + ZZZ untracked (no DB trade)
    held = [MagicMock(symbol="CCC", qty="3.0"), MagicMock(symbol="ZZZ", qty="5.0")]
    tc = _mock_tc(held)
    with patch("src.workers.performance.config", _cfg(enabled=True, dry_run=False)), \
         patch("src.workers.performance.PostgreSQLStore", return_value=pg), \
         patch("alpaca.trading.client.TradingClient", return_value=tc), \
         patch("src.workers.performance.TelegramNotifier"), \
         patch("src.workers.performance.run_async"):
        result = run_reconcile_positions()
    assert result["counts"]["over_held"] == 1
    assert result["counts"]["untracked_position"] == 1
    assert result["anomalies"] == 2
    # No genuinely_orphan -> nothing to close.
    assert result["autoclose"]["closed"] == 0
    pg.record_trade_exit.assert_not_called()


def test_classify_error_never_crashes_worker_and_alerts():
    """spec §2: a classify error -> alert (best-effort), never crash the worker."""
    pg = _mock_pg([])
    pg.fetch_trades.side_effect = RuntimeError("db down")
    with patch("src.workers.performance.config", _cfg(enabled=False)), \
         patch("src.workers.performance.PostgreSQLStore", return_value=pg), \
         patch("alpaca.trading.client.TradingClient", return_value=MagicMock()), \
         patch("src.workers.performance.TelegramNotifier") as tn, \
         patch("src.workers.performance.run_async"):
        result = run_reconcile_positions()
    assert "error" in result
    assert "db down" in result["error"]
    tn.assert_called_once()  # failure alert sent
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/stefano/Documents/Projects/Alembic
.venv/bin/python -m pytest tests/workers/test_reconcile_positions.py -x -q
```

Expected: `ImportError: cannot import name 'run_reconcile_positions' from 'src.workers.performance'` (the task does not exist yet). This is the TDD red phase.

- [ ] **Step 3: Write minimal implementation**

In `src/workers/performance.py`, insert the new task + helpers between the end of `run_reconcile_fills_intraday` (line 695 `pg.close()`) and `def _broker_mtm_snapshot` (line 698). Use this exact anchor:

old_string:
```
    except Exception as exc:
        log.warning("Intraday fill reconciliation failed: %s", exc)
        return {"error": str(exc)}
    finally:
        pg.close()


def _broker_mtm_snapshot(trading_client) -> dict | None:
```

new_string:
```
    except Exception as exc:
        log.warning("Intraday fill reconciliation failed: %s", exc)
        return {"error": str(exc)}
    finally:
        pg.close()


@app.task(name="src.workers.performance.run_reconcile_positions")
def run_reconcile_positions() -> dict:
    """EOD position reconciliation (spec §2) — runs at 21:35 UTC Mon-Fri (after
    reconcile-fills-evening at 21:30).

    Classifies every open DB trade against the live broker position and:
    - ALWAYS alerts (Telegram) on the three anomaly categories:
      genuinely_orphan, over_held, untracked_position. The other two
      (fully_held, partially_wound_down_coheld) are normal states -> no alert.
    - Conditionally auto-closes genuinely_orphan trades (DB force-close only —
      broker holds 0, no SELL order) when config.RECONCILE_AUTOCLOSE_ENABLED.
      Dry-run by default (RECONCILE_AUTOCLOSE_DRY_RUN=true): logs only, no
      writer calls. over_held / untracked_position are alerted only.

    Mirrors run_reconcile_fills_intraday's credential guard + try/except shape.
    A classify-time error is caught, a best-effort Telegram failure-alert is sent,
    and {"error": ...} is returned — the worker never crashes (spec §2).
    """
    from scripts.reconcile_open_trades_vs_broker import (
        classify_positions, force_close_orphans, summarize,
    )

    if not config.ALPACA_API_KEY or not config.ALPACA_SECRET_KEY:
        return {"skipped": True, "reason": "no_credentials"}

    pg = PostgreSQLStore()
    try:
        from alpaca.trading.client import TradingClient
        tc = TradingClient(
            api_key=config.ALPACA_API_KEY,
            secret_key=config.ALPACA_SECRET_KEY,
            paper=config.ALPACA_PAPER_MODE,
        )
        open_trades = pg.fetch_trades(status="open", limit=1000)
        held = {p.symbol: float(p.qty) for p in tc.get_all_positions()}
        records = classify_positions(
            open_trades, held, now=datetime.now(timezone.utc)
        )
        counts = summarize(records)

        anomaly_categories = ("genuinely_orphan", "over_held", "untracked_position")
        anomalies = [r for r in records if r["category"] in anomaly_categories]
        if anomalies:
            try:
                notifier = TelegramNotifier()
                msg = _format_reconcile_alert(anomalies, counts)
                run_async(notifier.send_alert(msg, level="warning"))
            except Exception as exc:
                log.warning("Reconcile Telegram alert failed: %s", exc)

        closed_summary: dict = {"planned": 0, "closed": 0, "errors": 0, "dry_run": True}
        if config.RECONCILE_AUTOCLOSE_ENABLED:
            orphans = [r for r in records if r["category"] == "genuinely_orphan"]
            # Best-effort: recover the real broker SELL order id for each orphan
            # so the existing reconcile_trade_fills beat can populate exit_price
            # from the fill. None -> force_close_orphans uses a synthetic id.
            for r in orphans:
                oid = _recover_exit_order_id(tc, r["symbol"])
                if oid:
                    r["exit_order_id"] = oid
            results = force_close_orphans(
                records, writer=pg.record_trade_exit,
                dry_run=config.RECONCILE_AUTOCLOSE_DRY_RUN,
            )
            closed_summary = {
                "planned": len(results),
                "closed": sum(1 for x in results if x.get("closed")),
                "errors": sum(1 for x in results if x.get("error")),
                "dry_run": config.RECONCILE_AUTOCLOSE_DRY_RUN,
            }
            log.info(
                "Reconcile autoclose: planned=%d closed=%d errors=%d dry_run=%s",
                closed_summary["planned"], closed_summary["closed"],
                closed_summary["errors"], closed_summary["dry_run"],
            )

        return {"counts": counts, "anomalies": len(anomalies), "autoclose": closed_summary}
    except Exception as exc:
        log.warning("Position reconciliation failed: %s", exc)
        # spec §2: a classify error -> alert (best-effort), never crash the worker.
        try:
            notifier = TelegramNotifier()
            run_async(notifier.send_alert(
                f"<b>Position Reconciliation FAILED</b>\n{exc}", level="critical"))
        except Exception as inner:
            log.warning("Reconcile failure-alert Telegram send failed: %s", inner)
        return {"error": str(exc)}
    finally:
        pg.close()


def _recover_exit_order_id(trading_client, symbol: str) -> str | None:
    """Best-effort: return the most recent filled SELL order id for symbol, so
    the existing reconcile_trade_fills beat can populate exit_price from the
    fill. Returns None on any failure (force_close_orphans falls back to a
    synthetic "orphan_reconcile:<trade_id>" id)."""
    try:
        from alpaca.trading.enums import OrderSide, QueryOrderStatus
        from alpaca.trading.requests import GetOrdersRequest
        orders = trading_client.get_orders(
            GetOrdersRequest(
                status=QueryOrderStatus.CLOSED,
                symbols=[symbol],
                side=OrderSide.SELL,
                limit=1,
            )
        )
        for o in orders:
            status = getattr(getattr(o, "status", None), "value", None) or str(
                getattr(o, "status", "")
            )
            if status in ("filled", "partially_filled") and getattr(o, "filled_avg_price", None):
                return str(o.id)
    except Exception as exc:
        log.debug("exit_order_id recovery failed for %s: %s", symbol, exc)
    return None


def _format_reconcile_alert(anomalies: list[dict], counts: dict[str, int]) -> str:
    """Format the Telegram alert for the three anomaly categories (HTML)."""
    lines = ["<b>Position Reconciliation — anomalies</b>", ""]
    for cat in ("genuinely_orphan", "over_held", "untracked_position"):
        n = counts.get(cat, 0)
        if n:
            lines.append(f"• {cat}: {n}")
    lines.append("")
    for r in anomalies[:20]:
        tid = r.get("trade_id") or "—"
        lines.append(
            f"  #{tid} {r['symbol']} {r['category']} "
            f"(db={r['db_qty']:.4f} held={r['held_qty']:.4f})"
        )
    if len(anomalies) > 20:
        lines.append(f"  ... +{len(anomalies) - 20} more")
    return "\n".join(lines)


def _broker_mtm_snapshot(trading_client) -> dict | None:
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /home/stefano/Documents/Projects/Alembic
.venv/bin/python -m pytest tests/workers/test_reconcile_positions.py -q
```

Expected: `8 passed`. If any test fails, re-read the task body and helpers and fix before proceeding. Also run the existing performance tests to confirm no regression:

```bash
cd /home/stefano/Documents/Projects/Alembic
.venv/bin/python -m pytest tests/workers/test_shadow_report.py tests/workers/test_loss_feedback.py -q
```

Expected: all previously-passing tests still pass.

- [ ] **Step 5: Commit**

```bash
cd /home/stefano/Documents/Projects/Alembic
git add src/workers/performance.py tests/workers/test_reconcile_positions.py
git commit -m "feat(reconcile): add run_reconcile_positions Celery task (spec §2)

EOD position reconciliation: alerts on genuinely_orphan/over_held/
untracked_position via Telegram, and (flag-gated, default OFF + dry-run)
force-closes genuinely_orphan trades via record_trade_exit. Best-effort
recovers the real broker SELL order id so reconcile_trade_fills can populate
exit_price. Mirrors run_reconcile_fills_intraday's shape.

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 4: `reconcile-positions-eod` beat schedule entry

**Files:**
- Modify: `src/workers/celery_app.py` (insert between line 99 `},` of `reconcile-fills-evening` and line 100 `# Performance daily report`)
- Test: `tests/workers/test_ingestion_source_gating.py` (append after line 47)

- [ ] **Step 1: Write the failing test**

Append to `tests/workers/test_ingestion_source_gating.py` (after line 47, the end of `test_reconcile_fills_evening_points_to_reconcile_task`):

```python


def test_reconcile_positions_eod_beat_entry():
    """spec §2: EOD position reconciliation beat entry at 21:35 UTC Mon-Fri,
    pointing at the new run_reconcile_positions task."""
    from src.workers.celery_app import app
    entry = app.conf.beat_schedule["reconcile-positions-eod"]
    assert entry["task"] == "src.workers.performance.run_reconcile_positions"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/stefano/Documents/Projects/Alembic
.venv/bin/python -m pytest tests/workers/test_ingestion_source_gating.py::test_reconcile_positions_eod_beat_entry -x -q
```

Expected: `KeyError: 'reconcile-positions-eod'` (the beat entry does not exist yet).

- [ ] **Step 3: Write minimal implementation**

In `src/workers/celery_app.py`, insert the new beat entry between the `reconcile-fills-evening` block (ends at line 99 `},`) and the `# Performance daily report` comment (line 100). Use this exact anchor:

old_string:
```
    # P0-E: EOD reconcile pass at 21:30 UTC — catches any fills missed intraday.
    "reconcile-fills-evening": {
        "task": "src.workers.performance.run_reconcile_fills_intraday",
        "schedule": crontab(hour=21, minute=30, day_of_week="1-5"),
    },
    # Performance daily report at 03:00 UTC
```

new_string:
```
    # P0-E: EOD reconcile pass at 21:30 UTC — catches any fills missed intraday.
    "reconcile-fills-evening": {
        "task": "src.workers.performance.run_reconcile_fills_intraday",
        "schedule": crontab(hour=21, minute=30, day_of_week="1-5"),
    },
    # §2: EOD position reconciliation at 21:35 UTC Mon-Fri (5 min after
    # reconcile-fills-evening). Classifies open DB trades vs broker positions,
    # alerts on anomalies (genuinely_orphan/over_held/untracked_position), and
    # (flag-gated, default OFF + dry-run) force-closes genuinely_orphan trades
    # in the DB. Auto-close is a money-path DB write -> backup + operator sign-off.
    "reconcile-positions-eod": {
        "task": "src.workers.performance.run_reconcile_positions",
        "schedule": crontab(hour=21, minute=35, day_of_week="1-5"),
    },
    # Performance daily report at 03:00 UTC
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /home/stefano/Documents/Projects/Alembic
.venv/bin/python -m pytest tests/workers/test_ingestion_source_gating.py -q
```

Expected: `7 passed` (6 existing + 1 new).

- [ ] **Step 5: Commit**

```bash
cd /home/stefano/Documents/Projects/Alembic
git add src/workers/celery_app.py tests/workers/test_ingestion_source_gating.py
git commit -m "feat(reconcile): schedule reconcile-positions-eod beat at 21:35 UTC (spec §2)

New beat entry at crontab(hour=21, minute=35, day_of_week=1-5), 5 min after
reconcile-fills-evening, pointing at run_reconcile_positions.

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 5: Backup procedure (operator runbook — money-path DB write)

**Files:** None (operator runbook — execute before the first live auto-close flip, not committed code).

- [ ] **Step 1: Back up the `trades` table before the first live auto-close**

The auto-close (`RECONCILE_AUTOCLOSE_ENABLED=true` + `RECONCILE_AUTOCLOSE_DRY_RUN=false`) is a money-path DB write. Before flipping to live for the first time, take a CSV snapshot of the `trades` table so any bad force-close can be recovered. `backups/` is gitignored (per repo memory).

```bash
cd /home/stefano/Documents/Projects/Alembic
mkdir -p backups
docker compose exec postgres psql -U trading -d trading -c \
  "\copy (SELECT * FROM trades ORDER BY id) TO STDOUT WITH CSV HEADER" \
  > "backups/trades_pre_autoclose_$(date +%Y%m%d_%H%M%S).csv"
```

Expected: a file `backups/trades_pre_autoclose_<timestamp>.csv` containing every `trades` row. Verify the row count matches `SELECT COUNT(*) FROM trades`:

```bash
cd /home/stefano/Documents/Projects/Alembic
docker compose exec postgres psql -U trading -d trading -t -c "SELECT COUNT(*) FROM trades"
wc -l < backups/trades_pre_autoclose_*.csv  # should be COUNT + 1 (header)
```

- [ ] **Step 2: Operator reviews a dry-run before the flip**

Run the task once in dry-run mode (the default: `RECONCILE_AUTOCLOSE_ENABLED=true`, `RECONCILE_AUTOCLOSE_DRY_RUN=true`). Inspect the Celery log for `Reconcile autoclose: planned=N closed=0 errors=0 dry_run=True` and the Telegram alert listing the `genuinely_orphan` trades. Confirm every planned close is a real orphan (broker holds 0, DB says open). Only then flip `RECONCILE_AUTOCLOSE_DRY_RUN=false`.

```bash
# Trigger one dry-run manually (no need to wait for 21:35):
docker compose exec worker celery -A src.workers.celery_app call src.workers.performance.run_reconcile_positions
# Inspect the worker log for the "Reconcile autoclose: planned=..." line.
```

---

## Notes

- **`freeze-ok` (reconciliation, not tuning):** This plan is correctness/tooling per spec §2 — it schedules an existing read-only reconciler and adds an alert. It is NOT tuning (no strategy parameter changes, no sizing changes). The freeze #171 (03/08→28/09) permits `freeze-ok` work; this plan qualifies.
- **Money-path DB write → zero live impact until flipped:** The auto-close is the only state-mutating piece, and it is double-gated: `RECONCILE_AUTOCLOSE_ENABLED=false` (default) + `RECONCILE_AUTOCLOSE_DRY_RUN=true` (default). With both at defaults, `run_reconcile_positions` only classifies + alerts — `force_close_orphans` is never called (the `if config.RECONCILE_AUTOCLOSE_ENABLED:` block is skipped), so `record_trade_exit` is never invoked. Zero DB writes occur until the operator sets `RECONCILE_AUTOCLOSE_ENABLED=true` AND `RECONCILE_AUTOCLOSE_DRY_RUN=false`. The backup (Task 5) + operator sign-off are required before that flip.
- **Alert is always on:** Even with autoclose fully disabled, the Telegram alert on the three anomaly categories fires every EOD (21:35 UTC Mon-Fri) whenever anomalies exist. This means no stuck trade passes one EOD without a Telegram alert (spec §2 success criterion), regardless of the autoclose flags.
- **Idempotency:** `record_trade_exit` is idempotent via `COALESCE(exit_time, %s)` + `COALESCE(exit_reason, %s)` + `COALESCE(exit_order_id, %s)` + `array_position` dedup on `exit_order_ids` (`src/store/pg_store.py:1026-1036`). Re-running `run_reconcile_positions` after a successful auto-close re-classifies (the closed trade is no longer in `open_trades`, so it does not appear as `genuinely_orphan`), and even if it did, `force_close_orphans` would call `record_trade_exit` again with no corruption (first non-null wins).
- **Exit-price recovery:** `run_reconcile_positions` best-effort recovers the real broker SELL order id (`_recover_exit_order_id`) so the existing `reconcile_trade_fills` beat (intraday every 15 min + evening 21:30) can populate `exit_price` from the fill. If no fill is found, the synthetic `orphan_reconcile:<trade_id>` id is used and `exit_price` stays NULL until operator manual review (the "last-known" fallback in spec §2). This is a best-effort recovery, not a synchronous fill fetch — it never blocks the force-close.
- **Out of scope (per spec §2 Cross-cutting):** auto-close of `over_held` / `untracked_position` (would need broker orders — riskier, separate governance); §5 trailing-stop implementation (frozen by #171 until 28/09); retry of non-Alpaca calls; TIF / twin-bug / pin fixes (already deployed, commit `71315b9`).
- **`record_trade_exit` reuse, not modification:** per spec §2 Files, `record_trade_exit` is reused as-is. Its signature is `(self, symbol, exit_order_id, exit_time, exit_reason, *, trade_id=None, is_final=True) -> int | None` (`src/store/pg_store.py:973-982`). `force_close_orphans` calls it via the writer callable with keyword args matching this signature; `is_final` defaults to `True` (sets `exit_time` + `exit_reason`), which is the desired force-close semantics.