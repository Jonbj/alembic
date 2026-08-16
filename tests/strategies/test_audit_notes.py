"""Regression guards for strategy audit notes used in operator decisions."""
from __future__ import annotations

from pathlib import Path

import yaml


_ROOT = Path(__file__).resolve().parents[2]


def test_s1_demotion_note_names_current_backtest_limitations() -> None:
    config = yaml.safe_load((_ROOT / "config/strategies.yaml").read_text())
    note = config["strategies"]["S1"]["note"]

    assert "same-bar fill" not in note
    assert "zero-cost assumption" not in note
    assert "look-ahead" in note
    assert "survivorship bias" in note
    assert "regime" in note
    assert "backtest/live" in note
    assert "docs/audits/strategies/S1/07_bugs.md" in note
