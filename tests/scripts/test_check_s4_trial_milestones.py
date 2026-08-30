"""#298: la sorveglianza delle milestone legge i codici del report, non il testo.

`report_s4_replacement.py` esce con tre codici distinti e stampa **sempre** un
report valido: 0 riconciliato, 1 non riconciliato, 2 nessuna coppia
misurabile. Solo il primo e' un successo, ma nessuno dei tre e' un crash —
mentre il monitor li trattava tutti come tale e moriva prima di guardare le
milestone, proprio nello stato normale della raccolta.
"""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

import scripts.check_s4_trial_milestones as check_script
from scripts.report_s4_replacement import (
    EXIT_NO_COMPARABLE_PAIRS,
    EXIT_NOT_RECONCILED,
    EXIT_RECONCILED,
)


def _report(
    *,
    comparable: int = 0,
    observations: int = 0,
    clusters: int = 0,
    reconciled: bool = True,
    blocking: tuple[str, ...] = (),
    deltas: tuple[float, ...] = (),
) -> dict:
    """Il payload che il report stampa comunque, in ognuno dei tre esiti."""
    return {
        "window_start": "2026-08-25",
        "window_end": "2026-08-30",
        "policy_id": "P1",
        "paired": {"total": 2, "comparable": comparable},
        "paired_records": [
            {"comparable": True, "delta_bps": value} for value in deltas
        ],
        "evaluation": {
            "observations": observations,
            "clusters_observed": clusters,
            "n_cluster": None,
        },
        "reconciliation": {
            "reconciled": reconciled,
            "blocking_reasons": list(blocking),
        },
    }


def _fake_run(payload: dict, returncode: int, stderr: str = ""):
    def run(_argv, **_kwargs):
        return subprocess.CompletedProcess(
            _argv, returncode, stdout=json.dumps(payload), stderr=stderr
        )

    return run


def _invoke(monkeypatch, capsys, payload: dict, returncode: int) -> tuple[int, dict]:
    monkeypatch.setattr(check_script.subprocess, "run", _fake_run(payload, returncode))
    monkeypatch.setattr(
        sys, "argv", ["check", "--start", "2026-08-25", "--end", "2026-08-30"]
    )
    codice = check_script.main()
    return codice, json.loads(capsys.readouterr().out)


def test_una_finestra_senza_coppie_misurabili_non_e_un_fallimento(
    monkeypatch, capsys
):
    """Codice 2 e' lo stato normale della raccolta: il monitor deve riferirlo."""
    codice, payload = _invoke(
        monkeypatch, capsys, _report(), EXIT_NO_COMPARABLE_PAIRS
    )

    assert codice == 0
    assert payload["milestone"] is None
    assert payload["observations"] == 0


def test_una_finestra_riconciliata_propone_n_cluster(monkeypatch, capsys):
    """Con abbastanza osservazioni la milestone scatta: il percorso felice resta."""
    codice, payload = _invoke(
        monkeypatch,
        capsys,
        _report(
            comparable=25,
            observations=25,
            clusters=9,
            deltas=(120.0, -80.0, 40.0, 10.0),
        ),
        EXIT_RECONCILED,
    )

    assert codice == check_script.USCITA_MILESTONE
    assert payload["milestone"] == "N_CLUSTER_PROPONIBILE"
    assert payload["sigma_delta_bps"] > 0
    # L'effetto non esce mai da un interim, nemmeno per errore di copia.
    assert "mean_delta_bps" not in payload


def test_un_report_che_non_riconcilia_non_diventa_una_milestone(
    monkeypatch, capsys
):
    """Codice 1: le due viste si contraddicono, quindi la sigma non e' quella del contratto.

    Derivare `N_cluster` da qui fisserebbe il traguardo del trial su una
    misura che il report stesso dichiara rotta, e consumerebbe l'unica
    ri-stima blinded concessa.
    """
    codice, payload = _invoke(
        monkeypatch,
        capsys,
        _report(
            comparable=25,
            observations=25,
            clusters=9,
            reconciled=False,
            blocking=("UNATTRIBUTED_RESIDUAL",),
            deltas=(120.0, -80.0, 40.0, 10.0),
        ),
        EXIT_NOT_RECONCILED,
    )

    assert codice == check_script.USCITA_NON_RICONCILIATO
    assert payload["milestone"] is None
    assert payload["blocco"] == "REPORT_NON_RICONCILIATO"
    assert payload["blocking_reasons"] == ["UNATTRIBUTED_RESIDUAL"]
    assert "sigma_delta_bps" not in payload


def test_un_report_davvero_fallito_resta_un_fallimento(monkeypatch):
    """Un codice fuori contratto e' un guasto, e va detto con la coda dell'errore."""
    monkeypatch.setattr(
        check_script.subprocess,
        "run",
        _fake_run({}, 3, stderr="ALPACA_API_KEY mancante"),
    )
    monkeypatch.setattr(
        sys, "argv", ["check", "--start", "2026-08-25", "--end", "2026-08-30"]
    )

    with pytest.raises(SystemExit) as errore:
        check_script.main()

    assert "ALPACA_API_KEY mancante" in str(errore.value)


def test_uno_stdout_illeggibile_non_passa_per_un_report(monkeypatch):
    """Codice ammesso ma niente JSON: il report non ha prodotto nulla da leggere."""

    def run(argv, **_kwargs):
        return subprocess.CompletedProcess(
            argv, EXIT_NO_COMPARABLE_PAIRS, stdout="Traceback...", stderr=""
        )

    monkeypatch.setattr(check_script.subprocess, "run", run)
    monkeypatch.setattr(
        sys, "argv", ["check", "--start", "2026-08-25", "--end", "2026-08-30"]
    )

    with pytest.raises(SystemExit):
        check_script.main()
