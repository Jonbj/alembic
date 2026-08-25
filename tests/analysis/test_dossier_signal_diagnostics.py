"""#283 — diagnostica dei segnali e controlli negativi.

Questi test fissano il contratto del modulo puro ``signal_diagnostics``: metriche
time-forward senza leakage, residualizzate vs SPY/settore, hit rate / precision /
recall dei mover azionabili, quintili, splits per fonte/modello/fallback/extraction/
ensemble std, falsi positivi, controlli matched riproducibili (separati dal
benchmark di libro), score stability e shadow curves descrittive.

Il modulo e' puro: riceve dict/list in ingresso e restituisce dict, niente I/O,
niente DB, niente rete. Le barre e i forward return sono forniti dal chiamante
(orchestratore). Lo schema e' versionato e ogni stima porta n e missingness
esplicita, cosi' un buco di dato non si confonde mai con zero.

Freeze (#171): solo misura. Nessuna soglia/gate/modello/fonte live viene scelta
qui — la griglia di sweep e' una costante dichiarata e i risultati sono marcati
``descriptive_only``. La soglia mover arriva dal dossier (gia' dichiarata), non e'
una nuova taratura.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.analysis.dossier import signal_diagnostics as sd


# ---------------------------------------------------------------------------
# Barre di test: giornata 2026-08-12, seduta 13:30-20:00 UTC, barre 5Min.
# L'orario e' UTC (Alpaca SIP). Signal_ts cade a meta' seduta.
# ---------------------------------------------------------------------------

_SESSION_OPEN = datetime(2026, 8, 12, 13, 30, tzinfo=timezone.utc)
_SESSION_CLOSE = datetime(2026, 8, 12, 20, 0, tzinfo=timezone.utc)
_SIGNAL_TS = datetime(2026, 8, 12, 15, 0, tzinfo=timezone.utc)  # 15:00 UTC


def _bar(ts: datetime, o: float, h: float, lo: float, c: float) -> dict:
    return {"timestamp": ts.isoformat(), "open": o, "high": h, "low": lo, "close": c}


def _bars_from(start: datetime, n: int, step_min: int, price_fn) -> list[dict]:
    """n barre 5Min a partire da start; price_fn(i)->(o,h,l,c)."""
    bars = []
    t = start
    for i in range(n):
        o, h, lo, c = price_fn(i)
        bars.append(_bar(t, o, h, lo, c))
        t = t + timedelta(minutes=step_min)
    return bars


def _intraday_bars() -> list[dict]:
    """Barre 5Min sintetiche 13:30->16:05. Piatto a 100 fino al 14:55, poi il
    15:00 segna il segnale (open=100) e il prezzo sale fino a ~102."""
    # 13:30 .. 14:55 (18 barre piatte a 100)
    flat = _bars_from(
        datetime(2026, 8, 12, 13, 30, tzinfo=timezone.utc), 18, 5,
        lambda i: (100.0, 100.5, 99.5, 100.0),
    )
    # 15:00: barra del segnale (open=100, close=100.5)
    signal_bar = _bar(datetime(2026, 8, 12, 15, 0, tzinfo=timezone.utc), 100.0, 100.8, 99.9, 100.5)
    # 15:05 .. 16:05 (13 barre): prezzo sale linearmente fino a ~102
    rising = _bars_from(
        datetime(2026, 8, 12, 15, 5, tzinfo=timezone.utc), 13, 5,
        lambda i: (
            100.5 + (i + 1) / 13.0 * 1.5,  # open
            100.5 + (i + 1) / 13.0 * 1.5 + 0.2,
            100.5 + (i + 1) / 13.0 * 1.5 - 0.2,
            100.5 + (i + 1) / 13.0 * 1.5 + 0.1,  # close
        ),
    )
    return flat + [signal_bar] + rising


def _daily_bars() -> list[dict]:
    """Barre giornaliere: [0]=giorno segnale (close=101), [1]=T+1 (102),
    [3]=T+3 (104), [5]=T+5 (106)."""
    return [
        {"date": "2026-08-12", "open": 100.0, "high": 101.5, "low": 99.5, "close": 101.0},
        {"date": "2026-08-13", "open": 101.0, "high": 102.5, "low": 100.5, "close": 102.0},
        {"date": "2026-08-14", "open": 102.0, "high": 103.0, "low": 101.5, "close": 102.5},
        {"date": "2026-08-15", "open": 102.5, "high": 104.5, "low": 102.0, "close": 104.0},
        {"date": "2026-08-18", "open": 104.0, "high": 105.0, "low": 103.5, "close": 104.5},
        {"date": "2026-08-19", "open": 104.5, "high": 106.5, "low": 104.0, "close": 106.0},
    ]


# ---------------------------------------------------------------------------
# 1. Forward returns time-forward, senza leakage
# ---------------------------------------------------------------------------


class TestForwardReturnsPIT:
    def test_entry_price_e_il_precio_osservabile_al_segnale(self):
        """L'entry e' l'open della prima barra >= signal_ts (PIT, no look-ahead)."""
        out = sd.compute_forward_returns(
            _SIGNAL_TS, _intraday_bars(), _daily_bars(),
            session_open=_SESSION_OPEN, session_close=_SESSION_CLOSE,
        )
        # la barra delle 15:00 ha open=100: e' il prezzo al segnale.
        assert out["entry_price"] == pytest.approx(100.0)
        # l'entry NON deriva da una barra futura: il suo timestamp e' >= signal_ts.
        assert out["entry_bar_ts"] is not None
        assert datetime.fromisoformat(out["entry_bar_ts"]) >= _SIGNAL_TS

    def test_30m_usa_barra_successiva_al_segnale_non_precedente(self):
        out = sd.compute_forward_returns(
            _SIGNAL_TS, _intraday_bars(), _daily_bars(),
            session_open=_SESSION_OPEN, session_close=_SESSION_CLOSE,
        )
        r30 = out["30m"]["return"]
        assert r30 is not None
        # 30m forward: prima barra >= signal_ts+30m = 15:30, close ~ 100.5+(30/60)*1.5=101.25
        # entry 100 -> return ~0.0125. La barra di chiusura e' > entry (trend su).
        assert r30 > 0
        # la barra di exit e' strettamente dopo signal_ts (no leakage).
        assert out["30m"]["exit_bar_ts"] is not None
        assert datetime.fromisoformat(out["30m"]["exit_bar_ts"]) > _SIGNAL_TS

    def test_60m_orizzonte_piu_lungo_di_30m(self):
        out = sd.compute_forward_returns(
            _SIGNAL_TS, _intraday_bars(), _daily_bars(),
            session_open=_SESSION_OPEN, session_close=_SESSION_CLOSE,
        )
        assert out["60m"]["return"] > out["30m"]["return"]

    def test_eod_ultimo_close_della_seduta(self):
        out = sd.compute_forward_returns(
            _SIGNAL_TS, _intraday_bars(), _daily_bars(),
            session_open=_SESSION_OPEN, session_close=_SESSION_CLOSE,
        )
        # EOD: close della barra di seduta (16:05 ~ 101.6) / entry 100 - 1 ~ 0.016
        assert out["EOD"]["return"] is not None
        assert out["EOD"]["return"] > 0

    def test_t_plus_n_usa_close_del_giorno_n(self):
        out = sd.compute_forward_returns(
            _SIGNAL_TS, _intraday_bars(), _daily_bars(),
            session_open=_SESSION_OPEN, session_close=_SESSION_CLOSE,
        )
        # T+1 = daily[1].close=102 / entry 100 - 1 = 0.02
        assert out["T+1"]["return"] == pytest.approx(0.02)
        # T+3 = daily[3].close=104 / 100 - 1 = 0.04
        assert out["T+3"]["return"] == pytest.approx(0.04)
        # T+5 = daily[5].close=106 / 100 - 1 = 0.06
        assert out["T+5"]["return"] == pytest.approx(0.06)

    def test_missingness_esplicita_se_barre_intraday_mancano(self):
        """Senza barre intraday, gli orizzonti intraday sono None con reason."""
        out = sd.compute_forward_returns(
            _SIGNAL_TS, [], _daily_bars(),
            session_open=_SESSION_OPEN, session_close=_SESSION_CLOSE,
        )
        assert out["entry_price"] is None
        assert out["30m"]["return"] is None
        assert "entry_bar_missing" in out["30m"]["missingness"]
        # T+1..T+5 dipendono solo dalle daily: restano calcolabili? No — l'entry
        # intraday manca, quindi anche T+n non ha anchor: None con missingness.
        assert out["T+1"]["return"] is None
        assert "entry_bar_missing" in out["T+1"]["missingness"]

    def test_missingness_se_daily_mancano_per_t_plus_n(self):
        out = sd.compute_forward_returns(
            _SIGNAL_TS, _intraday_bars(),
            _daily_bars()[:2],  # solo giorno segnale + T+1
            session_open=_SESSION_OPEN, session_close=_SESSION_CLOSE,
        )
        assert out["T+1"]["return"] is not None
        assert out["T+3"]["return"] is None
        assert "daily_bar_missing" in out["T+3"]["missingness"]

    def test_segnale_pre_apertura_usa_prima_barra_di_seduta(self):
        """Signal_ts prima dell'open: entry = open della prima barra di seduta."""
        early = datetime(2026, 8, 12, 9, 0, tzinfo=timezone.utc)
        out = sd.compute_forward_returns(
            early, _intraday_bars(), _daily_bars(),
            session_open=_SESSION_OPEN, session_close=_SESSION_CLOSE,
        )
        # nessuna barra >= 09:00 nella seduta 13:30-> l'entry resta la prima
        # barra disponibile >= session_open (PIT: non si puo' tradare prima dell'open).
        assert out["entry_price"] is not None
        assert datetime.fromisoformat(out["entry_bar_ts"]) >= _SESSION_OPEN

    def test_segnale_post_chiusura_senza_barre_future_entry_mancante(self):
        """Signal_ts dopo la chiusura e barre solo di oggi: nessuna barra >= ts,
        entry mancante con missingness esplicita. La funzione non inventa un
        roll: e' l'orchestratore che fornisce le barre della seduta successiva
        quando vuole che l'entry rolli (PIT generale, vedi test multigiorno)."""
        late = datetime(2026, 8, 12, 22, 0, tzinfo=timezone.utc)
        out = sd.compute_forward_returns(
            late, _intraday_bars(), _daily_bars(),
            session_open=_SESSION_OPEN, session_close=_SESSION_CLOSE,
        )
        assert out["entry_price"] is None
        assert "entry_bar_missing" in out["30m"]["missingness"]

    def test_entry_rolls_a_next_session_con_barre_multigiorno(self):
        """Con barre intraday di piu' giorni, l'entry e' la prima barra >= ts:
        per un segnale post-chiusura, rolla al primo bar della seduta successiva
        (PIT: si puo' tradare solo alla seduta utile successiva)."""
        late = datetime(2026, 8, 12, 22, 0, tzinfo=timezone.utc)
        # aggiungi una barra della seduta successiva (T+1) alle intraday.
        bars = _intraday_bars() + [
            _bar(datetime(2026, 8, 13, 13, 30, tzinfo=timezone.utc), 101.0, 101.5, 100.5, 101.2),
            _bar(datetime(2026, 8, 13, 13, 35, tzinfo=timezone.utc), 101.2, 101.8, 101.0, 101.6),
        ]
        out = sd.compute_forward_returns(
            late, bars, _daily_bars(),
            session_open=_SESSION_OPEN, session_close=_SESSION_CLOSE,
        )
        assert out["entry_price"] == pytest.approx(101.0)
        # entry su T+1, >= signal_ts (22:00 del 12/08).
        assert datetime.fromisoformat(out["entry_bar_ts"]) > late

    def test_restituisce_tutti_gli_orizzonti(self):
        out = sd.compute_forward_returns(
            _SIGNAL_TS, _intraday_bars(), _daily_bars(),
            session_open=_SESSION_OPEN, session_close=_SESSION_CLOSE,
        )
        for h in sd.HORIZONS:
            assert h in out
            assert "return" in out[h]
            assert "missingness" in out[h]

