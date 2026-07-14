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
from src.llm.model_registry import (
    default_weights,
    model_ids_for_keys,
    normalize_model_selection,
    sentiment_model_payload,
    valid_selection_tokens,
)

router = APIRouter(prefix="/api/admin")

_VALID_MODES = frozenset({"backtest", "paper", "semi_auto", "full_auto", "halted", "dry_run"})
_VALID_LLM_MODELS = frozenset(valid_selection_tokens())

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
    llm_selection, _, _ = normalize_model_selection(store.get_llm_models() or "all")
    return {
        "killswitch": store.is_killswitch_active(),
        "mode": store.get_mode() or "unknown",
        "llm_models": llm_selection,
        "llm_model_registry": sentiment_model_payload(llm_selection),
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
        models: canonical comma-separated model keys (e.g. "glm52,gptoss") or
            "all" to expand to every model with in_all=True in the registry.
            Valid keys are taken from src.llm.model_registry; do not hardcode
            model names here.
    """
    canonical, keys, invalid = normalize_model_selection(req.models)
    if invalid:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid model(s): {invalid}. Valid: {sorted(_VALID_LLM_MODELS)}",
        )
    store.set_llm_models(canonical)

    # WS-3 (2026-07-14): if the new pair does not include every model that the
    # stored ensemble weights reference, the stored weights are stale. Re-sync
    # to uniform weights over the new active model_ids so the dashboard never
    # displays weights for a dead pair.
    active_model_ids = model_ids_for_keys(keys)
    current_weights_data = store.get_current_weights_stored()
    if current_weights_data:
        current_weights = current_weights_data.get("weights", {})
        if current_weights and any(mid not in active_model_ids for mid in current_weights.keys()):
            store.set_ensemble_weights(
                default_weights(active_model_ids), source="pair_swap_resync"
            )

    return {
        "llm_models": canonical,
        "model_registry": sentiment_model_payload(canonical),
        "status": "ok",
    }


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
