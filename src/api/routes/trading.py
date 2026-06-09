"""Alpaca positions, order history, and trade analytics endpoints.

Route prefix: /api

Trade analytics (Phase A):
  GET /api/trades/analytics/by-symbol
  GET /api/trades/analytics/by-dimension?dim=regime|hour|score|holdtime

Feedback loop (Phase B):
  GET /api/feedback/status   — current Redis-adjusted threshold + regime scale

Counterfactual (Phase C):
  GET /api/trades/analytics/counterfactual   — aggregate opportunity cost stats
"""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from src.api.auth import require_api_key
from src.api.deps import get_alpaca_trading_client, get_pg_store, get_redis_store

router = APIRouter(prefix="/api", dependencies=[Depends(require_api_key)])

# NOTE: FastAPI matches routes in declaration order. The specific paths
# (/api/trades/summary, /api/trades/analytics/*, /api/trades/postmortem/*)
# must be declared before any parameterised path like /api/trades/{id}
# to prevent shadowing.


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


def _execution_engine() -> str:
    """Return execution.engine from trading.yaml (same logic as execution worker)."""
    try:
        import yaml
        with open("/app/config/trading.yaml") as f:
            return yaml.safe_load(f).get("execution", {}).get("engine", "legacy_sentiment")
    except Exception:
        return "legacy_sentiment"


def _alpaca_orders_as_trades(client, symbol: str | None, status: str, limit: int) -> list[dict]:
    """Fetch Alpaca filled orders and map them to a Trade-shaped dict for the UI."""
    from alpaca.trading.requests import GetOrdersRequest
    from alpaca.trading.enums import QueryOrderStatus

    req = GetOrdersRequest(status=QueryOrderStatus.CLOSED, limit=min(limit, 500))
    orders = client.get_orders(req)

    rows = []
    for o in orders:
        if o.filled_at is None:
            continue
        if symbol and o.symbol.upper() != symbol.upper():
            continue
        side = o.side.value if o.side else "buy"
        filled_price = float(o.filled_avg_price) if o.filled_avg_price else None
        qty = float(o.filled_qty) if o.filled_qty else None
        notional = round(filled_price * qty, 2) if filled_price and qty else None
        trade_status = "open" if side == "buy" else "closed"
        if status != "all" and trade_status != status:
            continue
        rows.append({
            "id": str(o.id),
            "symbol": o.symbol,
            "entry_time": o.filled_at.isoformat(),
            "entry_price": filled_price,
            "entry_notional": notional,
            "entry_order_id": str(o.id),
            "exit_time": None,
            "exit_price": None,
            "exit_reason": f"portfolio_{side}",
            "qty": qty,
            "score": 0.0,
            "regime_mult": 1.0,
            "gross_pnl": None,
            "slippage_est": None,
            "net_pnl": None,
            "signal_id": None,
            "decision_id": None,
            "postmortem_diagnosis": None,
            "status": trade_status,
        })
    return rows[:limit]


@router.get("/trades")
def get_trades(
    pg: Annotated[object, Depends(get_pg_store)],
    client: Annotated[object, Depends(get_alpaca_trading_client)],
    symbol: str | None = None,
    status: str = Query(default="all", pattern="^(open|closed|all)$"),
    limit: int = Query(default=50, ge=1, le=500),
) -> list[dict]:
    """List trades. In portfolio mode reads Alpaca filled orders; legacy mode reads DB."""
    if _execution_engine() == "portfolio":
        return _alpaca_orders_as_trades(client, symbol, status, limit)
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


@router.get("/trades/analytics/by-symbol")
def get_analytics_by_symbol(
    pg: Annotated[object, Depends(get_pg_store)],
    days: int = Query(default=90, ge=1, le=365),
) -> list[dict]:
    """P&L metrics grouped by symbol."""
    return pg.fetch_analytics_by_symbol(limit_days=days)


@router.get("/trades/analytics/by-dimension")
def get_analytics_by_dimension(
    pg: Annotated[object, Depends(get_pg_store)],
    dim: str = Query(pattern="^(regime|hour|score|holdtime)$"),
    days: int = Query(default=90, ge=1, le=365),
) -> list[dict]:
    """P&L metrics grouped by the requested dimension."""
    dispatch = {
        "regime":   pg.fetch_analytics_by_regime,
        "hour":     pg.fetch_analytics_by_hour,
        "score":    pg.fetch_analytics_by_score_bucket,
        "holdtime": pg.fetch_analytics_by_hold_time,
    }
    return dispatch[dim](limit_days=days)


@router.get("/trades/analytics/counterfactual")
def get_counterfactual_summary(
    pg: Annotated[object, Depends(get_pg_store)],
    days: int = Query(default=7, ge=1, le=90),
) -> list[dict]:
    """Aggregate counterfactual (opportunity cost) stats per decision type.

    Returns one row per decision type (SKIP_EMA, SKIP_CAP) with:
      - total_skips: how many decisions were skipped
      - computed: how many have a 1h forward return computed
      - avg_return: average 1h return if we had entered
      - pct_profitable: fraction of skips that would have been profitable
      - sum_positive_returns: total upside we missed
    """
    return pg.fetch_counterfactual_summary(days=days)


@router.get("/feedback/status")
def get_feedback_status(
    redis: Annotated[object, Depends(get_redis_store)],
) -> dict:
    """Current loss-feedback adjustments active in Redis (Phase B).

    Returns the live threshold override and regime scale factor.
    If no adjustment is active, returns baseline defaults.
    """
    from src.workers.execution import ENTRY_THRESHOLD
    threshold = redis.get_feedback_entry_threshold()
    scale = redis.get_feedback_regime_scale()
    state = redis.get_feedback_state() or {}
    return {
        "entry_threshold": threshold if threshold is not None else ENTRY_THRESHOLD,
        "entry_threshold_baseline": ENTRY_THRESHOLD,
        "regime_scale": scale if scale is not None else 1.0,
        "adjustment_active": threshold is not None or scale is not None,
        "last_adjustment_ts": state.get("last_adjustment_ts"),
        "last_reason": state.get("reason"),
        "consecutive_losses": state.get("consecutive_losses"),
        "rolling_net_pnl": state.get("rolling_net_pnl"),
    }


@router.get("/trades/postmortem/{trade_id}")
def get_postmortem(
    trade_id: int,
    pg: Annotated[object, Depends(get_pg_store)],
) -> dict:
    """Return trade detail with postmortem_diagnosis (or null if not computed)."""
    row = pg.fetch_trade_with_signal(trade_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Trade not found")
    for key in ("entry_time", "exit_time", "signal_generated_at"):
        if row.get(key) is not None and hasattr(row[key], "isoformat"):
            row[key] = row[key].isoformat()
    return row
