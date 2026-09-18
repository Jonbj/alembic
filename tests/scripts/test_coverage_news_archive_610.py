"""Artefatto di copertura dell'archivio news 2024-2025 (#610).

Le quattro popolazioni devono restare distinte e ridursi nell'ordine giusto:
confonderle e' il modo in cui un buco di copertura diventa un effetto.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from scripts import coverage_news_archive_610 as copertura


def _articolo(
    identificativo: int,
    *,
    creato: str = "2024-03-05T14:00:00Z",
    aggiornato: str | None = None,
    titolo: str = "Apple Reports Q4 Earnings Beat",
    summary: str = "Corpo dell'articolo.",
    content: str = "<p>Corpo dell'articolo.</p>",
    symbols: list[str] | None = None,
) -> dict:
    return {
        "id": identificativo,
        "headline": titolo,
        "summary": summary,
        "content": content,
        "created_at": creato,
        "updated_at": aggiornato or creato,
        "symbols": symbols if symbols is not None else ["AAPL"],
        "url": f"https://example.com/{identificativo}",
    }


def _archivio(tmp_path: Path, articoli: list[dict], mese: str = "2024-03") -> Path:
    directory = tmp_path / "archivio"
    directory.mkdir(exist_ok=True)
    with (directory / f"news_{mese}.jsonl").open("w", encoding="utf-8") as handle:
        for articolo in articoli:
            handle.write(json.dumps(articolo) + "\n")
    return directory


class TestLeQuattroPopolazioni:
    def test_un_articolo_normale_arriva_fino_alla_ricostruita(self, tmp_path) -> None:
        out = copertura.copertura(_archivio(tmp_path, [_articolo(1)]), ["AAPL"])
        assert out["popolazioni"]["archivio"] == 1
        assert out["popolazioni"]["popolazione"] == 1
        assert out["popolazioni"]["ricostruita"] == 1

    def test_fuori_finestra_su_created_at_esce_subito(self, tmp_path) -> None:
        """L'evergreen del 2020 ri-toccato nel 2024: sta nell'archivio, non
        nella popolazione (§1.2 della pre-registrazione)."""
        evergreen = _articolo(
            1,
            creato="2020-06-01T17:50:12Z",
            aggiornato="2024-03-05T04:47:14Z",
            titolo="3 Outdoor Stocks To Watch For Summer 2020",
        )
        out = copertura.copertura(_archivio(tmp_path, [evergreen]), ["AAPL"])
        assert out["popolazioni"]["archivio"] == 1
        assert out["popolazioni"]["fuori_finestra_created_at"] == 1
        assert out["popolazioni"]["popolazione"] == 0
        assert out["popolazioni"]["ricostruita"] == 0

    def test_senza_corpo_conta_ma_non_entra_nella_ricostruita(self, tmp_path) -> None:
        """La pipeline non li vede affatto: `_parse_article` restituisce None."""
        vuoto = _articolo(1, summary="", content="")
        out = copertura.copertura(_archivio(tmp_path, [vuoto]), ["AAPL"])
        assert out["popolazioni"]["popolazione"] == 1
        assert out["popolazioni"]["senza_corpo"] == 1
        assert out["popolazioni"]["ricostruita"] == 0

    def test_senza_corpo_e_diverso_da_template_content_empty(self, tmp_path) -> None:
        """Distinzione che regge H-A: il template HA il testo, il vuoto no.

        Metterli nello stesso gruppo confonderebbe cio' che la pipeline scarta
        con cio' che il detector riconosce.
        """
        template = _articolo(
            1, titolo="If You Invested $1000 In Apple 10 Years Ago, Here's How Much"
        )
        vuoto = _articolo(2, summary="", content="", titolo="Apple Reports Q4 Earnings")
        out = copertura.copertura(_archivio(tmp_path, [template, vuoto]), ["AAPL"])
        assert out["popolazioni"]["senza_corpo"] == 1
        assert out["quote_sulla_popolazione"]["senza_corpo"] == 0.5
        # il template ha il corpo, quindi arriva alla ricostruita...
        assert out["popolazioni"]["ricostruita"] == 1
        # ...ed e' comunque contato come template
        assert out["per_mese"]["2024-03"]["template_content_empty"] == 1

    def test_il_duplicato_di_produzione_viene_scartato_una_volta_sola(
        self, tmp_path
    ) -> None:
        """Stesso titolo+corpo, id diversi: e' la chiave di produzione a decidere."""
        primo = _articolo(1)
        gemello = _articolo(2)  # stesso titolo e corpo
        out = copertura.copertura(_archivio(tmp_path, [primo, gemello]), ["AAPL"])
        assert out["popolazioni"]["popolazione"] == 2
        assert out["popolazioni"]["duplicato_produzione"] == 1
        assert out["popolazioni"]["ricostruita"] == 1

    def test_corpo_html_viene_ripulito_dal_parse_article(self, tmp_path) -> None:
        """`_parse_article` strip i tag HTML e collassa gli spazi: se lo script
        riapplicasse il body grezzo, `compute_dedup_hash` produrrebbe un hash
        diverso da quello che la pipeline calcolerebbe sul testo reale. La
        regola di dedup di produzione va chiamata, non ricopiata (#169/#467)."""
        # Stesso articolo concettuale, forme diverse (HTML vs HTML compattato):
        # in produzione deduplicano, qui devono fare lo stesso.
        con_spazi = _articolo(
            1, content="<p>Apple</p>\n<p>reports</p>\n<p>Q4</p>"
        )
        compattato = _articolo(
            2, content="<p>Apple reports Q4</p>"
        )
        out = copertura.copertura(
            _archivio(tmp_path, [con_spazi, compattato]), ["AAPL"]
        )
        assert out["popolazioni"]["popolazione"] == 2
        assert out["popolazioni"]["duplicato_produzione"] == 1
        assert out["popolazioni"]["ricostruita"] == 1

    def test_fan_out_multi_ticker_non_collassa(self, tmp_path) -> None:
        """Stesso testo ma ticker primario diverso: in produzione la chiave
        `dedup:content:{hash}:{asset_tags[0]}` tiene separati i due item
        (EN-03 — il fan-out multi-ticker e' una funzione voluta della
        pipeline). Lo script NON li deve unificare in un solo duplicato."""
        stesso_testo_aapl = _articolo(1, symbols=["AAPL"])
        stesso_testo_msft = _articolo(2, symbols=["MSFT"])
        # Stesso titolo e stesso body, ticker primario diverso: devono essere
        # due item distinti in produzione, quindi due ricostruiti qui.
        out = copertura.copertura(
            _archivio(tmp_path, [stesso_testo_aapl, stesso_testo_msft]),
            ["AAPL", "MSFT"],
        )
        assert out["popolazioni"]["popolazione"] == 2
        assert out["popolazioni"]["duplicato_produzione"] == 0
        assert out["popolazioni"]["ricostruita"] == 2

    def test_articolo_senza_ticker_non_deduplicato_per_contenuto(self, tmp_path) -> None:
        """`is_duplicate_content_symbol` rifiuta gli item senza `asset_tags`:
        la pipeline non li scarta per contenuto. Lo script deve riflettere
        questa asimmetria, non collassarli in un duplicato spurio."""
        orfano = _articolo(1, symbols=[])
        gemello = _articolo(2, symbols=[])
        out = copertura.copertura(_archivio(tmp_path, [orfano, gemello]), ["AAPL"])
        assert out["popolazioni"]["popolazione"] == 2
        # nessuna chiave di dedup generabile: passano entrambi
        assert out["popolazioni"]["duplicato_produzione"] == 0
        assert out["popolazioni"]["ricostruita"] == 2

    def test_lo_stantio_all_arrivo_viene_scartato(self, tmp_path) -> None:
        """Creato molto prima di quando e' stato servito: in produzione
        `_is_stale_news` lo scarta, e qui deve fare lo stesso."""
        stantio = _articolo(
            1, creato="2024-03-01T10:00:00Z", aggiornato="2024-03-20T10:00:00Z"
        )
        out = copertura.copertura(_archivio(tmp_path, [stantio]), ["AAPL"])
        assert out["popolazioni"]["stantio_all_arrivo"] == 1
        assert out["popolazioni"]["ricostruita"] == 0


