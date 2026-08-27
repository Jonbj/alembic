"""#297: l'adattatore che porta P1 dal mondo osservabile al modulo puro."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.strategies.s4.lifecycle import MarketSession
from src.strategies.s4.p1_runtime import (
    build_window,
    d_hard_distance,
    project_p1_candidates,
)

DUE_CLOSE = datetime(2026, 8, 27, 20, 0, tzinfo=UTC)


def _sessions() -> list[MarketSession]:
    return [
        MarketSession(
            session_date=date(2026, 8, day),
            open_at=datetime(2026, 8, day, 13, 30, tzinfo=UTC),
            close_at=datetime(2026, 8, day, 20, 0, tzinfo=UTC),
        )
        for day in (25, 26, 27)
    ]


def _row(**overrides) -> dict:
    values = {
        "event_id": "5f9f6a7e-1a2b-4c3d-8e9f-0a1b2c3d4e5f",
        "intent_id": "34d6c4c0-bcb2-55ef-a0f4-e3db1a4a13b0",
        "event_type": "ENTRY_RECONCILIATION",
        "observed_at": datetime(2026, 8, 25, 19, 12, tzinfo=UTC),
        "symbol": "AMD",
        "order_id": "entry-order-1",
        "status": "FILLED",
        "reason_code": "BROKER_FILLED",
        "fill_id": "0a1b2c3d-4e5f-6a7b-8c9d-0e1f2a3b4c5d",
        "filled_at": datetime(2026, 8, 25, 19, 7, 5, tzinfo=UTC),
        "filled_quantity": 2.0,
        "filled_notional": 200.0,
        "fill_price": 100.0,
        "first_executable_price": 100.0,
        "first_executable_price_source": "alpaca_snapshot.latest_trade",
        "d0": date(2026, 8, 25),
        "due_session": date(2026, 8, 27),
        "policy_version": "s4-exit-trial:1.0.0",
        "s1_virtual_quantity": 0.0,
        "s4_virtual_quantity": 2.0,
        "broker_quantity": 0.0,
        "unattributed_quantity": 0.0,
        "reconstructible": True,
        "details": {},
        "stop_mode": "vol_scaled",
        "stop_d_init": 0.08,
        "stop_vol_at_entry": 0.02,
        # Floor e cap del **protective stop** S4 (`stop_strategy_params`), che
        # e' cio' che la riga di trade porta davvero. Non sono i confini del
        # disaster stop: la fixture precedente scriveva 0.12/0.20 — i valori
        # del disaster stop — e nascondeva proprio il difetto.
        "stop_floor": 0.03,
        "stop_cap": 0.08,
    }
    values.update(overrides)
    return values


def _bar(minute: int, close: float, low: float | None = None):
    return SimpleNamespace(
        timestamp=datetime(2026, 8, 27, 19, minute, tzinfo=UTC),
        close=close,
        low=close if low is None else low,
    )


# ── Lo stop congelato, non uno ricalcolato oggi ────────────────────────────


_DISASTER_STOP = {
    "multiplier": 1.5,
    "sigma_multiple": 5.0,
    "floor_pct": 0.12,
    "cap_pct": 0.20,
}


def test_la_distanza_di_stop_viene_dai_parametri_congelati_all_ingresso():
    """Usare la sigma di oggi per un'uscita di due giorni fa sarebbe look-ahead."""
    distanza = d_hard_distance(_row(), _DISASTER_STOP)

    # max(1.5 × 0.08, 5.0 × 0.02) = 0.12, dentro [floor, cap] del disaster stop
    assert distanza == pytest.approx(0.12)


def test_floor_e_cap_vengono_dal_disaster_stop_non_dal_protective():
    """`stop_floor`/`stop_cap` sulla riga di trade sono un'altra cosa.

    Sono i confini dello stop protettivo di sleeve (S4: 0.03–0.08). Il disaster
    stop vive in `broker_disaster_stop` (0.12–0.20) e `StopPolicy.d_hard` legge
    solo quello. Clippare a 0.08 darebbe a P1 uno stop molto piu' stretto di
    quello comune, cioe' una violazione di `identical_across_policies`: P1
    uscirebbe per rischio dove nessun'altra policy lo farebbe.
    """
    distanza = d_hard_distance(
        _row(stop_d_init=0.0, stop_vol_at_entry=0.0237), _DISASTER_STOP
    )

    assert distanza == pytest.approx(0.12)
    assert distanza > 0.08


