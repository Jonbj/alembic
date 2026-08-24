"""Attribuzione read-only del P&L active/passive e qualita' decisionale (#284).

Il modulo e' puro: riceve trade, barre e il dossier gia' caricati e non tocca
DB, rete, file di evidenza o parametri live. La decomposizione additiva e'::

    actual_intraday = passive_open_to_close + new_selection + exit_effect

``timing`` e ``sizing`` sono invece viste controfattuali dello stesso ingresso:
non si sommano alla decomposizione ne' fra loro. Ogni asse porta la propria
confidenza, per non mescolare importi misurati e attribuiti.

L'attribuzione beta e' deliberatamente un proxy beta=1, non una regressione
stimata: market = SPY, sector = ETF settoriale meno SPY, residual = resto. La
formula e' dichiarata in ogni riga e non influenza alcuna decisione di trading.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import date, datetime
from math import sqrt
from typing import Any

DECISION_QUALITY_SCHEMA_VERSION = "1.0"

SECTOR_BENCHMARK = {
    "tech": "XLK",
    "semis": "SOXX",
    "financials": "XLF",
    "healthcare": "XLV",
    "energy": "XLE",
}


def _float(value: Any) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def _intraday_return(bar: dict | None) -> float | None:
    if not bar:
        return None
    open_, close = _float(bar.get("open")), _float(bar.get("close"))
    if open_ in (None, 0.0) or close is None:
        return None
    return close / open_ - 1.0


def _same_day(value: str | datetime | None, expected: str) -> bool:
    if value is None:
        return False
    if isinstance(value, datetime):
        return value.date().isoformat() == expected
    try:
        return datetime.fromisoformat(value).date().isoformat() == expected
    except ValueError:
        try:
            return date.fromisoformat(value[:10]).isoformat() == expected
        except ValueError:
            return False


def build_opening_snapshot(
    trades: list[dict],
    bars: dict[str, dict],
    *,
    data: str,
    sector_by_ticker: dict[str, str],
) -> list[dict]:
    """Congela le posizioni vive all'open e il loro no-action P&L a EOD.

    Una posizione chiusa intraday conserva come ``passive_pnl_usd`` il mark
    open->close che avrebbe avuto senza la decisione. ``exit_active_effect``
    corregge quel baseline fino al fill osservato; cosi' il passivo non viene
    riscritto ex post dall'azione che stiamo cercando di misurare.
    """
    market_return = _intraday_return(bars.get("SPY"))
    rows: list[dict] = []
    for trade in sorted(
        trades, key=lambda row: (row.get("trade_id") is None, row.get("trade_id") or 0)
    ):
        ticker = trade["symbol"]
        qty = _float(trade.get("qty"))
        bar = bars.get(ticker)
        open_ = _float(bar.get("open")) if bar else None
        close = _float(bar.get("close")) if bar else None
        missingness: list[str] = []
        if bar is None:
            missingness.append("daily_bar_missing")
        elif open_ is None or close is None:
            missingness.append("daily_open_or_close_missing")
        if qty is None:
            missingness.append("qty_missing")

        passive = (
            (close - open_) * qty
            if close is not None and open_ is not None and qty is not None
            else None
        )
        exited_today = _same_day(trade.get("exit_time"), data)
        exit_price = _float(trade.get("exit_price")) if exited_today else None
        actual_mark = exit_price if exit_price is not None else close
        actual = (
            (actual_mark - open_) * qty
            if actual_mark is not None and open_ is not None and qty is not None
            else None
        )
        exit_effect = (
            actual - passive if actual is not None and passive is not None else None
        )

        opening_notional = (
            open_ * qty if open_ is not None and qty is not None else None
        )
        market_usd = (
            opening_notional * market_return
            if opening_notional is not None and market_return is not None
            else None
        )
        sector = sector_by_ticker.get(ticker)
        sector_benchmark = SECTOR_BENCHMARK.get(sector)
        sector_return = (
            _intraday_return(bars.get(sector_benchmark)) if sector_benchmark else None
        )
        sector_incremental = (
            opening_notional * (sector_return - market_return)
            if opening_notional is not None
            and sector_return is not None
            and market_return is not None
            else None
        )
        residual = None
        if passive is not None and market_usd is not None:
            residual = passive - market_usd - (sector_incremental or 0.0)

        trade_id = trade.get("trade_id")
        cid_payload = (
            trade_id if trade_id is not None else f"{ticker}:{trade.get('entry_time')}"
        )
        rows.append(
            {
                "schema_version": DECISION_QUALITY_SCHEMA_VERSION,
                "data": data,
                "ticker": ticker,
                "strategia": trade.get("strategia"),
                "trade_id": trade_id,
                "causal_event_id": f"opening-trade:{cid_payload}:{data}",
                "qty_open": qty,
                "open_price": open_,
                "close_price": close,
                "opening_notional_usd": opening_notional,
                "exited_intraday": exited_today,
                "exit_price": exit_price,
                "passive_pnl_usd": passive,
                "actual_intraday_pnl_usd": actual,
                "exit_active_effect_usd": exit_effect,
                "confidenza": "misurata",
                "formula": (
                    "passive=(close-open)*qty; actual=(exit_if_today_else_close-open)*qty; "
                    "exit_active_effect=actual-passive"
                ),
                "beta_1_attribution": {
                    "market_benchmark": "SPY",
                    "sector": sector,
                    "sector_benchmark": sector_benchmark,
                    "market_usd": market_usd,
                    "sector_incremental_usd": sector_incremental,
                    "residual_usd": residual,
                    "formula": (
                        "beta=1 proxy: market=notional*SPY_intraday; "
                        "sector=notional*(sector_ETF_intraday-SPY_intraday); residual=passive-market-sector"
                    ),
                },
                "missingness": missingness,
            }
        )
    return rows


def _sum_present(values: list[float | None]) -> float:
    return sum(value for value in values if value is not None)


def _correlation(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 2 or len(xs) != len(ys):
        return None
    x_mean, y_mean = statistics.mean(xs), statistics.mean(ys)
    x_var = sum((x - x_mean) ** 2 for x in xs)
    y_var = sum((y - y_mean) ** 2 for y in ys)
    if x_var == 0 or y_var == 0:
        return None
    covariance = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys))
    return covariance / sqrt(x_var * y_var)


def _entry_rows(dossier: dict) -> list[dict]:
    data = dossier["data"]
    assumptions = dossier.get("decision_quality_assumptions") or {}
    reference = _float(assumptions.get("sizing_reference_usd"))
    reference_source = assumptions.get("sizing_reference_source")
    rows: list[dict] = []
    for index, entry in enumerate(dossier.get("ingressi") or []):
        mtm = _float(entry.get("mtm_eod"))
        open_counterfactual = _float(entry.get("vs_apertura"))
        price, qty = _float(entry.get("entry_price")), _float(entry.get("qty"))
        notional = price * qty if price is not None and qty is not None else None
        trade_return = (
            mtm / notional if mtm is not None and notional not in (None, 0.0) else None
        )
        sizing_counterfactual = (
            trade_return * reference
            if trade_return is not None and reference is not None
            else None
        )
        rows.append(
            {
                "schema_version": DECISION_QUALITY_SCHEMA_VERSION,
                "data": data,
                "ticker": entry.get("symbol"),
                "strategia": entry.get("strategia"),
                "causal_event_id": (
                    f"entry-quality:{data}:{entry.get('symbol')}:{entry.get('ora_utc')}:{index}"
                ),
                "entry_price": price,
                "qty": qty,
                "notional_usd": notional,
                "entry_percentile": _float(entry.get("entry_percentile")),
                "selection": {
                    "baseline": "no_trade",
                    "actual_usd": mtm,
                    "counterfactual_usd": 0.0 if mtm is not None else None,
                    "effect_usd": mtm,
                    "confidenza": "misurata",
                    "verdict": "provisional_eod_mark",
                },
                "timing": {
                    "baseline": "same_ticker_same_qty_entry_at_open",
                    "actual_usd": mtm,
                    "counterfactual_usd": open_counterfactual,
                    "effect_usd": (
                        mtm - open_counterfactual
                        if mtm is not None and open_counterfactual is not None
                        else None
                    ),
                    "confidenza": "attribuita",
                },
                "sizing": {
                    "baseline": "same_ticker_same_entry_reference_notional",
                    "reference_notional_usd": reference,
                    "reference_source": reference_source,
                    "actual_usd": mtm,
                    "counterfactual_usd": sizing_counterfactual,
                    "effect_usd": (
                        mtm - sizing_counterfactual
                        if mtm is not None and sizing_counterfactual is not None
                        else None
                    ),
                    "confidenza": "attribuita",
                },
            }
        )
    return rows


def _exit_rows(dossier: dict) -> list[dict]:
    data = dossier["data"]
    rows: list[dict] = []
    for index, closed in enumerate(dossier.get("chiusure") or []):
        drift = _float(closed.get("drift_post_uscita"))
        rows.append(
            {
                "schema_version": DECISION_QUALITY_SCHEMA_VERSION,
                "data": data,
                "ticker": closed.get("symbol"),
                "strategia": closed.get("strategia"),
                "causal_event_id": (
                    f"exit-quality:{data}:{closed.get('symbol')}:{closed.get('strategia')}:{index}"
                ),
                "pnl_net": _float(closed.get("pnl_net")),
                "holding_hours": _float(closed.get("ore_tenuta")),
                "exit_reason": closed.get("exit_reason"),
                "exit": {
                    "baseline": "same_qty_hold_to_eod",
                    "drift_post_exit_usd": drift,
                    "effect_usd": -drift if drift is not None else None,
                    "confidenza": "attribuita",
                },
            }
        )
    return rows


def _guard_key(row: dict, data: str) -> str:
    signal_id = row.get("signal_id")
    if signal_id is not None:
        return f"guard:signal:{signal_id}"
    return f"guard:{data}:{row.get('symbol')}:{row.get('decision')}"


def _guard_rows(dossier: dict) -> list[dict]:
    data = dossier["data"]
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in dossier.get("guard_decisions") or []:
        grouped[_guard_key(row, data)].append(row)

    output: list[dict] = []
    for causal_id, source_rows in sorted(grouped.items()):
        source_rows.sort(
            key=lambda row: (
                str(row.get("tick_time") or ""),
                row.get("decision_id") or 0,
            )
        )
        first = source_rows[0]
        one_hour = _float(first.get("counterfactual_return_1h"))
        overnight = _float(first.get("counterfactual_return_overnight"))
        observed_return = one_hour if one_hour is not None else overnight
        horizon = (
            "1h"
            if one_hour is not None
            else ("overnight" if overnight is not None else None)
        )
        notional = next(
            (
                value
                for value in (
                    _float(row.get("intended_notional_usd")) for row in source_rows
                )
                if value is not None
            ),
            None,
        )
        cost_return = max(observed_return, 0.0) if observed_return is not None else None
        avoided_return = (
            max(-observed_return, 0.0) if observed_return is not None else None
        )
        output.append(
            {
                "schema_version": DECISION_QUALITY_SCHEMA_VERSION,
                "data": data,
                "causal_event_id": causal_id,
                "ticker": first.get("symbol"),
                "signal_id": first.get("signal_id"),
                "primary_guard": first.get("decision"),
                "guard_reasons": sorted(
                    {row.get("decision") for row in source_rows if row.get("decision")}
                ),
                "source_decision_ids": sorted(
                    row["decision_id"]
                    for row in source_rows
                    if row.get("decision_id") is not None
                ),
                "horizon": horizon,
                "counterfactual_return": observed_return,
                "counterfactual_skip_reason": first.get("counterfactual_skip_reason"),
                "intended_notional_usd": notional,
                "guard_cost_return": cost_return,
                "guard_cost_usd": (
                    cost_return * notional
                    if cost_return is not None and notional is not None
                    else None
                ),
                "avoided_loss_return": avoided_return,
                "avoided_loss_usd": (
                    avoided_return * notional
                    if avoided_return is not None and notional is not None
                    else None
                ),
                "confidenza": "attribuita",
                "formula": (
                    "guard_cost=max(counterfactual_return,0); "
                    "avoided_loss=max(-counterfactual_return,0); one causal event counted once"
                ),
            }
        )
    return output


def _diagnostics(entries: list[dict], exits: list[dict]) -> dict:
    percentiles = [
        row["entry_percentile"]
        for row in entries
        if row.get("entry_percentile") is not None
    ]
    notionals = [
        row["notional_usd"] for row in entries if row.get("notional_usd") is not None
    ]
    sizing_pairs = [
        (row["notional_usd"], row["selection"]["actual_usd"])
        for row in entries
        if row.get("notional_usd") is not None
        and row["selection"].get("actual_usd") is not None
    ]
    holding_pairs = [
        (row["holding_hours"], row["pnl_net"])
        for row in exits
        if row.get("holding_hours") is not None and row.get("pnl_net") is not None
    ]
    return {
        "entry_percentile": {
            "n": len(percentiles),
            "median": statistics.median(percentiles) if percentiles else None,
            "n_sopra_0_70": sum(value > 0.70 for value in percentiles),
            "quota_sopra_0_70": (
                sum(value > 0.70 for value in percentiles) / len(percentiles)
                if percentiles
                else None
            ),
        },
        "holding": {
            "n": len(holding_pairs),
            "median_hours": (
                statistics.median(value[0] for value in holding_pairs)
                if holding_pairs
                else None
            ),
            "pnl_correlation": _correlation(
                [value[0] for value in holding_pairs],
                [value[1] for value in holding_pairs],
            ),
        },
        "sizing": {
            "n": len(notionals),
            "median_notional_usd": statistics.median(notionals) if notionals else None,
            "pnl_correlation": _correlation(
                [value[0] for value in sizing_pairs],
                [value[1] for value in sizing_pairs],
            ),
        },
        "policy_output": "descriptive_only_no_live_tuning",
    }


def build_decision_quality_panel(dossier: dict, *, dossier_hash: str = "") -> dict:
    """Costruisce il pannello giornaliero senza modificare il dossier sorgente."""
    has_snapshot = "snapshot_apertura" in dossier
    has_guards = "guard_decisions" in dossier
    opening = list(dossier.get("snapshot_apertura") or [])
    entries = _entry_rows(dossier)
    exits = _exit_rows(dossier)
    guards = _guard_rows(dossier)

    passive = _sum_present([_float(row.get("passive_pnl_usd")) for row in opening])
    selection = _sum_present([row["selection"]["effect_usd"] for row in entries])
    exit_effect = _sum_present([row["exit"]["effect_usd"] for row in exits])
    active = selection + exit_effect
    missingness = []
    if not has_snapshot:
        missingness.append("opening_snapshot_not_available_in_legacy_dossier")
    if not has_guards:
        missingness.append("guard_decisions_not_available_in_legacy_dossier")

    return {
        "schema_version": DECISION_QUALITY_SCHEMA_VERSION,
        "data": dossier["data"],
        "dossier_hash": dossier_hash,
        "opening_snapshot": opening,
        "active_decisions": {"entries": entries, "exits": exits},
        "guards": guards,
        "summary": {
            "passive_pnl_usd": passive if has_snapshot else None,
            "selection_pnl_usd": selection,
            "exit_effect_usd": exit_effect,
            "active_decision_pnl_usd": active,
            "actual_intraday_pnl_usd": passive + active if has_snapshot else None,
            "market_beta_1_usd": (
                _sum_present(
                    [
                        _float((row.get("beta_1_attribution") or {}).get("market_usd"))
                        for row in opening
                    ]
                )
                if has_snapshot
                else None
            ),
            "sector_beta_1_incremental_usd": (
                _sum_present(
                    [
                        _float(
                            (row.get("beta_1_attribution") or {}).get(
                                "sector_incremental_usd"
                            )
                        )
                        for row in opening
                    ]
                )
                if has_snapshot
                else None
            ),
            "guard_cost_usd": _sum_present(
                [row.get("guard_cost_usd") for row in guards]
            ),
            "guard_avoided_loss_usd": _sum_present(
                [row.get("avoided_loss_usd") for row in guards]
            ),
            "counterfactual_axes_are_additive": False,
        },
        "diagnostics": _diagnostics(entries, exits),
        "missingness": missingness,
        "freeze": {
            "mode": "read_only_measurement",
            "live_thresholds_weights_flags_cooldowns_changed": False,
            "live_size_holding_exit_policy_changed": False,
        },
    }


def build_decision_quality_rollup(panels: list[dict]) -> dict:
    """Serie ordinata e cumulati, senza imputare a zero i giorni incompleti."""
    ordered = sorted(panels, key=lambda panel: panel["data"])
    cumulative_passive = 0.0
    cumulative_active = 0.0
    series: list[dict] = []
    passive_values: list[float] = []
    active_values: list[float] = []
    guard_cost_values: list[float] = []
    guard_benefit_values: list[float] = []
    missing_opening = 0
    missing_guards = 0
    duplicate_guards = 0
    seen_guard_ids: set[str] = set()

    for panel in ordered:
        summary = panel.get("summary") or {}
        passive = _float(summary.get("passive_pnl_usd"))
        active = _float(summary.get("active_decision_pnl_usd"))
        guard_source_missing = "guard_decisions_not_available_in_legacy_dossier" in (
            panel.get("missingness") or []
        )
        daily_guard_cost = 0.0
        daily_guard_benefit = 0.0
        for guard in panel.get("guards") or []:
            causal_id = guard.get("causal_event_id")
            if causal_id in seen_guard_ids:
                duplicate_guards += 1
                continue
            if causal_id is not None:
                seen_guard_ids.add(causal_id)
            cost = _float(guard.get("guard_cost_usd"))
            benefit = _float(guard.get("avoided_loss_usd"))
            if cost is not None:
                daily_guard_cost += cost
            if benefit is not None:
                daily_guard_benefit += benefit
        guard_cost = None if guard_source_missing else daily_guard_cost
        guard_benefit = None if guard_source_missing else daily_guard_benefit
        if passive is None:
            missing_opening += 1
        else:
            passive_values.append(passive)
            cumulative_passive += passive
        if active is not None:
            active_values.append(active)
            cumulative_active += active
        if guard_source_missing:
            missing_guards += 1
        if guard_cost is not None:
            guard_cost_values.append(guard_cost)
        if guard_benefit is not None:
            guard_benefit_values.append(guard_benefit)
        series.append(
            {
                "data": panel["data"],
                "passive_pnl_usd": passive,
                "active_decision_pnl_usd": active,
                "guard_cost_usd": guard_cost,
                "guard_avoided_loss_usd": guard_benefit,
                "cumulative_passive_pnl_usd": (
                    cumulative_passive if passive is not None else None
                ),
                "cumulative_active_decision_pnl_usd": cumulative_active,
                "opening_snapshot_complete": passive is not None,
            }
        )

    return {
        "schema_version": DECISION_QUALITY_SCHEMA_VERSION,
        "n_giorni": len(ordered),
        "n_giorni_snapshot_apertura_mancante": missing_opening,
        "n_giorni_guard_mancanti": missing_guards,
        "n_guard_duplicati_scartati": duplicate_guards,
        "totali_usd": {
            "passive_pnl_usd": sum(passive_values),
            "active_decision_pnl_usd": sum(active_values),
            "guard_cost_usd": sum(guard_cost_values),
            "guard_avoided_loss_usd": sum(guard_benefit_values),
        },
        "serie": series,
        "policy_output": "descriptive_only_no_live_tuning",
    }
