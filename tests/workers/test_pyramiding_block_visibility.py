"""Il blocco anti-pyramiding deve lasciare traccia in execution_decisions (#231).

Quando il guard P0-05 scarta un BUY per un simbolo gia' a libro, lo fa con un `continue`
che salta anche la persistenza. Dal database non si distingue «bloccato di proposito» da
«mai valutato»: due stati di significato opposto che producono la stessa assenza di righe.

Il 2026-08-10 sono spariti cosi' sei segnali sopra il gate, incluso il piu' alto della
giornata (TSM +0,691). Il protocollo alpha-miss ha dovuto DEDURRE il guard dalla scomparsa
delle righe invece di leggerlo — e i log dei container sono gia' andati persi tre volte.

Vincolo che il fix non deve violare: la riga NON deve essere un `BUY`. Quello era il difetto
precedente (10-24 BUY identici per ciclo per simbolo aperto, che apparivano come replay di
segnali stale) ed e' presidiato da `test_buy_decision_not_logged_for_symbol_with_open_trade`.
La riga nuova e' uno SKIP, e va scritta una sola volta per segnale — non a ogni ciclo.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from src.workers.portfolio_scheduler import (
    _pyramiding_block_key,
    _record_pyramiding_blocks,
)


class TestChiaveDiIdempotenza:
    """Una riga per segnale, non una per ciclo."""

    def test_il_segnale_identifica_il_blocco(self) -> None:
        assert _pyramiding_block_key("TSM", 4211) == "TSM|4211"

    def test_senza_segnale_si_ricade_sul_giorno(self) -> None:
        """Un BUY di solo momentum non ha signal_id: senza un fallback datato
        produrrebbe una riga a ogni ciclo, cioe' la pollution che il fix
        precedente aveva eliminato."""
        k = _pyramiding_block_key("XLK", None, giorno="2026-08-10")
        assert k == "XLK|nosig|2026-08-10"

    def test_segnali_diversi_sullo_stesso_simbolo_sono_blocchi_diversi(self) -> None:
        assert _pyramiding_block_key("TSM", 1) != _pyramiding_block_key("TSM", 2)


class TestScritturaDellaRiga:
    def _pg(self):
        pg = MagicMock()
        pg.write_execution_decision = MagicMock(return_value=1)
        return pg

    def test_scrive_una_riga_skip_per_il_simbolo_bloccato(self) -> None:
        pg = self._pg()
        bloccati = [
            {"symbol": "TSM", "signal_id": 4211, "signal_score": 0.691,
             "allocation_weight": 0.20, "open_since": "2026-07-14"},
        ]
        _record_pyramiding_blocks(pg, bloccati, gia_registrati=set(), regime_mult=1.0)

        assert pg.write_execution_decision.call_count == 1
        kw = pg.write_execution_decision.call_args.kwargs
        assert kw["symbol"] == "TSM"
        assert kw["signal_score"] == 0.691
        assert kw["signal_id"] == 4211

    def test_la_decisione_non_e_un_buy(self) -> None:
        """Il vincolo che protegge il fix precedente."""
        pg = self._pg()
        _record_pyramiding_blocks(
            pg,
            [{"symbol": "TSM", "signal_id": 1, "signal_score": 0.69,
              "allocation_weight": 0.2, "open_since": None}],
            gia_registrati=set(),
            regime_mult=1.0,
        )
        decisione = pg.write_execution_decision.call_args.kwargs["decision"]
        assert decisione != "BUY"
        assert decisione.startswith("SKIP")
        assert len(decisione) <= 20, "la colonna decision e' varchar(20)"

    def test_la_ragione_dice_perche_ed_e_leggibile(self) -> None:
        pg = self._pg()
        _record_pyramiding_blocks(
            pg,
            [{"symbol": "XLE", "signal_id": 77, "signal_score": 0.516,
              "allocation_weight": 0.20, "open_since": "2026-07-10"}],
            gia_registrati=set(),
            regime_mult=1.0,
        )
        reason = pg.write_execution_decision.call_args.kwargs["reason"]
        assert "0.516" in reason
        assert "2026-07-10" in reason

    def test_conserva_il_peso_che_sarebbe_stato_allocato(self) -> None:
        """Serve a #230: senza questo non si puo' misurare quanto capitale
        il blocco lascia non impiegato."""
        pg = self._pg()
        _record_pyramiding_blocks(
            pg,
            [{"symbol": "XLE", "signal_id": 77, "signal_score": 0.5,
              "allocation_weight": 0.20, "open_since": None}],
            gia_registrati=set(),
            regime_mult=1.0,
        )
        assert pg.write_execution_decision.call_args.kwargs["score"] == 0.20


class TestIdempotenza:
    def test_non_riscrive_un_blocco_gia_registrato(self) -> None:
        pg = MagicMock()
        bloccati = [{"symbol": "TSM", "signal_id": 4211, "signal_score": 0.691,
                     "allocation_weight": 0.2, "open_since": None}]
        _record_pyramiding_blocks(
            pg, bloccati, gia_registrati={"TSM|4211"}, regime_mult=1.0
        )
        pg.write_execution_decision.assert_not_called()

    def test_restituisce_le_chiavi_scritte_per_marcarle(self) -> None:
        pg = MagicMock()
        pg.write_execution_decision = MagicMock(return_value=1)
        nuove = _record_pyramiding_blocks(
            pg,
            [{"symbol": "TSM", "signal_id": 1, "signal_score": 0.6,
              "allocation_weight": 0.2, "open_since": None},
             {"symbol": "XLE", "signal_id": 2, "signal_score": 0.5,
              "allocation_weight": 0.2, "open_since": None}],
            gia_registrati=set(),
            regime_mult=1.0,
        )
        assert set(nuove) == {"TSM|1", "XLE|2"}

    def test_registra_solo_i_nuovi_di_un_lotto_misto(self) -> None:
        pg = MagicMock()
        pg.write_execution_decision = MagicMock(return_value=1)
        nuove = _record_pyramiding_blocks(
            pg,
            [{"symbol": "TSM", "signal_id": 1, "signal_score": 0.6,
              "allocation_weight": 0.2, "open_since": None},
             {"symbol": "XLE", "signal_id": 2, "signal_score": 0.5,
              "allocation_weight": 0.2, "open_since": None}],
            gia_registrati={"TSM|1"},
            regime_mult=1.0,
        )
        assert nuove == ["XLE|2"]
        assert pg.write_execution_decision.call_count == 1


class TestNonRompeIlCiclo:
    """Come `_record_stale_drops`: la visibilita' non deve mai far cadere un ciclo."""

    def test_un_errore_di_scrittura_non_propaga(self) -> None:
        pg = MagicMock()
        pg.write_execution_decision.side_effect = RuntimeError("DB giu'")
        nuove = _record_pyramiding_blocks(
            pg,
            [{"symbol": "TSM", "signal_id": 1, "signal_score": 0.6,
              "allocation_weight": 0.2, "open_since": None}],
            gia_registrati=set(),
            regime_mult=1.0,
        )
        assert nuove == []

    def test_lista_vuota_non_tocca_il_db(self) -> None:
        pg = MagicMock()
        assert _record_pyramiding_blocks(pg, [], gia_registrati=set(), regime_mult=1.0) == []
        pg.write_execution_decision.assert_not_called()
