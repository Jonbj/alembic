"""Contratto della migrazione 077 — velocity_multiplier su execution_decisions (#550)."""

from pathlib import Path


MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "migrations"
    / "077_execution_decision_velocity_multiplier.sql"
)


def test_la_colonna_e_additiva_e_nullable():
    sql = MIGRATION.read_text()

    assert "ALTER TABLE execution_decisions" in sql
    assert "ADD COLUMN IF NOT EXISTS velocity_multiplier" in sql
    assert "NOT NULL" not in sql


def test_nessun_backfill_retroattivo_del_moltiplicatore():
    """Lo storico non registra il moltiplicatore per ciclo: ricostruirlo dalle
    soglie o dai log morti col container inventerebbe un dato dentro una serie
    misurata. NULL = «non strumentato», ed e' un'informazione vera (come la
    provenienza di trasporto nella 075)."""
    sql = MIGRATION.read_text()

    assert "UPDATE execution_decisions" not in sql


def test_la_migrazione_non_tocca_soglie_ne_altre_tabelle():
    """freeze #171: e' strumentazione su una tabella di evidenza, non taratura.
    I nomi di altre tabelle possono comparire nella prosa del commento, mai
    come oggetto di uno statement."""
    sql = MIGRATION.read_text()

    assert sql.count("ALTER TABLE") == 1
    assert "ALTER TABLE execution_decisions" in sql
    assert "UPDATE " not in sql
    # un DEFAULT fingerebbe un moltiplicatore mai misurato
    assert "DEFAULT" not in sql


def test_il_commento_dichiara_la_semantica_del_decidente():
    """La riga si spieghi da sola: decidente = signal_score x velocity_multiplier,
    a confronto con la soglia attiva."""
    sql = MIGRATION.read_text()

    assert "COMMENT ON COLUMN execution_decisions.velocity_multiplier" in sql
    assert "signal_score" in sql
