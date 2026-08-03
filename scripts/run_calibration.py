#!/usr/bin/env python3
"""Esegue le calibrazioni C1-C3 del programma di backtest e scrive il risultato.

Orchestratore SOTTILE: fa l'I/O (Alpaca, disco) e delega ogni calcolo ai moduli
puri in `src/analysis/calibration/`. Nessuna formula vive qui.

Le tre calibrazioni, definite in docs/evidence/PREREGISTRAZIONE_BACKTEST_S1.md §4:

  C1  ordine di grandezza dell'effetto sulla gamba long, con intervallo
  C2  diluizione da universo ristretto + disponibilita' storica dei simboli
  C3  costo per rotazione, dai modelli gia' presenti in src/backtest/costs/

NON sono test: non c'e' un'ipotesi nulla da rifiutare. Producono una stima e il
suo intervallo. La pre-registrazione dichiara in anticipo che C1 NON sara'
significativo (servono 100+ mesi per t=3 con l'effetto atteso): il risultato
utile e' l'ampiezza dell'intervallo, non un verdetto.

Uso:
    set -a; source .env; set +a
    uv run python scripts/run_calibration.py --start 2015-01-01 --n-top 10
"""
from __future__ import annotations

import argparse
import json
import logging
from datetime import date, datetime, timezone
from pathlib import Path

import yaml

from src.analysis.calibration.momentum import (
    equal_weighted_return,
    momentum_scores,
    select_top,
    summarize_excess,
)
from src.backtest.data.alpaca_loader import AlpacaDailyLoader

log = logging.getLogger(__name__)

PROJECT_DIR = Path(__file__).resolve().parents[1]
OUT_DIR = PROJECT_DIR / "docs" / "evidence" / "calibration"
BENCH_SYMBOL = "SPY"  # solo come riferimento secondario e come calendario di borsa


def _watchlist() -> list[str]:
    with open(PROJECT_DIR / "config" / "trading.yaml") as f:
        return list(yaml.safe_load(f)["symbols"]["watchlist"])


def _build_position_index(bars: dict, calendar_symbol: str) -> tuple[list[date], dict]:
    """Traduce date reali in posizioni intere sul calendario di borsa.

    I moduli puri ragionano su posizioni ("252 giorni di BORSA"), non su date:
    sottrarre giorni di calendario darebbe una finestra diversa e sbagliata. La
    traduzione avviene qui perche' l'orchestratore e' l'unico che sa quali giorni
    la borsa fosse aperta — e lo sa guardando un simbolo che ha scambiato sempre.
    """
    if calendar_symbol not in bars:
        raise SystemExit(
            f"Manca {calendar_symbol}, che serve come calendario di borsa. "
            "Senza, le posizioni non sono confrontabili fra simboli."
        )
    dates = [d.date() for d in bars[calendar_symbol].index]

    # Il calendario DEVE essere denso: le posizioni hanno senso solo se ogni
    # posizione e' un giorno di borsa realmente consecutivo. Con un feed lacunoso
    # (Alpaca IEX non ha il 2019 e ha 111 barre nel 2020) una finestra di "242
    # posizioni" attraversa i buchi e misura molti piu' mesi di calendario di
    # quanti dovrebbe: il segnale 12-2 diventerebbe un 32-2 senza che nulla lo
    # segnali. Meglio rifiutare l'anno che calcolare un numero sbagliato.
    per_anno: dict[int, int] = {}
    for d in dates:
        per_anno[d.year] = per_anno.get(d.year, 0) + 1
    anni_pieni = [a for a, n in per_anno.items() if n >= 240]
    if not anni_pieni:
        raise SystemExit(
            f"Nessun anno con >=240 barre su {calendar_symbol}: calendario troppo "
            f"lacunoso per calcolare finestre posizionali. Conteggi: {per_anno}"
        )
    primo_anno_buono = min(anni_pieni)
    scartate = [d for d in dates if d.year < primo_anno_buono]
    if scartate:
        log.warning(
            "Calendario lacunoso prima del %d (conteggi per anno: %s) — scarto %d "
            "barre iniziali. Le finestre posizionali sarebbero state sbagliate.",
            primo_anno_buono,
            {a: n for a, n in sorted(per_anno.items()) if a < primo_anno_buono},
            len(scartate),
        )
        dates = [d for d in dates if d.year >= primo_anno_buono]

    pos_of = {d: i for i, d in enumerate(dates)}

    closes: dict[str, dict[int, float]] = {}
    for sym, df in bars.items():
        serie: dict[int, float] = {}
        for ts, row in df.iterrows():
            i = pos_of.get(ts.date())
            if i is not None:  # giorni fuori dal calendario di riferimento: scartati
                serie[i] = float(row["Close"])
        closes[sym] = serie
    return dates, closes


