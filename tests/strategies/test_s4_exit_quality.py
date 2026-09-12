"""#299: la qualita' dell'uscita dal path di prezzo, prima degli esiti forward.

Tutto qui gira su barre sintetiche: il valutatore va costruito e testato prima
di leggere qualunque esito reale. Le definizioni sono quelle operazionali di
`docs/s4-exit-research-2026-08-14/consolidato_exit.md` §8.3 (false-exit rate,
recovery entro l'orizzonte, giveback da MFE) e la regola e' quella di
`live_tp_check`: **ignoto non e' zero** — un dato mancante resta `None` e
rimane fuori dalle medie, mai contato come un favorevole.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from src.strategies.s4.exit_quality import (
    PairedExitPath,
    exit_quality_from_path,
)

ENTRY_AT = datetime(2026, 8, 25, 15, 50, tzinfo=UTC)
BASELINE_EXIT_AT = datetime(2026, 8, 25, 15, 55, tzinfo=UTC)
CHALLENGER_EXIT_AT = datetime(2026, 8, 26, 13, 33, tzinfo=UTC)


def _bars() -> list[tuple[datetime, float, float]]:
    """Due sedute: chiusura a 100, riapertura a 102, uscita a 104.

    Le barre interne sono a un minuto: nessun gap dentro la seduta conta come
    overnight, solo il salto fra le due sedute.
    """
    sessione_a = [
        (ENTRY_AT + timedelta(minutes=minute), 99.5 + minute * 0.05, 99.5 + minute * 0.05)
        for minute in range(1, 11)
    ]
    sessione_b = [
        (datetime(2026, 8, 26, 13, 31, tzinfo=UTC) + timedelta(minutes=minute), 102.0 + minute, 102.0 + minute)
        for minute in range(0, 3)
    ]
    # Il massimo favorevole: la seduta B tocca 104 di close ma 110 di high
    sessione_b[1] = (sessione_b[1][0], 110.0, 103.0)
    return sessione_a + sessione_b


def _path(**overrides) -> PairedExitPath:
    values = {
        "intent_id": "intent-1",
        "entry_at": ENTRY_AT,
        "entry_price": 99.0,
        "quantity": 10.0,
        "baseline_exit_at": BASELINE_EXIT_AT,
        "baseline_exit_price": 98.0,
        "challenger_exit_at": CHALLENGER_EXIT_AT,
        "challenger_exit_price": 104.0,
    }
    values.update(overrides)
    return PairedExitPath(**values)


def test_la_componente_overnight_e_il_salto_fra_le_sedute():
    quality = exit_quality_from_path(_path(), _bars())

    # Gap overnight: da 100 (ultima seduta A) a 102 (prima seduta B), per 10
    # azioni. I movimenti dentro la seduta restano intraday: la decomposizione
    # somma esattamente al pnl della gamba, (104-99)*10 = 50.
    assert quality.overnight_pnl_usd == pytest.approx(20.0)


def test_un_uscita_della_baseline_recuperata_all_orizzonte_e_falsa():
    """P0 vende a 98, all'orizzonte (uscita P1) il prezzo e' 104: tenere sarebbe
    stato meglio, e il prezzo e' anche tornato sopra l'ingresso."""
    quality = exit_quality_from_path(_path(), _bars())

    assert quality.false_exit is True
    assert quality.recovered_within_horizon is True


def test_un_uscita_della_baseline_che_avrebbe_perso_piu_non_e_falsa():
    path = _path(challenger_exit_price=97.5)
    quality = exit_quality_from_path(path, _bars())

    assert quality.false_exit is False
    # La recovery ha senso solo per un'uscita falsa: altrove non si applica
    assert quality.recovered_within_horizon is None


def test_una_baseline_che_tiene_fino_all_orizzonte_non_ha_un_uscita_falsa():
    path = _path(
        baseline_exit_at=CHALLENGER_EXIT_AT, baseline_exit_price=104.0
    )
    quality = exit_quality_from_path(path, _bars())

    assert quality.false_exit is False


def test_il_giveback_misura_la_restituzione_dal_mfe_della_challenger():
    """Il massimo favorevole toccato e' 110: l'uscita a 104 restituisce
    (110-104)/99 in bps dell'ingresso."""
    quality = exit_quality_from_path(_path(), _bars())

    assert quality.giveback_from_mfe_bps == pytest.approx(606.060606, rel=1e-6)


def test_senza_barre_la_qualita_e_ignota_non_zero():
    """Nessun path di prezzo: le metriche che lo richiedono restano ignote. La
    falsita' dell'uscita invece si vede dai soli fill — un None conteggiato
    come favore abbasserebbe il false-exit rate, che e' il numero da vigilare."""
    quality = exit_quality_from_path(_path(), ())

    assert quality.overnight_pnl_usd is None
    # P0 vende a 98, P1 chiude a 104: i fill bastano a dire che era falsa
    assert quality.false_exit is True
    assert quality.recovered_within_horizon is None
    assert quality.giveback_from_mfe_bps is None


def test_una_gamba_aperta_non_ha_neanche_l_orizzonte():
    """Il tempo di P1 non e' scaduto: l'orizzonte non esiste ancora, quindi
    niente componente overnight ne' giveback — ma la gamba baseline chiusa
    resta misurabile sul false exit."""
    path = _path(challenger_exit_at=None, challenger_exit_price=None)
    quality = exit_quality_from_path(path, _bars())

    assert quality.overnight_pnl_usd is None
    assert quality.giveback_from_mfe_bps is None
    assert quality.false_exit is None


def test_un_ingresso_senza_fill_non_inventa_un_decomposizione():
    path = _path(entry_at=None, entry_price=None)
    quality = exit_quality_from_path(path, _bars())

    assert quality.overnight_pnl_usd is None
    assert quality.recovered_within_horizon is None
    assert quality.giveback_from_mfe_bps is None


def test_barre_fuori_finestra_non_inquina_no_il_mfe():
    """Il massimo dopo l'uscita della challenger non e' un giveback: la
    finestra si chiude all'uscita."""
    dopo = [
        (CHALLENGER_EXIT_AT + timedelta(minutes=minute), 200.0, 200.0)
        for minute in range(1, 4)
    ]
    quality = exit_quality_from_path(_path(), _bars() + dopo)

    assert quality.giveback_from_mfe_bps == pytest.approx(606.060606, rel=1e-6)


def test_la_recovery_guarda_dopo_l_uscita_della_baseline():
    """Il prezzo torna sopra l'ingresso solo dopo l'uscita di P0: e' recovery
    entro l'orizzonte, non un favore che l'uscita aveva gia' in tasca."""
    bars = _bars()[:4] + [
        (BASELINE_EXIT_AT + timedelta(minutes=1), 99.5, 99.5),
        (CHALLENGER_EXIT_AT - timedelta(minutes=1), 99.5, 99.5),
    ]
    quality = exit_quality_from_path(_path(), bars)

    assert quality.recovered_within_horizon is True