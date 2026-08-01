"""Metriche di mercato del dossier: rendimenti, dispersione, mover, copertura news."""

import pytest

from src.analysis.dossier.market import compute_market, compute_miss_candidates


def test_rendimenti_dispersione_e_mover():
    """Return = close/close_prec - 1; sigma = dev.std cross-sectional; mover = |ret| >= soglia."""
    closes = {
        "AAA": (100.0, 110.0),  # +10%  -> mover up
        "BBB": (100.0, 95.0),  # -5%   -> mover down
        "CCC": (100.0, 101.0),  # +1%   -> non mover
    }
    out = compute_market(closes=closes, news_counts={}, soglia_mover=0.03)

    assert out["rendimenti"]["AAA"] == pytest.approx(0.10)
    assert out["rendimenti"]["BBB"] == pytest.approx(-0.05)
    assert out["mover_3pct"] == 2
    assert out["up"] == 1
    assert out["down"] == 1
    # dev.std campionaria di [0.10, -0.05, 0.01]
    assert out["dispersione_sigma"] == pytest.approx(0.0754983, abs=1e-6)


def test_copertura_news_conta_i_simboli_a_zero():
    """watchlist_zero_news = quanti simboli non compaiono affatto o hanno conteggio 0."""
    closes = {"AAA": (100.0, 101.0), "BBB": (100.0, 101.0), "CCC": (100.0, 101.0)}
    out = compute_market(
        closes=closes, news_counts={"AAA": 3, "BBB": 0}, soglia_mover=0.03
    )
    # BBB ha 0 esplicito, CCC e' assente dal dizionario: entrambi contano
    assert out["watchlist_zero_news"] == 2


def test_simbolo_senza_barra_precedente_e_escluso_non_inventato():
    """Un simbolo senza entrambe le barre non produce un rendimento finto."""
    closes = {"AAA": (100.0, 110.0), "BBB": (None, 95.0)}
    out = compute_market(closes=closes, news_counts={}, soglia_mover=0.03)
    assert "BBB" not in out["rendimenti"]
    assert out["simboli_senza_dati"] == ["BBB"]
    assert out["mover_3pct"] == 1


def test_dispersione_none_con_meno_di_due_simboli():
    """La dev.std non e' definita su un solo campione: None, non zero."""
    out = compute_market(
        closes={"AAA": (100.0, 110.0)}, news_counts={}, soglia_mover=0.03
    )
    assert out["dispersione_sigma"] is None


def test_soglia_e_inclusiva():
    """Esattamente sulla soglia conta come mover."""
    out = compute_market(
        closes={"AAA": (100.0, 103.0)}, news_counts={}, soglia_mover=0.03
    )
    assert out["mover_3pct"] == 1


def test_candidati_miss_solo_mover_non_in_portafoglio():
    rendimenti = {"AAA": 0.10, "BBB": -0.05, "CCC": 0.01}
    out = compute_miss_candidates(
        rendimenti=rendimenti,
        news_counts={"AAA": 2},
        segnali={},
        in_portafoglio={"BBB"},
        soglia_mover=0.03,
    )
    simboli = [candidate["symbol"] for candidate in out]
    assert simboli == ["AAA"]  # BBB e' in portafoglio, CCC non e' mover
    assert out[0]["news_count"] == 2
    assert out[0]["in_portafoglio"] is False


def test_candidati_miss_ordinati_per_rendimento_assoluto_decrescente():
    rendimenti = {"AAA": 0.04, "BBB": -0.12, "CCC": 0.08}
    out = compute_miss_candidates(
        rendimenti=rendimenti,
        news_counts={},
        segnali={},
        in_portafoglio=set(),
        soglia_mover=0.03,
    )
    assert [candidate["symbol"] for candidate in out] == ["BBB", "CCC", "AAA"]


def test_candidati_miss_riportano_i_segnali_con_fallback():
    segnali = {"AAA": [{"ora": "16:10", "score": 0.15, "fallback": True}]}
    out = compute_miss_candidates(
        rendimenti={"AAA": 0.10},
        news_counts={"AAA": 1},
        segnali=segnali,
        in_portafoglio=set(),
        soglia_mover=0.03,
    )
    assert out[0]["segnali"] == [{"ora": "16:10", "score": 0.15, "fallback": True}]


def test_candidati_miss_senza_segnali_lista_vuota_non_none():
    out = compute_miss_candidates(
        rendimenti={"AAA": 0.10},
        news_counts={},
        segnali={},
        in_portafoglio=set(),
        soglia_mover=0.03,
    )
    assert out[0]["segnali"] == []
