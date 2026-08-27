"""Test di accettazione #333 (punto 4) — riconciliazione report <-> dossier.

Il report alpha-miss del 2026-08-20 narra 1 dei 4 ingressi S4 e 1 delle 4 chiusure,
omettendo HOOD (-$60,32), la perdita realizzata piu' grande della giornata. L'aggregato
in sommario e' corretto, manca l'itemizzazione: nulla nella pipeline confronta i simboli
narrati con `dossier.ingressi` / `dossier.chiusure`, quindi la divergenza e' silenziosa.

Serve una funzione pura nel modulo `src/analysis/dossier/reconciliation.py`:

    simboli_non_menzionati(dossier: dict, testo_report: str) -> dict

che restituisce esattamente queste chiavi:

    {"ingressi_mancanti": [...], "chiusure_mancanti": [...], "ok": bool}

Le liste sono ordinate alfabeticamente (esito deterministico, confrontabile fra
esecuzioni); `ok` e' True se e solo se sono entrambe vuote.
"""

from __future__ import annotations

import pytest

from src.analysis.dossier.reconciliation import simboli_non_menzionati


def _dossier(ingressi=(), chiusure=()):
    return {
        "data": "2026-08-20",
        "ingressi": [{"symbol": s} for s in ingressi],
        "chiusure": [{"symbol": s} for s in chiusure],
    }


def test_riconcilia_quando_il_report_nomina_tutti_i_simboli():
    dossier = _dossier(ingressi=["WMT"], chiusure=["WMT"])
    esito = simboli_non_menzionati(dossier, "Oggi S4 ha aperto e chiuso WMT in giornata.")
    assert esito == {"ingressi_mancanti": [], "chiusure_mancanti": [], "ok": True}


def test_segnala_gli_ingressi_omessi():
    dossier = _dossier(ingressi=["NVDA", "WMT", "NOW", "AVGO"], chiusure=[])
    esito = simboli_non_menzionati(dossier, "Tradato oggi: WMT.")
    assert esito["ingressi_mancanti"] == ["AVGO", "NOW", "NVDA"]
    assert esito["ok"] is False


def test_segnala_le_chiusure_omesse_separatamente_dagli_ingressi():
    dossier = _dossier(ingressi=["WMT"], chiusure=["HOOD", "NVDA", "WMT", "NOW"])
    esito = simboli_non_menzionati(dossier, "Tradato oggi: WMT.")
    assert esito["ingressi_mancanti"] == []
    assert esito["chiusure_mancanti"] == ["HOOD", "NOW", "NVDA"]


def test_le_liste_sono_ordinate_alfabeticamente():
    dossier = _dossier(ingressi=["NVDA", "AVGO", "NOW"])
    assert simboli_non_menzionati(dossier, "nessuno")["ingressi_mancanti"] == ["AVGO", "NOW", "NVDA"]


def test_un_dossier_senza_operazioni_riconcilia_con_qualunque_report():
    assert simboli_non_menzionati(_dossier(), "Giornata senza operazioni.")["ok"] is True


def test_chiavi_ingressi_o_chiusure_assenti_non_sollevano():
    """I dossier piu' vecchi possono non avere le due chiavi: assenti = nessuna
    operazione, non un errore."""
    esito = simboli_non_menzionati({"data": "2026-07-01"}, "testo")
    assert esito == {"ingressi_mancanti": [], "chiusure_mancanti": [], "ok": True}


def test_il_simbolo_va_riconosciuto_come_parola_intera():
    """`NOW` non deve risultare menzionato da 'NOWHERE', altrimenti la
    riconciliazione passa su un report che non nomina il titolo."""
    esito = simboli_non_menzionati(_dossier(ingressi=["NOW"]), "Il gate NOWHERE ha scartato tutto.")
    assert esito["ingressi_mancanti"] == ["NOW"]


def test_il_simbolo_e_riconosciuto_anche_dentro_una_tabella_markdown():
    esito = simboli_non_menzionati(_dossier(ingressi=["HOOD"]), "| IN | HOOD | 15:22 |")
    assert esito["ok"] is True


def test_il_confronto_ignora_le_differenze_di_maiuscole():
    esito = simboli_non_menzionati(_dossier(chiusure=["HOOD"]), "chiusa la posizione hood in perdita")
    assert esito["ok"] is True


def test_un_simbolo_ripetuto_nel_dossier_compare_una_volta_sola():
    dossier = _dossier(chiusure=["NVDA", "NVDA"])
    assert simboli_non_menzionati(dossier, "nessuno")["chiusure_mancanti"] == ["NVDA"]


def test_le_voci_senza_simbolo_vengono_ignorate():
    dossier = {"ingressi": [{"symbol": ""}, {"pct": 0.3}, {"symbol": "WMT"}], "chiusure": []}
    assert simboli_non_menzionati(dossier, "nessuno")["ingressi_mancanti"] == ["WMT"]


def test_il_caso_reale_del_20_agosto():
    """Regressione sul caso che ha originato la issue: report che nomina solo WMT
    mentre il dossier registra 4 ingressi e 4 chiusure."""
    dossier = _dossier(
        ingressi=["NVDA", "WMT", "NOW", "AVGO"],
        chiusure=["HOOD", "NVDA", "WMT", "NOW"],
    )
    report = "## 4. Titoli catturati: esito\n\n**Tradato oggi:** WMT, entrata alle 16:37.\n"
    esito = simboli_non_menzionati(dossier, report)
    assert esito["ingressi_mancanti"] == ["AVGO", "NOW", "NVDA"]
    assert esito["chiusure_mancanti"] == ["HOOD", "NOW", "NVDA"]
    assert esito["ok"] is False


def test_il_simbolo_con_spazi_attorno_viene_riconosciuto():
    """Difetto trovato in review sondando oltre il test di accettazione: il codice usava
    `strip()` per decidere se il simbolo fosse vuoto, poi `upper()` SENZA strip per cercarlo,
    quindi cercava `\\b WMT \\b` e non trovava mai nulla."""
    dossier = {"ingressi": [{"symbol": " WMT "}], "chiusure": []}
    # il simbolo a fine riga espone il difetto: cercando " WMT " con gli spazi, il match
    # fallisce perche' dopo WMT non c'e' spazio ma fine stringa
    assert simboli_non_menzionati(dossier, "oggi abbiamo aperto WMT")["ok"] is True


def test_una_chiave_presente_con_valore_nullo_non_solleva():
    """`dossier.get('ingressi', [])` restituisce None se la chiave esiste col valore None:
    i dossier piu' vecchi possono averla cosi'."""
    dossier = {"ingressi": None, "chiusure": None}
    assert simboli_non_menzionati(dossier, "qualunque testo")["ok"] is True


def test_una_lista_malformata_non_solleva():
    dossier = {"ingressi": "non e' una lista", "chiusure": []}
    assert simboli_non_menzionati(dossier, "testo")["ok"] is True