class TestCoperturaDellUniverso:
    def test_i_tag_fuori_watchlist_non_gonfiano_la_copertura(self, tmp_path) -> None:
        """I `symbols` di Benzinga portano ogni ticker taggato: contarli tutti
        dava 8038 «simboli coperti» su un universo di 96."""
        articolo = _articolo(1, symbols=["AAPL", "ZZZZ", "QQQQ"])
        out = copertura.copertura(_archivio(tmp_path, [articolo]), ["AAPL", "MSFT"])
        assert out["simboli"]["universo_richiesto"] == 2
        assert out["simboli"]["universo_coperto"] == 1
        assert out["simboli"]["universo_assente"] == ["MSFT"]
        assert out["simboli"]["tag_distinti_totali"] == 3

    def test_i_selezionati_sull_esito_sono_riportati_a_parte(self, tmp_path) -> None:
        """ROKU, RDDT, HOOD, WDC, SPCX sono in watchlist perche' producevano
        segnali forti: il loro peso va letto separatamente, non fuso nel totale."""
        out = copertura.copertura(
            _archivio(tmp_path, [_articolo(1, symbols=["HOOD"])]), ["HOOD", "AAPL"]
        )
        assert out["simboli"]["selezionati_sull_esito"]["HOOD"] == 1
        assert out["simboli"]["selezionati_sull_esito"]["SPCX"] == 0


