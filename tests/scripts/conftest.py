# tests/scripts/conftest.py
"""Isolamento del filesystem di evidenza per i test degli script di dossier.

`alpha_miner_dossier` scrive e (dal #507, per lo streak del calendario earnings)
legge i dossier in `docs/evidence/dossier/`. I test non devono toccare quella
directory: i file sono la serie pubblicata dell'osservazione #171. Il redirect
vale per tutto il package, cosi' un nuovo test non puo' dimenticarselo.
"""

from pathlib import Path

import pytest

import scripts.alpha_miner_dossier as dossier


@pytest.fixture(autouse=True)
def _dossier_out_dir_isolato(tmp_path: Path):
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(dossier, "OUT_DIR", tmp_path / "dossier")
        yield