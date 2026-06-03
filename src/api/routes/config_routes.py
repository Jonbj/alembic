"""Runtime config read/write via config/trading.yaml."""
from typing import Annotated

import yaml
from fastapi import APIRouter, Depends, HTTPException

from src.api.auth import require_api_key

router = APIRouter(prefix="/api")

_CONFIG_PATH = "config/trading.yaml"


def _read_config() -> dict:
    try:
        with open(_CONFIG_PATH) as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="config/trading.yaml not found")


@router.get("/config")
def get_config() -> dict:
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
