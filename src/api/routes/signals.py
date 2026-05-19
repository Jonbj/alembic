"""Signal retrieval endpoints."""

import yaml
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from src.store.redis_store import RedisStore
from src.api.main import get_redis_store

router = APIRouter(prefix="/api/signals")


def _watchlist() -> list[str]:
    try:
        with open("config/trading.yaml") as f:
            return yaml.safe_load(f).get("symbols", {}).get("watchlist", [])
    except Exception:
        return []


@router.get("")
async def get_all_signals(
    store: Annotated[RedisStore, Depends(get_redis_store)],
    symbol: str | None = None,
) -> list[dict]:
    """Get latest signals for all watchlist symbols (or a single symbol if provided)."""
    symbols = [symbol.upper()] if symbol else _watchlist()
    results = []
    for sym in symbols:
        result = store.read_sentiment(sym)
        if result is not None:
            results.append(result)
    return results


@router.get("/{symbol}")
async def get_signal(
    symbol: str,
    store: Annotated[RedisStore, Depends(get_redis_store)]
) -> dict:
    """Get latest sentiment signal for a symbol."""
    result = store.read_sentiment(symbol.upper())
    if result is None:
        raise HTTPException(status_code=404, detail=f"No signal found for symbol: {symbol}")
    return result
