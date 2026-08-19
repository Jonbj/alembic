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

    Uses a pre-linked ``exit_order_id`` when the caller already has one;
    otherwise uses a synthetic "orphan_reconcile:<trade_id>" id. The scheduled
    reconciler does not infer that link from symbol-only broker history because
    doing so could copy a historical fill into this trade and corrupt its price,
    quantity and P&L. Those fields therefore remain unreconciled for synthetic ids.

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
