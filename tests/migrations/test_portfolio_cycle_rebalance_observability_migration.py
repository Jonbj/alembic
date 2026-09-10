"""Contratto della telemetria di ribilanciamento su portfolio_cycles (#468)."""

from pathlib import Path


MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "migrations"
    / "067_portfolio_cycle_rebalance_observability.sql"
)


def test_migration_aggiunge_decisione_e_transizioni_a_peso_zero() -> None:
    sql = MIGRATION.read_text()

    assert "ALTER TABLE portfolio_cycles" in sql
    assert "rebalanced_strategies" in sql
    assert "zero_weight_symbols" in sql
    assert "DEFAULT '[]'::jsonb" in sql
    assert "DEFAULT '{}'::jsonb" in sql

