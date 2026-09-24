"""Scaricatore dell'archivio news 2024-2025 (#610).

Le proprieta' che la DoD della issue richiede e che qui sono bloccate:
idempotenza, ripartibilita', e soprattutto il **fail-closed sul fetch** — un
fetch fallito non deve produrre artefatto, perche' una finestra troncata
auto-seleziona il campione invece di degradarlo.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest
import yaml

from scripts import fetch_news_archive_610 as scaricatore


def _config(tmp_path: Path, simboli: list[str] | None = None) -> Path:
    percorso = tmp_path / "trading.yaml"
    percorso.write_text(yaml.safe_dump({"symbols": {"watchlist": simboli or ["AAPL", "MSFT"]}}))
    return percorso


def _articolo(identificativo: int, mese: str = "2024-01") -> dict:
    return {
        "id": identificativo,
        "headline": f"Titolo {identificativo}",
        "summary": "s",
        "content": "<p>c</p>",
        "created_at": f"{mese}-15T14:00:00Z",
        "symbols": ["AAPL"],
        "url": f"https://example.com/{identificativo}",
    }


class _ConnettoreFinto:
    """Restituisce articoli per finestra; una finestra puo' sollevare."""

    def __init__(self, per_mese: dict[str, list[dict] | Exception]) -> None:
        self.per_mese = per_mese
        self.finestre_viste: list[str] = []

    async def fetch_historical_raw(self, da: datetime, a: datetime):
        etichetta = f"{da.year:04d}-{da.month:02d}"
        self.finestre_viste.append(etichetta)
        esito = self.per_mese.get(etichetta, [])
        if isinstance(esito, Exception):
            raise esito
        for articolo in esito:
            yield articolo


@pytest.fixture(autouse=True)
def _credenziali(monkeypatch):
    monkeypatch.setenv("ALPACA_API_KEY", "k")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "s")


@pytest.fixture
def _finestra_breve(monkeypatch):
    """Riduce la finestra congelata a tre mesi: i test esercitano le regole."""
    monkeypatch.setattr(scaricatore, "INIZIO", "2024-01-01")
    monkeypatch.setattr(scaricatore, "FINE", "2024-03-31")
    monkeypatch.setattr(scaricatore, "fine_fetch", lambda: "2024-03-31")


class TestFinestre:
    def test_i_mesi_coprono_la_finestra_estremi_inclusi(self) -> None:
        out = scaricatore.mesi("2024-11-01", "2025-02-28")
        assert [etichetta for etichetta, _, _ in out] == [
            "2024-11", "2024-12", "2025-01", "2025-02",
        ]

    def test_ogni_mese_finisce_dove_comincia_il_successivo(self) -> None:
        out = scaricatore.mesi("2024-01-01", "2024-03-31")
        for (_, _, fine), (_, inizio_dopo, _) in zip(out, out[1:]):
            assert fine == inizio_dopo


class TestFailClosed:
    """La proprieta' centrale: un fetch fallito non produce artefatto."""

    @pytest.mark.asyncio
    async def test_un_fetch_fallito_aborta_e_non_scrive_il_mese(
        self, tmp_path, monkeypatch, _finestra_breve
    ) -> None:
        finto = _ConnettoreFinto({
            "2024-01": [_articolo(1)],
            "2024-02": RuntimeError("subscription does not permit querying recent SIP data"),
            "2024-03": [_articolo(3, "2024-03")],
        })
        monkeypatch.setattr(scaricatore, "AlpacaNewsConnector", lambda **_: finto)

        codice = await scaricatore.esegui(tmp_path, _config(tmp_path), forza=False)

        assert codice == 1
        assert (tmp_path / "news_2024-01.jsonl").exists()   # il mese buono resta
        assert not (tmp_path / "news_2024-02.jsonl").exists()
        # e soprattutto: NON prosegue sui mesi successivi
        assert not (tmp_path / "news_2024-03.jsonl").exists()
        assert "2024-03" not in finto.finestre_viste
        manifest = json.loads((tmp_path / "manifest.json").read_text())
        assert "2024-02" not in manifest["mesi"]

    @pytest.mark.asyncio
    async def test_nessun_file_parziale_sopravvive_a_un_abort(
        self, tmp_path, monkeypatch, _finestra_breve
    ) -> None:
        finto = _ConnettoreFinto({"2024-01": RuntimeError("HTTP 422")})
        monkeypatch.setattr(scaricatore, "AlpacaNewsConnector", lambda **_: finto)

        await scaricatore.esegui(tmp_path, _config(tmp_path), forza=False)

        assert list(tmp_path.glob("*.part")) == []
        assert list(tmp_path.glob("*.jsonl")) == []

    @pytest.mark.asyncio
    async def test_un_articolo_senza_id_aborta(
        self, tmp_path, monkeypatch, _finestra_breve
    ) -> None:
        """Senza id l'articolo non e' deduplicabile: il file non sarebbe
        riproducibile fra due run, e un archivio non riproducibile non e'
        evidenza."""
        senza_id = {k: v for k, v in _articolo(1).items() if k != "id"}
        finto = _ConnettoreFinto({"2024-01": [senza_id]})
        monkeypatch.setattr(scaricatore, "AlpacaNewsConnector", lambda **_: finto)

        codice = await scaricatore.esegui(tmp_path, _config(tmp_path), forza=False)

        assert codice == 1
        assert list(tmp_path.glob("*.jsonl")) == []


