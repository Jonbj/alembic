"""#208: il dossier deve usare la soglia S4 letta da Redis, non il default 0.30.

Il bug originale: `classify_miss_candidates` veniva chiamato senza argomenti,
quindi usava il default 0.30. Quando il ratchet (#191) aveva spinto il gate a
0.40-0.45, ogni candidato con score in [0.30, 0.45) finiva in NON_CLASSIFICATO
invece di BELOW_GATE — nei giorni che il dossier deve spiegare, la causa
dominante veniva mis-classificata.

Il fix: l'orchestratore legge `feedback:entry_threshold:S4` da Redis (con
fallback al baseline solo se la chiave e' assente) e la passa al classificatore.
Qui testiamo entrambi i rami: con soglia Redis a 0.45 il candidato BELOW_GATE,
senza chiave il candidato NON_CLASSIFICATO.
"""

from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch

import scripts.alpha_miner_dossier as dossier


def _cand_data():
    """Dati minimi coerenti: un solo simbolo, una barra, un segnale a 0.35."""
    return {
        "barre": {
            "AAPL": {
                "open": 100.0, "high": 110.0, "low": 99.0, "close": 107.0,
                "close_prec": 100.0,
            }
        },
        "news_counts": {"AAPL": 1},
        "segnali_rows": [
            ["AAPL", "15:30", "0.35", "f", "org_lookup", "AAPL hits record high", "1"],
        ],
        "in_portafoglio_rows": [],
        "ingressi_rows": [],
        "chiusure_rows": [],
        "chiusi_storici_rows": [],
    }


def _patch_io(canned):
    """Rende tutte le funzioni di I/O del dossier deterministiche."""
    from contextlib import ExitStack

    def fake_psql(query):
        # #244: la query dei segnali fa join+sottoquery su news_log, quindi va
        # riconosciuta PRIMA del conteggio news, altrimenti il match e' ambiguo.
        if "FROM sentiment_signals" in query:
            return canned["segnali_rows"]
        if "FROM news_log" in query:
            return [[sym, str(n)] for sym, n in canned["news_counts"].items()]
        if "FROM trades" in query and "entry_time <" in query and "DISTINCT symbol" in query:
            return canned["in_portafoglio_rows"]
        if "FROM trades" in query and "entry_time >=" in query:
            return canned["ingressi_rows"]
        if "FROM trades" in query and "exit_time >=" in query:
            return canned["chiusure_rows"]
        if "EXTRACT(hour FROM entry_time)" in query:
            return canned["chiusi_storici_rows"]
        return []

    stack = ExitStack()
    stack.enter_context(patch.object(dossier, "_psql", side_effect=fake_psql))
    stack.enter_context(patch.object(dossier, "_barre", return_value=canned["barre"]))
    stack.enter_context(patch.object(dossier, "_timeline_eventi", return_value=[]))
    stack.enter_context(patch.object(
        dossier,
        "_barre_intraday",
        return_value=({}, datetime(2026, 8, 5, 23, 59, tzinfo=timezone.utc)),
    ))
    stack.enter_context(patch.object(dossier, "_dettagli_ordini", return_value={}))
    stack.enter_context(patch.object(dossier, "_watchlist", return_value=["AAPL"]))
    return stack


def test_con_soglia_redis_a_045_candidato_con_score_035_e_below_gate():
    """Con `feedback:entry_threshold:S4=0.45` in Redis, score 0.35 -> BELOW_GATE.

    Con il default 0.30 il candidato sarebbe NON_CLASSIFICATO. Questo e' il
    bug che #208 corregge: il dossier deve confrontarsi con la soglia
    EFFETTIVA del giorno, non con quella baseline congelata.
    """
    canned = _cand_data()
    with _patch_io(canned), \
         patch("redis.Redis") as mock_cls:
        inst = MagicMock()
        inst.get.return_value = "0.45"
        mock_cls.from_url.return_value = inst
        out = dossier.costruisci_dossier(date(2026, 8, 5), ["AAPL"])

    candidati = out["candidati_miss"]
    assert len(candidati) == 1
    assert candidati[0]["symbol"] == "AAPL"
    assert candidati[0]["causa"] == "BELOW_GATE"


def test_senza_chiave_redis_usa_il_baseline_030():
    """Senza `feedback:entry_threshold:S4`, score 0.35 -> NON_CLASSIFICATO.

    Conferma che il fallback al baseline e' la safety net: meglio classificare
    come NON_CLASSIFICATO (e segnalare il problema) che dichiarare un BELOW_GATE
    sulla soglia sbagliata.
    """
    canned = _cand_data()
    with _patch_io(canned), \
         patch("redis.Redis") as mock_cls:
        inst = MagicMock()
        inst.get.return_value = None  # sia per-strategy che legacy assenti
        mock_cls.from_url.return_value = inst
        out = dossier.costruisci_dossier(date(2026, 8, 5), ["AAPL"])

    candidati = out["candidati_miss"]
    assert candidati[0]["causa"] == "NON_CLASSIFICATO"


def test_redis_irraggiungibile_usa_il_baseline_030():
    """Se Redis non risponde, il dossier non si rompe: usa il baseline."""
    canned = _cand_data()
    with _patch_io(canned), \
         patch("redis.Redis") as mock_cls:
        mock_cls.from_url.side_effect = ConnectionError("redis down")
        out = dossier.costruisci_dossier(date(2026, 8, 5), ["AAPL"])

    candidati = out["candidati_miss"]
    assert candidati[0]["causa"] == "NON_CLASSIFICATO"
