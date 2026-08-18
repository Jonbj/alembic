#!/usr/bin/env python3
"""Phase 0 discovery — sonda gli endpoint dell'earnings chain (read-only).

Nessuna scrittura, nessun DB, nessun worker, nessuna taratura: emette solo una
matrice di codici HTTP + uno snippet di schema per ogni endpoint rilevante, così
il report di discovery (docs/superpowers/plans/2026-07-12-vettore-a-earnings-chain-brief.md)
è verificabile e re-eseguibile. Le chiavi API si leggono dall'ambiente come gli
altri script (set -a; source .env; set +a).

Cosa prova:
  - FMP: earnings-calendar (con/senza range), earnings (per-symbol), analyst-estimates
    (annual/quarter), earning-call-transcript, profile/quote (sanity del piano).
  - Finnhub: calendar/earnings, stock/earnings, stock/recommendation,
    stock/earnings-estimate, company-news (sanity).
  - Alpha Vantage: EARNINGS_CALL_TRANSCRIPT (fonte transcript del POC S7).

Run: set -a; source .env; set +a; .venv/bin/python scripts/probe_earnings_chain_phase0.py
"""
from __future__ import annotations

import json
import os
import sys

import httpx

FMP = "https://financialmodelingprep.com"
FH = "https://finnhub.io/api/v1"
AV = "https://www.alphavantage.co/query"

# 5 simboli di watchlist rappresentativi (mega-cap tech + finanza + pharma).
SYMBOLS = ["AAPL", "MSFT", "NVDA", "JPM", "PFE"]


def _snippet(payload: object, limit: int = 320) -> str:
    """Serializza il payload in uno snippet compatto su una riga."""
    if not payload:
        return "(body vuoto)"
    try:
        s = json.dumps(payload, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(payload)[:limit]
    return (s[:limit] + "…") if len(s) > limit else s


def _probe(name: str, url: str, *, params: dict | None = None) -> None:
    """GET read-only, stampa [HTTP] name :: snippet."""
    try:
        r = httpx.get(url, params=params, timeout=20.0)
    except httpx.HTTPError as exc:
        print(f"[ERR] {name} :: {exc}")
        return
    body: object = r.text
    # prova a parsare come JSON per uno snippet leggibile
    try:
        body = r.json()
    except (ValueError, json.JSONDecodeError):
        body = r.text.strip()
    code = r.status_code
    # per liste lunghe, mostra solo il primo elemento + il conteggio
    if isinstance(body, list):
        first = body[0] if body else "(lista vuota)"
        print(f"[{code}] {name} :: {len(body)} record :: {_snippet(first)}")
    else:
        print(f"[{code}] {name} :: {_snippet(body)}")


def main() -> None:
    fmp = os.environ.get("FMP_API_KEY", "")
    fh = os.environ.get("FINNHUB_API_KEY", "")
    av = os.environ.get("ALPHAVANTAGE_API_KEY", "")

    print(f"# Earnings chain — Phase 0 endpoint probe (symboli={SYMBOLS})\n")
    print(f"FMP_API_KEY: {'presente' if fmp else 'ASSENTE'}")
    print(f"FINNHUB_API_KEY: {'presente' if fh else 'ASSENTE'}")
    print(f"ALPHAVANTAGE_API_KEY: {'presente' if av else 'ASSENTE'}\n")

    # Endpoint globali (non per-symbol): una sola chiamata per categoria
    print("=== FMP (financialmodelingprep.com) — endpoint globali ===")
    if fmp:
        _probe("stable/earnings-calendar (no range)", f"{FMP}/stable/earnings-calendar",
               params={"apikey": fmp})
        _probe("stable/earnings-calendar (range=premium)", f"{FMP}/stable/earnings-calendar",
               params={"from": "2024-01-01", "to": "2026-08-18", "apikey": fmp})
        print("\n  --- v3/earning-calendar (legacy, per-symbol sweep) ---")
        for sym in SYMBOLS:
            _probe(f"v3/earning-calendar/{sym}", f"{FMP}/api/v3/earning-calendar/{sym}",
                   params={"apikey": fmp})
    else:
        print("  (saltato: FMP_API_KEY non in env)")

    # Endpoint per-symbol: una riga per simbolo × provider, su tutti i 5 della watchlist
    print("\n=== FMP — per-symbol (uno per simbolo watchlist) ===")
    if fmp:
        for sym in SYMBOLS:
            _probe(f"stable/earnings {sym}", f"{FMP}/stable/earnings",
                   params={"symbol": sym, "apikey": fmp})
            _probe(f"stable/analyst-estimates annual {sym}", f"{FMP}/stable/analyst-estimates",
                   params={"symbol": sym, "period": "annual", "apikey": fmp})
            _probe(f"stable/analyst-estimates quarter {sym}", f"{FMP}/stable/analyst-estimates",
                   params={"symbol": sym, "period": "quarter", "apikey": fmp})
            _probe(f"stable/earning-call-transcript {sym}", f"{FMP}/stable/earning-call-transcript",
                   params={"symbol": sym, "apikey": fmp})
            _probe(f"stable/profile {sym} (sanity piano)", f"{FMP}/stable/profile",
                   params={"symbol": sym, "apikey": fmp})
    else:
        print("  (saltato: FMP_API_KEY non in env)")

    print("\n=== Finnhub (finnhub.io) — globali ===")
    if fh:
        _probe("calendar/earnings (range)", f"{FH}/calendar/earnings",
               params={"from": "2026-08-18", "to": "2026-08-25", "token": fh})
    else:
        print("  (saltato: FINNHUB_API_KEY non in env)")

    print("\n=== Finnhub — per-symbol (uno per simbolo watchlist) ===")
    if fh:
        for sym in SYMBOLS:
            _probe(f"stock/earnings {sym}", f"{FH}/stock/earnings",
                   params={"symbol": sym, "token": fh})
            _probe(f"stock/recommendation {sym}", f"{FH}/stock/recommendation",
                   params={"symbol": sym, "token": fh})
            _probe(f"stock/earnings-estimate {sym}", f"{FH}/stock/earnings-estimate",
                   params={"symbol": sym, "freq": "quarterly", "token": fh})
            _probe(f"company-news {sym} (sanity wired)", f"{FH}/company-news",
                   params={"symbol": sym, "from": "2026-08-11", "to": "2026-08-18", "token": fh})
    else:
        print("  (saltato: FINNHUB_API_KEY non in env)")

    print("\n=== Alpha Vantage (alphavantage.co) — transcript (POC S7) ===")
    if av:
        # AV quota free tier = 25/day, già risicata in earnings season per la Phase 2.
        # La sonda verifica solo shape/contenuto del payload su 1 simbolo
        # (l'endpoint richiede fiscal quarter, non data singola): iterare 5 simboli
        # mangerebbe 5/25 della quota senza aggiungere informazione.
        _probe(f"EARNINGS_CALL_TRANSCRIPT {SYMBOLS[0]} (probe shape, no quarter — AV quota 25/day)",
               AV, params={"function": "EARNINGS_CALL_TRANSCRIPT",
                            "symbol": SYMBOLS[0], "apikey": av})
    else:
        print("  (saltato: ALPHAVANTAGE_API_KEY non in env)")

    print("\n# Legenda codici: 200=ok, 402=payment required (piano), "
          "403=legacy endpoint, 404=non trovato, 302=redirect (endpoint rinominato).")
    return None


if __name__ == "__main__":
    sys.exit(main())