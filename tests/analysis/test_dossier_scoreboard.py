"""Scoreboard delle due domande di uscita della carta (#278).

Lo scoreboard raccoglie in un colpo solo i numeri che la carta pre-registra:
giorno N/40, quota di giorni con NO_NEWS dominante, P&L economico S4 vs +-200$,
P&L economico S1 vs SPY, P&L economico book, segmenti pre/post #185 e #191.
Espone sempre numeratore e denominatore: la carta decide, lo scoreboard non
decide al posto suo.
"""

from datetime import date

import pytest

from src.analysis.dossier.scoreboard import (
    DEPLOY_185,
    STOPGAP_191,
    compute_scoreboard,
    dominant_miss,
    spy_cumulative_return,
)

W_START = date(2026, 8, 3)


def _md(data, spy=0.0, miss=None, dispersione=0.01):
    return {"data": data, "spy": spy, "miss": miss or {}, "dispersione_sigma": dispersione}


# --- dominant_miss: nessuna forzatura in caso di pareggio ------------------


def test_dominant_miss_restituisce_la_causa_con_piu_occorrenze():
    assert dominant_miss({"NO_NEWS": 3, "THIN_NEUTRAL": 1, "WRONG_SIGN": 0}) == "NO_NEWS"


def test_dominant_miss_pareggio_restituisce_none_non_a_caso():
    """La carta del 2026-08-05 (NO_NEWS=2, BELOW_GATE=2) mostra che il pareggio
    capita: dichiarare una dominante a caso e' il difetto che la pre-registrazione
    vuole evitare."""
    assert dominant_miss({"NO_NEWS": 2, "THIN_NEUTRAL": 2}) is None


def test_dominant_miss_vuota_restituisce_none():
    assert dominant_miss({}) is None


def test_dominant_miss_copre_le_cause_del_ledger_non_solo_la_tassonomia_dossier():
    """market_daily usa WRONG_SIGN/FILTERED/OUT_OF_STRATEGY_SCOPE, che la CAUSE_ORDER
    del classificatore miss_cause non contiene: la dominante li deve considerare."""
    assert dominant_miss({"WRONG_SIGN": 4, "NO_NEWS": 2}) == "WRONG_SIGN"


# --- SPY cumulative return -------------------------------------------------


def test_spy_cumulative_return_e_composto():
    rows = [_md(date(2026, 8, 3), spy=0.01), _md(date(2026, 8, 4), spy=0.02)]
    r = spy_cumulative_return(rows, W_START, date(2026, 8, 4))
    assert r == pytest.approx((1.01 * 1.02) - 1.0)


def test_spy_cumulative_return_ignora_la_riga_pre_finestra():
    """La riga 2026-07-31 del ledger non conta (nota della carta)."""
    rows = [_md(date(2026, 7, 31), spy=0.05), _md(date(2026, 8, 3), spy=0.01)]
    r = spy_cumulative_return(rows, W_START, date(2026, 8, 3))
    assert r == pytest.approx(0.01)


# --- compute_scoreboard: forma generale ------------------------------------


def _economic(cum_s1, cum_s4, cum_contam, capital_s1=10000.0, giorni=None):
    """Economic result minimale. cum_* sono liste allineate a ``giorni``."""
    if giorni is None:
        giorni = [date(2026, 8, 3), date(2026, 8, 7), date(2026, 8, 12)]
    cum = {}
    for s, vals in {"S1": cum_s1, "S4": cum_s4, "CONTAMINAZIONE": cum_contam}.items():
        cum[s] = {giorni[i]: vals[i] for i in range(len(giorni))}
    cum["BOOK"] = {d: cum["S1"][d] + cum["S4"][d] + cum["CONTAMINAZIONE"][d] for d in giorni}
    return {
        "cumulato": cum,
        "capital_base": {"S1": capital_s1, "S4": 0.0, "CONTAMINAZIONE": 0.0, "BOOK": capital_s1},
        "numerosita": {"S1": 1, "S4": 1, "CONTAMINAZIONE": 0},
        "esclusi": 0,
        "missing": {s: {d: 0 for d in giorni} for s in cum},
    }


