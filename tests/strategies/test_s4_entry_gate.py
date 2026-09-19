"""#550 (F-073) — lo score che il gate d'ingresso S4 valuta davvero.

Il ciclo S4 moltiplica lo score grezzo per il moltiplicatore di signal-velocity
PRIMA di confrontarlo con la soglia `feedback:entry_threshold:S4`. Due decisori
diversi (produzione e misura) che calcolano «cosa passa il gate» in due modi
diversi sono il difetto #169/#467: qui la formula vive una volta sola.
"""
from __future__ import annotations

import pytest

from src.strategies.s4.entry_gate import deciding_entry_score, passes_entry_gate


class TestDecidingEntryScore:
    def test_il_decidente_e_il_grezzo_per_il_moltiplicatore(self):
        # BA 2026-09-17: grezzo 0.2738, boost 1.2 -> il gate ha visto 0.3285.
        assert deciding_entry_score(0.27375, 1.2) == pytest.approx(0.3285)

    def test_senza_moltiplicatore_il_decidente_e_il_grezzo(self):
        """None = riga non strumentata (storico pre-077): l'unica lettura onesta
        e' trattarla come moltiplicatore unitario, non come gate superato."""
        assert deciding_entry_score(0.27375, None) == pytest.approx(0.27375)

    def test_il_moltiplicatore_unitario_e_l_identita(self):
        assert deciding_entry_score(0.42, 1.0) == pytest.approx(0.42)


class TestPassesEntryGate:
    def test_un_grezzo_sotto_soglia_con_boost_oltre_soglia_passa(self):
        """Il caso NVDA/BA della issue: 0.266 < 0.300 grezzo, 0.319 >= 0.300
        con velocity — e' l'ordine che la produzione ha davvero eseguito."""
        assert passes_entry_gate(0.26625, 1.2, 0.300) is True

    def test_un_grezzo_sotto_soglia_senza_boost_non_passa(self):
        assert passes_entry_gate(0.2883, 1.0, 0.300) is False

    def test_all_equality_sul_decidente_passa(self):
        """Il gate di produzione droppa `abs(score) < threshold`: all'uguaglianza
        resta. La stessa frontiera, non una piu' stretta."""
        assert passes_entry_gate(0.300, 1.0, 0.300) is True
        assert passes_entry_gate(-0.300, 1.0, 0.300) is True

    def test_il_confronto_e_sul_valore_assoluto(self):
        """I segnali bearish sono gated come i bullish (commento al filtro
        produzione: absolute value check)."""
        assert passes_entry_gate(-0.26625, 1.2, 0.300) is True
        assert passes_entry_gate(-0.2883, 1.0, 0.300) is False

    def test_moltiplicatore_assente_degrada_al_grezzo(self):
        assert passes_entry_gate(0.29, None, 0.300) is False
