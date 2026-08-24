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