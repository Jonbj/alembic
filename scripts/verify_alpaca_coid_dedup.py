"""Probe Alpaca paper-trading duplicate ``client_order_id`` semantics.

This intentionally submits a $1 AAPL market order twice with the same client
order ID, looks up a 409 conflict by that ID, and cancels the original order on
a best-effort basis.
"""
from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from uuid import uuid4

from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.trading.requests import MarketOrderRequest

from src.portfolio.order_id import build_client_order_id


@dataclass(frozen=True)
class ProbeResult:
    verdict: str
    behavior: str
    client_order_id: str
    first_order_id: str
    second_order_id: str | None = None
    lookup_order_id: str | None = None
    detail: str | None = None


def _is_duplicate_conflict(exc: Exception) -> bool:
    status_code = getattr(exc, "status_code", None)
    message = str(exc).lower()
    return status_code == 409 or (
        "client_order_id" in message
        and ("409" in message or "unique" in message or "duplicate" in message)
    )


def probe_duplicate_submit(
    trading_client,
    request,
    *,
    pause_seconds: float = 5,
) -> ProbeResult:
    """Submit ``request`` twice and classify the broker response."""
    first = trading_client.submit_order(request)
    first_id = str(first.id)
    if pause_seconds:
        time.sleep(pause_seconds)

    try:
        second = trading_client.submit_order(request)
    except Exception as exc:
        if not _is_duplicate_conflict(exc):
            return ProbeResult(
                verdict="inconclusive",
                behavior="unexpected_error",
                client_order_id=request.client_order_id,
                first_order_id=first_id,
                detail=f"{type(exc).__name__}: {exc}",
            )
        try:
            existing = trading_client.get_order_by_client_id(request.client_order_id)
        except Exception as lookup_exc:
            return ProbeResult(
                verdict="inconclusive",
                behavior="conflict_lookup_failed",
                client_order_id=request.client_order_id,
                first_order_id=first_id,
                detail=f"{type(lookup_exc).__name__}: {lookup_exc}",
            )
        lookup_id = str(existing.id)
        return ProbeResult(
            verdict="dedup_confirmed" if lookup_id == first_id else "inconclusive",
            behavior="conflict_409",
            client_order_id=request.client_order_id,
            first_order_id=first_id,
            lookup_order_id=lookup_id,
            detail=str(exc),
        )

    second_id = str(second.id)
    return ProbeResult(
        verdict="dedup_confirmed" if second_id == first_id else "no_dedup",
        behavior="returned_original" if second_id == first_id else "created_duplicate",
        client_order_id=request.client_order_id,
        first_order_id=first_id,
        second_order_id=second_id,
    )


def main() -> int:
    api_key = os.environ.get("ALPACA_API_KEY")
    secret_key = os.environ.get("ALPACA_SECRET_KEY") or os.environ.get("ALPACA_API_SECRET")
    if not api_key or not secret_key:
        print(
            "ERROR: set ALPACA_API_KEY and ALPACA_SECRET_KEY with paper credentials.",
            file=sys.stderr,
        )
        return 1

    trading_client = TradingClient(api_key, secret_key, paper=True)
    client_order_id = build_client_order_id(
        "spike",
        "AAPL",
        datetime.now(timezone.utc),
        signal_id=uuid4().hex[:8],
    )
    request = MarketOrderRequest(
        symbol="AAPL",
        notional=1.0,
        side=OrderSide.BUY,
        time_in_force=TimeInForce.DAY,
        client_order_id=client_order_id,
    )

    result = probe_duplicate_submit(trading_client, request)
    print(json.dumps(asdict(result), indent=2, sort_keys=True))
    cleanup_ids = {result.first_order_id}
    if result.second_order_id is not None:
        cleanup_ids.add(result.second_order_id)
    for order_id in cleanup_ids:
        try:
            trading_client.cancel_order_by_id(order_id)
            print(f"cleanup={order_id}:cancel_requested")
        except Exception as exc:
            print(f"cleanup={order_id}:best_effort_failed ({type(exc).__name__}: {exc})")
    return 0 if result.verdict == "dedup_confirmed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
