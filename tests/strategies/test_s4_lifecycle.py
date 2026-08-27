"""#295: lifecycle broker e sleeve virtuali per il trial exit S4."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from src.strategies.s4.lifecycle import (
    BrokerOrderSnapshot,
    MarketSession,
    SubmittedIntent,
    apply_virtual_s4_exit,
    build_reconstruction_report,
    reconcile_entry,
)


UTC = timezone.utc
OBSERVED_AT = datetime(2026, 8, 25, 15, 8, tzinfo=UTC)


def _sessions() -> list[MarketSession]:
    return [
        MarketSession(
            session_date=date(2026, 8, 25),
            open_at=datetime(2026, 8, 25, 13, 30, tzinfo=UTC),
            close_at=datetime(2026, 8, 25, 20, 0, tzinfo=UTC),
        ),
        MarketSession(
            session_date=date(2026, 8, 26),
            open_at=datetime(2026, 8, 26, 13, 30, tzinfo=UTC),
            close_at=datetime(2026, 8, 26, 20, 0, tzinfo=UTC),
        ),
        MarketSession(
            session_date=date(2026, 8, 27),
            open_at=datetime(2026, 8, 27, 13, 30, tzinfo=UTC),
            close_at=datetime(2026, 8, 27, 20, 0, tzinfo=UTC),
        ),
    ]


def _intent(**overrides) -> SubmittedIntent:
    values = {
        "intent_id": "34d6c4c0-bcb2-55ef-a0f4-e3db1a4a13b0",
        "symbol": "AMD",
        "order_id": "alpaca-order-1",
        "submitted_at": datetime(2026, 8, 25, 15, 7, tzinfo=UTC),
        "requested_quantity": 6.0,
        "requested_notional": 630.0,
        "first_executable_price": 105.0,
        "first_executable_price_source": "alpaca_snapshot.latest_trade",
        "policy_version": "s4-exit-trial:1.0.0",
        "sleeve_contributions": {"S1": 0.05, "S4": 0.01},
    }
    values.update(overrides)
    return SubmittedIntent(**values)


def _order(**overrides) -> BrokerOrderSnapshot:
    values = {
        "order_id": "alpaca-order-1",
        "status": "filled",
        "filled_at": datetime(2026, 8, 25, 15, 7, 4, tzinfo=UTC),
        "filled_quantity": 6.0,
        "filled_avg_price": 105.25,
    }
    values.update(overrides)
    return BrokerOrderSnapshot(**values)


def test_fill_conserva_identita_d0_due_session_e_sleeve_senza_assorbire_residui():
    event = reconcile_entry(
        _intent(),
        _order(),
        sessions=_sessions(),
        observed_at=OBSERVED_AT,
        broker_position_quantity=6.5,
    )

    assert event.status == "FILLED"
    assert event.reason_code == "BROKER_SURPLUS_UNATTRIBUTED"
    assert event.fill_id is not None
    assert event.filled_quantity == 6.0
    assert event.fill_price == 105.25
    assert event.filled_notional == pytest.approx(631.5)
    assert event.details["fill_id_source"] == "derived:alpaca_order_snapshot"
    assert event.first_executable_price == 105.0
    assert event.d0 == date(2026, 8, 25)
    assert event.due_session == date(2026, 8, 27)
    assert event.policy_version == "s4-exit-trial:1.0.0"
    assert event.s1_virtual_quantity == pytest.approx(5.0)
    assert event.s4_virtual_quantity == pytest.approx(1.0)
    assert event.broker_quantity == 6.5
    assert event.unattributed_quantity == pytest.approx(0.5)
    assert event.reconstructible is False


@pytest.mark.parametrize(
    ("broker_status", "filled_qty", "expected_status", "expected_reason"),
    [
        ("partially_filled", 2.0, "PARTIAL_FILL", "PARTIAL_FILL_OPEN"),
        ("rejected", 0.0, "REJECTED", "BROKER_REJECTED"),
        ("canceled", 0.0, "CANCELLED", "BROKER_CANCELLED"),
        ("new", 0.0, "MISSING_FILL", "AWAITING_FILL"),
    ],
)
def test_stati_broker_hanno_reason_code_deterministici(
    broker_status, filled_qty, expected_status, expected_reason
):
    event = reconcile_entry(
        _intent(),
        _order(
            status=broker_status,
            filled_quantity=filled_qty,
            filled_at=OBSERVED_AT if filled_qty else None,
            filled_avg_price=105.25 if filled_qty else None,
        ),
        sessions=_sessions(),
        observed_at=OBSERVED_AT,
        broker_position_quantity=filled_qty,
    )

    assert (event.status, event.reason_code) == (expected_status, expected_reason)


def test_reject_senza_fill_non_dipende_da_prezzo_calendario_o_posizione():
    event = reconcile_entry(
        _intent(first_executable_price=0.0),
        _order(
            status="rejected",
            filled_quantity=0.0,
            filled_at=None,
            filled_avg_price=None,
        ),
        sessions=[],
        observed_at=OBSERVED_AT,
        broker_position_quantity=None,
    )

    assert event.status == "REJECTED"
    assert event.reason_code == "BROKER_REJECTED"
    assert event.reconstructible is True


def test_corporate_action_e_gap_sono_espliciti_e_non_scompaiono_dal_campione():
    corporate_action = reconcile_entry(
        _intent(),
        _order(),
        sessions=_sessions(),
        observed_at=OBSERVED_AT,
        broker_position_quantity=6.0,
        market_event="corporate_action",
    )
    gap = reconcile_entry(
        _intent(),
        _order(),
        sessions=_sessions(),
        observed_at=OBSERVED_AT,
        broker_position_quantity=6.0,
        market_event="gap",
    )

    assert corporate_action.status == "CENSORED"
    assert corporate_action.reason_code == "CORPORATE_ACTION"
    assert corporate_action.reconstructible is False
    assert gap.status == "FILLED"
    assert gap.reason_code == "FILLED_AFTER_GAP"
    assert gap.reconstructible is True


def test_retry_e_restart_producono_un_solo_evento_logico():
    first = reconcile_entry(
        _intent(), _order(), _sessions(), OBSERVED_AT, broker_position_quantity=6.0
    )
    retry = reconcile_entry(
        _intent(), _order(), _sessions(), OBSERVED_AT, broker_position_quantity=6.0
    )

    assert first.event_id == retry.event_id
    assert first.fill_id == retry.fill_id
    assert first == retry


def test_exit_virtuale_riduce_solo_s4_e_non_richiede_un_broker():
    entry = reconcile_entry(
        _intent(), _order(), _sessions(), OBSERVED_AT, broker_position_quantity=6.0
    )

    exit_event = apply_virtual_s4_exit(
        entry,
        quantity=0.4,
        price=110.0,
        observed_at=datetime(2026, 8, 27, 19, 55, tzinfo=UTC),
        reason_code="P1_TIME_DUE",
    )

    assert exit_event.s1_virtual_quantity == pytest.approx(5.0)
    assert exit_event.s4_virtual_quantity == pytest.approx(0.6)
    assert exit_event.virtual_exit_quantity == pytest.approx(0.4)
    assert exit_event.broker_order_id is None


def test_report_validation_window_quantifica_il_residuo_per_motivo():
    rows = [
        reconcile_entry(
            _intent(intent_id=f"00000000-0000-0000-0000-{i:012d}"),
            _order(),
            _sessions(),
            OBSERVED_AT,
            broker_position_quantity=6.0 if i < 95 else None,
        )
        for i in range(100)
    ]

    report = build_reconstruction_report(
        rows,
        window_start=date(2026, 8, 25),
        window_end=date(2026, 8, 25),
    )

    assert report["total"] == 100
    assert report["reconstructible"] == 95
    assert report["coverage"] == pytest.approx(0.95)
    assert report["meets_minimum"] is True
    assert report["residual_by_reason"] == {"BROKER_POSITION_MISSING": 5}


def test_una_posizione_uscita_resta_ricostruibile_se_l_uscita_la_spiega():
    """Il fill d'ingresso non diventa inspiegabile perche' la posizione e' uscita.

    Il reconciler confronta l'ingresso con lo snapshot delle posizioni
    *correnti*: un simbolo venduto non compare piu', e senza l'uscita osservata
    il suo `0.0` e' indistinguibile da un ammanco. Poiche' solo gli intenti
    chiusi portano un `net_pnl`, trattarli come non ricostruibili escludeva per
    costruzione le uniche coppie che il trial puo' misurare.
    """
    event = reconcile_entry(
        _intent(),
        _order(),
        _sessions(),
        OBSERVED_AT,
        broker_position_quantity=0.0,
        broker_exited_quantity=6.0,
    )

    assert event.status == "FILLED"
    assert event.reason_code == "BROKER_FILLED"
    assert event.reconstructible is True
    assert event.unattributed_quantity == pytest.approx(0.0)


def test_un_ammanco_non_spiegato_da_un_uscita_resta_segnalato():
    """La correzione spiega i deficit osservati, non li assorbe tutti."""
    event = reconcile_entry(
        _intent(),
        _order(),
        _sessions(),
        OBSERVED_AT,
        broker_position_quantity=0.0,
        broker_exited_quantity=4.0,
    )

    assert event.reason_code == "BROKER_DEFICIT_UNEXPLAINED"
    assert event.reconstructible is False
    assert event.unattributed_quantity == pytest.approx(-2.0)


def test_un_uscita_parziale_lascia_il_resto_in_posizione():
    event = reconcile_entry(
        _intent(),
        _order(),
        _sessions(),
        OBSERVED_AT,
        broker_position_quantity=2.5,
        broker_exited_quantity=3.5,
    )

    assert event.reason_code == "BROKER_FILLED"
    assert event.reconstructible is True


def test_un_uscita_osservata_non_maschera_un_surplus():
    """Se l'uscita e' avvenuta ma le quote ci sono ancora, qualcuno ne ha aggiunte."""
    event = reconcile_entry(
        _intent(),
        _order(),
        _sessions(),
        OBSERVED_AT,
        broker_position_quantity=6.0,
        broker_exited_quantity=3.0,
    )

    assert event.reason_code == "BROKER_SURPLUS_UNATTRIBUTED"
    assert event.reconstructible is False
    assert event.unattributed_quantity == pytest.approx(3.0)


def test_senza_uscita_osservata_il_comportamento_non_cambia():
    """Il default e' zero: un chiamante che non osserva le uscite vede l'ammanco."""
    event = reconcile_entry(
        _intent(),
        _order(),
        _sessions(),
        OBSERVED_AT,
        broker_position_quantity=0.0,
    )

    assert event.reason_code == "BROKER_DEFICIT_UNEXPLAINED"
    assert event.reconstructible is False


def test_la_posizione_di_un_altro_intento_non_diventa_un_surplus():
    """Lo snapshot delle posizioni e' per simbolo, l'intento e' uno solo.

    Quando il sistema rientra sullo stesso titolo, le azioni del nuovo intento
    comparivano nello snapshot anche per quelli vecchi, gia' usciti per intero:
    risultavano avere piu' azioni di quante ne avessero comprate. Sul live tre
    intenti su otto erano censurati cosi', e il difetto peggiora a ogni
    rientro. E' lo specchio dell'ammanco corretto in #374: la stessa posizione
    per simbolo attribuita a un singolo intento.
    """
    event = reconcile_entry(
        _intent(),
        _order(),
        _sessions(),
        OBSERVED_AT,
        # L'intento e' uscito per intero; le 5.4 azioni presenti ora sul
        # simbolo appartengono a un ingresso successivo.
        broker_position_quantity=5.4,
        shares_symbol_with_other_intents=True,
        broker_exited_quantity=6.0,
    )

    assert event.status == "FILLED"
    assert event.reason_code == "BROKER_FILLED"
    assert event.reconstructible is True
    assert event.unattributed_quantity == pytest.approx(0.0)


def test_un_surplus_vero_su_un_intento_ancora_aperto_resta_segnalato():
    """La correzione limita il credito, non spegne il controllo."""
    event = reconcile_entry(
        _intent(),
        _order(),
        _sessions(),
        OBSERVED_AT,
        broker_position_quantity=9.0,
        broker_exited_quantity=0.0,
    )

    assert event.reason_code == "BROKER_SURPLUS_UNATTRIBUTED"
    assert event.reconstructible is False
    assert event.unattributed_quantity == pytest.approx(3.0)


def test_un_uscita_parziale_accredita_solo_quello_che_resta_atteso():
    """Uscite 3.5 su 6: il broker puo' garantire per le 2.5 che mancano, non oltre."""
    event = reconcile_entry(
        _intent(),
        _order(),
        _sessions(),
        OBSERVED_AT,
        # 8.0 sul simbolo, ma questo intento ne attende solo 2.5: il resto e'
        # di un altro ingresso.
        broker_position_quantity=8.0,
        shares_symbol_with_other_intents=True,
        broker_exited_quantity=3.5,
    )

    assert event.reason_code == "BROKER_FILLED"
    assert event.reconstructible is True
    assert event.unattributed_quantity == pytest.approx(0.0)


def test_un_ammanco_resta_visibile_anche_con_un_altro_intento_sul_simbolo():
    """Il cap non puo' nascondere un deficit: e' il caso pericoloso."""
    event = reconcile_entry(
        _intent(),
        _order(),
        _sessions(),
        OBSERVED_AT,
        broker_position_quantity=1.0,
        shares_symbol_with_other_intents=True,
        broker_exited_quantity=2.0,
    )

    assert event.reason_code == "BROKER_DEFICIT_UNEXPLAINED"
    assert event.reconstructible is False
    assert event.unattributed_quantity == pytest.approx(-3.0)