def test_scoreboard_giorno_n_su_40_con_numeratore_e_denominatore():
    rows = [_md(date(2026, 8, 3)), _md(date(2026, 8, 4)), _md(date(2026, 8, 5))]
    sb = compute_scoreboard(_economic([0, 0, 0], [0, 0, 0], [0, 0, 0]),
                            rows, W_START, date(2026, 8, 5))
    assert sb["giorno"]["n"] == 3
    assert sb["giorno"]["denominatore"] == 40
    assert sb["giorno"]["osservati"] == [date(2026, 8, 3), date(2026, 8, 4), date(2026, 8, 5)]


def test_scoreboard_no_news_dominant_quota_numeratore_denominatore():
    rows = [
        _md(date(2026, 8, 3), miss={"NO_NEWS": 3, "THIN_NEUTRAL": 1}),
        _md(date(2026, 8, 4), miss={"THIN_NEUTRAL": 2, "WRONG_SIGN": 1}),  # dominante THIN_NEUTRAL
        _md(date(2026, 8, 5), miss={"NO_NEWS": 2, "THIN_NEUTRAL": 2}),     # pareggio -> None
    ]
    sb = compute_scoreboard(_economic([0, 0, 0], [0, 0, 0], [0, 0, 0]),
                            rows, W_START, date(2026, 8, 5))
    assert sb["no_news_dominant"]["numerator"] == 1
    assert sb["no_news_dominant"]["denominator"] == 3
    assert sb["no_news_dominant"]["giorni"] == [date(2026, 8, 3)]
    # la carta domanda 1: >=60% dei giorni. 1/3 = 33% -> non ancora superata.
    assert sb["no_news_dominant"]["soglia_carta"] == 0.60


def test_scoreboard_s4_vs_200_dentro_e_fuori():
    rows = [_md(date(2026, 8, 12))]
    # S4 cum a 150 -> dentro +-200
    sb = compute_scoreboard(_economic([0, 0, 0], [0, 0, 150.0], [0, 0, 0]),
                            rows, W_START, date(2026, 8, 12))
    assert sb["s4_vs_200"]["cumulato"] == pytest.approx(150.0)
    assert sb["s4_vs_200"]["within"] is True
    # S4 cum a 250 -> fuori
    sb2 = compute_scoreboard(_economic([0, 0, 0], [0, 0, 250.0], [0, 0, 0]),
                             rows, W_START, date(2026, 8, 12))
    assert sb2["s4_vs_200"]["within"] is False


def test_scoreboard_s1_vs_spy_in_dollari_sulla_base_capitale_s1():
    """SPY benchmark in USD = spy_cum_return * capital_base S1, per confronto dollaro-contro-dollaro."""
    rows = [_md(date(2026, 8, 3), spy=0.01), _md(date(2026, 8, 7), spy=0.02)]
    # capital_base S1 = 10000, spy cum = (1.01*1.02)-1 = 0.0302 -> benchmark 302
    sb = compute_scoreboard(_economic([0, 0, 500.0], [0, 0, 0], [0, 0, 0], capital_s1=10000.0),
                            rows, W_START, date(2026, 8, 12))
    assert sb["s1_vs_spy"]["s1_cumulato"] == pytest.approx(500.0)
    assert sb["s1_vs_spy"]["spy_cum_return"] == pytest.approx((1.01 * 1.02) - 1.0)
    assert sb["s1_vs_spy"]["spy_benchmark_usd"] == pytest.approx(((1.01 * 1.02) - 1.0) * 10000.0)
    assert sb["s1_vs_spy"]["delta_vs_spy"] == pytest.approx(500.0 - ((1.01 * 1.02) - 1.0) * 10000.0)
    assert sb["s1_vs_spy"]["capital_base"] == 10000.0


