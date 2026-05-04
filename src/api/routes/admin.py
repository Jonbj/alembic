"""Admin control endpoints for mode management and killswitch."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.api.auth import require_api_key
from src.store.redis_store import RedisStore
from src.api.main import get_redis_store

router = APIRouter(prefix="/api/admin")

_VALID_MODES = frozenset({"backtest", "paper", "semi_auto", "full_auto", "halted"})


class ModeRequest(BaseModel):
    """Request body for setting operating mode."""
    mode: str


@router.post("/mode")
async def set_mode(
    req: ModeRequest,
    store: Annotated[RedisStore, Depends(get_redis_store)],
    api_key: Annotated[str, Depends(require_api_key)]
) -> dict:
    """Set the system operating mode.

    Args:
        req: ModeRequest with new mode value
        store: RedisStore dependency
        api_key: Validated API key

    Returns:
        Confirmation with new mode

    Raises:
        HTTPException: 400 if mode is invalid
    """
    if req.mode not in _VALID_MODES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid mode. Must be one of: {_VALID_MODES}"
        )
    store.set_mode(req.mode)
    return {"mode": req.mode, "status": "ok"}


@router.post("/killswitch")
async def activate_killswitch(
    store: Annotated[RedisStore, Depends(get_redis_store)],
    api_key: Annotated[str, Depends(require_api_key)]
) -> dict:
    """Activate the emergency killswitch.

    Immediately halts all trading activity by:
    1. Setting killswitch_active flag in Redis
    2. Setting mode to 'halted'

    Args:
        store: RedisStore dependency
        api_key: Validated API key

    Returns:
        Confirmation of killswitch activation
    """
    store.activate_killswitch()
    store.set_mode("halted")
    return {"killswitch": "activated", "mode": "halted"}
