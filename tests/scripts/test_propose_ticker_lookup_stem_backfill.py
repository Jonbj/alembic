"""#566 — backfill proposal CLI: il file CSV e' l'artefatto di review.

Lo script ``scripts/propose_ticker_lookup_stem_backfill.py`` legge il DB
live e scrive un CSV con i bucket (safe / short / collision / noop). Il
test qui sotto verifica la pipeline offline, senza dipendere dal DB:
mocka ``_fetch_rows`` e controlla che il CSV prodotto sia coerente con la
funzione pura ``propose_stem_backfill``.

Il test non esegue la lettura dal DB perche' quella parte richiede Docker
ed e' gia' coperta indirettamente dall'esecuzione manuale dell'operatore
durante la review del CSV. La funzione pura, invece, e' il contratto.
"""

from __future__ import annotations

import csv
import importlib
import sys
from pathlib import Path

import pytest

PROJECT_DIR = Path(__file__).resolve().parent.parent.parent
SCRIPTS_DIR = PROJECT_DIR / "scripts"


@pytest.fixture
def cli_module(monkeypatch: pytest.MonkeyPatch):
    """Importa lo script CLI con un _fetch_rows finto."""
    sys.path.insert(0, str(SCRIPTS_DIR))
    monkeypatch.setattr(
        "scripts.propose_ticker_lookup_stem_backfill._fetch_rows",
        lambda: [
            {"ticker": "ORCL", "company_name": "Oracle Corporation", "aliases": ["Oracle Corp"]},
            {"ticker": "AAPL", "company_name": "Apple Inc", "aliases": ["Apple Computer"]},
            {"ticker": "F", "company_name": "Ford Motor Company", "aliases": ["Ford Motor Co"]},
            {"ticker": "MSFT", "company_name": "Microsoft Corporation", "aliases": ["Microsoft"]},
            {"ticker": "MS", "company_name": "Morgan Stanley", "aliases": []},
        ],
    )
    return importlib.import_module("scripts.propose_ticker_lookup_stem_backfill")


def test_cli_scrive_un_csv_con_i_sei_campi_per_riga(cli_module, tmp_path: Path) -> None:
    out = tmp_path / "proposal.csv"
    rc = cli_module.main(["--out", str(out)])
    assert rc == 0
    assert out.exists()

    # #566: line endings LF, non CRLF. Il default di csv.DictWriter su
    # molte piattaforme e' "\r\n", che i linter segnalano come trailing
    # whitespace e che rompe il diff del CSV. Il file e' un artefatto di
    # review: deve poter diff-are pulito.
    raw = out.read_bytes()
    assert b"\r\n" not in raw, "CSV deve usare LF, non CRLF"
    assert raw.endswith(b"\n"), "CSV deve terminare con newline"

    with out.open() as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        assert reader.fieldnames == [
            "ticker", "company_name", "current_aliases",
            "proposed_alias", "bucket", "reason",
        ]
    by_ticker = {row["ticker"]: row for row in rows}
    assert set(by_ticker) == {"ORCL", "AAPL", "F", "MSFT", "MS"}
    # current_aliases e' serializzato con '|' come separatore (CSV-safe)
    assert by_ticker["ORCL"]["current_aliases"] == "Oracle Corp"
    assert by_ticker["F"]["current_aliases"] == "Ford Motor Co"
    # proposed_alias vuoto per i bucket noop
    assert by_ticker["MSFT"]["proposed_alias"] == ""
    # bucket corretti
    assert by_ticker["ORCL"]["bucket"] == "safe"
    assert by_ticker["AAPL"]["bucket"] == "collision"
    assert by_ticker["F"]["bucket"] == "short"
    assert by_ticker["MSFT"]["bucket"] == "noop"
    assert by_ticker["MS"]["bucket"] == "noop"


def test_parse_pg_array_gestisce_array_vuoto_e_quote(cli_module) -> None:
    assert cli_module._parse_pg_array("{}") == []
    assert cli_module._parse_pg_array("") == []
    assert cli_module._parse_pg_array("Oracle Corp") == ["Oracle Corp"]
    assert cli_module._parse_pg_array("{Oracle Corp,Oracle}") == [
        "Oracle Corp",
        "Oracle",
    ]
    assert cli_module._parse_pg_array(
        '{"Ford Motor Co","General Motors"}'
    ) == ["Ford Motor Co", "General Motors"]