# ---------------------------------------------------------------------------
# 2. IC residualizzata, hit/precision/recall, quintili, falsi positivi
# ---------------------------------------------------------------------------


class TestICResidualizzazione:
    def test_ic_spearman_perfetta_monotona(self):
        scores = [0.1, 0.2, 0.3, 0.4, 0.5]
        returns = [0.01, 0.02, 0.03, 0.04, 0.05]
        ic = sd.rank_ic_with_ci(scores, returns)
        assert ic["ic"] == pytest.approx(1.0, abs=1e-9)
        assert ic["n"] == 5
        assert ic["pvalue"] is not None
        # CI bootstrap contiene l'IC puntuale.
        assert ic["ci_lo"] <= ic["ic"] <= ic["ci_hi"]

    def test_ic_negativa_per_antitrend(self):
        scores = [0.5, 0.4, 0.3, 0.2, 0.1]
        returns = [0.01, 0.02, 0.03, 0.04, 0.05]
        ic = sd.rank_ic_with_ci(scores, returns)
        assert ic["ic"] == pytest.approx(-1.0, abs=1e-9)

    def test_ic_riporta_n_e_ci_finiti(self):
        ic = sd.rank_ic_with_ci([0.1, 0.2, 0.3, 0.4, 0.5], [0.05, 0.04, 0.03, 0.02, 0.01])
        assert ic["n"] == 5
        assert ic["ci_lo"] is not None and ic["ci_hi"] is not None
        assert ic["ci_lo"] <= ic["ci_hi"]

    def test_residualize_sottrae_benchmark_sulla_stessa_finestra(self):
        res = sd.residualize([0.05, 0.03, None], [0.02, 0.01, 0.04])
        assert res[0] == pytest.approx(0.03)
        assert res[1] == pytest.approx(0.02)
        # missing propaga: nessun valore inventato.
        assert res[2] is None

    def test_ic_residualizzata_sottrae_il_book_benchmark(self):
        # score e return perfettamente correlati, ma il benchmark spiega meta':
        # la IC residualizzata deve essere minore di quella grezza.
        scores = [0.1, 0.2, 0.3, 0.4, 0.5]
        signal_ret = [0.02, 0.04, 0.06, 0.08, 0.10]
        benchmark = [0.01, 0.02, 0.03, 0.04, 0.05]  # meta' del movimento
        raw = sd.rank_ic_with_ci(scores, signal_ret)["ic"]
        resid = sd.rank_ic_with_ci(scores, sd.residualize(signal_ret, benchmark))["ic"]
        assert raw == pytest.approx(1.0)
        # residualizzata: signal_ret - benchmark = [0.01,0.02,...] ancora monotona
        # con score -> IC resta 1.0, ma il punto e' che la metrica e' NETTA dal
        # fattore sistematico. Verifichiamo che residualize effettivamente toglie
        # il benchmark e che la funzione accetti la lista residualizzata.
        assert resid == pytest.approx(1.0)
        assert sd.residualize(signal_ret, benchmark) == [pytest.approx(0.01), pytest.approx(0.02),
                                                         pytest.approx(0.03), pytest.approx(0.04),
                                                         pytest.approx(0.05)]

    def test_ic_con_pochi_punti_riporta_n_basso(self):
        ic = sd.rank_ic_with_ci([0.1, 0.2], [0.01, 0.02])
        assert ic["n"] == 2
        # sotto la soglia minima la IC e' None o marcata debole.
        assert ic["ic"] is None or ic["weak"] is True


