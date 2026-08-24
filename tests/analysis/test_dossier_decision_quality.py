"""#284 — P&L active/passive e qualita' decisionale read-only."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from src.analysis.dossier.decision_quality import (
    DECISION_QUALITY_SCHEMA_VERSION,
    build_decision_quality_panel,
    build_decision_quality_rollup,
    build_opening_snapshot,
)


def _bars() -> dict[str, dict[str, float]]:
    return {
        "AAPL": {"open": 100.0, "close": 105.0},
        "MSFT": {"open": 100.0, "close": 101.0},
        "TSLA": {"open": 100.0, "close": 105.0},
        "SPY": {"open": 100.0, "close": 102.0},
        "XLK": {"open": 50.0, "close": 50.5},
    }


def _opening_trades() -> list[dict]:
    return [
        {
            "trade_id": 1,
            "symbol": "AAPL",
            "strategia": "S1",
            "qty": 10.0,
            "entry_price": 90.0,
            "entry_time": "2026-08-01T14:00:00+00:00",
            "exit_time": None,
            "exit_price": None,
        },
        {
            "trade_id": 2,
            "symbol": "MSFT",
            "strategia": "S1",
            "qty": 5.0,
            "entry_price": 95.0,
            "entry_time": "2026-08-02T14:00:00+00:00",
            "exit_time": "2026-08-12T18:00:00+00:00",
            "exit_price": 103.0,
        },
    ]


def _dossier() -> dict:
    snapshot = build_opening_snapshot(
        _opening_trades(),
        _bars(),
        data="2026-08-12",
        sector_by_ticker={"AAPL": "tech", "MSFT": "tech"},
    )
    return {
        "data": "2026-08-12",
        "snapshot_apertura": snapshot,
        "decision_quality_assumptions": {
            "sizing_reference_usd": 2200.0,
            "sizing_reference_source": "S4 fixed slot osservato",
        },
        "ingressi": [
            {
                "symbol": "TSLA",
                "strategia": "S4",
                "ora_utc": "15:22",
                "entry_price": 102.0,
                "qty": 10.0,
                "mtm_eod": 30.0,
                "vs_apertura": 50.0,
                "entry_percentile": 0.8,
            }
        ],
        "chiusure": [
            {
                "symbol": "MSFT",
                "strategia": "S1",
                "exit_price": 103.0,
                "qty": 5.0,
                "pnl_net": 25.0,
                "exit_reason": "portfolio_sell",
                "ore_tenuta": 240.0,
                "drift_post_uscita": -10.0,
            },
            {
                "symbol": "NVDA",
                "strategia": "S4",
                "exit_price": 110.0,
                "qty": 2.0,
                "pnl_net": -5.0,
                "exit_reason": "sentiment_reversal",
                "ore_tenuta": 4.0,
                "drift_post_uscita": 6.0,
            },
        ],
        "guard_decisions": [
            {
                "decision_id": 10,
                "tick_time": "2026-08-12T15:00:00+00:00",
                "symbol": "AAPL",
                "signal_id": 501,
                "decision": "SKIP_CAP",
                "counterfactual_return_1h": 0.04,
                "counterfactual_return_overnight": None,
                "counterfactual_skip_reason": None,
                "intended_notional_usd": 1000.0,
            },
            # Stesso evento causale osservato in un ciclo successivo: non va
            # contato una seconda volta.
            {
                "decision_id": 11,
                "tick_time": "2026-08-12T15:15:00+00:00",
                "symbol": "AAPL",
                "signal_id": 501,
                "decision": "SKIP_CAP",
                "counterfactual_return_1h": 0.03,
                "counterfactual_return_overnight": None,
                "counterfactual_skip_reason": None,
                "intended_notional_usd": 1000.0,
            },
            {
                "decision_id": 12,
                "tick_time": "2026-08-12T16:00:00+00:00",
                "symbol": "MSFT",
                "signal_id": 502,
                "decision": "SKIP_EMA",
                "counterfactual_return_1h": -0.03,
                "counterfactual_return_overnight": None,
                "counterfactual_skip_reason": None,
                "intended_notional_usd": 2000.0,
            },
        ],
    }


def test_snapshot_apertura_isola_il_passivo_e_scompone_beta_uno():
    rows = build_opening_snapshot(
        _opening_trades(),
        _bars(),
        data="2026-08-12",
        sector_by_ticker={"AAPL": "tech", "MSFT": "tech"},
    )

    aapl = next(row for row in rows if row["ticker"] == "AAPL")
    assert aapl["causal_event_id"] == "opening-trade:1:2026-08-12"
    assert aapl["passive_pnl_usd"] == pytest.approx(50.0)
    assert aapl["actual_intraday_pnl_usd"] == pytest.approx(50.0)
    assert aapl["exit_active_effect_usd"] == pytest.approx(0.0)
    assert aapl["beta_1_attribution"]["market_usd"] == pytest.approx(20.0)
    assert aapl["beta_1_attribution"]["sector_incremental_usd"] == pytest.approx(-10.0)
    assert aapl["beta_1_attribution"]["residual_usd"] == pytest.approx(40.0)

    msft = next(row for row in rows if row["ticker"] == "MSFT")
    # Il passivo e' il no-action close-open; l'uscita attiva corregge poi il
    # baseline fino al prezzo di fill osservato.
    assert msft["passive_pnl_usd"] == pytest.approx(5.0)
    assert msft["actual_intraday_pnl_usd"] == pytest.approx(15.0)
    assert msft["exit_active_effect_usd"] == pytest.approx(10.0)
    assert msft["qty_close"] == pytest.approx(0.0)


def test_selection_timing_sizing_exit_sono_controfattuali_separati():
    panel = build_decision_quality_panel(_dossier(), dossier_hash="sha")
    entry = panel["active_decisions"]["entries"][0]

    assert panel["schema_version"] == DECISION_QUALITY_SCHEMA_VERSION
    assert entry["selection"]["effect_usd"] == pytest.approx(30.0)
    assert entry["selection"]["confidenza"] == "misurata"
    assert entry["timing"]["counterfactual_usd"] == pytest.approx(50.0)
    assert entry["timing"]["effect_usd"] == pytest.approx(-20.0)
    assert entry["timing"]["confidenza"] == "attribuita"
    assert entry["sizing"]["counterfactual_usd"] == pytest.approx(
        (105.0 / 102.0 - 1.0) * 2200.0
    )
    assert entry["sizing"]["confidenza"] == "attribuita"

    exits = panel["active_decisions"]["exits"]
    msft = next(row for row in exits if row["ticker"] == "MSFT")
    nvda = next(row for row in exits if row["ticker"] == "NVDA")
    assert msft["exit"]["effect_usd"] == pytest.approx(10.0)
    assert nvda["exit"]["effect_usd"] == pytest.approx(-6.0)
    assert all(row["exit"]["confidenza"] == "attribuita" for row in exits)
    assert panel["summary"]["passive_pnl_usd"] == pytest.approx(55.0)
    assert panel["summary"]["active_decision_pnl_usd"] == pytest.approx(34.0)
    assert panel["summary"]["actual_intraday_pnl_usd"] == pytest.approx(89.0)
    assert panel["summary"]["counterfactual_axes_are_additive"] is False


def test_guard_cost_e_avoided_loss_non_doppio_conteggio():
    panel = build_decision_quality_panel(_dossier())
    guards = panel["guards"]

    assert len(guards) == 2
    cost = next(row for row in guards if row["signal_id"] == 501)
    benefit = next(row for row in guards if row["signal_id"] == 502)
    assert cost["source_decision_ids"] == [10, 11]
    assert cost["guard_cost_return"] == pytest.approx(0.04)
    assert cost["guard_cost_usd"] == pytest.approx(40.0)
    assert cost["avoided_loss_return"] == pytest.approx(0.0)
    assert benefit["guard_cost_return"] == pytest.approx(0.0)
    assert benefit["avoided_loss_return"] == pytest.approx(0.03)
    assert benefit["avoided_loss_usd"] == pytest.approx(60.0)
    assert panel["summary"]["guard_cost_usd"] == pytest.approx(40.0)
    assert panel["summary"]["guard_avoided_loss_usd"] == pytest.approx(60.0)


def test_holding_e_size_restano_analisi_descrittive_senza_taratura():
    panel = build_decision_quality_panel(_dossier())
    diagnostics = panel["diagnostics"]

    assert diagnostics["entry_percentile"]["median"] == pytest.approx(0.8)
    assert diagnostics["entry_percentile"]["quota_sopra_0_70"] == pytest.approx(1.0)
    assert diagnostics["holding"]["median_hours"] == pytest.approx(122.0)
    assert diagnostics["sizing"]["n"] == 1
    assert diagnostics["sizing"]["median_notional_usd"] == pytest.approx(1020.0)
    assert diagnostics["policy_output"] == "descriptive_only_no_live_tuning"
    assert "recommendation" not in diagnostics


def test_missingness_non_diventa_zero():
    rows = build_opening_snapshot(
        [{**_opening_trades()[0], "symbol": "MISSING"}],
        _bars(),
        data="2026-08-12",
        sector_by_ticker={},
    )
    assert rows[0]["passive_pnl_usd"] is None
    assert rows[0]["actual_intraday_pnl_usd"] is None
    assert rows[0]["missingness"] == ["daily_bar_missing"]
    panel = build_decision_quality_panel(
        {"data": "2026-08-12", "snapshot_apertura": rows, "guard_decisions": []}
    )
    assert panel["summary"]["passive_pnl_usd"] is None
    assert panel["summary"]["actual_intraday_pnl_usd"] is None


def test_variazione_quantita_intraday_corregge_il_baseline_passivo():
    trade = {
        **_opening_trades()[0],
        "qty": 10.0,
        "exit_fills": [
            {
                "order_id": "prior",
                "filled_at": "2026-08-11T18:00:00+00:00",
                "filled_qty": 2.0,
                "filled_avg_price": 99.0,
            },
            {
                "order_id": "partial-today",
                "filled_at": datetime(2026, 8, 12, 18, 0, tzinfo=timezone.utc),
                "filled_qty": 3.0,
                "filled_avg_price": 104.0,
            },
        ],
    }
    rows = build_opening_snapshot(
        [trade],
        _bars(),
        data="2026-08-12",
        sector_by_ticker={"AAPL": "tech"},
    )
    row = rows[0]

    assert row["qty_open"] == pytest.approx(8.0)
    assert row["qty_close"] == pytest.approx(5.0)
    assert row["passive_pnl_usd"] == pytest.approx(40.0)
    assert row["actual_intraday_pnl_usd"] == pytest.approx(37.0)
    assert row["exit_active_effect_usd"] == pytest.approx(-3.0)
    assert row["quantity_changes_intraday"][0]["order_id"] == "partial-today"
    json.dumps(rows)  # i datetime del broker devono essere normalizzati a ISO

    panel = build_decision_quality_panel(
        {"data": "2026-08-12", "snapshot_apertura": rows, "guard_decisions": []}
    )
    assert panel["summary"]["exit_effect_usd"] == pytest.approx(-3.0)
    assert panel["summary"]["actual_intraday_pnl_usd"] == pytest.approx(37.0)


def test_guard_senza_notional_non_diventa_zero_dollari():
    dossier = _dossier()
    for guard in dossier["guard_decisions"]:
        guard["intended_notional_usd"] = None
    panel = build_decision_quality_panel(dossier)

    assert panel["summary"]["guard_cost_usd"] is None
    assert panel["summary"]["guard_avoided_loss_usd"] is None
    assert panel["guards"][0]["guard_cost_return"] is not None
    rollup = build_decision_quality_rollup([panel])
    assert rollup["totali_usd"]["guard_cost_usd"] is None
    assert rollup["totali_usd"]["guard_avoided_loss_usd"] is None
    assert rollup["n_guard_cost_usd_mancanti"] == 1
    assert rollup["n_guard_avoided_loss_usd_mancanti"] == 1


def test_rollup_cumulativo_non_imputa_il_passivo_mancante():
    complete = build_decision_quality_panel(_dossier())
    legacy = build_decision_quality_panel(
        {
            "data": "2026-08-11",
            "ingressi": [],
            "chiusure": [],
        }
    )

    rollup = build_decision_quality_rollup([legacy, complete])

    assert rollup["n_giorni"] == 2
    assert rollup["n_giorni_snapshot_apertura_mancante"] == 1
    assert rollup["totali_usd"]["passive_pnl_usd"] == pytest.approx(55.0)
    assert rollup["totali_usd"]["active_decision_pnl_usd"] == pytest.approx(34.0)
    assert rollup["serie"][0]["passive_pnl_usd"] is None
    assert rollup["serie"][1]["cumulative_passive_pnl_usd"] == pytest.approx(55.0)


def test_rollup_deduplica_lo_stesso_guard_anche_fra_due_giorni():
    first = build_decision_quality_panel(_dossier())
    next_day_dossier = _dossier()
    next_day_dossier["data"] = "2026-08-13"
    second = build_decision_quality_panel(next_day_dossier)

    rollup = build_decision_quality_rollup([first, second])

    assert rollup["totali_usd"]["guard_cost_usd"] == pytest.approx(40.0)
    assert rollup["totali_usd"]["guard_avoided_loss_usd"] == pytest.approx(60.0)
    assert rollup["n_guard_duplicati_scartati"] == 2
