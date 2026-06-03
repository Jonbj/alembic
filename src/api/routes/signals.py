"""Signal retrieval endpoints."""

import yaml
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from src.store.redis_store import RedisStore
from src.store.pg_store import PostgreSQLStore
from src.api.auth import require_api_key
from src.api.deps import get_redis_store, get_pg_store

router = APIRouter(prefix="/api/signals")


def _watchlist() -> list[str]:
    try:
        with open("config/trading.yaml") as f:
            return yaml.safe_load(f).get("symbols", {}).get("watchlist", [])
    except Exception:
        return []


@router.get("")
async def get_all_signals(
    redis_store: Annotated[RedisStore, Depends(get_redis_store)],
    pg_store: Annotated[PostgreSQLStore, Depends(get_pg_store)],
    _: Annotated[str, Depends(require_api_key)],
    symbol: str | None = None,
) -> list[dict]:
    """Get latest signals for all watchlist symbols (or a single symbol if provided).
    
    Tries Redis cache first (fast, TTL 4h). Falls back to PostgreSQL
    for any symbols not found in cache.
    """
    symbols = [symbol.upper()] if symbol else _watchlist()
    if not symbols:
        return []

    results = []
    missing_symbols = []

    # Phase 1: Try Redis cache for each symbol
    for sym in symbols:
        result = redis_store.read_sentiment(sym)
        if result is not None:
            results.append(result)
        else:
            missing_symbols.append(sym)

    # Phase 2: Fallback to PostgreSQL for missing symbols
    if missing_symbols:
        try:
            pg_results = pg_store.fetch_latest_signals(missing_symbols)
            # Build a lookup by symbol
            pg_by_symbol = {r["symbol"]: r for r in pg_results}
            for sym in missing_symbols:
                if sym in pg_by_symbol:
                    results.append(pg_by_symbol[sym])
        except Exception:
            # If PG fallback fails, just return what we have from Redis
            pass

    # Sort by generated_at descending (newest first)
    results.sort(key=lambda x: x.get("generated_at", ""), reverse=True)
    return results


@router.get("/{symbol}")
async def get_signal(
    symbol: str,
    api_key: Annotated[str, Depends(require_api_key)],
    redis_store: Annotated[RedisStore, Depends(get_redis_store)],
    pg_store: Annotated[PostgreSQLStore, Depends(get_pg_store)],
) -> dict:
    """Get latest sentiment signal for a symbol."""
    symbol = symbol.upper()
    
    # Try Redis first
    result = redis_store.read_sentiment(symbol)
    if result is not None:
        return result
    
    # Fallback to PostgreSQL
    try:
        pg_results = pg_store.fetch_latest_signals([symbol])
        if pg_results:
            return pg_results[0]
    except Exception:
        pass
    
    raise HTTPException(status_code=404, detail=f"No signal found for symbol: {symbol}")
