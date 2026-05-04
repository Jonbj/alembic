"""Signal retrieval endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from src.store.redis_store import RedisStore
from src.api.main import get_redis_store

router = APIRouter(prefix="/api/signals")


@router.get("/{symbol}")
async def get_signal(
    symbol: str,
    store: Annotated[RedisStore, Depends(get_redis_store)]
) -> dict:
    """Get latest sentiment signal for a symbol.

    Args:
        symbol: Ticker symbol (e.g., AAPL, MSFT)
        store: RedisStore dependency

    Returns:
        SentimentResult as JSON dict

    Raises:
        HTTPException: 404 if no signal exists for symbol
    """
    result = store.read_sentiment(symbol.upper())
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"No signal found for symbol: {symbol}"
        )
    # result is already a dict from RedisStore.read_sentiment()
    return result
