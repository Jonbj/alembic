"""#491: misura offline del gap fra target S1 e posizioni broker."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from scripts.measure_s1_weight_gap import build_report


def test_fixture_calcola_sleeve_righe_e_totali_senza_rete() -> None:
    report = build_report(
        as_of=datetime(2026, 9, 4, 8, 0, tzinfo=timezone.utc),
        rebalance_state={
            "last_rebalance": "2026-09-01T14:07:00+00:00",
            "target_weights": {"NOK": 0.02, "WDC": 0.01, "GS": 0.03},
        },
        rebalance_fills=[
            # `trades.score` e' portfolio-level e puo' essere diverso: per la
            # sleeve implicita deve vincere il peso S1 vivo letto da Redis.
            {"symbol": "NOK", "entry_notional": 200.0, "weight": 0.01},
            {"symbol": "WDC", "entry_notional": 100.0, "weight": 0.005},
        ],
        broker_positions={"NOK": 6.0, "WDC": 20.0},
        open_trade_sleeves={"NOK": "S1", "WDC": "S4"},
    )

    assert report["sleeve_implicit_usd"] == pytest.approx(10_000.0)
    rows = {row["symbol"]: row for row in report["rows"]}
    assert rows["NOK"] == {
        "symbol": "NOK",
        "target_weight": pytest.approx(0.02),
        "target_usd": pytest.approx(200.0),
        "current_usd": pytest.approx(6.0),
        "ratio": pytest.approx(0.03),
        "gap_usd": pytest.approx(-194.0),
        "open_trade_sleeve": "S1",
        "covered_by_other_sleeve": False,
    }
    assert rows["GS"]["current_usd"] == 0.0
    assert rows["GS"]["ratio"] == 0.0
    assert report["totals"]["gross"] == {
        "target_usd": pytest.approx(600.0),
        "current_usd": pytest.approx(26.0),
        "gap_usd": pytest.approx(-574.0),
    }
    assert report["totals"]["excluding_other_sleeves"] == {
        "target_usd": pytest.approx(500.0),
        "current_usd": pytest.approx(6.0),
        "gap_usd": pytest.approx(-494.0),
    }


def test_sleeve_implicita_richiede_almeno_un_fill_valido() -> None:
    with pytest.raises(ValueError, match="fill valido"):
        build_report(
            as_of=datetime(2026, 9, 4, tzinfo=timezone.utc),
            rebalance_state={
                "last_rebalance": "2026-09-01T14:07:00+00:00",
                "target_weights": {"NOK": 0.02},
            },
            rebalance_fills=[],
            broker_positions={"NOK": 6.0},
            open_trade_sleeves={"NOK": "S1"},
        )
