#!/usr/bin/env python3
"""#397: one-off repair of the three phantom-quantity rows (NOK/WDC/MRVL).

These open trades carried their entry quantity forever (record_trade_exit never
decremented qty; broker-side stop fills were never written back), so the book
overstated the position 2.8x-74x vs the broker (~$1,870 phantom notional, [F-048]).

The fix lives in PostgreSQLStore.reconcile_open_positions: it recomputes
trades.quantity_remaining from the broker's full SELL-fill history (portfolio
tranches + protective-stop fills), appends any unrecorded stop order ids to
exit_order_ids, and closes the trade if the position is exhausted. This script
just runs that path for the three symbols with a lookback wide enough to reach
their late-July entries (the daily task's 30-day window already misses them).

Idempotent: reconcile_open_positions is a recompute, so re-running with the
same broker state changes nothing after the first pass. Read-only verification
before/after; it writes only trades.quantity_remaining / exit_order_ids /
exit_time (never exit_price or P&L — those stay with reconcile_trade_fills,
which prices from the real order ids now linked).

Does NOT rewrite docs/evidence/market_daily.jsonl (append-only ledger — the
contamination is noted in the issue, not backfilled). The operator runs this
once after applying migration 057; the daily reconcile_open_positions task
keeps every other open position correct going forward.

Run inside the worker container:
    docker compose exec worker python scripts/repair_phantom_quantities_397.py
Or locally against the live DB/broker:
    DATABASE_URL=postgresql://trading:trading@localhost:5432/trading \\
        .venv/bin/python scripts/repair_phantom_quantities_397.py
"""
from __future__ import annotations

import sys

# The three symbols from the 2026-08-26/27 alpha-miss reports ([F-048]). Their
# entries date to 2026-07-20/21, so look back 120 days to be safe regardless of
# when the operator runs this.
SYMBOLS = ["NOK", "WDC", "MRVL"]
LOOKBACK_DAYS = 120


def main() -> int:
    from alpaca.trading.client import TradingClient

    from src.config import config
    from src.store.pg_store import PostgreSQLStore

    if not config.ALPACA_API_KEY or not config.ALPACA_SECRET_KEY:
        print("ERROR: ALPACA_API_KEY / ALPACA_SECRET_KEY not set — cannot pull "
              "broker order history.", file=sys.stderr)
        return 2

    pg = PostgreSQLStore()
    tc = TradingClient(
        api_key=config.ALPACA_API_KEY,
        secret_key=config.ALPACA_SECRET_KEY,
        paper=config.ALPACA_PAPER_MODE,
    )
    try:
        print("=== #397 phantom-quantity repair ===")
        print(f"symbols: {SYMBOLS}   lookback: {LOOKBACK_DAYS} days")
        print("\n-- before --")
        for t in pg.fetch_trades(status="open", limit=1000):
            if t["symbol"] in SYMBOLS:
                print(f"  #{t['id']:>4} {t['symbol']:<5} "
                      f"qty={t.get('qty')} remaining={t.get('quantity_remaining')} "
                      f"exit_order_ids={t.get('exit_order_ids')}")

        updated = pg.reconcile_open_positions(
            tc, symbols=SYMBOLS, lookback_days=LOOKBACK_DAYS,
        )
        print(f"\nreconcile_open_positions updated {updated} row(s)")

        print("\n-- after --")
        for t in pg.fetch_trades(status="open", limit=1000):
            if t["symbol"] in SYMBOLS:
                print(f"  #{t['id']:>4} {t['symbol']:<5} "
                      f"qty={t.get('qty')} remaining={t.get('quantity_remaining')} "
                      f"exit_order_ids={t.get('exit_order_ids')}")
        print("\nDone. Verify the broker positions match `remaining` above, then "
              "let reconcile-fills-evening price any newly-closed rows.")
        return 0
    finally:
        pg.close()


if __name__ == "__main__":
    sys.exit(main())