"""Alpaca positions and order history endpoints."""
from typing import Annotated

from fastapi import APIRouter, Depends

from src.api.deps import get_alpaca_trading_client

router = APIRouter(prefix="/api")


@router.get("/positions")
def get_positions(
    client: Annotated[object, Depends(get_alpaca_trading_client)],
) -> list[dict]:
    """Return all open positions from Alpaca."""
    positions = client.get_all_positions()
    return [
        {
            "symbol": p.symbol,
            "qty": str(p.qty),
            "market_value": str(p.market_value),
            "unrealized_pl": str(p.unrealized_pl),
            "unrealized_plpc": str(p.unrealized_plpc),
            "avg_entry_price": str(p.avg_entry_price),
            "current_price": str(p.current_price),
        }
        for p in positions
    ]


@router.get("/orders")
def get_orders(
    client: Annotated[object, Depends(get_alpaca_trading_client)],
    limit: int = 50,
) -> list[dict]:
    """Return order history from Alpaca (filled + cancelled)."""
    from alpaca.trading.requests import GetOrdersRequest
    from alpaca.trading.enums import QueryOrderStatus
    orders = client.get_orders(GetOrdersRequest(
        status=QueryOrderStatus.ALL,
        limit=min(limit, 500),
    ))
    return [
        {
            "id": str(o.id),
            "symbol": o.symbol,
            "side": o.side.value,
            "qty": str(o.qty),
            "filled_avg_price": str(o.filled_avg_price) if o.filled_avg_price else None,
            "status": o.status.value,
            "filled_at": o.filled_at.isoformat() if o.filled_at else None,
            "submitted_at": o.submitted_at.isoformat() if o.submitted_at else None,
        }
        for o in orders
    ]
