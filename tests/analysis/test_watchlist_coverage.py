"""Test per il controllo di copertura della watchlist (#226).

Il caso che ha motivato il controllo: il sentiment scrive `BRKB`, la watchlist e tutto
il resto del sistema usano `BRK.B`. Le due forme non si incontrano mai, e BRK.B e'
rimasto cieco al sentiment per 96 segnali senza che nulla lo segnalasse.

Nota sul perche' il controllo NON guarda `execution_decisions`: BRK.B **ha** 4 righe
in quella tabella, prodotte dal path momentum S1. Un controllo su "mai deciso" non
avrebbe visto niente. La firma che coglie il difetto e' l'assenza di *segnali di
sentiment* per un simbolo di watchlist, piu' la presenza di un orfano che gli
somiglia a meno della normalizzazione.
"""

from __future__ import annotations

from src.analysis.watchlist_coverage import (
    forma_confrontabile,
    orfani_di_normalizzazione,
    simboli_watchlist_senza_segnali,
)


class TestFormaConfrontabile:
    def test_toglie_punteggiatura_e_normalizza(self) -> None:
        assert forma_confrontabile("BRK.B") == "BRKB"
        assert forma_confrontabile("brk-b") == "BRKB"
        assert forma_confrontabile("  BRK.B  ") == "BRKB"
        assert forma_confrontabile("BRK/B") == "BRKB"

    def test_lascia_intatti_i_ticker_semplici(self) -> None:
        assert forma_confrontabile("AAPL") == "AAPL"
        assert forma_confrontabile("TSM") == "TSM"


class TestOrfaniDiNormalizzazione:
    """Il segnale scritto in una forma che la watchlist non riconosce."""

    def test_riconosce_il_caso_brkb(self) -> None:
        watchlist = ["AAPL", "BRK.B", "TSM"]
        simboli_segnale = ["AAPL", "BRKB", "TSM"]
        assert orfani_di_normalizzazione(watchlist, simboli_segnale) == [("BRKB", "BRK.B")]

    def test_nessun_orfano_quando_le_forme_coincidono(self) -> None:
        assert orfani_di_normalizzazione(["AAPL", "BRK.B"], ["AAPL", "BRK.B"]) == []

    def test_un_simbolo_fuori_watchlist_non_e_un_orfano(self) -> None:
        """VOO non e' in watchlist e non somiglia a nulla che ci sia: e' solo
        fuori universo, non un difetto di normalizzazione."""
        assert orfani_di_normalizzazione(["AAPL", "BRK.B"], ["VOO", "DIA"]) == []

    def test_non_confonde_classi_azionarie_diverse(self) -> None:
        """BRKA non deve essere appaiato a BRK.B: sono due titoli."""
        assert orfani_di_normalizzazione(["BRK.B"], ["BRKA"]) == []

    def test_ordinato_e_senza_duplicati(self) -> None:
        watchlist = ["BRK.B", "BF.B"]
        simboli = ["BRKB", "BRKB", "BFB"]
        assert orfani_di_normalizzazione(watchlist, simboli) == [("BFB", "BF.B"), ("BRKB", "BRK.B")]


class TestSimboliSenzaSegnali:
    """Un simbolo di watchlist che non riceve mai sentiment."""

    def test_segnala_il_simbolo_muto(self) -> None:
        conteggi = {"AAPL": 40, "TSM": 12, "BRK.B": 0}
        assert simboli_watchlist_senza_segnali(["AAPL", "TSM", "BRK.B"], conteggi) == ["BRK.B"]

    def test_simbolo_assente_dai_conteggi_vale_zero(self) -> None:
        assert simboli_watchlist_senza_segnali(["AAPL", "BRK.B"], {"AAPL": 5}) == ["BRK.B"]

    def test_nessun_falso_positivo_se_tutti_hanno_segnali(self) -> None:
        assert simboli_watchlist_senza_segnali(["AAPL", "TSM"], {"AAPL": 1, "TSM": 1}) == []

    def test_watchlist_vuota(self) -> None:
        assert simboli_watchlist_senza_segnali([], {}) == []


class TestIlControlloAvrebbeColtoIlCasoReale:
    """Ricostruzione del 2026-08-10 con i dati veri di produzione."""

    def test_brkb_sarebbe_stato_segnalato(self) -> None:
        watchlist = ["AAPL", "TSM", "BRK.B", "GE", "MU"]
        # In produzione: 96 segnali su BRKB, zero su BRK.B.
        conteggi = {"AAPL": 30, "TSM": 18, "GE": 6, "MU": 4, "BRKB": 96}

        muti = simboli_watchlist_senza_segnali(watchlist, conteggi)
        orfani = orfani_di_normalizzazione(watchlist, list(conteggi))

        assert muti == ["BRK.B"]
        assert orfani == [("BRKB", "BRK.B")]

    def test_un_controllo_sulle_decisioni_non_lo_avrebbe_colto(self) -> None:
        """BRK.B ha 4 righe in execution_decisions dal path momentum: guardare
        li' avrebbe dato un falso negativo. E' il motivo per cui il controllo
        guarda i segnali."""
        decisioni_per_simbolo = {"AAPL": 120, "TSM": 90, "BRK.B": 4}
        mai_deciso = [s for s, n in decisioni_per_simbolo.items() if n == 0]
        assert "BRK.B" not in mai_deciso
