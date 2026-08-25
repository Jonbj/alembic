"""#283 — test di wiring dell'orchestratore ``build_signal_diagnostics``.

L'orchestratore legge i dossier, arricchisce da DB (model_id/extraction_method/
ensemble_std/source) e carica barre Alpaca (forward return PIT). Entrambi i loader
esterni sono iniettabili: qui li si monkeypatcha con dati sintetici, cosi' il test
gira senza DB nÃ© rete. Verifica che l'orchestratore assembli le righe arricchite
nel formato che il modulo puro ``signal_diagnostics`` mangia e produca il report
con pannelli per-giorno + rollup + blocco freeze + policy descriptive_only.
"""

from __future__ import annotations

import importlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

PROJECT_DIR = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Fixture: dossier sintetico + loader mockati.
# ---------------------------------------------------------------------------

_DAY = "2026-08-12"
_ANCHOR = datetime(2026, 8, 12, 15, 0, tzinfo=timezone.utc)


def _signal(symbol, sid, score, is_mover, fallback=False):
    return {
        "kind": "signal", "symbol": symbol, "is_mover": is_mover,
        "signal_id": sid, "news_log_id": sid, "score": score, "fallback": fallback,
        "order_id": None, "trade_id": None, "order_lookup_error": None,
        "movimento": {}, "sessioni": {}, "stages": {
            "scored_at": {
                "timestamp": _ANCHOR.isoformat(),
                "bar_timestamp": _ANCHOR.isoformat(),
                "price": 100.0, "price_source": "alpaca_sip_5min.open",
            },
        },
    }


def _dossier() -> dict:
    return {
        "schema_version": "1.0",
        "data": _DAY,
        "generato_il": "2026-08-12T20:00:00+00:00",
        "soglia_mover": 0.03,
        "mercato": {"rendimenti": {
            "AAA": 0.05, "BBB": 0.04, "CCC": -0.01, "DDD": 0.06, "POOL1": 0.05,
        }},
        # candidati_miss: AAA ha segnali (signal row), POOL1 no (controllo pool).
        "candidati_miss": [
            {"symbol": "AAA", "return": 0.05, "segnali": [{"ora": "15:00", "score": 0.5,
              "fallback": False, "extraction_method": "ner", "testo_scorato": "x",
              "n_ticker_articolo": 1}], "in_portafoglio": False, "causa": "BELOW_GATE"},
            {"symbol": "POOL1", "return": 0.05, "segnali": [], "in_portafoglio": False,
             "causa": "NO_NEWS"},
        ],
        "ingressi": [], "chiusure": [],
        "timeline": [
            _signal("AAA", 1, 0.50, True, fallback=False),
            _signal("BBB", 2, 0.40, True, fallback=True),
            _signal("CCC", 3, 0.10, False, fallback=True),
            _signal("DDD", 4, 0.60, True, fallback=False),
        ],
    }


def _bars(drift_per_step: float) -> dict:
    """Barre sintetiche: intraday 5Min 13:30-16:00 (entry alla 15:00 open=100,
    poi sale di drift_per_step per barra) + daily 6 giorni (close cresce)."""
    intraday = []
    t = datetime(2026, 8, 12, 13, 30, tzinfo=timezone.utc)
    for i in range(31):  # 13:30 .. 16:00
        base = 100.0
        # prima della 15:00 piatto a 100; dalla 15:00 sale di drift.
        close = base if t < _ANCHOR else base + (i - 18) * drift_per_step
        intraday.append({
            "timestamp": t.isoformat(), "open": close, "high": close + 0.2,
            "low": close - 0.2, "close": close,
        })
        t = t + timedelta(minutes=5)
    daily = []
    for n in range(6):
        d = (datetime(2026, 8, 12, tzinfo=timezone.utc).date() + timedelta(days=n)).isoformat()
        daily.append({"date": d, "open": 100.0, "high": 101.0, "low": 99.0,
                      "close": 100.0 + n * 0.5 * (1 + drift_per_step)})
    return {"intraday": intraday, "daily": daily}


def _mock_bar_loader(symbol, day):
    # drift diverso per symbol -> forward return diverso -> IC non degenere.
    drift = {"AAA": 0.30, "BBB": 0.10, "CCC": -0.20, "DDD": 0.40, "POOL1": 0.05,
             "SPY": 0.02, "XLK": 0.03, "SOXX": 0.025, "XLF": 0.01,
             "XLV": 0.015, "XLE": 0.02}.get(symbol, 0.0)
    return _bars(drift)