def _month_end_positions(dates: list[date]) -> list[int]:
    """Ultima posizione di borsa di ogni mese."""
    out: list[int] = []
    for i, d in enumerate(dates[:-1]):
        if (d.year, d.month) != (dates[i + 1].year, dates[i + 1].month):
            out.append(i)
    return out


def run_c1(closes: dict, dates: list[date], n_top: int, lookback: int, skip: int) -> dict:
    """Effetto della gamba long: top-N per momentum contro l'equipesato dell'universo.

    Ribilanciamento MENSILE, non il ciclo a 15 minuti di S1: C1 deve misurare
    quanto vale l'effetto DOCUMENTATO sul nostro paniere, e l'unico modo di
    confrontarlo con la letteratura e' usarne la cadenza. Il disallineamento con
    l'holding reale di S1 non e' un difetto di C1 — e' l'oggetto dell'ipotesi F2.
    """
    mesi = _month_end_positions(dates)
    eccessi: list[float] = []
    dettaglio: list[dict] = []

    for a, b in zip(mesi, mesi[1:]):
        scores = momentum_scores(closes, idx=a, lookback=lookback, skip=skip)
        if not scores:
            continue
        top = select_top(scores, n_top=n_top)
        r_top = equal_weighted_return(top, closes, a, b)
        # Benchmark: equipesato dei soli simboli ELEGGIBILI a quella data, non SPY.
        # Confrontare i vincitori del paniere contro SPY mescolerebbe la selezione
        # per momentum con il fatto che il paniere non e' il mercato.
        r_uni = equal_weighted_return(tuple(sorted(scores)), closes, a, b)
        if r_top is None or r_uni is None:
            continue
        eccessi.append(r_top - r_uni)
        dettaglio.append({
            "fine_mese": dates[a].isoformat(),
            "n_eleggibili": len(scores),
            "r_top": r_top,
            "r_universo": r_uni,
            "eccesso": r_top - r_uni,
        })

    return {"sintesi": summarize_excess(eccessi), "mensili": dettaglio}


def run_c2(closes: dict, dates: list[date], lookback: int, skip: int) -> dict:
    """Quanti simboli erano effettivamente eleggibili, anno per anno.

    E' la misura del bias di sopravvivenza che la pre-registrazione chiede di
    MISURARE invece di assumere: se dei 96 di oggi solo N avevano dati nel 2015,
    un backtest su tutti e 96 sta usando informazione che allora non avevamo.
    """
    per_anno: dict[int, list[int]] = {}
    for i in _month_end_positions(dates):
        scores = momentum_scores(closes, idx=i, lookback=lookback, skip=skip)
        per_anno.setdefault(dates[i].year, []).append(len(scores))

    return {
        "totale_watchlist": len(closes),
        "eleggibili_per_anno": {
            str(anno): {"min": min(v), "max": max(v), "medio": sum(v) / len(v)}
            for anno, v in sorted(per_anno.items())
        },
    }


