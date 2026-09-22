#!/usr/bin/env python3
"""Cancello di riproducibilità del replay di portafoglio sulle uscite — #614, Fase 2.

Pre-registrazione: docs/evidence/PREREGISTRAZIONE_DISEGNO_CONTROFATTUALE_USCITE_2026-09-16.md
§4: con la regola invariata il replay deve riprodurre la storia realmente accaduta
entro ±2% sull'equity terminale della finestra, e la differenza va spiegata.

Cosa fa: scarica fill reali (ordini Alpaca), equity giornaliera del broker (portfolio
history), barre RAW e posizioni correnti; ricostruisce lo stato a inizio finestra;
rigioca i fill sulla contabilità di ``src/backtest/engine/portfolio.py`` e confronta
l'equity terminale con quella del broker. Nessun ramo controfattuale viene eseguito:
quelli richiedono la riga in OBSERVATION_CHARTER.md di cui alla DoD 5 della issue.

Sola lettura: nessuna scrittura su DB o Redis; l'unico output è l'artefatto JSON.

Uso (dall'host, con le chiavi del .env del checkout principale):
    export $(grep -E '^(ALPACA_API_KEY|ALPACA_SECRET_KEY|ALPACA_BASE_URL)=' ../.env)
    ../../.venv/bin/python scripts/replay_gate_614.py \
        --start 2026-08-03 --end 2026-09-21 \
        --output docs/research/2026-09-22-gate-riproducibilita-uscite.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.backtest.engine.exit_replay import (
    BrokerFill,
    equity_di_seduta,
    evaluate_gate,
    initial_cash,
    reconstruct_start_quantities,
    replay,
)
from src.backtest.engine.types import OrderSide


# ---------------------------------------------------------------------------
# Funzioni pure (testate in tests/scripts/test_replay_gate_614.py)
# ---------------------------------------------------------------------------


def fills_da_ordini(ordini: list[dict[str, Any]]) -> list[BrokerFill]:
    """Ordini broker -> fill. Contano anche i parzialmente riempiti poi annullati:
    un fill parziale ha mosso il cash comunque."""
    fills: list[BrokerFill] = []
    for o in ordini:
        qty = float(o.get("filled_qty") or 0)
        prezzo = o.get("filled_avg_price")
        if qty <= 0 or prezzo is None:
            continue
        fills.append(
            BrokerFill(
                timestamp=datetime.fromisoformat(o["filled_at"].replace("Z", "+00:00")),
                symbol=o["symbol"],
                side=OrderSide(o["side"].upper()),
                quantity=qty,
                fill_price=float(prezzo),
            )
        )
    return sorted(fills, key=lambda f: f.timestamp)


def session_closes_da_calendario(calendario: list[dict[str, Any]]) -> dict[date, datetime]:
    """Righe del calendario Alpaca -> campana di chiusura UTC per seduta."""
    chiuse: dict[date, datetime] = {}
    for riga in calendario:
        giorno = date.fromisoformat(riga["date"])
        hhmm = riga["session_close"].zfill(4)
        chiuse[giorno] = datetime(
            giorno.year, giorno.month, giorno.day, int(hhmm[:2]), int(hhmm[2:]),
            tzinfo=timezone.utc,
        )
    return chiuse


def closes_da_barre(barre_df: Any) -> dict[date, dict[str, float]]:
    """Barre giornaliere multi-simbolo -> {giorno: {simbolo: close}}."""
    closes: dict[date, dict[str, float]] = {}
    for (simbolo, ts), riga in barre_df["close"].items():
        giorno = ts.date() if hasattr(ts, "date") else ts
        closes.setdefault(giorno, {})[simbolo] = float(riga)
    return closes


def seduta_precedente(giorno: date, sedute: list[date]) -> date:
    """L'ultima seduta utile strettamente prima di ``giorno``."""
    precedenti = [g for g in sedute if g < giorno]
    if not precedenti:
        raise ValueError(f"nessuna seduta prima di {giorno}")
    return precedenti[-1]


