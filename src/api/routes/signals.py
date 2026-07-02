"""Signal retrieval endpoints."""

import logging
from pathlib import Path
from typing import Annotated

import yaml
from fastapi import APIRouter, Depends, HTTPException

log = logging.getLogger(__name__)

from src.api.auth import require_api_key
from src.store.redis_store import RedisStore
from src.store.pg_store import PostgreSQLStore
from src.api.deps import get_redis_store, get_pg_store

_TRADING_YAML = Path(__file__).resolve().parents[3] / "config" / "trading.yaml"

router = APIRouter(prefix="/api/signals", dependencies=[Depends(require_api_key)])


def _watchlist() -> list[str]:
    try:
        with open(_TRADING_YAML) as f:
            return yaml.safe_load(f).get("symbols", {}).get("watchlist", [])
    except Exception:
        log.warning("Could not load watchlist from %s — returning empty list", _TRADING_YAML)
        return []


@router.get("")
async def get_all_signals(
    redis_store: Annotated[RedisStore, Depends(get_redis_store)],
    pg_store: Annotated[PostgreSQLStore, Depends(get_pg_store)],
    symbol: str | None = None,
    news_id: int | None = None,
) -> list[dict]:
    """Get latest signals for all watchlist symbols (or a single symbol if provided).
    
    Tries Redis cache first (fast, TTL 4h). Falls back to PostgreSQL
    for any symbols not found in cache.
    """
    if news_id is not None:
        results = pg_store.fetch_signals_for_news(news_id)
        signal_ids = [int(r["signal_id"]) for r in results if r.get("signal_id") is not None]
        if signal_ids:
            try:
                status_map = pg_store.fetch_signal_decision_status(signal_ids)
                for r in results:
                    sid = r.get("signal_id")
                    if sid is not None and int(sid) in status_map:
                        r.update(status_map[int(sid)])
                    else:
                        r["used_in_decision"] = False
                        r["decision_at"] = None
                        r["decision_type"] = None
            except Exception:
                pass
        return results

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

    # Enrich with decision status: did this signal produce an execution_decision?
    signal_ids = [int(r["signal_id"]) for r in results if r.get("signal_id") is not None]
    if signal_ids:
        try:
            status_map = pg_store.fetch_signal_decision_status(signal_ids)
            for r in results:
                sid = r.get("signal_id")
                if sid is not None and int(sid) in status_map:
                    r.update(status_map[int(sid)])
                else:
                    r["used_in_decision"] = False
                    r["decision_at"] = None
                    r["decision_type"] = None
        except Exception:
            pass

    return results


@router.get("/{symbol}")
async def get_signal(
    symbol: str,
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
