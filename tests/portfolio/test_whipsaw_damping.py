"""Tests for #61: anti-whipsaw damping for S4 weight-0 SELL exits.

Scope: only the "whipsaw" exit_mechanism (#60) — a fresh weak/neutral
re-signal zeroing an S4 position. Requires N (default 2) CONSECUTIVE
whipsaw-classified cycles before letting the SELL through; a single
occurrence holds one more cycle instead.
"""
from __future__ import annotations

import pytest

from src.portfolio.whipsaw_damping import evaluate_whipsaw_damping


class TestEvaluateWhipsawDamping:
    def test_first_whipsaw_suppresses_and_sets_streak_to_one(self):
        decision = evaluate_whipsaw_damping(is_whipsaw=True, prior_streak=0, confirm_cycles=2)

        assert decision.suppress is True
        assert decision.new_streak == 1

    def test_second_consecutive_whipsaw_confirms_and_resets(self):
        decision = evaluate_whipsaw_damping(is_whipsaw=True, prior_streak=1, confirm_cycles=2)

        assert decision.suppress is False
        assert decision.new_streak == 0

    def test_not_whipsaw_resets_streak_and_never_suppresses(self):
        decision = evaluate_whipsaw_damping(is_whipsaw=False, prior_streak=1, confirm_cycles=2)

        assert decision.suppress is False
        assert decision.new_streak == 0

    def test_confirm_cycles_of_one_never_suppresses(self):
        """confirm_cycles=1 means the first occurrence already confirms — no damping."""
        decision = evaluate_whipsaw_damping(is_whipsaw=True, prior_streak=0, confirm_cycles=1)

        assert decision.suppress is False
        assert decision.new_streak == 0

    def test_confirm_cycles_of_three_requires_two_suppressions(self):
        d1 = evaluate_whipsaw_damping(is_whipsaw=True, prior_streak=0, confirm_cycles=3)
        assert d1.suppress is True and d1.new_streak == 1

        d2 = evaluate_whipsaw_damping(is_whipsaw=True, prior_streak=d1.new_streak, confirm_cycles=3)
        assert d2.suppress is True and d2.new_streak == 2

        d3 = evaluate_whipsaw_damping(is_whipsaw=True, prior_streak=d2.new_streak, confirm_cycles=3)
        assert d3.suppress is False and d3.new_streak == 0
