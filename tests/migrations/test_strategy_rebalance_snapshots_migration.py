"""Contratto dello schema degli snapshot di ribilanciamento S1 (#489)."""

from pathlib import Path

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "migrations"
    / "064_strategy_rebalance_snapshots.sql"
)


def test_migration_persiste_tutto_il_contesto_della_decisione() -> None:
    sql = MIGRATION.read_text()

    assert "CREATE TABLE IF NOT EXISTS strategy_rebalance_snapshots" in sql
    for column in (
        "strategy_id",
        "rebalance_ts",
        "symbol",
        "signal_z",
        "weight",
        "in_target",
        "held",
        "position_market_value",
        "target_notional",
    ):
        assert column in sql
    assert "UNIQUE (strategy_id, rebalance_ts, symbol)" in sql
