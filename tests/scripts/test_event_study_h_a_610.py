"""Test per la misura H-A (issue #610): il detector CONTENT_EMPTY / RETROSPECTIVE
separa davvero?

L'output del detector e' dicotomico (`content_empty_title_reason` di
`src/analysis/dossier/article_coverage.py`). La domanda che H-A pone non e' se il
detector sia preciso: e' se gli articoli che RICONOSCE hanno una reazione di
prezzo diversa da quelli che NON riconosce. La misura e' il rapporto fra
volatilita' al minuto nei 5 minuti dopo `created_at` e volatilita' di fondo
(T-30 -> T-6), per gruppo, con t clusterizzato per giornata.

Questi test non misurano H-A — misurano il calcolatore che produrra' H-A. La
misura vera richiede l'archivio news e i prezzi minuto, e la sua priorita' e'
portarla al tavolo del 28/09 per la Leva A di #607.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from scripts.event_study_h_a_610 import (
    MINUTI_BASELINE,
    MINUTI_EVENTO,
    _esegui_anno,
    articoli_per_anno,
    calcola_rapporto,
    classifica,
    media_delle_medie_giornaliere,
    fetch_minute_bars,
    leggi_archivio,
    parse_timestamp,
    scrivi_artefatto,
    within_cooldown,
)


# ---------- Timestamp parsing ----------


def test_parse_timestamp_iso8601_utc():
    """Z e +00:00 sono equivalenti."""
    a = parse_timestamp("2024-03-05T14:30:00Z")
    b = parse_timestamp("2024-03-05T14:30:00+00:00")
    assert a == b
    assert a.tzinfo is not None
    assert a.utcoffset().total_seconds() == 0


def test_parse_timestamp_con_frazioni():
    """Le frazioni di secondo non rompono il parsing."""
    ts = parse_timestamp("2024-03-05T14:30:00.123456+00:00")
    assert ts.year == 2024 and ts.month == 3 and ts.day == 5


# ---------- Classificazione ----------


def test_classifica_riconosce_template_noti():
    """I template pre-registrati dalla #508 devono uscire content_empty=True.

    La lista e' congelata: aggiungerne una nuova e' una scelta di misura, non
    un default. Se la lista cambia, lo script va aggiornato e il test
    rappresenta il commit di quell'aggiornamento.

    Il vocabolario di `content_empty_title_reason` e' deliberatamente
    stretto — 3 pattern, non un catch-all "listicle" o "recap": solo gli
    evergreen "if you invested $X" e "here's how much", i "whale activity"
    e i ratings-listicle "here are the top N upgrades".
    """
    # EVERGREEN_RETURN_TEMPLATE
    assert classifica("If You Invested $10,000 In Microsoft 5 Years Ago")[0] is True
    assert classifica("Here's How Much $1,000 Invested In Tesla 3 Years Ago")[0] is True
    # WHALE_ACTIVITY_TEMPLATE
    assert classifica("Whale Activity Spotted In Coinbase Stock")[0] is True
    # RATINGS_LISTICLE_TEMPLATE (notare "Here Are The Top N Upgrades")
    assert classifica("Here Are The Top 5 Upgrades From Last Week")[0] is True


def test_classifica_non_riguarda_earnings_o_guidance():
    """Titoli che non sono template devono uscire content_empty=False.

    La pre-registrazione di H-B elenca earnings/guidance/M&A/rating fra i
    non-template: sono il segnale che la pipeline vorrebbe catturare, non il
    rumore che H-A vuole scartare.
    """
    assert classifica("Apple Reports Q3 Earnings, Beats Estimates")[0] is False
    assert classifica("Microsoft Raises FY Guidance")[0] is False
    assert classifica("Tesla Downgraded By Goldman Sachs")[0] is False


# ---------- Volatility ratio ----------


def _bars_piatti(ts: datetime, n: int = 60) -> pd.Series:
    """Serie di close costante: volatilita' zero ovunque."""
    idx = pd.date_range(ts - pd.Timedelta(minutes=n), periods=n + 5, freq="1min", tz="UTC")
    return pd.Series(100.0, index=idx)


def _bars_piccolo_picco(ts: datetime, baseline: float = 1.0, evento: float = 3.0) -> pd.Series:
    """Volatilita' baseline 1bp, evento 3bp: rapporto atteso ~3.0.

    Per evitare che un drift costante produca std=0 (e quindi un rapporto
    di 0/1bp), alterno segno: rets ~ ±baseline nella baseline, ±evento
    nella finestra di evento. La std di log-return cosi' riflette
    effettivamente l'ampiezza dei movimenti.
    """
    idx = pd.date_range(ts - pd.Timedelta(minutes=30), periods=40, freq="1min", tz="UTC")
    rets: list[float] = []
    for i in range(len(idx)):
        segno = 1.0 if i % 2 == 0 else -1.0
        if 30 <= i <= 34:  # T+0..T+4: finestra evento
            rets.append(segno * evento * 0.001)
        else:
            rets.append(segno * baseline * 0.001)
    prices = [100.0]
    for r in rets:
        prices.append(prices[-1] * (1 + r))
    return pd.Series(prices[1:], index=idx)


def test_calcola_rapporto_picco_nel_evento():
    """Un articolo che produce un picco al T+0 deve avere rapporto > 1."""
    ts = datetime(2024, 3, 5, 14, 30, tzinfo=timezone.utc)
    bars = _bars_piccolo_picco(ts)
    ratio = calcola_rapporto(ts, bars, finestra_evento=MINUTI_EVENTO, finestra_baseline=MINUTI_BASELINE)
    # 3bp / 1bp = 3.0 (drift verso l'alto aggiunge poco in 5 min)
    assert ratio is not None
    assert ratio > 1.5


def test_calcola_rapporto_piatti():
    """Serie piatta: rapporto indefinito (0/0). Lo script lo segnala come None."""
    ts = datetime(2024, 3, 5, 14, 30, tzinfo=timezone.utc)
    bars = _bars_piatti(ts)
    ratio = calcola_rapporto(ts, bars)
    assert ratio is None


