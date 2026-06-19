"""P1-STRATEGY-SOT-DB — Single source of truth for strategy mode/state.

Problems identified in ALEMBIC_REMEDIATION_MASTER_PLAN_2026-06-18 (WS-02):

1. Fragmented SoT: strategy mode (paper/live/supervised_paper/research/disabled)
   is declared in YAML, docstrings, UI, and roadmap — which contradict each other.
   Fix: `strategy_lifecycle` DB table is the canonical SoT; YAML is the bootstrap
   seed; registry reads from DB when available and falls back to YAML.

2. _validate_allocations was only a warning (fixed pre-this session — already raises).
   Tests here confirm the raise behavior is present and correct.

3. Registry mode enforcement: when YAML says mode='live', the registry must enforce
   it (not silently accept anything the caller says). This is already partially
   implemented; these tests pin the behavior.

Tests:
- strategy_lifecycle table must exist (migration) with correct schema
- StrategyRegistry.load_mode_from_db overrides YAML mode when DB has a row
- Falls back to YAML mode when DB is unavailable or has no row
- validate_allocations raises on over-allocation (pins existing behavior)
- Single source: mode is read from ONE place per call, not multiple
"""
from __future__ import annotations

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# 1. strategy_lifecycle table schema (via pg_store migration)
# ─────────────────────────────────────────────────────────────────────────────

class TestStrategyLifecycleMigration:

    def test_migration_file_exists(self):
        """A migration file for strategy_lifecycle must exist."""
        from pathlib import Path
        migrations_dir = Path(__file__).resolve().parents[1] / "migrations"
        lifecycle_migrations = [
            f for f in migrations_dir.glob("*.sql")
            if "strategy_lifecycle" in f.read_text()
        ]
        assert len(lifecycle_migrations) >= 1, (
            "A migration file defining the strategy_lifecycle table must exist in migrations/. "
            "This table is the single source of truth for strategy mode and state."
        )

    def test_migration_creates_required_columns(self):
        """strategy_lifecycle migration must define strategy_id, mode, promoted_by columns."""
        from pathlib import Path
        migrations_dir = Path(__file__).resolve().parents[1] / "migrations"
        lifecycle_sql = ""
        for f in sorted(migrations_dir.glob("*.sql")):
            text = f.read_text()
            if "strategy_lifecycle" in text and "CREATE TABLE" in text:
                lifecycle_sql = text
                break

        assert lifecycle_sql, "Migration with CREATE TABLE strategy_lifecycle not found"

        required_columns = ["strategy_id", "mode", "promoted_by"]
        for col in required_columns:
            assert col in lifecycle_sql, (
                f"strategy_lifecycle table must have column '{col}': "
                f"it tracks which strategy is in which mode and who approved it."
            )


# ─────────────────────────────────────────────────────────────────────────────
# 2. StrategyRegistry DB mode loading
# ─────────────────────────────────────────────────────────────────────────────

class TestRegistryDBModeLoading:

    def test_registry_has_load_mode_from_db_method(self):
        """StrategyRegistry must expose load_mode_from_db(db_conn) method."""
        import inspect
        from src.strategies.registry import StrategyRegistry
        assert hasattr(StrategyRegistry, "load_mode_from_db"), (
            "StrategyRegistry must have load_mode_from_db(db_conn) method. "
            "This method reads mode from strategy_lifecycle table and overrides YAML mode."
        )

    def test_db_mode_overrides_yaml_mode(self):
        """When DB has a mode row for a strategy, it overrides the YAML-loaded mode."""
        from unittest.mock import MagicMock
        from src.strategies.registry import StrategyRegistry

        reg = StrategyRegistry(load_defaults=False)
        from src.strategies.registry import StrategyEntry
        # Register S1 with mode from YAML = 'paper'
        entry = StrategyEntry(
            strategy_id="S1",
            strategy_class=object,
            allocation_pct=0.5,
            schedule="30 14 * * 1-5",
            enabled=True,
            mode="paper",
        )
        reg._entries["S1"] = entry

        # DB says S1 is in 'supervised_paper' mode
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_cursor.fetchall.return_value = [
            {"strategy_id": "S1", "mode": "supervised_paper"}
        ]

        reg.load_mode_from_db(mock_conn)

        assert reg.get_strategy("S1").mode == "supervised_paper", (
            "DB mode must override YAML mode when strategy_lifecycle has a row for this strategy."
        )

    def test_db_unavailable_keeps_yaml_mode(self):
        """When DB raises on load_mode_from_db, YAML-loaded mode is preserved (fail-open)."""
        from unittest.mock import MagicMock
        from src.strategies.registry import StrategyRegistry

        reg = StrategyRegistry(load_defaults=False)
        from src.strategies.registry import StrategyEntry
        entry = StrategyEntry(
            strategy_id="S1",
            strategy_class=object,
            allocation_pct=0.5,
            schedule="30 14 * * 1-5",
            enabled=True,
            mode="paper",
        )
        reg._entries["S1"] = entry

        # DB connection raises
        mock_conn = MagicMock()
        mock_conn.cursor.side_effect = Exception("Connection refused")

        # Must not raise — fall back to YAML mode
        reg.load_mode_from_db(mock_conn)

        assert reg.get_strategy("S1").mode == "paper", (
            "When DB is unavailable, load_mode_from_db must fail-open and keep YAML mode."
        )

    def test_db_missing_row_keeps_yaml_mode(self):
        """When DB has no row for a strategy, YAML-loaded mode is preserved."""
        from unittest.mock import MagicMock
        from src.strategies.registry import StrategyRegistry

        reg = StrategyRegistry(load_defaults=False)
        from src.strategies.registry import StrategyEntry
        entry = StrategyEntry(
            strategy_id="S4",
            strategy_class=object,
            allocation_pct=0.1,
            schedule="30 14 * * 1-5",
            enabled=True,
            mode="paper",
        )
        reg._entries["S4"] = entry

        # DB returns no rows (strategy not yet in lifecycle table)
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_cursor.fetchall.return_value = []  # no rows

        reg.load_mode_from_db(mock_conn)

        assert reg.get_strategy("S4").mode == "paper", (
            "When strategy_lifecycle has no row for a strategy, YAML mode is kept as fallback."
        )