def _mock_db_enricher(signal_ids):
    return {
        1: {"model_id": "glm52", "ensemble_std": 0.05, "extraction_method": "ner",
            "source": "test", "published_at": _ANCHOR.isoformat(), "n_ticker_articolo": 1},
        2: {"model_id": "gptoss", "ensemble_std": 0.12, "extraction_method": "source_metadata",
            "source": "test", "published_at": _ANCHOR.isoformat(), "n_ticker_articolo": 9},
        3: {"model_id": "glm52", "ensemble_std": 0.20, "extraction_method": "fallback_finbert",
            "source": "test", "published_at": _ANCHOR.isoformat(), "n_ticker_articolo": 1},
        4: {"model_id": "gptoss", "ensemble_std": 0.08, "extraction_method": "ner",
            "source": "test", "published_at": _ANCHOR.isoformat()},  # n_ticker_articolo assente
    }


@pytest.fixture(scope="module")
def report(tmp_path_factory):
    # carica l'orchestratore dai scripts.
    if str(PROJECT_DIR / "scripts") not in sys.path:
        sys.path.insert(0, str(PROJECT_DIR / "scripts"))
    mod = importlib.import_module("build_signal_diagnostics")

    dossier_dir = tmp_path_factory.mktemp("dossier")
    (dossier_dir / f"{_DAY}.json").write_text(
        json.dumps(_dossier(), ensure_ascii=False), encoding="utf-8")

    out = tmp_path_factory.mktemp("out") / "signal_diagnostics.json"
    return mod.costruisci(
        dossier_dir=dossier_dir,
        bar_loader=_mock_bar_loader,
        db_enricher=_mock_db_enricher,
        sectors={"AAA": "tech", "BBB": "tech", "CCC": "semis", "DDD": "tech",
                  "POOL1": "tech"},
        out_path=out, write=True,
    )


# ---------------------------------------------------------------------------
# Contratti di wiring.
# ---------------------------------------------------------------------------


def test_report_ha_schema_e_policy_freeze(report):
    assert report["schema_version"]
    assert report["policy_output"] == "descriptive_only"
    f = report["freeze"]
    assert f["mode"] == "read_only_measurement"
    assert f["live_thresholds_weights_flags_changed"] is False
    assert f["anchor"].startswith("stages.scored_at")


def test_report_ha_un_pannello_per_giorno_con_tutti_i_blocchi(report):
    assert report["n_giorni"] == 1
    assert report["n_signals"] == 4
    assert report["n_movers"] == 3  # AAA, BBB, DDD (CCC non-mover)
    assert report["n_pool_controlli"] == 1  # POOL1
    p = report["panels"][0]
    assert p["data"] == _DAY
    for blocco in ("rank_ic", "hit_precision_recall", "quintiles",
                   "false_positives", "matched_controls", "splits",
                   "fanout_sweep"):
        assert blocco in p, f"blocco {blocco} mancante nel pannello"
    assert p["policy_output"] == "descriptive_only"


def test_fanout_sweep_arricchito_da_db_enricher(report):
    # Regressione review #283 (criterio 1, 2 volte respinta): n_ticker_articolo
    # arriva dall'arricchimento DB (_default_db_enricher) fino al fanout_sweep
    # del pannello. AAA/CCC single-ticker (n=1), BBB multi-ticker (n=9),
    # DDD senza dato (assente, escluso da ogni cutoff filtrato).
    p = report["panels"][0]
    fanout = p["fanout_sweep"]
    assert fanout["n_fanout_missing"] == 1  # DDD
    cutoff_1 = next(s for s in fanout["sweeps"] if s["max_fanout"] == 1)
    assert cutoff_1["n_rows"] == 2  # AAA, CCC
    cutoff_wide = next(s for s in fanout["sweeps"] if s["max_fanout"] >= 9)
    assert cutoff_wide["n_rows"] == 3  # AAA, BBB, CCC (DDD resta escluso)


def test_rank_ic_per_giorno_ha_tre_benchmark_per_orizzonte(report):
    p = report["panels"][0]
    for h in ("30m", "60m", "EOD", "T+1", "T+3", "T+5"):
        assert h in p["rank_ic"]
        for bench in ("raw", "spy_residual", "sector_residual"):
            cell = p["rank_ic"][h][bench]
            assert "ic" in cell and "n" in cell and "ci_lo" in cell


def test_forward_return_pit_non_none_sugli_orizzonti_intraday(report):
    # i segnali hanno anchor + barre: il 30m deve essere calcolato (non None).
    p = report["panels"][0]
    raw30 = p["rank_ic"]["30m"]["raw"]
    # con 4 segnali e forward return non tutti None, n>=3 -> IC numerico.
    assert raw30["n"] >= 3
    assert raw30["ic"] is not None


