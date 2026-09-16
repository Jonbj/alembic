#!/usr/bin/env python3
"""Il gap fuori orario e' incassabile in pre-market? (issue #608)

Misura di **sola lettura**. Non invia ordini, nemmeno in paper, e non scrive
nulla su `news_log`, `sentiment_signals` o Redis.

Pre-registrazione: `docs/evidence/PREREGISTRAZIONE_ESEGUIBILITA_PREMARKET_2026-09-16.md`
(campione, outcome, statistica e **soglia** dichiarati prima dell'esecuzione).

QUATTRO MISURE, nell'ordine della DoD di #608:

  1. liquidita' pre-market per fascia oraria (04:00-07:00, 07:00-08:00,
     08:00-09:00, 09:00-09:30 ET): volume, trade, controvalore e — la voce che
     decide davvero — la quota di (simbolo, seduta) con ZERO scambi nella fascia.
  2. quota di gap gia' consumata, nella forma che risponde alla domanda e non
     soffre del denominatore piccolo:
        residuo(t) = sign(score) x [ (open-p_t)/p_t - (openSPY-pSPY_t)/pSPY_t ]
     cioe' quanto resta da incassare entrando a `t` invece che al close
     precedente. Inferenza clusterizzata **per giornata**, come #606.
  3. costo di attraversamento da quote NBBO SIP: mezzo spread relativo mediano
     e profondita' al tocco in dollari, contro il controvalore d'ordine
     EMPIRICO (tabella `trades`, non `config/trading.yaml`).
  4. vincoli del broker: descritti nel rapporto, non qui.

DIFETTO DA NON RIPETERE (§3 della pre-registrazione, §1 di quella di #606):
Alpaca rifiuta l'INTERA richiesta con `subscription does not permit querying
recent SIP data` quando la finestra tocca l'embargo sul dato recente. Nel pilota
questo ha portato n da 330 a 68 eliminando **i simboli piu' liquidi**, cioe'
auto-selezionando il campione al contrario. Qui la finestra e' troncata a
`now - GIORNI_EMBARGO` e **ogni fetch fallito aborta la misura**: mai proseguire
su cio' che resta.

Uso:
    .venv/bin/python scripts/measure_608_premarket_feasibility.py \
        --out docs/evidence/premarket_feasibility_608.json
"""

from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import sys
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.measure_169_dedup_rules import scelta_produzione  # noqa: E402

ET = ZoneInfo("America/New_York")

# --- parametri dichiarati nella pre-registrazione, non rivedibili a posteriori ---
SOGLIA_SCORE = 0.10
LORDO_BP = 56.0  # +0,560% clusterizzato del pilota (#606)
SOGLIA_NETTO_BP = LORDO_BP / 3.0  # 18,7 bp: sotto, la domanda non e' piu' decidibile
DISPERSIONE_GIORNALIERA = 0.0167  # dal pilota, usata per la potenza
GIORNATE_A_56BP = 80  # potenza dichiarata in #606
GIORNI_EMBARGO = 3
BENCHMARK = "SPY"
SOGLIA_GAP_DIAGNOSTICO = 0.0020  # |gap| >= 0,20% per il rapporto diagnostico

# fasce orarie ET: (etichetta, inizio, fine)
FASCE = [
    ("04:00-07:00", time(4, 0), time(7, 0)),
    ("07:00-08:00", time(7, 0), time(8, 0)),
    ("08:00-09:00", time(8, 0), time(9, 0)),
    ("09:00-09:30", time(9, 0), time(9, 30)),
]
# ore di esecuzione esaminate per il residuo
ORE_ESECUZIONE = [time(7, 0), time(8, 0), time(9, 0), time(9, 29)]
# finestre quote: (etichetta, inizio, fine) — 5 minuti che chiudono sulla fascia
FINESTRE_QUOTE = [
    ("06:55-07:00", time(6, 55), time(7, 0)),
    ("07:55-08:00", time(7, 55), time(8, 0)),
    ("08:55-09:00", time(8, 55), time(9, 0)),
    ("09:25-09:30", time(9, 25), time(9, 30)),
    ("09:30-09:31", time(9, 30), time(9, 31)),  # riferimento in orario
]


class MisuraAbortita(RuntimeError):
    """Un fetch e' fallito: la misura si ferma, non si riduce il campione."""