def test_calcola_rapporto_finestra_evento_vuota():
    """Se non ci sono barre nell'evento (articolo a fine giornata), None.

    Senza questo, l'output sarebbe NaN e il downstream dovrebbe gestire il
    nan-a-una-volta — meglio troncare a monte.
    """
    ts = datetime(2024, 3, 5, 14, 30, tzinfo=timezone.utc)
    # Solo 30 barre, tutte PRIMA di ts
    idx = pd.date_range(ts - pd.Timedelta(minutes=30), periods=30, freq="1min", tz="UTC")
    bars = pd.Series(100.0 + np.arange(30) * 0.01, index=idx)
    ratio = calcola_rapporto(ts, bars, finestra_evento=5, finestra_baseline=24)
    assert ratio is None


# ---------- Cooldown anti-doppione ----------


def test_within_cooldown_doppione_stesso_minuto():
    """Due articoli sullo stesso ticker nello stesso minuto collassano in uno."""
    ts = datetime(2024, 3, 5, 14, 30, tzinfo=timezone.utc)
    assert within_cooldown(ts, ts, cooldown_minuti=5) is True


def test_within_cooldown_distanza_sopra_soglia():
    """Oltre il cooldown non sono doppioni."""
    ts1 = datetime(2024, 3, 5, 14, 30, tzinfo=timezone.utc)
    ts2 = datetime(2024, 3, 5, 14, 36, tzinfo=timezone.utc)
    assert within_cooldown(ts1, ts2, cooldown_minuti=5) is False


def test_within_cooldown_ticker_diverso_non_collassa():
    """Stesso timestamp, ticker diverso: articoli distinti.

    H-A misura per articolo-ticker: collassare ticker diversi avrebbe
    confuso fan-out (EN-03) con doppione.
    """
    ts = datetime(2024, 3, 5, 14, 30, tzinfo=timezone.utc)
    assert within_cooldown(ts, ts, cooldown_minuti=5, ticker_a="AAPL", ticker_b="MSFT") is False


# ---------- Statistica per giornata (prereg §4) ----------


def test_ogni_giornata_pesa_uno_singleton_compresi():
    """La media e' delle medie giornaliere e un giorno con un articolo conta.

    Regressione della review di PR #641: la versione cluster-robust mediava
    per articolo ed escludeva i giorni singleton dal solo SE. 39 giorni a ~1
    e un singleton a 5 davano t ~ 7e14, cioe' un PASS spurio.
    """
    obs = [("2024-03-01", 5.0)] + [
        (f"2024-04-{d:02d}", 1.0 + 0.01 * (j % 2)) for d in range(1, 29) for j in range(2)
    ]
    stat = media_delle_medie_giornaliere(obs)

    assert stat.n_giorni == 29
    assert stat.n_obs == 57
    medie = [5.0] + [1.005] * 28
    assert stat.media == pytest.approx(sum(medie) / 29)
    assert abs(stat.t) < 3  # il giorno estremo pesa anche sull'errore


def test_l_effetto_rilevabile_e_tre_volte_l_se_osservato():
    poco_rumore = [(f"2024-03-{d:02d}", 1.0 + 0.01 * (d % 2)) for d in range(1, 21)]
    tanto_rumore = [(f"2024-03-{d:02d}", 1.0 + 0.5 * (d % 2)) for d in range(1, 21)]

    a = media_delle_medie_giornaliere(poco_rumore)
    b = media_delle_medie_giornaliere(tanto_rumore)

    assert a.effetto_rilevabile_a_t3 == pytest.approx(3 * a.se)
    assert b.effetto_rilevabile_a_t3 > 10 * a.effetto_rilevabile_a_t3


def test_meno_di_due_giornate_non_ha_errore_standard():
    stat = media_delle_medie_giornaliere([("2024-03-05", 1.2), ("2024-03-05", 1.4)])

    assert stat.n_giorni == 1
    assert math.isnan(stat.t)
    assert math.isinf(stat.effetto_rilevabile_a_t3)


def test_nan_e_none_non_entrano_nella_media():
    stat = media_delle_medie_giornaliere(
        [("2024-03-05", float("nan")), ("2024-03-05", None), ("2024-03-06", 1.1), ("2024-03-07", 1.3)]
    )

    assert stat.n_obs == 2
    assert stat.media == pytest.approx(1.2)


def test_due_sole_barre_non_danno_un_rapporto_nan():
    """Un solo log-return: std(ddof=1) = NaN, che prima passava il filtro."""
    ts = datetime(2024, 3, 5, 15, 0, tzinfo=timezone.utc)
    idx = [ts - pd.Timedelta(minutes=30) + pd.Timedelta(minutes=i) for i in range(24)]
    idx += [ts, ts + pd.Timedelta(minutes=1)]
    close = pd.Series([100 + 0.01 * (i % 3) for i in range(24)] + [100.5, 100.2],
                      index=pd.DatetimeIndex(idx))

    assert calcola_rapporto(ts, close) is None


# ---------- Articoli per anno ----------


def test_articoli_per_anno_split_2024_2025():
    """La popolazione si divide sulle righe create."""
    archivio = [
        {"created_at": "2024-03-05T14:30:00Z", "symbols": ["AAPL"]},
        {"created_at": "2024-12-31T23:59:00Z", "symbols": ["MSFT"]},
        {"created_at": "2025-01-01T00:00:00Z", "symbols": ["NVDA"]},
        {"created_at": "2025-12-31T23:59:00Z", "symbols": ["GOOG"]},
    ]
    out = articoli_per_anno(archivio)
    assert set(out.anni) == {"2024", "2025"}
    assert out.per_anno["2024"] == archivio[:2]
    assert out.per_anno["2025"] == archivio[2:]


# ---------- Lettura archivio JSONL ----------


def test_leggi_archivio_da_due_mesi(tmp_path: Path):
    """I file news_YYYY-MM.jsonl si leggono in ordine di mese."""
    a = tmp_path / "news_2024-03.jsonl"
    b = tmp_path / "news_2024-04.jsonl"
    a.write_text(
        json.dumps({"id": "1", "created_at": "2024-03-05T14:30:00Z", "headline": "x", "symbols": ["AAPL"]}) + "\n"
    )
    b.write_text(
        json.dumps({"id": "2", "created_at": "2024-04-01T10:00:00Z", "headline": "y", "symbols": ["MSFT"]}) + "\n"
    )
    out, malformate = leggi_archivio(tmp_path)
    assert len(out) == 2
    assert out[0]["id"] == "1"
    assert out[1]["id"] == "2"


