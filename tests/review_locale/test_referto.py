"""Validazione del referto del modello locale (spec 2026-09-03).

Il test che conta e' `test_verificato_e_scartato_non_esce_mai`: protegge il
principio dell'intera spec — le assoluzioni del modello non raggiungono GitHub.
"""

import json

from src.review_locale.referto import prepara


def _referto(rilievi, con_assoluzioni=True) -> str:
    corpo = {
        "rilievi": rilievi,
        "criteri_issue": [{"criterio": "c", "esito": "SODDISFATTO", "perche": "p"}],
        "informazioni_mancanti": [],
        "confidenza": 0.8,
    }
    if con_assoluzioni:
        corpo["verificato_e_scartato"] = [
            "La SQL esclude correttamente SKIP_THRESHOLD",
            "La partizione actionability e' completa",
        ]
    return json.dumps(corpo)


_RILIEVO = {
    "gravita": "ALTA",
    "categoria": "classificazione_sbagliata",
    "posizione": "src/x.py:10",
    "difetto": "d",
    "scenario_di_fallimento": "s",
    "mascherato_da": None,
}


def test_verificato_e_scartato_non_esce_mai():
    """Le assoluzioni del modello non compaiono in nulla di pubblicabile.

    Su PR #472 il modello ha prodotto 11 voci in `verificato_e_scartato`, di cui
    almeno 2 dimostrabilmente false, e false esattamente sui due punti dove i
    difetti erano reali. Pubblicarle equivarrebbe a pubblicare un via libera
    sbagliato.
    """
    esito = prepara(_referto([_RILIEVO]))

    assert esito.stato == "PUBBLICABILE"
    serializzato = json.dumps(esito.rilievi)
    assert "verificato_e_scartato" not in serializzato
    assert "correttamente" not in serializzato
    assert "completa" not in serializzato


def test_rilievi_vuoti_non_sono_pubblicabili():
    esito = prepara(_referto([]))

    assert esito.stato == "SENZA_RILIEVI"
    assert esito.rilievi == ()


def test_json_invalido_non_e_pubblicabile():
    esito = prepara("{questo non e' JSON")

    assert esito.stato == "NON_VALIDO"
    assert esito.causa is not None
    assert esito.rilievi == ()


def test_rilievi_non_lista_e_trattato_come_non_valido():
    esito = prepara(json.dumps({"rilievi": "due"}))

    assert esito.stato == "NON_VALIDO"


def test_rilievo_senza_scenario_e_scartato():
    """Un rilievo senza scenario concreto non e' azionabile: non si pubblica.

    Lo schema del prompt chiede uno scenario di fallimento per ogni rilievo. Un
    rilievo che non lo porta e' una preoccupazione generica.
    """
    incompleto = dict(_RILIEVO)
    del incompleto["scenario_di_fallimento"]

    esito = prepara(_referto([incompleto]))

    assert esito.stato == "SENZA_RILIEVI"


def test_rilievi_validi_e_invalidi_insieme_tiene_solo_i_validi():
    incompleto = dict(_RILIEVO)
    del incompleto["scenario_di_fallimento"]

    esito = prepara(_referto([_RILIEVO, incompleto]))

    assert esito.stato == "PUBBLICABILE"
    assert len(esito.rilievi) == 1


def test_referto_senza_assoluzioni_resta_valido():
    esito = prepara(_referto([_RILIEVO], con_assoluzioni=False))

    assert esito.stato == "PUBBLICABILE"
    assert len(esito.rilievi) == 1
