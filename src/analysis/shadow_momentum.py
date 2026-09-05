"""Misura pre-registrata del momentum shadow per #451.

Il modulo e' puro: riceve dossier gia' caricati, non legge file, rete o DB e
non modifica il comportamento live. La specifica che vincola il calcolo e' in
``docs/evidence/PREREGISTRAZIONE_SHADOW_MOMENTUM_451.md``.
"""

from __future__ import annotations

import math
import random
from collections import defaultdict
from typing import Any, Iterable

ANALYSIS_VERSION = "shadow_momentum_451_v1"
BOOTSTRAP_SEED = 451
BOOTSTRAP_RESAMPLES = 10_000
LOOKBACK_SESSIONS = 5
TARGET_CAUSES = frozenset({"NO_NEWS", "THIN_NEUTRAL"})


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _momentum_5d(history: list[dict[str, Any]], symbol: str) -> float | None:
    if len(history) != LOOKBACK_SESSIONS:
        return None

    compounded = 1.0
    for dossier in history:
        returns = (dossier.get("mercato") or {}).get("rendimenti") or {}
        daily_return = _finite_number(returns.get(symbol))
        if daily_return is None or daily_return <= -1.0:
            return None
        compounded *= 1.0 + daily_return
    return compounded - 1.0


def build_observations(
    dossiers: Iterable[dict[str, Any]],
    start_date: str,
    end_date: str,
    sample_manifest: Iterable[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Estrae il campione e calcola il segnale usando solo le sedute precedenti."""
    ordered = sorted(dossiers, key=lambda dossier: str(dossier.get("data") or ""))
    dates = [str(dossier.get("data") or "") for dossier in ordered]
    if len(dates) != len(set(dates)):
        raise ValueError("duplicate dossier date")

    manifest_by_key: dict[tuple[str, str], dict[str, Any]] | None = None
    if sample_manifest is not None:
        manifest_by_key = {}
        for manifest_row in sample_manifest:
            key = (str(manifest_row.get("data") or ""), str(manifest_row.get("symbol") or ""))
            if not all(key) or manifest_row.get("causa") not in TARGET_CAUSES:
                raise ValueError(f"invalid sample manifest row: {manifest_row!r}")
            if key in manifest_by_key:
                raise ValueError(f"duplicate sample manifest row: {key!r}")
            manifest_by_key[key] = manifest_row

    observations: list[dict[str, Any]] = []
    seen_manifest_keys: set[tuple[str, str]] = set()
    for index, dossier in enumerate(ordered):
        event_date = dates[index]
        if not start_date <= event_date <= end_date:
            continue

        history = ordered[max(0, index - LOOKBACK_SESSIONS):index]
        history_dates = [str(item.get("data") or "") for item in history]
        for candidate in dossier.get("candidati_miss") or []:
            symbol = str(candidate.get("symbol") or "")
            key = (event_date, symbol)
            manifest_row = manifest_by_key.get(key) if manifest_by_key is not None else None
            if manifest_by_key is not None:
                if manifest_row is None:
                    continue
                cause = manifest_row["causa"]
                seen_manifest_keys.add(key)
            else:
                cause = candidate.get("causa")
                if cause not in TARGET_CAUSES:
                    continue

            momentum = _momentum_5d(history, symbol)
            intent = (
                "NOT_EVALUABLE"
                if momentum is None
                else "LONG"
                if momentum > 0.0
                else "ABSTAIN"
            )

            opportunity = candidate.get("opportunity_v2") or {}
            accessible = _finite_number(opportunity.get("accessible_opportunity_usd"))
            positive_accessible = max(accessible, 0.0) if accessible is not None else None
            missingness: list[str] = []
            if momentum is None:
                missingness.append("momentum_history_incomplete")
            if accessible is None:
                missingness.append("accessible_opportunity_missing")

            observations.append(
                {
                    "data": event_date,
                    "symbol": symbol,
                    "causa": cause,
                    "dossier_causa": candidate.get("causa"),
                    "classification_source": (
                        manifest_row.get("source") if manifest_row is not None else "dossier.causa"
                    ),
                    "history_dates": history_dates,
                    "momentum_5d": momentum,
                    "intent_shadow": intent,
                    "return": _finite_number(candidate.get("return")),
                    "accessible_opportunity_usd": accessible,
                    "positive_accessible_opportunity_usd": positive_accessible,
                    "missingness": missingness,
                }
            )
    if manifest_by_key is not None and seen_manifest_keys != set(manifest_by_key):
        missing = sorted(set(manifest_by_key) - seen_manifest_keys)
        raise ValueError(f"manifest rows not found in dossiers: {missing!r}")
    return observations


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def _cluster_contribution(rows: Iterable[dict[str, Any]]) -> tuple[float, float, int]:
    captured = 0.0
    potential = 0.0
    outcome_rows = 0
    for row in rows:
        positive = _finite_number(row.get("positive_accessible_opportunity_usd"))
        if positive is None:
            continue
        outcome_rows += 1
        potential += positive
        if row.get("intent_shadow") == "LONG":
            captured += positive
    return captured, potential, outcome_rows


def _bootstrap_intervals(
    observations: list[dict[str, Any]],
    n_bootstrap: int,
) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in observations:
        grouped[str(row.get("data") or "")].append(row)

    dates = sorted(grouped)
    result: dict[str, Any] = {
        "method": "percentile_95_two_sided",
        "cluster": "event_date",
        "seed": BOOTSTRAP_SEED,
        "n_clusters": len(dates),
        "n_resamples": n_bootstrap,
        "capture_ratio_ci95": None,
        "captured_mean_usd_per_outcome_row_ci95": None,
    }
    if not dates or n_bootstrap <= 0:
        return result

    contributions = {day: _cluster_contribution(grouped[day]) for day in dates}
    rng = random.Random(BOOTSTRAP_SEED)
    ratios: list[float] = []
    means: list[float] = []
    for _ in range(n_bootstrap):
        captured = 0.0
        potential = 0.0
        outcome_rows = 0
        for _ in dates:
            day = rng.choice(dates)
            day_captured, day_potential, day_rows = contributions[day]
            captured += day_captured
            potential += day_potential
            outcome_rows += day_rows
        if potential > 0.0:
            ratios.append(captured / potential)
        if outcome_rows > 0:
            means.append(captured / outcome_rows)

    ratio_low = _percentile(ratios, 0.025)
    ratio_high = _percentile(ratios, 0.975)
    mean_low = _percentile(means, 0.025)
    mean_high = _percentile(means, 0.975)
    result["capture_ratio_ci95"] = (
        [ratio_low, ratio_high] if ratio_low is not None and ratio_high is not None else None
    )
    result["captured_mean_usd_per_outcome_row_ci95"] = (
        [mean_low, mean_high] if mean_low is not None and mean_high is not None else None
    )
    return result


def summarize_observations(
    observations: Iterable[dict[str, Any]],
    n_bootstrap: int = BOOTSTRAP_RESAMPLES,
) -> dict[str, Any]:
    """Riassume copertura e incertezza senza trasformarle in P&L di strategia."""
    rows = list(observations)
    evaluable = [row for row in rows if row.get("intent_shadow") != "NOT_EVALUABLE"]
    longs = [row for row in rows if row.get("intent_shadow") == "LONG"]
    with_outcome = [
        row
        for row in rows
        if _finite_number(row.get("positive_accessible_opportunity_usd")) is not None
    ]

    potential = sum(float(row["positive_accessible_opportunity_usd"]) for row in with_outcome)
    captured = sum(
        float(row["positive_accessible_opportunity_usd"])
        for row in with_outcome
        if row.get("intent_shadow") == "LONG"
    )
    capture_ratio = captured / potential if potential > 0.0 else None
    captured_mean = captured / len(with_outcome) if with_outcome else None

    long_up = 0
    long_down = 0
    long_direction_missing = 0
    for row in longs:
        session_return = _finite_number(row.get("return"))
        if session_return is None or session_return == 0.0:
            long_direction_missing += 1
        elif session_return > 0.0:
            long_up += 1
        else:
            long_down += 1

    return {
        "analysis_version": ANALYSIS_VERSION,
        "counts": {
            "population": len(rows),
            "momentum_evaluable": len(evaluable),
            "long_intents": len(longs),
            "outcome_available": len(with_outcome),
            "long_up_sessions": long_up,
            "long_down_sessions": long_down,
            "long_session_direction_missing": long_direction_missing,
        },
        "estimates": {
            "accessible_positive_total_usd": potential,
            "accessible_positive_captured_usd": captured,
            "capture_ratio": capture_ratio,
            "captured_mean_usd_per_outcome_row": captured_mean,
        },
        "bootstrap": _bootstrap_intervals(rows, n_bootstrap),
        "interpretation": "opportunity_capture_not_strategy_pnl",
    }
