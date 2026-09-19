"""#565 / F-076: `economic_pnl.json` e' una serie pre-registrata: i giorni gia'
pubblicati non possono cambiare di valore senza una discontinuita' dichiarata.
Il difetto originale era che ``scrivi()`` riscriveva il file in toto su ogni
run, e il ricalcolo retroattivo (Alpaca ``adjustment=all`` sull'intera finestra)
riallineava indietro i valori dei giorni passati.

L'esito atteso: prima di scrivere il nuovo payload, lo script diff'a i giorni
gia' osservati nel committed contro quelli del nuovo payload e, su QUALSIASI
cambio a un giorno passato, abortisce con SystemExit non-zero e scrive un
sommario del diff su stderr (l'allert lato cron e' del wrapper, non dello
script). Il fallimento e' l'unica risposta onesta, non un merge.
"""

from __future__ import annotations

import json
from contextlib import ExitStack
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

import scripts.economic_pnl_scoreboard as orch


def _canned_giornaliero():
    """Payload minimale: tre giorni, valori costanti."""
    return {
        "2026-08-04": 100.0,
        "2026-08-05": 50.0,
        "2026-08-06": -25.0,
    }


def _canned_payload(giornaliero):
    return {
        "data": "2026-08-06",
        "generato_il": "2026-08-07T10:00:00+00:00",
        "fonte_prezzi": "Alpaca SIP, adjustment=all",
        "fonte_ledger": "docs/evidence/market_daily.jsonl (sola lettura)",
        "pnl_economico": {"cumulato": {}, "giornaliero": giornaliero,
                          "capital_base": 0.0},
        "scoreboard": {},
        "numerosita": {},
        "esclusi": {},
        "missingness": {},
    }


def _patch_io_su_payload(committed_payload):
    """Patch di I/O con un payload committed gia' scritto su disco."""
    def fake_psql(query):
        return []
    return ExitStack()


def test_scrivi_su_primo_commit_silenzioso(tmp_path):
    """Il primo commit (file non esiste) non trova regressioni e scrive."""
    out = tmp_path / "economic_pnl.json"
    payload = _canned_payload(_canned_giornaliero())
    # niente committed, niente diff: scrive
    result = orch.scrivi(
        payload,
        out_path=out,
        giorni_committed=[],
    )
    assert result == out
    assert json.loads(out.read_text()) == payload


def test_scrivi_rifiuta_quando_giorno_passato_cambia_valore(tmp_path):
    """Un giorno gia' pubblicato cambia: abort non-zero, file non toccato."""
    out = tmp_path / "economic_pnl.json"
    committed = _canned_payload(_canned_giornaliero())
    out.write_text(json.dumps(committed))

    nuovo = _canned_payload({
        "2026-08-04": 100.0,   # invariato
        "2026-08-05": 50.0,    # invariato
        "2026-08-06": -30.0,   # <- cambiato: era -25.0, ora -30.0
    })

    with pytest.raises(SystemExit) as exc:
        orch.scrivi(
            nuovo,
            out_path=out,
            giorni_committed=["2026-08-04", "2026-08-05", "2026-08-06"],
        )
    assert exc.value.code != 0
    # il file committed non viene sovrascritto
    assert json.loads(out.read_text()) == committed


def test_scrivi_accetta_nuovo_giorno_a_fine_finestra(tmp_path):
    """Solo l'ultimo giorno e' cambiato? L'aggiunta di un giorno nuovo e' OK."""
    out = tmp_path / "economic_pnl.json"
    committed = _canned_payload({
        "2026-08-04": 100.0,
        "2026-08-05": 50.0,
    })
    out.write_text(json.dumps(committed))

    nuovo = _canned_payload({
        "2026-08-04": 100.0,
        "2026-08-05": 50.0,
        "2026-08-06": -25.0,  # giorno nuovo, non committed
    })
    # i giorni committed sono solo i primi due
    result = orch.scrivi(
        nuovo,
        out_path=out,
        giorni_committed=["2026-08-04", "2026-08-05"],
    )
    assert result == out
    assert json.loads(out.read_text()) == nuovo
