"""Contract for #328 per-model relevance evidence persistence."""

from pathlib import Path


MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "migrations"
    / "052_llm_response_relevance.sql"
)


def test_migration_adds_nullable_relevance_evidence_columns():
    sql = MIGRATION.read_text()

    for column in (
        "event_type",
        "directness",
        "materiality",
        "novelty",
        "risk_flags",
        "evidence_sentences",
    ):
        assert f"ADD COLUMN IF NOT EXISTS {column}" in sql