# --------------------------------------------------------------------------- #
# popolazione
# --------------------------------------------------------------------------- #

_SQL_OFFHOURS = """
SELECT s.id, s.symbol, s.score, s.confidence, s.fallback_used,
       s.generated_at, s.published_at
  FROM sentiment_signals s
  JOIN news_log n ON n.id = s.news_log_id
 WHERE n.source = 'alpaca_benzinga'
   AND s.published_at IS NOT NULL
   AND abs(s.score) >= %(soglia)s
   AND NOT (
        extract(dow FROM s.published_at AT TIME ZONE 'America/New_York') BETWEEN 1 AND 5
    AND (s.published_at AT TIME ZONE 'America/New_York')::time >= time '09:30'
    AND (s.published_at AT TIME ZONE 'America/New_York')::time <  time '16:00'
   )
 ORDER BY s.published_at
"""


def carica_segnali_fuori_orario(conn) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(_SQL_OFFHOURS, {"soglia": SOGLIA_SCORE})
        righe = cur.fetchall()
    return [
        {
            "id": r[0],
            "symbol": r[1],
            "score": float(r[2]),
            "confidence": float(r[3]) if r[3] is not None else None,
            "fallback": bool(r[4]),
            "generated_at": r[5],
            "published_at": r[6],
        }
        for r in righe
    ]


