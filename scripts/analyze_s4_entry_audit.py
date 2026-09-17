#!/usr/bin/env python3
"""Compute reproducible descriptive metrics for the S4 entry-funnel audit.

This script reads immutable JSONL snapshots only. It does not access the
database, network, cluster, or runtime configuration beyond the data already
embedded in the snapshots. Results are descriptive and do not select a policy.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from statistics import fmean, median, stdev
from typing import Any, Iterable, Mapping

import numpy as np
from scipy.stats import spearmanr


def _read_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSON at {path}:{line_number}") from exc


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _summary(values: Iterable[Any]) -> dict[str, Any]:
    clean = [value for raw in values if (value := _number(raw)) is not None]
    if not clean:
        return {
            "n": 0,
            "mean": None,
            "median": None,
            "sum": None,
            "p10": None,
            "p90": None,
            "positive_rate": None,
        }
    return {
        "n": len(clean),
        "mean": fmean(clean),
        "median": median(clean),
        "sum": sum(clean),
        "p10": float(np.percentile(clean, 10)),
        "p90": float(np.percentile(clean, 90)),
        "positive_rate": sum(value > 0 for value in clean) / len(clean),
    }


def _score_bucket(score: Any) -> str:
    value = _number(score)
    if value is None:
        return "UNKNOWN"
    if value >= 0.30:
        return "LONG_SCORE_GE_030"
    if value > 0:
        return "LONG_SCORE_0_TO_030"
    if value == 0:
        return "NEUTRAL"
    return "NEGATIVE_LONG_ONLY"


def _group_summary(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    materialised = list(rows)
    returns = [row.get("return_to_close") for row in materialised]
    scores = [_number(row.get("score")) for row in materialised]
    valid_directional = [
        (score, ret)
        for score, ret in zip(scores, map(_number, returns))
        if score is not None and ret is not None and score != 0 and ret != 0
    ]
    positive_long = [
        ret
        for score, ret in valid_directional
        if score > 0
    ]
    return {
        "rows": len(materialised),
        "return_to_close": _summary(returns),
        "positive_long_hit_rate": (
            sum(ret > 0 for ret in positive_long) / len(positive_long)
            if positive_long
            else None
        ),
        "positive_long_n": len(positive_long),
        "signed_direction_hit_rate": (
            sum(score * ret > 0 for score, ret in valid_directional)
            / len(valid_directional)
            if valid_directional
            else None
        ),
        "signed_direction_n": len(valid_directional),
    }


def _daily_rank_ic(latest_rows: list[dict], outcome_key: str) -> dict[str, Any]:
    by_day: dict[str, list[dict]] = defaultdict(list)
    for row in latest_rows:
        by_day[row["dossier_date"]].append(row)
    daily: list[dict[str, Any]] = []
    for day, rows in sorted(by_day.items()):
        pairs = [
            (_number(row.get("score")), _number(row.get(outcome_key)))
            for row in rows
        ]
        pairs = [(score, outcome) for score, outcome in pairs if score is not None and outcome is not None]
        if len(pairs) < 3:
            continue
        scores = [pair[0] for pair in pairs]
        outcomes = [pair[1] for pair in pairs]
        if len(set(scores)) < 2 or len(set(outcomes)) < 2:
            continue
        coefficient = float(spearmanr(scores, outcomes).statistic)
        if math.isfinite(coefficient):
            daily.append({"date": day, "n": len(pairs), "ic": coefficient})
    values = [row["ic"] for row in daily]
    mean_ic = fmean(values) if values else None
    daily_std = stdev(values) if len(values) >= 2 else None
    t_stat = (
        mean_ic / (daily_std / math.sqrt(len(values)))
        if mean_ic is not None and daily_std not in (None, 0)
        else None
    )
    return {
        "days": len(daily),
        "mean_daily_ic": mean_ic,
        "daily_ic_std": daily_std,
        "t_stat_descriptive": t_stat,
        "daily": daily,
    }


def _latest_per_symbol_day(stage_rows: list[dict]) -> list[dict]:
    latest: dict[tuple[str, str], dict] = {}
    for row in stage_rows:
        scored_at = ((row.get("stages") or {}).get("scored_at") or {}).get(
            "timestamp"
        )
        key = (row["dossier_date"], row["symbol"])
        prior = latest.get(key)
        prior_at = (
            ((prior.get("stages") or {}).get("scored_at") or {}).get("timestamp")
            if prior
            else None
        )
        if prior is None or (scored_at or "") > (prior_at or ""):
            latest[key] = row
    output = []
    for row in latest.values():
        scored = ((row.get("stages") or {}).get("scored_at") or {})
        forward = row.get("snapshot_forward_returns") or {}
        output.append(
            {
                "dossier_date": row["dossier_date"],
                "symbol": row["symbol"],
                "score": row.get("score"),
                "return_to_close": scored.get("return_to_regular_close"),
                "forward_1d": forward.get("1d"),
                "forward_3d": forward.get("3d"),
                "forward_5d": forward.get("5d"),
            }
        )
    return sorted(output, key=lambda row: (row["dossier_date"], row["symbol"]))


def analyze(snapshot_dir: Path, enrichment_dir: Path) -> dict[str, Any]:
    signals = list(_read_jsonl(snapshot_dir / "signals.jsonl"))
    signals_by_id = {int(row["signal_id"]): row for row in signals}
    intents = list(_read_jsonl(snapshot_dir / "intents.jsonl"))
    stage_rows = list(_read_jsonl(enrichment_dir / "signal_stage_outcomes.jsonl"))
    cases = list(_read_jsonl(enrichment_dir / "alpha_miss_cases.jsonl"))
    case_signals = list(
        _read_jsonl(enrichment_dir / "alpha_miss_case_signals.jsonl")
    )
    annotations = list(
        _read_jsonl(enrichment_dir / "alpha_miss_annotations.jsonl")
    )

    stage_by_signal = {
        int(row["signal_id"]): row
        for row in stage_rows
        if row.get("signal_id") is not None
    }
    submitted_signal_ids = {
        int(row["signal_id"])
        for row in intents
        if row.get("final_reason_code") == "SUBMITTED" and row.get("signal_id") is not None
    }

    scored_rows: list[dict[str, Any]] = []
    for row in stage_rows:
        scored = ((row.get("stages") or {}).get("scored_at") or {})
        signal_id = row.get("signal_id")
        signal = signals_by_id.get(int(signal_id)) if signal_id is not None else None
        scored_rows.append(
            {
                "signal_id": signal_id,
                "score": row.get("score"),
                "fallback": row.get("fallback"),
                "return_to_close": scored.get("return_to_regular_close"),
                "mfe": scored.get("mfe"),
                "mae": scored.get("mae"),
                "quota_intraday": scored.get("quota_movimento_intraday"),
                "source": signal.get("source") if signal else None,
                "content_hash": signal.get("content_hash") if signal else None,
                "submitted": signal_id in submitted_signal_ids,
            }
        )

    score_buckets: dict[str, list[dict]] = defaultdict(list)
    fallback_groups: dict[str, list[dict]] = defaultdict(list)
    submitted_groups: dict[str, list[dict]] = defaultdict(list)
    for row in scored_rows:
        score_buckets[_score_bucket(row["score"])].append(row)
        fallback_groups["fallback" if row.get("fallback") else "ensemble"].append(row)
        submitted_groups["submitted" if row.get("submitted") else "not_submitted"].append(row)

    fanout_by_hash: dict[str, set[str]] = defaultdict(set)
    for signal in signals:
        if signal.get("content_hash"):
            fanout_by_hash[str(signal["content_hash"])].add(str(signal["symbol"]))
    fanout_groups: dict[str, list[dict]] = defaultdict(list)
    for row in scored_rows:
        content_hash = row.get("content_hash")
        if not content_hash:
            fanout_groups["unknown"].append(row)
            continue
        fanout = len(fanout_by_hash[str(content_hash)])
        fanout_groups["single_ticker" if fanout == 1 else "multi_ticker"].append(row)

    latency_keys = (
        "published_to_first_seen",
        "first_seen_to_ingested",
        "ingested_to_scored",
        "published_to_scored",
    )
    latency_minutes = {
        key: _summary(
            _number((row.get("latencies_seconds") or {}).get(key)) / 60
            for row in stage_rows
            if _number((row.get("latencies_seconds") or {}).get(key)) is not None
        )
        for key in latency_keys
    }

    stage_coverage: dict[str, Any] = {}
    for stage_name in (
        "published_at",
        "first_seen_at",
        "ingested_at",
        "scored_at",
        "eligible_cycle_at",
        "order_submitted_at",
        "filled_at",
    ):
        rows = [((row.get("stages") or {}).get(stage_name) or {}) for row in stage_rows]
        stage_coverage[stage_name] = {
            "rows": len(rows),
            "with_price": sum(row.get("price") is not None for row in rows),
            "with_mfe": sum(row.get("mfe") is not None for row in rows),
            "with_mae": sum(row.get("mae") is not None for row in rows),
            "with_return_to_close": sum(
                row.get("return_to_regular_close") is not None for row in rows
            ),
        }

    latest = _latest_per_symbol_day(stage_rows)
    rank_ic = {
        outcome: _daily_rank_ic(latest, outcome)
        for outcome in (
            "return_to_close",
            "forward_1d",
            "forward_3d",
            "forward_5d",
        )
    }

    raw_responses = [
        response
        for signal in signals
        for response in (signal.get("model_outputs") or [])
    ]
    event_types: dict[str, int] = defaultdict(int)
    directness_values: dict[str, int] = defaultdict(int)
    for response in raw_responses:
        event_types[str(response.get("event_type") or "UNKNOWN")] += 1
        directness_values[str(response.get("directness") or "UNKNOWN")] += 1

    miss_opportunity: dict[str, list[dict]] = defaultdict(list)
    for case in cases:
        miss_opportunity[str(case.get("dossier_cause") or "UNKNOWN")].append(case)

    miss_by_cause: dict[str, Any] = {}
    for cause, rows in sorted(miss_opportunity.items()):
        opportunities = [row.get("opportunity_v2") or {} for row in rows]
        miss_by_cause[cause] = {
            "cases": len(rows),
            "gross_opportunity_usd": _summary(
                opportunity.get("gross_opportunity_usd") for opportunity in opportunities
            ),
            "accessible_opportunity_usd": _summary(
                opportunity.get("accessible_opportunity_usd")
                for opportunity in opportunities
            ),
            "net_opportunity_usd": _summary(
                opportunity.get("net_opportunity_usd") for opportunity in opportunities
            ),
        }

    return {
        "schema_version": 1,
        "generated_at": datetime.now().astimezone().isoformat(),
        "policy_output": "DESCRIPTIVE_ONLY",
        "multiplicity_warning": (
            "Exploratory families and horizons are not independent; no policy is selected."
        ),
        "population": {
            "snapshot_signals": len(signals),
            "dossier_stage_signals": len(stage_rows),
            "signals_without_frozen_dossier_stage": len(signals) - len(stage_by_signal),
            "intent_rows": len(intents),
            "submitted_unique_signals": len(submitted_signal_ids),
            "alpha_miss_cases": len(cases),
            "alpha_miss_signal_references": len(case_signals),
            "alpha_miss_annotations": len(annotations),
            "case_signal_references_with_id": sum(
                row.get("signal_id") is not None for row in case_signals
            ),
            "case_signal_exact_joins": sum(
                bool(row.get("exact_join_valid")) for row in case_signals
            ),
            "case_signal_causal_event_links": sum(
                row.get("causal_event_id") is not None for row in case_signals
            ),
        },
        "coverage": {
            "stage": stage_coverage,
            "forward_return_1d": sum(
                signal.get("forward_return_1d") is not None for signal in signals
            ),
            "forward_return_3d": sum(
                signal.get("forward_return_3d") is not None for signal in signals
            ),
            "forward_return_5d": sum(
                signal.get("forward_return_5d") is not None for signal in signals
            ),
        },
        "latency_minutes": latency_minutes,
        "scored_stage": {
            "return_to_close": _summary(row["return_to_close"] for row in scored_rows),
            "mfe": _summary(row["mfe"] for row in scored_rows),
            "mae": _summary(row["mae"] for row in scored_rows),
            "quota_intraday": _summary(row["quota_intraday"] for row in scored_rows),
            "quota_intraday_ge_075": sum(
                (_number(row["quota_intraday"]) or -math.inf) >= 0.75
                for row in scored_rows
            ),
            "quota_intraday_valid_n": sum(
                _number(row["quota_intraday"]) is not None for row in scored_rows
            ),
        },
        "score_buckets": {
            key: _group_summary(rows) for key, rows in sorted(score_buckets.items())
        },
        "fallback_groups": {
            key: _group_summary(rows) for key, rows in sorted(fallback_groups.items())
        },
        "submission_groups": {
            key: _group_summary(rows) for key, rows in sorted(submitted_groups.items())
        },
        "fanout_groups": {
            key: _group_summary(rows) for key, rows in sorted(fanout_groups.items())
        },
        "latest_signal_per_symbol_day": {
            "rows": len(latest),
            "rank_ic": rank_ic,
        },
        "model_feature_coverage": {
            "raw_responses": len(raw_responses),
            "event_type_present": sum(
                response.get("event_type") is not None for response in raw_responses
            ),
            "directness_present": sum(
                response.get("directness") is not None for response in raw_responses
            ),
            "materiality_present": sum(
                response.get("materiality") is not None for response in raw_responses
            ),
            "novelty_present": sum(
                response.get("novelty") is not None for response in raw_responses
            ),
            "event_type_counts": dict(sorted(event_types.items())),
            "directness_counts": dict(sorted(directness_values.items())),
            "fallback_signals": sum(bool(signal.get("fallback_used")) for signal in signals),
            "ensemble_std_ge_030": sum(
                (_number(signal.get("ensemble_std")) or 0) >= 0.30
                for signal in signals
            ),
        },
        "alpha_miss_by_dossier_cause": miss_by_cause,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot-dir", type=Path, required=True)
    parser.add_argument("--enrichment-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    metrics = analyze(args.snapshot_dir, args.enrichment_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(metrics, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, args.output)
    manifest = {
        "schema_version": 1,
        "generated_at": datetime.now().astimezone().isoformat(),
        "mode": "READ_ONLY_DESCRIPTIVE_ANALYSIS",
        "policy_output": "DESCRIPTIVE_ONLY",
        "inputs": {
            "snapshot_dir": str(args.snapshot_dir),
            "enrichment_dir": str(args.enrichment_dir),
        },
        "metrics": {
            "path": args.output.name,
            "sha256": _sha256(args.output),
        },
    }
    manifest_path = args.output.parent / "manifest.json"
    manifest_temporary = manifest_path.with_suffix(".json.tmp")
    with manifest_temporary.open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(manifest_temporary, manifest_path)
    print(json.dumps(metrics["population"], sort_keys=True))


if __name__ == "__main__":
    main()
