#!/usr/bin/env python3
"""P&L totale per sleeve (realized + mark-to-market delle aperte), issue #210.

Orchestratore SOTTILE: fa l'I/O (Alpaca, Postgres) e delega ogni calcolo al
modulo puro ``src/analysis/dossier/total_pnl.py``. Nessuna formula vive qui,
come in ``scripts/economic_pnl_scoreboard.py``.

Affianca al P&L realizzato il MTMark delle posizioni ancora aperte, cosi'
il verdetto del 28/09 possa leggere una metrica che non e' selezionata
avversariamente dalla regola d'uscita di S1 (#165: chiude quando perde rango,
le vincenti restano aperte).

Sola lettura su Postgres e Alpaca. Non tocca ``findings.json`` ne'
``market_daily.jsonl``: quelli sono append-only e scritti solo dalle sessioni
col protocollo del ledger. L'output va in
``docs/evidence/realized_total_pnl.json`` (parallelo a ``economic_pnl.json``,
strumentazione ammessa dal freeze #171).

Uso:
    set -a; source .env; set +a
    uv run python scripts/realized_total_pnl.py
    uv run python scripts/realized_total_pnl.py --as-of 2026-08-20
"""
from __future__ import annotations

import argparse
import json
import logging
import os
from datetime import date, datetime, timedelta
from pathlib import Path

from src.analysis.dossier.total_pnl import compute_total_pnl

log = logging.getLogger(__name__)

PROJECT_DIR = Path(__file__).resolve().parents[1]
OUT_PATH = PROJECT_DIR / "docs" / "evidence" / "realized_total_pnl.json"
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


def _load_closes(symbols: list[str], window_start: date, as_of: date) -> dict:
    """Barre giornaliere SIP (adjustment=all) per i simboli delle posizioni.

    Restituisce ``{giorno: {simbolo: close}}``. La stessa fonte usata da
    ``economic_pnl_scoreboard.py``: una sola verita' sui prezzi per la
    finestra di osservazione.
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


def _load_trades(as_of: date) -> list[dict]:
    """Tutti i trade entrati prima della fine della finestra.

    A differenza di ``economic_pnl_scoreboard`` (che serve solo le posizioni
    che toccano la finestra di mark-from-first-day), qui vogliamo anche le
    chiusure avvenute dentro la finestra per il realized. Le posizioni chiuse
    *prima* dell'inizio finestra sono ammesse nella query ma ignorate dal
    modulo puro (realized=0 per costruzione se exit_date < window_start).
    """
    rows = _psql(
        f"SELECT symbol, stop_strategy, signal_id::text, entry_price, "
        f"entry_time::date, exit_price, exit_time::date, net_pnl::text, qty "
        f"FROM trades WHERE entry_time < '{as_of}'::date + 1 "
        f"ORDER BY entry_time;"
    )
    out = []
    for r in rows:
        out.append({
            "symbol": r[0],
            "stop_strategy": r[1] or None,
            "signal_id": int(r[2]) if r[2] not in (None, "") else None,
            "entry_price": float(r[3]) if r[3] not in (None, "") else None,
            "entry_date": date.fromisoformat(r[4]) if r[4] else None,
            "exit_price": float(r[5]) if r[5] not in (None, "") else None,
            "exit_date": date.fromisoformat(r[6]) if r[6] else None,
            "net_pnl": float(r[7]) if r[7] not in (None, "") else None,
            "qty": float(r[8]) if r[8] not in (None, "") else None,
        })
    return out


def _current_prices(closes: dict, as_of: date) -> dict[str, float]:
    """Prezzo corrente = close dell'ultimo giorno di borsa disponibile.

    Stessa convenzione del P&L economico: il mark-to-market delle posizioni
    aperte e' letto dall'ultimo close SIP noto, non dal prezzo live Alpaca.
    Vantaggio: stessa fonte del realized-implicit del modulo economico, e
    deterministico (un solo numero per simbolo al giorno di valutazione).
    """
    giorni = sorted(d for d in closes if d <= as_of)
    if not giorni:
        return {}
    ultimo = giorni[-1]
    return dict(closes[ultimo])


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
    trades = _load_trades(as_of)
    simboli = sorted({t["symbol"] for t in trades if t.get("symbol")})
    closes = _load_closes(simboli, INIZIO_OSSERVAZIONE, as_of)
    prezzi_correnti = _current_prices(closes, as_of)

    pnl = compute_total_pnl(trades, prezzi_correnti, INIZIO_OSSERVAZIONE)

    return {
        "data": as_of.isoformat(),
        "generato_il": datetime.now().astimezone().isoformat(),
        "fonte_prezzi": "Alpaca SIP, adjustment=all",
        "fonte_ledger": "docs/evidence/market_daily.jsonl (n/a per realized+MTMark)",
        "finestra_inizio": INIZIO_OSSERVAZIONE.isoformat(),
        "definizione": (
            "P&L totale per sleeve: SUM(net_pnl) delle chiuse nella finestra "
            "+ SUM((close_ultimo_giorno - entry_price) * qty) delle aperte. "
            "Affianca il realized per leggere le aperte che la regola d'uscita "
            "di S1 (#165) non chiude. Vedi issue #210."
        ),
        "attribuzione": (
            "stop_strategy -> quella strategia; else signal_id -> S4; else "
            "CONTAMINAZIONE. Stessa attribuzione del P&L economico (#278)."
        ),
        "pnl_totale": pnl,
    }


def scrivi(payload: dict) -> Path:
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(_jsonable(payload), indent=2, ensure_ascii=False))
    tmp.replace(OUT_PATH)  # atomica
    return OUT_PATH


def _riepilogo(payload: dict) -> str:
    pnl = payload["pnl_totale"]
    s1, s4, cont, book = pnl["S1"], pnl["S4"], pnl["CONTAMINAZIONE"], pnl["BOOK"]
    return (
        f"as_of {payload['data']} (finestra da {payload['finestra_inizio']})\n"
        f"  S1: realized {s1['realized']:+.2f}$ + MTMark {s1['mark_to_market_open']:+.2f}$ "
        f"= total {s1['total']:+.2f}$  "
        f"(chiuse={s1['n_closed']}, aperte_marcate={s1['n_open_marked']}, "
        f"aperte_non_marcate={s1['n_open_unmarked']})\n"
        f"  S4: realized {s4['realized']:+.2f}$ + MTMark {s4['mark_to_market_open']:+.2f}$ "
        f"= total {s4['total']:+.2f}$  "
        f"(chiuse={s4['n_closed']}, aperte_marcate={s4['n_open_marked']}, "
        f"aperte_non_marcate={s4['n_open_unmarked']})\n"
        f"  CONTAM: realized {cont['realized']:+.2f}$ + MTMark "
        f"{cont['mark_to_market_open']:+.2f}$ = total {cont['total']:+.2f}$  "
        f"(chiuse={cont['n_closed']}, aperte_marcate={cont['n_open_marked']}, "
        f"aperte_non_marcate={cont['n_open_unmarked']})\n"
        f"  BOOK: total {book['total']:+.2f}$  "
        f"(chiuse={book['n_closed']}, aperte_marcate={book['n_open_marked']}, "
        f"aperte_non_marcate={book['n_open_unmarked']})"
    )


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--as-of", help="giorno di valutazione (YYYY-MM-DD); default oggi")
    args = ap.parse_args()

    as_of = date.fromisoformat(args.as_of) if args.as_of else date.today()

    payload = costruisci(as_of)
    p = scrivi(payload)
    log.info("scritto %s", p)
    print(_riepilogo(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
