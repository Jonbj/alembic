#!/usr/bin/env python3
"""Test confermativo pre-registrato sul gap delle news fuori orario (#606).

Misura di sola lettura: interroga ``sentiment_signals`` e ``news_log`` e
scarica barre giornaliere SIP. Non scrive su database, Redis o money path.
Prima di 80 sedute l'artefatto pubblica soltanto il conteggio e
``INSUFFICIENT_N``: il valore dell'effetto resta deliberatamente nascosto.

Uso:
    python scripts/measure_606_offhours_gap.py \
        --out docs/evidence/gap_offhours_606.json
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
SOGLIA_SCORE = 0.10
GIORNI_EMBARGO = 3
GIORNATE_RICHIESTE = 80
SOGLIA_T = 3.0
BENCHMARK = "SPY"


class MisuraAbortita(RuntimeError):
    """Dati incompleti o fetch fallito: mai selezionare il campione a posteriori."""


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
    AND (s.published_at AT TIME ZONE 'America/New_York')::time < time '16:00'
   )
 ORDER BY s.published_at
"""


def taglio_embargo(ora: datetime | None = None) -> datetime:
    """Il limite SIP è sempre tre giorni prima dell'istante del run."""
    return (ora or datetime.now(timezone.utc)) - timedelta(days=GIORNI_EMBARGO)


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


def carica_calendario(inizio: date, fine: date) -> list[dict]:
    """Sedute Alpaca, localizzando gli orari naive nel fuso del mercato."""
    from alpaca.trading.client import TradingClient
    from alpaca.trading.requests import GetCalendarRequest

    client = TradingClient(
        os.environ["ALPACA_API_KEY"], os.environ["ALPACA_SECRET_KEY"], paper=True
    )
    try:
        giorni = client.get_calendar(GetCalendarRequest(start=inizio, end=fine))
    except Exception as exc:  # pragma: no cover - rete
        raise MisuraAbortita(f"calendario Alpaca non recuperabile: {exc}") from exc
    return [
        {
            "data": g.date,
            "apertura": datetime.combine(g.date, g.open.time(), tzinfo=ET),
            "chiusura": datetime.combine(g.date, g.close.time(), tzinfo=ET),
        }
        for g in giorni
    ]


def seduta_di_reazione(published_at: datetime, sedute: list[dict]) -> dict | None:
    """La prima seduta la cui apertura segue strettamente la pubblicazione."""
    return next((s for s in sedute if s["apertura"] > published_at), None)


def costruisci_popolazione(
    segnali: list[dict], sedute: list[dict], taglio: datetime
) -> tuple[list[dict], dict[str, int]]:
    """Riduce a (simbolo, seduta) con l'identica regola del ranker in produzione."""
    gruppi: dict[tuple[date, str], list[dict]] = defaultdict(list)
    scarti = {"senza_seduta_di_reazione": 0, "oltre_taglio_embargo": 0}
    for segnale in segnali:
        seduta = seduta_di_reazione(segnale["published_at"], sedute)
        if seduta is None:
            scarti["senza_seduta_di_reazione"] += 1
            continue
        if seduta["chiusura"] > taglio:
            scarti["oltre_taglio_embargo"] += 1
            continue
        segnale["seduta"] = seduta
        gruppi[(seduta["data"], segnale["symbol"])].append(segnale)
    for gruppo in gruppi.values():
        gruppo.sort(key=lambda s: s["generated_at"])
    return [scelta_produzione(g) for g in gruppi.values()], scarti


def _client_dati():
    from alpaca.data.historical import StockHistoricalDataClient

    return StockHistoricalDataClient(
        os.environ["ALPACA_API_KEY"], os.environ["ALPACA_SECRET_KEY"]
    )


