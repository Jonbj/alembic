"""P0-13 — S4 promotion block + S7 R&D containment.

Problem:
- S4 has no gate report and no IC>placebo evaluation yet. Without a promotion block,
  it could be quietly promoted from paper to live by editing strategies.yaml.
- S7 (PEAD) is a new strategy in R&D that must not appear in the operational registry.
  If it gets accidentally enabled, it can run with real capital before any validation.

Fix:
- S4: add promotion_blocked=true in strategies.yaml; _validate_allocations rejects
  if S4 mode is 'live' (only paper until gate report exists).
- S7: must not be present in StrategyRegistry as an enabled entry.

Acceptance: test_s7_not_in_operational_registry passes.
"""

from __future__ import annotations

import pytest


class TestS4PromotionBlock:
    """S4 must have promotion_blocked=true and must not be in live mode."""

    def test_s4_promotion_blocked_in_yaml(self):
        """S4 must have promotion_blocked: true in strategies.yaml."""
        from src.strategies.registry import StrategyRegistry
        reg = StrategyRegistry()
        s4 = reg._entries.get("S4")
        assert s4 is not None, "S4 must exist in registry"
        assert getattr(s4, "promotion_blocked", False) is True, (
            "S4 must have promotion_blocked=true — no gate report exists yet. "
            "Alpha non valutabile until IC>placebo is confirmed (P1-03/04)."
        )

    def test_s4_not_in_live_mode(self):
        """S4 mode must not be 'live' — only paper until gate report passes."""
        from src.strategies.registry import StrategyRegistry
        reg = StrategyRegistry()
        s4 = reg._entries.get("S4")
        assert s4 is not None
        assert s4.mode != "live", (
            "S4 must not be in live mode — no gate report has passed. "
            "Current mode should be 'paper' or 'supervised_paper'."
        )

    def test_validate_allocations_rejects_s4_live_mode(self):
        """_validate_allocations must raise ValueError if S4 is in live mode."""
        from src.strategies.registry import StrategyEntry, _validate_allocations

        entries = {
            "S4": StrategyEntry(
                strategy_id="S4",
                strategy_class=object,
                allocation_pct=0.10,
                schedule="30 14 * * 1-5",
                enabled=True,
                mode="live",
            ),
        }
        with pytest.raises(ValueError, match="S4"):
            _validate_allocations(entries)


class TestS7NotInOperationalRegistry:
    """S7 must not appear as an active/enabled strategy in the operational registry."""

    def test_s7_not_in_operational_registry(self):
        """S7 must not be an enabled strategy in StrategyRegistry.

        S7/PEAD is a speculative R&D strategy. Until it has:
        - A runnable gate script
        - IC>placebo evaluation
        - OOS backtest on real (non-circular) data
        it must not be in the operational registry at all, or if present,
        must be disabled with mode='research'.
        """
        from src.strategies.registry import StrategyRegistry
        reg = StrategyRegistry()

        s7 = reg._entries.get("S7")
        if s7 is not None:
            # If S7 is present, it must be disabled and in research mode
            assert not s7.enabled, (
                "S7 is present in strategies.yaml but is enabled — "
                "S7/PEAD must not be operational until IC>placebo (P1-03). "
                "Set enabled: false and mode: research."
            )
            assert s7.mode == "research", (
                f"S7 mode is '{s7.mode}' but must be 'research' when present. "
                "S7 is R&D-only — remove it from the operational registry or set mode: research."
            )

    def test_s7_not_in_active_strategies(self):
        """S7 must not appear in get_active_strategies() — must never receive capital."""
        from src.strategies.registry import StrategyRegistry
        reg = StrategyRegistry()
        active_ids = [e.strategy_id for e in reg.get_active_strategies()]
        assert "S7" not in active_ids, (
            "S7 is in get_active_strategies() — it would receive capital allocation. "
            "S7/PEAD is R&D and must not be in the active strategy list. "
            "Fix: disable S7 in strategies.yaml or remove it."
        )

    def test_only_validated_strategies_are_live_or_paper(self):
        """No strategy with mode='live' may exist without prior validation."""
        from src.strategies.registry import StrategyRegistry
        reg = StrategyRegistry()
        live_strategies = [
            s for s in reg._entries.values()
            if s.mode == "live"
        ]
        assert len(live_strategies) == 0, (
            f"Strategies with mode='live': {[s.strategy_id for s in live_strategies]}. "
            "No strategy should be in live mode until all P0+P1 gates are cleared "
            "and ≥90 days of paper trading are completed."
        )