def test_leggi_archivio_righe_malformate_saltate(tmp_path: Path):
    """Righe non-JSON o vuote non abortiscono la lettura.

    Un articolo malformato non puo' essere analizzato ma l'archivio e'
    ancora utilizzabile: meglio loggarlo e proseguire che abortire
    sull'intero dataset.
    """
    a = tmp_path / "news_2024-03.jsonl"
    a.write_text(
        json.dumps({"id": "1", "created_at": "2024-03-05T14:30:00Z", "headline": "x", "symbols": ["AAPL"]}) + "\n"
        + "non-json\n"
        + "\n"
        + json.dumps({"id": "2", "created_at": "2024-03-06T10:00:00Z", "headline": "y", "symbols": ["MSFT"]}) + "\n"
    )
    out, malformate = leggi_archivio(tmp_path)
    assert len(out) == 2
    assert malformate == 1  # contate, non piu' perse in silenzio


# ---------- Percorso composto (_esegui_anno) ----------


def test_esegui_anno_con_piu_articoli_al_giorno_non_e_sempre_insufficient_n():
    """Il percorso reale deve poter superare INSUFFICIENT_N con dati sufficienti.

    Regressione del difetto trovato in review su PR #641: se `_esegui_anno`
    pre-mediasse i rapporti per giorno prima di clusterizzare, ogni cluster
    sarebbe un singleton e il verdetto sarebbe SEMPRE `INSUFFICIENT_N`,
    indipendentemente dal volume di articoli. Con 2 articoli non-template
    per giorno su 3 giorni distinti, il gruppo non_content_empty deve
    raggiungere almeno 2 cluster validi.
    """
    giorni = [5, 6, 7]
    ticker_per_giorno = [("AAPL", "MSFT"), ("TSLA", "NVDA"), ("META", "AMZN")]
    articoli = []
    for giorno, (t1, t2) in zip(giorni, ticker_per_giorno):
        for ticker, minuto in ((t1, 30), (t2, 0)):
            ora = 14 if minuto == 30 else 15
            ts_iso = f"2024-03-{giorno:02d}T{ora:02d}:{minuto:02d}:00Z"
            articoli.append({
                "id": f"{ticker}-{giorno}",
                "created_at": ts_iso,
                "symbols": [ticker],
                # Non-template: finisce nel gruppo non_content_empty.
                "headline": f"{ticker} Reports Q1 Earnings, Beats Estimates",
            })

    def loader(symbol: str, start: datetime, end: datetime) -> pd.Series:
        ts = start + pd.Timedelta(minutes=30)
        # Ampiezza dell'evento diversa per giorno: senza varianza between-day
        # la statistica cluster-robust degenera a t=inf (SE=0), che il
        # verdetto tratta come INSUFFICIENT_N — qui si vuole invece che il
        # test possa raggiungere PASS/FAIL con dati sufficienti.
        return _bars_piccolo_picco(ts, baseline=1.0, evento=2.0 + ts.day * 0.7)

    risultato = _esegui_anno("2024", articoli, loader, escludi_selezionati=False)
    gruppo = risultato["gruppo_non_content_empty"]
    assert gruppo["n_giorni"] == 3
    assert math.isfinite(gruppo["t"])
    assert gruppo["verdetto"] in {"PASS", "FAIL"}


# ---------- Minute bars fetch (seam) ----------


def test_fetch_minute_bars_delega_a_loader(monkeypatch):
    """Lo script non chiama Alpaca direttamente: delaga a una funzione `loader`.

    La separazione e' strumentale — quando il fetch fallisce (embargo SIP),
    un test fail-closed abortisce la misura (regola §1.1 della
    pre-registrazione). Il seam e' una funzione semplice.
    """
    chiamato = {}

    def fake_loader(symbol: str, start, end):
        chiamato["args"] = (symbol, start, end)
        return pd.Series(dtype=float)

    bars = fetch_minute_bars(
        "AAPL",
        datetime(2024, 3, 5, 14, 0, tzinfo=timezone.utc),
        datetime(2024, 3, 5, 15, 0, tzinfo=timezone.utc),
        loader=fake_loader,
    )
    assert chiamato["args"][0] == "AAPL"
    assert bars.empty


# ---------- Output artefatto ----------


def test_scrivi_artefatto_contiene_campi_richiesti(tmp_path: Path):
    """L'output JSON contiene tutti i campi che la pre-registrazione richiede."""
    out_path = tmp_path / "h_a_2024.json"
    risultato = {
        "anno": "2024",
        "popolazione_n": 100,
        "gruppo_content_empty": {"n": 30, "media": 1.5, "t": 2.1, "n_cluster_validi": 12,
                                  "effetto_rilevabile_a_t3": 0.8, "verdetto": "INSUFFICIENT_N"},
        "gruppo_non_content_empty": {"n": 70, "media": 2.3, "t": 4.5, "n_cluster_validi": 18,
                                      "effetto_rilevabile_a_t3": 0.4, "verdetto": "PASS"},
        "selezionati_esclusi": False,
        "discontinuita_di_misura": None,
    }
    scrivi_artefatto(out_path, risultato)
    scritto = json.loads(out_path.read_text())
    assert scritto["anno"] == "2024"
    assert scritto["gruppo_content_empty"]["verdetto"] == "INSUFFICIENT_N"
    assert scritto["gruppo_non_content_empty"]["verdetto"] == "PASS"


def test_scrivi_artefatto_senza_selezionati_sull_esito(tmp_path: Path):
    """Ogni esito si pubblica anche senza ROKU/RDDT/HOOD/WDC/SPCX.

    La pre-registrazione §6 dice che se i due numeri divergono, la
    watchlist guida il risultato. Lo script produce ENTRAMBI gli artefatti
    in coppia.
    """
    out_path = tmp_path / "h_a.json"
    scrivi_artefatto(out_path, {"anno": "2024", "selezionati_esclusi": True})
    scritto = json.loads(out_path.read_text())
    assert scritto["selezionati_esclusi"] is True

# ---------- Loader Alpaca fail-closed (prereg §1.1) ----------


class _Barra:
    def __init__(self, ts, close):
        self.timestamp = ts
        self.close = close


class _ClientFinto:
    def __init__(self, errore=None):
        self.richieste = []
        self.errore = errore

    def get_stock_bars(self, req):
        self.richieste.append((req.symbol_or_symbols, req.start))
        if self.errore:
            raise self.errore
        # alpaca-py normalizza start a UTC naive (e lo invia come UTC)
        inizio = pd.Timestamp(req.start).tz_localize("UTC")
        barre = [_Barra(inizio + pd.Timedelta(minutes=m), 100.0 + m * 0.01) for m in range(0, 24 * 60, 1)]

        class _R:
            data = {req.symbol_or_symbols: barre}
        return _R()


