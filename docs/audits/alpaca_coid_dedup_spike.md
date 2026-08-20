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

**RUN 2026-08-20 08:38 UTC (04:38 ET, market closed, `clock.is_open=False`,
next open 09:30 ET). Verdict: `dedup_confirmed`.**

```json
{
  "behavior": "conflict_409",
  "client_order_id": "ambc-spike-KO-577eacec",
  "detail": "{\"code\":40010001,\"message\":\"client_order_id must be unique\"}",
  "first_order_id": "24b237ab-d0de-47d2-a948-507cdff0ae8b",
  "lookup_order_id": "24b237ab-d0de-47d2-a948-507cdff0ae8b",
  "second_order_id": null,
  "verdict": "dedup_confirmed"
}
cleanup=24b237ab-d0de-47d2-a948-507cdff0ae8b:cancel_requested
```

The second submit was rejected, no duplicate order was created, and the lookup by
`client_order_id` returned exactly the first order
(`lookup_order_id == first_order_id`). This is the safe branch the gate below
asked for.

### Correction: the status is 422, not 409

The `behavior` label reads `conflict_409` because that is what the script calls
this branch, but **the observed status is HTTP 422 with Alpaca code
`40010001 client_order_id must be unique`**. The 409 in this document came from
the Alpaca CLI skill guidance; it does not describe the paper Trading API.
Measured directly:

```
status_code HTTP = 422 | code = 40010001 | APIError: {"code":40010001,"message":"client_order_id must be unique"}
```

This matters for #203, and in the reassuring direction: `src/util/retry.py`
already classifies 422 as fail-fast, non-retryable, which is the correct
response to a duplicate. A submit-retry helper must key the "already submitted"
case on **422 / code 40010001**, not on 409, and resolve it with
`get_order_by_client_id` — the lookup verified above.

Uniqueness also **outlives the order**: a third submit carrying the same
`client_order_id`, issued after the first order had already been canceled, was
rejected identically. The dedup is not limited to the window in which the
original order is live.

### The probe symbol had to change: AAPL is unusable

The first run, on AAPL as this document specified, failed before reaching the
dedup question:

```
APIError: {"code":40310000,"existing_order_id":"d70e2048-...","message":"potential wash trade detected. use complex orders","reject_reason":"opposite side market/stop order exists"}
```

AAPL carries the protective SELL stop of its own position (qty 2 @ $277.38, open
since 2026-07-22), and Alpaca refuses an opposite-side BUY on a symbol with a
resting stop. **No order was created** — the failure is on the first submit — and
the book was verified unchanged (37 open orders and 49 positions before and
after, AAPL qty/avg entry identical).

The probe therefore ran on **KO**, chosen because the book neither holds it nor
has an open order on it. That is strictly safer than AAPL on every axis: a stray
$1 fill cannot move the average entry price of a position under the #171
observation freeze. `scripts/verify_alpaca_coid_dedup.py` now takes the symbol
from `ALPACA_SPIKE_SYMBOL` (default `KO`) and refuses upfront to probe a symbol
that is held or has an open order, so this failure mode reports itself in one
line instead of a traceback.

### Cleanup confirmed

The order was queued for the next open, not filled, and the cancellation
succeeded: final status `CANCELED`, `filled_qty=0`. After the run the book is
identical to before it — 37 open orders, 49 positions, no KO order and no KO
position. The one AAPL order that remains open is the pre-existing protective
stop `d70e2048-5254-4278-bd02-1f2d2535087d`, which the probe never touched;
this document's earlier "no AAPL order may remain open" check should be read as
"no order the probe created may remain open".

### Scope of the verdict

The probe tests an immediate retry after five seconds, plus one submit after
cancellation. It does not establish a deduplication window measured in hours or
across trading days.

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

## Gate — satisfied 2026-08-20

Issue #203 was blocked until an operator ran the paper spike and this document
recorded the output. Both are now done, with the verdict `dedup_confirmed`
above: **the gate is satisfied and #203 is unblocked.** Attaching deterministic
IDs in #201 never assumed the broker deduplicates; only downstream automatic
submit retries do, and those now rest on a measured broker behaviour rather than
on a documentation claim.

One constraint carries into #203: the duplicate signal is **422 / code
`40010001`**, not 409. A retry helper that fails fast on 422 (as
`src/util/retry.py` does) is correct, but a submit-retry path must recognise
that specific 422 as "already submitted" and resolve it with
`get_order_by_client_id` instead of treating it as an outright failure.