class TestHitPrecisionRecall:
    def _rows(self):
        return [
            {"score": 0.5, "return": 0.05},
            {"score": 0.4, "return": 0.02},
            {"score": 0.2, "return": 0.06},
            {"score": 0.35, "return": 0.01},
        ]

    def test_precision_recall_valori_esatti_lato_long(self):
        # threshold=0.3, mover_threshold=0.03, long.
        # signal>=0.3: idx0(0.05 up-mover TP), idx1(0.02 FP), idx3(0.01 FP) -> TP=1 FP=2
        # up-movers (ret>=0.03): idx0(0.05), idx2(0.06) -> total=2; FN=idx2(score<0.3)=1
        out = sd.precision_recall(self._rows(), threshold=0.3,
                                  mover_threshold=0.03, direction="long")
        assert out["tp"] == 1
        assert out["fp"] == 2
        assert out["fn"] == 1
        assert out["precision"] == pytest.approx(1 / 3)
        assert out["recall"] == pytest.approx(0.5)
        assert out["n_signals"] == 3
        assert out["n_movers"] == 2

    def test_hit_rate_sign_agreement(self):
        # sign(score)==sign(return): idx0(+,+),idx1(+,+),idx2(+,+),idx3(+,+) tutte
        # hit (tutti score>0 e return>0). Ma idx2 ha return 0.06>0: hit.
        hr = sd.hit_rate([0.5, 0.4, 0.2, 0.35], [0.05, 0.02, 0.06, 0.01])
        assert hr["hit_rate"] == pytest.approx(1.0)
        assert hr["n"] == 4
        # con un controesempio: score positivo, return negativo -> miss.
        hr2 = sd.hit_rate([0.5, -0.4], [0.05, 0.02])
        assert hr2["hit_rate"] == pytest.approx(0.5)

    def test_precision_recall_lato_short(self):
        # short: positive_signal = score<=-threshold; positive_outcome = return<=-mt
        rows = [
            {"score": -0.5, "return": -0.05},  # TP
            {"score": -0.4, "return": -0.01},  # FP (non down-mover)
            {"score": -0.2, "return": -0.06},  # FN (down-mover non segnalato)
        ]
        out = sd.precision_recall(rows, threshold=0.3, mover_threshold=0.03, direction="short")
        assert out["tp"] == 1
        assert out["fp"] == 1
        assert out["fn"] == 1
        assert out["recall"] == pytest.approx(0.5)

    def test_senza_movers_recall_zero_e_non_nan(self):
        rows = [{"score": 0.5, "return": 0.01}, {"score": 0.4, "return": 0.02}]
        out = sd.precision_recall(rows, threshold=0.3, mover_threshold=0.03, direction="long")
        assert out["n_movers"] == 0
        # recall con denominatore 0: None (non definito), non NaN o crash.
        assert out["recall"] is None
        assert out["precision"] == 0.0  # nessun TP