def scarica_barre_giornaliere(
    client, simboli: list[str], inizio: date, fine: date
) -> dict[str, dict[date, dict[str, float]]]:
    """Barre SIP aggiustate; qualsiasi risposta fallita interrompe la misura."""
    from alpaca.data.enums import DataFeed
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame

    try:
        risposta = client.get_stock_bars(
            StockBarsRequest(
                symbol_or_symbols=sorted(set(simboli)),
                timeframe=TimeFrame.Day,
                start=datetime.combine(inizio, time.min, tzinfo=timezone.utc),
                end=datetime.combine(fine, time.min, tzinfo=timezone.utc),
                feed=DataFeed.SIP,
                adjustment="all",
            )
        )
    except Exception as exc:  # pragma: no cover - rete
        raise MisuraAbortita(f"barre giornaliere non recuperabili: {exc}") from exc

    fuori: dict[str, dict[date, dict[str, float]]] = defaultdict(dict)
    for simbolo, barre in (risposta.data or {}).items():
        for barra in barre:
            fuori[simbolo][barra.timestamp.astimezone(ET).date()] = {
                "open": float(barra.open), "close": float(barra.close)
            }
    return dict(fuori)


def media_t(valori_per_giorno: dict[date, list[float]]) -> dict[str, Any]:
    """Media delle medie giornaliere e t sugli errori standard fra sedute."""
    medie = [statistics.fmean(v) for v in valori_per_giorno.values() if v]
    n = len(medie)
    comune = {"n_giornate": n, "n_eventi": sum(len(v) for v in valori_per_giorno.values())}
    if n < 2:
        return comune
    media = statistics.fmean(medie)
    ds = statistics.stdev(medie)
    se = ds / math.sqrt(n)
    return {
        **comune,
        "media_bp": media * 10_000,
        "t": media / se if se else None,
        "ds_giornaliera_bp": ds * 10_000,
        "effetto_rilevabile_a_t3_bp": SOGLIA_T * se * 10_000,
        "giornate_positive": sum(1 for media_giornaliera in medie if media_giornaliera > 0),
    }


def verdetto(statistica: dict[str, Any]) -> dict[str, Any]:
    """Applica l'ordine pre-registrato: insufficienza prima di PASS o FAIL."""
    n = statistica.get("n_giornate", 0)
    effetto_rilevabile = statistica.get("effetto_rilevabile_a_t3_bp")
    base = {
        "n_giornate": n,
        "n_eventi": statistica.get("n_eventi", 0),
        "n_richiesto": GIORNATE_RICHIESTE,
        "soglia_t": SOGLIA_T,
        "effetto_rilevabile_a_t3_bp": effetto_rilevabile,
    }
    if n < GIORNATE_RICHIESTE:
        return {**base, "esito": "INSUFFICIENT_N", "effetto_osservato_bp": None, "t": None}

    effetto = statistica.get("media_bp")
    t_stat = statistica.get("t")
    if (
        effetto is None or t_stat is None or effetto_rilevabile is None
        or abs(effetto) < effetto_rilevabile or abs(t_stat) < SOGLIA_T
    ):
        esito = "INSUFFICIENT_N"
    elif effetto > 0 and t_stat >= SOGLIA_T:
        esito = "PASS"
    else:
        esito = "FAIL"
    return {**base, "esito": esito, "effetto_osservato_bp": effetto, "t": t_stat}