# ─────────────────────────────────────────────────────────────────────────────
# 3. validate_allocations raises (pins existing behavior from P0-04)
# ─────────────────────────────────────────────────────────────────────────────

class TestValidateAllocationsRaises:
    """Pin the raise behavior from _validate_allocations (not just a warning)."""

    def test_raises_on_over_allocation(self):
        """_validate_allocations must raise ValueError when total > 1.0."""
        from src.strategies.registry import StrategyEntry, _validate_allocations

        entries = {
            "S1": StrategyEntry("S1", object, 0.70, "* * * * *", enabled=True),
            "S4": StrategyEntry("S4", object, 0.40, "* * * * *", enabled=True),
        }
        with pytest.raises(ValueError, match="over-allocated"):
            _validate_allocations(entries)

    def test_passes_for_valid_allocation(self):
        """_validate_allocations must not raise for valid total ≤ 1.0."""
        from src.strategies.registry import StrategyEntry, _validate_allocations

        entries = {
            "S1": StrategyEntry("S1", object, 0.50, "* * * * *", enabled=True),
            "S4": StrategyEntry("S4", object, 0.10, "* * * * *", enabled=True),
        }
        _validate_allocations(entries)  # must not raise


# ─────────────────────────────────────────────────────────────────────────────
# 4. Registry mode enforced from YAML (single source, no silent override)
# ─────────────────────────────────────────────────────────────────────────────

class TestRegistryModeFromYAML:

    def test_registry_reads_mode_from_yaml_config(self):
        """When YAML has mode set, registry must load it into StrategyEntry.mode."""
        import tempfile
        import os
        from pathlib import Path
        from unittest.mock import patch

        yaml_content = """
strategies:
  S1:
    enabled: true
    allocation_pct: 0.50
    mode: supervised_paper
  S4:
    enabled: true
    allocation_pct: 0.10
    mode: paper
  S2:
    enabled: false
    allocation_pct: 0.00
    mode: disabled
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            tmp_path = Path(f.name)

        try:
            with patch("src.strategies.registry._STRATEGIES_YAML", tmp_path):
                from src.strategies.registry import StrategyRegistry
                reg = StrategyRegistry(load_defaults=True)
                s1 = reg.get_strategy("S1")
                assert s1.mode == "supervised_paper", (
                    f"Registry must load mode='supervised_paper' from YAML for S1, got '{s1.mode}'"
                )
        finally:
            os.unlink(tmp_path)

    def test_mode_default_is_paper_when_yaml_omits_mode(self):
        """When YAML omits the 'mode' key, StrategyEntry.mode defaults to 'paper'."""
        import tempfile
        import os
        from pathlib import Path
        from unittest.mock import patch

        yaml_content = """
strategies:
  S1:
    enabled: true
    allocation_pct: 0.50
  S4:
    enabled: true
    allocation_pct: 0.10
  S2:
    enabled: false
    allocation_pct: 0.00
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            tmp_path = Path(f.name)

        try:
            with patch("src.strategies.registry._STRATEGIES_YAML", tmp_path):
                from src.strategies.registry import StrategyRegistry
                reg = StrategyRegistry(load_defaults=True)
                s1 = reg.get_strategy("S1")
                assert s1.mode == "paper", (
                    f"When YAML omits 'mode', StrategyEntry.mode must default to 'paper', got '{s1.mode}'"
                )
        finally:
            os.unlink(tmp_path)