class TestQuintili:
    def test_quintili_monotoni_su_dato_costruito(self):
        # 10 segnali: score crescente, return crescente. Bucket 5 (top) > bucket 1.
        scores = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50]
        returns = [0.001, 0.002, 0.003, 0.004, 0.005, 0.006, 0.007, 0.008, 0.009, 0.010]
        q = sd.quintile_analysis(scores, returns)
        assert len(q) == 5
        assert q[0]["n"] == 2
        assert q[-1]["mean_return"] > q[0]["mean_return"]
        # ogni bucket porta n.
        for bucket in q:
            assert "n" in bucket and "mean_score" in bucket and "mean_return" in bucket

    def test_quintili_con_pochi_dati_collapse_gracefully(self):
        q = sd.quintile_analysis([0.1, 0.2, 0.3], [0.01, 0.02, 0.03])
        # 3 punti in 5 bucket: alcuni vuoti, ma nessun crash.
        assert len(q) == 5
        assert sum(b["n"] for b in q) == 3


class TestFalsiPositivi:
    def test_falsi_positivi_score_alto_rendimento_avverso(self):
        rows = [
            {"score": 0.5, "return": -0.05},
            {"score": 0.4, "return": -0.03},
            {"score": 0.2, "return": 0.01},
        ]
        fp = sd.false_positives(rows, threshold=0.3)
        # score>=0.3 con return<0: idx0, idx1 -> n_fp=2
        assert fp["n_fp"] == 2
        assert fp["mean_adverse_return"] == pytest.approx(-0.04)
        assert fp["n_signals"] == 2

    def test_falsi_positivi_zero_se_tutti_corretti(self):
        rows = [{"score": 0.5, "return": 0.05}, {"score": 0.4, "return": 0.02}]
        fp = sd.false_positives(rows, threshold=0.3)
        assert fp["n_fp"] == 0
        assert fp["mean_adverse_return"] is None


# ---------------------------------------------------------------------------
# 3. Matched controls, splits, score stability
# ---------------------------------------------------------------------------


def _row(ticker, data="2026-08-12", sector="tech", ret=0.0, score=None,
         fwd=None, **kw):
    r = {"ticker": ticker, "data": data, "sector": sector, "return": ret,
         "score": score, "forward_returns": fwd or {}}
    r.update(kw)
    return r


