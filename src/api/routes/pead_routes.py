"""PEAD (Post-Earnings Announcement Drift) signal endpoints."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends

from src.api.auth import require_api_key
from src.api.deps import get_redis_store
from src.store.redis_store import RedisStore

router = APIRouter(prefix="/api/pead", dependencies=[Depends(require_api_key)])


@router.get("/signals")
def get_pead_signals(
    redis: Annotated[RedisStore, Depends(get_redis_store)],
) -> list[dict]:
    """Return all active PEAD surprise signals from Redis."""
    from src.config import config

    now = datetime.now(timezone.utc)
    results = []

    for symbol in config.WATCHLIST_SYMBOLS or []:
        try:
            signal = redis.read_pead_signal(symbol)
            if signal is None:
                continue
            days_remaining = max(0, (signal.hold_until - now).days)
            results.append({
                "symbol": signal.symbol,
                "direction": signal.direction,
                "surprise_pct": signal.surprise_pct,
                "confidence": signal.confidence,
                "filing_id": signal.filing_id,
                "detected_at": signal.detected_at.isoformat(),
                "hold_until": signal.hold_until.isoformat(),
                "days_remaining": days_remaining,
                "is_active": signal.is_active(now),
            })
        except Exception:
            continue

    results.sort(key=lambda x: x["detected_at"], reverse=True)
    return results