_ORA = datetime(2026, 9, 24, tzinfo=timezone.utc)


def test_il_loader_scarica_una_volta_per_simbolo_e_giorno():
    from scripts.event_study_h_a_610 import CaricatoreBarreAlpaca

    client = _ClientFinto()
    loader = CaricatoreBarreAlpaca(client, ora=_ORA)
    t = datetime(2024, 3, 5, 15, 0, tzinfo=timezone.utc)

    a = loader("AAPL", t - pd.Timedelta(minutes=30), t + pd.Timedelta(minutes=6))
    loader("AAPL", t + pd.Timedelta(hours=2), t + pd.Timedelta(hours=2, minutes=36))

    assert len(client.richieste) == 1
    assert len(a) == 36
    assert a.index.min() >= t - pd.Timedelta(minutes=30)
    assert a.index.max() < t + pd.Timedelta(minutes=6)


def test_un_fetch_fallito_ferma_la_misura():
    from scripts.event_study_h_a_610 import CaricatoreBarreAlpaca, MisuraAbortita

    loader = CaricatoreBarreAlpaca(
        _ClientFinto(errore=RuntimeError("subscription does not permit querying recent SIP data")),
        ora=_ORA,
    )
    t = datetime(2024, 3, 5, 15, 0, tzinfo=timezone.utc)
    with pytest.raises(MisuraAbortita, match="AAPL"):
        loader("AAPL", t, t + pd.Timedelta(minutes=6))


def test_una_finestra_oltre_l_embargo_ferma_la_misura_senza_chiedere():
    from scripts.event_study_h_a_610 import CaricatoreBarreAlpaca, MisuraAbortita

    client = _ClientFinto()
    loader = CaricatoreBarreAlpaca(client, ora=_ORA)
    t = _ORA - pd.Timedelta(days=1)
    with pytest.raises(MisuraAbortita, match="embargo"):
        loader("AAPL", t, t + pd.Timedelta(minutes=6))
    assert client.richieste == []


def test_una_finestra_a_cavallo_di_mezzanotte_new_york_unisce_i_due_giorni(tmp_path):
    from scripts.event_study_h_a_610 import CaricatoreBarreAlpaca

    client = _ClientFinto()
    loader = CaricatoreBarreAlpaca(client, cache_dir=tmp_path, ora=_ORA)
    # 00:10 ET del 6 marzo = 05:10 UTC: il fondo parte il 5 marzo ET.
    t = datetime(2024, 3, 6, 5, 10, tzinfo=timezone.utc)
    serie = loader("AAPL", t - pd.Timedelta(minutes=30), t + pd.Timedelta(minutes=6))

    assert len(client.richieste) == 2
    assert len(serie) == 36
    # la cache su disco evita di riscaricare in un nuovo run
    secondo = CaricatoreBarreAlpaca(_ClientFinto(errore=AssertionError("non deve chiedere")),
                                    cache_dir=tmp_path, ora=_ORA)
    assert len(secondo("AAPL", t - pd.Timedelta(minutes=30), t + pd.Timedelta(minutes=6))) == 36


# ---------- La nulla del rapporto non e' 1 (review PR #641, punto 7) ----------


def test_la_nulla_del_rapporto_non_e_uno():
    """Sotto "nessuna notizia" il rapporto medio NON e' 1: e' 0,955.

    Il numeratore ha 4 log-return, il denominatore 23. La std campionaria e'
    correttamente piu' piccola di sigma con cosi' pochi gradi di liberta'
    (fattore c(4)=0,921 contro c(23)=0,989), quindi il rapporto e' sistematicamente
    sotto 1 anche quando il mercato non reagisce a nulla.

    Conseguenza: testare `media > 1` significa che un gruppo di articoli
    genuinamente inerti non esce "indistinguibile da 1" ma esce con t negativo —
    cioe' FAIL su un effetto che non c'e'. Il riferimento giusto e' la nulla a
    forma chiusa, non 1.
    """
    from scripts.event_study_h_a_610 import null_log_rapporto

    # Riferimento Monte Carlo indipendente (rng fissato, 20k campioni).
    rng = np.random.default_rng(20240305)
    evento = np.std(rng.normal(0.0, 1.0, (20_000, 4)), axis=1, ddof=1)
    fondo = np.std(rng.normal(0.0, 1.0, (20_000, 23)), axis=1, ddof=1)
    monte_carlo = float(np.mean(np.log(evento / fondo)))

    assert null_log_rapporto(4, 23) == pytest.approx(monte_carlo, abs=0.01)
    # E il riferimento implicito del codice (1.0) sbaglia di questa misura:
    assert abs(monte_carlo - math.log(1.0)) > 0.10


def test_l_eccesso_e_nullo_quando_il_mercato_non_reagisce():
    """Il percorso vero: nessun evento iniettato, eccesso medio ~ 0.

    `calcola_esito` lavora in spazio logaritmico e sottrae la nulla a forma
    chiusa della finestra EFFETTIVAMENTE osservata (righe di prezzo diverse da
    quelle del test precedente cambiano la nulla). Qui nessun picco viene
    iniettato: l'eccesso deve cadere vicino a zero, mentre il rapporto grezzo
    resta sotto 1 — esattamente il difetto che rendeva illeggibile il
    verdetto di H-A.
    """
    from scripts.event_study_h_a_610 import calcola_esito

    rng = np.random.default_rng(99)
    eccessi, rapporti = [], []
    for giorno in range(40):
        ts = datetime(2024, 3, 4 + giorno % 20, 15, 0, tzinfo=timezone.utc)
        # Prezzi con volatilita' costante e nessun evento: ritorni iid.
        idx = pd.date_range(ts - pd.Timedelta(minutes=30), periods=40, freq="1min", tz="UTC")
        rets = rng.normal(0.0, 0.001, size=len(idx))
        prezzi = 100.0 * np.exp(np.cumsum(rets))
        esito = calcola_esito(ts, pd.Series(prezzi, index=idx))
        assert esito is not None
        eccessi.append(esito.eccesso_log)
        rapporti.append(esito.rapporto)

    # L'eccesso e' centrato su zero per costruzione.
    assert float(np.mean(eccessi)) == pytest.approx(0.0, abs=0.05)
    # Il rapporto grezzo, invece, e' sistematicamente sotto 1: il riferimento
    # implicito di RAPPORTO_H0=1.0 avrebbe letto questi gruppi come FAIL.
    assert float(np.mean(rapporti)) < 0.99


