"""Contratto della migration 065 — tabella PoC shadow news_poc_samples (#458)."""

from pathlib import Path

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "migrations"
    / "065_news_poc_samples.sql"
)


def test_migration_crea_tabella_idempotente() -> None:
    sql = MIGRATION.read_text()

    assert "CREATE TABLE IF NOT EXISTS news_poc_samples" in sql
    for column in (
        "poc_source",
        "symbol",
        "external_id",
        "title",
        "body_chars",
        "url",
        "published_at",
        "fetched_at",
        "latency_seconds",
        "ticker_valid",
        "raw_response",
        "created_at",
    ):
        assert column in sql, f"manca colonna {column}"

    # Vincolo di unicita' dedup su (poc_source, external_id) — vedi seam 2.
    assert "idx_news_poc_samples_source_extid" in sql
    assert "WHERE external_id IS NOT NULL" in sql

    # Indice di lookup per cohorte PoC.
    assert "idx_news_poc_samples_source_symbol" in sql


def test_migration_crea_ledger_budget_giornaliero() -> None:
    """Edge case 8: il budget va fermato da noi, non dal rate limit del provider —
    serve un ledger persistente delle richieste consumate per giorno."""
    sql = MIGRATION.read_text()

    assert "CREATE TABLE IF NOT EXISTS news_poc_request_budget" in sql
    for column in ("poc_source", "day", "requests", "updated_at"):
        assert column in sql, f"manca colonna {column}"
    # una riga per (poc_source, giorno): il contatore e' cumulativo sulle run
    assert "PRIMARY KEY (poc_source, day)" in sql
    # idempotente come il resto della migration (coesistenza con PoC parallele)
    assert "CREATE INDEX IF NOT EXISTS" in sql or sql.count("IF NOT EXISTS") >= 2