class TestIdempotenzaERipartenza:
    @pytest.mark.asyncio
    async def test_rieseguire_non_riscarica_i_mesi_gia_a_terra(
        self, tmp_path, monkeypatch, _finestra_breve
    ) -> None:
        dati = {
            "2024-01": [_articolo(1)],
            "2024-02": [_articolo(2, "2024-02")],
            "2024-03": [_articolo(3, "2024-03")],
        }
        primo = _ConnettoreFinto(dati)
        monkeypatch.setattr(scaricatore, "AlpacaNewsConnector", lambda **_: primo)
        assert await scaricatore.esegui(tmp_path, _config(tmp_path), forza=False) == 0

        secondo = _ConnettoreFinto(dati)
        monkeypatch.setattr(scaricatore, "AlpacaNewsConnector", lambda **_: secondo)
        assert await scaricatore.esegui(tmp_path, _config(tmp_path), forza=False) == 0

        assert secondo.finestre_viste == []  # nessuna richiesta di rete la seconda volta

    @pytest.mark.asyncio
    async def test_riprende_dal_mese_mancante_dopo_un_abort(
        self, tmp_path, monkeypatch, _finestra_breve
    ) -> None:
        rotto = _ConnettoreFinto({
            "2024-01": [_articolo(1)],
            "2024-02": RuntimeError("HTTP 500"),
        })
        monkeypatch.setattr(scaricatore, "AlpacaNewsConnector", lambda **_: rotto)
        assert await scaricatore.esegui(tmp_path, _config(tmp_path), forza=False) == 1

        riparato = _ConnettoreFinto({
            "2024-02": [_articolo(2, "2024-02")],
            "2024-03": [_articolo(3, "2024-03")],
        })
        monkeypatch.setattr(scaricatore, "AlpacaNewsConnector", lambda **_: riparato)
        assert await scaricatore.esegui(tmp_path, _config(tmp_path), forza=False) == 0

        # riparte da 02, non riscarica 01
        assert riparato.finestre_viste == ["2024-02", "2024-03"]
        manifest = json.loads((tmp_path / "manifest.json").read_text())
        assert sorted(manifest["mesi"]) == ["2024-01", "2024-02", "2024-03"]
        assert manifest["totale_articoli"] == 3

    @pytest.mark.asyncio
    async def test_la_pagina_ripetuta_non_duplica_righe(
        self, tmp_path, monkeypatch, _finestra_breve
    ) -> None:
        finto = _ConnettoreFinto({"2024-01": [_articolo(1), _articolo(1), _articolo(2)]})
        monkeypatch.setattr(scaricatore, "AlpacaNewsConnector", lambda **_: finto)

        await scaricatore.esegui(tmp_path, _config(tmp_path), forza=False)

        righe = (tmp_path / "news_2024-01.jsonl").read_text().strip().splitlines()
        assert len(righe) == 2
        assert sorted(json.loads(r)["id"] for r in righe) == [1, 2]


class TestArchivioGrezzo:
    @pytest.mark.asyncio
    async def test_gli_articoli_sono_scritti_come_arrivano(
        self, tmp_path, monkeypatch, _finestra_breve
    ) -> None:
        """L'archivio non e' parsato: i campi che le misure usano restano
        intatti, compresi gli articoli senza corpo che il path live scarta."""
        senza_corpo = dict(_articolo(9), summary="", content="", symbols=["AAPL", "MSFT"])
        finto = _ConnettoreFinto({"2024-01": [senza_corpo]})
        monkeypatch.setattr(scaricatore, "AlpacaNewsConnector", lambda **_: finto)

        await scaricatore.esegui(tmp_path, _config(tmp_path), forza=False)

        riga = json.loads((tmp_path / "news_2024-01.jsonl").read_text().strip())
        assert riga["symbols"] == ["AAPL", "MSFT"]
        assert riga["summary"] == "" and riga["content"] == ""
        assert riga["created_at"] == "2024-01-15T14:00:00Z"

    @pytest.mark.asyncio
    async def test_il_manifest_registra_universo_e_checksum(
        self, tmp_path, monkeypatch, _finestra_breve
    ) -> None:
        finto = _ConnettoreFinto({"2024-01": [_articolo(1)]})
        monkeypatch.setattr(scaricatore, "AlpacaNewsConnector", lambda **_: finto)

        await scaricatore.esegui(tmp_path, _config(tmp_path, ["AAPL", "MSFT", "NVDA"]), forza=False)

        manifest = json.loads((tmp_path / "manifest.json").read_text())
        assert manifest["universo"]["n"] == 3
        assert manifest["finestra"] == {"inizio": scaricatore.INIZIO, "fine": scaricatore.FINE}
        atteso = scaricatore.sha256_file(tmp_path / "news_2024-01.jsonl")
        assert manifest["mesi"]["2024-01"]["sha256"] == atteso