def test_un_picco_reale_sopravvive_al_passaggio_in_space_di_log():
    """Il riscorretto non spentere la potenza: un picco vero resta positivo.

    Stesso picco di `test_calcola_rapporto_picco_nel_evento`, letto con
    `calcola_esito`: l'eccesso deve essere nettamente sopra la nulla, altrimenti
    la correzione avrebbe cancellato il segnale che H-A vuole trovare.
    """
    from scripts.event_study_h_a_610 import calcola_esito

    ts = datetime(2024, 3, 5, 14, 30, tzinfo=timezone.utc)
    esito = calcola_esito(ts, _bars_piccolo_picco(ts, baseline=1.0, evento=3.0))

    assert esito is not None
    assert esito.eccesso_log > null_log_di_riferimento(esito)
    assert esito.eccesso_log > 0.5


def null_log_di_riferimento(esito) -> float:
    from scripts.event_study_h_a_610 import null_log_rapporto

    return null_log_rapporto(esito.n_ritorni_evento, esito.n_ritorni_fondo)


def test_la_nulla_segue_le_riprezioni_osservate():
    """Finestra con meno barre ha una nulla diversa: si calcola, non si assume.

    Un articolo misurato su 3 barre di evento ha 2 ritorni, non 4: la sua
    nulla e' piu' negativa. Applicare la nulla fissa della finestra piena
    sbiaserebbe proprio gli articoli a bassa copertura, che sono i piu'
    sospetti di essere rumore.
    """
    from scripts.event_study_h_a_610 import null_log_rapporto

    pieno = null_log_rapporto(4, 23)
    scarso = null_log_rapporto(2, 23)
    assert scarso < pieno  # meno gradi di liberta' => std piu' piccola => ratio piu' basso


# ---------- H-A confronta i due gruppi: non due test separati (review, punto 7) ----------


def test_il_verdetto_di_ha_e_un_confronto_fra_i_due_gruppi():
    """La domanda di H-A e' se il detector SEPARA, quindi e' una differenza.

    Testare i due gruppi separatamente contro la nulla risponde a un'altra
    domanda ("i non-template reagiscono?") e perde quella che conta: puo'
    succedere che entrambi reagiscano uguale (niente separazione, nessuna
    differenza) pur avendo entrambi un t sopra soglia. Il verdetto di H-A deve
    essere la differenza fra le medie giornaliere dei due gruppi, con t su
    quella differenza.
    """
    from scripts.event_study_h_a_610 import confronto_gruppi

    # Due gruppi con lo STESSO effetto (1.6 ciascuno): nessuna separazione.
    osservazioni = [
        ("content_empty", f"2024-03-{d:02d}", 1.6 + 0.05 * (d % 3)) for d in range(1, 11)
    ] + [
        ("non_content_empty", f"2024-03-{d:02d}", 1.6 + 0.05 * (d % 3)) for d in range(1, 11)
    ]
    esito = confronto_gruppi(osservazioni)

    assert esito.differenza == pytest.approx(0.0, abs=1e-9)
    # t non e' definito (0/0: dispersione nulla su differenze tutte nulle), ma
    # il verdetto e' una constatazione esatta, non una mancanza di potenza.
    assert math.isnan(esito.t)
    assert esito.verdetto == "INDISTINGUIBILE"


def test_i_due_gruppi_con_effetti_diversi_danno_separazione():
    """CONTENT_EMPTY fermo, non-CONTENT_EMPTY che reagisce: il verdetto passa."""
    from scripts.event_study_h_a_610 import confronto_gruppi

    osservazioni = [
        ("content_empty", f"2024-03-{d:02d}", 0.96 + 0.01 * (d % 2)) for d in range(1, 26)
    ] + [
        ("non_content_empty", f"2024-03-{d:02d}", 1.9 + 0.10 * (d % 3)) for d in range(1, 26)
    ]
    esito = confronto_gruppi(osservazioni)

    assert esito.differenza > 0
    assert esito.verdetto == "SEPARA"


def test_il_confronto_richiede_giornate_in_entrambi_i_gruppi():
    """Un gruppo privo di osservazioni non da una differenza: INSUFFICIENT_N.

    Il detector riconosce il 2,5% della popolazione: su una giornata stretta
    puo' non restarne nessuno. In quel caso la differenza non e' 0, e' non
    calcolabile — e "non calcolabile" batte ogni verdetto.
    """
    from scripts.event_study_h_a_610 import confronto_gruppi

    solo_non_template = [
        ("non_content_empty", f"2024-03-{d:02d}", 1.9) for d in range(1, 26)
    ]
    esito = confronto_gruppi(solo_non_template)

    assert esito.verdetto == "INSUFFICIENT_N"
    assert esito.n_giorni_content_empty == 0


def test_dispersione_nulla_con_differenza_non_nulla_non_autorizza_pass():
    """Il caso degenere inverso: se=0 ma differenza != 0 resta INSUFFICIENT_N.

    E' il caso che la review non aveva considerato. Con se = 0 il t vale
    infinito e un'implementazione ingenua lo passerebbe a PASS: un t infinito
    non e' una misura, e' un denominatore sparito. Senza errore standard
    stimabile non si autorizza nessun verdetto direzionale.
    """
    from scripts.event_study_h_a_610 import confronto_gruppi

    osservazioni = [
        ("content_empty", f"2024-03-{d:02d}", 1.0) for d in range(1, 11)
    ] + [
        ("non_content_empty", f"2024-03-{d:02d}", 2.0) for d in range(1, 11)
    ]
    esito = confronto_gruppi(osservazioni)

    assert esito.differenza == pytest.approx(1.0)
    assert esito.se == 0.0
    assert math.isnan(esito.t) or math.isinf(esito.t)
    assert esito.verdetto == "INSUFFICIENT_N"


# ---------- classify_timing (review PR #641, punto 6) ----------


