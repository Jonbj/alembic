# Alpaca `client_order_id` dedup spike

**Prepared:** 2026-08-18  
**Environment:** Alpaca paper trading  
**Script:** `scripts/verify_alpaca_coid_dedup.py`

## Documentation check

Alpaca's official order documentation defines `client_order_id` as unique,
queryable through `GET /orders:by_client_order_id`, and limited to 48 characters:

- <https://docs.alpaca.markets/docs/trading/orders/>
- <https://github.com/alpacahq/alpaca-docs/blob/master/content/api-references/broker-api/trading/orders.md>

The official Alpaca CLI guidance is more explicit: duplicate IDs are rejected
with HTTP 409, and an ambiguous failure must be resolved by looking up the order
by `client_order_id` before any retry:

- <https://github.com/alpacahq/cli/blob/main/.agents/skills/alpaca-cli/SKILL.md>

This corrects the implementation plan's stale 1024-character assumption. The
builder in `src/portfolio/order_id.py` enforces the documented 48-character
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
the probe, but cleanup is best-effort because a market order may already fill.

## Gate

Issue #203 must remain blocked until an operator runs the paper spike and this
document records the output. Attaching deterministic IDs in #201 does not itself
assume the broker deduplicates; only downstream automatic submit retries do.
