#!/usr/bin/env python3
"""Rende e verifica la sezione book di un report alpha-miss dal dossier."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.analysis.dossier.report import riconcilia_attivita_book


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dossier", type=Path)
    parser.add_argument("report", type=Path)
    args = parser.parse_args()

    dossier = json.loads(args.dossier.read_text())
    report = riconcilia_attivita_book(args.report.read_text(), dossier)
    temporaneo = args.report.with_suffix(args.report.suffix + ".tmp")
    temporaneo.write_text(report)
    temporaneo.replace(args.report)
    print(
        f"Report riconciliato: {len(dossier.get('ingressi', []))} ingressi, "
        f"{len(dossier.get('chiusure', []))} chiusure"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
