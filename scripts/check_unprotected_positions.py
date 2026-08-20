#!/usr/bin/env python3
"""Quali posizioni del libro non hanno uno stop, e quali non possono averlo (#161).

Sola lettura su Alpaca: legge posizioni e ordini stop aperti, applica la stessa
classificazione del ciclo portfolio (`src/portfolio/unprotected_positions.py`) e
stampa il libro ordinato per perdita, piu' i messaggi che l'alert manderebbe
adesso. Non invia nulla, non sincronizza nulla, non piazza nessun ordine: serve a
verificare il comportamento dell'alert senza aspettare un ciclo.

Alpaca accetta uno stop solo su almeno 1 azione intera: una posizione sotto quella
soglia e' non proteggibile per costruzione, ed e' la distinzione che il sistema
non faceva da nessuna parte prima di #161.

Uso (le credenziali Alpaca arrivano dall'ambiente, come per gli altri script):
    set -a; source .env; set +a
    uv run python scripts/check_unprotected_positions.py
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

import yaml

_TRADING_YAML = Path(__file__).resolve().parents[1] / "config" / "trading.yaml"


# Il libro del 2026-07-28, come misurato nel corpo di #161. Serve solo da termine
# di paragone stampato accanto a quello di oggi: la decisione dell'operatore del
# 2026-08-06 rimanda la correzione strutturale al 28/09 ma si riserva di riaprirla
# prima "se il rosso si allarga in modo marcato", e senza il punto di partenza
# accanto quella frase non e' misurabile.
_BASELINE_20260728 = {
    "protectable": (35, 26_816.0, 659.79),
    "unprotectable": (13, 5_224.0, -452.40),
}


def _print_sleeves(summary) -> None:
    """Il libro diviso sulla linea di 1 azione, con il confronto col 28/07.

    L'alert per simbolo risponde a "questa posizione sta perdendo oltre il -15%
    senza pavimento sotto". Non risponde alla domanda su cui la decisione si
    riserva di riaprire, che riguarda la sleeve nel suo insieme: quella e' una
    somma, e finora nessuno strumento la calcolava.
    """
    base_p = _BASELINE_20260728["protectable"]
    base_u = _BASELINE_20260728["unprotectable"]
    print()
    print("sleeve (linea = 1 azione intera, sotto cui Alpaca non accetta stop):")
    print(f"  {'':16s} {'n':>4s} {'valore':>12s} {'P&L non real.':>14s}")
    for label, s, b in (
        ("proteggibili", summary.protectable, base_p),
        ("NON protegg.", summary.unprotectable, base_u),
    ):
        print(
            f"  {label:16s} {s.n:4d} {s.market_value:12,.2f} {s.unrealized_pl:14,.2f}"
            f"    (28/07: n={b[0]} ${b[1]:,.0f} ${b[2]:+,.2f})"
        )
    if summary.unprotectable_value_share is None:
        print("  quota non proteggibile del libro: n/d (libro vuoto)")
    else:
        print(
            f"  quota non proteggibile del libro: "
            f"{summary.unprotectable_value_share:.1%} (28/07: 16.3%)"
        )


def main() -> None:
    from alpaca.trading.client import TradingClient
    from alpaca.trading.enums import OrderSide, OrderType, QueryOrderStatus
    from alpaca.trading.requests import GetOrdersRequest

    from src.config import config
    from src.portfolio.fractional_stop_orders import (
        ExistingStopOrder,
        build_protective_stop_plans,
    )
    from src.portfolio.stop_policy import StopPolicy
    from src.portfolio.unprotected_positions import (
        classify_protection,
        format_unprotected_alert,
        select_unprotected_alerts,
        summarize_protection,
    )

    risk_cfg = (yaml.safe_load(open(_TRADING_YAML)) or {}).get("risk", {}) or {}
    threshold = float(risk_cfg.get("unprotected_position_alert_pct", 0.15))

    client = TradingClient(
        api_key=config.ALPACA_API_KEY,
        secret_key=config.ALPACA_SECRET_KEY,
        paper=config.ALPACA_PAPER_MODE,
    )
    positions = client.get_all_positions()
    open_sells = client.get_orders(
        GetOrdersRequest(status=QueryOrderStatus.OPEN, side=OrderSide.SELL)
    )

    stops_by_symbol: dict[str, list] = {}
    for o in open_sells:
        if getattr(o, "type", None) != OrderType.STOP:
            continue
        stops_by_symbol.setdefault(o.symbol, []).append(
            ExistingStopOrder(id=str(o.id), qty=float(o.qty), stop_price=float(o.stop_price))
        )

    # Gli stessi piani che il ciclo calcolerebbe — costruiti, mai eseguiti.
    plans = build_protective_stop_plans(
        positions, stops_by_symbol, StopPolicy(risk_cfg), datetime.now(timezone.utc)
    )
    rows = classify_protection(positions, plans)

    n_unprotectable = sum(1 for r in rows if not r.protectable)
    n_unprotected = sum(1 for r in rows if not r.protected)
    print(
        f"posizioni: {len(rows)} | non proteggibili (qty < 1): {n_unprotectable} "
        f"| senza stop attivo: {n_unprotected}"
    )
    _print_sleeves(summarize_protection(rows))
    for r in sorted(rows, key=lambda r: (r.loss_pct if r.loss_pct is not None else 0.0)):
        pct = "     n/d" if r.loss_pct is None else f"{r.loss_pct * 100:7.2f}%"
        print(f"  {r.symbol:6s} qty={r.qty:10.4f} pnl={pct}  {r.status}")

    alerts = select_unprotected_alerts(rows, threshold)
    print(f"\nalert oltre -{threshold:.0%}: {len(alerts)}")
    for r in alerts:
        print("  " + format_unprotected_alert(r, threshold))


if __name__ == "__main__":
    main()
