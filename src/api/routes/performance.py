"""Performance and weights endpoints."""

import json
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from src.api.auth import require_api_key
from src.store.redis_store import RedisStore

router = APIRouter(prefix="/api")


def _get_redis_store() -> RedisStore:
    """Create RedisStore instance for route handlers."""
    from src.config import config
    from redis import Redis
    redis_client = Redis.from_url(config.REDIS_URL)
    return RedisStore(redis_client)


@router.get("/performance/latest")
async def get_latest_performance() -> dict:
    """Get the latest performance report.

    Reads from Redis key 'performance:latest_report' set by PerformanceWorker.

    Returns:
        PerformanceReport as JSON dict

    Raises:
        HTTPException: 404 if no report available yet
    """
    store = _get_redis_store()
    raw = store._r.get("performance:latest_report")
    if raw is None:
        raise HTTPException(
            status_code=404,
            detail="No performance report available yet"
        )
    return json.loads(raw)


@router.get("/weights/current")
async def get_current_weights() -> dict:
    """Get current ensemble model weights.

    Reads from Redis key 'ensemble:weights:current'.
    Falls back to default equal weights if not set.

    Returns:
        Dict with 'weights' and 'source' keys
    """
    store = _get_redis_store()
    raw = store._r.get("ensemble:weights:current")
    if raw is None:
        return {
            "weights": {
                "opus": 0.34,
                "qwen35": 0.33,
                "deepseek": 0.33
            },
            "source": "default"
        }
    return json.loads(raw)


@router.post("/weights/approve")
async def approve_weights(
    weights: dict[str, float],
    api_key: Annotated[str, Depends(require_api_key)]
) -> dict:
    """Manually approve and set ensemble weights.

    Args:
        weights: Dict mapping model_id to weight (0.0-1.0)
        api_key: Validated API key

    Returns:
        Confirmation with approved weights
    """
    store = _get_redis_store()
    payload = {"weights": weights, "source": "manual_approval"}
    store._r.set("ensemble:weights:current", json.dumps(payload))
    return {"approved": weights}
