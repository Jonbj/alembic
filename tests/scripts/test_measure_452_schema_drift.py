"""Test per l'orchestratore di scripts/measure_452_schema_drift.py (#452) —
verifica il cablaggio DB -> rilevatore -> JSON con una connessione Postgres
finta, senza toccare il database vero."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import scripts.measure_452_schema_drift as msd


def test_esegui_e_scrivi_evidenza(tmp_path, monkeypatch) -> None:
    righe = [
        ("glm-5.2:cloud", "direct", "earnings", ["rumor"], None),
        ("glm-5.2:cloud", "supplier_readthrough", None, [], None),
        ("gpt-oss:20b-cloud", None, "earnings|guidance", None, None),
    ]

    cur = MagicMock()
    cur.fetchall.return_value = righe
    cur.__enter__ = MagicMock(return_value=cur)
    cur.__exit__ = MagicMock(return_value=False)

    conn = MagicMock()
    conn.cursor.return_value = cur
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=False)

    monkeypatch.setattr(msd, "_connetti", lambda: conn)
    percorso_output = tmp_path / "ollama_schema_drift_452.json"
    monkeypatch.setattr(msd, "_PERCORSO_EVIDENZA", percorso_output)
    monkeypatch.setattr("sys.argv", ["measure_452_schema_drift.py"])

    msd.main()

    dati = json.loads(percorso_output.read_text())
    assert dati["sintesi"]["n_campione"] == 3
    assert dati["sintesi"]["riga_in_deriva"]["n"] == 2
    assert "glm-5.2:cloud" in dati["per_modello"]
    assert "gpt-oss:20b-cloud" in dati["per_modello"]
    assert dati["per_modello"]["glm-5.2:cloud"]["directness"]["n_invalidi"] == 1
