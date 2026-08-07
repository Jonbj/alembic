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
    for r in sorted(rows, key=lambda r: (r.loss_pct if r.loss_pct is not None else 0.0)):
        pct = "     n/d" if r.loss_pct is None else f"{r.loss_pct * 100:7.2f}%"
        print(f"  {r.symbol:6s} qty={r.qty:10.4f} pnl={pct}  {r.status}")

    alerts = select_unprotected_alerts(rows, threshold)
    print(f"\nalert oltre -{threshold:.0%}: {len(alerts)}")
    for r in alerts:
        print("  " + format_unprotected_alert(r, threshold))


if __name__ == "__main__":
    main()