# ---------------------------------------------------------------------------
# I/O broker
# ---------------------------------------------------------------------------


def _client_trading() -> Any:
    from alpaca.trading.client import TradingClient

    return TradingClient(
        os.environ["ALPACA_API_KEY"], os.environ["ALPACA_SECRET_KEY"], raw_data=True
    )


def _scarica_ordini(tc: Any, dopo: datetime, fino: datetime) -> list[dict[str, Any]]:
    """Tutti gli ordini chiusi con fill, paginando su ``after``."""
    ordini: list[dict[str, Any]] = []
    after = dopo.strftime("%Y-%m-%dT%H:%M:%SZ")
    while True:
        pagina = tc.get(
            "/orders",
            data={
                "status": "closed",
                "after": after,
                "until": fino.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "limit": 500,
                "direction": "asc",
            },
        )
        if not pagina:
            break
        ordini.extend(pagina)
        if len(pagina) < 500:
            break
        after = pagina[-1]["submitted_at"]
    # ``after`` potrebbe essere inclusivo: deduplica per id ordine
    univoci: dict[str, dict[str, Any]] = {o["id"]: o for o in ordini}
    return list(univoci.values())


def _scarica_ph(tc: Any, inizio: date, fine: date) -> dict[str, Any]:
    from alpaca.trading.requests import GetPortfolioHistoryRequest

    return tc.get_portfolio_history(
        GetPortfolioHistoryRequest(
            start=datetime(inizio.year, inizio.month, inizio.day, tzinfo=timezone.utc),
            end=datetime(fine.year, fine.month, fine.day, tzinfo=timezone.utc) + timedelta(days=3),
            timeframe="1D",
        )
    )


def _scarica_barre(simboli: list[str], inizio: date, fine: date) -> Any:
    from alpaca.data.enums import Adjustment
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame

    client = StockHistoricalDataClient(
        api_key=os.environ["ALPACA_API_KEY"], secret_key=os.environ["ALPACA_SECRET_KEY"]
    )
    richieste = StockBarsRequest(
        symbol_or_symbols=sorted(set(simboli)),
        timeframe=TimeFrame.Day,
        start=datetime(inizio.year, inizio.month, inizio.day, tzinfo=timezone.utc),
        end=datetime(fine.year, fine.month, fine.day, tzinfo=timezone.utc) + timedelta(days=1),
        # RAW: il broker marca l'equity ai prezzi come negoziati, non aggiustati
        adjustment=Adjustment.RAW,
    )
    return client.get_stock_bars(richieste).df


