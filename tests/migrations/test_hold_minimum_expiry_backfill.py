"""Contratto del backfill diagnostico #430."""

from pathlib import Path


MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "migrations"
    / "063_hold_minimum_expiry.sql"
)


def test_backfill_e_limitato_alla_finestra_e_alle_portfolio_sell_105_minuti():
    sql = MIGRATION.read_text()

    assert "SET exit_reason = 'hold_minimum_expiry'" in sql
    assert "exit_reason = 'portfolio_sell'" in sql
    assert "entry_time >= TIMESTAMPTZ '2026-08-03 00:00:00+00'" in sql
    assert "EXTRACT(EPOCH FROM (exit_time - entry_time))" in sql
    assert "6300" in sql


def test_backfill_non_modifica_logica_o_parametri_di_uscita():
    sql = MIGRATION.read_text()

    assert "UPDATE trades" in sql
    assert "execution.hold_minimum_minutes" not in sql
    assert "s4_anti_whipsaw_damping_enabled" not in sql