def misura(conn, ora: datetime | None = None, verbose: bool = True) -> dict[str, Any]:
    """Costruisce i due outcome su tutte le sedute completamente fuori embargo."""
    taglio = taglio_embargo(ora)
    segnali = carica_segnali_fuori_orario(conn)
    if not segnali:
        raise MisuraAbortita("popolazione fuori orario vuota")
    primo = min(s["published_at"] for s in segnali)
    ultimo = max(s["published_at"] for s in segnali)
    sedute = carica_calendario(
        primo.astimezone(ET).date() - timedelta(days=10),
        ultimo.astimezone(ET).date() + timedelta(days=10),
    )
    osservazioni, scarti = costruisci_popolazione(segnali, sedute, taglio)
    if not osservazioni:
        raise MisuraAbortita("nessuna osservazione dopo il troncamento dell'embargo")

    per_data: dict[date, list[dict]] = defaultdict(list)
    for osservazione in osservazioni:
        per_data[osservazione["seduta"]["data"]].append(osservazione)
    indice_sedute = {s["data"]: i for i, s in enumerate(sedute)}
    def precedente(giorno: date) -> date | None:
        indice = indice_sedute.get(giorno)
        return sedute[indice - 1]["data"] if indice is not None and indice > 0 else None

    barre = scarica_barre_giornaliere(
        _client_dati(),
        sorted({o["symbol"] for o in osservazioni} | {BENCHMARK}),
        min(per_data) - timedelta(days=10), max(per_data) + timedelta(days=2),
    )
    gap: dict[date, list[float]] = defaultdict(list)
    intraday: dict[date, list[float]] = defaultdict(list)
    dopo_apertura = 0
    for giorno, gruppo in sorted(per_data.items()):
        giorno_prec = precedente(giorno)
        if giorno_prec is None:
            raise MisuraAbortita(f"seduta precedente assente per {giorno}")
        spy = barre.get(BENCHMARK, {})
        if giorno not in spy or giorno_prec not in spy:
            raise MisuraAbortita(f"benchmark {BENCHMARK} incompleto per la seduta {giorno}")
        open_spy, close_prec_spy = spy[giorno]["open"], spy[giorno_prec]["close"]
        if open_spy <= 0 or close_prec_spy <= 0:
            raise MisuraAbortita(f"benchmark {BENCHMARK} non valido per la seduta {giorno}")
        for osservazione in gruppo:
            simbolo = osservazione["symbol"]
            dati = barre.get(simbolo, {})
            if giorno not in dati or giorno_prec not in dati:
                raise MisuraAbortita(f"barre incomplete per {simbolo} nella seduta {giorno}")
            apertura, chiusura = dati[giorno]["open"], dati[giorno]["close"]
            close_prec = dati[giorno_prec]["close"]
            if min(apertura, chiusura, close_prec) <= 0:
                raise MisuraAbortita(f"barre non valide per {simbolo} nella seduta {giorno}")
            segno = 1.0 if osservazione["score"] > 0 else -1.0
            gap[giorno].append(segno * (
                (apertura - close_prec) / close_prec - (open_spy - close_prec_spy) / close_prec_spy
            ))
            intraday[giorno].append(segno * (
                (chiusura - apertura) / apertura - (spy[giorno]["close"] - open_spy) / open_spy
            ))
            dopo_apertura += osservazione["generated_at"] > osservazione["seduta"]["apertura"]
        if verbose:
            print(f"  {giorno}: {len(gruppo)} osservazioni", flush=True)

    return {
        "popolazione": {
            "segnali_fuori_orario": len(segnali),
            "osservazioni_simbolo_seduta": len(osservazioni),
            "simboli": len({o["symbol"] for o in osservazioni}),
            "sedute": len(per_data), "da": primo.isoformat(), "a": ultimo.isoformat(),
            "taglio_embargo": taglio.isoformat(), **scarti,
            "quota_scorati_dopo_apertura": dopo_apertura / len(osservazioni),
        },
        "gap_eccesso": media_t(gap),
        "intraday_eccesso": media_t(intraday),
    }


def artefatto(risultato: dict[str, Any]) -> dict[str, Any]:
    """Rende l'artefatto senza svelare alcun effetto prima della soglia fissata."""
    primario = verdetto(risultato["gap_eccesso"])
    fuori = {
        "prereg": "docs/evidence/PREREGISTRAZIONE_GAP_OFFHOURS_2026-09-16.md",
        "popolazione": risultato["popolazione"],
        "primario_gap_eccesso": primario,
    }
    if primario["esito"] != "INSUFFICIENT_N" or primario["n_giornate"] >= GIORNATE_RICHIESTE:
        fuori["secondario_intraday_eccesso"] = verdetto(risultato["intraday_eccesso"])
    return fuori


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="docs/evidence/gap_offhours_606.json")
    ap.add_argument("--silenzioso", action="store_true")
    args = ap.parse_args()

    import psycopg2
    from dotenv import load_dotenv

    load_dotenv(str(Path(__file__).resolve().parent.parent / ".env"))
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    try:
        risultato = artefatto(misura(conn, verbose=not args.silenzioso))
    finally:
        conn.close()
    risultato["generato_il"] = datetime.now(timezone.utc).isoformat()
    Path(args.out).write_text(json.dumps(risultato, indent=2, default=str), encoding="utf-8")
    print(json.dumps(risultato["primario_gap_eccesso"], indent=2))
    print(f"\nscritto: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
