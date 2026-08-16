"""Schema contract for the FIX-06 discard ledger migration."""

from pathlib import Path


MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "migrations"
    / "047_news_discard_reasons.sql"
)


def test_migration_backfills_stale_rows_before_reason_becomes_required():
    sql = MIGRATION.read_text()

    backfill = sql.index("SET discarded_reason = 'stale'")
    not_null = sql.index("ALTER COLUMN discarded_reason SET NOT NULL")

    assert backfill < not_null


def test_migration_constrains_every_reason_emitted_by_workers():
    sql = MIGRATION.read_text()
    expected = {
        "no_ticker",
        "stale",
        "duplicate_id",
        "duplicate_content",
        "not_tradable",
        "parse_fail",
        "near_neutral",
    }

    assert all(f"'{reason}'" in sql for reason in expected)
    assert "discard_stage IN ('ingestion', 'sentiment')" in sql
