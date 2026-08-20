# Alpaca `client_order_id` dedup spike

**Prepared:** 2026-08-18
**Environment:** Alpaca paper trading
**Script:** `scripts/verify_alpaca_coid_dedup.py`

## Documentation check

Alpaca's current Trading API v2 reference defines `client_order_id` as unique,
queryable through `GET /orders:by_client_order_id`, and limited to 128 characters:

- <https://docs.alpaca.markets/us/reference/postorder>
- <https://docs.alpaca.markets/us/reference/getorderbyclientorderid>

The official Alpaca CLI guidance is more explicit: duplicate IDs are rejected
with HTTP 409, and an ambiguous failure must be resolved by looking up the order
by `client_order_id` before any retry:

- <https://github.com/alpacahq/cli/blob/main/.agents/skills/alpaca-cli/SKILL.md>

This corrects the implementation plan's stale 1024-character assumption. The
builder in `src/portfolio/order_id.py` enforces the documented 128-character
limit, preserving uniqueness for oversized inputs with a hash suffix.

## Sandbox result

**PENDING — not run in this worktree.** Neither `ALPACA_API_KEY` nor
`ALPACA_SECRET_KEY` is available in the execution environment. No order was
submitted and no broker-side verdict is claimed.

Run with paper credentials:

```bash
ALPACA_API_KEY=<paper_key> ALPACA_SECRET_KEY=<paper_secret> \
  .venv/bin/python scripts/verify_alpaca_coid_dedup.py
```

Expected output is a JSON object. A safe verdict is
`"verdict": "dedup_confirmed"` with either:

- `"behavior": "conflict_409"` and `lookup_order_id == first_order_id`; or
- `"behavior": "returned_original"` and `second_order_id == first_order_id`.

`"no_dedup"` or `"inconclusive"` must keep submit retries disabled. The script
tests an immediate retry after five seconds only; it does not establish a longer
deduplication window. It requests cancellation of the first paper order after
the probe, including both IDs if the broker creates a duplicate, but cleanup is
best-effort because a market order may already fill.

## When to run it: outside market hours

**Run the spike while the US market is closed.** The probe submits a $1 notional
**market** BUY on **AAPL**, and AAPL is a position the paper book already holds
(qty 2.4579 on 2026-08-20). During regular trading hours that order fills
essentially on submission, cancellation then fails, and the fill does not create
a harmless $1 stray position — it moves the qty and the average entry price of a
position currently under observation. The freeze of issue #171 runs to
2026-09-28 precisely to keep the observed book comparable before and after, so a
fill here contaminates the measurement it is supposed to leave alone.

Submitted outside regular hours, the same `DAY` market order is accepted and
queued for the next open instead of filling, so the best-effort
`cancel_order_by_id` cleanup actually succeeds and the book is left untouched.
The property under test is broker-side — whether a second submit carrying the
same `client_order_id` is rejected with 409 — and it does not depend on the
first order having filled. Nothing about the verdict is weakened by running it
on a closed market.

Before recording a verdict, confirm the cleanup: the output must show
`cleanup=<id>:cancel_requested`, and no AAPL order may remain open.

```bash
.venv/bin/python -c "
from alpaca.trading.client import TradingClient; import os
c = TradingClient(os.environ['ALPACA_API_KEY'], os.environ['ALPACA_SECRET_KEY'], paper=True)
print([(o.symbol, o.status, o.client_order_id) for o in c.get_orders()])"
```

## Gate

Issue #203 must remain blocked until an operator runs the paper spike and this
document records the output. Attaching deterministic IDs in #201 does not itself
assume the broker deduplicates; only downstream automatic submit retries do.
