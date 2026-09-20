#!/usr/bin/env python3
"""Proposta di backfill bare-stem per ticker_lookup (#566 / F-077).

Legge le righe correnti di ticker_lookup dal DB live, applica la funzione
``propose_stem_backfill`` (deterministica, in
``src/analysis/dossier/article_coverage.py``) e scrive il risultato come CSV
in ``docs/evidence/proposals/ticker_lookup_stem_backfill.csv``.

Lo script NON scrive nel DB: il freeze #171 vieta modifiche di taratura e la
review umana del CSV e' il vincolo. L'output ha quattro bucket:

    - ``safe``:      stem applicabile senza review ulteriore
    - ``short``:     ticker da 1-2 caratteri o stem < 3 caratteri; richiede
                     conferma umana (es. ``F`` -> ``Ford Motor``)
    - ``collision``: lo stem collide col lessico inglese; da NON aggiungere
                     in automatico perche' riapre il buco dei falsi positivi
                     di #405 (``Apple``, ``Amazon``, ``Shell``, ...)
    - ``noop``:      stem identico a un alias o company_name, niente da fare

Uso:
    set -a; source .env; set +a
    python scripts/propose_ticker_lookup_stem_backfill.py
    python scripts/propose_ticker_lookup_stem_backfill.py --out path/al/file.csv
"""
from __future__ import annotations

import argparse
import csv
import os
import subprocess
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

from src.analysis.dossier.article_coverage import propose_stem_backfill  # noqa: E402


def _fetch_rows() -> list[dict]:
    """Legge ticker_lookup dal DB live via ``docker exec psql``."""
    res = subprocess.run(
        [
            "docker", "exec", "alembic-postgres-1",
            "psql", "-U", "trading", "-d", "trading",
            "-t", "-A", "-F", "|",
            "-c", "SELECT ticker, company_name, aliases FROM ticker_lookup ORDER BY ticker;",
        ],
        capture_output=True, text=True, check=True,
    )
    rows: list[dict] = []
    for line in res.stdout.splitlines():
        parts = line.split("|")
        if len(parts) < 3:
            continue
        ticker, company, aliases_literal = parts[0].strip(), parts[1].strip(), parts[2].strip()
        # psql array literal: '{Oracle Corp,Oracle}' -> ["Oracle Corp", "Oracle"]
        aliases = _parse_pg_array(aliases_literal)
        rows.append({
            "ticker": ticker,
            "company_name": company,
            "aliases": aliases,
        })
    return rows


def _parse_pg_array(value: str) -> list[str]:
    s = value.strip()
    if not s or s == "{}":
        return []
    if s.startswith("{") and s.endswith("}"):
        s = s[1:-1]
    # Split su ',' rispettando le virgolette
    items: list[str] = []
    buf: list[str] = []
    in_quote = False
    for char in s:
        if char == '"':
            in_quote = not in_quote
            continue
        if char == "," and not in_quote:
            items.append("".join(buf).strip())
            buf = []
            continue
        buf.append(char)
    if buf:
        items.append("".join(buf).strip())
    return [item for item in items if item]


def _write_csv(proposal: list[dict], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "ticker", "company_name", "current_aliases",
        "proposed_alias", "bucket", "reason",
    ]
    with out_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in proposal:
            writer.writerow({
                "ticker": row["ticker"],
                "company_name": row["company_name"],
                "current_aliases": "|".join(row["current_aliases"]),
                "proposed_alias": row["proposed_alias"] or "",
                "bucket": row["bucket"],
                "reason": row["reason"],
            })


def _summarise(proposal: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in proposal:
        counts[row["bucket"]] = counts.get(row["bucket"], 0) + 1
    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    default_out = PROJECT_DIR / "docs" / "evidence" / "proposals" / "ticker_lookup_stem_backfill.csv"
    parser.add_argument(
        "--out", type=Path, default=default_out,
        help=f"Path del CSV di proposta (default: {default_out})",
    )
    args = parser.parse_args(argv)

    if not os.environ.get("DATABASE_URL"):
        # Lo script usa docker exec, non DATABASE_URL, ma il parent di solito
        # source .env: avvisiamo se manca per coerenza con gli altri script.
        print("hint: DATABASE_URL non in env (lo script usa docker exec, no impact)", file=sys.stderr)

    rows = _fetch_rows()
    proposal = propose_stem_backfill(rows)
    _write_csv(proposal, args.out)

    counts = _summarise(proposal)
    print(f"Proposte: {len(proposal)} righe -> {args.out}")
    for bucket in ("safe", "short", "collision", "noop"):
        print(f"  {bucket:<10s}: {counts.get(bucket, 0)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())