def test_scoreboard_book_e_la_somma_inclusa_contaminazione():
    rows = [_md(date(2026, 8, 12))]
    sb = compute_scoreboard(_economic([0, 0, 100.0], [0, 0, 80.0], [0, 0, -50.0]),
                            rows, W_START, date(2026, 8, 12))
    assert sb["book"]["cumulato"] == pytest.approx(130.0)
    assert sb["contaminazione"]["cumulato"] == pytest.approx(-50.0)


def test_scoreboard_segmenti_185_s1_pre_post_con_delta():
    """#185: PR #188 deployata 2026-08-07 pre US-open -> 08-07 e' primo giorno post.
    Il segmento riporta il P&L economico S1 guadagnato dentro ogni tratto."""
    giorni = [date(2026, 8, 3), date(2026, 8, 6), date(2026, 8, 7), date(2026, 8, 12)]
    rows = [_md(d) for d in giorni]
    # S1 cum: 08-03=0, 08-06=30 (pre), 08-07=30 (primo post, nessun guadagno), 08-12=100
    sb = compute_scoreboard(_economic([0, 30.0, 30.0, 100.0], [0, 0, 0, 0], [0, 0, 0, 0],
                                      giorni=giorni),
                            rows, W_START, date(2026, 8, 12))
    seg = sb["segmenti"]["#185"]
    assert seg["strategia"] == "S1"
    assert seg["confine"] == DEPLOY_185
    assert seg["pre"]["giorni"] == [date(2026, 8, 3), date(2026, 8, 6)]
    assert seg["pre"]["delta_cum"] == pytest.approx(30.0)
    assert seg["post"]["giorni"] == [date(2026, 8, 7), date(2026, 8, 12)]
    assert seg["post"]["delta_cum"] == pytest.approx(70.0)


def test_scoreboard_segmenti_191_s4_pre_include_08_07_post_dopo():
    """#191: la carta dice 'dal 2026-08-03 al 2026-08-07' gate a 0,45 -> 08-07 e' pre."""
    rows = [_md(date(2026, 8, 3)), _md(date(2026, 8, 7)), _md(date(2026, 8, 12))]
    # S4 cum: 08-03=0, 08-07=-40 (pre, gate 0.45), 08-12=20 (post: +60)
    sb = compute_scoreboard(_economic([0, 0, 0], [0, -40.0, 20.0], [0, 0, 0]),
                            rows, W_START, date(2026, 8, 12))
    seg = sb["segmenti"]["#191"]
    assert seg["strategia"] == "S4"
    assert seg["confine"] == STOPGAP_191
    assert seg["pre"]["giorni"] == [date(2026, 8, 3), date(2026, 8, 7)]  # 08-07 incluso nel pre
    assert seg["pre"]["delta_cum"] == pytest.approx(-40.0)
    assert seg["post"]["giorni"] == [date(2026, 8, 12)]
    assert seg["post"]["delta_cum"] == pytest.approx(60.0)


def test_scoreboard_segmenti_nota_l_ambiguita_del_giorno_08_07():
    """08-07 e' post-#185 (S1 mensile) ma pre-#191 (gate ancora 0.45): il giorno
    cade in segmenti opposti per le due strategie. Lo scoreboard lo documenta."""
    rows = [_md(date(2026, 8, 7))]
    sb = compute_scoreboard(_economic([0, 0, 0], [0, 0, 0], [0, 0, 0]),
                            rows, W_START, date(2026, 8, 7))
    assert "2026-08-07" in sb["segmenti"]["nota_08_07"]


def test_scoreboard_esposizione_numerosita_e_missingness():
    rows = [_md(date(2026, 8, 12))]
    eco = _economic([0, 0, 0], [0, 0, 0], [0, 0, 0])
    eco["missing"]["S4"][date(2026, 8, 12)] = 1
    sb = compute_scoreboard(eco, rows, W_START, date(2026, 8, 12))
    assert sb["numerosita"]["S1"] == 1
    assert sb["numerosita"]["S4"] == 1
    assert sb["numerosita"]["CONTAMINAZIONE"] == 0
    assert sb["missingness"]["S4"][date(2026, 8, 12)] == 1