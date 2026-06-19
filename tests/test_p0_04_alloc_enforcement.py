"""P0-04 — Strategy Status SoT + allocation enforcement.

Problems:
1. _validate_allocations() only warns — over-allocation silently deploys >100% capital.
2. StrategyEntry has no `mode` field — supervised_paper vs live distinction is
   invisible to runtime code; relies purely on ALPACA_PAPER_MODE global.
3. strategies.yaml `promotion_blocked` field is ignored at load time.

Fixes:
1. _validate_allocations() raises ValueError on total > 1.0 or S4 > 10%.
2. StrategyEntry gains `mode: str` field (default "paper" — safe default).
3. _load_strategies_yaml reads mode + promotion_blocked into StrategyEntry.
4. S2 enabled → raises (not just warns).
"""

from __future__ import annotations

import pytest

from src.strategies.registry import StrategyEntry, StrategyRegistry, _validate_allocations


class _Mock:
    def __call__(self, *a, **kw):
        return []


def _entry(sid: str, alloc: float, enabled: bool = True, mode: str = "paper") -> StrategyEntry:
    return StrategyEntry(
        strategy_id=sid,
        strategy_class=_Mock,
        allocation_pct=alloc,
        schedule="30 14 * * 1-5",
        enabled=enabled,
        mode=mode,
    )


class TestValidateAllocationsRaises:
    """_validate_allocations must raise, not warn, on policy violations."""

    def test_raises_when_total_exceeds_one(self):
        """Total enabled allocation > 1.0 must raise ValueError."""
        entries = {
            "S1": _entry("S1", 0.60),
            "S4": _entry("S4", 0.50),
        }
        with pytest.raises(ValueError, match="over-allocated"):
            _validate_allocations(entries)

    def test_raises_when_s4_exceeds_cap(self):
        """S4 > 10% allocation must raise ValueError (no gate report)."""
        entries = {
            "S1": _entry("S1", 0.50),
            "S4": _entry("S4", 0.20),
        }
        with pytest.raises(ValueError, match="S4"):
            _validate_allocations(entries)

    def test_raises_when_s2_enabled(self):
        """S2 enabled must raise — OOS gates failed, backtest not valid."""
        entries = {
            "S1": _entry("S1", 0.50),
            "S2": _entry("S2", 0.20, enabled=True),
            "S4": _entry("S4", 0.10),
        }
        with pytest.raises(ValueError, match="S2"):
            _validate_allocations(entries)

    def test_passes_for_valid_allocation(self):
        """S1=50% + S4=10% = 60% must pass without error."""
        entries = {
            "S1": _entry("S1", 0.50),
            "S2": _entry("S2", 0.00, enabled=False),
            "S4": _entry("S4", 0.10),
        }
        _validate_allocations(entries)  # must not raise

    def test_disabled_strategies_excluded_from_total(self):
        """Disabled strategies must not count toward the total cap."""
        entries = {
            "S1": _entry("S1", 0.50),
            "S2": _entry("S2", 0.60, enabled=False),  # disabled — should not count
            "S4": _entry("S4", 0.10),
        }
        _validate_allocations(entries)  # must not raise


class TestStrategyEntryMode:
    """StrategyEntry must carry a mode field loaded from strategies.yaml."""

    def test_strategy_entry_has_mode_field(self):
        """StrategyEntry must have a `mode` attribute."""
        entry = _entry("S1", 0.50, mode="supervised_paper")
        assert hasattr(entry, "mode"), "StrategyEntry is missing `mode` field"

    def test_strategy_entry_mode_value(self):
        """mode field value is stored and retrievable."""
        entry = _entry("S1", 0.50, mode="supervised_paper")
        assert entry.mode == "supervised_paper"

    def test_strategy_entry_mode_default_is_paper(self):
        """Default mode must be 'paper' — safe default prevents accidental live."""
        entry = StrategyEntry(
            strategy_id="TEST",
            strategy_class=_Mock,
            allocation_pct=0.10,
            schedule="30 14 * * 1-5",
        )
        assert entry.mode == "paper"

    def test_s1_mode_is_supervised_paper(self):
        """StrategyRegistry must load S1 with mode=supervised_paper from strategies.yaml."""
        registry = StrategyRegistry()
        s1 = registry.get_strategy("S1")
        assert s1.mode == "supervised_paper", (
            f"S1.mode should be 'supervised_paper' (demoted P0-01), got {s1.mode!r}.\n"
            "Check config/strategies.yaml — S1.mode must be 'supervised_paper'."
        )

    def test_s4_mode_is_paper(self):
        """S4 must load with mode=paper (paper overlay, no gate report)."""
        registry = StrategyRegistry()
        s4 = registry.get_strategy("S4")
        assert s4.mode == "paper"

    def test_no_strategy_mode_is_live(self):
        """No strategy in the current registry may have mode='live' (freeze policy P0-01)."""
        registry = StrategyRegistry()
        live_strategies = [
            e.strategy_id
            for e in registry._entries.values()
            if getattr(e, "mode", "paper") == "live"
        ]
        assert not live_strategies, (
            f"Strategies with mode='live' found during operational freeze: {live_strategies}.\n"
            "Update config/strategies.yaml to set mode=supervised_paper or mode=paper."
        )
