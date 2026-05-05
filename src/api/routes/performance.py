"""Performance and weights endpoints."""

import hashlib
from datetime import datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.api.auth import require_api_key
from src.api.deps import get_pg_store, get_redis_store
from src.config import config
from src.store.pg_store import PostgreSQLStore
from src.store.redis_store import RedisStore

router = APIRouter(prefix="/api")

_WEIGHT_MIN = 0.10
_WEIGHT_MAX = 0.70

_DEFAULT_WEIGHTS = {
    "weights": {
        "opus": 0.34,
        "qwen3.5:cloud": 0.33,
        "deepseek-v4-pro:cloud": 0.33,
    },
    "source": "default",
}


class ApproveWeightsRequest(BaseModel):
    override_weights: dict[str, float] | None = None
    note: str | None = None


def _validate_override_weights(weights: dict[str, float]) -> dict[str, float]:
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
    report = redis.get_performance_report()
    if report is None:
        raise HTTPException(status_code=404, detail="No performance report available yet")
    return report


@router.get("/weights/current")
async def get_current_weights(
    redis: Annotated[RedisStore, Depends(get_redis_store)],
) -> dict:
    stored = redis.get_current_weights_stored()
    return stored if stored is not None else _DEFAULT_WEIGHTS


@router.get("/weights/suggestion")
async def get_weight_suggestion(
    redis: Annotated[RedisStore, Depends(get_redis_store)],
) -> dict:
    suggestion = redis.get_weight_suggestion()
    if suggestion is None:
        raise HTTPException(status_code=404, detail="No weight suggestion available")
    try:
        computed_at = datetime.fromisoformat(suggestion["computed_at"])
    except (KeyError, ValueError):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid computed_at format: {suggestion.get('computed_at', 'missing')}",
        )
    return {**suggestion, "expires_at": (computed_at + timedelta(days=7)).isoformat()}


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

    # Redis write happens before PostgreSQL write. If pg.log_weight_update() fails,
    # the weights are applied but not in the audit log. Acceptable trade-off: a missing
    # log row is preferable to blocking or reverting a weight update that is already live.
    redis.set_ensemble_weights(weights, source=source)
    redis._r.delete("ensemble:weights:suggestion:snapshot")

    # approved_by stores SHA-256[:8] — 8 hex chars are sufficient to distinguish operators
    # in the audit log; the truncated hash is not reversible to the raw API key.
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