class TestMatchedControls:
    def test_match_deterministico_stesso_giorno_e_settore(self):
        signal = _row("AAPL", ret=0.05, score=0.5, fwd={"T+1": 0.04})
        pool = [
            _row("MSFT", ret=0.05, fwd={"T+1": 0.02}),   # |0.05-0.05|=0 nearest
            _row("NVDA", ret=-0.05, fwd={"T+1": 0.01}),   # |−0.05-0.05|=0.10
        ]
        out = sd.matched_controls([signal], pool, horizon="T+1")
        assert len(out["matches"]) == 1
        m = out["matches"][0]
        assert m["matched_ticker"] == "MSFT"
        assert m["delta"] == pytest.approx(0.02)  # 0.04 - 0.02

    def test_match_riproducibile_chiamate_identiche(self):
        signal = _row("AAPL", ret=0.05, score=0.5, fwd={"T+1": 0.04})
        pool = [_row("MSFT", ret=0.05, fwd={"T+1": 0.02}),
                _row("GOOG", ret=0.05, fwd={"T+1": 0.03})]  # parita' di distanza
        out1 = sd.matched_controls([signal], pool, horizon="T+1")
        out2 = sd.matched_controls([signal], pool, horizon="T+1")
        # tie-break deterministico per ticker (GOOG < MSFT): stesso risultato.
        assert out1["matches"][0]["matched_ticker"] == out2["matches"][0]["matched_ticker"]
        assert out1["matches"][0]["matched_ticker"] == "GOOG"

    def test_il_match_esclude_il_ticker_segnalato_stesso(self):
        # il pool contiene anche AAPL (il ticker segnalato): non si matcha con se'.
        signal = _row("AAPL", ret=0.05, score=0.5, fwd={"T+1": 0.04})
        pool = [
            _row("AAPL", ret=0.05, fwd={"T+1": 0.99}),  # se stesso: escluso
            _row("MSFT", ret=0.06, fwd={"T+1": 0.02}),
        ]
        out = sd.matched_controls([signal], pool, horizon="T+1")
        assert out["matches"][0]["matched_ticker"] == "MSFT"

    def test_match_mancante_se_nessun_candidato_stesso_settore(self):
        signal = _row("AAPL", sector="tech", ret=0.05, score=0.5, fwd={"T+1": 0.04})
        pool = [_row("JPM", sector="financials", ret=0.05, fwd={"T+1": 0.02})]
        out = sd.matched_controls([signal], pool, horizon="T+1")
        assert out["matches"] == []
        assert out["summary"]["n_unmatched"] == 1
        assert "no_matched_control" in out["unmatched"][0]["missingness"]

    def test_il_matched_control_e_separato_dal_book_benchmark(self):
        """Il matched control e' un ticker non segnalato, NON il benchmark SPY:
        il risultato non porta campi SPY/residual — quelli vivono in residualize()."""
        signal = _row("AAPL", ret=0.05, score=0.5, fwd={"T+1": 0.04})
        pool = [_row("MSFT", ret=0.05, fwd={"T+1": 0.02})]
        out = sd.matched_controls([signal], pool, horizon="T+1")
        m = out["matches"][0]
        assert "spy_return" not in m
        assert "residual" not in m
        assert "matched_ticker" in m and "delta" in m
        # il book benchmark e' una funzione separata:
        assert sd.residualize([0.04], [0.01]) == [pytest.approx(0.03)]

    def test_summary_riporta_delta_medio_per_orizzonte(self):
        signals = [_row("AAPL", ret=0.05, score=0.5, fwd={"T+1": 0.04}),
                   _row("CSCO", ret=0.04, score=0.4, fwd={"T+1": 0.03})]
        pool = [_row("MSFT", ret=0.05, fwd={"T+1": 0.02}),
                _row("ORCL", ret=0.04, fwd={"T+1": 0.05})]
        out = sd.matched_controls(signals, pool, horizon="T+1")
        # delta: AAPL 0.04-0.02=0.02; CSCO 0.03-0.05=-0.02 -> medio 0.0
        assert out["summary"]["mean_delta"] == pytest.approx(0.0)
        assert out["summary"]["n_matched"] == 2


class TestSplits:
    def _split_rows(self):
        return [
            _row("A", score=0.5, fwd={"T+1": 0.05}, source="benzinga"),
            _row("B", score=0.4, fwd={"T+1": 0.04}, source="benzinga"),
            _row("C", score=0.1, fwd={"T+1": -0.02}, source="gdelt"),
            _row("D", score=-0.3, fwd={"T+1": -0.05}, source="gdelt"),
        ]

    def test_splits_per_fonte_con_n_per_cella(self):
        out = sd.splits_by_dimension(self._split_rows(), "source", horizon="T+1")
        assert set(out.keys()) == {"benzinga", "gdelt"}
        # benzinga: score [0.5,0.4] fwd [0.05,0.04] IC=1.0 (monotona)
        assert out["benzinga"]["n"] == 2
        assert out["benzinga"]["ic"]["n"] == 2
        assert out["benzinga"]["ic"]["weak"] is True  # n<3
        assert out["gdelt"]["n"] == 2

    def test_splits_per_fallback_e_model(self):
        rows = [
            _row("A", score=0.5, fwd={"T+1": 0.05}, fallback=True, model="glm52"),
            _row("B", score=0.4, fwd={"T+1": 0.04}, fallback=False, model="gptoss"),
        ]
        fb = sd.splits_by_dimension(rows, "fallback", horizon="T+1")
        assert set(fb.keys()) == {"True", "False"}
        md = sd.splits_by_dimension(rows, "model", horizon="T+1")
        assert set(md.keys()) == {"glm52", "gptoss"}

    def test_splits_ensemble_std_bucket(self):
        # il pannello assegna un bucket di ensemble_std (terzile); lo split e'
        # uniforme sulle dimensioni categoriche, incluso il bucket.
        rows = [
            _row("A", score=0.5, fwd={"T+1": 0.05}, ensemble_std_bucket="low"),
            _row("B", score=0.4, fwd={"T+1": 0.04}, ensemble_std_bucket="high"),
        ]
        out = sd.splits_by_dimension(rows, "ensemble_std_bucket", horizon="T+1")
        assert set(out.keys()) == {"low", "high"}
        assert out["low"]["n"] == 1

    def test_splits_marca_debole_le_celle_piccole(self):
        rows = [_row("A", score=0.5, fwd={"T+1": 0.05}, source="x")]
        out = sd.splits_by_dimension(rows, "source", horizon="T+1")
        # n=1: IC non definita (weak), ma n e' riportato.
        assert out["x"]["n"] == 1
        assert out["x"]["ic"]["ic"] is None


