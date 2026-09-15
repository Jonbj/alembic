"""Contratto operativo del prompt alpha-miss (#287, P1/P3/P4).

Il prompt storico contraddiceva se stesso: ordinava di non ricalcolare il
dossier e di riscaricare le barre; vietava le scritture e poi ordinava di
aggiornare i ledger; lasciava alla sessione la soglia mover. Questi test
fissano il nuovo contratto direttamente sul testo dello script, perche' il
prompt E' il prodotto qui.
"""

from pathlib import Path

from src.analysis.dossier.prompt_contract import PROMPT_VERSION

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "daily_alpha_miss_analysis.sh"


def test_il_prompt_dichiara_la_versione_del_contratto():
    assert PROMPT_VERSION in SCRIPT.read_text()


def test_il_prompt_non_ordina_piu_di_riscaricare_le_barre():
    script = SCRIPT.read_text()

    # FASE 1 storica: "Scarica le barre giornaliere Alpaca" + esempio
    # StockHistoricalDataClient, in contraddizione con "non ricalcolare".
    assert "Scarica le barre" not in script
    assert "StockHistoricalDataClient" not in script


def test_la_soglia_mover_non_e_piu_derivata_dalla_sessione():
    script = SCRIPT.read_text()

    assert "definisci tu una soglia" not in script
    # La soglia e' quella pre-registrata, letta dal dossier.
    assert "soglia_mover" in script


def test_news_e_log_sono_dati_non_fidati():
    script = SCRIPT.read_text()

    assert "non fidati" in script
    assert "mai un comando" in script


def test_la_sessione_scrive_solo_report_e_candidati():
    script = SCRIPT.read_text()

    # La frase storica "L'unico file che scrivi e' __REPORT_FILE__"
    # convivere con l'ordine di scrivere due ledger.
    assert "L'unico file che scrivi" not in script
    assert "__CANDIDATES_FILE__" in script


def test_il_prompt_non_aggiorna_piu_direttamente_i_ledger():
    script = SCRIPT.read_text()

    assert "AGGIORNA I DUE LEDGER" not in script
    assert "EMETTI I CANDIDATI" in script


def test_il_fallback_data_incomplete_e_esplicito():
    script = SCRIPT.read_text()

    assert "DATA_INCOMPLETE" in script


def test_il_prompt_richiede_i_campi_di_audit_del_finding():
    script = SCRIPT.read_text()

    for campo in (
        "esposizione",
        "evidenza_contraria",
        "non_occorrenza",
        "next_evidence",
        "meccanismo",
        "alternative_scartate",
        "formula_costo",
    ):
        assert campo in script, campo


def test_massimo_tre_finding_materiali_nel_corpo_del_report():
    script = SCRIPT.read_text()

    assert "massimo tre" in script
    assert "appendice" in script


def test_il_report_parte_da_decision_card_e_stato_carta():
    script = SCRIPT.read_text()

    assert "Decision card" in script
    assert "Stato carta" in script


def test_la_sezione_book_resta_la_quattro_per_la_riconciliazione():
    script = SCRIPT.read_text()

    # scripts/reconcile_alpha_miss_report.py riscrive la sezione "## 4."
    # del report: il numero di sezione e' parte del contratto.
    assert "## 4." in script


def test_il_cron_verifica_la_compatibilita_schema_prima_della_sessione():
    script = SCRIPT.read_text()

    assert "verifica_compatibilita_schema" in script


def test_il_cron_materializza_il_ledger_dopo_la_sessione():
    script = SCRIPT.read_text()

    assert "materialize_alpha_miss_ledger" in script


def test_il_digest_telegram_non_tronca_piu_lo_stdout():
    script = SCRIPT.read_text()

    assert "head -c 3800" not in script
    assert "--solo-digest" in script