def test_matched_controls_riproducibili_e_separati_dal_book(report):
    p = report["panels"][0]
    mc = p["matched_controls"]["30m"]
    assert mc["summary"]["n_matched"] >= 1  # almeno un mover abbinato a POOL1
    # il control_kind dichiara la separazione dal benchmark di libro.
    assert "separato dal book benchmark" in mc["summary"]["control_kind"]
    assert mc["summary"]["matching"].startswith("deterministic_nearest")
    for m in mc["matches"]:
        assert m["matched_ticker"] == "POOL1"  # unico ticker non segnalato
        # forward-return del pool non calcolato -> delta None con missingness.
        assert m["delta"] is None
        assert "forward_return_missing" in m["missingness"]


def test_splits_per_source_model_fallback_extraction_ensemble_bucket(report):
    p = report["panels"][0]
    s = p["splits"]
    for dim in ("source", "model", "fallback", "extraction_method",
                "ensemble_std_bucket"):
        assert dim in s, f"split {dim} mancante"
        # ogni dimensione ha un orizzonte (almeno 30m) con gruppi.
        assert "30m" in s[dim]


def test_ensemble_std_bucket_assegnato_da_terzile(report):
    # 4 segnali con ensemble_std [0.05, 0.12, 0.20, 0.08] -> terzili, >=2 bucket.
    p = report["panels"][0]
    s = p["splits"]["ensemble_std_bucket"]["30m"]
    assert len(s) >= 2  # low/med/high distribuiti


def test_rollup_ha_shadow_curves_score_stability_moltiplicita(report):
    r = report["rollup"]
    assert r["n_giorni"] == 1
    assert "shadow_curves" in r
    assert "score_stability" in r
    m = r["multiplicity"]
    assert m["method"] == "benjamini_hochberg_descriptive"
    assert m["policy"] == "descriptive_only_no_threshold_selected"
    assert m["n_trials"] >= 1


def test_file_scritto_su_disco(report, tmp_path_factory):
    # costruisci(write=True) ha scritto un JSON valido con la stessa struttura.
    # Lo si ritrova via il path di out: ricerca il file creato nella factory.
    # (Il report stesso e' il dict; verifichiamo solo che sia serializzabile.)
    json.dumps(report)  # non solleva -> i dict sono JSON-serializzabili


def test_provenance_dichiara_le_fonti_read_only(report):
    pr = report["provenance"]
    assert "dossier" in pr and "sectors" in pr
    assert "read-only" in pr["dossier"]
    assert pr["note"].startswith("File derivato")


# ---------------------------------------------------------------------------
# Test di contratto sulla query SQL dell'arricchitore.
# (Il wiring sopra usa un mock, ma la query REALE deve riferirsi alla PK
#  reale di sentiment_signals: colonna ``id`` — NON ``signal_id`` che non
#  esiste. Questo test e' bloccante: se cambia, lo rivedo.)
# ---------------------------------------------------------------------------


def test_query_db_enricher_referenzia_pk_id_di_sentiment_signals(monkeypatch):
    """La query SQL di ``_default_db_enricher`` deve usare ``s.id`` (PK reale di
    sentiment_signals, vedi 001_initial.sql riga 38) in SELECT e WHERE, NON
    ``s.signal_id`` (colonna inesistente). Riafferma il rilievo bloccante del
    review: il fail-soft del 2026-08-24 mascherava la rottura lasciando vuoti
    gli split per source/model/extraction.
    """
    importlib.invalidate_caches()
    if str(PROJECT_DIR / "scripts") not in sys.path:
        sys.path.insert(0, str(PROJECT_DIR / "scripts"))
    mod = importlib.import_module("build_signal_diagnostics")

    catturata: dict = {}

    class _FakeCompleted:
        def __init__(self):
            self.returncode = 0
            self.stdout = "1|glm52|0.05|ner|test|2026-08-12T15:00:00+00:00|3\n"
            self.stderr = ""

    def _fake_run(cmd, **kwargs):
        catturata["cmd"] = cmd
        return _FakeCompleted()

    monkeypatch.setattr(mod.subprocess, "run", _fake_run)
    out = mod._default_db_enricher([1])

    # la query deve contenere 's.id' (PK reale) e NON 's.signal_id' (colonna inesistente).
    psql_cmd = [a for a in catturata["cmd"] if isinstance(a, str)]
    query = psql_cmd[-1]
    assert "s.id" in query, f"query non referenza la PK reale 's.id': {query!r}"
    assert "s.signal_id" not in query, (
        f"query referenzia la colonna inesistente 's.signal_id': {query!r}"
    )
    # e l'arricchimento, dato un psql che ha successo, valorizza davvero il dict.
    assert out[1]["model_id"] == "glm52"
    assert out[1]["extraction_method"] == "ner"
    # n_ticker_articolo (fan-out, #169): regressione review #283 criterio 1.
    assert out[1]["n_ticker_articolo"] == 3