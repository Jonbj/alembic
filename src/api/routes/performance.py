"""Performance and weights endpoints."""

import hashlib
import json
from datetime import datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.api.auth import require_api_key
from src.api.deps import get_pg_store, get_redis_store
from src.store.pg_store import PostgreSQLStore
from src.store.redis_store import RedisStore

router = APIRouter(prefix="/api")

_WEIGHT_MIN = 0.10
_WEIGHT_MAX = 0.70


class ApproveWeightsRequest(BaseModel):
    override_weights: dict[str, float] | None = None
    note: str | None = None


def _validate_override_weights(weights: dict[str, float]) -> dict[str, float]:
    from src.config import config
    known = set(config.MODEL_COSTS.keys())
    for model_id, w in weights.items():
        if model_id not in known:
            raise HTTPException(status_code=422, detail=f"Unknown model: {model_id}")
        if w < _WEIGHT_MIN:
            raise HTTPException(
                status_code=422,
                detail=f"Weight for {model_id}={w} below floor {_WEIGHT_MIN}",
            )
        if w > _WEIGHT_MAX:
            raise HTTPException(
                status_code=422,
                detail=f"Weight for {model_id}={w} exceeds cap {_WEIGHT_MAX}",
            )
    total = sum(weights.values())
    if abs(total - 1.0) > 0.001:
        raise HTTPException(
            status_code=422, detail=f"Weights must sum to 1.0 (got {total:.4f})"
        )
    return weights


@router.get("/performance/latest")
async def get_latest_performance(
    redis: Annotated[RedisStore, Depends(get_redis_store)],
) -> dict:
    raw = redis._r.get("performance:latest_report")
    if raw is None:
        raise HTTPException(status_code=404, detail="No performance report available yet")
    return json.loads(raw)


@router.get("/weights/current")
async def get_current_weights(
    redis: Annotated[RedisStore, Depends(get_redis_store)],
) -> dict:
    raw = redis._r.get("ensemble:weights:current")
    if raw is None:
        return {
            "weights": {
                "opus": 0.34,
                "qwen3.5:cloud": 0.33,
                "deepseek-v4-pro:cloud": 0.33,
            },
            "source": "default",
        }
    return json.loads(raw)


@router.get("/weights/suggestion")
async def get_weight_suggestion(
    redis: Annotated[RedisStore, Depends(get_redis_store)],
) -> dict:
    suggestion = redis.get_weight_suggestion()
    if suggestion is None:
        raise HTTPException(status_code=404, detail="No weight suggestion available")
    computed_at = datetime.fromisoformat(suggestion["computed_at"])
    suggestion["expires_at"] = (computed_at + timedelta(days=7)).isoformat()
    return suggestion


@router.post("/weights/approve")
async def approve_weights(
    body: ApproveWeightsRequest,
    api_key: Annotated[str, Depends(require_api_key)],
    redis: Annotated[RedisStore, Depends(get_redis_store)],
    pg: Annotated[PostgreSQLStore, Depends(get_pg_store)],
) -> dict:
    suggestion = redis.get_weight_suggestion()
    if suggestion is None:
        raise HTTPException(status_code=404, detail="No weight suggestion available")

    if suggestion.get("freeze_reason") and body.override_weights is None:
        raise HTTPException(
            status_code=403,
            detail=f"Weight update frozen: {suggestion['freeze_reason']}",
        )

    if body.override_weights is not None:
        weights = _validate_override_weights(body.override_weights)
        source = "override"
    else:
        weights = suggestion["suggested_weights"]
        source = "suggestion"

    redis.set_ensemble_weights(weights, source=source)
    redis._r.delete("ensemble:weights:suggestion:snapshot")

    approved_by = hashlib.sha256(api_key.encode()).hexdigest()[:8]
    log_id = pg.log_weight_update(
        source=source,
        applied_weights=weights,
        suggested_weights=suggestion.get("suggested_weights"),
        purified_icir=suggestion.get("purified_icir"),
        freeze_reason=suggestion.get("freeze_reason") or None,
        note=body.note,
        approved_by=approved_by,
    )

    return {"applied_weights": weights, "source": source, "log_id": log_id}
