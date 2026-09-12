"""Distribuzione quota-movimento x P&L realizzato per #512.

Modulo puro: l'orchestratore carica dossier e P&L, qui si fanno soltanto join
deterministici e aggregazioni descrittive.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

_BUCKETS = ("<0.0", "0.0-0.5", "0.5-1.0", ">=1.0", "DEGENERATE", "MISSING")


def _decision_minute(value: Any) -> str | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value)).strftime("%H:%M")
    except ValueError:
        return None


def late_entry_rows_from_dossiers(dossiers: Sequence[Mapping[str, Any]]) -> list[dict]:
    """Collega ingressi S4 e trade_id senza matching FIFO o assunzioni ambigue."""
    rows: list[dict] = []
    for dossier in dossiers:
        submitted_by_symbol: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
        for intent in dossier.get("intenti_ingresso_s4") or []:
            if intent.get("trade_id") is None:
                continue
            submitted_by_symbol[str(intent.get("symbol") or "")].append(intent)

        used_trade_ids: set[int] = set()
        for entry in dossier.get("ingressi") or []:
            if entry.get("strategia") != "S4":
                continue
            trade_id = entry.get("trade_id")
            if trade_id is None:
                candidates = [
                    intent for intent in submitted_by_symbol.get(
                        str(entry.get("symbol") or ""), []
                    )
                    if int(intent["trade_id"]) not in used_trade_ids
                ]
                same_minute = [
                    intent for intent in candidates
                    if _decision_minute(intent.get("decision_at")) == entry.get("ora_utc")
                ]
                matched = same_minute if len(same_minute) == 1 else candidates
                if len(matched) == 1:
                    trade_id = int(matched[0]["trade_id"])
            if trade_id is not None:
                trade_id = int(trade_id)
                used_trade_ids.add(trade_id)
            rows.append({
                "data": dossier.get("data"),
                "symbol": entry.get("symbol"),
                "ora_utc": entry.get("ora_utc"),
                "quota": entry.get("quota_movimento_precedente_al_segnale"),
                "denominatore_degenere": bool(entry.get("denominatore_degenere")),
                "trade_id": trade_id,
            })
    return rows


def _bucket(row: Mapping[str, Any]) -> str:
    if row.get("denominatore_degenere"):
        return "DEGENERATE"
    quota = row.get("quota")
    if quota is None:
        return "MISSING"
    value = float(quota)
    if value < 0:
        return "<0.0"
    if value < 0.5:
        return "0.0-0.5"
    if value < 1.0:
        return "0.5-1.0"
    return ">=1.0"


def aggregate_late_entry_distribution(
    rows: Sequence[Mapping[str, Any]],
    *,
    pnl_by_trade_id: Mapping[int, float | None],
) -> dict:
    """Pubblica bucket fissi, inclusi missingness e denominatori degeneri."""
    grouped: dict[str, list[Mapping[str, Any]]] = {name: [] for name in _BUCKETS}
    for row in rows:
        grouped[_bucket(row)].append(row)

    output = []
    total_with_pnl = 0
    for name in _BUCKETS:
        bucket_rows = grouped[name]
        pnl_values: list[float] = []
        for row in bucket_rows:
            trade_id = row.get("trade_id")
            if trade_id is None:
                continue
            pnl = pnl_by_trade_id.get(int(trade_id))
            if pnl is not None:
                pnl_values.append(float(pnl))
        total_with_pnl += len(pnl_values)
        output.append({
            "fascia": name,
            "n": len(bucket_rows),
            "n_con_pnl_realizzato": len(pnl_values),
            "somma_pnl_realizzato": round(sum(pnl_values), 6) if pnl_values else None,
            "mediana_pnl_realizzato": (
                statistics.median(pnl_values) if pnl_values else None
            ),
            "win_rate": (
                sum(value > 0 for value in pnl_values) / len(pnl_values)
                if pnl_values else None
            ),
        })

    return {
        "n_ingressi": len(rows),
        "n_con_pnl_realizzato": total_with_pnl,
        "n_senza_identita_trade": sum(row.get("trade_id") is None for row in rows),
        "bucket": output,
        "regola_bucket": (
            "quota non degenere: <0, [0,0.5), [0.5,1), >=1; "
            "denominatore_degenere e quota mancante restano separati"
        ),
    }