def test_la_distanza_resta_dentro_floor_e_cap():
    assert d_hard_distance(_row(stop_d_init=0.5), _DISASTER_STOP) == pytest.approx(0.20)
    assert d_hard_distance(
        _row(stop_d_init=0.001, stop_vol_at_entry=0.0), _DISASTER_STOP
    ) == pytest.approx(0.12)


def test_una_config_del_disaster_stop_mancante_non_inventa_confini():
    """Senza config i default sono quelli di `StopPolicy`, mai quelli di sleeve."""
    assert d_hard_distance(_row(stop_d_init=0.0, stop_vol_at_entry=0.0), {}) == (
        pytest.approx(0.12)
    )


def test_senza_stop_congelato_la_distanza_e_ignota_non_zero():
    assert d_hard_distance(_row(stop_d_init=None), _DISASTER_STOP) is None


# ── La finestra: completa solo quando il cutoff e' davvero passato ─────────


def test_la_finestra_non_e_completa_prima_della_close_di_scadenza():
    window = build_window(
        [(datetime(2026, 8, 26, 15, 0, tzinfo=UTC), 101.0, 100.0)],
        DUE_CLOSE,
        now=datetime(2026, 8, 26, 16, 0, tzinfo=UTC),
    )

    assert window.complete is False


def test_la_finestra_e_completa_dopo_la_close_di_scadenza():
    window = build_window(
        [(datetime(2026, 8, 27, 19, 59, tzinfo=UTC), 110.0, 109.0)],
        DUE_CLOSE,
        now=DUE_CLOSE + timedelta(minutes=25),
    )

    assert window.complete is True
    assert window.quotes[0].price == pytest.approx(110.0)
    assert window.quotes[0].low == pytest.approx(109.0)


def test_senza_cutoff_la_finestra_non_si_dichiara_completa():
    """Una due_session fuori dal calendario non deve far uscire P1 comunque."""
    window = build_window([], None, now=DUE_CLOSE + timedelta(days=5))

    assert window.complete is False


# ── Proiezione end-to-end, con il broker solo in lettura ──────────────────


def test_la_proiezione_scrive_un_esito_p1_senza_toccare_ordini():
    store = MagicMock()
    store.fetch_s4_p1_candidates.return_value = [_row()]
    data = MagicMock()
    data.get_stock_bars.return_value = SimpleNamespace(
        data={"AMD": [_bar(0, 105.0), _bar(59, 110.0)]}
    )

    count = project_p1_candidates(
        store, data, _sessions(), observed_at=DUE_CLOSE + timedelta(minutes=30)
    )

    assert count == 1
    [event] = store.write_s4_exit_policy_events.call_args.args[0]
    assert event.policy_id == "P1"
    assert event.status == "CLOSED"
    assert event.reason_code == "P1_TIME_DUE"
    assert event.fill_price == pytest.approx(110.0)
    assert event.shadow_order_id is None
    data.get_stock_bars.assert_called_once()


def test_prima_della_scadenza_la_proiezione_dice_solo_che_sta_tenendo():
    store = MagicMock()
    store.fetch_s4_p1_candidates.return_value = [_row()]
    data = MagicMock()
    data.get_stock_bars.return_value = SimpleNamespace(
        data={"AMD": [_bar(0, 105.0)]}
    )

    project_p1_candidates(
        store, data, _sessions(), observed_at=datetime(2026, 8, 26, 16, tzinfo=UTC)
    )

    [event] = store.write_s4_exit_policy_events.call_args.args[0]
    assert event.status == "OPEN"
    assert event.reason_code == "P1_HOLDING"


def test_barre_non_disponibili_non_bloccano_la_proiezione():
    """Criterio 4: un data failure non falsifica la tesi aperta."""
    store = MagicMock()
    store.fetch_s4_p1_candidates.return_value = [_row()]
    data = MagicMock()
    data.get_stock_bars.side_effect = RuntimeError("429 rate limited")

    project_p1_candidates(
        store, data, _sessions(), observed_at=DUE_CLOSE + timedelta(minutes=30)
    )

    [event] = store.write_s4_exit_policy_events.call_args.args[0]
    assert event.status == "TRIGGERED"
    assert event.reason_code == "P1_EXIT_PRICE_MISSING"
    assert event.net_pnl is None


def test_nessun_candidato_non_scrive_nulla():
    store = MagicMock()
    store.fetch_s4_p1_candidates.return_value = []

    assert project_p1_candidates(store, MagicMock(), _sessions()) == 0
    store.write_s4_exit_policy_events.assert_not_called()