def test_la_finestra_congelata_e_quella_preregistrata() -> None:
    """2024-2025, col 2026 fuori: e' la finestra live su cui abbiamo gia'
    formato un'opinione, e rientrarci significherebbe misurarla due volte."""
    assert scaricatore.INIZIO == "2024-01-01"
    assert scaricatore.FINE == "2025-12-31"


class TestFinestraApiControPopolazione:
    """`start`/`end` dell'API filtrano su `updated_at`, non su `created_at`.

    Misurato contro l'API vera il 2026-09-17: su 2024-03-01..08, 14 articoli su
    880 erano stati creati anni prima e solo ritoccati dentro la finestra — e
    tutti evergreen/listicle, cioe' la classe che H-A e H-B misurano. Senza il
    ritaglio su `created_at` la contaminazione caricherebbe un gruppo solo.
    """

    def test_un_evergreen_ritoccato_resta_fuori_popolazione(self) -> None:
        evergreen = dict(
            _articolo(1),
            created_at="2020-06-01T17:50:12Z",
            updated_at="2024-03-05T04:47:14Z",
        )
        assert scaricatore.dentro_popolazione(evergreen) is False

    def test_un_articolo_del_periodo_e_dentro(self) -> None:
        assert scaricatore.dentro_popolazione(_articolo(1)) is True

    def test_il_2026_resta_fuori(self) -> None:
        assert scaricatore.dentro_popolazione(dict(_articolo(1), created_at="2026-01-02T12:00:00Z")) is False

    def test_senza_created_at_resta_fuori(self) -> None:
        senza = {k: v for k, v in _articolo(1).items() if k != "created_at"}
        assert scaricatore.dentro_popolazione(senza) is False

    @pytest.mark.asyncio
    async def test_si_pagina_oltre_la_fine_della_popolazione(
        self, tmp_path, monkeypatch
    ) -> None:
        """La coda va recuperata: un articolo creato a fine 2025 e aggiornato nel
        2026 non comparirebbe mai in una finestra ferma al 2025-12-31."""
        monkeypatch.setattr(scaricatore, "INIZIO", "2025-11-01")
        monkeypatch.setattr(scaricatore, "FINE", "2025-12-31")

        monkeypatch.setattr(scaricatore, "fine_fetch", lambda: "2026-02-15")
        finto = _ConnettoreFinto({})
        monkeypatch.setattr(scaricatore, "AlpacaNewsConnector", lambda **_: finto)

        await scaricatore.esegui(tmp_path, _config(tmp_path), forza=False)

        # si pagina fino al mese di scaricamento, non alla fine della popolazione
        assert finto.finestre_viste[0] == "2025-11"
        assert finto.finestre_viste[-1] == "2026-02"

    @pytest.mark.asyncio
    async def test_il_manifest_separa_archivio_e_popolazione(
        self, tmp_path, monkeypatch, _finestra_breve
    ) -> None:
        dentro = _articolo(1)
        fuori = dict(_articolo(2), created_at="2020-06-01T17:50:12Z", updated_at="2024-01-05T00:00:00Z")
        finto = _ConnettoreFinto({"2024-01": [dentro, fuori]})
        monkeypatch.setattr(scaricatore, "AlpacaNewsConnector", lambda **_: finto)

        await scaricatore.esegui(tmp_path, _config(tmp_path), forza=False)

        manifest = json.loads((tmp_path / "manifest.json").read_text())
        assert manifest["mesi"]["2024-01"]["articoli"] == 2
        assert manifest["mesi"]["2024-01"]["nella_popolazione"] == 1
        assert manifest["fetch"]["filtro_api"] == "updated_at"
        assert manifest["popolazione"]["filtro"] == "created_at"
        # l'archivio su disco resta grezzo: il ritaglio e' a valle, non qui
        righe = (tmp_path / "news_2024-01.jsonl").read_text().strip().splitlines()
        assert len(righe) == 2