def controvalori_ordine(conn, giorni: int = 60) -> list[float]:
    """Controvalore d'ingresso EMPIRICO, non il cap di config."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT entry_notional FROM trades "
            " WHERE entry_notional IS NOT NULL AND entry_notional > 0 "
            "   AND entry_time >= now() - make_interval(days => %s)",
            (giorni,),
        )
        return sorted(float(r[0]) for r in cur.fetchall())


# --------------------------------------------------------------------------- #
# calendario
# --------------------------------------------------------------------------- #


def carica_calendario(inizio: date, fine: date) -> list[dict]:
    """Sedute di borsa dal calendario Alpaca.

    #372: `giorno.date` e' una data di calendario locale al mercato, NON un
    istante UTC. Gli orari `open`/`close` sono ore ET naive: vanno localizzati
    su America/New_York, mai interpretati come UTC.
    """
    from alpaca.trading.client import TradingClient
    from alpaca.trading.requests import GetCalendarRequest

    client = TradingClient(
        os.environ["ALPACA_API_KEY"], os.environ["ALPACA_SECRET_KEY"], paper=True
    )
    try:
        giorni = client.get_calendar(GetCalendarRequest(start=inizio, end=fine))
    except Exception as exc:  # pragma: no cover - rete
        raise MisuraAbortita(f"calendario Alpaca non recuperabile: {exc}") from exc
    sedute = []
    for g in giorni:
        sedute.append(
            {
                "data": g.date,
                "apertura": datetime.combine(g.date, g.open.time(), tzinfo=ET),
                "chiusura": datetime.combine(g.date, g.close.time(), tzinfo=ET),
            }
        )
    return sedute


def seduta_di_reazione(published_at: datetime, sedute: list[dict]) -> dict | None:
    """La prima seduta che APRE dopo `published_at`."""
    for s in sedute:
        if s["apertura"] > published_at:
            return s
    return None


# --------------------------------------------------------------------------- #
# dati di mercato
# --------------------------------------------------------------------------- #


def _client_dati():
    from alpaca.data.historical import StockHistoricalDataClient

    return StockHistoricalDataClient(
        os.environ["ALPACA_API_KEY"], os.environ["ALPACA_SECRET_KEY"]
    )


def scarica_barre_minuto(
    client, simboli: list[str], inizio: datetime, fine: datetime
) -> dict[str, list[dict]]:
    """Barre al minuto SIP. Un fallimento ABORTA: non riduce il campione."""
    from alpaca.data.enums import DataFeed
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame

    try:
        risposta = client.get_stock_bars(
            StockBarsRequest(
                symbol_or_symbols=sorted(set(simboli)),
                timeframe=TimeFrame.Minute,
                start=inizio,
                end=fine,
                feed=DataFeed.SIP,
                adjustment="all",
            )
        )
    except Exception as exc:  # pragma: no cover - rete
        raise MisuraAbortita(
            f"barre al minuto non recuperabili per {sorted(set(simboli))[:5]}... "
            f"[{inizio} -> {fine}]: {exc}"
        ) from exc
    fuori: dict[str, list[dict]] = defaultdict(list)
    for simbolo, barre in (risposta.data or {}).items():
        for b in barre:
            fuori[simbolo].append(
                {
                    "ts": b.timestamp.astimezone(ET),
                    "open": float(b.open),
                    "high": float(b.high),
                    "low": float(b.low),
                    "close": float(b.close),
                    "volume": float(b.volume or 0.0),
                    "trades": float(b.trade_count or 0.0),
                    "vwap": float(b.vwap) if b.vwap else float(b.close),
                }
            )
    for barre in fuori.values():
        barre.sort(key=lambda x: x["ts"])
    return dict(fuori)


def scarica_quote(
    client, simboli: list[str], inizio: datetime, fine: datetime
) -> dict[str, list[dict]]:
    from alpaca.data.enums import DataFeed
    from alpaca.data.requests import StockQuotesRequest

    try:
        risposta = client.get_stock_quotes(
            StockQuotesRequest(
                symbol_or_symbols=sorted(set(simboli)),
                start=inizio,
                end=fine,
                feed=DataFeed.SIP,
            )
        )
    except Exception as exc:  # pragma: no cover - rete
        raise MisuraAbortita(
            f"quote non recuperabili per {sorted(set(simboli))[:5]}... "
            f"[{inizio} -> {fine}]: {exc}"
        ) from exc
    fuori: dict[str, list[dict]] = defaultdict(list)
    for simbolo, quote in (risposta.data or {}).items():
        for q in quote:
            bid, ask = float(q.bid_price or 0.0), float(q.ask_price or 0.0)
            if bid <= 0 or ask <= 0 or ask < bid:
                continue  # quote incrociate o a un lato solo: non attraversabili
            mid = (bid + ask) / 2.0
            fuori[simbolo].append(
                {
                    "ts": q.timestamp.astimezone(ET),
                    "spread_rel": (ask - bid) / mid,
                    # bid_size/ask_size Alpaca sono in AZIONI, non in lotti da 100:
                    # verificato sui dati (NVDA 100/200/300, F 2500/7700 a $13).
                    # Moltiplicare per 100 gonfiava la profondita' al tocco di 100x.
                    "tocco_usd": min(float(q.bid_size or 0), float(q.ask_size or 0)) * mid,
                }
            )
    return dict(fuori)


def scarica_barre_giornaliere(
    client, simboli: list[str], inizio: date, fine: date
) -> dict[str, dict[date, dict]]:
    from alpaca.data.enums import DataFeed
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame

    try:
        risposta = client.get_stock_bars(
            StockBarsRequest(
                symbol_or_symbols=sorted(set(simboli)),
                timeframe=TimeFrame.Day,
                start=datetime.combine(inizio, time(0, 0), tzinfo=timezone.utc),
                end=datetime.combine(fine, time(0, 0), tzinfo=timezone.utc),
                feed=DataFeed.SIP,
                adjustment="all",
            )
        )
    except Exception as exc:  # pragma: no cover - rete
        raise MisuraAbortita(f"barre giornaliere non recuperabili: {exc}") from exc
    fuori: dict[str, dict[date, dict]] = defaultdict(dict)
    for simbolo, barre in (risposta.data or {}).items():
        for b in barre:
            g = b.timestamp.astimezone(ET).date()
            fuori[simbolo][g] = {"open": float(b.open), "close": float(b.close)}
    return dict(fuori)


# --------------------------------------------------------------------------- #
# utilità
# --------------------------------------------------------------------------- #


def ultimo_prezzo_entro(barre: list[dict], limite: datetime) -> float | None:
    """Ultimo prezzo scambiato a `limite` o prima, nella STESSA giornata ET."""
    scelto = None
    for b in barre:
        if b["ts"] > limite:
            break
        if b["ts"].date() != limite.date():
            continue
        scelto = b
    return scelto["close"] if scelto else None


def media_t(valori_per_giorno: dict[date, list[float]]) -> dict[str, Any]:
    """Media delle medie giornaliere e t sugli errori standard FRA giornate.

    L'unita' di inferenza e' la giornata: gli eventi della stessa seduta
    condividono il fattore di mercato e non sono indipendenti (#606 §5).
    """
    medie = [statistics.fmean(v) for v in valori_per_giorno.values() if v]
    n = len(medie)
    if n < 2:
        return {"n_giornate": n, "n_eventi": sum(len(v) for v in valori_per_giorno.values())}
    media = statistics.fmean(medie)
    ds = statistics.stdev(medie)
    se = ds / math.sqrt(n)
    return {
        "n_giornate": n,
        "n_eventi": sum(len(v) for v in valori_per_giorno.values()),
        "media_bp": media * 10_000,
        "t": media / se if se else None,
        "ds_giornaliera_bp": ds * 10_000,
        "effetto_rilevabile_a_t3_bp": 3 * se * 10_000,
        "giornate_positive": sum(1 for m in medie if m > 0),
    }


def percentile(valori: list[float], p: float) -> float | None:
    if not valori:
        return None
    ordinati = sorted(valori)
    k = (len(ordinati) - 1) * p / 100.0
    basso, alto = math.floor(k), math.ceil(k)
    if basso == alto:
        return ordinati[int(k)]
    return ordinati[basso] * (alto - k) + ordinati[alto] * (k - basso)


def giornate_necessarie(netto_bp: float) -> float | None:
    """80 giornate bastano su 56 bp; su `x` bp ne servono 80 x (56/x)^2."""
    if netto_bp is None or netto_bp <= 0:
        return None
    return GIORNATE_A_56BP * (LORDO_BP / netto_bp) ** 2


# --------------------------------------------------------------------------- #
# misura
# --------------------------------------------------------------------------- #


def costruisci_popolazione(segnali: list[dict], sedute: list[dict], taglio: datetime):
    """Una osservazione per (simbolo, seduta di reazione), regola di produzione."""
    gruppi: dict[tuple[date, str], list[dict]] = defaultdict(list)
    senza_seduta = 0
    oltre_taglio = 0
    for s in segnali:
        seduta = seduta_di_reazione(s["published_at"], sedute)
        if seduta is None:
            senza_seduta += 1
            continue
        if seduta["chiusura"] > taglio:
            oltre_taglio += 1
            continue
        s["seduta"] = seduta
        gruppi[(seduta["data"], s["symbol"])].append(s)
    for g in gruppi.values():
        g.sort(key=lambda x: x["generated_at"])
    scelti = [scelta_produzione(g) for g in gruppi.values()]
    return scelti, {"senza_seduta_di_reazione": senza_seduta, "oltre_taglio_embargo": oltre_taglio}


def misura(conn, verbose: bool = True, max_sedute: int | None = None) -> dict[str, Any]:
    taglio = datetime.now(timezone.utc) - timedelta(days=GIORNI_EMBARGO)

    segnali = carica_segnali_fuori_orario(conn)
    if not segnali:
        raise MisuraAbortita("popolazione fuori orario vuota")
    primo = min(s["published_at"] for s in segnali)
    ultimo = max(s["published_at"] for s in segnali)

    sedute = carica_calendario(
        (primo.astimezone(ET).date() - timedelta(days=5)),
        (ultimo.astimezone(ET).date() + timedelta(days=10)),
    )
    osservazioni, scarti = costruisci_popolazione(segnali, sedute, taglio)
    if not osservazioni:
        raise MisuraAbortita("nessuna osservazione dopo il troncamento dell'embargo")

    per_data: dict[date, list[dict]] = defaultdict(list)
    for o in osservazioni:
        per_data[o["seduta"]["data"]].append(o)

    client = _client_dati()

    # barre giornaliere: close precedente e open della seduta di reazione
    simboli = sorted({o["symbol"] for o in osservazioni} | {BENCHMARK})
    giornaliere = scarica_barre_giornaliere(
        client,
        simboli,
        min(per_data) - timedelta(days=10),
        max(per_data) + timedelta(days=2),
    )
    indice_sedute = {s["data"]: i for i, s in enumerate(sedute)}

    def seduta_precedente(d: date) -> date | None:
        i = indice_sedute.get(d)
        return sedute[i - 1]["data"] if i and i > 0 else None

    # accumulatori
    liquidita: dict[str, dict[str, list[float]]] = {
        e: {"volume": [], "trades": [], "controvalore": [], "zero": []} for e, _, _ in FASCE
    }
    # Tre varianti, perche' il residuo a un'ora `t` calcolato su una notizia
    # pubblicata DOPO `t` e' look-ahead: e' un rendimento che nessuno poteva
    # prendere. `tutti` resta come descrizione della forma della curva; la
    # raccomandazione si legge su `scorati`, che e' cio' che il sistema di oggi
    # sa davvero a quell'ora.
    VARIANTI = ("tutti", "pubblicati", "scorati")
    residui: dict[str, dict[str, dict[date, list[float]]]] = {
        v: {
            "close_prec": defaultdict(list),
            **{o.strftime("%H:%M"): defaultdict(list) for o in ORE_ESECUZIONE},
            "open": defaultdict(list),
        }
        for v in VARIANTI
    }
    azionabilita: dict[str, dict[str, int]] = {
        o.strftime("%H:%M"): {"tutti": 0, "pubblicati": 0, "scorati": 0}
        for o in ORE_ESECUZIONE
    }
    quota_consumata: dict[str, list[float]] = {o.strftime("%H:%M"): [] for o in ORE_ESECUZIONE}
    spread: dict[str, dict[str, list[float]]] = {
        e: {"spread_rel": [], "tocco_usd": []} for e, _, _ in FINESTRE_QUOTE
    }
    prezzi_riferimento: list[float] = []
    coperture = {"con_barre": 0, "senza_barre": 0, "senza_giornaliere": 0}

    date_da_lavorare = sorted(per_data)
    if max_sedute:  # solo per lo smoke test: un run parziale NON e' l'esito
        date_da_lavorare = date_da_lavorare[:max_sedute]
    for d in date_da_lavorare:
        gruppo = per_data[d]
        simboli_giorno = sorted({o["symbol"] for o in gruppo} | {BENCHMARK})
        prec = seduta_precedente(d)
        if prec is None:
            coperture["senza_giornaliere"] += len(gruppo)
            continue
        inizio = datetime.combine(d, time(4, 0), tzinfo=ET)
        fine = datetime.combine(d, time(9, 40), tzinfo=ET)
        barre = scarica_barre_minuto(client, simboli_giorno, inizio, fine)

        barre_spy = barre.get(BENCHMARK, [])
        gior_spy = giornaliere.get(BENCHMARK, {})
        if not barre_spy or d not in gior_spy or prec not in gior_spy:
            raise MisuraAbortita(f"benchmark {BENCHMARK} incompleto per la seduta {d}")
        open_spy = gior_spy[d]["open"]
        close_prec_spy = gior_spy[prec]["close"]

        if verbose:
            print(f"  {d}: {len(gruppo)} oss, {len(simboli_giorno)} simboli", flush=True)

        for o in gruppo:
            sim = o["symbol"]
            gior = giornaliere.get(sim, {})
            if d not in gior or prec not in gior:
                coperture["senza_giornaliere"] += 1
                continue
            b = barre.get(sim, [])
            apertura, close_prec = gior[d]["open"], gior[prec]["close"]
            if close_prec <= 0 or apertura <= 0:
                coperture["senza_giornaliere"] += 1
                continue
            segno = 1.0 if o["score"] > 0 else -1.0
            prezzi_riferimento.append(close_prec)

            # (1) liquidita' per fascia
            if b:
                coperture["con_barre"] += 1
            else:
                coperture["senza_barre"] += 1
            for etichetta, da, a in FASCE:
                d_da = datetime.combine(d, da, tzinfo=ET)
                d_a = datetime.combine(d, a, tzinfo=ET)
                dentro = [x for x in b if d_da <= x["ts"] < d_a]
                vol = sum(x["volume"] for x in dentro)
                trd = sum(x["trades"] for x in dentro)
                ctrl = sum(x["volume"] * x["vwap"] for x in dentro)
                liquidita[etichetta]["volume"].append(vol)
                liquidita[etichetta]["trades"].append(trd)
                liquidita[etichetta]["controvalore"].append(ctrl)
                liquidita[etichetta]["zero"].append(1.0 if trd == 0 else 0.0)

            # (2) residuo entrando a t, in eccesso su SPY
            gap_ecc = segno * (
                (apertura - close_prec) / close_prec - (open_spy - close_prec_spy) / close_prec_spy
            )
            for v in VARIANTI:
                residui[v]["close_prec"][d].append(gap_ecc)
                residui[v]["open"][d].append(0.0)
            for ora in ORE_ESECUZIONE:
                limite = datetime.combine(d, ora, tzinfo=ET)
                chiave = ora.strftime("%H:%M")
                azionabilita[chiave]["tutti"] += 1
                if o["published_at"] <= limite:
                    azionabilita[chiave]["pubblicati"] += 1
                if o["generated_at"] <= limite:
                    azionabilita[chiave]["scorati"] += 1
                p = ultimo_prezzo_entro(b, limite)
                p_spy = ultimo_prezzo_entro(barre_spy, limite)
                if p is None or p_spy is None or p <= 0 or p_spy <= 0:
                    continue
                res = segno * ((apertura - p) / p - (open_spy - p_spy) / p_spy)
                residui["tutti"][chiave][d].append(res)
                if o["published_at"] <= limite:
                    residui["pubblicati"][chiave][d].append(res)
                if o["generated_at"] <= limite:
                    residui["scorati"][chiave][d].append(res)
                gap_grezzo = (apertura - close_prec) / close_prec
                if abs(gap_grezzo) >= SOGLIA_GAP_DIAGNOSTICO:
                    quota_consumata[ora.strftime("%H:%M")].append(
                        (p - close_prec) / (apertura - close_prec)
                    )

        # (3) quote
        for etichetta, da, a in FINESTRE_QUOTE:
            q_da = datetime.combine(d, da, tzinfo=ET)
            q_a = datetime.combine(d, a, tzinfo=ET)
            quote = scarica_quote(client, simboli_giorno, q_da, q_a)
            for o in gruppo:
                qs = quote.get(o["symbol"], [])
                if not qs:
                    continue
                spread[etichetta]["spread_rel"].append(
                    statistics.median(x["spread_rel"] for x in qs)
                )
                spread[etichetta]["tocco_usd"].append(
                    statistics.median(x["tocco_usd"] for x in qs)
                )

    return {
        "popolazione": {
            "segnali_fuori_orario": len(segnali),
            "osservazioni_simbolo_seduta": len(osservazioni),
            "simboli": len({o["symbol"] for o in osservazioni}),
            "sedute": len(per_data),
            "da": primo.isoformat(),
            "a": ultimo.isoformat(),
            "taglio_embargo": taglio.isoformat(),
            **scarti,
            **coperture,
        },
        "liquidita": {
            etichetta: {
                "volume_mediano": percentile(v["volume"], 50),
                "trade_mediani": percentile(v["trades"], 50),
                "controvalore_mediano_usd": percentile(v["controvalore"], 50),
                "controvalore_p10_usd": percentile(v["controvalore"], 10),
                "quota_senza_scambi": statistics.fmean(v["zero"]) if v["zero"] else None,
                "n": len(v["zero"]),
            }
            for etichetta, v in liquidita.items()
        },
        "residuo": {
            variante: {k: media_t(v) for k, v in per_ora.items()}
            for variante, per_ora in residui.items()
        },
        "azionabilita": azionabilita,
        "quota_gap_consumata_diagnostico": {
            k: {
                "mediana": percentile(v, 50),
                "p25": percentile(v, 25),
                "p75": percentile(v, 75),
                "n": len(v),
            }
            for k, v in quota_consumata.items()
        },
        "spread": {
            etichetta: {
                "spread_rel_mediano_bp": (percentile(v["spread_rel"], 50) or 0) * 10_000,
                "spread_rel_p75_bp": (percentile(v["spread_rel"], 75) or 0) * 10_000,
                "spread_rel_p90_bp": (percentile(v["spread_rel"], 90) or 0) * 10_000,
                "tocco_mediano_usd": percentile(v["tocco_usd"], 50),
                "tocco_p10_usd": percentile(v["tocco_usd"], 10),
                "n": len(v["spread_rel"]),
            }
            for etichetta, v in spread.items()
        },
    }


def verdetto(
    risultato: dict, controvalori: list[float], variante: str = "scorati"
) -> dict[str, Any]:
    """La regola del §5 della pre-registrazione, applicata alla lettera.

    `variante` = quale insieme di osservazioni conta come azionabile all'ora
    `t`. Il default e' `scorati`: solo i segnali che il sistema di OGGI aveva
    gia' prodotto a quell'ora. Usare `tutti` sarebbe look-ahead.
    """
    size_mediana = percentile(controvalori, 50) or 0.0
    uscita = risultato["spread"].get("09:30-09:31", {})
    costo_uscita_bp = (uscita.get("spread_rel_mediano_bp") or 0.0) / 2.0

    abbinamento = {"07:00": "06:55-07:00", "08:00": "07:55-08:00",
                   "09:00": "08:55-09:00", "09:29": "09:25-09:30"}
    righe = []
    for ora, finestra in abbinamento.items():
        res = risultato["residuo"].get(variante, {}).get(ora, {})
        sp = risultato["spread"].get(finestra, {})
        lordo_bp = res.get("media_bp")
        if lordo_bp is None:
            continue
        costo_ingresso_bp = (sp.get("spread_rel_mediano_bp") or 0.0) / 2.0
        costo_all_in = costo_ingresso_bp + costo_uscita_bp
        netto = lordo_bp - costo_all_in
        tocco = sp.get("tocco_mediano_usd")
        righe.append(
            {
                "ora": ora,
                "residuo_lordo_bp": lordo_bp,
                "t": res.get("t"),
                "effetto_rilevabile_a_t3_bp": res.get("effetto_rilevabile_a_t3_bp"),
                "costo_ingresso_bp": costo_ingresso_bp,
                "costo_uscita_bp": costo_uscita_bp,
                "costo_all_in_bp": costo_all_in,
                "netto_bp": netto,
                "giornate_necessarie": giornate_necessarie(netto),
                "tocco_mediano_usd": tocco,
                "size_oltre_il_tocco": (size_mediana > tocco) if tocco else None,
                "quota_senza_scambi": risultato["liquidita"]
                .get({"07:00": "04:00-07:00", "08:00": "07:00-08:00",
                      "09:00": "08:00-09:00", "09:29": "09:00-09:30"}[ora], {})
                .get("quota_senza_scambi"),
                "azionabili": risultato["azionabilita"].get(ora, {}),
            }
        )

    migliore = max(righe, key=lambda r: r["netto_bp"]) if righe else None
    if migliore is None:
        esito = "INSUFFICIENT_N"
    elif migliore["residuo_lordo_bp"] < (migliore["effetto_rilevabile_a_t3_bp"] or 0):
        esito = "INSUFFICIENT_N"
    elif migliore["netto_bp"] >= SOGLIA_NETTO_BP:
        esito = "RACCOGLIBILE"
    else:
        esito = "NON_RACCOGLIBILE"

    return {
        "esito": esito,
        "variante": variante,
        "soglia_netto_bp": SOGLIA_NETTO_BP,
        "lordo_riferimento_bp": LORDO_BP,
        "size": {
            "mediana_usd": size_mediana,
            "p75_usd": percentile(controvalori, 75),
            "p90_usd": percentile(controvalori, 90),
            "max_usd": max(controvalori) if controvalori else None,
            "n_trade": len(controvalori),
        },
        "per_ora": righe,
        "migliore": migliore,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="docs/evidence/premarket_feasibility_608.json")
    ap.add_argument("--silenzioso", action="store_true")
    ap.add_argument(
        "--max-sedute",
        type=int,
        default=None,
        help="smoke test: lavora solo le prime N sedute. Un run parziale NON e' l'esito.",
    )
    args = ap.parse_args()

    import psycopg2
    from dotenv import load_dotenv

    load_dotenv(str(Path(__file__).resolve().parent.parent / ".env"))
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    try:
        risultato = misura(
            conn, verbose=not args.silenzioso, max_sedute=args.max_sedute
        )
        if args.max_sedute:
            risultato["RUN_PARZIALE"] = (
                f"smoke test su {args.max_sedute} sedute: NON e' l'esito di #608"
            )
        contro = controvalori_ordine(conn)
        risultato["verdetto"] = verdetto(risultato, contro, variante="scorati")
        risultato["verdetto_varianti"] = {
            v: verdetto(risultato, contro, variante=v)
            for v in ("tutti", "pubblicati", "scorati")
        }
    finally:
        conn.close()

    risultato["generato_il"] = datetime.now(timezone.utc).isoformat()
    risultato["prereg"] = "docs/evidence/PREREGISTRAZIONE_ESEGUIBILITA_PREMARKET_2026-09-16.md"
    Path(args.out).write_text(json.dumps(risultato, indent=2, default=str), encoding="utf-8")
    print(json.dumps(risultato["verdetto"], indent=2, default=str))
    print(f"\nscritto: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
