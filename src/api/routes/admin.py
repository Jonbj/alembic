"""Admin control endpoints for mode management and killswitch."""

import json
import secrets
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from src.api.auth import require_api_key
from src.store.redis_store import RedisStore
from src.store.pg_store import PostgreSQLStore
from src.api.deps import get_redis_store, get_pg_store

router = APIRouter(prefix="/api/admin")

_VALID_MODES = frozenset({"backtest", "paper", "semi_auto", "full_auto", "halted", "dry_run"})
_VALID_LLM_MODELS = frozenset({"all", "kimi", "qwen", "deepseek", "glm"})

# Recovery token lives 5 minutes; operator must deactivate within that window.
_RECOVERY_TOKEN_TTL = 300
# Minimum seconds between activation and deactivation (prevents accidental immediate resume).
_DEACTIVATION_COOLDOWN_SECONDS = 120


class ModeRequest(BaseModel):
    """Request body for setting operating mode."""
    mode: str


@router.get("/mode")
async def get_mode(
    store: Annotated[RedisStore, Depends(get_redis_store)],
    _: Annotated[str, Depends(require_api_key)],
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


class KillswitchRequest(BaseModel):
    """Optional body for POST /killswitch."""
    reason: str = "manual operator halt via API"


@router.get("/killswitch")
async def get_killswitch(
    store: Annotated[RedisStore, Depends(get_redis_store)],
    _: Annotated[str, Depends(require_api_key)],
) -> dict:
    """Return current kill-switch state, activation time, and reason."""
    active = store.is_killswitch_active()
    detail = store.get_killswitch_reason()
    return {
        "active": active,
        "activated_at": detail.get("activated_at") if detail else None,
        "reason": detail.get("reason") if detail else None,
    }


@router.post("/killswitch/recovery-token")
async def request_recovery_token(
    store: Annotated[RedisStore, Depends(get_redis_store)],
    _: Annotated[str, Depends(require_api_key)],
) -> dict:
    """Generate a one-time recovery token required to deactivate the kill-switch.

    The token expires in _RECOVERY_TOKEN_TTL seconds. The operator must call
    DELETE /killswitch with this token within the window.
    """
    token = secrets.token_hex(16)
    store._r.setex("ks:recovery_token", _RECOVERY_TOKEN_TTL, token)
    return {"recovery_token": token, "expires_in_seconds": _RECOVERY_TOKEN_TTL}


@router.post("/killswitch")
async def activate_killswitch(
    store: Annotated[RedisStore, Depends(get_redis_store)],
    pg: Annotated[PostgreSQLStore, Depends(get_pg_store)],
    _: Annotated[str, Depends(require_api_key)],
    req: KillswitchRequest = KillswitchRequest(),
) -> dict:
    """Activate the emergency kill-switch with an optional operator-supplied reason."""
    store.activate_operator_halt(req.reason)
    store.set_mode("halted")
    try:
        pg.write_audit_log(action="KILLSWITCH_ACTIVATE", details={"reason": req.reason, "source": "api"})
    except Exception:
        pass  # audit failure must never block activation
    return {"killswitch": "activated", "mode": "halted", "reason": req.reason}


@router.delete("/killswitch")
async def deactivate_killswitch(
    store: Annotated[RedisStore, Depends(get_redis_store)],
    pg: Annotated[PostgreSQLStore, Depends(get_pg_store)],
    _: Annotated[str, Depends(require_api_key)],
    confirm_token: str = Query(..., description="One-time token from POST /killswitch/recovery-token"),
) -> dict:
    """Deactivate the kill-switch. Requires a recovery token and respects cooldown."""
    # Cooldown: block deactivation if activation happened less than _DEACTIVATION_COOLDOWN_SECONDS ago.
    for reason_key in ("system:halted_by_operator_reason", "killswitch_reason"):
        raw = store._r.get(reason_key)
        if raw is None:
            continue
        try:
            reason_data = json.loads(raw)
            activated_at = datetime.fromisoformat(reason_data.get("activated_at", ""))
            if activated_at.tzinfo is None:
                activated_at = activated_at.replace(tzinfo=timezone.utc)
            age = (datetime.now(timezone.utc) - activated_at).total_seconds()
            if age < _DEACTIVATION_COOLDOWN_SECONDS:
                wait = int(_DEACTIVATION_COOLDOWN_SECONDS - age)
                raise HTTPException(
                    status_code=422,
                    detail=f"Kill-switch cooldown active: wait {wait}s before deactivating",
                )
        except HTTPException:
            raise
        except Exception:
            pass  # malformed timestamp — allow deactivation
        break

    # Token validation (one-time use).
    stored_token = store._r.get("ks:recovery_token")
    stored_token_str = stored_token.decode() if isinstance(stored_token, bytes) else stored_token
    if not confirm_token or stored_token is None or stored_token_str != confirm_token:
        raise HTTPException(
            status_code=422,
            detail="Invalid or expired recovery token — request a new one via POST /killswitch/recovery-token",
        )
    store._r.delete("ks:recovery_token")

    store.deactivate_killswitch()
    store.deactivate_operator_halt()
    store.set_mode("paper")
    try:
        pg.write_audit_log(
            action="KILLSWITCH_DEACTIVATE",
            details={"source": "api", "token_prefix": confirm_token[:4] + "..."},
        )
    except Exception:
        pass  # audit failure must never block deactivation
    return {"killswitch": "deactivated", "mode": "paper"}
