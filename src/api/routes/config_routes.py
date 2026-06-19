"""Runtime config read/write via config/trading.yaml."""
from pathlib import Path
from typing import Annotated

import yaml
from fastapi import APIRouter, Depends, HTTPException

from src.api.auth import require_api_key

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
) -> dict:
    """Merge updates into trading.yaml and persist. Requires API key.

    Only top-level keys present in updates are changed; other keys are preserved.
    The running Celery workers read config at task start, so changes take effect
    on the next task invocation without a restart.
    """
    _validate_risk_params(updates)
    current = _read_config()
    _deep_merge(current, updates)
    with open(_CONFIG_PATH, "w") as f:
        yaml.dump(current, f, default_flow_style=False, allow_unicode=True)
    return current


def _deep_merge(base: dict, updates: dict) -> None:
    """Recursively merge updates into base in place."""
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
