"""#280: il dossier pubblica opportunity_v2 (stimatore parallelo) per ogni candidato.

Lo stimatore e' deterministico e versionato; la serie legacy (costo_usd del
prompt, findings.json) resta intatta. Qui si verifica che l'orchestratore attacchi
`opportunity_v2` a ogni candidato miss con i campi obbligatori, che i ribassi non
detenuti in book long-only abbiano accessible/net = 0.0 verificato (non null), e
che i rialzi senza barre intraday (#277 non in main) abbiano accessible None con
missingness esplicita ma gross calcolato.
"""

from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

import scripts.alpha_miner_dossier as dossier
from src.analysis.dossier.opportunity import ESTIMATOR_VERSION


def _cand_data():
    """Due mover non detenuti: AAPL +7% (rialzista), META -5% (ribassista)."""
    return {
        "barre": {
            "AAPL": {"open": 100.0, "high": 110.0, "low": 99.0, "close": 107.0,
                     "close_prec": 100.0},
            "META": {"open": 195.0, "high": 196.0, "low": 184.0, "close": 184.0,
                     "close_prec": 195.0},
        },
        "news_counts": {"AAPL": 1, "META": 1},
        "segnali_rows": [
            ["AAPL", "15:30", "0.35", "f", "org_lookup", "AAPL hits record high", "1"],
            ["META", "15:30", "-0.35", "f", "org_lookup", "META slides on ad miss", "1"],
        ],
        "in_portafoglio_rows": [],
        "ingressi_rows": [],
        "chiusure_rows": [],
        "chiusi_storici_rows": [],
    }


def _patch_io(canned):
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
    stack.enter_context(patch.object(dossier, "_watchlist", return_value=["AAPL", "META"]))
    # timeline PIT (#291): fuori scope per questi test opportunity_v2
    stack.enter_context(patch.object(dossier, "_timeline_eventi", return_value=[]))
    cutoff = datetime(2026, 8, 12, 23, 59, tzinfo=timezone.utc)
    stack.enter_context(
        patch.object(dossier, "_barre_intraday", return_value=({}, cutoff))
    )
    return stack


def _build():
    canned = _cand_data()
    with _patch_io(canned), patch("redis.Redis") as mock_cls:
        inst = MagicMock()
        inst.get.return_value = "0.30"
        mock_cls.from_url.return_value = inst
        return dossier.costruisci_dossier(date(2026, 8, 12), ["AAPL", "META"])


def _by_symbol(out, sym):
    return next(c for c in out["candidati_miss"] if c["symbol"] == sym)


def test_ogni_candidato_ha_opportunity_v2_con_campi_obbligatori():
    out = _build()
    for c in out["candidati_miss"]:
        assert "opportunity_v2" in c, f"{c['symbol']} senza opportunity_v2"
        ov = c["opportunity_v2"]
        assert ov["estimator_version"] == ESTIMATOR_VERSION
        for campo in ("cutoff", "entry", "exit", "size", "vincoli", "costi", "formula"):
            assert campo in ov, f"{c['symbol']}: manca {campo}"


def test_rialzista_senza_intraday_gross_calcolato_accessible_null_con_missingness():
    out = _build()
    ov = _by_symbol(out, "AAPL")["opportunity_v2"]
    # gross = |+7%| x 2200 = 154
    assert ov["gross_opportunity_usd"] == pytest.approx(154.0)
    # niente barre intraday (#277): accessible None, ma NON confuso con gross
    assert ov["accessible_opportunity_usd"] is None
    assert ov["net_opportunity_usd"] is None
    assert "intraday_bars_not_available_eligible_cycle_unpriced" in ov["missingness"]
    assert ov["confidenza"] == "congetturale"


def test_ribassista_non_detenuto_long_only_zero_verificato_non_null():
    out = _build()
    ov = _by_symbol(out, "META")["opportunity_v2"]
    # long-only: il ribasso non detenuto non era catturabile -> 0.0 verificato
    assert ov["accessible_opportunity_usd"] == 0.0
    assert ov["net_opportunity_usd"] == 0.0
    assert ov["costi"]["total_usd"] == 0.0
    assert ov["entry"]["missing_reason"] == "long_only_no_short_downside_not_held"
    # gross resta il full move (directional accuracy), ma non e' accessible
    assert ov["gross_opportunity_usd"] is not None and ov["gross_opportunity_usd"] > 0.0


def test_fungibilita_none_e_size_dichiarata():
    out = _build()
    ov = _by_symbol(out, "AAPL")["opportunity_v2"]
    assert ov["fungibility_rule"].startswith("none")
    assert ov["size"]["usd"] == 2200.0
    assert ov["size"]["slot_fraction"] is not None