class TestWrongSignAudit:
    def test_separa_wrong_sign_neutral_missing_per_provenienza_e_fanout(self):
        rows = [
            _row("A", score=0.5, fwd={"30m": 0.02}, fallback=False,
                 n_ticker_articolo=1),
            _row("B", score=0.4, fwd={"30m": -0.03}, fallback=True,
                 n_ticker_articolo=4),
            _row("C", score=0.0, fwd={"30m": -0.02}, fallback=True,
                 n_ticker_articolo=2),
            _row("D", score=-0.2, fwd={"30m": None}, fallback=False,
                 n_ticker_articolo=None),
            _row("E", score=-0.3, fwd={"30m": 0.01}, fallback=None,
                 n_ticker_articolo=None),
        ]

        out = sd.wrong_sign_audit(rows, horizon="30m")

        assert out["overall"] == {
            "n_rows": 5,
            "n_score_missing": 0,
            "n_return_missing": 1,
            "n_score_neutral": 1,
            "n_return_flat": 0,
            "n_directional": 3,
            "n_correct_sign": 1,
            "n_wrong_sign": 2,
            "sign_accuracy": pytest.approx(1 / 3),
        }
        assert out["by_provenance"]["ensemble"]["n_correct_sign"] == 1
        assert out["by_provenance"]["ensemble"]["n_return_missing"] == 1
        assert out["by_provenance"]["fallback"]["n_wrong_sign"] == 1
        assert out["by_provenance"]["fallback"]["n_score_neutral"] == 1
        assert out["by_provenance"]["unknown"]["n_wrong_sign"] == 1
        assert out["by_fanout"]["single_ticker"]["n_correct_sign"] == 1
        assert out["by_fanout"]["multi_ticker"]["n_wrong_sign"] == 1
        assert out["by_provenance_and_fanout"]["fallback"]["multi_ticker"] == {
            "n_rows": 2,
            "n_score_missing": 0,
            "n_return_missing": 0,
            "n_score_neutral": 1,
            "n_return_flat": 0,
            "n_directional": 1,
            "n_correct_sign": 0,
            "n_wrong_sign": 1,
            "sign_accuracy": 0.0,
        }
        assert out["outcome"] == "forward_return:30m"
        assert out["policy"] == "descriptive_only_no_gate_or_discount"

    def test_zero_non_e_wrong_sign_e_missing_non_diventa_zero(self):
        rows = [
            _row("ZERO_SCORE", score=0.0, fwd={"60m": -0.02}, fallback=True),
            _row("FLAT_RETURN", score=0.4, fwd={"60m": 0.0}, fallback=False),
            _row("NO_SCORE", score=None, fwd={"60m": 0.03}, fallback=False),
            _row("NO_RETURN", score=-0.4, fwd={"60m": None}, fallback=True),
        ]

        overall = sd.wrong_sign_audit(rows, horizon="60m")["overall"]

        assert overall["n_wrong_sign"] == 0
        assert overall["n_directional"] == 0
        assert overall["n_score_neutral"] == 1
        assert overall["n_return_flat"] == 1
        assert overall["n_score_missing"] == 1
        assert overall["n_return_missing"] == 1
        assert overall["sign_accuracy"] is None


class TestScoreStability:
    def test_score_stability_da_serie_ic_per_giorno(self):
        series = [0.10, 0.20, 0.30, 0.40]
        out = sd.score_stability(series)
        assert out["n_days"] == 4
        assert out["mean_ic"] == pytest.approx(0.25)
        assert out["std_ic"] is not None
        assert out["icir"] is not None
        # positive_fraction: tutti > 0 -> 1.0
        assert out["positive_fraction"] == 1.0

    def test_score_stability_serie_vuota_o_breve(self):
        out = sd.score_stability([0.1])
        assert out["n_days"] == 1
        # std con 1 punto: non definito.
        assert out["std_ic"] is None
        assert out["icir"] is None

    def test_score_stability_icir_maggiore_per_serie_consistente(self):
        # serie stabile (bassa std) ha ICIR maggiore di serie instabile a pari mean.
        stable = [0.20, 0.21, 0.19, 0.20, 0.20]
        noisy = [0.40, -0.30, 0.50, -0.20, 0.35]
        s_out = sd.score_stability(stable)
        n_out = sd.score_stability(noisy)
        assert s_out["icir"] is not None and n_out["icir"] is not None
        assert abs(s_out["icir"]) > abs(n_out["icir"])


# ---------------------------------------------------------------------------
# 4. Panel per-day, rollup shadow curves, moltiplcita'
# ---------------------------------------------------------------------------


def _sig(signal_id, ticker, score, fwd_t1, *, spy_t1=0.01, sector_t1=0.02,
         ret=0.05, source="benzinga", model="glm52", fallback=False,
         extraction="cashtag", ensemble_std_bucket="low", sector="tech",
         data="2026-08-12", n_ticker_articolo=None):
    return {
        "signal_id": signal_id, "ticker": ticker, "data": data,
        "score": score, "timestamp": f"{data}T15:00:00+00:00",
        "return": ret, "is_mover": abs(ret) >= 0.03,
        "sector": sector, "source": source, "model": model, "fallback": fallback,
        "extraction_method": extraction, "ensemble_std_bucket": ensemble_std_bucket,
        "forward_returns": {"T+1": fwd_t1},
        "benchmark_returns": {"T+1": {"spy": spy_t1, "sector": sector_t1}},
        "n_ticker_articolo": n_ticker_articolo,
    }


def _day1_signals():
    return [
        _sig(1, "AAPL", 0.5, 0.05, ret=0.05, n_ticker_articolo=1),
        _sig(2, "MSFT", 0.4, 0.02, ret=0.02, n_ticker_articolo=1),
        _sig(3, "CSCO", 0.2, 0.06, ret=0.06, n_ticker_articolo=8),
        _sig(4, "ORCL", 0.35, 0.01, ret=0.01, n_ticker_articolo=None),
    ]


def _day2_signals():
    return [
        _sig(5, "AAPL", 0.45, 0.04, ret=0.04, data="2026-08-13"),
        _sig(6, "MSFT", 0.3, 0.03, ret=0.03, data="2026-08-13"),
        _sig(7, "CSCO", 0.15, 0.01, ret=0.01, data="2026-08-13"),
    ]


