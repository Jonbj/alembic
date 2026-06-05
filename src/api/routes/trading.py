"""Alpaca positions and order history endpoints."""
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from src.api.auth import require_api_key
from src.api.deps import get_alpaca_trading_client, get_pg_store

router = APIRouter(prefix="/api", dependencies=[Depends(require_api_key)])


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
            "side": o.side.value if o.side else None,
            "qty": str(o.qty),
            "filled_avg_price": str(o.filled_avg_price) if o.filled_avg_price else None,
            "status": o.status.value if o.status else None,
            "filled_at": o.filled_at.isoformat() if o.filled_at else None,
            "submitted_at": o.submitted_at.isoformat() if o.submitted_at else None,
        }
        for o in orders
    ]


@router.get("/trades")
def get_trades(
    pg: Annotated[object, Depends(get_pg_store)],
    symbol: str | None = None,
    status: str = Query(default="all", pattern="^(open|closed|all)$"),
    limit: int = Query(default=50, ge=1, le=500),
) -> list[dict]:
    """List trades with optional symbol/status filter."""
    return pg.fetch_trades(symbol=symbol, status=status, limit=limit)


@router.get("/trades/summary")
def get_trades_summary(
    pg: Annotated[object, Depends(get_pg_store)],
    days: int = Query(default=7, ge=1, le=90),
) -> dict:
    """Aggregated P&L metrics for closed trades."""
    return pg.fetch_trade_summary(days=days)


@router.get("/decisions")
def get_decisions(
    pg: Annotated[object, Depends(get_pg_store)],
    symbol: str | None = None,
    limit: int = Query(default=20, ge=1, le=200),
) -> list[dict]:
    """Execution decision log (score > threshold candidates only)."""
    return pg.fetch_decisions(symbol=symbol, limit=limit)
