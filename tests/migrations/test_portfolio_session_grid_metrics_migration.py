"""Contratto dello schema persistente per la misura #428."""

from pathlib import Path


MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "migrations"
    / "058_portfolio_session_grid_metrics.sql"
)


def test_migration_conserva_confini_cicli_gap_e_soglia() -> None:
    sql = MIGRATION.read_text()

    assert "CREATE TABLE IF NOT EXISTS portfolio_session_grid_metrics" in sql
    for column in (
        "session_date",
        "session_open",
        "session_close",
        "first_effective_cycle",
        "last_effective_cycle",
        "open_gap_minutes",
        "close_gap_minutes",
        "threshold_minutes",
        "alert_required",
        "measured_at",
    ):
        assert column in sql
    assert "PRIMARY KEY (session_date)" in sql

