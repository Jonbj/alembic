"""StrategyRegistry: central registry for active trading strategies.

Allocation configuration is read from config/strategies.yaml at startup.
Safe defaults apply when the file is absent:
    S1 (TimeSeriesMomentum)  — 50% allocation, enabled
    S2 (VRPStrategy)         — 0%  allocation, disabled (OOS gates not passed)
    S4 (NewsDrivenTactical)  — 10% allocation, enabled (paper overlay)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# Weekday market-open cron: 9:30 AM ET = 14:30 UTC
_DEFAULT_SCHEDULE = "30 14 * * 1-5"

_STRATEGIES_YAML = Path(__file__).resolve().parents[2] / "config" / "strategies.yaml"

# Safe fallback when config/strategies.yaml is not found.
_SAFE_DEFAULTS: dict[str, dict] = {
    "S1": {"enabled": True,  "allocation_pct": 0.50},
    "S2": {"enabled": False, "allocation_pct": 0.00},
    "S4": {"enabled": True,  "allocation_pct": 0.10},
}


@dataclass
class StrategyEntry:
    """Metadata for a registered strategy.

    Args:
        strategy_id:    Unique identifier (e.g. "S1").
        strategy_class: Strategy class or callable instance.
        allocation_pct: Target portfolio allocation (0–1). Sleeve-local weights
                        produced by compute_target_weights() are scaled by this
                        value to yield portfolio-level contributions.
        schedule:       5-field cron expression for Celery beat.
        enabled:        Whether this strategy participates in live cycles.
    """
    strategy_id: str
    strategy_class: Any
    allocation_pct: float
    schedule: str
    enabled: bool = True


class StrategyRegistry:
    """Central registry of active strategies with allocation weights.

    Reads allocation config from config/strategies.yaml; falls back to safe
    defaults (S2 disabled, S4 capped at 10%) when the file is absent.

    Args:
        load_defaults: When True (default), pre-populates S1/S2/S4 entries.
                       Pass False to get an empty registry (useful in tests).
    """

    def __init__(self, load_defaults: bool = True) -> None:
        self._entries: dict[str, StrategyEntry] = {}
        if load_defaults:
            self._load_defaults()

    # ── Public API ─────────────────────────────────────────────────────────────

    def register(self, entry: StrategyEntry) -> None:
        """Add a strategy entry. Raises ValueError if strategy_id already exists."""
        if entry.strategy_id in self._entries:
            raise ValueError(
                f"Strategy '{entry.strategy_id}' already registered. "
                "Use set_enabled() to toggle or reload() to reset."
            )
        self._entries[entry.strategy_id] = entry

    def get_strategy(self, strategy_id: str) -> StrategyEntry:
        """Return a single entry by ID. Raises KeyError if not found."""
        if strategy_id not in self._entries:
            raise KeyError(f"Strategy '{strategy_id}' not registered")
        return self._entries[strategy_id]

    def get_active_strategies(self) -> list[StrategyEntry]:
        """Return all enabled strategy entries."""
        return [e for e in self._entries.values() if e.enabled]

    def get_strategy_ids(self) -> list[str]:
        """Return all registered strategy IDs (enabled and disabled)."""
        return list(self._entries.keys())

    def set_enabled(self, strategy_id: str, enabled: bool) -> None:
        """Enable or disable a strategy without removing it."""
        entry = self.get_strategy(strategy_id)
        self._entries[strategy_id] = StrategyEntry(
            strategy_id=entry.strategy_id,
            strategy_class=entry.strategy_class,
            allocation_pct=entry.allocation_pct,
            schedule=entry.schedule,
            enabled=enabled,
        )

    def reload(self) -> None:
        """Reset registry to config/strategies.yaml (or safe defaults)."""
        self._entries.clear()
        self._load_defaults()

    # ── Private ────────────────────────────────────────────────────────────────

    def _load_defaults(self) -> None:
        from src.strategies.s1.strategy import TimeSeriesMomentum
        from src.strategies.s2.strategy import VRPStrategy
        from src.strategies.s4.strategy import NewsDrivenTactical

        yaml_cfg = _load_strategies_yaml()

        classes: dict[str, Any] = {
            "S1": TimeSeriesMomentum,
            "S2": VRPStrategy,
            "S4": NewsDrivenTactical,
        }

        for sid, cls in classes.items():
            cfg = yaml_cfg.get(sid, _SAFE_DEFAULTS[sid])
            self._entries[sid] = StrategyEntry(
                strategy_id=sid,
                strategy_class=cls,
                allocation_pct=cfg["allocation_pct"],
                schedule=_DEFAULT_SCHEDULE,
                enabled=cfg["enabled"],
            )

        _validate_allocations(self._entries)
        log.debug(
            "StrategyRegistry loaded: %s",
            {sid: (e.allocation_pct, "on" if e.enabled else "off")
             for sid, e in self._entries.items()},
        )


# ── Helpers ────────────────────────────────────────────────────────────────────

def _load_strategies_yaml() -> dict[str, dict]:
    """Load config/strategies.yaml; return safe defaults on any error."""
    try:
        import yaml
        with open(_STRATEGIES_YAML) as f:
            raw = yaml.safe_load(f) or {}
        result: dict[str, dict] = {}
        for sid, cfg in raw.get("strategies", {}).items():
            result[sid] = {
                "enabled": bool(cfg.get("enabled", False)),
                "allocation_pct": float(cfg.get("allocation_pct", 0.0)),
            }
        return result
    except FileNotFoundError:
        log.warning("config/strategies.yaml not found — using safe defaults")
        return dict(_SAFE_DEFAULTS)
    except Exception as exc:
        log.warning("Could not load config/strategies.yaml (%s) — using safe defaults", exc)
        return dict(_SAFE_DEFAULTS)


def _validate_allocations(entries: dict[str, StrategyEntry]) -> None:
    """Warn on allocation policy violations. Never raises."""
    enabled = [e for e in entries.values() if e.enabled]
    total = sum(e.allocation_pct for e in enabled)
    if total > 1.0:
        log.warning(
            "Enabled strategy allocations sum to %.2f > 1.0 — portfolio is over-allocated",
            total,
        )
    s4 = entries.get("S4")
    if s4 and s4.enabled and s4.allocation_pct > 0.10:
        log.warning(
            "S4 allocation %.0f%% exceeds 10%% cap — no dedicated gate report found",
            s4.allocation_pct * 100,
        )
    s2 = entries.get("S2")
    if s2 and s2.enabled:
        log.warning("S2 is enabled but OOS backtest gates have not passed — consider research mode")
