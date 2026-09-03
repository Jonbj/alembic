"""Contratto dello schema persistente per l'aggregato #432."""

from pathlib import Path


MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "migrations"
    / "062_stale_drop_metrics_daily.sql"
)


def test_migration_persiste_quota_cause_e_parametri_di_misura() -> None:
    sql = MIGRATION.read_text()

    assert "CREATE TABLE IF NOT EXISTS stale_drop_metrics_daily" in sql
    for column in (
        "day",
        "source",
        "queued",
        "stale_drops",
        "already_stale_at_fetch",
        "went_stale_in_queue",
        "unclassified_stale",
        "stale_drop_share",
        "avg_fetch_latency_hours",
        "avg_queue_wait_hours",
        "max_news_age_hours",
        "alert_threshold",
        "alert_required",
        "measured_at",
    ):
        assert column in sql
    assert "PRIMARY KEY (day, source)" in sql
