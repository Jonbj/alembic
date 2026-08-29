"""Schema and backfill contract for issue #325."""

from pathlib import Path


MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "migrations"
    / "056_stop_strategy_attribution.sql"
)


def test_migration_backfills_only_the_verified_legacy_cohort():
    sql = MIGRATION.read_text()

    for symbol in (
        "BAC",
        "GOOGL",
        "GS",
        "MS",
        "PBR",
        "RIO",
        "ROKU",
        "SPY",
        "UBS",
        "UNH",
        "XLE",
    ):
        assert f"'{symbol}'" in sql

    assert "SET stop_strategy = 'S1'" in sql
    assert "stop_strategy IS NULL" in sql
    assert "entry_time >= TIMESTAMPTZ '2026-07-10 00:00:00+00'" in sql
    assert "entry_time < TIMESTAMPTZ '2026-07-11 00:00:00+00'" in sql


def test_migration_rejects_future_null_attribution_without_rewriting_history():
    sql = MIGRATION.read_text()

    backfill = sql.index("SET stop_strategy = 'S1'")
    constraint = sql.index("CHECK (stop_strategy IS NOT NULL) NOT VALID")

    assert backfill < constraint
