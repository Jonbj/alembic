#!/usr/bin/env python3
"""Scoreboard del P&L economico della carta di osservazione (#278, M3).

Orchestratore SOTTILE: fa l'I/O (Alpaca, Postgres, ledger di mercato) e delega
OGNI calcolo ai moduli puri ``src/analysis/dossier/economic_pnl.py`` e
``src/analysis/dossier/scoreboard.py``. Nessuna formula vive qui.

Calcola deterministicamente il P&L economico di S1 / S4 / book sulla finestra di
osservazione (2026-08-03 -> 2026-09-28) secondo la definizione della carta, e lo
mostra nello scoreboard delle due domande di uscita pre-registrate: giorno N/40,
quota di giorni con NO_NEWS dominante, S4 vs +-200$, S1 vs SPY, segmenti
pre/post #185 e #191.

Sola lettura su Postgres, Alpaca e ``docs/evidence/market_daily.jsonl``. Non
tocca MAI findings.json ne' market_daily.jsonl in scrittura: quelli sono
append-only e scritti solo dalle sessioni col protocollo del ledger. L'output
va in ``docs/evidence/economic_pnl.json`` (strumentazione parallela, ammessa
dal freeze).

Uso:
    set -a; source .env; set +a
    uv run python scripts/economic_pnl_scoreboard.py
    uv run python scripts/economic_pnl_scoreboard.py --as-of 2026-08-12
"""
from __future__ import annotations

import argparse
import json
import logging
import os
from datetime import date, datetime, timedelta
from pathlib import Path

from src.analysis.dossier.economic_pnl import compute_economic_pnl
from src.analysis.dossier.scoreboard import compute_scoreboard

log = logging.getLogger(__name__)

PROJECT_DIR = Path(__file__).resolve().parents[1]
OUT_PATH = PROJECT_DIR / "docs" / "evidence" / "economic_pnl.json"
MARKET_DAILY = PROJECT_DIR / "docs" / "evidence" / "market_daily.jsonl"
INIZIO_OSSERVAZIONE = date(2026, 8, 3)


def _psql(query: str) -> list[list[str]]:
    """Query read-only su Postgres. Righe come liste di stringhe."""
    import subprocess
    res = subprocess.run(
        ["docker", "exec", "alembic-postgres-1", "psql", "-U", "trading", "-d",
         "trading", "-t", "-A", "-F", "|", "-c", query],
        capture_output=True, text=True,
    )
    if res.returncode != 0:
        raise SystemExit(f"Query fallita: {res.stderr.strip()[:300]}")
    return [r.split("|") for r in res.stdout.strip().split("\n") if r.strip()]


def _market_rows() -> list[dict]:
    """Righe del ledger di mercato (append-only, sola lettura)."""
    if not MARKET_DAILY.exists():
        return []
    return [json.loads(r) for r in MARKET_DAILY.read_text().splitlines() if r.strip()]


def _load_positions(as_of: date) -> list[dict]:
    """Posizioni attive in qualche punto della finestra [INIZIO_OSSERVAZIONE, as_of].

    Una posizione conta se e' entrata prima della fine e non e' uscita prima
    dell'inizio. L'attribuzione passa stop_strategy / signal_id ai moduli puri,
    che non applicano il fallback S1 arbitrario del dossier legacy.
    """
    rows = _psql(
        f"SELECT symbol, stop_strategy, signal_id::text, entry_price, "
        f"entry_time::date, exit_price, exit_time::date, qty "
        f"FROM trades WHERE entry_time < '{as_of}'::date + 1 "
        f"AND (exit_time IS NULL OR exit_time >= '{INIZIO_OSSERVAZIONE}') "
        f"ORDER BY entry_time;"
    )
    pos = []
    for r in rows:
        pos.append({
            "symbol": r[0],
            "stop_strategy": r[1] or None,
            "signal_id": int(r[2]) if r[2] not in (None, "") else None,
            "entry_price": float(r[3]) if r[3] not in (None, "") else None,
            "entry_date": date.fromisoformat(r[4]) if r[4] else None,
            "exit_price": float(r[5]) if r[5] not in (None, "") else None,
            "exit_date": date.fromisoformat(r[6]) if r[6] else None,
            "qty": float(r[7]) if r[7] not in (None, "") else None,
        })
    return pos


def _load_closes(symbols: list[str], window_start: date, as_of: date) -> dict:
    """Barre giornaliere SIP (adjustment=all) per i simboli delle posizioni.

    Parte da una settimana prima del window_start per garantire il close del
    primo giorno (mark_from delle posizioni pre-finestra). Restituisce
    {giorno: {simbolo: close}}.
    """
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame

    chiave, segreto = os.environ.get("ALPACA_API_KEY"), os.environ.get("ALPACA_SECRET_KEY")
    if not chiave or not segreto:
        raise SystemExit("ALPACA_API_KEY / ALPACA_SECRET_KEY mancanti (.env non caricato?)")
    if not symbols:
        return {}

    client = StockHistoricalDataClient(chiave, segreto)
    req = StockBarsRequest(
        symbol_or_symbols=sorted(symbols),
        timeframe=TimeFrame.Day,
        start=datetime.combine(window_start - timedelta(days=7), datetime.min.time()),
        end=datetime.combine(min(as_of + timedelta(days=1), date.today()), datetime.min.time()),
        feed="sip",
        adjustment="all",
    )
    df = client.get_stock_bars(req).df
    closes: dict[date, dict[str, float]] = {}
    if df is None or df.empty:
        return closes
    for sym in df.index.get_level_values(0).unique():
        for ts, row in df.loc[sym].iterrows():
            d = ts.date()
            closes.setdefault(d, {})[sym] = float(row["close"])
    return closes


