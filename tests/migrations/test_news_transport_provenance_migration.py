"""Contratto della migrazione 075 — provenienza di trasporto per riga (#541)."""

from pathlib import Path


MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "migrations"
    / "075_news_transport_provenance.sql"
)


def test_la_colonna_e_additiva_su_entrambi_i_ledger():
    sql = MIGRATION.read_text()

    assert "ALTER TABLE news_log" in sql
    assert "ALTER TABLE news_queue_drops" in sql
    assert sql.count("ADD COLUMN IF NOT EXISTS transport") == 2


def test_il_dominio_e_chiuso_sui_due_trasporti_reali():
    sql = MIGRATION.read_text()

    assert "'ws'" in sql
    assert "'rest'" in sql


def test_nessun_backfill_retroattivo_della_provenienza():
    """Lo storico non ha provenienza e non e' ricostruibile: dedurla dalla
    latenza inventerebbe un dato dentro una serie misurata. NULL = «non
    strumentato», ed e' un'informazione vera."""
    sql = MIGRATION.read_text()

    assert "UPDATE news_log" not in sql
    assert "UPDATE news_queue_drops" not in sql


def test_lo_snapshot_di_sottoscrizione_esiste_ed_e_temporale():
    sql = MIGRATION.read_text()

    assert "CREATE TABLE IF NOT EXISTS news_stream_subscriptions" in sql
    assert "observed_at" in sql
    assert "symbols" in sql


def test_la_serie_ws_missed_e_una_vista_interrogabile_in_una_query_sola():
    """DoD #541: «una query sola risponde quanti articoli il WebSocket ha perso
    ieri, su quali simboli, con che ritardo di recupero REST»."""
    sql = MIGRATION.read_text()

    assert "CREATE OR REPLACE VIEW news_transport_first_sighting" in sql
    assert "CREATE OR REPLACE VIEW news_ws_missed_daily" in sql
    for colonna in (
        "articoli_ws_missed",
        "simboli_ws_missed",
        "ritardo_recupero_medio_ore",
    ):
        assert colonna in sql


def test_la_vista_distingue_articoli_da_coppie_articolo_ticker():
    """La misura del 15/09 §2.3: «i 313 scarti sono 69 articoli», rapporto 4,5:1.
    Una serie che conta coppie e le chiama articoli e' gonfia per costruzione."""
    sql = MIGRATION.read_text()

    assert "count(DISTINCT f.url)" in sql or "count(DISTINCT url)" in sql
    assert "coppie_ws_missed" in sql


def test_il_miss_e_ristretto_ai_simboli_sottoscritti_in_quel_momento():
    sql = MIGRATION.read_text()

    assert "news_stream_subscriptions" in sql
    assert "observed_at <=" in sql
    assert "symbol_subscribed" in sql


def test_la_migrazione_non_tocca_soglie_ne_money_path():
    """freeze #171: e' strumentazione, non taratura."""
    sql = MIGRATION.read_text()

    for vietato in (
        "MAX_NEWS_AGE_HOURS",
        "stale_drop_metrics_daily",
        "alert_threshold",
        "execution_decisions",
        "sentiment_signals",
        "trades",
    ):
        assert vietato not in sql
