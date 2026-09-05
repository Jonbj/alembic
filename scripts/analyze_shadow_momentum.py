#!/usr/bin/env python3
"""Esegue la misura pre-registrata del momentum shadow (#451).

Il comando legge soltanto i dossier versionati e scrive JSON su stdout. Non
tocca DB, rete, configurazione o file di evidenza protetti dal freeze #171.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Sequence

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.analysis.shadow_momentum import (  # noqa: E402
    ANALYSIS_VERSION,
    BOOTSTRAP_RESAMPLES,
    BOOTSTRAP_SEED,
    LOOKBACK_SESSIONS,
    TARGET_CAUSES,
    build_observations,
    summarize_observations,
)

DEFAULT_DOSSIER_DIR = Path("docs/evidence/dossier")
DEFAULT_START = "2026-08-17"
DEFAULT_END = "2026-08-27"
PREREGISTRATION = "docs/evidence/PREREGISTRAZIONE_SHADOW_MOMENTUM_451.md"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dossier-dir", type=Path, default=DEFAULT_DOSSIER_DIR)
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--end", default=DEFAULT_END)
    parser.add_argument(
        "--bootstrap-resamples",
        type=int,
        default=BOOTSTRAP_RESAMPLES,
    )
    return parser


def _load_dossiers(directory: Path) -> tuple[list[dict[str, Any]], dict[str, str]]:
    dossiers: list[dict[str, Any]] = []
    hashes: dict[str, str] = {}
    for path in sorted(directory.glob("*.json")):
        raw = path.read_bytes()
        payload = json.loads(raw)
        if not isinstance(payload, dict) or not payload.get("data"):
            raise ValueError(f"dossier non valido: {path}")
        dossiers.append(payload)
        hashes[path.name] = hashlib.sha256(raw).hexdigest()
    if not dossiers:
        raise ValueError(f"nessun dossier JSON in {directory}")
    return dossiers, hashes


def _build_output(
    directory: Path,
    dossiers: list[dict[str, Any]],
    hashes: dict[str, str],
    start: str,
    end: str,
    n_bootstrap: int,
) -> dict[str, Any]:
    observations = build_observations(dossiers, start, end)
    return {
        "analysis_version": ANALYSIS_VERSION,
        "specification": {
            "preregistration": PREREGISTRATION,
            "sample_start": start,
            "sample_end": end,
            "target_causes": sorted(TARGET_CAUSES),
            "lookback_sessions": LOOKBACK_SESSIONS,
            "signal_formula": "product(1 + previous_daily_return) - 1",
            "intent_rule": "LONG iff momentum_5d > 0; otherwise ABSTAIN",
            "outcome_source": "opportunity_v2.accessible_opportunity_usd",
            "bootstrap": {
                "method": "percentile_95_two_sided",
                "cluster": "event_date",
                "seed": BOOTSTRAP_SEED,
                "n_resamples": n_bootstrap,
            },
        },
        "provenance": {
            "dossier_dir": str(directory),
            "dossier_count": len(dossiers),
            "dossier_dates": sorted(str(item["data"]) for item in dossiers),
            "sha256": hashes,
        },
        "summary": summarize_observations(observations, n_bootstrap=n_bootstrap),
        "observations": observations,
        "limitations": [
            "conditional ex-post alpha-miss population; not a deployable universe selector",
            "opportunity capture, not strategy P&L",
            "negative-mover counterfactual entries are unavailable in opportunity_v2",
            "descriptive shadow measurement only; no live calibration authorized",
        ],
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.start > args.end:
        raise ValueError("--start deve precedere o coincidere con --end")
    if args.bootstrap_resamples <= 0:
        raise ValueError("--bootstrap-resamples deve essere positivo")

    dossiers, hashes = _load_dossiers(args.dossier_dir)
    output = _build_output(
        args.dossier_dir,
        dossiers,
        hashes,
        args.start,
        args.end,
        args.bootstrap_resamples,
    )
    json.dump(output, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