def _jsonable(obj):
    """Converte ricorsivamente date (chiavi e valori) in stringhe ISO per JSON."""
    if isinstance(obj, dict):
        return {(_jsonable_k(k)): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, date):
        return obj.isoformat()
    return obj


def _jsonable_k(k):
    return k.isoformat() if isinstance(k, date) else k


def costruisci(as_of: date) -> dict:
    market_rows = _market_rows()
    # as_of di default = ultimo giorno osservato nel ledger; se richiesto oltre,
    # lo agganciamo all'ultimo giorno disponibile per coerenza col ledger.
    osservati = sorted(
        date.fromisoformat(r["data"]) for r in market_rows
        if date.fromisoformat(r["data"]) >= INIZIO_OSSERVAZIONE
    )
    if osservati and as_of > osservati[-1]:
        log.warning("as_of %s oltre l'ultimo giorno osservato (%s): uso quest'ultimo.",
                    as_of, osservati[-1])
        as_of = osservati[-1]
    if not osservati:
        raise SystemExit("Nessun giorno osservato nel ledger (market_daily.jsonl vuoto?).")

    trading_days = [d for d in osservati if d <= as_of]
    posizioni = _load_positions(as_of)
    simboli = sorted({p["symbol"] for p in posizioni if p["symbol"]})
    closes = _load_closes(simboli, INIZIO_OSSERVAZIONE, as_of)

    economic = compute_economic_pnl(posizioni, trading_days, INIZIO_OSSERVAZIONE, closes)
    scoreboard = compute_scoreboard(economic, market_rows, INIZIO_OSSERVAZIONE, as_of)

    return {
        "data": as_of.isoformat(),
        "generato_il": datetime.now().astimezone().isoformat(),
        "fonte_prezzi": "Alpaca SIP, adjustment=all",
        "fonte_ledger": "docs/evidence/market_daily.jsonl (sola lettura)",
        "finestra_inizio": INIZIO_OSSERVAZIONE.isoformat(),
        "definizione": (
            "P&L economico: mark dal close del primo giorno della finestra (o "
            "entry_price se ingresso successivo) al prezzo corrente (o exit_price "
            "se uscita anteriore), per qty. Somma su tutte le posizioni. "
            "Vedi docs/evidence/OBSERVATION_CHARTER.md 'Definizione: P&L economico'."
        ),
        "attribuzione": (
            "stop_strategy -> quella strategia; else signal_id -> S4; else "
            "CONTAMINAZIONE. Niente fallback S1 arbitrario (criterio #278)."
        ),
        "pnl_economico": {
            "cumulato": economic["cumulato"],
            "giornaliero": economic["giornaliero"],
            "capital_base": economic["capital_base"],
        },
        "scoreboard": scoreboard,
        "numerosita": economic["numerosita"],
        "esclusi": economic["esclusi"],
        "missingness": economic["missing"],
    }


def scrivi(payload: dict) -> Path:
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(_jsonable(payload), indent=2, ensure_ascii=False))
    tmp.replace(OUT_PATH)  # atomica
    return OUT_PATH


def _riepilogo(payload: dict) -> str:
    sb = payload["scoreboard"]
    g = sb["giorno"]
    nn = sb["no_news_dominant"]
    s4 = sb["s4_vs_200"]
    s1 = sb["s1_vs_spy"]
    book = sb["book"]
    cont = sb["contaminazione"]
    s185 = sb["segmenti"]["#185"]
    s191 = sb["segmenti"]["#191"]
    return (
        f"Giorno {g['n']}/{g['denominatore']} (as_of {sb['finestra']['as_of']})\n"
        f"  NO_NEWS dominante: {nn['numerator']}/{nn['denominator']} giorni "
        f"(soglia carta {nn['soglia_carta']:.0%})\n"
        f"  S4 economico: {s4['cumulato']:+.2f}$  vs +-{s4['soglia']:.0f}$ -> "
        f"{'DENTRO' if s4['within'] else 'FUORI'}\n"
        f"  S1 economico: {s1['s1_cumulato']:+.2f}$  | SPY {s1['spy_cum_return']:+.2%} "
        f"(benchmark {s1['spy_benchmark_usd']:+.2f}$ su base {s1['capital_base']:.0f}$) "
        f"-> delta {s1['delta_vs_spy']:+.2f}$\n"
        f"  Book economico: {book['cumulato']:+.2f}$  (contaminazione {cont['cumulato']:+.2f}$ "
        f"su {cont['numerosita']} pos.)\n"
        f"  #185 S1: pre {s185['pre']['delta_cum']:+.2f}$ / post {s185['post']['delta_cum']:+.2f}$\n"
        f"  #191 S4: pre {s191['pre']['delta_cum']:+.2f}$ / post {s191['post']['delta_cum']:+.2f}$\n"
        f"  Numerosita: {payload['numerosita']}  | esclusi: {payload['esclusi']}"
    )


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--as-of", help="giorno di valutazione (YYYY-MM-DD); default ultimo osservato")
    args = ap.parse_args()

    as_of = date.fromisoformat(args.as_of) if args.as_of else None
    if as_of is None:
        rows = _market_rows()
        cand = sorted(date.fromisoformat(r["data"]) for r in rows
                      if date.fromisoformat(r["data"]) >= INIZIO_OSSERVAZIONE)
        if not cand:
            raise SystemExit("Nessun giorno osservato nel ledger.")
        as_of = cand[-1]

    payload = costruisci(as_of)
    p = scrivi(payload)
    log.info("scritto %s", p)
    print(_riepilogo(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())