"""Contratto della migration 068 — tabella news_queue_census (censimento coda, opzione A)."""

from pathlib import Path

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "migrations"
    / "068_news_queue_census.sql"
)


def test_migration_crea_tabella_idempotente() -> None:
    sql = MIGRATION.read_text()

    assert "CREATE TABLE IF NOT EXISTS news_queue_census" in sql
    for column in (
        "sampled_at",
        "queue_depth",
        "processing_depth",
        "dead_letter_depth",
        "source",
        "n_fresh",
        "n_stale",
        "oldest_age_hours",
        "p50_age_hours",
    ):
        assert column in sql, f"manca colonna {column}"


def test_le_profondita_non_possono_essere_negative() -> None:
    """Vengono da LLEN: un valore negativo sarebbe un difetto dello strumento."""
    sql = MIGRATION.read_text()

    for column in ("queue_depth", "processing_depth", "dead_letter_depth"):
        assert f"CHECK ({column} >= 0)" in sql, f"manca il CHECK su {column}"


def test_source_resta_nullable() -> None:
    """`source IS NULL` e' la riga di sola profondita': senza di lei la serie
    avrebbe buchi proprio quando la coda vale zero, cioe' nel caso che conta."""
    sql = MIGRATION.read_text()

    assert "source              TEXT," in sql
    assert "source              TEXT NOT NULL" not in sql


def test_indici_per_il_taglio_temporale_e_per_sorgente() -> None:
    sql = MIGRATION.read_text()

    assert "idx_news_queue_census_sampled_at" in sql
    assert "idx_news_queue_census_source" in sql
    assert sql.count("CREATE INDEX IF NOT EXISTS") >= 2
