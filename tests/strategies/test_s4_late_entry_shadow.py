"""#512: misura point-in-time degli ingressi S4 tardivi, solo shadow."""

from __future__ import annotations

import pytest

from src.strategies.s4.late_entry_shadow import observe_late_entry


def test_guardia_ombra_segnala_un_long_inseguito_nella_parte_alta_del_range():
    observation = observe_late_entry(
        signal_score=0.52,
        decision_price=108.0,
        session_open=100.0,
        session_high=110.0,
        session_low=100.0,
        price_source="alpaca_snapshot.latest_trade",
    )

    assert observation["session_return_from_open"] == pytest.approx(0.08)
    assert observation["session_range_percentile"] == pytest.approx(0.8)
    assert observation["shadow_late_entry"] is True
    assert observation["shadow_reason"].startswith("SHADOW_LATE_ENTRY")
    assert observation["missingness"] == {}


def test_guardia_ombra_non_confonde_un_ribasso_con_un_ingresso_precoce():
    observation = observe_late_entry(
        signal_score=0.52,
        decision_price=92.0,
        session_open=100.0,
        session_high=101.0,
        session_low=90.0,
        price_source="alpaca_snapshot.latest_trade",
    )

    assert observation["session_return_from_open"] == pytest.approx(-0.08)
    assert observation["shadow_late_entry"] is False
    assert observation["shadow_reason"] is None


def test_guardia_ombra_dichiara_il_range_degenere_senza_inventare_un_false():
    observation = observe_late_entry(
        signal_score=0.52,
        decision_price=100.0,
        session_open=100.0,
        session_high=100.0,
        session_low=100.0,
        price_source="alpaca_snapshot.minute_bar.close",
    )

    assert observation["session_range_percentile"] is None
    assert observation["shadow_late_entry"] is None
    assert observation["missingness"] == {
        "session_range_percentile": "session_range_not_positive"
    }

