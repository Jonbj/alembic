"""primo_avvistamento riallineato in modo deterministico (main rossa 22/09 e 24/09)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from src.analysis.dossier.ledger_validator import (
    normalizza_primo_avvistamento,
    validate_findings,
)

ROOT = Path(__file__).resolve().parents[2]


def _ledger(primo: str, *date_occ: str) -> dict:
    return {
        "schema_version": 1,
        "prossimo_id": 90,
        "findings": [{
            "id": "F-089", "titolo": "x", "tipo": "difetto", "confidenza": "misurata",
            "primo_avvistamento": primo,
            "occorrenze": [
                {"data": d, "costo_usd": None, "nota": "", "fonte": ""} for d in date_occ
            ],
            "costo_cumulato_usd": 0.0, "occorrenze_non_stimate": len(date_occ),
            "stato": "aperto", "issue": None,
        }],
    }


def test_una_rianalisi_di_un_giorno_passato_arretra_il_primo_avvistamento():
    ledger = _ledger("2026-09-22", "2026-09-22", "2026-09-17")
    assert validate_findings(ledger)["errors"]

    modifiche = normalizza_primo_avvistamento(ledger)

    assert modifiche == [{"id": "F-089", "da": "2026-09-22", "a": "2026-09-17"}]
    assert ledger["findings"][0]["primo_avvistamento"] == "2026-09-17"
    assert not validate_findings(ledger)["errors"]


def test_niente_da_fare_se_il_ledger_e_gia_coerente():
    ledger = _ledger("2026-09-17", "2026-09-17", "2026-09-22")
    assert normalizza_primo_avvistamento(ledger) == []
    assert ledger["findings"][0]["primo_avvistamento"] == "2026-09-17"


def test_la_cli_preserva_il_formato_e_non_tocca_un_file_coerente(tmp_path):
    coerente = tmp_path / "ok.json"
    testo = json.dumps(_ledger("2026-09-17", "2026-09-17"), indent=2, ensure_ascii=False) + "\n"
    coerente.write_text(testo)
    mtime = coerente.stat().st_mtime_ns

    subprocess.run([sys.executable, str(ROOT / "scripts/normalizza_primo_avvistamento.py"),
                    str(coerente)], check=True)
    assert coerente.stat().st_mtime_ns == mtime

    rotto = tmp_path / "rotto.json"
    rotto.write_text(json.dumps(_ledger("2026-09-22", "2026-09-17"), indent=2, ensure_ascii=False) + "\n")
    out = subprocess.run([sys.executable, str(ROOT / "scripts/normalizza_primo_avvistamento.py"),
                          str(rotto)], check=True, capture_output=True, text=True).stdout

    assert "F-089: 2026-09-22 -> 2026-09-17" in out
    atteso = json.dumps(_ledger("2026-09-17", "2026-09-17"), indent=2, ensure_ascii=False) + "\n"
    assert rotto.read_text() == atteso


def test_il_cron_forense_normalizza_prima_del_commit():
    sorgente = (ROOT / "scripts/daily_analysis.sh").read_text()
    normalizza = sorgente.index("normalizza_primo_avvistamento.py")
    commit = sorgente.index('GIT_OUTPUT=$("$PROJECT_DIR/scripts/commit_evidence_ledger.sh"')
    assert normalizza < commit


def test_il_ledger_committato_e_coerente():
    ledger = json.loads((ROOT / "docs/evidence/findings.json").read_text())
    assert normalizza_primo_avvistamento(ledger) == []