class TestQuote:
    def test_fuori_orario_copre_weekend_e_notte(self, tmp_path) -> None:
        # 2024-03-05 14:00Z = 09:00 ET, prima dell'apertura
        prima = _articolo(1, creato="2024-03-05T14:00:00Z")
        # 2024-03-05 18:00Z = 13:00 ET, in seduta
        dentro = _articolo(2, creato="2024-03-05T18:00:00Z", titolo="Altro titolo A")
        # 2024-03-09 = sabato
        weekend = _articolo(3, creato="2024-03-09T18:00:00Z", titolo="Altro titolo B")
        out = copertura.copertura(_archivio(tmp_path, [prima, dentro, weekend]), ["AAPL"])
        assert out["popolazioni"]["popolazione"] == 3
        assert out["per_mese"]["2024-03"]["fuori_orario"] == 2

    def test_multi_ticker_conta_solo_oltre_un_simbolo(self, tmp_path) -> None:
        singolo = _articolo(1, symbols=["AAPL"])
        multiplo = _articolo(2, symbols=["AAPL", "MSFT"], titolo="Altro titolo")
        out = copertura.copertura(_archivio(tmp_path, [singolo, multiplo]), ["AAPL"])
        assert out["quote_sulla_popolazione"]["multi_ticker"] == 0.5

    def test_le_quote_sono_nulle_su_popolazione_vuota(self, tmp_path) -> None:
        fuori = _articolo(1, creato="2020-01-01T10:00:00Z", aggiornato="2024-03-01T10:00:00Z")
        out = copertura.copertura(_archivio(tmp_path, [fuori]), ["AAPL"])
        assert out["quote_sulla_popolazione"]["senza_corpo"] is None


class TestArtefatto:
    def test_dichiara_la_ricostruzione_come_tale(self, tmp_path) -> None:
        """`now = updated_at` e' una ricostruzione, non un dato: l'archivio non
        registra la latenza di consegna reale, e l'artefatto deve dirlo."""
        out = copertura.copertura(_archivio(tmp_path, [_articolo(1)]), ["AAPL"])
        assert "ricostruzione dichiarata" in out["nota_ricostruzione"]
        assert out["finestra_popolazione"]["filtro"] == "created_at"

    def test_senza_jsonl_esce_non_zero(self, tmp_path, monkeypatch, capsys) -> None:
        vuota = tmp_path / "vuota"
        vuota.mkdir()
        config = tmp_path / "trading.yaml"
        config.write_text(yaml.safe_dump({"symbols": {"watchlist": ["AAPL"]}}))
        monkeypatch.setattr(
            "sys.argv",
            ["x", "--archivio", str(vuota), "--out", str(tmp_path / "o.json"),
             "--config", str(config)],
        )
        assert copertura.main() == 1


@pytest.mark.parametrize(
    "summary,content,atteso",
    [
        ("", "", True),
        ("   ", "  ", True),
        ("testo", "", False),
        ("", "<p>testo</p>", False),
    ],
)
def test_senza_corpo_riproduce_lo_scarto_del_connettore(summary, content, atteso) -> None:
    assert copertura.senza_corpo({"summary": summary, "content": content}) is atteso