def test_la_classificazione_del_timing_delega_al_rilevatore_di_produzione():
    """H-A nomina `classify_timing` accanto a `content_empty_title_reason`.

    Il rilevatore di #607 filtra su RETROSPECTIVE **e** CONTENT_EMPTY: sono due
    marche diverse e la Leva A scarterebbe gli articoli di entrambe. Misurare
    solo la seconda lascia mettere a tacere metà della leva con un t verde.

    La classificazione e' delegata, non ricostruita (regola #169/#467): i
    limiti di seduta li decide il calendario, e qui devono essere gli stessi
    che in produzione.
    """
    from scripts.event_study_h_a_610 import bounds_seduta, classifica_timing

    # Un istante di giornata: midnight UTC e' il 4 marzo a New York, quindi
    # `bounds_seduta` aggancia correttamente la seduta precedente.
    apertura, chiusura = bounds_seduta(datetime(2024, 3, 5, 15, 0, tzinfo=timezone.utc))
    assert (apertura, chiusura) == (
        datetime(2024, 3, 5, 14, 30, tzinfo=timezone.utc),   # 09:30 ET = 14:30 UTC (EST)
        datetime(2024, 3, 5, 21, 0, tzinfo=timezone.utc),    # 16:00 ET = 21:00 UTC
    )

    # Prima dell'apertura, dentro, dopo: le tre marche di production.
    assert classifica_timing("2024-03-05T13:00:00Z", apertura, chiusura) == "ANTICIPATORY"
    assert classifica_timing("2024-03-05T15:00:00Z", apertura, chiusura) == "CONCURRENT"
    assert classifica_timing("2024-03-05T22:00:00Z", apertura, chiusura) == "RETROSPECTIVE"


def test_l_articolo_che_o_il_livello_dossier_taggia_content_empty():
    """L'esito di H-A copre i due gruppi che #607 vuole filtrare.

    Un RETROSPECTIVE non templatizzato e' un CONTENT_EMPTY per il livello
    dossier (`_content_empty_reason` restituisce RETROSPECTIVE_TIMING), ma non
    per `content_empty_title_reason`: i due predicati non coincidono, ed e' il
    motivo per cui il gruppo va pubblicato con la sua provenienza.
    """
    from src.analysis.dossier.article_coverage import (
        _content_empty_reason,
        content_empty_title_reason,
    )

    # Un titolo qualsiasi, niente template: il predicato sul titolo no.
    assert content_empty_title_reason("Box Expands Its Partnership With Microsoft") is None
    # Ma il percorso di produzione lo marca CONTENT_EMPTY per il timing.
    assert _content_empty_reason([{"title": "Box Expands Its Partnership"}], "ISSUER_SPECIFIC", "RETROSPECTIVE") \
        == "RETROSPECTIVE_TIMING"


def test_l_artefatto_pubblica_i_due_gruppi_con_la_loro_provenienza():
    """Ogni osservazione porta con se' *perche'* e' nel suo gruppo.

    Senza questa colonna un lettore non può distinguere «template riconosciuto
    dal titolo» da «articolo fuori tempo massimo», che sono filtri diversi con
    lo stesso nome: aggiungerne uno non implementa l'altro.
    """
    from scripts.event_study_h_a_610 import raggruppa_per_gruppo

    osservazioni = [
        ("content_empty", "TEMPLATE_TITLE", "2024-03-05", 1.5),
        ("content_empty", "RETROSPECTIVE_TIMING", "2024-03-06", 1.4),
        ("non_content_empty", None, "2024-03-05", 2.0),
    ]
    per_gruppo = raggruppa_per_gruppo(osservazioni)

    assert per_gruppo["content_empty"]["provenienza"] == {"TEMPLATE_TITLE": 1, "RETROSPECTIVE_TIMING": 1}
    assert per_gruppo["non_content_empty"]["provenienza"] == {}


def test_i_confini_di_seduta_seguono_l_ora_legale():
    """Luglio (EDT) e inverno (EST): la stessa ora locale, un'ora UTC di scarto.

    Copre il difetto che `bounds_seduta` dichiara di evitare: la crontab
    `14-21` di `celery_app.py` e' giusta d'estate e sbagliata d'inverno, e
    sbaglierebbe di un'ora per meta' anno — quindi metterebbe a metà degli
    articoli diurno la marca RETROSPECTIVE che li vorrebbe ANTICIPATORY.
    """
    from scripts.event_study_h_a_610 import bounds_seduta

    # 10 luglio 2024: EDT, 09:30 locale = 13:30 UTC
    estate = bounds_seduta(datetime(2024, 7, 10, 15, 0, tzinfo=timezone.utc))
    # 10 dicembre 2024: EST, 09:30 locale = 14:30 UTC
    inverno = bounds_seduta(datetime(2024, 12, 10, 15, 0, tzinfo=timezone.utc))

    assert estate[0].hour == 13
    assert inverno[0].hour == 14
    # La chiusura segue lo stesso spostamento.
    assert estate[1].hour == 20
    assert inverno[1].hour == 21


# ---------- Ticker canonico (regola #169/#467: la riduzione e' di produzione) ----------


def test_il_ticker_primario_passa_dalla_canonizzazione_di_produzione():
    """`simboli[0].upper()` non e' la riduzione di produzione.

    Il percorso live porta ogni simbolo attraverso `canonicalizza_ticker`
    (`src/workers/ingestion.py:701`) prima di usarlo: e' la regola che ha
    riparato #226, dove `BRKB` restava `BRKB` e 96 segnali — sei dei quali
    sopra il gate — non trovavano mai `BRK.B` in watchlist.

    Benzinga scrive `BRK-B`; la watchlist scrive `BRK.B`. Con `.upper()` H-A
    chiederebbe le barre di `BRK-B` ad Alpaca e riceverebbe una serie vuota
    per ogni articolo di Berkshire: non un errore, un buco di copertura che
    l'artefatto conterebbe fra i mancanti senza dire perché.
    """
    from scripts.event_study_h_a_610 import ticker_primario

    assert ticker_primario(["BRK-B"]) == "BRK.B"
    assert ticker_primario(["brk-b"]) == "BRK.B"
    assert ticker_primario(["aapl", "msft"]) == "AAPL"


def test_l_articolo_senza_ticker_non_ha_ticker_primario():
    """Nessun simbolo => nessuna misura: la pipeline live lo scarta gia' li'."""
    from scripts.event_study_h_a_610 import ticker_primario

    assert ticker_primario([]) is None
    assert ticker_primario(None) is None


