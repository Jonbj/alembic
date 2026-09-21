"""#565 / F-076: il dossier di una seduta chiusa non puo' essere sovrascritto
in silenzio. Senza `--force-regenerate` la riesecuzione del dossier per una
data gia' pubblicata deve abortire ad alta voce e produrre un file accanto
(`<date>.regen-<ts>.json`) con un sommario del diff, non sovrascrivere il
committed.

La sovrascrittura silenziosa era esattamente il difetto che ha prodotto il
commit 88bfb05 sul dossier 2026-09-04, dove il rewrite era invisibile in
`git log` perche' portava lo stesso messaggio di e5512c9.
"""

from __future__ import annotations

import json
import re
from datetime import date

import pytest

import scripts.alpha_miner_dossier as dossier


def _payload(giorno: date) -> dict:
    return {"data": giorno.isoformat(), "schema_version": "3.1", "x": 1}


def test_scrivi_rifiuta_overwrite_su_dossier_esistente(tmp_path):
    """Senza --force-regenerate il dossier committato non viene sovrascritto."""
    out_dir = tmp_path / "dossier"
    out_dir.mkdir(parents=True, exist_ok=True)
    esistente = out_dir / "2026-09-04.json"
    originale = _payload(date(2026, 9, 4))
    esistente.write_text(json.dumps(originale))

    nuovo = _payload(date(2026, 9, 4))
    nuovo["x"] = 999  # payload diverso

    with pytest.raises(SystemExit) as exc:
        dossier.scrivi(nuovo, dossier_dir=out_dir)
    assert exc.value.code != 0
    # il file originale non viene toccato
    assert json.loads(esistente.read_text())["x"] == 1


def test_scrivi_con_force_regenerate_produce_file_accanto_e_non_tocca_originale(tmp_path):
    """Con --force-regenerate il nuovo file e' scritto accanto, mai in place."""
    out_dir = tmp_path / "dossier"
    out_dir.mkdir(parents=True, exist_ok=True)
    esistente = out_dir / "2026-09-04.json"
    esistente.write_text(json.dumps(_payload(date(2026, 9, 4))))

    nuovo = _payload(date(2026, 9, 4))
    nuovo["x"] = 999

    out = dossier.scrivi(
        nuovo, dossier_dir=out_dir, force_regenerate=True
    )
    # L'originale e' ancora il payload di prima
    assert json.loads(esistente.read_text())["x"] == 1
    # Il nuovo file ha il pattern .regen-<ts>.json e contiene il nuovo payload
    assert re.match(r"2026-09-04\.regen-\d{8}T\d{6}\.json$", out.name)
    assert json.loads(out.read_text())["x"] == 999


def test_scrivi_prima_scrittura_non_richiede_flag(tmp_path):
    """Una data che non esiste ancora viene sempre scritta normalmente."""
    out_dir = tmp_path / "dossier"
    out_dir.mkdir(parents=True, exist_ok=True)

    nuovo = _payload(date(2026, 9, 10))
    out = dossier.scrivi(nuovo, dossier_dir=out_dir)
    assert out.name == "2026-09-10.json"
    assert json.loads(out.read_text())["x"] == 1
