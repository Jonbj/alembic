"""Riconciliazione deterministica fra dossier e attivita' narrata nel report."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.analysis.dossier.report import (
    ReportReconciliationError,
    riconcilia_attivita_book,
    verifica_riconciliazione,
)


def _dossier() -> dict:
    return {
        "ingressi": [
            {
                "symbol": "NVDA",
                "strategia": "S4",
                "ora_utc": "15:22",
                "entry_price": 217.238836,
                "qty": 8.595976799,
                "entry_percentile": 0.3759133333,
                "denominatore_degenere": False,
            },
            {
                "symbol": "AVGO",
                "strategia": "S4",
                "ora_utc": "17:07",
                "entry_price": 363.13,
                "qty": 5.136011896,
                "entry_percentile": 0.1806813282,
                "denominatore_degenere": True,
            },
        ],
        "chiusure": [
            {
                "symbol": "HOOD",
                "strategia": "S4",
                "exit_price": 95.28,
                "qty": 18.648486695,
                "pnl_net": -60.3192855,
                "exit_reason": "portfolio_sell",
            },
            {
                "symbol": "NVDA",
                "strategia": "S4",
                "exit_price": 217.16302,
                "qty": 8.595976799,
                "pnl_net": -1.0328763,
                "exit_reason": "portfolio_sell",
            },
        ],
    }


def test_riconciliazione_rende_ogni_ingresso_e_uscita_del_dossier():
    report = """# Report\n\n## 4. Titoli catturati: esito\n\n**Tradato oggi:** WMT.\n\n## 5. Pattern osservato\n"""

    riconciliato = riconcilia_attivita_book(report, _dossier())

    assert verifica_riconciliazione(riconciliato, _dossier())
    assert "| IN | NVDA | S4 | 15:22 |" in riconciliato
    assert "| IN | AVGO | S4 | 17:07 |" in riconciliato
    assert "| OUT | HOOD | S4 | — |" in riconciliato
    assert "| OUT | NVDA | S4 | — |" in riconciliato
    assert "denominatore intraday degenere: quota non interpretabile" in riconciliato
    assert "**Tradato oggi:** WMT." in riconciliato


def test_riconciliazione_e_idempotente():
    report = "# Report\n\n## 4. Esito\n\nAnnotazione.\n\n## 5. Pattern\n"

    prima = riconcilia_attivita_book(report, _dossier())
    seconda = riconcilia_attivita_book(prima, _dossier())

    assert seconda == prima


def test_report_senza_sezione_quattro_fallisce_chiaramente():
    with pytest.raises(ReportReconciliationError, match="sezione 4"):
        riconcilia_attivita_book("# Report\n\n## 5. Pattern\n", _dossier())


def test_report_2026_08_20_riconcilia_uno_a_uno_col_dossier():
    root = Path(__file__).resolve().parents[2]
    dossier = json.loads(
        (root / "docs/evidence/dossier/2026-08-20.json").read_text()
    )
    report = (root / "docs/ALPHA_MISS_REPORT_2026-08-20.md").read_text()

    assert verifica_riconciliazione(report, dossier)
