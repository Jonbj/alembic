"""Canonicalizzazione del ticker in ingestione (#226).

`BRK.B` è l'unico simbolo di watchlist con un punto, ed è rimasto cieco al sentiment
per 96 segnali: i provider lo restituiscono come `BRKB` e la watchlist dice `BRK.B`.
Gli alias espliciti esistevano già (`GOOG→GOOGL`, `BRK.A→BRK.B`), ma sono mappature
*semantiche* — classi azionarie diverse, ridenominazioni — e nessuno aveva aggiunto
la variante di scrittura.

Questi test fissano la regola generale invece del caso singolo: qualunque forma che
differisca solo per punteggiatura deve ricadere sul simbolo canonico di watchlist,
così il prossimo titolo con classe azionaria (BF.B, BRK.A…) non ripete il difetto.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.workers import ingestion


@pytest.fixture
def watchlist_finta(monkeypatch):
    """Watchlist ridotta con un simbolo puntato, come quella reale.

    `Config` e' un modello pydantic congelato, quindi non si puo' sostituire il
    singolo attributo: si sostituisce il riferimento `config` dentro il modulo.
    """
    monkeypatch.setattr(
        ingestion,
        "config",
        SimpleNamespace(WATCHLIST_SYMBOLS=["AAPL", "GOOGL", "META", "BRK.B", "BF.B"]),
    )
    ingestion._mappa_forme_watchlist.cache_clear()
    yield
    ingestion._mappa_forme_watchlist.cache_clear()


class TestVariantiDiScrittura:
    """Stesso titolo, punteggiatura diversa."""

    @pytest.mark.parametrize("forma", ["BRKB", "BRK-B", "BRK/B", "brk.b"])
    def test_le_varianti_ricadono_sul_simbolo_di_watchlist(self, forma, watchlist_finta):
        assert ingestion.canonicalizza_ticker(forma) == "BRK.B"

    def test_la_regola_vale_anche_per_gli_altri_puntati(self, watchlist_finta):
        """Non è una toppa per Berkshire: BF.B non era mai stato toccato."""
        assert ingestion.canonicalizza_ticker("BFB") == "BF.B"

    def test_il_simbolo_gia_canonico_resta_intatto(self, watchlist_finta):
        assert ingestion.canonicalizza_ticker("BRK.B") == "BRK.B"
        assert ingestion.canonicalizza_ticker("AAPL") == "AAPL"


class TestAliasSemanticiPreservati:
    """Gli alias esistenti sono mappature fra titoli diversi, non varianti."""

    def test_classe_azionaria_e_ridenominazione(self, watchlist_finta):
        assert ingestion.canonicalizza_ticker("GOOG") == "GOOGL"
        assert ingestion.canonicalizza_ticker("FB") == "META"
        assert ingestion.canonicalizza_ticker("BRK.A") == "BRK.B"

    def test_brka_non_finisce_su_brkb_per_somiglianza(self, watchlist_finta):
        """BRK.A → BRK.B deve restare una decisione ESPLICITA. La forma
        normalizzata di BRK.A è BRKA, che non corrisponde a nessun simbolo di
        watchlist: se un giorno l'alias venisse tolto, il titolo deve sparire,
        non essere silenziosamente rimappato."""
        assert ingestion.forma_confrontabile("BRK.A") == "BRKA"
        assert "BRKA" not in ingestion._mappa_forme_watchlist()


class TestNessunaRimappaturaIndebita:
    """Il rischio peggiore è un ordine sul titolo sbagliato."""

    def test_un_ticker_fuori_watchlist_resta_se_stesso(self, watchlist_finta):
        assert ingestion.canonicalizza_ticker("VOO") == "VOO"
        assert ingestion.canonicalizza_ticker("DIA") == "DIA"

    def test_non_accorpa_titoli_diversi(self, watchlist_finta):
        """AAPL e AAPL.X sarebbero due cose: senza corrispondenza esatta sulla
        forma normalizzata non si tocca niente."""
        assert ingestion.canonicalizza_ticker("APPL") == "APPL"  # refuso, non un match

    def test_stringa_vuota_non_esplode(self, watchlist_finta):
        assert ingestion.canonicalizza_ticker("") == ""


class TestIlCasoRealeDiProduzione:
    def test_brkb_arriva_alla_watchlist(self, watchlist_finta):
        """I 96 segnali persi sarebbero stati attribuiti a BRK.B."""
        assert ingestion.canonicalizza_ticker("BRKB") == "BRK.B"

    def test_prima_del_fix_la_mappa_alias_non_bastava(self):
        """`_TICKER_ALIASES` da solo non contiene BRKB: è la prova che il difetto
        non era una voce mancante ma l'assenza della regola."""
        assert "BRKB" not in ingestion._TICKER_ALIASES