def test_il_simbolo_passo_viene_conservato_e_non_inventato():
    """Cosa `canonicalizza_ticker` NON fa: non è un validatore.

    Un simbolo che non conosce passa invariato — per disegno, perché la sua
    funzione è riportare alla forma della watchlist, non decidere se il
    simbolo è legittimo. Il validatore del percorso live è un altro:
    `sentiment.run_inference` scarta l'item quando `sanitize_ticker` non
    restituisce un simbolo.

    Lo dichiaro perché il conteggio dei mancanti di H-A non distingue "simbolo
    inesistente" da "nessun titolo scambiato in quei 5 minuti": se i due
    casi si confondessero, il buco BRK-B della prima versione sarebbe
    invisibile.
    """
    from scripts.event_study_h_a_610 import ticker_primario

    assert ticker_primario(["BRK-B"]) == "BRK.B"   # noto, riportato
    assert ticker_primario(["\x00\x01"]) == "\x00\x01"  # ignoto, passato
    assert ticker_primario([]) is None


# ---------- Integrazione: il percorso composto produce il verdetto di H-A ----------


def _articolo_610(
    identificativo: str, ticker: str, ts: str, titolo: str
) -> dict:
    return {
        "id": identificativo,
        "created_at": ts,
        "updated_at": ts,
        "symbols": [ticker],
        "headline": titolo,
        "summary": "Corpo.",
        "content": "<p>Corpo.</p>",
    }


def test_il_percorso_composto_puo_pronunciare_separa_e_indistinguibile():
    """Su `_esegui_anno`: nessun evento, ma i due gruppi si separano lo stesso.

    E' la regressione che lega i tre fix. Il picco e' identico per tutti gli
    articoli — cioe' il mercato non reagisce a nessuna delle notizie, e il
    rapporto grezzo resta sotto 1 per tutti. Prima: entrambi i gruppi escono
    FAIL e H-A non puo' pronunciare "indistinguibile", che e' la sua risposta
    attesa. Ora: se il detector e' davvero inerte l'eccesso e' ~0 per tutti e il
    verdetto e' INDISTINGUIBILE; se distingue, SEPARA.

    Il test fallisce se il verdetto dipende dal riferimento implicito 1.0.
    """
    from scripts.event_study_h_a_610 import _esegui_anno

    rng = np.random.default_rng(4242)

    def loader(symbol: str, start: datetime, end: datetime) -> pd.Series:
        # Nessun evento: prezzo con volatilita' costante, rumore iid.
        idx = pd.date_range(start, end, freq="1min", inclusive="left", tz="UTC")
        return pd.Series(100.0 * np.exp(np.cumsum(rng.normal(0, 0.0008, len(idx)))), index=idx)

    articoli = []
    for giorno in range(1, 26):
        for ticker in ("AAPL", "MSFT"):
            articoli.append(_articolo_610(
                f"template-{ticker}-{giorno}", ticker,
                f"2024-03-{giorno:02d}T15:30:00Z",
                "Here Are The Top 5 Upgrades From Last Week",   # template
            ))
            articoli.append(_articolo_610(
                f"normale-{ticker}-{giorno}", ticker,
                f"2024-03-{giorno:02d}T16:30:00Z",
                f"{ticker} Reports Q1 Earnings, Beats Estimates",
            ))

    risultato = _esegui_anno("2024", articoli, loader, escludi_selezionati=False)
    confronto = risultato["confronto_gruppi"]

    # Nessuna notizia muove il prezzo: nessuna separazione, e nessun FAIL.
    assert confronto["verdetto"] in {"INDISTINGUIBILE", "INSUFFICIENT_N"}
    assert confronto["verdetto"] != "SEPARA" or abs(confronto["t"]) >= 3.0
    # I due gruppi sono entrambi popolati e la provenienza dichiarata. Il
    # valore e' la stringa che restituisce il detector di produzione, non
    # un'etichetta dello script: se i due divergono, l'artefetto attribuisce
    # a una marca del detector una provenienza che non e'.
    assert confronto["n_giorni_appaiate"] >= 2
    assert risultato["gruppo_content_empty"]["provenienza"]["RATINGS_LISTICLE_TEMPLATE"] > 0


def test_il_confronto_e_il_verdetto_principale_del_artefatto():
    """L'artefatto dichiara il confronto oltre ai due gruppi presi a se'."""
    from scripts.event_study_h_a_610 import _esegui_anno

    def loader(symbol: str, start: datetime, end: datetime) -> pd.Series:
        idx = pd.date_range(start, end, freq="1min", inclusive="left", tz="UTC")
        return pd.Series(100.0 + np.arange(len(idx)) * 0.01, index=idx)

    articoli = [
        _articolo_610("a", "AAPL", "2024-03-05T15:30:00Z", "Here Are The Top 5 Upgrades From Last Week"),
        _articolo_610("b", "MSFT", "2024-03-06T15:30:00Z", "MSFT Reports Q1 Earnings, Beats Estimates"),
    ]
    risultato = _esegui_anno("2024", articoli, loader, escludi_selezionati=False)

    assert "confronto_gruppi" in risultato
    for campo in ("differenza", "t", "n_giorni_appaiate", "effetto_rilevabile_a_t3", "verdetto"):
        assert campo in risultato["confronto_gruppi"]
    # Il riferimento usato e' dichiarato: 1.0 non e' la nulla.
    assert risultato["riferimento_riportato"]["log"] != 0.0


# ---------- Holm-Bonferroni sulla famiglia delle cinque ipotesi (review, punto 8) ----------


def test_holm_ordina_per_p_value_e_correge_per_posizione():
    """Holm: si ordina per p crescente e ogni soglia è m/(m-k+1).

    Nessun `p * m` sui singoli (Bonferroni) ne' una soglia unica: la correzione
    è progressiva, e questo è ciò che distingue Holm-Bonferroni.
    """
    from scripts.event_study_h_a_610 import holm

    esito = holm({"H-A": 0.010, "H-B": 0.040, "H-C": 0.200, "H-E": 0.600, "H-F": 0.900})
    assert [esito[h]["p"] for h in ("H-A", "H-B", "H-C", "H-E", "H-F")] == \
        [0.010, 0.040, 0.200, 0.600, 0.900]
    # p = 0,010 con m = 5: soglia 1 = 0,05/5 = 0,010 -> rifiutata al limite.
    assert esito["H-A"]["rifiutata"] is True
    assert esito["H-A"]["soglia"] == pytest.approx(0.01)
    # p = 0,040: soglia 2 = 0,05/4 = 0,0125 -> NON rifiutata. Holm e' piu'
    # restrittivo di Bonferroni (che avrebbe dato soglia 0,05 per tutte).
    assert esito["H-B"]["rifiutata"] is False
    assert esito["H-B"]["soglia"] == pytest.approx(0.0125)
    # p = 0,200: soglia 3 × 0,05 = 0,15 -> non rifiutata, e la correzione
    # si ferma: sotto Holm nessuna ipotesi successiva puo' essere rifiutata.
    assert esito["H-C"]["rifiutata"] is False
    # Oltre il primo non-rifiuto la correzione si ferma: H-E e H-F restano
    # non rifiutate per la loro posizione, non per la propria soglia.
    assert esito["H-E"]["rifiutata"] is False
    assert esito["H-F"]["rifiutata"] is False


