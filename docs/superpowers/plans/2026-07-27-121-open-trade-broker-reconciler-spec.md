# #121 — Read-only open-trade ↔ broker reconciler — Execution Spec

> **For the executing agent:** You have NO prior context on this repo. Read this whole document once, then execute the single task exactly as written, on ONE git branch with ONE PR. Do NOT improvise beyond this spec. A human reviewer reviews the PR before merge.

**Repo:** `/home/stefano/Documents/Projects/Alembic` — an LLM-based paper-trading system. This is a **read-only diagnostic script** — it queries the DB and the broker and prints a classification. It **mutates nothing** (no writes to `trades`, no orders, no config). Zero money-path risk by construction.

**Goal (partial #121):** WDC trade #373 has looked like a stuck "orphan" in forensic reports for days, but it is actually a legitimate partially-wound-down position still co-held by strategy S1 (operator decision 2026-07-27: leave such residuals to the co-holding strategy). Give the forensic layer (and humans) a tool that **distinguishes a legit co-held residual from a genuinely stuck orphan**, so the false High-severity flags stop. This ticket delivers ONLY that read-only classifier — it does NOT change any accounting, does NOT close trades, does NOT decrement `trades.qty`.

**Explicitly out of scope (do NOT attempt):** decrementing `trades.qty` (it is the P&L cost-basis — `net_pnl = ((exit_price − entry_price) * qty) − costs`, `pg_store.py:822` — mutating it corrupts P&L); booking partial-close realized P&L; re-attributing a residual's strategy; closing any trade. Those are separate operator decisions, not this task.

**Tech stack:** Python 3, `alpaca-py` (`TradingClient`), `PostgreSQLStore`, pytest (run via `uv run pytest`). `scripts/` is an importable package (`scripts/__init__.py` exists); tests import via `from scripts.<module> import <fn>`.

**Branch:** `feat/121-open-trade-broker-reconciler`

---

## Session protocol

1. **Test runner:** always `uv run pytest <path> -v`; `uv run pytest -q` for the full suite. Never bare `pytest`.
2. **TDD, strictly:** write the failing tests for the pure functions → run and SEE them fail → implement → run and SEE them pass → commit. The `main()` wiring (DB + broker) is not unit-tested; only the pure functions are.
3. **One branch + one PR** (name above). PR body must contain `closes #121` ONLY IF the reviewer confirms this partial fix closes the issue — otherwise reference `#121` and let the reviewer decide (this delivers the read-only classifier the operator asked for; deeper accounting gaps are separate). Default: write `Part of #121` in the PR body, not `closes`.
4. **Create ONLY these files:** `scripts/reconcile_open_trades_vs_broker.py` and `tests/test_reconcile_open_trades.py`. Do not modify any existing file.
5. **No DB migrations, no config, no writes anywhere.** The script must never call any method that writes (no `record_*`, no `submit_order`, no `cancel_*`, no `write_*`). Only reads: `pg.fetch_trades(...)` and `trading_client.get_all_positions()`.
6. **Full-suite gate before the PR:** capture the baseline first (`uv run pytest -q 2>&1 | tail -5`). Known pre-existing failures (NOT yours): `tests/store/test_pg_store_stop_methods.py::test_fixed_mode_freezes_audit_fields` (issue #112) and a flaky `tests/api/test_strategies_routes.py::test_get_s1_backtest_returns_equity_curve`.
7. **Do not deploy, do not run the script against the live broker, do not push to `main`.** PR only. (The reviewer runs it against the live DB/broker.)
8. **When ADDING a test class, APPEND it** — never insert by replacing an adjacent `class`/`def` declaration. Before the PR, `git diff main` must show no removed `class`/`def` lines.

---

## Background (verified in code — you may rely on these facts)

- A trade is "open" in the DB iff `exit_time IS NULL`. `pg.fetch_trades(status="open", limit=N)` returns open-trade dicts with keys including `id, symbol, qty, entry_time, stop_strategy` (`qty` = the entry quantity, never decremented; `stop_strategy` = the strategy attribution, e.g. "S1"/"S4").
- The pyramiding guard guarantees **at most one open trade per symbol**, so an open trade's `qty` can be compared directly to that symbol's currently-held broker quantity.
- Broker positions come from `trading_client.get_all_positions()`; each has `.symbol` and `.qty` (a string; `float(p.qty)` = signed held quantity). A symbol with no position is simply absent from that list (held = 0).
- The WDC case: DB open trade qty `2.981`, broker held `1.334` → partial wind-down, residual legitimately co-held by S1. This must classify as **not an orphan**.

## The classification (what to build)

A pure function `classify_positions(open_trades, held_qty_by_symbol, *, now, eps=1e-4, match_tol_pct=0.02)` returning one record per open trade, plus one record per broker-held symbol that has no open trade. Each record is a dict: `{trade_id, symbol, strategy, db_qty, held_qty, sold_qty, days_open, category}`.

Category rules, per open trade (let `held = held_qty_by_symbol.get(symbol, 0.0)`, `db = db_qty`):
- `held <= eps` → **`genuinely_orphan`** (DB says open, broker holds nothing — the real stuck case worth flagging)
- `held >= db * (1 + match_tol_pct)` → **`over_held`** (broker holds materially more than the entry basis — untracked add)
- `held >= db * (1 - match_tol_pct)` → **`fully_held`** (within ±2% of entry — nothing meaningfully sold)
- otherwise (`eps < held < db*(1-tol)`) → **`partially_wound_down_coheld`** (partial exits, residual still held — the WDC case, NOT an orphan)

Plus, for every symbol in `held_qty_by_symbol` with `held > eps` that is NOT the symbol of any open trade → one record with `trade_id=None, db_qty=0.0, category="untracked_position"` (a held position with no open trade row — a different real accounting hole).

`sold_qty = max(0.0, db_qty - held_qty)` (0.0 for untracked). `days_open = (now - entry_time).days`, where `entry_time` may be a `datetime` or an ISO string (normalize with `datetime.fromisoformat` if a string; treat naive as UTC); `None` for untracked.

A second pure helper `summarize(records) -> dict[str, int]` returns the count per category.

---

## Steps

- [ ] **Step 1 — Write the failing tests.** Create `tests/test_reconcile_open_trades.py`:

```python
"""#121: read-only classifier distinguishing legit co-held residuals from
genuinely-stuck orphan trades. Pure-function tests (no DB, no broker)."""
from datetime import datetime, timezone

from scripts.reconcile_open_trades_vs_broker import classify_positions, summarize


def _trade(tid, symbol, qty, strategy="S4", entry_days_ago=5):
    entry = datetime(2026, 7, 22, 16, 0, tzinfo=timezone.utc)
    return {"id": tid, "symbol": symbol, "qty": qty, "entry_time": entry,
            "stop_strategy": strategy}


NOW = datetime(2026, 7, 27, 16, 0, tzinfo=timezone.utc)


def _one(records, symbol):
    return next(r for r in records if r["symbol"] == symbol)


def test_fully_held():
    recs = classify_positions([_trade(1, "AAA", 2.0)], {"AAA": 2.0}, now=NOW)
    assert _one(recs, "AAA")["category"] == "fully_held"
    assert _one(recs, "AAA")["sold_qty"] == 0.0


def test_partial_wind_down_coheld_is_not_orphan():
    # WDC case: entered 2.981, broker still holds 1.334.
    recs = classify_positions([_trade(373, "WDC", 2.981064744, strategy="S1")],
                              {"WDC": 1.334697164}, now=NOW)
    r = _one(recs, "WDC")
    assert r["category"] == "partially_wound_down_coheld"
    assert r["strategy"] == "S1"
    assert round(r["sold_qty"], 4) == round(2.981064744 - 1.334697164, 4)
    assert r["days_open"] == 5


def test_genuinely_orphan_when_broker_holds_nothing():
    recs = classify_positions([_trade(9, "BBB", 3.0)], {}, now=NOW)  # BBB absent = 0 held
    assert _one(recs, "BBB")["category"] == "genuinely_orphan"


def test_over_held_when_broker_exceeds_entry():
    recs = classify_positions([_trade(2, "CCC", 1.0)], {"CCC": 3.0}, now=NOW)
    assert _one(recs, "CCC")["category"] == "over_held"


def test_untracked_position_has_no_trade_row():
    recs = classify_positions([_trade(1, "AAA", 2.0)], {"AAA": 2.0, "ZZZ": 5.0}, now=NOW)
    z = _one(recs, "ZZZ")
    assert z["category"] == "untracked_position"
    assert z["trade_id"] is None
    assert z["db_qty"] == 0.0


def test_entry_time_accepts_iso_string():
    t = _trade(1, "AAA", 2.0)
    t["entry_time"] = "2026-07-25T16:00:00+00:00"
    recs = classify_positions([t], {"AAA": 2.0}, now=NOW)
    assert _one(recs, "AAA")["days_open"] == 2


def test_summarize_counts_by_category():
    recs = classify_positions(
        [_trade(1, "AAA", 2.0), _trade(9, "BBB", 3.0), _trade(373, "WDC", 2.98, strategy="S1")],
        {"AAA": 2.0, "WDC": 1.33, "ZZZ": 5.0},
        now=NOW,
    )
    counts = summarize(recs)
    assert counts["fully_held"] == 1
    assert counts["genuinely_orphan"] == 1
    assert counts["partially_wound_down_coheld"] == 1
    assert counts["untracked_position"] == 1
```

- [ ] **Step 2 — Run the tests, confirm they fail.**

Run: `uv run pytest tests/test_reconcile_open_trades.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.reconcile_open_trades_vs_broker'`.

- [ ] **Step 3 — Implement the script.** Create `scripts/reconcile_open_trades_vs_broker.py`:

```python
#!/usr/bin/env python3
"""#121: read-only reconciler — classify every open DB trade against the live
broker position, so forensics can tell a legit partially-wound-down co-held
residual (e.g. WDC held by S1) from a genuinely-stuck orphan.

Read-only / idempotent. Mutates NOTHING: it only calls pg.fetch_trades(...) and
trading_client.get_all_positions(). It never closes a trade, never touches
trades.qty (the P&L cost-basis), never submits/cancels orders.

Categories (per open trade; pyramiding guard => at most one open trade/symbol):
  fully_held                    broker holds ~ the entry qty (nothing sold)
  partially_wound_down_coheld   0 < held < entry qty — partial exits, residual
                                still held (legit under the 2026-07-27 operator
                                decision to leave residuals to the co-holder)
  genuinely_orphan              DB says open but broker holds nothing (real stuck
                                trade — the state worth flagging/acting on)
  over_held                     broker holds materially MORE than the entry basis
  untracked_position            broker holds a symbol with no open trade row

Exit code: non-zero iff any genuinely_orphan is found (usable as a cron gate);
zero otherwise.

Run inside the worker container:
    docker compose exec worker python scripts/reconcile_open_trades_vs_broker.py
Or locally against the live DB/broker:
    DATABASE_URL=postgresql://trading:trading@localhost:5432/trading \\
        .venv/bin/python scripts/reconcile_open_trades_vs_broker.py
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone


def _to_dt(value) -> datetime:
    """Normalize entry_time (datetime or ISO string) to an aware UTC datetime."""
    dt = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def classify_positions(
    open_trades: list[dict],
    held_qty_by_symbol: dict[str, float],
    *,
    now: datetime,
    eps: float = 1e-4,
    match_tol_pct: float = 0.02,
) -> list[dict]:
    """Classify each open trade vs the held broker qty, plus untracked positions.

    Pure function — no DB, no broker. See module docstring for categories.
    """
    records: list[dict] = []
    trade_symbols: set[str] = set()

    for t in open_trades:
        symbol = t["symbol"]
        trade_symbols.add(symbol)
        db_qty = float(t.get("qty") or 0.0)
        held = float(held_qty_by_symbol.get(symbol, 0.0))

        if held <= eps:
            category = "genuinely_orphan"
        elif held >= db_qty * (1 + match_tol_pct):
            category = "over_held"
        elif held >= db_qty * (1 - match_tol_pct):
            category = "fully_held"
        else:
            category = "partially_wound_down_coheld"

        entry_time = t.get("entry_time")
        days_open = (now - _to_dt(entry_time)).days if entry_time is not None else None
        records.append({
            "trade_id": t.get("id"),
            "symbol": symbol,
            "strategy": t.get("stop_strategy"),
            "db_qty": db_qty,
            "held_qty": held,
            "sold_qty": max(0.0, db_qty - held),
            "days_open": days_open,
            "category": category,
        })

    for symbol, held in held_qty_by_symbol.items():
        if symbol in trade_symbols or float(held) <= eps:
            continue
        records.append({
            "trade_id": None,
            "symbol": symbol,
            "strategy": None,
            "db_qty": 0.0,
            "held_qty": float(held),
            "sold_qty": 0.0,
            "days_open": None,
            "category": "untracked_position",
        })

    return records


def summarize(records: list[dict]) -> dict[str, int]:
    """Count records per category."""
    counts: dict[str, int] = {}
    for r in records:
        counts[r["category"]] = counts.get(r["category"], 0) + 1
    return counts


def _fetch_inputs() -> tuple[list[dict], dict[str, float]]:
    """Read open trades from the DB and held quantities from the broker."""
    from alpaca.trading.client import TradingClient

    from src.config import config
    from src.store.pg_store import PostgreSQLStore

    pg = PostgreSQLStore()
    try:
        open_trades = pg.fetch_trades(status="open", limit=1000)
    finally:
        pg.close()

    client = TradingClient(
        api_key=config.ALPACA_API_KEY,
        secret_key=config.ALPACA_SECRET_KEY,
        paper=config.ALPACA_PAPER_MODE,
    )
    held = {p.symbol: float(p.qty) for p in client.get_all_positions()}
    return open_trades, held


def main() -> int:
    open_trades, held = _fetch_inputs()
    records = classify_positions(open_trades, held, now=datetime.now(timezone.utc))
    counts = summarize(records)

    print("=== Open-trade ↔ broker reconciliation ===")
    print(f"open trades: {len(open_trades)}   held symbols: {len(held)}")
    print("counts:", {k: counts[k] for k in sorted(counts)})
    print()
    header = f"{'trade_id':>8} {'symbol':<8} {'strat':<6} {'db_qty':>12} {'held':>12} {'sold':>12} {'days':>5}  category"
    print(header)
    order = {
        "genuinely_orphan": 0, "untracked_position": 1, "over_held": 2,
        "partially_wound_down_coheld": 3, "fully_held": 4,
    }
    for r in sorted(records, key=lambda x: (order.get(x["category"], 9), x["symbol"])):
        tid = "" if r["trade_id"] is None else r["trade_id"]
        days = "" if r["days_open"] is None else r["days_open"]
        print(f"{str(tid):>8} {r['symbol']:<8} {str(r['strategy'] or ''):<6} "
              f"{r['db_qty']:>12.6f} {r['held_qty']:>12.6f} {r['sold_qty']:>12.6f} "
              f"{str(days):>5}  {r['category']}")

    n_orphan = counts.get("genuinely_orphan", 0)
    if n_orphan:
        print(f"\nFAIL: {n_orphan} genuinely-orphan trade(s) — DB open but broker holds nothing.")
    return 1 if n_orphan else 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4 — Run the tests, confirm they pass.**

Run: `uv run pytest tests/test_reconcile_open_trades.py -v`
Expected: PASS (all 7 tests).

- [ ] **Step 5 — Import-check the script (no accidental import-time side effects).**

Run: `uv run python -c "import scripts.reconcile_open_trades_vs_broker as m; print(m.summarize([]))"`
Expected: prints `{}` with no error (importing the module must NOT touch the DB or broker — only `main()` does).

- [ ] **Step 6 — Commit.**

```bash
git add scripts/reconcile_open_trades_vs_broker.py tests/test_reconcile_open_trades.py
git commit -m "feat(#121): read-only open-trade vs broker reconciler

Classify each open DB trade against the live broker position so forensics can
distinguish a legit partially-wound-down co-held residual (WDC held by S1) from
a genuinely-stuck orphan. Read-only: never mutates trades, never touches qty
(the P&L cost-basis), never submits/cancels orders. Exits non-zero only when a
genuinely-orphan trade is found.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

- [ ] **Step 7 — Full suite + PR.** `uv run pytest -q` (baseline-identical failures only), then open the PR. Body: `Part of #121` + a 3-line summary. Do NOT write `closes #121` — the reviewer decides whether this partial fix closes the issue.

---

## Hand-back checklist (for the human reviewer)

- Confirm the script is genuinely read-only (grep for any write call — there must be none). Run it against the live DB/broker: `docker compose exec worker python scripts/reconcile_open_trades_vs_broker.py` and check WDC classifies as `partially_wound_down_coheld` (not orphan), and that the exit code is 0 unless a real orphan exists.
- Decide whether to wire this into the daily forensic (so it stops prose-flagging co-held residuals) and whether this partial delivery closes #121 or the deeper accounting gaps (deferred partial realized-P&L; strategy re-attribution) stay open as separate operator decisions.
