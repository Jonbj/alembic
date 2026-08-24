"""#284 — wiring read-only di snapshot apertura e guard nel dossier."""

from __future__ import annotations

from datetime import date

import scripts.alpha_miner_dossier as dossier


def test_opening_positions_usa_l_open_rth_e_non_attribuisce_null_a_s1(monkeypatch):
    queries: list[str] = []

    def fake_psql(query: str):
        queries.append(query)
        return [
            [
                "7",
                "AAPL",
                "CONTAMINAZIONE",
                "2.5",
                "100.0",
                "2026-08-01 14:00:00+00",
                "",
                "",
            ]
        ]

    monkeypatch.setattr(dossier, "_psql", fake_psql)
    rows = dossier._opening_positions(date(2026, 8, 12))

    assert rows[0]["trade_id"] == 7
    assert rows[0]["strategia"] == "CONTAMINAZIONE"
    assert rows[0]["exit_time"] is None
    sql = queries[0]
    assert "entry_time < '2026-08-12T13:30:00+00:00'" in sql
    assert "exit_time >= '2026-08-12T13:30:00+00:00'" in sql
    assert "ELSE 'CONTAMINAZIONE'" in sql


def test_guard_decisions_porta_ritorni_e_notional_solo_quando_misurabile(monkeypatch):
    queries: list[str] = []

    def fake_psql(query: str):
        queries.append(query)
        return [
            [
                "10",
                "2026-08-12 15:00:00+00",
                "AAPL",
                "501",
                "SKIP_CAP",
                "0.04",
                "",
                "",
                "2026-08-12 23:00:00+00",
                "",
            ]
        ]

    monkeypatch.setattr(dossier, "_psql", fake_psql)
    rows = dossier._guard_decisions(date(2026, 8, 12))

    assert rows == [
        {
            "decision_id": 10,
            "tick_time": "2026-08-12 15:00:00+00",
            "symbol": "AAPL",
            "signal_id": 501,
            "decision": "SKIP_CAP",
            "counterfactual_return_1h": 0.04,
            "counterfactual_return_overnight": None,
            "counterfactual_skip_reason": None,
            "counterfactual_computed_at": "2026-08-12 23:00:00+00",
            "intended_notional_usd": None,
        }
    ]
    assert "SKIP_PYRAMIDING" in queries[0]
    assert "portfolio_monitor_snapshots" in queries[0]
    assert "2026-08-19" in queries[0]