def test_holm_si_ferma_al_primo_non_rifiuto():
    """La correzione e' monotona decrescente: dopo un non-rifiuto, niente passa.

    E' la proprieta' che rende Holm-Bonferroni piu' potente di Bonferroni e,
    insieme, quella che impedisce a un p medio di ereditare la rifiutazione di un
    p piccolo che sta solo al suo posto nell'ordinamento.
    """
    from scripts.event_study_h_a_610 import holm

    # Solo la prima ipotesi e' sotto la propria soglia; la seconda no.
    esito = holm({"H-A": 0.01, "H-B": 0.30, "H-C": 0.31, "H-E": 0.32, "H-F": 0.33})
    assert esito["H-A"]["rifiutata"] is True
    assert [esito[h]["rifiutata"] for h in ("H-B", "H-C", "H-E", "H-F")] == [False] * 4


def test_un_ipotesi_indecidibile_non_entra_nella_famiglia_ma_viene_dichiarata():
    """INSUFFICIENT_N non e' un p: non si ordina e non si dichiara rifiutata.

    Il perimetro della famiglia conta m. Inserire un INSUFFICIENT_N come se
    fosse p = 1.0 gonfierebbe la correzione degli altri cinque ipotesi e
    indebolirebbe l'intera famiglia per un'ipotesi che non e' stata decisa.
    """
    from scripts.event_study_h_a_610 import holm

    esito = holm(
        {"H-A": 0.01, "H-B": 0.02},
        indecidibili={"H-E": "INSUFFICIENT_N (3 giornate)", "H-F": "INSUFFICIENT_N"},
    )
    # m = 2, non 4: la soglia di H-A resta 0,05/2 = 0,025.
    assert esito["H-A"]["soglia"] == pytest.approx(0.025)
    assert "H-E" in esito["indecidibili"]
    assert esito["indecidibili"]["H-E"].startswith("INSUFFICIENT_N")
    assert "H-E" not in esito


def test_la_famiglia_di_ha_resta_dichiarata_in_artefatto():
    """Finche' la famiglia non e' completa, l'artefatto dichiara l'attesa.

    H-A e' una delle cinque ipotesi primarie: applicarle oggi la correzione
    sulla famiglia di uno solo darebbe a H-A una potenza che non ha e
    pubblicarebbe un verdetto di famiglia prima che la famiglia esista.
    """
    from scripts.event_study_h_a_610 import stato_famiglia_holm

    stato = stato_famiglia_holm(p_value=0.001, famiglia_attese=("H-A", "H-B", "H-C", "H-E", "H-F"),
                                ipotesi_disponibili=("H-A",))
    assert stato["famiglia"] == ["H-A"]
    assert stato["attese"] == ["H-A", "H-B", "H-C", "H-E", "H-F"]
    assert stato["completa"] is False
    assert stato["p"] == 0.001
    # Finche' non e' completa, nessuna correzione e' pubblicata come verdetto.
    assert stato["p_holm"] is None
    assert "non applicata" in stato["nota"]


# ---------- Copertura prezzi degradata: dichiarata, non silenziosa ----------


def test_la_copertura_prezzi_degradata_e_dichiarata_nell_artefatto():
    """Un fetch che vuota il campione per meta' va detto, non assorbito.

    Il caso è quello del pilota 2026-09-16: Alpaca rifiuta l'intera richiesta
    SIP e la finestra si tronca, restano i simboli meno liquidi e l'effetto
    **gonfia** (+0,678% → +0,936%). Senza dichiarazione, un artefatto con
    t = 3,4 letta come PASS sarebbe misurato su un campione selezionato dal
    fallimento stesso — cioè dal difetto che doveva essere escluso.

    La misura non puo' distinguere "nessun titolo scambiato in quei 5 minuti"
    da "simbolo inesistente": entrambi danno ratio None. Quel che puo' fare, e
    che e' il suo perimetro, è dichiarare la quota di mancanti: un lettore vede
    che il campione è coperto al 54% e non lo confonde con una misura piena.
    """
    from scripts.event_study_h_a_610 import _esegui_anno

    def loader(symbol: str, start: datetime, end: datetime) -> pd.Series:
        idx = pd.date_range(start, end, freq="1min", inclusive="left", tz="UTC")
        if symbol == "MSFT":          # meta' del campione cade
            return pd.Series(dtype=float)
        return pd.Series(100.0 * np.exp(np.cumsum(np.random.default_rng(1).normal(0, 0.001, len(idx)))),
                         index=idx)

    articoli = [
        _articolo_610(f"a{d}", "AAPL", f"2024-03-{d:02d}T15:30:00Z", "AAPL Reports Q1 Earnings, Beats Estimates")
        for d in range(1, 16)
    ] + [
        _articolo_610(f"m{d}", "MSFT", f"2024-03-{d:02d}T16:30:00Z", "Here Are The Top 5 Upgrades From Last Week")
        for d in range(1, 16)
    ]

    risultato = _esegui_anno("2024", articoli, loader, escludi_selezionati=False)
    copertura = risultato["copertura_prezzi"]

    assert copertura["n_temporale"] == 30
    assert copertura["n_calcolati"] == 15
    assert copertura["quota_mancanti"] == pytest.approx(0.5)
    # Un quarto delle osservazioni manca: dichiarato, e il verdetto lo sa.
    assert copertura["campione_degradato"] is True


def test_un_campione_completo_non_e_marchiato_degradato():
    """La dichiarazione di degrado deve valere per qualcosa di diverso da 0."""
    from scripts.event_study_h_a_610 import quota_copertura_prezzi

    assert quota_copertura_prezzi(10, 10)["campione_degradato"] is False
    assert quota_copertura_prezzi(10, 4)["campione_degradato"] is True
    # Campione vuoto: non "completo", e nemmeno "quasi completo".
    assert quota_copertura_prezzi(0, 10)["quota_mancanti"] == pytest.approx(1.0)
