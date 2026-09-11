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


MIGRATION_067 = (
    Path(__file__).resolve().parents[2]
    / "migrations"
    / "067_stale_drop_off_session.sql"
)


def test_067_aggiunge_il_flag_di_seduta_sulle_righe_di_scarto() -> None:
    sql = MIGRATION_067.read_text()

    assert "ALTER TABLE news_queue_drops" in sql
    assert "enqueued_off_session" in sql


def test_067_backfilla_le_righe_storiche_con_il_fuso_di_borsa() -> None:
    """Le righe di 08-09/09 precedono la colonna: senza backfill la serie
    ricalcolata avrebbe due definizioni nella stessa colonna."""
    sql = MIGRATION_067.read_text()

    assert "UPDATE news_queue_drops" in sql
    # DST gestito dal fuso, non da un orario UTC cablato.
    assert "America/New_York" in sql


def test_067_estende_a_quattro_addendi_il_check_sulla_somma() -> None:
    sql = MIGRATION_067.read_text()

    assert "ALTER TABLE stale_drop_metrics_daily" in sql
    assert "went_stale_off_session" in sql
    # La 062 impone la somma a tre: il vincolo vecchio va rimosso, non affiancato.
    assert "DROP CONSTRAINT" in sql
    compatto = " ".join(sql.split())
    assert (
        "already_stale_at_fetch + went_stale_in_queue"
        " + went_stale_off_session + unclassified_stale = stale_drops" in compatto
    )


def test_067_rimuove_il_vincolo_della_somma_senza_portarsi_via_la_non_negativita() -> None:
    """`already_stale_at_fetch` compare in DUE vincoli della 062.

    Cercare la colonna invece della somma faceva cadere anche
    `CHECK (already_stale_at_fetch >= 0)`: la tabella usciva dalla migrazione
    con un vincolo in meno di quelli che aveva, senza che nulla lo segnalasse.
    """
    compatto = " ".join(MIGRATION_067.read_text().split())

    predicato = compatto.split("FOR vecchio IN")[1].split("LOOP")[0]
    assert "LIKE '%already_stale_at_fetch%'" in predicato
    # E' la somma a identificare il vincolo, non la singola colonna.
    assert "LIKE '%unclassified_stale%'" in predicato
    assert "LIKE '%stale_drops%'" in predicato
    assert "NOT LIKE '%went_stale_off_session%'" in predicato


def test_067_e_idempotente_e_cerca_i_vincoli_sulla_propria_tabella() -> None:
    compatto = " ".join(MIGRATION_067.read_text().split())

    assert compatto.count("ADD COLUMN IF NOT EXISTS") == 2
    # conname non e' unico per database: senza conrelid la guardia potrebbe
    # leggere il vincolo omonimo di un'altra tabella.
    assert compatto.count(
        "WHERE conrelid = 'stale_drop_metrics_daily'::regclass"
        " AND conname = 'ck_stale_drop_metrics"
    ) == 2