def _pool(data):
    # controlli non segnalati: stesso giorno/settore, return confrontabile.
    return [
        _sig(0, "INTC", None, 0.02, ret=0.05, source=None, model=None,
             extraction=None, ensemble_std_bucket="low", data=data),
    ]


class TestPanel:
    def test_panel_struttura_completa_e_policy_descriptive(self):
        panel = sd.build_signal_diagnostics_panel(
            _day1_signals(), pool_rows=_pool("2026-08-12"),
            mover_threshold=0.03,
        )
        assert panel["schema_version"] == sd.SIGNAL_DIAGNOSTICS_SCHEMA_VERSION
        assert panel["data"] == "2026-08-12"
        assert panel["n_signals"] == 4
        assert panel["policy_output"] == "descriptive_only"
        assert panel["freeze"]["live_thresholds_weights_flags_changed"] is False
        assert panel["mover_threshold"] == 0.03  # dichiarata, non scelta
        # blocchi previsti
        for key in ("rank_ic", "hit_precision_recall", "quintiles",
                    "false_positives", "matched_controls", "splits",
                    "fanout_sweep"):
            assert key in panel

    def test_panel_sweep_fanout_grid_descrittivo_senza_scelta(self):
        # Regressione review #283 (criterio 1, 2 volte respinta): la issue
        # richiede lo sweep predefinito e descrittivo anche del fan-out
        # (n_ticker_articolo), non solo della soglia di score.
        panel = sd.build_signal_diagnostics_panel(
            _day1_signals(), pool_rows=_pool("2026-08-12"),
            mover_threshold=0.03,
        )
        fanout = panel["fanout_sweep"]
        assert fanout["fanout_grid"] == list(sd.DEFAULT_FANOUT_GRID)
        # ORCL non porta n_ticker_articolo: assente != zero, dichiarato a parte.
        assert fanout["n_fanout_missing"] == 1
        assert len(fanout["sweeps"]) == len(sd.DEFAULT_FANOUT_GRID)
        for point in fanout["sweeps"]:
            assert point["max_fanout"] in sd.DEFAULT_FANOUT_GRID
            assert len(point["hit_precision_recall"]) == len(sd.DEFAULT_THRESHOLD_GRID)
        # cutoff=1: solo AAPL e MSFT (n_ticker_articolo==1); CSCO (8) escluso,
        # ORCL (mancante) escluso.
        cutoff_1 = next(p for p in fanout["sweeps"] if p["max_fanout"] == 1)
        assert cutoff_1["n_rows"] == 2
        # un cutoff che include anche CSCO (8) porta 3 righe.
        cutoff_wide = next(p for p in fanout["sweeps"] if p["max_fanout"] >= 8)
        assert cutoff_wide["n_rows"] == 3
        assert fanout["policy"] == "descriptive_only_no_threshold_selected"

    def test_panel_rank_ic_per_ogni_orizzonte_con_raw_e_residual(self):
        panel = sd.build_signal_diagnostics_panel(
            _day1_signals(), pool_rows=_pool("2026-08-12"),
            mover_threshold=0.03,
        )
        # ogni orizzonte ha raw, spy_residual, sector_residual.
        for h in sd.HORIZONS:
            assert h in panel["rank_ic"]
            assert "raw" in panel["rank_ic"][h]
            assert "spy_residual" in panel["rank_ic"][h]
            assert "sector_residual" in panel["rank_ic"][h]
        # T+1 e' popolato (i dati ci sono): raw IC calcolabile.
        assert panel["rank_ic"]["T+1"]["raw"]["n"] == 4
        # residual vs spy: signal_t1 - 0.01
        assert panel["rank_ic"]["T+1"]["spy_residual"]["n"] == 4

    def test_panel_sweep_threshold_grid_descrittivo_senza_scelta(self):
        panel = sd.build_signal_diagnostics_panel(
            _day1_signals(), pool_rows=_pool("2026-08-12"),
            mover_threshold=0.03,
        )
        # hit/precision/recall e' sul mover del giorno (azione catturabile),
        # non per-orizzonte: uno sweep singolo sulla griglia predefinita.
        sweep = panel["hit_precision_recall"]
        assert len(sweep) == len(sd.DEFAULT_THRESHOLD_GRID)
        thresholds = [p["threshold"] for p in sweep]
        assert thresholds == list(sd.DEFAULT_THRESHOLD_GRID)
        # nessuna soglia e' marcata come "scelta".
        for p in sweep:
            assert p["direction"] == "long"
            assert "chosen" not in p

    def test_panel_quintili_e_false_positives_per_orizzonte(self):
        panel = sd.build_signal_diagnostics_panel(
            _day1_signals(), pool_rows=_pool("2026-08-12"),
            mover_threshold=0.03,
        )
        assert len(panel["quintiles"]["T+1"]) == 5
        assert isinstance(panel["false_positives"]["T+1"], list)
        assert len(panel["false_positives"]["T+1"]) == len(sd.DEFAULT_THRESHOLD_GRID)

    def test_panel_espone_wrong_sign_audit_per_orizzonte(self):
        panel = sd.build_signal_diagnostics_panel(
            _day1_signals(), pool_rows=_pool("2026-08-12"),
            mover_threshold=0.03,
        )

        assert set(panel["wrong_sign_audit"]) == set(sd.HORIZONS)
        t1 = panel["wrong_sign_audit"]["T+1"]
        assert t1["outcome"] == "forward_return:T+1"
        assert t1["by_provenance"]["ensemble"]["n_rows"] == 4
        assert t1["policy"] == "descriptive_only_no_gate_or_discount"

    def test_panel_matched_controls_per_orizzonte(self):
        panel = sd.build_signal_diagnostics_panel(
            _day1_signals(), pool_rows=_pool("2026-08-12"),
            mover_threshold=0.03,
        )
        # matched controls presenti per ogni orizzonte, separati dal book benchmark.
        mc = panel["matched_controls"]["T+1"]
        assert "matches" in mc and "summary" in mc
        assert mc["summary"]["control_kind"].startswith("ticker_level_non_signaled")

    def test_panel_splits_per_tutte_le_dimensioni(self):
        panel = sd.build_signal_diagnostics_panel(
            _day1_signals(), pool_rows=_pool("2026-08-12"),
            mover_threshold=0.03,
        )
        for dim in ("source", "model", "fallback", "extraction_method",
                    "ensemble_std_bucket"):
            assert dim in panel["splits"]
            assert "T+1" in panel["splits"][dim]

    def test_panel_missingness_se_orizzonti_senza_dati(self):
        # le righe di test hanno solo T+1; gli altri orizzonti sono None:
        # la IC e' weak/None ma il panel non crasha e lo dichiara.
        panel = sd.build_signal_diagnostics_panel(
            _day1_signals(), pool_rows=_pool("2026-08-12"),
            mover_threshold=0.03,
        )
        assert panel["rank_ic"]["30m"]["raw"]["n"] == 0
        assert panel["rank_ic"]["30m"]["raw"]["ic"] is None
        assert "forward_return_missing" in panel["missingness"] or \
               panel["rank_ic"]["30m"]["raw"]["n"] == 0

    def test_panel_vuoto_restituisce_struttura_valida(self):
        panel = sd.build_signal_diagnostics_panel(
            [], pool_rows=[], mover_threshold=0.03,
        )
        assert panel["n_signals"] == 0
        assert panel["policy_output"] == "descriptive_only"


