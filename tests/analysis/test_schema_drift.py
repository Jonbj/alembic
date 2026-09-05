"""Test per il rilevatore di deriva sull'enum (#452).

I casi reali sono presi dalla query diretta su `llm_responses` in produzione
(2026-09-05, prima del fix): valori inventati, separatori della lista
ricopiati, refusi sui risk_flags, un carattere invisibile dentro un valore
altrimenti valido.
"""

from __future__ import annotations

from src.analysis.schema_drift import (
    aggrega_deriva,
    classifica_riga,
    risk_flags_in_deriva,
    valore_in_deriva,
)


class TestValoreInDeriva:
    def test_valore_valido_non_e_in_deriva(self) -> None:
        assert valore_in_deriva("direct", frozenset({"direct", "sector"})) is False

    def test_valore_none_non_e_in_deriva(self) -> None:
        """Un campo assente (self-report non fornito) non e' un difetto di
        enum: e' fuori campione, non deriva."""
        assert valore_in_deriva(None, frozenset({"direct"})) is False

    def test_valore_inventato_e_in_deriva(self) -> None:
        assert valore_in_deriva("supplier_readthrough", frozenset({"direct"})) is True

    def test_separatore_della_lista_ricopiato_e_in_deriva(self) -> None:
        assert valore_in_deriva("competitor_readthrough|macro", frozenset({"competitor_readthrough"})) is True

    def test_carattere_invisibile_e_in_deriva(self) -> None:
        """'uncl​ear' (zero-width space) non e' 'unclear': un match
        esatto lo cattura, un confronto case-insensitive o strip() no."""
        assert valore_in_deriva("uncl​ear", frozenset({"unclear"})) is True

    def test_valore_da_un_campo_diverso_e_in_deriva(self) -> None:
        """'product' e' un event_type valido, non un directness valido:
        conta come deriva sul campo su cui compare."""
        assert valore_in_deriva("product", frozenset({"direct", "sector"})) is True


class TestRiskFlagsInDeriva:
    def test_flag_validi_restano_fuori(self) -> None:
        assert risk_flags_in_deriva(["rumor", "already_priced_in"]) == []

    def test_refusi_reali_di_produzione(self) -> None:
        assert risk_flags_in_deriva(
            ["ambiguo_entity", "amplechance_already_priced_in", "whether already_priced_in", "ambiguou_entity"]
        ) == ["ambiguo_entity", "amplechance_already_priced_in", "whether already_priced_in", "ambiguou_entity"]

    def test_lista_vuota_o_none(self) -> None:
        assert risk_flags_in_deriva([]) == []
        assert risk_flags_in_deriva(None) == []


class TestClassificaRiga:
    def test_riga_pulita(self) -> None:
        v = classifica_riga("direct", "earnings", ["rumor"])
        assert v == {
            "directness_invalido": False,
            "event_type_invalido": False,
            "risk_flags_invalidi": [],
            "riga_in_deriva": False,
        }

    def test_riga_con_un_solo_campo_in_deriva_conta_come_in_deriva(self) -> None:
        v = classifica_riga("direct", "sector", [])  # 'sector' non e' un event_type valido
        assert v["event_type_invalido"] is True
        assert v["riga_in_deriva"] is True

    def test_casi_reali_di_produzione(self) -> None:
        assert classifica_riga("supplier_readthrough", None, None)["riga_in_deriva"] is True
        assert classifica_riga("competitor_readthrough|macro", None, None)["riga_in_deriva"] is True
        assert classifica_riga("uncl​ear", None, None)["riga_in_deriva"] is True
        assert classifica_riga(None, "earnings|guidance", None)["riga_in_deriva"] is True


class TestAggregaDeriva:
    def test_conteggio_e_tasso(self) -> None:
        righe = [
            {"directness": "direct", "event_type": "earnings", "risk_flags": []},
            {"directness": "supplier_readthrough", "event_type": None, "risk_flags": []},
            {"directness": None, "event_type": None, "risk_flags": None},  # fuori campione
        ]
        r = aggrega_deriva(righe)
        assert r["n_campione"] == 2
        assert r["directness"]["n_invalidi"] == 1
        assert r["directness"]["tasso"] == 0.5
        assert r["directness"]["valori_osservati"] == ["supplier_readthrough"]
        assert r["riga_in_deriva"]["n"] == 1
        assert r["riga_in_deriva"]["tasso"] == 0.5

    def test_nessuna_riga_nel_campione(self) -> None:
        r = aggrega_deriva([{"directness": None, "event_type": None, "risk_flags": None}])
        assert r["n_campione"] == 0
        assert r["directness"]["tasso"] is None
        assert r["riga_in_deriva"]["tasso"] is None

    def test_risk_flags_aggregati_su_piu_righe(self) -> None:
        righe = [
            {"directness": "direct", "event_type": "other", "risk_flags": ["ambiguo_entity"]},
            {"directness": "direct", "event_type": "other", "risk_flags": ["rumor", "ambiguou_entity"]},
        ]
        r = aggrega_deriva(righe)
        assert r["risk_flags"]["n_righe_con_flag_invalido"] == 2
        assert r["risk_flags"]["valori_osservati"] == ["ambiguo_entity", "ambiguou_entity"]
