"""Test del cancello a citazione sul referto di triage."""

import pytest

from src.triage_log.distillazione import distilla
from src.triage_log.referto import SENZA_REPERTI, VALIDO, verifica

RIGHE = [
    "[2026-09-14 08:09:15,466: ERROR/MainProcess] Process 'ForkPoolWorker-1' exited",
    "[2026-09-14 07:01:42,796: WARNING/ForkPoolWorker-1] LLM-1 failed: Ollama timeout",
]
VOCI = distilla(RIGHE)


def _reperto(**sovrascrivi):
    base = {
        "template_id": "T0001",
        "gravita": "ALTA",
        "anomalia": "il worker e' uscito da solo",
        "citazione": RIGHE[0],
        "perche_anomalo": "un'uscita non richiesta interrompe la coda",
        "cosa_controllare": "confrontare con i riavvii del compose",
    }
    base.update(sovrascrivi)
    return base


def test_un_reperto_che_cita_una_riga_vera_del_suo_template_passa():
    esito = verifica([_reperto()], VOCI, RIGHE)
    assert esito.stato == VALIDO
    assert len(esito.reperti) == 1
    assert esito.scartati == ()


def test_una_citazione_inventata_viene_scartata():
    esito = verifica([_reperto(citazione="[2026-09-14 08:09:15,466: ERROR/MainProcess] boom")], VOCI, RIGHE)
    assert esito.reperti == ()
    assert esito.scartati[0]["motivi"] == ["CITAZIONE_NON_TROVATA"]


def test_una_citazione_vera_ma_di_un_altro_template_viene_scartata():
    esito = verifica([_reperto(citazione=RIGHE[1])], VOCI, RIGHE)
    assert esito.reperti == ()
    assert esito.scartati[0]["motivi"] == ["CITAZIONE_FUORI_TEMPLATE"]


def test_un_template_inesistente_viene_scartato():
    esito = verifica([_reperto(template_id="T9999")], VOCI, RIGHE)
    assert esito.reperti == ()
    assert esito.scartati[0]["motivi"] == ["TEMPLATE_INESISTENTE"]


@pytest.mark.parametrize("chiave", ["gravita", "anomalia", "perche_anomalo", "cosa_controllare"])
def test_un_reperto_incompleto_non_e_azionabile(chiave):
    reperto = _reperto()
    del reperto[chiave]
    esito = verifica([reperto], VOCI, RIGHE)
    assert esito.reperti == ()
    assert f"MANCA_{chiave.upper()}" in esito.scartati[0]["motivi"]


def test_nessun_reperto_non_e_un_verdetto_di_sanita():
    esito = verifica([], VOCI, RIGHE)
    assert esito.stato == SENZA_REPERTI
    assert esito.reperti == ()


def test_le_assoluzioni_del_modello_non_attraversano_il_cancello():
    esito = verifica(
        [_reperto(), {"template_id": "T0002", "verificato_e_scartato": "tutto regolare"}],
        VOCI,
        RIGHE,
    )
    assert len(esito.reperti) == 1
    assert "MANCA_ANOMALIA" in esito.scartati[0]["motivi"]


def test_recupera_troncato_taglia_l_elemento_a_meta_e_chiude_i_container():
    from src.triage_log.referto import recupera_troncato

    troncato = '{"reperti": [{"a": 1}, {"b": "meta'
    assert recupera_troncato(troncato) == '{"reperti": [{"a": 1}]}'


def test_recupera_troncato_non_inventa_quando_nessun_elemento_e_completo():
    from src.triage_log.referto import recupera_troncato

    assert recupera_troncato('{"reperti": [{"a": "meta') is None


def test_recupera_troncato_lascia_stare_un_json_gia_valido():
    from src.triage_log.referto import recupera_troncato

    assert recupera_troncato('{"reperti": []}') is None