def _scarica_dividendi(tc: Any, simboli: list[str], inizio: date, fine: date) -> list[dict[str, Any]]:
    """Annunci di dividendo sui titoli toccati dalla finestra (diagnostica)."""
    from alpaca.trading.enums import CorporateAnnouncementType
    from alpaca.trading.requests import GetCorporateAnnouncementsRequest

    richiesta = GetCorporateAnnouncementsRequest(
        ca_types=[CorporateAnnouncementType.DIVIDEND],
        since=datetime(inizio.year, inizio.month, inizio.day, tzinfo=timezone.utc),
        until=datetime(fine.year, fine.month, fine.day, tzinfo=timezone.utc),
    )
    annunci = tc.get_corporate_announcements(richiesta)
    lista = annunci if isinstance(annunci, list) else list(annunci)
    return [a for a in lista if getattr(a, "symbol", None) in set(simboli)]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="Cancello di riproducibilità uscite #614")
    parser.add_argument("--start", required=True, help="Prima seduta della finestra (YYYY-MM-DD)")
    parser.add_argument("--end", required=True, help="Ultima seduta COMPLETA della finestra")
    parser.add_argument("--output", required=True, help="Percorso dell'artefatto JSON")
    parser.add_argument("--tolleranza-pct", type=float, default=2.0, help="Tolleranza %% (default 2, pre-registrata)")
    args = parser.parse_args()

    inizio = date.fromisoformat(args.start)
    fine = date.fromisoformat(args.end)

    tc = _client_trading()

    # calendario con margine: serve la seduta precedente a --start come ancoraggio
    calendario = tc.get(
        "/calendar",
        data={
            "start": (inizio - timedelta(days=10)).isoformat(),
            "end": (fine + timedelta(days=3)).isoformat(),
        },
    )
    session_closes = session_closes_da_calendario(list(calendario))
    sedute = sorted(session_closes)
    if inizio not in session_closes or fine not in session_closes:
        raise SystemExit(f"--start/--end devono essere sedute: {inizio}, {fine}")

    ancoraggio = seduta_precedente(inizio, sedute)

    # fill: da dopo la campana dell'ancoraggio fino alla fine finestra (per il replay)
    # e fino a ORA (per ricostruire le quantita' iniziali dalle posizioni correnti).
    # Margine di una settimana su ``after`` (filtra su submitted_at): un ordine
    # sottomesso prima dell'ancoraggio ma riempito dopo non deve sfuggire.
    ordini = _scarica_ordini(
        tc, dopo=session_closes[ancoraggio] - timedelta(days=7), fino=datetime.now(timezone.utc)
    )
    fills = fills_da_ordini(ordini)
    fills_finestra = [f for f in fills if session_closes[ancoraggio] < f.timestamp <= session_closes[fine]]

    posizioni_correnti = {
        p["symbol"]: float(p["qty"]) for p in tc.get_all_positions() if float(p["qty"]) != 0
    }
    qty_inizio = reconstruct_start_quantities(
        posizioni_correnti, fills, after=session_closes[ancoraggio]
    )

    simboli = sorted(
        set(qty_inizio) | set(posizioni_correnti) | {f.symbol for f in fills_dopo_ancoraggio}
    )
    barre = _scarica_barre(simboli, inizio=ancoraggio, fine=fine)
    closes = closes_da_barre(barre)
    if ancoraggio not in closes:
        raise SystemExit(f"barre mancanti per la seduta di ancoraggio {ancoraggio}")

    ph = _scarica_ph(tc, inizio=ancoraggio, fine=fine)
    equity_inizio_broker = equity_di_seduta(ph, ancoraggio)
    equity_fine_broker = equity_di_seduta(ph, fine)

    cash_inizio = initial_cash(equity_inizio_broker, qty_inizio, closes[ancoraggio])

    sedute_finestra = [g for g in sedute if ancoraggio < g <= fine]
    serie, portafoglio = replay(
        start_qty=qty_inizio,
        start_cash=cash_inizio,
        start_closes=closes[ancoraggio],
        fills=fills_finestra,
        closes_by_day={g: closes.get(g, {}) for g in sedute_finestra},
        session_closes={g: session_closes[g] for g in sedute_finestra},
    )

    esito = evaluate_gate(
        replay_equity=serie[-1].equity,
        broker_equity=equity_fine_broker,
        tolleranza_pct=args.tolleranza_pct,
    )

    # --- spiegazione della differenza, non solo dichiarazione ---
    valore_posizioni_mio_mark = sum(
        p.quantity * closes.get(fine, {}).get(p.symbol, p.avg_cost)
        for p in portafoglio.all_positions()
    )
    residuo_marcazione = equity_fine_broker - portafoglio.cash - valore_posizioni_mio_mark

    dividendi = _scarica_dividendi(tc, simboli, inizio, fine)

    giornaliero_broker = []
    for g in sedute_finestra:
        try:
            giornaliero_broker.append({"giorno": g.isoformat(), "equity": equity_di_seduta(ph, g)})
        except ValueError:
            pass  # seduta scoperta dalla ph: segnalata sotto

    dopo_campana = [f for f in fills_finestra if f.timestamp.time() > session_closes[f.timestamp.date()].time()]

    artefatto = {
        "issue": 614,
        "fase": "cancello-di-riproducibilita",
        "pre_registrazione": "docs/evidence/PREREGISTRAZIONE_DISEGNO_CONTROFATTUALE_USCITE_2026-09-16.md#4",
        "finestra": {"sedute": [inizio.isoformat(), fine.isoformat()], "ancoraggio": ancoraggio.isoformat()},
        "tolleranza_pct": args.tolleranza_pct,
        "conteggi": {
            "fill_applicati": len(fills_finestra),
            "fill_buy": sum(1 for f in fills_finestra if f.side == OrderSide.BUY),
            "fill_sell": sum(1 for f in fills_finestra if f.side == OrderSide.SELL),
            "fill_dopo_campana": len(dopo_campana),
            "posizioni_iniziali": len(qty_inizio),
            "posizioni_finali": len(portafoglio.all_positions()),
        },
        "equity": {
            "broker_inizio": equity_inizio_broker,
            "broker_fine": equity_fine_broker,
            "replay_fine": serie[-1].equity,
            "cash_inizio": cash_inizio,
            "cash_fine": portafoglio.cash,
            "valore_posizioni_mio_mark": valore_posizioni_mio_mark,
        },
        "gate": {
            "delta": esito.delta,
            "delta_pct": esito.delta_pct,
            "superato": esito.superato,
        },
        "spiegazione": {
            "residuo_marcazione_broker": residuo_marcazione,
            "residuo_marcazione_pct_equity": (
                residuo_marcazione / equity_fine_broker * 100 if equity_fine_broker else None
            ),
            "dividendi_annunciati_su_simboli_finestra": [
                {
                    "simbolo": getattr(a, "symbol", None),
                    "ex_date": str(getattr(a, "ex_date", None)),
                    "importo_per_azione": getattr(a, "cash_amount", None),
                }
                for a in dividendi
            ],
            "nota_dividendi": (
                "il paper Alpaca non accredita i dividendi in cash: se la finestra "
                "contiene ex-date su titoli detenuti, quel delta resta qui visibile"
            ),
        },
        "serie_replay": [
            {"giorno": r.giorno.isoformat(), "equity": r.equity, "cash": r.cash, "valore_posizioni": r.valore_posizioni}
            for r in serie
        ],
        "serie_broker": giornaliero_broker,
        "generato_il": datetime.now(timezone.utc).isoformat(),
    }

    uscita = Path(args.output)
    uscita.parent.mkdir(parents=True, exist_ok=True)
    with open(uscita, "w") as f:
        json.dump(artefatto, f, indent=2, ensure_ascii=False)

    print(f"Finestra: {inizio} .. {fine} (ancoraggio {ancoraggio}), {len(sedute_finestra)} sedute")
    print(f"Fill applicati: {len(fills_finestra)} "
          f"(buy {artefatto['conteggi']['fill_buy']} / sell {artefatto['conteggi']['fill_sell']}, "
          f"post-campana {len(dopo_campana)})")
    print(f"Equity broker:  inizio {equity_inizio_broker:,.2f}  fine {equity_fine_broker:,.2f}")
    print(f"Equity replay:  fine {serie[-1].equity:,.2f}")
    print(f"Delta: {esito.delta:+,.2f} ({esito.delta_pct:+.4f}%) "
          f"[tolleranza ±{args.tolleranza_pct}%] -> "
          f"{'SUPERATO' if esito.superato else 'FALLITO'}")
    print(f"Residuo di marcazione broker vs mio mark a fine finestra: {residuo_marcazione:+,.2f}")
    if dividendi:
        print(f"Dividendi annunciati su simboli della finestra: {len(dividendi)} (dettaglio nell'artefatto)")
    print(f"Artefatto: {uscita}")
    return 0 if esito.superato else 1


if __name__ == "__main__":
    raise SystemExit(main())
