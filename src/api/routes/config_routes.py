"""Runtime config read/write via config/trading.yaml."""
from pathlib import Path
from typing import Annotated

import yaml
from fastapi import APIRouter, Depends, HTTPException, Query

from src.api.auth import require_api_key
from src.store.pg_store import PostgreSQLStore
from src.api.deps import get_pg_store

router = APIRouter(prefix="/api")

_CONFIG_PATH = Path(__file__).resolve().parents[3] / "config" / "trading.yaml"

# P0-08: conservative hard bounds for risk parameters.
# Violating these disables safety controls — reject immediately, do not persist.
_RISK_BOUNDS: dict[str, tuple[float, float]] = {
    "stop_loss":             (0.001, 0.10),   # 0.1% – 10%
    "max_position_pct":      (0.01,  0.20),   # 1% – 20%
    "max_portfolio_exposure":(0.10,  1.0),    # 10% – 100%
    "vix_spike":             (10.0,  100.0),  # 10–100 VIX points
    "portfolio_drawdown":    (0.01,  0.20),   # 1% – 20%
}

# Fields where increasing the value weakens the control.
_WEAKENING_FIELDS = (
    "stop_loss", "max_position_pct", "max_portfolio_exposure",
    "vix_spike", "portfolio_drawdown",
)


def _validate_risk_params(updates: dict) -> None:
    """Raise HTTPException 422 if any risk parameter is outside its safe bound."""
    risk = updates.get("risk")
    if not isinstance(risk, dict):
        return
    violations: list[str] = []
    for field, (lo, hi) in _RISK_BOUNDS.items():
        if field not in risk:
            continue
        val = risk[field]
        if not isinstance(val, (int, float)) or not (lo <= float(val) <= hi):
            violations.append(
                f"{field}={val!r} is outside [{lo}, {hi}]"
            )
    if violations:
        raise HTTPException(
            status_code=422,
            detail=f"Risk parameter bounds violation: {'; '.join(violations)}",
        )


def _detect_risk_weakening(current_risk: dict, new_risk: dict) -> list[str]:
    """Return field names that are being moved toward the less-safe direction."""
    weakened: list[str] = []
    for field in _WEAKENING_FIELDS:
        if field not in new_risk:
            continue
        old = current_risk.get(field)
        if old is None:
            continue
        try:
            if float(new_risk[field]) > float(old):
                weakened.append(field)
        except (TypeError, ValueError):
            pass
    return weakened


def _require_reason_for_weakening(current: dict, updates: dict, reason: str | None) -> None:
    """Raise HTTPException 422 if risk controls are being weakened without a reason."""
    current_risk = current.get("risk", {})
    new_risk = updates.get("risk", {})
    weakened = _detect_risk_weakening(current_risk, new_risk)
    # Re-enabling auto-recovery is also a weakening change (P0-06 disabled it by default).
    new_ks = new_risk.get("killswitch_recovery", {})
    if isinstance(new_ks, dict) and new_ks.get("enabled") is True:
        weakened.append("killswitch_recovery.enabled")
    if weakened and not reason:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Weakening risk controls requires a justification reason "
                f"(pass ?reason=... query param): {weakened}"
            ),
        )


def _read_config() -> dict:
    try:
        with open(_CONFIG_PATH) as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail=f"{_CONFIG_PATH} not found")


@router.get("/config")
def get_config(api_key: Annotated[str, Depends(require_api_key)]) -> dict:
    """Return the current trading.yaml as a JSON object."""
    return _read_config()


@router.post("/config")
def update_config(
    updates: dict,
    api_key: Annotated[str, Depends(require_api_key)],
    pg: Annotated[PostgreSQLStore, Depends(get_pg_store)],
    reason: Annotated[str | None, Query(description="Required when weakening risk controls")] = None,
) -> dict:
    """Merge updates into trading.yaml and persist. Requires API key.

    Only top-level keys present in updates are changed; other keys are preserved.
    The running Celery workers read config at task start, so changes take effect
    on the next task invocation without a restart.

    Weakening risk controls (raising stop_loss, drawdown cap, etc.) requires a
    ?reason=... query parameter that is captured in the audit log.
    """
    _validate_risk_params(updates)
    current = _read_config()
    _require_reason_for_weakening(current, updates, reason)
    old_risk = dict(current.get("risk", {}))
    _deep_merge(current, updates)
    with open(_CONFIG_PATH, "w") as f:
        yaml.dump(current, f, default_flow_style=False, allow_unicode=True)
    try:
        pg.write_audit_log(
            action="UPDATE",
            table_name="config",
            details={
                "changed_keys": list(updates.keys()),
                "old_risk": old_risk,
                "new_risk": dict(current.get("risk", {})),
                "reason": reason,
            },
        )
    except Exception:
        pass  # audit failure must not block config update
    return current


def _deep_merge(base: dict, updates: dict) -> None:
    """Recursively merge updates into base in place."""
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