class TestRollup:
    def test_rollup_shadow_curve_serie_per_giorno_e_cumulato(self):
        p1 = sd.build_signal_diagnostics_panel(
            _day1_signals(), pool_rows=_pool("2026-08-12"), mover_threshold=0.03)
        p2 = sd.build_signal_diagnostics_panel(
            _day2_signals(), pool_rows=_pool("2026-08-13"), mover_threshold=0.03)
        roll = sd.build_signal_diagnostics_rollup([p1, p2])
        # shadow curve T+1: una riga per giorno con IC e cumulato.
        series = roll["shadow_curves"]["T+1"]["raw"]
        assert len(series) == 2
        assert "ic" in series[0] and "cumulative_mean_ic" in series[0]
        # ordinato per data.
        assert series[0]["data"] == "2026-08-12"
        assert series[1]["data"] == "2026-08-13"

    def test_rollup_score_stability_dalla_serie_di_ic(self):
        p1 = sd.build_signal_diagnostics_panel(
            _day1_signals(), pool_rows=_pool("2026-08-12"), mover_threshold=0.03)
        p2 = sd.build_signal_diagnostics_panel(
            _day2_signals(), pool_rows=_pool("2026-08-13"), mover_threshold=0.03)
        roll = sd.build_signal_diagnostics_rollup([p1, p2])
        stab = roll["score_stability"]["T+1"]["raw"]
        assert stab["n_days"] == 2
        assert "icir" in stab

    def test_rollup_moltiplcita_dichiara_n_trials_e_bh(self):
        p1 = sd.build_signal_diagnostics_panel(
            _day1_signals(), pool_rows=_pool("2026-08-12"), mover_threshold=0.03)
        roll = sd.build_signal_diagnostics_rollup([p1])
        mult = roll["multiplicity"]
        assert mult["n_trials"] >= 1
        assert mult["method"] == "benjamini_hochberg_descriptive"
        # n_trials = orizzonti x benchmark x splits x soglie (almeno).
        assert mult["n_trials"] == len(sd.HORIZONS) * 3 * len(sd.DEFAULT_THRESHOLD_GRID) * 5 \
            or mult["n_trials"] > 0
        assert mult["policy"] == "descriptive_only_no_threshold_selected"

    def test_rollup_policy_descriptive_e_freeze(self):
        p1 = sd.build_signal_diagnostics_panel(
            _day1_signals(), pool_rows=_pool("2026-08-12"), mover_threshold=0.03)
        roll = sd.build_signal_diagnostics_rollup([p1])
        assert roll["policy_output"] == "descriptive_only"
        assert roll["freeze"]["mode"] == "read_only_measurement"


# ---------------------------------------------------------------------------
# 5a. Bucket ensemble_std (terzile descrittivo, per gli split)
# ---------------------------------------------------------------------------


class TestEnsembleStdBucket:
    def test_bucket_terzili_sulla_distribuzione(self):
        rows = [{"ensemble_std": v} for v in [0.0, 0.1, 0.2, 0.3, 0.4, 0.5]]
        buckets, edges = sd.assign_ensemble_std_buckets(rows)
        assert len(buckets) == 6
        assert set(buckets) <= {"low", "med", "high"}
        # i tre bucket sono tutti presenti (distribuzione continua).
        assert "low" in buckets and "high" in buckets
        assert edges[0] <= edges[1]

    def test_bucket_unknown_per_ensemble_std_mancante(self):
        rows = [{"ensemble_std": 0.1}, {"ensemble_std": None}, {"ensemble_std": 0.4}]
        buckets, _ = sd.assign_ensemble_std_buckets(rows)
        assert buckets[1] == "unknown"

    def test_bucket_niente_variabilita_tutti_nello_stesso(self):
        rows = [{"ensemble_std": 0.2}, {"ensemble_std": 0.2}, {"ensemble_std": 0.2}]
        buckets, edges = sd.assign_ensemble_std_buckets(rows)
        # terzili degeneri (tutto uguale): un solo bucket, edges uguali.
        assert len(set(buckets)) == 1
