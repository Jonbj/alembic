"""Admin control endpoints for mode management and killswitch."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.api.auth import require_api_key
from src.store.redis_store import RedisStore
from src.api.main import get_redis_store

router = APIRouter(prefix="/api/admin")

_VALID_MODES = frozenset({"backtest", "paper", "semi_auto", "full_auto", "halted", "dry_run"})
_VALID_LLM_MODELS = frozenset({"all", "kimi", "qwen", "deepseek", "glm"})


class ModeRequest(BaseModel):
    """Request body for setting operating mode."""
    mode: str



@router.get("/mode")
async def get_mode(
    store: Annotated[RedisStore, Depends(get_redis_store)],
) -> dict:
    """Get current operating mode."""
    return {"mode": store.get_mode() or "unknown"}

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


@router.get("/status")
async def get_status(
    store: Annotated[RedisStore, Depends(get_redis_store)],
) -> dict:
    """System status — killswitch state, operating mode, and LLM model selection. No auth."""
    return {
        "killswitch": store.is_killswitch_active(),
        "mode": store.get_mode() or "unknown",
        "llm_models": store.get_llm_models() or "all",
    }


class LLMModelsRequest(BaseModel):
    """Request body for setting LLM model selection."""
    models: str


@router.post("/llm-models")
async def set_llm_models(
    req: LLMModelsRequest,
    store: Annotated[RedisStore, Depends(get_redis_store)],
    _: Annotated[str, Depends(require_api_key)],
) -> dict:
    """Set LLM model selection for token-budget savings.

    Args:
        models: "all" (full ensemble) or comma-separated subset: kimi, qwen, deepseek, glm
    """
    selections = [m.strip() for m in req.models.lower().split(",")]
    invalid = [m for m in selections if m not in _VALID_LLM_MODELS]
    if invalid:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid model(s): {invalid}. Valid: {sorted(_VALID_LLM_MODELS)}",
        )
    store.set_llm_models(req.models.lower())
    return {"llm_models": req.models.lower(), "status": "ok"}


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
