"""#397: the dossier's open-position reader must report the live quantity
(quantity_remaining) for still-open trades, not the entry qty that partial exits
and broker stop fills never decremented (the 74x phantom signature)."""
from __future__ import annotations

from datetime import date
from unittest.mock import patch

import scripts.alpha_miner_dossier as dossier


def test_opening_positions_uses_quantity_remaining_for_open_rows():
    """The SELECT must read COALESCE(quantity_remaining, qty) for open rows so a
    partially-wound-down position reports its live residual, not entry qty."""
    captured: dict = {}

    def fake_psql(query):
        captured["sql"] = query
        # One still-open row: the DB returns the reconciled remaining (0.564),
        # not the phantom entry qty (41.564).
        return [["5", "NOK", "S1", "0.564", "4.20", "2026-07-21T16:00:00+00:00",
                 "", "", ""]]

    with patch.object(dossier, "_psql", fake_psql):
        rows = dossier._opening_positions(date(2026, 8, 26))

    sql = captured["sql"]
    assert "COALESCE(quantity_remaining, qty)" in sql
    assert "exit_time IS NULL" in sql
    assert rows[0]["qty"] == 0.564  # the live residual, not 41.564


def test_opening_positions_keeps_qty_for_rows_closed_today():
    """A row that closed today keeps qty (exit fill qty) — COALESCE on it would
    yield 0 and erase the position from the day's book MTM (regression guard)."""
    captured: dict = {}

    def fake_psql(query):
        captured["sql"] = query
        # exit_time set => closed today; the CASE must select `qty` (2.0), not
        # quantity_remaining (which reconcile set to ~0).
        return [["9", "AAA", "S4", "2.0", "100.0", "2026-08-25T16:00:00+00:00",
                 "2026-08-26T19:00:00+00:00", "101.0", "sell-1"]]

    with patch.object(dossier, "_psql", fake_psql):
        rows = dossier._opening_positions(date(2026, 8, 26))

    assert "ELSE qty END" in captured["sql"]
    assert rows[0]["qty"] == 2.0  # closed-today row keeps the exit-fill qty