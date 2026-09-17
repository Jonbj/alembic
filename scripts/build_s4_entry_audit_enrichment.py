#!/usr/bin/env python3
"""Build immutable Alpha Miss and point-in-time outcome enrichment tables.

Inputs are frozen dossier JSON, the findings ledger, trading sector metadata,
and a read-only S4 funnel snapshot. No database or network access is performed.
Unknown relationships stay explicit; the builder never uses fuzzy or nearest
matching.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tempfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping
from zoneinfo import ZoneInfo

import yaml

from src.analysis.dossier.decision_quality import SECTOR_BENCHMARK


NEW_YORK = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")


def _read_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSON at {path}:{line_number}") from exc


def _write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> int:
    count = 0
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            json.dump(
                dict(row),
                handle,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            handle.write("\n")
            count += 1
        handle.flush()
        os.fsync(handle.fileno())
    return count


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(dict(value), handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _as_float(value: Any) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def _same_float(left: Any, right: Any, tolerance: float = 1e-12) -> bool | None:
    left_float = _as_float(left)
    right_float = _as_float(right)
    if left_float is None or right_float is None:
        return None
    return abs(left_float - right_float) <= tolerance


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _session_date(timestamp: str) -> str:
    parsed = _parse_timestamp(timestamp)
    if parsed is None:
        raise ValueError("decision_slot is required")
    return parsed.astimezone(NEW_YORK).date().isoformat()


def _relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _sector_by_symbol(trading_yaml: Path) -> dict[str, str]:
    with trading_yaml.open(encoding="utf-8") as handle:
        sectors = (yaml.safe_load(handle) or {}).get("sectors") or {}
    return {
        str(symbol): str(sector)
        for sector, symbols in sectors.items()
        for symbol in (symbols or [])
    }


def _residual(symbol_return: Any, benchmark_return: Any) -> float | None:
    symbol_value = _as_float(symbol_return)
    benchmark_value = _as_float(benchmark_return)
    if symbol_value is None or benchmark_value is None:
        return None
    return symbol_value - benchmark_value


def _stage_outcomes(stages: Mapping[str, Any], regular: Mapping[str, Any]) -> dict:
    regular_close = _as_float(regular.get("close"))
    regular_close_at = _parse_timestamp(regular.get("last_bar_at"))
    output: dict[str, Any] = {}
    for stage_name, raw_stage in stages.items():
        stage = dict(raw_stage or {})
        stage_price = _as_float(stage.get("price"))
        stage_at = _parse_timestamp(stage.get("bar_timestamp") or stage.get("timestamp"))
        return_to_close = None
        return_missing_reason = None
        if stage_price is None or stage_price <= 0:
            return_missing_reason = "STAGE_PRICE_MISSING"
        elif regular_close is None or regular_close <= 0:
            return_missing_reason = "REGULAR_CLOSE_MISSING"
        elif stage_at is None or regular_close_at is None:
            return_missing_reason = "STAGE_OR_CLOSE_TIMESTAMP_MISSING"
        elif stage_at > regular_close_at:
            return_missing_reason = "STAGE_AFTER_REGULAR_CLOSE"
        else:
            return_to_close = regular_close / stage_price - 1.0
        stage["return_to_regular_close"] = return_to_close
        stage["return_to_regular_close_missing_reason"] = return_missing_reason
        output[stage_name] = stage
    return output


def _load_snapshot(snapshot_dir: Path) -> tuple[dict[int, dict], dict[str, Any]]:
    signals = {
        int(row["signal_id"]): row
        for row in _read_jsonl(snapshot_dir / "signals.jsonl")
    }
    causal_events_by_signal: dict[int, set[str]] = defaultdict(set)
    intents_by_session_symbol: dict[tuple[str, str], list[dict[str, Any]]] = (
        defaultdict(list)
    )
    for row in _read_jsonl(snapshot_dir / "intents.jsonl"):
        signal_id = row.get("signal_id")
        if signal_id is not None and row.get("causal_event_id"):
            causal_events_by_signal[int(signal_id)].add(str(row["causal_event_id"]))
        key = (_session_date(row["decision_slot"]), str(row["symbol"]))
        intents_by_session_symbol[key].append(
            {
                "intent_id": row["intent_id"],
                "signal_id": signal_id,
                "causal_event_id": row.get("causal_event_id"),
                "final_reason_code": row.get("final_reason_code"),
            }
        )
    for signal_id, causal_events in causal_events_by_signal.items():
        if len(causal_events) > 1:
            raise ValueError(
                f"signal_id {signal_id} has multiple causal_event_id values: "
                f"{sorted(causal_events)}"
            )
    return signals, {
        "causal_events_by_signal": causal_events_by_signal,
        "intents_by_session_symbol": intents_by_session_symbol,
    }


def _signal_join(
    signal_reference: Mapping[str, Any],
    dossier_date: str,
    ticker: str,
    snapshot_signals: Mapping[int, Mapping[str, Any]],
    causal_events_by_signal: Mapping[int, set[str]],
) -> dict[str, Any]:
    signal_id = signal_reference.get("signal_id")
    missingness: list[str] = []
    snapshot_signal = None
    if signal_id is None:
        missingness.append("DOSSIER_SIGNAL_ID_MISSING")
    else:
        signal_id = int(signal_id)
        snapshot_signal = snapshot_signals.get(signal_id)
        if snapshot_signal is None:
            missingness.append("SIGNAL_NOT_IN_SNAPSHOT_POPULATION")

    ticker_matches = None
    generated_date_matches = None
    score_matches = None
    article_matches = None
    causal_event_id = None
    if snapshot_signal is not None:
        ticker_matches = snapshot_signal.get("symbol") == ticker
        generated_at = _parse_timestamp(snapshot_signal.get("generated_at"))
        generated_date_matches = (
            generated_at.date().isoformat() == dossier_date if generated_at else None
        )
        score_matches = _same_float(signal_reference.get("score"), snapshot_signal.get("score"))
        canonical_article_id = signal_reference.get("canonical_article_id")
        content_hash = snapshot_signal.get("content_hash")
        article_matches = (
            canonical_article_id == f"content:{content_hash}"
            if canonical_article_id is not None and content_hash is not None
            else None
        )
        for label, result in (
            ("TICKER_MISMATCH", ticker_matches),
            ("GENERATED_DATE_MISMATCH", generated_date_matches),
            ("SCORE_MISMATCH", score_matches),
            ("ARTICLE_ID_MISMATCH", article_matches),
        ):
            if result is False:
                missingness.append(label)
        causal_events = causal_events_by_signal.get(signal_id, set())
        if causal_events:
            causal_event_id = next(iter(causal_events))
        else:
            missingness.append("NO_S4_INTENT_CAUSAL_EVENT")

    identity_checks = [
        result
        for result in (
            ticker_matches,
            generated_date_matches,
            score_matches,
            article_matches,
        )
        if result is not None
    ]
    return {
        "signal_id": signal_id,
        "causal_event_id": causal_event_id,
        "snapshot_signal_found": snapshot_signal is not None,
        "identity_checks": {
            "ticker_matches": ticker_matches,
            "generated_date_matches": generated_date_matches,
            "score_matches": score_matches,
            "canonical_article_matches_content_hash": article_matches,
        },
        "exact_join_valid": snapshot_signal is not None and all(identity_checks),
        "missingness": missingness,
    }


def _build_tables(
    *,
    project_root: Path,
    dossier_dir: Path,
    findings_path: Path,
    snapshot_dir: Path,
    trading_yaml: Path,
) -> dict[str, list[dict[str, Any]]]:
    snapshot_signals, indexes = _load_snapshot(snapshot_dir)
    causal_events_by_signal = indexes["causal_events_by_signal"]
    intents_by_session_symbol = indexes["intents_by_session_symbol"]
    sectors = _sector_by_symbol(trading_yaml)

    cases: list[dict[str, Any]] = []
    case_signals: list[dict[str, Any]] = []
    signal_stages: list[dict[str, Any]] = []
    seen_case_ids: set[str] = set()
    seen_stage_signal_ids: set[int] = set()

    for dossier_path in sorted(dossier_dir.glob("*.json")):
        dossier = json.loads(dossier_path.read_text(encoding="utf-8"))
        dossier_date = str(dossier["data"])
        source_path = _relative(dossier_path, project_root)
        market_returns = (dossier.get("mercato") or {}).get("rendimenti") or {}
        event_context = (dossier.get("event_market_context") or {}).get("per_symbol") or {}

        for case in dossier.get("candidati_miss") or []:
            ticker = str(case["symbol"])
            case_id = f"alpha-miss:{dossier_date}:{ticker}"
            if case_id in seen_case_ids:
                raise ValueError(f"duplicate Alpha Miss case: {case_id}")
            seen_case_ids.add(case_id)
            references = case.get("segnali") or []
            reference_signal_ids = {
                int(reference["signal_id"])
                for reference in references
                if reference.get("signal_id") is not None
            }
            same_ticker_intents = intents_by_session_symbol.get(
                (dossier_date, ticker), []
            )
            causal_intents = [
                intent
                for intent in same_ticker_intents
                if intent.get("signal_id") in reference_signal_ids
            ]
            case_missingness: list[str] = ["ANALYST_CAUSE_NOT_STRUCTURED"]
            if not references:
                case_missingness.append("NO_SIGNAL")
            if references and len(reference_signal_ids) < len(references):
                case_missingness.append("DOSSIER_SIGNAL_ID_MISSING")
            if not same_ticker_intents:
                case_missingness.append("NO_SAME_SESSION_TICKER_INTENT")
            if reference_signal_ids and not causal_intents:
                case_missingness.append("NO_CAUSAL_INTENT_IN_SESSION")

            cases.append(
                {
                    "schema_version": 1,
                    "case_id": case_id,
                    "session_date": dossier_date,
                    "ticker": ticker,
                    "dossier_schema_version": dossier.get("schema_version"),
                    "dossier_source_path": source_path,
                    "report_source_path": (
                        f"docs/ALPHA_MISS_REPORT_{dossier_date}.md"
                        if (project_root / f"docs/ALPHA_MISS_REPORT_{dossier_date}.md").exists()
                        else None
                    ),
                    "return": case.get("return"),
                    "news_count": case.get("news_count"),
                    "in_portfolio": case.get("in_portafoglio"),
                    "dossier_cause": case.get("causa"),
                    "analyst_cause": None,
                    "opportunity_v2": case.get("opportunity_v2"),
                    "fanout_share": case.get("quota_righe_fanout"),
                    "max_score_own": case.get("max_score_own"),
                    "max_score_fanout": case.get("max_score_fanout"),
                    "event_market_context": event_context.get(ticker),
                    "signal_reference_count": len(references),
                    "signal_ids_present": sorted(reference_signal_ids),
                    "same_session_ticker_intent_count": len(same_ticker_intents),
                    "causal_intent_count": len(causal_intents),
                    "causal_intent_ids": [row["intent_id"] for row in causal_intents],
                    "context_only_intent_count": len(same_ticker_intents) - len(causal_intents),
                    "context_only_is_causal": False,
                    "case_missingness": sorted(set(case_missingness)),
                }
            )

            for reference_index, reference in enumerate(references):
                join = _signal_join(
                    reference,
                    dossier_date,
                    ticker,
                    snapshot_signals,
                    causal_events_by_signal,
                )
                case_signals.append(
                    {
                        "schema_version": 1,
                        "case_signal_id": f"{case_id}:signal:{reference_index}",
                        "case_id": case_id,
                        "session_date": dossier_date,
                        "ticker": ticker,
                        "reference_index": reference_index,
                        "dossier_source_path": source_path,
                        "dossier_signal": reference,
                        **join,
                    }
                )

        regular_by_symbol: dict[str, Mapping[str, Any]] = {}
        for timeline_row in dossier.get("timeline") or []:
            if timeline_row.get("kind") != "signal":
                continue
            signal_id = timeline_row.get("signal_id")
            symbol = str(timeline_row.get("symbol"))
            if signal_id is not None:
                signal_id = int(signal_id)
                if signal_id in seen_stage_signal_ids:
                    raise ValueError(f"duplicate dossier timeline signal_id: {signal_id}")
                seen_stage_signal_ids.add(signal_id)
            regular = (timeline_row.get("sessioni") or {}).get("regular") or {}
            regular_by_symbol[symbol] = regular
            snapshot_signal = snapshot_signals.get(signal_id) if signal_id is not None else None
            sector = sectors.get(symbol)
            sector_etf = SECTOR_BENCHMARK.get(sector) if sector else None
            symbol_return = market_returns.get(symbol)
            spy_return = market_returns.get("SPY")
            sector_return = market_returns.get(sector_etf) if sector_etf else None
            missingness: list[str] = []
            if signal_id is None:
                missingness.append("DOSSIER_SIGNAL_ID_MISSING")
            elif snapshot_signal is None:
                missingness.append("SIGNAL_NOT_IN_SNAPSHOT_POPULATION")
            if symbol_return is None:
                missingness.append("SESSION_RETURN_MISSING")
            if sector_etf and sector_return is None:
                missingness.append("SECTOR_BENCHMARK_RETURN_MISSING")

            signal_stages.append(
                {
                    "schema_version": 1,
                    "dossier_date": dossier_date,
                    "dossier_source_path": source_path,
                    "signal_id": signal_id,
                    "news_log_id": timeline_row.get("news_log_id"),
                    "symbol": symbol,
                    "score": timeline_row.get("score"),
                    "fallback": timeline_row.get("fallback"),
                    "is_mover": timeline_row.get("is_mover"),
                    "order_id": timeline_row.get("order_id"),
                    "trade_id": timeline_row.get("trade_id"),
                    "latencies_seconds": timeline_row.get("latenze_secondi"),
                    "movement": timeline_row.get("movimento"),
                    "sessions": timeline_row.get("sessioni"),
                    "stages": _stage_outcomes(timeline_row.get("stages") or {}, regular),
                    "session_close_to_close": {
                        "symbol_return": symbol_return,
                        "spy_return": spy_return,
                        "sector": sector,
                        "sector_etf": sector_etf,
                        "sector_return": sector_return,
                        "residual_vs_spy_beta_1": _residual(symbol_return, spy_return),
                        "residual_vs_sector_beta_1": _residual(
                            symbol_return, sector_return
                        ),
                    },
                    "snapshot_signal_found": snapshot_signal is not None,
                    "snapshot_forward_returns": {
                        "1d": snapshot_signal.get("forward_return_1d"),
                        "3d": snapshot_signal.get("forward_return_3d"),
                        "5d": snapshot_signal.get("forward_return_5d"),
                    }
                    if snapshot_signal
                    else None,
                    "missingness": sorted(set(missingness)),
                }
            )

    findings = json.loads(findings_path.read_text(encoding="utf-8"))
    annotations: list[dict[str, Any]] = []
    for finding in findings.get("findings") or []:
        for occurrence_index, occurrence in enumerate(finding.get("occorrenze") or []):
            source = str(occurrence.get("fonte") or "")
            if "ALPHA_MISS_REPORT_" not in source:
                continue
            source_file = source.split()[0].rstrip(",")
            annotations.append(
                {
                    "schema_version": 1,
                    "annotation_id": (
                        f"alpha-miss-annotation:{finding.get('id')}:"
                        f"{occurrence.get('data')}:{occurrence_index}"
                    ),
                    "finding_id": finding.get("id"),
                    "finding_title": finding.get("titolo"),
                    "finding_type": finding.get("tipo"),
                    "finding_confidence": finding.get("confidenza"),
                    "scope_kind": "SESSION",
                    "session_date": occurrence.get("data"),
                    "ticker": None,
                    "signal_id": None,
                    "causal_event_id": None,
                    "intent_id": None,
                    "link_method": "SESSION_ONLY",
                    "source_path": f"docs/{source_file}",
                    "source_locator": source[len(source_file) :].strip() or None,
                    "cost_usd": occurrence.get("costo_usd"),
                    "text": occurrence.get("nota"),
                    "missingness": ["NO_STRUCTURED_ROW_KEY"],
                }
            )

    return {
        "alpha_miss_cases.jsonl": sorted(cases, key=lambda row: row["case_id"]),
        "alpha_miss_case_signals.jsonl": sorted(
            case_signals, key=lambda row: row["case_signal_id"]
        ),
        "alpha_miss_annotations.jsonl": sorted(
            annotations, key=lambda row: row["annotation_id"]
        ),
        "signal_stage_outcomes.jsonl": sorted(
            signal_stages,
            key=lambda row: (
                row["dossier_date"],
                row["signal_id"] if row["signal_id"] is not None else -1,
                row["symbol"],
            ),
        ),
    }


def build_enrichment(
    *,
    project_root: Path,
    dossier_dir: Path,
    findings_path: Path,
    snapshot_dir: Path,
    trading_yaml: Path,
    output_dir: Path,
) -> dict[str, Any]:
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite immutable enrichment: {output_dir}")
    tables = _build_tables(
        project_root=project_root,
        dossier_dir=dossier_dir,
        findings_path=findings_path,
        snapshot_dir=snapshot_dir,
        trading_yaml=trading_yaml,
    )
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    temporary_dir = Path(
        tempfile.mkdtemp(prefix=f".{output_dir.name}.", dir=output_dir.parent)
    )
    try:
        table_manifest: dict[str, Any] = {}
        for file_name, rows in tables.items():
            table_path = temporary_dir / file_name
            row_count = _write_jsonl(table_path, rows)
            table_manifest[file_name] = {
                "rows": row_count,
                "sha256": _sha256(table_path),
            }
        manifest = {
            "schema_version": 1,
            "generated_at": datetime.now().astimezone().isoformat(),
            "mode": "READ_ONLY_OFFLINE_ENRICHMENT",
            "join_policy": "EXACT_KEYS_ONLY",
            "unknown_policy": "PRESERVE_UNKNOWN",
            "inputs": {
                "snapshot_dir": _relative(snapshot_dir, project_root),
                "dossier_dir": _relative(dossier_dir, project_root),
                "findings": _relative(findings_path, project_root),
                "trading_yaml": _relative(trading_yaml, project_root),
            },
            "tables": table_manifest,
        }
        _write_json(temporary_dir / "manifest.json", manifest)
        os.replace(temporary_dir, output_dir)
        return manifest
    except Exception:
        shutil.rmtree(temporary_dir, ignore_errors=True)
        raise


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--snapshot-dir",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--dossier-dir",
        type=Path,
        default=project_root / "docs/evidence/dossier",
    )
    parser.add_argument(
        "--findings",
        type=Path,
        default=project_root / "docs/evidence/findings.json",
    )
    parser.add_argument(
        "--trading-yaml",
        type=Path,
        default=project_root / "config/trading.yaml",
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    manifest = build_enrichment(
        project_root=project_root,
        dossier_dir=args.dossier_dir,
        findings_path=args.findings,
        snapshot_dir=args.snapshot_dir,
        trading_yaml=args.trading_yaml,
        output_dir=args.output_dir,
    )
    print(json.dumps(manifest["tables"], sort_keys=True))


if __name__ == "__main__":
    main()
