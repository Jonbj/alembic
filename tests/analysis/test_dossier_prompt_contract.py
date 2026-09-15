"""Contratto prompt<->dossier versionato (#287, P1).

Il prompt del cron alpha-miss e lo schema del dossier devono dichiarare una
versione e la combinazione deve essere verificabile meccanicamente: una
sessione lanciata contro un dossier incompatibile produce report e ledger che
nessuno puo' difendere.
"""

from src.analysis.dossier.prompt_contract import (
    PROMPT_VERSION,
    SCHEMA_DOSSIER_COMPATIBILI,
    verifica_compatibilita_schema,
)


def _dossier(schema_version: str) -> dict:
    return {"schema_version": schema_version, "data": "2026-09-15"}


def test_lo_schema_compatibile_passa_e_riporta_le_versioni():
    esito = verifica_compatibilita_schema(_dossier("3.1"))

    assert esito["ok"] is True
    assert esito["errors"] == []
    assert esito["prompt_version"] == PROMPT_VERSION
    assert esito["schema_version"] == "3.1"


def test_schema_sconosciuto_fail_closed_con_motivo_leggibile():
    esito = verifica_compatibilita_schema(_dossier("9.9"))

    assert esito["ok"] is False
    assert any("9.9" in e for e in esito["errors"])
    assert any(PROMPT_VERSION in e for e in esito["errors"])


def test_schema_assente_fail_closed_non_silenzioso():
    esito = verifica_compatibilita_schema({})

    assert esito["ok"] is False
    assert esito["errors"]


def test_le_versioni_compatibili_sono_dichiarate_e_coprono_lo_schema_corrente():
    # Il dossier di produzione oggi e' 3.1: se DOSSIER_SCHEMA_VERSION sale e
    # questa lista non viene aggiornata nella stessa PR, il cron deve fermarsi,
    # non improvvisare.
    from scripts.alpha_miner_dossier import DOSSIER_SCHEMA_VERSION

    assert DOSSIER_SCHEMA_VERSION in SCHEMA_DOSSIER_COMPATIBILI