def run_c3(symbols: list[str], n_top: int) -> dict:
    """Costo per rotazione, dai modelli gia' presenti in src/backtest/costs/.

    Non inventa una stima: se quei modelli sono inadeguati, il risultato onesto e'
    "i modelli esistenti dicono X". Scriverne un secondo accanto a uno esistente
    creerebbe due verita'.
    """
    from src.backtest.costs.spread_tiers import SpreadTierLookup

    lookup = SpreadTierLookup.from_config(PROJECT_DIR / "config" / "cost_model.yaml")
    spread = {s: lookup.get_spread_bps(s) for s in symbols}
    medio = sum(spread.values()) / len(spread) if spread else None

    # Una rotazione completa del paniere = vendere n_top e comprarne n_top, e ogni
    # lato paga mezzo spread. Andata e ritorno = 1 spread pieno per posizione.
    return {
        "spread_bps_medio_watchlist": medio,
        "spread_bps_per_simbolo": spread,
        "costo_bps_per_rotazione_completa": medio,
        "nota": (
            "Andata+ritorno paga circa uno spread pieno per posizione ruotata. "
            "A ~18 rotazioni/anno (holding ~14 giorni) il drag annuo e' circa "
            "18 x spread_medio_bps, contro ~2 rotazioni per una 6/6. E' il numero "
            "che rende interpretabile l'ipotesi F2."
        ),
    }


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--start", default="2015-01-01")
    ap.add_argument("--end", default=date.today().isoformat())
    ap.add_argument("--n-top", type=int, default=10, help="ampiezza del paniere long-only")
    ap.add_argument("--lookback", type=int, default=242, help="giorni di borsa (12-2)")
    ap.add_argument("--skip", type=int, default=21, help="giorni di borsa saltati (12-2)")
    args = ap.parse_args()

    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)
    symbols = _watchlist()
    if BENCH_SYMBOL not in symbols:
        symbols = [*symbols, BENCH_SYMBOL]

    log.info("Scarico %d simboli da Alpaca (%s -> %s)", len(symbols), start, end)
    bars = AlpacaDailyLoader().download_many(symbols, start, end)
    log.info("Ottenuti %d/%d simboli", len(bars), len(symbols))

    dates, closes = _build_position_index(bars, BENCH_SYMBOL)
    log.info("Calendario: %d giorni di borsa, %s -> %s", len(dates), dates[0], dates[-1])

    risultato = {
        "generato_il": datetime.now(timezone.utc).isoformat(),
        "parametri": {
            "start": args.start, "end": args.end, "n_top": args.n_top,
            "lookback": args.lookback, "skip": args.skip,
            "benchmark": "equal-weight dell'universo eleggibile",
            "fonte_prezzi": "Alpaca IEX, adjustment=all",
        },
        "copertura": {
            "simboli_richiesti": len(symbols),
            "simboli_ottenuti": len(bars),
            "primo_giorno": dates[0].isoformat(),
            "ultimo_giorno": dates[-1].isoformat(),
        },
        "C1": run_c1(closes, dates, args.n_top, args.lookback, args.skip),
        "C2": run_c2(closes, dates, args.lookback, args.skip),
        "C3": run_c3([s for s in symbols if s != BENCH_SYMBOL], args.n_top),
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"calibration_{date.today().isoformat()}.json"
    tmp = out.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(risultato, indent=2, ensure_ascii=False))
    tmp.replace(out)  # scrittura atomica: mai un file mezzo scritto

    s = risultato["C1"]["sintesi"]
    print(f"\nScritto: {out}")
    print(f"\nC1 — mesi: {s['n']}")
    if s["media"] is not None:
        print(f"   eccesso medio mensile: {s['media']*100:+.3f}%")
    if s["t_stat"] is not None:
        print(f"   t = {s['t_stat']:.2f}   |t|>=3.0: {s['supera_soglia_3']}")
        print(f"   IC 95%: [{s['ci_low']*100:+.3f}%, {s['ci_high']*100:+.3f}%]")
        if not s["supera_soglia_3"]:
            print("   -> ESITO: 'non dimostrata su questo campione', NON 'falsa'.")
            print("      Con l'effetto atteso servono 100+ mesi per t=3: l'assenza")
            print("      di significativita' qui e' attesa per costruzione.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
