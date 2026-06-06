"""T-601: StrategyRegistry tests."""
from __future__ import annotations

import pytest

from src.strategies.registry import StrategyEntry, StrategyRegistry


class _MockStrategy:
    """Minimal callable for test entries."""
    def __call__(self, ts, data_replay, portfolio, market):
        return []


# ── StrategyEntry ─────────────────────────────────────────────────────────────

def test_strategy_entry_has_required_fields():
    entry = StrategyEntry(
        strategy_id="TEST",
        strategy_class=_MockStrategy,
        allocation_pct=0.5,
        schedule="30 14 * * 1-5",
    )
    assert entry.strategy_id == "TEST"
    assert entry.strategy_class is _MockStrategy
    assert entry.allocation_pct == 0.5
    assert entry.schedule == "30 14 * * 1-5"


def test_strategy_entry_enabled_by_default():
    entry = StrategyEntry(
        strategy_id="TEST",
        strategy_class=_MockStrategy,
        allocation_pct=0.5,
        schedule="30 14 * * 1-5",
    )
    assert entry.enabled is True


def test_strategy_entry_can_be_disabled():
    entry = StrategyEntry(
        strategy_id="TEST",
        strategy_class=_MockStrategy,
        allocation_pct=0.5,
        schedule="30 14 * * 1-5",
        enabled=False,
    )
    assert entry.enabled is False


# ── Default config ────────────────────────────────────────────────────────────

def test_registry_registers_s1_by_default():
    registry = StrategyRegistry()
    entry = registry.get_strategy("S1")
    assert entry.strategy_id == "S1"


def test_registry_registers_s2_by_default():
    registry = StrategyRegistry()
    entry = registry.get_strategy("S2")
    assert entry.strategy_id == "S2"


def test_registry_registers_s4_by_default():
    registry = StrategyRegistry()
    entry = registry.get_strategy("S4")
    assert entry.strategy_id == "S4"


def test_s1_allocation_pct():
    registry = StrategyRegistry()
    assert registry.get_strategy("S1").allocation_pct == pytest.approx(0.50)


def test_s2_allocation_pct():
    registry = StrategyRegistry()
    assert registry.get_strategy("S2").allocation_pct == pytest.approx(0.00)


def test_s4_allocation_pct():
    registry = StrategyRegistry()
    assert registry.get_strategy("S4").allocation_pct == pytest.approx(0.10)


def test_default_allocations_do_not_exceed_one():
    registry = StrategyRegistry()
    total = sum(e.allocation_pct for e in registry.get_active_strategies())
    assert total <= 1.0


def test_default_active_allocation_sum():
    """S1=50% + S4=10% = 60% deployed; 40% cash residual."""
    registry = StrategyRegistry()
    total = sum(e.allocation_pct for e in registry.get_active_strategies())
    assert total == pytest.approx(0.60)


def test_get_active_strategies_returns_two_by_default():
    """S1 and S4 are enabled; S2 is disabled (gates not passed)."""
    registry = StrategyRegistry()
    active = registry.get_active_strategies()
    assert len(active) == 2


def test_s1_and_s4_enabled_by_default():
    registry = StrategyRegistry()
    assert registry.get_strategy("S1").enabled is True
    assert registry.get_strategy("S4").enabled is True


def test_s2_disabled_by_default():
    """S2 is disabled: OOS Sharpe -0.55, all backtest gates failed."""
    registry = StrategyRegistry()
    assert registry.get_strategy("S2").enabled is False


def test_all_entries_have_non_empty_schedule():
    registry = StrategyRegistry()
    for entry in registry.get_active_strategies():
        assert entry.schedule


def test_all_schedules_are_valid_cron():
    """Each schedule must be a 5-field cron expression."""
    registry = StrategyRegistry()
    for entry in registry.get_active_strategies():
        fields = entry.schedule.split()
        assert len(fields) == 5, (
            f"{entry.strategy_id} schedule '{entry.schedule}' is not 5-field cron"
        )


def test_all_entries_have_strategy_class():
    registry = StrategyRegistry()
    for entry in registry.get_active_strategies():
        assert entry.strategy_class is not None


# ── get_strategy / get_strategy_ids ──────────────────────────────────────────

def test_get_strategy_raises_key_error_for_unknown():
    registry = StrategyRegistry()
    with pytest.raises(KeyError):
        registry.get_strategy("UNKNOWN")


def test_get_strategy_ids_returns_all():
    registry = StrategyRegistry()
    ids = registry.get_strategy_ids()
    assert set(ids) == {"S1", "S2", "S4"}


# ── register ─────────────────────────────────────────────────────────────────

def test_register_custom_strategy():
    registry = StrategyRegistry()
    entry = StrategyEntry(
        strategy_id="CUSTOM",
        strategy_class=_MockStrategy,
        allocation_pct=0.10,
        schedule="0 9 * * 1-5",
    )
    registry.register(entry)
    assert registry.get_strategy("CUSTOM").strategy_id == "CUSTOM"


def test_register_duplicate_raises_value_error():
    registry = StrategyRegistry()
    entry = StrategyEntry(
        strategy_id="S1",
        strategy_class=_MockStrategy,
        allocation_pct=0.10,
        schedule="0 9 * * 1-5",
    )
    with pytest.raises(ValueError, match="already registered"):
        registry.register(entry)


# ── set_enabled / get_active_strategies ──────────────────────────────────────

def test_disabled_strategy_not_in_active():
    registry = StrategyRegistry()
    registry.set_enabled("S2", False)
    active_ids = [e.strategy_id for e in registry.get_active_strategies()]
    assert "S2" not in active_ids


def test_get_active_strategies_returns_only_enabled():
    """Disabling S4 leaves only S1 active (S2 is already disabled by default)."""
    registry = StrategyRegistry()
    registry.set_enabled("S4", False)
    active = registry.get_active_strategies()
    assert len(active) == 1
    assert active[0].strategy_id == "S1"


def test_re_enable_strategy():
    registry = StrategyRegistry()
    registry.set_enabled("S1", False)
    registry.set_enabled("S1", True)
    active_ids = [e.strategy_id for e in registry.get_active_strategies()]
    assert "S1" in active_ids


# ── reload ────────────────────────────────────────────────────────────────────

def test_reload_reverts_manual_override():
    """reload() reverts to YAML/safe defaults, undoing manual set_enabled calls."""
    registry = StrategyRegistry()
    registry.set_enabled("S4", False)
    assert registry.get_strategy("S4").enabled is False
    registry.reload()
    assert registry.get_strategy("S4").enabled is True


def test_reload_removes_custom_registrations():
    registry = StrategyRegistry()
    registry.register(StrategyEntry(
        strategy_id="CUSTOM",
        strategy_class=_MockStrategy,
        allocation_pct=0.10,
        schedule="0 9 * * 1-5",
    ))
    registry.reload()
    with pytest.raises(KeyError):
        registry.get_strategy("CUSTOM")
