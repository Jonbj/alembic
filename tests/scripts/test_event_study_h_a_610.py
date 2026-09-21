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
    ClusteredMean,
    PopolazionePerAnno,
    VolatilityRatio,
    articoli_per_anno,
    calcola_rapporto,
    classifica,
    clustered_mean,
    effetto_rilevabile_a_t3,
    fetch_minute_bars,
    leggi_archivio,
    merged_per_day_means,
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


# ---------- Clustered mean ----------


def test_clustered_mean_ignorando_grappoli_singleton():
    """Un cluster da 1 non contribuisce al SE cluster-robust.

    La statistica cluster-robust richiede almeno 2 cluster per essere
    definita. Lo script NON scarta i singleton dal calcolo della media
    (sono osservazioni), ma li esclude dal SE — un singleton non dice
    nulla sulla variabilita' between-cluster.
    """
    # 3 cluster: due da 3 e uno da 1. Il SE si calcola sui 2 cluster "validi".
    obs = [(1, 1.5), (1, 1.4), (1, 1.6), (2, 2.5), (2, 2.4), (2, 2.6), (3, 0.0)]
    risultato = clustered_mean(obs)
    assert isinstance(risultato, ClusteredMean)
    # Media pesata per osservazione: 6/7≈0.857 + 1/7*0 = 0.857... + niente
    media_attesa = (1.5 + 1.4 + 1.6 + 2.5 + 2.4 + 2.6 + 0.0) / 7
    assert risultato.media == pytest.approx(media_attesa)
    # Il singleton non rende il SE infinito
    assert math.isfinite(risultato.t)
    # n_cluster validi = 2
    assert risultato.n_cluster_validi == 2


def test_clustered_mean_resto_zero():
    """Tutti i cluster sono singleton: SE non definito, t = inf, n_cluster_validi = 0.

    Questo e' il caso che diventa INSUFFICIENT_N anche se n articoli e'
    alto: una sola osservazione per giorno non consente di separare la
    variabilita' between-day dalla within-day.
    """
    obs = [(1, 1.0), (2, 1.1), (3, 0.9)]
    risultato = clustered_mean(obs)
    assert risultato.n_cluster_validi == 0
    assert math.isnan(risultato.t) or math.isinf(risultato.t)


# ---------- effetto_rilevabile_a_t3 ----------


def test_effetto_rilevabile_a_t3_calibra_su_n_cluster():
    """Con n_cluster=2 l'effetto minimo rilevabile e' enorme.

    Vero: sqrt(n) * sqrt(1-rho^2)/(1+rho^2) — non vado a implementare la
    formula ICC qui. Lo script la prende dal modulo statistico standard e
    questo test asserisce solo che la funzione esiste e ritorna un numero
    finite positivo.
    """
    eff = effetto_rilevabile_a_t3(n_cluster=2, n_obs=20, t_target=3.0)
    assert eff > 0
    assert math.isfinite(eff)


def test_effetto_rilevabile_a_t3_piu_cluster_minore_effetto():
    """Crescere n_cluster riduce (non aumenta) l'effetto minimo rilevabile.

    Con rho=0 (within = between), l'effetto minimo a t=3 e' ~3/sqrt(n).
    Verifico solo la monotonia — la formula esatta dipende dall'ICC assunto.
    """
    eff_2 = effetto_rilevabile_a_t3(n_cluster=2, n_obs=20)
    eff_50 = effetto_rilevabile_a_t3(n_cluster=50, n_obs=500)
    assert eff_50 < eff_2


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
    out = leggi_archivio(tmp_path)
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
    out = leggi_archivio(tmp_path)
    assert len(out) == 2


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